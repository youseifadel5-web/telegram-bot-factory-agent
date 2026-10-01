"""عميل فاصل HD — منقول من §2 في المواصفة.

الترتيب: المضيف الأساسي ثم مرآتين عبر hosts/config (أول رد غير فاضي يفوز)،
وهيدر packagename إلزامي في كل طلب، والـ APP_TOKEN في كل مسار.

ملاحظة: فيه دالة عامة اسمها list حسب المواصفة، وعشان كده بنستخدم builtins.list
جوه الملف بدل الاسم العادي.
"""
from __future__ import annotations

import builtins
import logging
from typing import Any, Dict, List, Optional
from urllib.parse import quote

from . import keys
from . import http
# نعيد تصدير الـ parsers من resolver حسب §2.6.4 (اختبارات الـ pair/master)
from .resolver import parse_pairs, parse_master  # noqa: F401

logger = logging.getLogger(__name__)

APP_TOKEN = keys.APP_TOKEN
IMAGE_BASE = "https://image.tmdb.org/t/p/w500/"

# 2.1 — المضيف الأساسي والمرايا (بالترتيب)
HOST_BASES: List[str] = [
    "https://fashd.com/faselhd15/public/api/",
    "https://kahitdgku.com/faselhd15/public/api/",
    "https://hrrejhp.com/egybestanto/public/api/",
]
BASE_URL = HOST_BASES[0]

# 2.5 — ترتيب أقسام الكتالوج الرئيسي
HOME_SECTIONS: List[tuple] = [
    ("featured", "FEATURED"),
    ("latest", "LATEST"),
    ("choosed", "CHOOSED"),
    ("recommended", "RECOMMENDED"),
    ("thisweek", "THIS WEEK"),
    ("trending", "TRENDING"),
    ("pinned", "PINNED"),
    ("top10", "TOP 10"),
    ("popular", "POPULAR"),
    ("recents", "RECENT"),
    ("popularSeries", "POPULAR SERIES"),
    ("anime", "ANIME"),
    ("livetv", "LIVE TV"),
]

DEFAULT_SERVER = "سيرفر"


def clean_text(value: Any) -> str:
    if value is None:
        return ""
    text = str(value).strip()
    if text.lower() in ("", "null", "none", "undefined"):
        return ""
    return text


def _first(*values: Any) -> str:
    for value in values:
        text = clean_text(value)
        if text:
            return text
    return ""


# ============================================================
# 2.5 — normalizeImage
# ============================================================
def normalize_image(value: Any) -> str:
    v = clean_text(value)
    if not v:
        return ""
    if v.startswith("http://"):
        return "https://" + v[len("http://"):]
    if v.startswith("https://"):
        return v
    if v.startswith("/"):
        return IMAGE_BASE + v[1:]
    return IMAGE_BASE + v


def _genres(value: Any) -> List[str]:
    """genreslist[]/genres[] ممكن تكون كائنات {name} أو نصوص."""
    out: List[str] = []
    if not isinstance(value, builtins.list):
        return out
    for g in value:
        if isinstance(g, dict):
            name = _first(g.get("name"), g.get("title"))
        else:
            name = clean_text(g)
        if name:
            out.append(name)
    return out


# ============================================================
# 2.5 — خرائط الحقول
# ============================================================
def map_media_item(item: Any) -> Dict[str, Any]:
    """عنصر قائمة → FaselMedia."""
    if not isinstance(item, dict):
        return {}
    try:
        media_id = int(item.get("id") or 0)
    except Exception:
        media_id = 0
    if media_id == 0:
        return {}
    type_value = clean_text(item.get("type")).lower()
    if item.get("is_anime") == 1:
        type_value = "anime"
    elif type_value in ("series", "tv"):
        type_value = "serie"
    elif not type_value:
        type_value = "movie"
    return {
        "id": media_id,
        "title": _first(item.get("title"), item.get("name")),
        "type": type_value,
        "poster": normalize_image(item.get("poster_path")),
        "backdrop": _first(item.get("backdrop_path"), item.get("backdrop_path_tv")),
        "subtitle": clean_text(item.get("subtitle")),
        "vote": item.get("vote_average"),
        "release": _first(item.get("release_date"), item.get("first_air_date")),
        "overview": clean_text(item.get("overview")),
        "genres": _genres(item.get("genreslist")) or _genres(item.get("genres")),
    }


