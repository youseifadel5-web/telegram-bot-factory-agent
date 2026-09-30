"""IPTV packages catalog — worldwide channels from iptv-org (GitHub).

Lazy per-package caching:
  - Packages = categories (أفلام، أخبار، رياضة ...) + country quick entries (مصر ...).
  - Inside a package the list can be filtered: عربي / أجنبي / مترجم / الكل.
  - "مترجم" = channel name carries a translation marker, or a subtitle track was
    detected by ffprobe during playback (persisted in data/iptv/catalog_cc.json).
Data source: https://iptv-org.github.io/iptv/ (auto-updated playlists).
"""
from __future__ import annotations

import asyncio
import json
import logging
import time
from pathlib import Path
from typing import Dict, List, Optional

from services.iptv import parse_m3u, fetch_m3u, filter_visible_channels

logger = logging.getLogger(__name__)

ROOT = Path(__file__).resolve().parent.parent
CATALOG_DIR = ROOT / "data" / "iptv" / "catalog"
CATALOG_DIR.mkdir(parents=True, exist_ok=True)

BASE = "https://iptv-org.github.io/iptv"

# ttl in seconds
CATEGORY_TTL = 6 * 3600
ARABIC_TTL = 24 * 3600
FETCH_TIMEOUT = 25

# (key, icon, arabic label) — displayed in this order.
CATEGORY_PACKAGES = [
    ("movies", "🎬", "أفلام"),
    ("series", "📺", "مسلسلات"),
    ("news", "📰", "أخبار"),
    ("sports", "⚽", "رياضة"),
    ("kids", "🧸", "أطفال"),
    ("music", "🎵", "موسيقى"),
    ("documentary", "🎓", "وثائقيات"),
    ("entertainment", "🎭", "ترفيه"),
    ("religious", "🕌", "ديني"),
    ("animation", "🎨", "رسوم متحركة"),
    ("comedy", "😂", "كوميديا"),
    ("cooking", "🍳", "طبخ"),
    ("culture", "🏛", "ثقافة"),
    ("education", "📚", "تعليم"),
    ("science", "🔬", "علوم"),
    ("travel", "✈️", "سفر"),
    ("business", "💼", "اقتصاد"),
    ("weather", "⛅", "طقس"),
    ("classic", "🎞", "كلاسيك"),
    ("family", "👨‍👩‍👧", "عائلي"),
    ("lifestyle", "✨", "لايف ستايل"),
    ("auto", "🚗", "سيارات"),
    ("outdoor", "🏕", "أنشطة خارجية"),
    ("relax", "🧘", "استرخاء"),
    ("shop", "🛍", "تسوق"),
    ("general", "📡", "عام"),
]

# Country quick entries (subset of countries/{cc}.m3u)
COUNTRY_PACKAGES = [
    ("eg", "🇪🇬", "قنوات مصر"),
    ("sa", "🇸🇦", "قنوات السعودية"),
    ("ae", "🇦🇪", "قنوات الإمارات"),
    ("ma", "🇲🇦", "قنوات المغرب"),
    ("dz", "🇩🇿", "قنوات الجزائر"),
    ("tn", "🇹🇳", "قنوات تونس"),
    ("iq", "🇮🇶", "قنوات العراق"),
    ("jo", "🇯🇴", "قنوات الأردن"),
    ("lb", "🇱🇧", "قنوات لبنان"),
    ("ly", "🇱🇾", "قنوات ليبيا"),
    ("sd", "🇸🇩", "قنوات السودان"),
    ("ps", "🇵🇸", "قنوات فلسطين"),
]

# name markers that usually mean a translated / subtitled channel
_CC_NAME_MARKERS = ("ترجمة", "مترجم", "مترجمة", " subtitles", "[cc]", "(cc)")

_ALL_PACKAGES = {k: (icon, label) for k, icon, label in CATEGORY_PACKAGES + COUNTRY_PACKAGES}


def package_meta(key: str):
    """Return (icon, arabic_label) for a package key, or None."""
    return _ALL_PACKAGES.get(key)


def _is_country(key: str) -> bool:
    return any(k == key for k, _, _ in COUNTRY_PACKAGES)


def package_url(key: str) -> str:
    if _is_country(key):
        return f"{BASE}/countries/{key}.m3u"
    return f"{BASE}/categories/{key}.m3u"


# --------------------------------------------------------------------------- #
# Arabic language set
# --------------------------------------------------------------------------- #

def _norm_name(name: str) -> str:
    return "".join(c for c in (name or "").lower() if c.isalnum())


