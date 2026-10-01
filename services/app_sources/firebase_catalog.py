"""كتالوج فايربيس (Google Firebase / Prime) — منقول من §3 في المواصفة.

بيقرا الشجرة من $FIREBASE_URL/$ROOT.json (بدون مفتاح auth)، وبيقسّم الناتج
لقنوات مباشرة + أفلام + مسلسلات + كرتون. كله فشل ناعم.
"""
from __future__ import annotations

import logging
import re
from typing import Any, Dict, List, Optional
from urllib.parse import urlparse

from . import keys
from . import http

logger = logging.getLogger(__name__)

DATABASE_URL = keys.FIREBASE_URL
ROOT_PATH = keys.FIREBASE_ROOT
SCRAPING_DOMAIN = keys.SCRAPING_DOMAIN

VOD_SCOPES = {"MOVIES", "SERIES", "CARTOONS", "ANIME", "VOD", "FILMS"}
IMAGE_FIELDS = (
    "imageUrl", "image_url", "logoUrl", "logo_url", "posterUrl", "poster_url",
    "thumbnailUrl", "thumbnail_url", "image", "logo", "poster", "icon",
)

MAX_MOVIE_ITEMS = 400


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


def _image_of(item: Dict[str, Any]) -> str:
    for field in IMAGE_FIELDS:
        value = clean_text(item.get(field))
        if value:
            return normalize_image_url(value)
    return ""


# ============================================================
# 3 — Scope / group
# ============================================================
def is_vod_scope(scope: Any) -> bool:
    return clean_text(scope).upper() in VOD_SCOPES


def vod_group(title: Any, scope: Any) -> str:
    """vodGroup: SERIES/CARTOONS/FILMS حسب الـ scope أو عنوان الفئة."""
    title = clean_text(title)
    scope_u = clean_text(scope).upper()
    upper_title = title.upper()
    if scope_u in ("SERIES", "SERIE") or "SERIES" in upper_title or "مسلسل" in title:
        return f"SERIES:{title}"
    if scope_u in ("CARTOONS", "ANIME") or "ANIME" in upper_title or "أنمي" in title or "كرتون" in title:
        return f"CARTOONS:{title}"
    if is_vod_scope(scope_u):
        return f"FILMS:{title}"
    return title


def infer_package(title: Any) -> str:
    """تخمين الباقة من اسم القناة لو مفيش فئة."""
    t = clean_text(title).upper()
    if "BEIN" in t:
        return "BEIN SPORT"
    if "TOD" in t:
        return "TOD Sports"
    if "SHAHID" in t:
        return "SHAHID SPORT"
    if "MBC" in t:
        return "MBC GROUP"
    if "ROTANA" in t:
        return "Rotana"
    if "ALKASS" in t or "الكأس" in t:
        return "ALKASS"
    if "ABU DHABI" in t:
        return "Abu Dhabi Sports"
    if "NEWS" in t:
        return "NEWS"
    return "OTHER"


# ============================================================
# 3 — تطبيع الروابط
# ============================================================
def normalize_scraping_url(url: Any) -> str:
    """لو الرابط فيه .xyz نحوّل ما قبله للنطاق الثابت SCRAPING_DOMAIN."""
    u = clean_text(url)
    marker = ".xyz"
    if marker in u:
        index = u.index(marker) + len(marker)
        return SCRAPING_DOMAIN + u[index:]
    return u


def normalize_image_url(url: Any) -> str:
    u = clean_text(url)
    if not u:
        return ""
    if u.startswith("//"):
        return "https:" + u
    if u.startswith(("http://", "https://")):
        return u
    return SCRAPING_DOMAIN + "/" + u.lstrip("/")


# ============================================================
# 3 — خرائط العناصر
# ============================================================
def map_category(item: Any) -> Dict[str, Any]:
    if not isinstance(item, dict):
        return {}
    scope = clean_text(item.get("scope")).upper() or "LIVE"
    try:
        order = int(item.get("order") or 0)
    except Exception:
        order = 0
    return {
        "id": clean_text(item.get("id")),
        "title": clean_text(item.get("title")) or "GENERAL",
        "scope": scope,
        "order": order,
        "targetUrl": normalize_scraping_url(item.get("targetUrl")),
        "image": _image_of(item),
    }