def map_video(obj: Any) -> Dict[str, Any]:
    """عنصر سيرفر/فيديو → FaselVideo."""
    if not isinstance(obj, dict):
        return {}
    if obj.get("status") == 0:
        return {}
    link = _first(obj.get("link"), obj.get("url"), obj.get("file"), obj.get("src"),
                  obj.get("video_url"), obj.get("download_url"))
    if not link:
        return {}
    quality = clean_text(obj.get("quality"))
    label = clean_text(obj.get("label"))
    hd = (
        obj.get("hd") == 1
        or "hd" in quality.lower()
        or "1080" in label or "720" in label
    )
    hls = obj.get("hls") == 1 or ".m3u8" in link.lower()
    return {
        "link": link,
        "server": _first(obj.get("server"), obj.get("name")) or DEFAULT_SERVER,
        "userAgent": _first(obj.get("useragent"), obj.get("user_agent")),
        "referer": _first(obj.get("header"), obj.get("referer"), obj.get("referrer")),
        "hd": hd,
        "hls": hls,
        "lang": clean_text(obj.get("lang")),
        "downloadOnly": obj.get("downloadonly") == 1 or obj.get("download_only") is True,
        "quality": quality,
        "label": label,
    }


def map_videos(*containers: Any) -> List[Dict[str, Any]]:
    """أول حاوية غير فاضية من videos/sources تتحوّل لقائمة FaselVideo."""
    for container in containers:
        if isinstance(container, builtins.list) and container:
            out = [map_video(v) for v in container if isinstance(v, dict)]
            out = [v for v in out if v]
            if out:
                return out
    return []


def map_detail(root: Any, related: Any = None) -> Dict[str, Any]:
    """media/detail/{id} → FaselDetail."""
    if not isinstance(root, dict):
        return {}
    media = root.get("media") if isinstance(root.get("media"), dict) else root
    videos = map_videos(root.get("videos"), media.get("videos"), media.get("sources"))
    cast = []
    for c in (root.get("casterslist") or []):
        if isinstance(c, dict) and _first(c.get("name")):
            cast.append(_first(c.get("name")))
    networks = []
    for n in (root.get("networkslist") or []):
        if isinstance(n, dict):
            networks.append({"id": n.get("id"), "name": _first(n.get("name")), "type": clean_text(n.get("type"))})
    subtitles = []
    for s in (root.get("substitles") or []):
        if isinstance(s, dict):
            url = _first(s.get("subDownloadLink"), s.get("zipDownloadLink"), s.get("link"))
            if url:
                subtitles.append(url)
    related_items = []
    for r in (related or []):
        mapped = map_media_item(r)
        if mapped:
            related_items.append(mapped)
    return {
        "id": media.get("id"),
        "kind": "movie",
        "title": _first(media.get("title"), media.get("name")),
        "overview": clean_text(media.get("overview")),
        "poster": normalize_image(media.get("poster_path")),
        "backdrop": _first(media.get("backdrop_path"), media.get("backdrop_path_tv")),
        "vote": media.get("vote_average"),
        "release": clean_text(media.get("release_date")),
        "subtitle": clean_text(media.get("subtitle")),
        "runtime": media.get("runtime"),
        "cast": cast,
        "genres": _genres(root.get("genres")) or _genres(media.get("genres")),
        "networks": networks,
        "subtitles": subtitles,
        "videos": videos,
        "related": related_items,
    }