def _arabic_cache_path() -> Path:
    return CATALOG_DIR / "arabic_set.json"


async def get_arabic_keys() -> set:
    """Set of urls + normalized names of Arabic-language channels (cached 24h)."""
    path = _arabic_cache_path()
    if path.exists():
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            if time.time() - float(data.get("ts", 0)) < ARABIC_TTL:
                return set(data.get("keys") or [])
        except Exception:
            pass
    keys: set = set()
    try:
        channels = await fetch_m3u(f"{BASE}/languages/ara.m3u", timeout=FETCH_TIMEOUT)
        for ch in channels:
            if ch.get("url"):
                keys.add(ch["url"])
            n = _norm_name(ch.get("name") or "")
            if n:
                keys.add(n)
    except Exception as e:
        logger.warning("arabic set fetch failed: %s", e)
        if path.exists():
            # keep serving the stale cache rather than an empty set
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
                return set(data.get("keys") or [])
            except Exception:
                pass
        return set()
    try:
        path.write_text(
            json.dumps({"ts": time.time(), "keys": sorted(keys)}, ensure_ascii=False),
            encoding="utf-8",
        )
    except Exception as e:
        logger.warning("arabic set save failed: %s", e)
    return keys


# --------------------------------------------------------------------------- #
# Subtitle (مترجم) registry
# --------------------------------------------------------------------------- #

def _cc_path() -> Path:
    return CATALOG_DIR / "catalog_cc.json"


def _load_cc() -> set:
    try:
        return set(json.loads(_cc_path().read_text(encoding="utf-8")).get("urls") or [])
    except Exception:
        return set()


def is_cc_channel(ch: Dict) -> bool:
    name = (ch.get("name") or "").lower()
    if any(m in name for m in _CC_NAME_MARKERS):
        return True
    return ch.get("url") in _load_cc()


def mark_cc(url: str) -> None:
    """Persist that this stream URL carries subtitle tracks (called after probe)."""
    if not url:
        return
    try:
        urls = _load_cc()
        if url in urls:
            return
        urls.add(url)
        _cc_path().write_text(
            json.dumps({"urls": sorted(urls)}, ensure_ascii=False), encoding="utf-8"
        )
    except Exception as e:
        logger.warning("mark_cc failed: %s", e)


# --------------------------------------------------------------------------- #
# Per-package cache
# --------------------------------------------------------------------------- #

def _package_cache_path(key: str) -> Path:
    return CATALOG_DIR / f"pkg_{key}.json"


def _load_cached_package(key: str) -> Optional[List[Dict]]:
    path = _package_cache_path(key)
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if time.time() - float(data.get("ts", 0)) < CATEGORY_TTL:
            return data.get("channels") or []
    except Exception:
        pass
    return None


async def get_package(key: str, force: bool = False) -> List[Dict]:
    """Channels of one package (category or country), cached, deduplicated."""
    if key not in _ALL_PACKAGES:
        return []
    if not force:
        cached = _load_cached_package(key)
        if cached is not None:
            return cached

    channels = filter_visible_channels(await fetch_m3u(package_url(key), timeout=FETCH_TIMEOUT))

    arabic = await get_arabic_keys()
    out, seen = [], set()
    for ch in channels:
        url = (ch.get("url") or "").split("#")[0].strip()
        if not url or url in seen:
            continue
        seen.add(url)
        ch = dict(ch)
        ch["url"] = url
        ch["package"] = key
        ch["arabic"] = url in arabic or _norm_name(ch.get("name") or "") in arabic
        name = (ch.get("name") or "")
        ch["geo_blocked"] = "geo-blocked" in name.lower() or "geo blocked" in name.lower()
        out.append(ch)

    try:
        _package_cache_path(key).write_text(
            json.dumps({"ts": time.time(), "channels": out}, ensure_ascii=False),
            encoding="utf-8",
        )
    except Exception as e:
        logger.warning("package cache save failed (%s): %s", key, e)
    return out


def filter_package(channels: List[Dict], lang: str) -> List[Dict]:
    if lang == "ara":
        return [c for c in channels if c.get("arabic")]
    if lang == "for":
        return [c for c in channels if not c.get("arabic")]
    if lang == "cc":
        return [c for c in channels if is_cc_channel(c)]
    return list(channels)


async def refresh_all() -> None:
    """Drop all cached packages (admin action)."""
    for p in CATALOG_DIR.glob("pkg_*.json"):
        try:
            p.unlink()
        except Exception:
            pass