def map_channel_items(item: Any, key: str, number: int, category: Dict[str, Any]) -> List[Dict[str, Any]]:
    """قناة واحدة → عنصر لكل سيرفر (أول سيرفر بس بياخد الاسم الخام)."""
    if not isinstance(item, dict):
        return []
    name = _first(item.get("title"), item.get("name")) or f"Channel {number}"
    servers = item.get("servers")
    group = vod_group(category.get("title"), category.get("scope"))
    logo = _image_of(item) or category.get("image") or ""
    if not isinstance(servers, list) or not servers:
        servers = [{"url": item.get("url"), "name": name,
                    "userAgent": item.get("userAgent"), "referer": item.get("referer")}]
    out: List[Dict[str, Any]] = []
    for index, server in enumerate(servers):
        if not isinstance(server, dict):
            continue
        url = clean_text(server.get("url"))
        if not url:
            continue
        if index == 0:
            item_id = f"firebase_{key}"
            display = name
        else:
            item_id = f"firebase_{key}_s{index}"
            suffix = clean_text(server.get("name")) or f"Server {index + 1}"
            display = f"{name} · {suffix}"
        out.append({
            "id": item_id,
            "name": display,
            "url": url,
            "group": group,
            "logoUrl": logo,
            "language": "AR",
            "isLive": not is_vod_scope(category.get("scope")),
            "httpUserAgent": clean_text(server.get("userAgent")),
            "httpReferrer": clean_text(server.get("referer")),
            "categoryId": category.get("id"),
            "order": category.get("order", 0),
            "channelNumber": number,
        })
    return out


def _channels_raw(raw: Any) -> List[tuple]:
    """catalog_channels مصفوفة أو كائن مفتاحه id — الاتنين مدعومين."""
    if isinstance(raw, list):
        return [(clean_text(x.get("id")) if isinstance(x, dict) else "", x) for x in raw]
    if isinstance(raw, dict):
        return [(k, v) for k, v in raw.items()]
    return []


def build_channels(categories: List[Dict[str, Any]], channels_raw: Any) -> List[Dict[str, Any]]:
    """يبني القنوات المباشرة مرتّبة حسب ترتيب الفئة ثم رقم القناة."""
    by_id = {c["id"]: c for c in categories}
    items: List[Dict[str, Any]] = []
    for number, (key, raw) in enumerate(_channels_raw(channels_raw), start=1):
        if not isinstance(raw, dict):
            continue
        category = by_id.get(clean_text(raw.get("categoryId"))) or {
            "id": "", "title": infer_package(_first(raw.get("title"), raw.get("name"))),
            "scope": "LIVE", "order": 0, "image": "",
        }
        items.extend(map_channel_items(raw, key or str(number), number, category))
    items.sort(key=lambda x: (x.get("order", 0), x.get("channelNumber", 0)))
    return items