def map_series_detail(root: Any, series_id: Any = None) -> Dict[str, Any]:
    """series/show/{id} → FaselSeries (المواسم منفصلة، تُجلب لاحقاً)."""
    if not isinstance(root, dict):
        return {}
    seasons = []
    for i, season in enumerate(root.get("seasons") or []):
        if not isinstance(season, dict):
            continue
        seasons.append({
            "id": season.get("id"),
            "name": _first(season.get("name")) or f"الموسم {i + 1}",
            "episodes": [],
        })
    return {
        "id": root.get("id") or series_id,
        "kind": "serie",
        "title": _first(root.get("name"), root.get("title")),
        "overview": clean_text(root.get("overview")),
        "poster": normalize_image(root.get("poster_path")),
        "vote": root.get("vote_average"),
        "genres": _genres(root.get("genreslist")),
        "seasons": seasons,
    }


def map_season(root: Any, season_id: Any = None) -> Dict[str, Any]:
    """series/season/{sid} → قائمة حلقات."""
    if not isinstance(root, dict):
        return {}
    episodes = []
    for j, ep in enumerate(root.get("episodes") or []):
        if not isinstance(ep, dict):
            continue
        episodes.append({
            "id": ep.get("id"),
            "number": ep.get("episode_number") or (j + 1),
            "name": _first(ep.get("name")) or f"الحلقة {j + 1}",
            "imdb": _first(ep.get("imdb_external_id"), ep.get("imdb_id")),
            "still": clean_text(ep.get("still_path")),
            "videos": map_videos(ep.get("videos"), ep.get("sources")),
        })
    return {"id": season_id or root.get("id"), "episodes": episodes}


def map_episode_streams(root: Any) -> List[Dict[str, Any]]:
    """series/episode/{imdb} → قائمة FaselVideo."""
    if not isinstance(root, dict):
        return []
    episode = root.get("episode") if isinstance(root.get("episode"), dict) else {}
    return map_videos(root.get("videos"), root.get("sources"), episode.get("videos"))


def map_live_channel(item: Any, group: str) -> Dict[str, Any]:
    """كائن قناة مباشرة (livetv/mostwatched و categories/streaming/show)."""
    if not isinstance(item, dict):
        return {}
    videos = item.get("videos") or []
    first_video = videos[0] if isinstance(videos, builtins.list) and videos and isinstance(videos[0], dict) else {}
    url = _first(first_video.get("link"), first_video.get("url"))
    if not url.startswith(("http", "rtmp")):
        return {}
    logo = _first(
        item.get("poster_path"), item.get("logo_path"), item.get("backdrop_path"),
        item.get("backdrop_path_tv"), item.get("image"), item.get("logo"),
        item.get("poster"), item.get("icon"), item.get("channel_logo"),
        item.get("channelLogo"), item.get("thumbnail"),
        first_video.get("logo"), first_video.get("logo_url"), first_video.get("logoUrl"),
        first_video.get("image"), first_video.get("poster"), first_video.get("icon"),
        first_video.get("poster_path"),
    )
    return {
        "id": item.get("id"),
        "name": _first(item.get("name")) or "Live",
        "url": url,
        "logo": normalize_image(logo),
        "group": group,
        "httpUserAgent": _first(first_video.get("useragent"), first_video.get("user_agent")),
        "httpReferrer": _first(first_video.get("header"), first_video.get("referer")),
        "isLive": True,
    }


def map_home_sections(root: Any) -> List[Dict[str, Any]]:
    """media/homecontent → الأقسام بترتيب المواصفة."""
    if not isinstance(root, dict):
        return []
    sections: List[Dict[str, Any]] = []
    for key, name in HOME_SECTIONS:
        raw = root.get(key)
        if not isinstance(raw, builtins.list) or not raw:
            continue
        if key == "livetv":
            items = [map_live_channel(x, "FASEL HD / LIVE TV") for x in raw]
        else:
            items = []
            for x in raw:
                media = map_media_item(x)
                if not media:
                    continue
                media["section"] = name
                media["kind"] = _home_kind(media.get("type"), name)
                media["group"] = f"FASEL HD / {media['kind']} / {name}"
                media["url"] = f"faselhd://{_marker_type(media['kind'])}/{media['id']}"
                media["item_id"] = f"faselhd_{media['kind'].lower()}_{media['id']}"
                items.append(media)
        items = [x for x in items if x]
        if items:
            sections.append({"key": key, "name": name, "items": items})
    return sections


