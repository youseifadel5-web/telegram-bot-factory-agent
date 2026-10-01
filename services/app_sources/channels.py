"""القنوات — منقول من §4 في المواصفة.

بيجمّع: سكرابينج ألووي (البصري)، قائمة القنوات الافتراضية، كتالوج الراديو،
ومحلّل M3U للاستيراد. كل حاجة من غير شبكة وقت الاستيراد.
"""
from __future__ import annotations

import json
import logging
import os
import re
from pathlib import Path
from typing import Any, Dict, List, Optional

from . import keys
from . import http

logger = logging.getLogger(__name__)

SCRAPING_DOMAIN = keys.SCRAPING_DOMAIN
MAX_GENRE_CARDS = 300
MAX_EPISODES = 120

# ============================================================
# 4.4 — القنوات الافتراضية (10 قنوات)
# ملاحظة: الروابط والمجموعات منقولة حرفياً من المواصفة. روابط الشعارات
# (logoUrl) وقيَم اللغة (AR/EN) المواصفة ما ذكرتهاش صريحاً، فاتحطّت Unsplash
# كـ placeholder واضح لحد ما تتظبط من إعدادات المستخدم.
# ============================================================
_LOGO_AR = "https://images.unsplash.com/photo-1593359677879-a4bb92f829d1?w=400"
_LOGO_TECH = "https://images.unsplash.com/photo-1446776811953-b23d57bd21aa?w=400"
_LOGO_SPORT = "https://images.unsplash.com/photo-1461896836934-ffe607ba8211?w=400"
_LOGO_NEWS = "https://images.unsplash.com/photo-1495020689067-958852a7765e?w=400"
_LOGO_MOVIE = "https://images.unsplash.com/photo-1489599849927-2ee91cede3ba?w=400"
_LOGO_KIDS = "https://images.unsplash.com/photo-1560169897-fc0cdbdfa4d5?w=400"

DEFAULT_CHANNELS: List[Dict[str, Any]] = [
    {"id": "ch_01", "channelNumber": 1, "name": "Al Jazeera Arabic",
     "url": "https://live-hls-web-aja.getaj.net/AJA/01.m3u8", "group": "ARABIC",
     "language": "AR", "isLive": True, "logoUrl": _LOGO_AR},
    {"id": "ch_02", "channelNumber": 2, "name": "TRT Arabi",
     "url": "https://tv-trtarabi.medya.trt.com.tr/master.m3u8", "group": "ARABIC",
     "language": "AR", "isLive": True, "logoUrl": _LOGO_AR},
    {"id": "ch_03", "channelNumber": 3, "name": "Al Jazeera Mubasher",
     "url": "https://live-hls-web-ajm.getaj.net/AJM/01.m3u8", "group": "ARABIC",
     "language": "AR", "isLive": True, "logoUrl": _LOGO_AR},
    {"id": "ch_04", "channelNumber": 4, "name": "NASA TV HD",
     "url": "https://ntv1.akamaized.net/hls/live/2014075/NASA-NTV1-HLS/master.m3u8", "group": "TECH",
     "language": "EN", "isLive": True, "logoUrl": _LOGO_TECH},
    {"id": "ch_05", "channelNumber": 5, "name": "Red Bull TV",
     "url": "https://rbmn-live.akamaized.net/hls/live/590964/BoRB-AT/master.m3u8", "group": "SPORTS",
     "language": "EN", "isLive": True, "logoUrl": _LOGO_SPORT},
    {"id": "ch_06", "channelNumber": 6, "name": "TRT World",
     "url": "https://tv-trtworld.medya.trt.com.tr/master.m3u8", "group": "NEWS",
     "language": "EN", "isLive": True, "logoUrl": _LOGO_NEWS},
    {"id": "ch_07", "channelNumber": 7, "name": "DW News",
     "url": "https://dwamdstream102.akamaized.net/hls/live/2015525/dwstream102/index.m3u8", "group": "NEWS",
     "language": "EN", "isLive": True, "logoUrl": _LOGO_NEWS},
    {"id": "ch_08", "channelNumber": 8, "name": "Tears of Steel",
     "url": "https://demo.unified-streaming.com/k8s/features/stable/video/tears-of-steel/tears-of-steel.ism/.m3u8",
     "group": "MOVIES", "language": "EN", "isLive": False, "logoUrl": _LOGO_MOVIE},
    {"id": "ch_09", "channelNumber": 9, "name": "Big Buck Bunny",
     "url": "https://test-streams.mux.dev/x36xhzz/x36xhzz.m3u8", "group": "CARTOONS",
     "language": "EN", "isLive": False, "logoUrl": _LOGO_KIDS},
    {"id": "ch_10", "channelNumber": 10, "name": "Apple 16:9",
     "url": "https://devstreaming-cdn.apple.com/videos/streaming/examples/bipbop_16x9/bipbop_16x9_variant.m3u8",
     "group": "TECH", "language": "EN", "isLive": True, "logoUrl": _LOGO_TECH},
]

