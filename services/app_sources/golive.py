"""عميل حكاية TV + GoLive — منقول من §1 في مواصفة التطبيق.

الاتنين على نفس المضيف، والفرق بس في هيدر الـ User-Agent وشكل الخرايط.
كل الدوال async وبترجّع قواميس مطبّعة، وأي فشل شبكة يرجّع [] أو None.
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from . import keys
from . import http

logger = logging.getLogger(__name__)

# 1.1 — نفس المضيف للاتنين
BASE_URL = "https://admin.golive-pro.online/api"
# 1.3 — حجم الصفحة الثابت
LIMIT = 35

# 1.5 — فئات الأفلام (key → label → GUID المستخدم كـ categoryId)
MOVIE_CATEGORIES: Dict[str, Dict[str, str]] = {
    "arabic": {"label": "أفلام عربية", "categoryId": "2185cd2d-f379-4584-8caa-5884bced7150"},
    "foreign": {"label": "أفلام أجنبية", "categoryId": "9ec354e5-4707-4161-9dab-b51f899b29d8"},
    "arabic_all": {"label": "كل الأفلام العربية", "categoryId": "a41d4764-d74e-4df3-a5aa-51e1725fe42e"},
    "foreign_general": {"label": "أفلام أجنبية عامة", "categoryId": "7bd112fc-a3c2-49ab-a3d7-5287ffd1d045"},
}

# 1.5 — فئات المسلسلات
SERIES_CATEGORIES: Dict[str, Dict[str, str]] = {
    "arabic": {"label": "مسلسلات عربية", "categoryId": "dd185bc6-1dfd-45c2-9189-13c47f672e5a"},
}

# 1.5 — أنواع الأفلام (key → الاسم العربي اللي يتبعت في باراميتر genre)
MOVIE_GENRES: Dict[str, str] = {
    "action": "أكشن",
    "comedy": "كوميدي",
    "drama": "دراما",
    "horror": "رعب",
    "sci_fi": "خيال علمي",
    "romance": "رومانسي",
    "thriller": "إثارة",
    "adventure": "مغامرة",
    "animation": "أنيميشن",
    "crime": "جريمة",
    "documentary": "وثائقي",
    "family": "عائلي",
}

# 1.5 — أوضاع بحث المسلسلات (key → النص العربي اللي يتبعت في باراميتر search)
SERIES_KEYWORDS: Dict[str, str] = {
    "foreign": "اجنبي",
    "turkish": "تركي",
    "korean": "كوري",
    "anime": "انمي",
    "dubbed": "مدبلج",
    "ramadan": "رمضان",
}

DEFAULT_SOURCE_LABEL = "سيرفر مشاهدة"
DEFAULT_TITLE = "بدون عنوان"
DEFAULT_SERIES_TITLE = "مسلسل"


# ============================================================
# 1.4 — cleanText: الفراغ بيساوي "" أو null أو none أو undefined
# ============================================================
def clean_text(value: Any) -> str:
    if value is None:
        return ""
    text = str(value).strip()
    if text.lower() in ("", "null", "none", "undefined"):
        return ""
    return text


def _first(*values: Any) -> str:
    """أول قيمة غير فاضية."""
    for value in values:
        text = clean_text(value)
        if text:
            return text
    return ""


# ============================================================
# 1.4 / 1.6 — خرايط الحقول
# ============================================================
def map_source(obj: Any) -> Dict[str, Any]:
    """عنصر sources[] → الشكل المطبّع {url,label,quality,format}."""
    if not isinstance(obj, dict):
        return {"url": "", "label": DEFAULT_SOURCE_LABEL, "quality": "", "format": ""}
    return {
        "url": _first(obj.get("streamUrl"), obj.get("url"), obj.get("link")),
        "label": clean_text(obj.get("label")) or DEFAULT_SOURCE_LABEL,
        "quality": clean_text(obj.get("quality")),
        "format": clean_text(obj.get("format")),
    }


def _derive_title(item: Dict[str, Any]) -> str:
    """العنوان: titleAr → titleEn → title → من slug → من posterUrl."""
    title = _first(item.get("titleAr"), item.get("titleEn"), item.get("title"))
    if title:
        return title
    slug = _first(item.get("slug"), item.get("seoSlug"))
    if slug:
        return slug.replace("-", " ").replace("_", " ").strip()
    poster = clean_text(item.get("posterUrl"))
    if poster:
        tail = poster.rstrip("/").split("/")[-1]
        return tail.split(".")[0] or DEFAULT_TITLE
    return DEFAULT_TITLE


def map_media(item: Any, kind: str = "movie", variant: str = "hikaye") -> Dict[str, Any]:
    """عنصر وسائط → قاموس مطبّع (مخرج الشكل الموحّد للـ public API).

    variant="hikaye" يستخدم خريطة §1.4، و variant="golive" يستخدم خريطة §1.6.
    """
    if not isinstance(item, dict):
        return {}
    if variant == "golive":
        title = _first(item.get("titleAr"), item.get("title"), item.get("titleEn")) or DEFAULT_TITLE
        category = _first((item.get("category") or {}).get("nameAr") if isinstance(item.get("category"), dict) else None,
                          (item.get("category") or {}).get("name") if isinstance(item.get("category"), dict) else None)
        return {
            "id": item.get("id"),
            "kind": kind,
            "title": title,
            "poster": clean_text(item.get("posterUrl")),
            "year": item.get("year"),
            "rating": item.get("rating"),
            "genre": category,
            "story": _first(item.get("descriptionAr"), item.get("description")),
            "sources": [map_source(s) for s in (item.get("sources") or []) if isinstance(s, dict)],
        }
    # الافتراضي: خريطة حكاية §1.4
    return {
        "id": item.get("id"),
        "kind": kind,
        "title": _derive_title(item),
        "title_ar": clean_text(item.get("titleAr")),
        "title_en": clean_text(item.get("titleEn")),
        "slug": _first(item.get("slug"), item.get("seoSlug")),
        "poster": clean_text(item.get("posterUrl")),
        "backdrop": clean_text(item.get("backdropUrl")),
        "year": item.get("year"),
        "rating": item.get("rating"),
        "genre": clean_text(item.get("genreAr")),
        "story": _first(item.get("descriptionAr"), item.get("description")),
        "sources": [map_source(s) for s in (item.get("sources") or []) if isinstance(s, dict)],
    }


def map_movie_detail(data: Any, movie_id: Any = None) -> Dict[str, Any]:
    """تفاصيل فيلم → الشكل الموحّد."""
    if not isinstance(data, dict):
        return {}
    root = data.get("data") if isinstance(data.get("data"), dict) else data
    out = map_media(root, "movie")
    if movie_id is not None and not out.get("id"):
        out["id"] = movie_id
    return out


def map_series_detail(data: Any, series_id: Any = None) -> Dict[str, Any]:
    """تفاصيل مسلسل → الشكل الموحّد مع المواسم والحلقات مرتّبة."""
    if not isinstance(data, dict):
        return {}
    root = data.get("data") if isinstance(data.get("data"), dict) else data
    title = _first(root.get("titleAr"), root.get("title"), root.get("titleEn")) or DEFAULT_SERIES_TITLE
    episodes = root.get("episodes") or []
    seasons: Dict[int, List[dict]] = {}
    for index, ep in enumerate(episodes):
        if not isinstance(ep, dict):
            continue
        season_no = ep.get("seasonNumber")
        try:
            season_no = int(season_no)
        except Exception:
            season_no = 1
        number = ep.get("episodeNumber")
        try:
            number = int(number)
        except Exception:
            number = 0
        ep_title = _first(ep.get("titleAr"), ep.get("title"), ep.get("titleEn")) or f"الحلقة {number or index + 1}"
        seasons.setdefault(season_no, []).append({
            "id": ep.get("id"),
            "number": number,
            "episode_number": number,
            "title": ep_title,
            "sources": [map_source(s) for s in (ep.get("sources") or []) if isinstance(s, dict)],
        })
    ordered = []
    for season_no in sorted(seasons.keys()):
        eps = sorted(seasons[season_no], key=lambda e: (e.get("number") or 0))
        ordered.append({
            "id": season_no,
            "season": season_no,
            "season_number": season_no,
            "episodes_count": len(eps),
            "episodes": eps,
        })
    return {
        "id": root.get("id") or series_id,
        "kind": "series",
        "title": title,
        "poster": clean_text(root.get("posterUrl")),
        "year": root.get("year"),
        "rating": root.get("rating"),
        "genre": clean_text(root.get("genreAr")),
        "story": _first(root.get("descriptionAr"), root.get("description")),
        "sources": [],
        "seasons": ordered,
    }


# ============================================================
# 1.5 — تحويل الأوضاع (mode) إلى باراميترات
# ============================================================
def is_popular(mode: Optional[str]) -> bool:
    """وضع "popular" للأفلام بس، وبيروح لمسار most-viewed."""
    return (mode or "").strip() == "popular"


def build_movies_params(
    mode: Optional[str] = None, page: int = 1, search: Optional[str] = None, limit: int = LIMIT
) -> Dict[str, Any]:
    """يبني باراميترات /content/movies من سلسلة الوضع."""
    params: Dict[str, Any] = {"page": page, "limit": limit}
    if search:
        params["search"] = search
    mode = (mode or "").strip()
    if mode == "arabic":
        params["categoryId"] = MOVIE_CATEGORIES["arabic"]["categoryId"]
    elif mode == "foreign":
        params["categoryId"] = MOVIE_CATEGORIES["foreign"]["categoryId"]
    elif mode.startswith("genre_"):
        key = mode[len("genre_"):]
        if key in MOVIE_GENRES:
            params["genre"] = MOVIE_GENRES[key]
    elif mode.startswith("year_"):
        year = mode[len("year_"):]
        if year.isdigit():
            params["year"] = year
    elif mode == "top_rated":
        params.update({"ratingMin": 7, "sortBy": "rating", "sortOrder": "desc"})
    return params


def build_series_params(
    mode: Optional[str] = None, page: int = 1, search: Optional[str] = None, limit: int = LIMIT
) -> Dict[str, Any]:
    """يبني باراميترات /content/series من سلسلة الوضع."""
    params: Dict[str, Any] = {"page": page, "limit": limit}
    if search:
        params["search"] = search
    mode = (mode or "").strip()
    if mode in SERIES_KEYWORDS:
        params["search"] = SERIES_KEYWORDS[mode]
    elif mode == "arabic":
        params["categoryId"] = SERIES_CATEGORIES["arabic"]["categoryId"]
    return params


# ============================================================
# العميل
# ============================================================
class GoLiveClient:
    """عميل async لحكاية TV / GoLive."""

    def __init__(self, base_url: str = BASE_URL, variant: str = "hikaye", timeout: float = 20.0):
        self.base = base_url.rstrip("/")
        self.variant = variant
        self.timeout = timeout

    def _headers(self) -> dict:
        return keys.GOLIVE_HEADERS if self.variant == "golive" else keys.HIKAYE_HEADERS

    async def _get(self, path: str, params: Optional[dict] = None) -> Any:
        url = f"{self.base}{path}"
        return await http.get_json(url, headers=self._headers(), params=params, timeout=self.timeout)

    @staticmethod
    def _items(payload: Any) -> List[dict]:
        """يقبل قائمة مباشرة أو {data:[…]} أو {data:{…}}."""
        if isinstance(payload, list):
            return [x for x in payload if isinstance(x, dict)]
        if isinstance(payload, dict):
            data = payload.get("data")
            if isinstance(data, list):
                return [x for x in data if isinstance(x, dict)]
            if isinstance(data, dict):
                return [data]
        return []

    # ---------- القوائم ----------
    async def movies(
        self, mode: Optional[str] = None, page: int = 1, search: Optional[str] = None, limit: int = LIMIT
    ) -> List[Dict[str, Any]]:
        if self.variant == "golive":
            payload = await self._get("/content/movies")
        elif is_popular(mode):
            payload = await self._get("/content/movies/most-viewed", {"limit": limit})
        else:
            payload = await self._get("/content/movies", build_movies_params(mode, page, search, limit))
        return [map_media(x, "movie", self.variant) for x in self._items(payload)]

    async def series(
        self, mode: Optional[str] = None, page: int = 1, search: Optional[str] = None, limit: int = LIMIT
    ) -> List[Dict[str, Any]]:
        if self.variant == "golive":
            payload = await self._get("/content/series")
        else:
            payload = await self._get("/content/series", build_series_params(mode, page, search, limit))
        return [map_media(x, "series", self.variant) for x in self._items(payload)]

    async def search(self, query: str, page: int = 1, limit: int = LIMIT) -> List[Dict[str, Any]]:
        """بحث موحّد: أفلام + مسلسلات، مدموجين ومزال التكرار بـ kind_id."""
        query = (query or "").strip()
        if len(query) < 2:
            return []
        movies = await self.movies(page=page, search=query, limit=limit)
        series = await self.series(page=page, search=query, limit=limit)
        merged: List[Dict[str, Any]] = []
        seen = set()
        for item in movies + series:
            key = f"{item.get('kind')}_{item.get('id')}"
            if key in seen:
                continue
            seen.add(key)
            merged.append(item)
        return merged

    # ---------- التفاصيل ----------
    async def movie_detail(self, movie_id: Any) -> Optional[Dict[str, Any]]:
        from urllib.parse import quote
        payload = await self._get(f"/content/movies/{quote(str(movie_id), safe='')}")
        if payload is None:
            return None
        return map_movie_detail(payload, movie_id)

    async def series_detail(self, series_id: Any) -> Optional[Dict[str, Any]]:
        from urllib.parse import quote
        payload = await self._get(f"/content/series/{quote(str(series_id), safe='')}")
        if payload is None:
            return None
        return map_series_detail(payload, series_id)

    # ---------- فك رابط البث ----------
    async def resolve_stream(self, url: str) -> str:
        """GET /stream/resolve — لو ok!=true نرجّع الرابط الأصلي."""
        if not url:
            return url
        payload = await self._get("/stream/resolve", {"url": url})
        if isinstance(payload, dict) and payload.get("ok") is True and payload.get("resolved"):
            return str(payload["resolved"])
        return url


# ============================================================
# واجهة الموديول (Public API)
# ============================================================
_client = GoLiveClient()


async def movies(mode: Optional[str] = None, page: int = 1, search: Optional[str] = None, limit: int = LIMIT) -> List[Dict[str, Any]]:
    return await _client.movies(mode=mode, page=page, search=search, limit=limit)


async def series(mode: Optional[str] = None, page: int = 1, search: Optional[str] = None, limit: int = LIMIT) -> List[Dict[str, Any]]:
    return await _client.series(mode=mode, page=page, search=search, limit=limit)


async def search(query: str, page: int = 1, limit: int = LIMIT) -> List[Dict[str, Any]]:
    return await _client.search(query, page=page, limit=limit)


async def movie_detail(movie_id: Any) -> Optional[Dict[str, Any]]:
    return await _client.movie_detail(movie_id)


async def series_detail(series_id: Any) -> Optional[Dict[str, Any]]:
    return await _client.series_detail(series_id)


async def resolve_stream(url: str) -> str:
    return await _client.resolve_stream(url)