def _home_kind(type_value: Any, section: str) -> str:
    t = clean_text(type_value).lower()
    if "anime" in t or section == "ANIME":
        return "ANIME"
    if "serie" in t or "SERIES" in section:
        return "SERIES"
    return "FILMS"


def _marker_type(kind: str) -> str:
    return {"ANIME": "anime", "SERIES": "series"}.get(kind, "movie")


def map_host_config(item: Any, index: int = 0) -> Dict[str, Any]:
    """hosts/config → HostConfig (مع التنظيف)."""
    if not isinstance(item, dict):
        return {}
    domains = [clean_text(d) for d in (item.get("domains") or []) if clean_text(d)]
    url_site = clean_text(item.get("urlsite"))
    if url_site and (not url_site.startswith("http") or len(url_site) > 300):
        url_site = ""
    if not url_site:
        enableded = clean_text(item.get("enableded"))
        if "http" in enableded:
            match = _find_first_url(enableded)
            if match:
                url_site = match
    return {
        "hostId": clean_text(item.get("host_id")) or f"host{index}",
        "domains": domains,
        "urlSite": url_site,
        "referer": clean_text(item.get("referer")),
        "userAgent": clean_text(item.get("useragent")),
        "enabled": bool(item.get("enabled", True)),
    }


def _find_first_url(text: str) -> str:
    import re
    match = re.search(r"https?://\S+", text)
    if not match:
        return ""
    return match.group(0).rstrip("| ").strip()


def map_network(item: Any) -> Dict[str, Any]:
    if not isinstance(item, dict):
        return {}
    network_id = clean_text(item.get("id"))
    if not network_id or network_id == "0":
        return {}
    return {"id": network_id, "name": _first(item.get("name")) or "قسم",
            "logo_path": clean_text(item.get("logo_path")), "type": clean_text(item.get("type"))}


def map_genre(item: Any) -> Dict[str, Any]:
    if not isinstance(item, dict):
        return {}
    try:
        genre_id = int(item.get("id"))
    except Exception:
        return {}
    return {"id": genre_id, "name": _first(item.get("name"))}


def map_country(item: Any) -> Dict[str, Any]:
    if not isinstance(item, dict):
        return {}
    return {"id": item.get("id"), "name": _first(item.get("name")), "type": "country"}