# 4.4 — أفلام (3)
DEFAULT_FILMS: List[Dict[str, Any]] = [
    {"id": "film_01", "channelNumber": 1, "name": "Tears of Steel",
     "url": "https://demo.unified-streaming.com/k8s/features/stable/video/tears-of-steel/tears-of-steel.ism/.m3u8",
     "group": "SCI-FI", "language": "EN", "isLive": False, "logoUrl": _LOGO_MOVIE},
    {"id": "film_02", "channelNumber": 2, "name": "Mux HD Cinema",
     "url": "https://test-streams.mux.dev/x36xhzz/x36xhzz.m3u8",
     "group": "ACTION", "language": "EN", "isLive": False, "logoUrl": _LOGO_MOVIE},
    {"id": "film_03", "channelNumber": 3, "name": "Red Bull Adventure",
     "url": "https://rbmn-live.akamaized.net/hls/live/590964/BoRB-AT/master.m3u8",
     "group": "DOCUMENTARY", "language": "EN", "isLive": False, "logoUrl": _LOGO_SPORT},
]

# 4.4 — كرتون (2)
DEFAULT_CARTOONS: List[Dict[str, Any]] = [
    {"id": "cart_01", "channelNumber": 1, "name": "Big Buck Bunny",
     "url": "https://test-streams.mux.dev/x36xhzz/x36xhzz.m3u8",
     "group": "ANIMATION", "language": "EN", "isLive": False, "logoUrl": _LOGO_KIDS},
    {"id": "cart_02", "channelNumber": 2, "name": "Apple Test",
     "url": "https://devstreaming-cdn.apple.com/videos/streaming/examples/bipbop_16x9/bipbop_16x9_variant.m3u8",
     "group": "KIDS", "language": "EN", "isLive": False, "logoUrl": _LOGO_KIDS},
]


def default_channels() -> List[Dict[str, Any]]:
    """كل القنوات الافتراضية (10 + 3 أفلام + 2 كرتون)."""
    return list(DEFAULT_CHANNELS) + list(DEFAULT_FILMS) + list(DEFAULT_CARTOONS)


# ============================================================
# 4.1 — سكرابينج ألووي (HTML)
# ============================================================
GENRE_ANCHOR = re.compile(r'class="movie-img"')
GENRE_LINK = re.compile(r'<h3[^>]*>\s*<a[^>]*href="([^"]+)"[^>]*>(.*?)</a>', re.I | re.S)
GENRE_IMG = re.compile(r'(?:data-src|data-original|data-lazy-src|src)="([^"]+)"', re.I)
EPISODE_COUNT = re.compile(r'(\d+)\s*عدد الحلقات')
TAG = re.compile(r"<[^>]+>")
WATCH_TITLE = re.compile(r"<h1[^>]*>(.*?)</h1>|<title[^>]*>(.*?)</title>", re.I | re.S)
WATCH_POSTER = re.compile(r'<(?:video|img)[^>]*(?:poster|src)="([^"]+)"', re.I)
BTN_EP = re.compile(r'class="[^"]*btn-ep[^"]*"')
SOURCE_SRC = re.compile(r'<source[^>]+src="([^"]+)"', re.I)