def category_cards(categories: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """كروت الفئات لغير المباشر اللي عندها targetUrl."""
    cards = []
    for category in categories:
        if is_vod_scope(category.get("scope")):
            continue
        if not category.get("targetUrl"):
            continue
        cards.append({
            "id": f"category_{category['id']}",
            "name": category["title"],
            "group": vod_group(category["title"], category["scope"]),
            "url": category["targetUrl"],
            "logoUrl": category.get("image") or "",
            # كارت فئة VOD (مش قناة مباشرة) — عشان كده isLive=false
            "isLive": False,
        })
    return cards


# ============================================================
# 3 — سكرابينج أفلام الفئات (HTML)
# ============================================================
MOVIE_IMG_ANCHOR = re.compile(r'class="[^"]*movie-img[^"]*"')
H3_LINK = re.compile(r'<h3[^>]*>\s*<a[^>]*href="([^"]+)"[^>]*>(.*?)</a>', re.I | re.S)
IMG_SRC = re.compile(r'(?:data-src|data-original|data-lazy-src|src)="([^"]+)"', re.I)
TAG = re.compile(r"<[^>]+>")


def _slug_from_url(url: str) -> str:
    tail = urlparse(url).path.rstrip("/").split("/")[-1]
    if tail.endswith(".html"):
        tail = tail[:-len(".html")]
    return tail


def _scrape_type(title: str) -> str:
    if "انمي" in title or "أنمي" in title:
        return "CARTOONS"
    if "مسلسل" in title or "series" in title.lower():
        return "SERIES"
    return "FILMS"


def parse_movie_html(html: str, category_title: str, max_items: int = MAX_MOVIE_ITEMS) -> List[Dict[str, Any]]:
    """سكان شريحي على class=…movie-img… (يقرا 2600 حرف بعدها)."""
    if not html:
        return []
    items: List[Dict[str, Any]] = []
    seen = set()
    for anchor in MOVIE_IMG_ANCHOR.finditer(html):
        if len(items) >= max_items:
            break
        chunk = html[anchor.start():anchor.start() + 2600]
        link = H3_LINK.search(chunk)
        if not link:
            continue
        page_url = link.group(1).strip()
        title = clean_text(TAG.sub("", link.group(2)))
        image = ""
        for match in IMG_SRC.finditer(chunk):
            candidate = match.group(1).strip()
            if "blank_thumbnail" in candidate:
                continue
            image = candidate
            break
        if not page_url or page_url in seen:
            continue
        seen.add(page_url)
        kind = _scrape_type(title)
        slug = _slug_from_url(page_url)
        items.append({
            "id": f"vod_{kind.lower()}_{slug}",
            "name": title,
            "url": normalize_scraping_url(page_url),
            "group": f"{kind}:{category_title}",
            "logoUrl": normalize_image_url(image),
            "isLive": False,
            "type": kind,
        })
    return items


async def fetch_movie_items(category: Dict[str, Any]) -> List[Dict[str, Any]]:
    """يجلب صفحة فئة أفلام ويسحب العناصر."""
    target = category.get("targetUrl")
    if not target:
        return []
    html = await http.get_text(target, headers=keys.FIREBASE_SCRAPE_HEADERS, timeout=25.0)
    if not html:
        return []
    return parse_movie_html(html, category.get("title") or "GENERAL")


# ============================================================
# 3 — التقسيم النهائي
# ============================================================
def split_catalog(items: List[Dict[str, Any]]) -> Dict[str, List[Dict[str, Any]]]:
    """يقسّم العناصر: قنوات مباشرة / أفلام / مسلسلات / كرتون."""
    result = {"channels": [], "films": [], "series": [], "cartoons": []}
    for item in items or []:
        group = str(item.get("group") or "")
        if item.get("isLive"):
            result["channels"].append(item)
            continue
        low = group.lower()
        if "مسلسل" in group or "series" in low or group.startswith("SERIES:"):
            result["series"].append(item)
        elif "انمي" in group or "أنمي" in group or "كرتون" in group or "رسوم" in group or group.startswith("CARTOONS:"):
            result["cartoons"].append(item)
        else:
            result["films"].append(item)
    return result


# ============================================================
# العميل
# ============================================================
async def fetch_root() -> Dict[str, Any]:
    """GET $FIREBASE_URL/$ROOT.json — رد فاضي أو null = نتيجة فاضية."""
    url = f"{DATABASE_URL.rstrip('/')}/{ROOT_PATH}.json"
    payload = await http.get_json(url, headers=keys.FIREBASE_HEADERS, timeout=25.0)
    if isinstance(payload, dict):
        return payload
    return {}


async def load_catalog(scrape_movies: bool = True) -> Dict[str, List[Dict[str, Any]]]:
    """يحمّل الكتالوج كامل ويقسّمه (مع دمج سكرابينج الأفلام لو مطلوب)."""
    root = await fetch_root()
    if not root:
        return {"channels": [], "films": [], "series": [], "cartoons": []}
    categories = [c for x in (root.get("catalog_categories") or []) if (c := map_category(x))]
    items = build_channels(categories, root.get("catalog_channels"))
    items.extend(category_cards(categories))
    if scrape_movies:
        for category in categories:
            if category.get("scope") == "MOVIES" and category.get("targetUrl"):
                items.extend(await fetch_movie_items(category))
    return split_catalog(items)


async def channels() -> List[Dict[str, Any]]:
    return (await load_catalog(scrape_movies=False))["channels"]


async def films() -> List[Dict[str, Any]]:
    return (await load_catalog())["films"]


async def series() -> List[Dict[str, Any]]:
    return (await load_catalog())["series"]


async def cartoons() -> List[Dict[str, Any]]:
    return (await load_catalog())["cartoons"]