# ============================================================
# العميل
# ============================================================
class FaselClient:
    """عميل async لفاصل HD."""

    def __init__(self, base_url: str = BASE_URL, timeout: float = 20.0):
        self._base = base_url
        self.timeout = timeout

    def base(self) -> str:
        return self._base.rstrip("/") + "/"

    async def _get(self, path: str, params: Optional[dict] = None) -> Any:
        url = self.base() + path.lstrip("/")
        return await http.get_json(url, headers=keys.FASEL_HEADERS, params=params, timeout=self.timeout)

    # ---------- القوائم ----------
    async def list(self, kind: str, page: int = 1) -> List[Dict[str, Any]]:
        segment = {"movie": "movies", "movies": "movies", "serie": "series",
                   "series": "series", "anime": "animes", "animes": "animes"}.get(
            clean_text(kind).lower(), "movies")
        payload = await self._get(f"genres/{segment}/all/{APP_TOKEN}", {"page": page})
        return _items_from(payload)

    async def search(self, query: str) -> List[Dict[str, Any]]:
        query = clean_text(query)
        if not query:
            return []
        payload = await self._get(f"search/{quote(query, safe='')}/{APP_TOKEN}")
        if isinstance(payload, dict):
            raw = payload.get("search")
            if isinstance(raw, builtins.list):
                return _items_from(raw)
        return _items_from(payload)

    async def network_media(self, network_id: Any, page: int = 1) -> List[Dict[str, Any]]:
        payload = await self._get(f"networks/media/show/{quote(str(network_id), safe='')}/{APP_TOKEN}", {"page": page})
        return _items_from(payload)

    async def genre_media(self, kind: str, genre_id: Any, page: int = 1) -> List[Dict[str, Any]]:
        segment = {"movie": "movies", "serie": "series", "series": "series",
                   "anime": "animes"}.get(clean_text(kind).lower(), "movies")
        payload = await self._get(f"genres/{segment}/show/{genre_id}/{APP_TOKEN}", {"page": page})
        return _items_from(payload)

    # ---------- القوائم المرجعية ----------
    async def networks(self) -> List[Dict[str, Any]]:
        payload = await self._get(f"networks/lists/{APP_TOKEN}")
        raw = payload.get("networks") if isinstance(payload, dict) else payload
        return [m for x in (raw or []) if (m := map_network(x))]

    async def genres(self) -> List[Dict[str, Any]]:
        payload = await self._get(f"genres/list/{APP_TOKEN}")
        raw = payload.get("genres") if isinstance(payload, dict) else payload
        return [m for x in (raw or []) if (m := map_genre(x))]

    async def countries(self) -> List[Dict[str, Any]]:
        payload = await self._get(f"categories/list/{APP_TOKEN}")
        raw = payload.get("categories") if isinstance(payload, dict) else payload
        return [m for x in (raw or []) if (m := map_country(x))]

    async def country_channels(self, category_id: Any) -> List[Dict[str, Any]]:
        payload = await self._get(f"categories/streaming/show/{category_id}/{APP_TOKEN}")
        raw = payload.get("data") if isinstance(payload, dict) else payload
        return [m for x in (raw or []) if (m := map_live_channel(x, "FASEL HD / LIVE / قنوات الدول"))]

    async def livetv_mostwatched(self) -> List[Dict[str, Any]]:
        payload = await self._get(f"livetv/mostwatched/{APP_TOKEN}")
        raw = payload.get("watched") if isinstance(payload, dict) else payload
        return [m for x in (raw or []) if (m := map_live_channel(x, "FASEL HD / LIVE / الأكثر مشاهدة"))]

    async def upcoming(self) -> List[Dict[str, Any]]:
        payload = await self._get(f"upcoming/latest/{APP_TOKEN}")
        raw = payload.get("upcoming") if isinstance(payload, dict) else payload
        return _items_from(raw)

    # ---------- التفاصيل ----------
    async def movie_detail(self, media_id: Any) -> Dict[str, Any]:
        payload = await self._get(f"media/detail/{media_id}/{APP_TOKEN}")
        if not isinstance(payload, dict):
            return {}
        related = await self._related(media_id)
        return map_detail(payload, related)

    async def anime_detail(self, media_id: Any) -> Dict[str, Any]:
        payload = await self._get(f"animes/show/{media_id}/{APP_TOKEN}")
        if not isinstance(payload, dict):
            # 2.4 — يرجع لـ series/show عند الخطأ
            payload = await self._get(f"series/show/{media_id}/{APP_TOKEN}")
        return map_series_detail(payload, media_id)

    async def series_detail(self, series_id: Any) -> Dict[str, Any]:
        payload = await self._get(f"series/show/{series_id}/{APP_TOKEN}")
        return map_series_detail(payload, series_id)

    async def _related(self, media_id: Any) -> List[Any]:
        payload = await self._get(f"media/relateds/{media_id}/{APP_TOKEN}")
        if isinstance(payload, dict):
            raw = payload.get("relateds")
            if isinstance(raw, builtins.list):
                return raw
        return []

    async def season(self, season_id: Any) -> Dict[str, Any]:
        payload = await self._get(f"series/season/{season_id}/{APP_TOKEN}")
        return map_season(payload, season_id)

    async def anime_season(self, season_id: Any) -> Dict[str, Any]:
        payload = await self._get(f"animes/season/{season_id}/{APP_TOKEN}")
        return map_season(payload, season_id)

    async def episode_streams(self, imdb: Any) -> List[Dict[str, Any]]:
        payload = await self._get(f"series/episode/{imdb}/{APP_TOKEN}")
        return map_episode_streams(payload)

    async def anime_episode_streams(self, imdb: Any) -> List[Dict[str, Any]]:
        payload = await self._get(f"animes/episode/{imdb}/{APP_TOKEN}")
        return map_episode_streams(payload)

    async def home_sections(self) -> List[Dict[str, Any]]:
        payload = await self._get(f"media/homecontent/{APP_TOKEN}")
        return map_home_sections(payload)

    async def hosts_config(self) -> List[Dict[str, Any]]:
        """hosts/config مع تجربة المضيفات بالترتيب — أول رد غير فاضي يفوز."""
        for base in HOST_BASES:
            payload = await http.get_json(
                base.rstrip("/") + "/hosts/config", headers=keys.FASEL_HEADERS, timeout=self.timeout)
            if isinstance(payload, builtins.list) and payload:
                return [m for i, x in enumerate(payload) if (m := map_host_config(x, i))]
        return []