def parse_genre_html(html: str, base: str = SCRAPING_DOMAIN) -> List[Dict[str, Any]]:
    """صفحة فئة → كروت (سكان شريحي 2600 حرف، حد أقصى 300، بلا تكرار)."""
    if not html:
        return []
    cards: List[Dict[str, Any]] = []
    seen = set()
    for anchor in GENRE_ANCHOR.finditer(html):
        if len(cards) >= MAX_GENRE_CARDS:
            break
        chunk = html[anchor.start():anchor.start() + 2600]
        link = GENRE_LINK.search(chunk)
        if not link:
            continue
        page_url = link.group(1).strip()
        title = " ".join(TAG.sub("", link.group(2)).split())
        image = ""
        for match in GENRE_IMG.finditer(chunk):
            candidate = match.group(1).strip()
            if "blank_thumbnail" in candidate:
                continue
            image = candidate
            break
        count_match = EPISODE_COUNT.search(chunk)
        episodes = int(count_match.group(1)) if count_match else 0
        if not page_url or page_url in seen:
            continue
        seen.add(page_url)
        cards.append({
            "name": title,
            "url": _absolute(page_url, base),
            "logoUrl": _absolute(image, base),
            "episodes": episodes,
            "group": "ALOOY",
            "isLive": False,
        })
    return cards


def parse_watch_html(html: str, base: str = SCRAPING_DOMAIN) -> Dict[str, Any]:
    """صفحة /watch → بوستر + عنوان + حلقات (أو حلقة واحدة من أول <source>)."""
    if not html:
        return {}
    title = ""
    for match in WATCH_TITLE.finditer(html):
        title = " ".join(TAG.sub("", (match.group(1) or match.group(2) or "")).split())
        if title:
            break
    poster = ""
    poster_match = WATCH_POSTER.search(html)
    if poster_match:
        poster = _absolute(poster_match.group(1).strip(), base)
    episodes: List[Dict[str, Any]] = []
    for anchor in BTN_EP.finditer(html):
        if len(episodes) >= MAX_EPISODES:
            break
        chunk = html[anchor.start():anchor.start() + 2600]
        source = SOURCE_SRC.search(chunk)
        if not source:
            continue
        episodes.append({"number": len(episodes) + 1, "url": _absolute(source.group(1).strip(), base)})
    if not episodes:
        first = SOURCE_SRC.search(html)
        if first:
            episodes.append({"number": 1, "url": _absolute(first.group(1).strip(), base)})
    return {"name": title, "poster": poster, "episodes": episodes, "group": "ALOOY", "isLive": False}


def _absolute(url: str, base: str) -> str:
    if not url:
        return ""
    if url.startswith(("http://", "https://")):
        return url
    return base.rstrip("/") + "/" + url.lstrip("/")


async def scrape_genre(path: str = "/genre/arabic.html") -> List[Dict[str, Any]]:
    url = path if path.startswith("http") else SCRAPING_DOMAIN + path
    html = await http.get_text(url, headers=keys.ALOOY_HEADERS, timeout=25.0)
    return parse_genre_html(html or "", SCRAPING_DOMAIN)


async def scrape_watch(path: str) -> Dict[str, Any]:
    url = path if path.startswith("http") else SCRAPING_DOMAIN + path
    html = await http.get_text(url, headers=keys.ALOOY_HEADERS, timeout=25.0)
    return parse_watch_html(html or "", SCRAPING_DOMAIN)


# ============================================================
# 4.6 — محلّل M3U
# ============================================================
_ATTR = lambda name: re.compile(name + r'="([^"]*)"', re.I)


def parse_m3u(content: str) -> List[Dict[str, Any]]:
    """يحلّل #EXTINF مع tvg-* و group-title (كابيتال) و http-user-agent/referrer."""
    if not content:
        return []
    lines = content.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    channels: List[Dict[str, Any]] = []
    meta: Dict[str, str] = {}
    for line in lines:
        line = line.strip()
        if not line:
            continue
        if line.startswith("#EXTINF"):
            meta = {
                "name": line.split(",")[-1].strip() if "," in line else "",
                "tvg_id": _attr(line, "tvg-id"),
                "tvg_name": _attr(line, "tvg-name"),
                "logo": _attr(line, "tvg-logo"),
                "group": (_attr(line, "group-title") or "IPTV").upper(),
                "language": _attr(line, "tvg-language") or "EN",
                "http_user_agent": _attr(line, "http-user-agent"),
                "http_referrer": _attr(line, "referrer") or _attr(line, "http-referrer"),
            }
        elif line.startswith("#"):
            continue
        elif line.startswith(("http://", "https://", "rtmp://", "rtmps://", "rtsp://")):
            channels.append({
                "name": meta.get("name") or "قناة",
                "url": line,
                "logo": meta.get("logo", ""),
                "group": meta.get("group") or "IPTV",
                "tvg_id": meta.get("tvg_id", ""),
                "tvg_name": meta.get("tvg_name", ""),
                "language": meta.get("language") or "EN",
                "httpUserAgent": meta.get("http_user_agent", ""),
                "httpReferrer": meta.get("http_referrer", ""),
                "isLive": True,
            })
            meta = {}
    return channels


def _attr(line: str, name: str) -> str:
    match = _ATTR(name).search(line)
    return match.group(1).strip() if match else ""


# ============================================================
# 4.5 — كتالوج الراديو
# ملاحظة: ملف assets/radio_catalog.json مش موجود في الريبو (التطبيق مش هنا)،
# فاتعملت بنية مطابقة: نفس الـ 6 تصنيفات ونفس الأنواع ونفس عدد العناصر
# المتوقّع لكل تصنيف. لو الملف موجود في أي مسار (RADIO_CATALOG_PATH أو
# data/radio_catalog.json) بيتقرا منه فعلياً.
# ============================================================
RADIO_CATEGORIES: List[Dict[str, Any]] = [
    {"name": "🟢 شيوخ العصر الحديث", "type": "modern", "expected_items": 16, "items": []},
    {"name": "🟤 شيوخ العصر القديم", "type": "classic", "expected_items": 8, "items": []},
    {"name": "📚 إذاعات القرآن الكريم", "type": "radio_quran", "expected_items": 7, "items": []},
    {"name": "🤲 الرقية الشرعية والأذكار", "type": "islamic", "expected_items": 6, "items": []},
    {"name": "🎤 المطربين", "type": "music_artists", "expected_items": 2, "items": []},
    {"name": "📻 المحطات الموسيقية", "type": "music_radios", "expected_items": 14, "items": []},
]

RADIO_TYPE_ICON = {
    "modern": "Person",
    "classic": "Person",
    "quran": "MenuBook",
    "radio_quran": "MenuBook",
    "islamic": "Favorite",
    "music_artists": "Mic",
    "music": "Radio",
}

_CATALOG_CANDIDATES = [
    os.getenv("RADIO_CATALOG_PATH", ""),
    str(Path(__file__).resolve().parent.parent.parent / "data" / "radio_catalog.json"),
    str(Path(__file__).resolve().parent.parent.parent / "app" / "src" / "main" / "assets" / "radio_catalog.json"),
]


def load_radio_catalog() -> List[Dict[str, Any]]:
    """يحمّل تصنيفات الراديو من الملف لو موجود، وإلا البنية المُعاد إنشاؤها."""
    for candidate in _CATALOG_CANDIDATES:
        if candidate and Path(candidate).is_file():
            try:
                data = json.loads(Path(candidate).read_text(encoding="utf-8"))
                categories = []
                for category in data.get("categories") or []:
                    items = [{"name": clean_text(i.get("name")), "url": clean_text(i.get("url"))}
                             for i in (category.get("items") or []) if isinstance(i, dict)]
                    categories.append({
                        "name": clean_text(category.get("name")),
                        "type": clean_text(category.get("type")),
                        "items": items,
                    })
                if categories:
                    return categories
            except Exception as exc:
                logger.warning("فشل قراءة كتالوج الراديو %s: %s", candidate, exc)
    return RADIO_CATEGORIES


def radio_stations(custom_lines: Optional[List[str]] = None) -> List[Dict[str, Any]]:
    """محطات الراديو كعناصر بوت: كتالوج + مخصّصة (name|||url)."""
    stations: List[Dict[str, Any]] = []
    for category in load_radio_catalog():
        for item in category.get("items") or []:
            stations.append({
                "id": f"radio_{abs(hash(item.get('url') or ''))}",
                "name": item.get("name"),
                "url": item.get("url"),
                "group": f"RADIO/{category.get('type')}",
                "logoUrl": "",
                "language": "AR",
                "isLive": True,
            })
    for line in custom_lines or []:
        if "|||" not in line:
            continue
        name, url = line.split("|||", 1)
        name, url = clean_text(name), clean_text(url)
        if not url:
            continue
        stations.append({
            "id": f"radio_{abs(hash(url))}",
            "name": name or "محطة",
            "url": url,
            "group": "RADIO/CUSTOM",
            "logoUrl": "",
            "language": "AR",
            "isLive": True,
        })
    return stations


def clean_text(value: Any) -> str:
    if value is None:
        return ""
    text = str(value).strip()
    if text.lower() in ("", "null", "none", "undefined"):
        return ""
    return text