def _items_from(payload: Any) -> List[Dict[str, Any]]:
    raw = payload
    if isinstance(payload, dict):
        raw = payload.get("data")
    if not isinstance(raw, builtins.list):
        return []
    return [m for x in raw if (m := map_media_item(x))]


_client = FaselClient()


# ============================================================
# واجهة الموديول (Public API)
# ============================================================
async def home_sections() -> List[Dict[str, Any]]:
    return await _client.home_sections()


async def search(q: str) -> List[Dict[str, Any]]:
    return await _client.search(q)


async def movie_detail(movie_id: Any) -> Dict[str, Any]:
    return await _client.movie_detail(movie_id)


async def series_detail(series_id: Any) -> Dict[str, Any]:
    return await _client.series_detail(series_id)


async def season(season_id: Any) -> Dict[str, Any]:
    return await _client.season(season_id)


async def episode_streams(imdb: Any) -> List[Dict[str, Any]]:
    return await _client.episode_streams(imdb)


async def anime_detail(anime_id: Any) -> Dict[str, Any]:
    return await _client.anime_detail(anime_id)


async def anime_season(season_id: Any) -> Dict[str, Any]:
    return await _client.anime_season(season_id)


async def anime_episode_streams(imdb: Any) -> List[Dict[str, Any]]:
    return await _client.anime_episode_streams(imdb)


async def livetv_mostwatched() -> List[Dict[str, Any]]:
    return await _client.livetv_mostwatched()


async def countries() -> List[Dict[str, Any]]:
    return await _client.countries()


async def country_channels(category_id: Any) -> List[Dict[str, Any]]:
    return await _client.country_channels(category_id)


async def networks() -> List[Dict[str, Any]]:
    return await _client.networks()


async def genres() -> List[Dict[str, Any]]:
    return await _client.genres()


async def hosts_config() -> List[Dict[str, Any]]:
    return await _client.hosts_config()


# ملاحظة: دالة list العاملة موجودة كـ _client.list وكمان هنا كـ list_media،
# وأخيراً نسخة بالاسم list حسب المواصفة (مش بنستخدم builtins.list بعد هنا).
async def list_media(kind: str, page: int = 1) -> List[Dict[str, Any]]:
    return await _client.list(kind, page)


# النسخة المطابقة للمواصفة — لازم تكون في آخر الملف.
def list(kind: str, page: int = 1):  # noqa: A001
    return _client.list(kind, page)
