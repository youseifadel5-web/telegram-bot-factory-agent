"""Unified cinema facade over the existing OscarTV API.

This module does not replace the existing movie/series services.  It only
normalizes the already configured OscarTV source for the new Cinema UI.
"""
from __future__ import annotations

import json
import logging
from typing import Any, Dict, List, Optional

from services.oscar_movies import oscar_api

logger = logging.getLogger(__name__)


def _as_list(value: Any) -> List[dict]:
    if isinstance(value, list):
        return [x for x in value if isinstance(x, dict)]
    return []


def _url(value: Any) -> str:
    return str(value or "").strip()


def _headers(value: Any) -> dict:
    if isinstance(value, dict):
        return {str(k): str(v) for k, v in value.items()}
    if isinstance(value, str):
        try:
            obj = json.loads(value)
            return obj if isinstance(obj, dict) else {}
        except Exception:
            return {}
    return {}


def _extract_groups(data: dict) -> List[dict]:
    """Accept the different link shapes used by the existing API.

    The old API has returned lists, dictionaries keyed by quality, and direct
    string URLs over time. Normalize all of them without changing the source.
    """
    groups = []

    def add(value, typ):
        if isinstance(value, list):
            for x in value:
                if isinstance(x, dict):
                    y = dict(x); y["type"] = x.get("type") or typ; groups.append(y)
                elif isinstance(x, str) and x.strip():
                    groups.append({"url": x.strip(), "type": typ})
        elif isinstance(value, dict):
            # A single link object.
            if any(k in value for k in ("url", "link", "stream_url", "streamUrl")):
                y = dict(value); y["type"] = value.get("type") or typ; groups.append(y)
            else:
                # quality -> url / object
                for quality, obj in value.items():
                    if isinstance(obj, str) and obj.strip():
                        groups.append({"url": obj.strip(), "quality": quality, "type": typ})
                    elif isinstance(obj, dict):
                        y = dict(obj); y.setdefault("quality", quality); y["type"] = y.get("type") or typ; groups.append(y)
        elif isinstance(value, str) and value.strip():
            groups.append({"url": value.strip(), "type": typ})

    for key, typ in (
        ("watch_links", "watch"),
        ("download_links", "download"),
        ("downloads", "download"),
        ("sources", "watch"),
        ("streams", "watch"),
        ("watch", "watch"),
        ("links", "watch"),
        ("playback", "watch"),
        ("media", "watch"),
        ("files", "download"),
    ):
        if key in data:
            add(data.get(key), typ)

    for key in (
        "url", "link", "stream_url", "streamUrl", "watch_url", "download_url",
        "hls", "hls_url", "m3u8", "file", "src", "playback_url", "media_url",
    ):
        if data.get(key):
            typ = "download" if "download" in key else "watch"
            groups.append({
                "url": data.get(key),
                "quality": data.get("quality") or data.get("resolution"),
                "type": typ,
                "size": data.get("file_size") or data.get("size"),
            })
    return groups


def _link_rank(link: Dict[str, Any]) -> tuple:
    """Lower is better. Prefer HLS/m3u8 for playback & stream over direct mp4."""
    url = str(link.get("url") or "").lower()
    fmt = str(link.get("format") or "").lower()
    typ = str(link.get("type") or "watch").lower()
    score = 50
    if typ == "download":
        score += 100
    if fmt == "m3u8" or ".m3u8" in url or "/hls/" in url or "mpegurl" in url:
        score -= 40
    elif fmt == "mpd" or ".mpd" in url:
        score -= 20
    elif fmt == "mp4" or ".mp4" in url:
        score += 10  # usable but not preferred for live RTMP
    # Prefer higher resolution labels lightly
    q = str(link.get("quality") or "").lower()
    for i, tag in enumerate(("2160", "4k", "1080", "720", "480", "360", "240")):
        if tag in q:
            score -= (6 - i)
            break
    return (score, q)


def prefer_stream_links(links: List[Dict[str, Any]], *, for_download: bool = False) -> List[Dict[str, Any]]:
    """Filter + sort links for watch/stream (HLS first) or download (mp4 first)."""
    if not links:
        return []
    items = [x for x in links if x.get("url")]
    if for_download:
        # prefer mp4 / download type
        dl = [x for x in items if str(x.get("type") or "").lower() == "download"]
        mp4 = [x for x in items if str(x.get("format") or "").lower() == "mp4" or ".mp4" in str(x.get("url")).lower()]
        pool = dl or mp4 or items
        return sorted(pool, key=lambda x: (0 if ".mp4" in str(x.get("url")).lower() else 1, str(x.get("quality") or "")))
    # watch / stream: prefer non-download, HLS
    watch = [x for x in items if str(x.get("type") or "watch").lower() != "download"]
    if not watch:
        watch = items
    hls = [x for x in watch if str(x.get("format") or "").lower() == "m3u8"
           or ".m3u8" in str(x.get("url")).lower()
           or "/hls/" in str(x.get("url")).lower()]
    pool = hls if hls else watch
    return sorted(pool, key=_link_rank)



def normalize_links(data: Any) -> List[Dict[str, Any]]:
    if not isinstance(data, dict):
        if isinstance(data, list):
            # some APIs return a bare list of link objects
            data = {"links": data}
        else:
            return []
    out = []
    seen = set()
    for item in _extract_groups(data):
        url = _url(
            item.get("url")
            or item.get("link")
            or item.get("stream_url")
            or item.get("streamUrl")
            or item.get("src")
            or item.get("file")
            or item.get("hls")
            or item.get("m3u8")
        )
        typ0 = str(item.get("type") or "watch").lower()
        if typ0 in ("dl", "file", "files"):
            typ0 = "download"
        key = f"{typ0}|{url}"
        if not url or key in seen:
            continue
        seen.add(key)
        headers = _headers(item.get("headers") or item.get("headersJson") or item.get("http_headers"))
        quality = item.get("quality") or item.get("resolution") or item.get("label") or "جودة متاحة"
        fmt = str(item.get("format") or "").lower()
        lower = url.lower()
        if not fmt:
            if ".m3u8" in lower or "mpegurl" in lower or "/hls/" in lower:
                fmt = "m3u8"
            elif ".mp4" in lower:
                fmt = "mp4"
            elif ".mpd" in lower:
                fmt = "mpd"
        typ = item.get("type") or "watch"
        if str(typ).lower() in ("dl", "file", "files"):
            typ = "download"
        out.append({
            "url": url,
            "quality": str(quality),
            "label": item.get("server_name") or item.get("server") or item.get("label") or "سيرفر",
            "format": fmt,
            "headers": headers,
            "type": typ,
            "size": item.get("file_size") or item.get("size") or "",
        })
    try:
        out.sort(key=_link_rank)
    except Exception:
        pass
    return out


def normalize(item: dict, kind: str, details: bool = False) -> dict:
    if not isinstance(item, dict):
        return {"kind": kind, "id": None, "title": "بدون عنوان", "links": []}
    title = item.get("title_ar") or item.get("title_en") or item.get("title") or "بدون عنوان"
    poster = (item.get("poster") or item.get("poster_url") or item.get("posterUrl") or
              item.get("image") or item.get("image_url") or item.get("thumbnail") or "")
    if poster and str(poster).startswith("/"):
        poster = f"{'https://ostvapp.cam'}{poster}"
    elif poster and not str(poster).startswith(("http://", "https://")):
        poster = f"https://ostvapp.cam/{str(poster).lstrip('/')}"
    genres = item.get("genres") or item.get("genre") or item.get("genre_list") or ""
    if isinstance(genres, list):
        names = []
        for g in genres:
            if isinstance(g, dict):
                names.append(str(g.get("name") or g.get("title") or g.get("name_ar") or ""))
            elif g:
                names.append(str(g))
        genres = ", ".join(x for x in names if x)
    return {
        "id": item.get("id") or item.get("_id"),
        "kind": kind,
        "title": str(title),
        "title_en": str(item.get("title_en") or item.get("titleEn") or ""),
        "year": item.get("release_year") or item.get("year") or item.get("releaseYear") or "",
        "rating": item.get("rating") or item.get("vote_average") or "",
        "genre": str(genres or ""),
        "story": item.get("story") or item.get("description") or item.get("overview") or "",
        "poster": str(poster or ""),
        "seasons": _as_list(item.get("seasons")),
        "episodes_count": item.get("episode_count") or item.get("episodes_count") or 0,
        "links": normalize_links(item) if details else [],
        "source": "oscar",
    }



def _fuzzy_variants(query: str) -> list:
    """Arabic/English transliteration hints for smarter search."""
    q = (query or "").strip()
    if not q:
        return []
    variants = [q]
    # common Arabic -> Latin movie word map (partial titles)
    mapping = {
        "افنجرز": "avengers",
        "افينجرز": "avengers",
        "اند جيم": "endgame",
        "اندجيم": "endgame",
        "هاري بوتر": "harry potter",
        "هاري": "harry",
        "بوتر": "potter",
        "حجر": "stone",
        "انترستلر": "interstellar",
        "انترستيلار": "interstellar",
        "اوبنهايمر": "oppenheimer",
        "افاتار": "avatar",
        "جoker": "joker",
        "جوكر": "joker",
        "ماتريكس": "matrix",
        "باتمان": "batman",
        "سوبرمان": "superman",
        "سبايدرمان": "spiderman",
        "سبايدر مان": "spider-man",
        "كابتن امريكا": "captain america",
        "ايرون مان": "iron man",
        "ثور": "thor",
        "ديدبول": "deadpool",
        "جون ويك": "john wick",
        "فاست": "fast",
        "فيوريوس": "furious",
        "كروتون": "cartoon",
        "انمي": "anime",
        "أنمي": "anime",
    }
    low = q.replace("أ", "ا").replace("إ", "ا").replace("آ", "ا")
    for ar, en in mapping.items():
        if ar in low or ar in q:
            variants.append(en)
            variants.append(q.replace(ar, en))
    # latin-ish space normalize
    variants.append(q.replace("اند", "and").replace("و", " "))
    # unique preserve order
    out, seen = [], set()
    for v in variants:
        v2 = " ".join(str(v).split()).strip()
        if v2 and v2.lower() not in seen:
            seen.add(v2.lower())
            out.append(v2)
    return out[:6]


async def search(query: str, limit: int = 12) -> List[dict]:
    """Search movies/series/anime with fuzzy variants; Oscar + Hekaya independent."""
    import asyncio
    q = (query or "").strip()
    if len(q) < 2:
        return []
    variants = _fuzzy_variants(q)

    async def safe(fn, qq):
        try:
            return await fn(qq, limit=limit)
        except Exception as exc:
            logger.warning("cinema search failed: %s", exc)
            return []

    results = []
    seen_ids = set()
    for v in variants:
        movie, series, anime = await asyncio.gather(
            safe(oscar_api.search_movies, v),
            safe(oscar_api.search_series, v),
            safe(oscar_api.search_anime, v),
        )
        for x in movie:
            n = normalize(x, "movie"); key = ("oscar", n.get("id"), "movie")
            if key not in seen_ids:
                seen_ids.add(key); results.append(n)
        for x in series:
            n = normalize(x, "series"); key = ("oscar", n.get("id"), "series")
            if key not in seen_ids:
                seen_ids.add(key); results.append(n)
        for x in anime:
            n = normalize(x, "anime"); key = ("oscar", n.get("id"), "anime")
            if key not in seen_ids:
                seen_ids.add(key); results.append(n)
        try:
            from services import hekaya
            hk = await hekaya.search(v, page=1, limit=limit)
            for x in hk or []:
                n = normalize(x, x.get("kind") or "movie")
                n["source"] = "hekaya"
                key = ("hekaya", n.get("id"), n.get("kind"))
                if key not in seen_ids:
                    seen_ids.add(key); results.append(n)
        except Exception as e:
            logger.debug("hekaya search: %s", e)
        if len(results) >= limit * 3:
            break
    return results[: max(1, limit * 3)]


async def details(kind: str, item_id: int) -> Optional[dict]:
    try:
        if kind == "movie":
            data = await oscar_api.get_movie_details(int(item_id))
        elif kind == "series":
            data = await oscar_api.get_series_details(int(item_id))
        else:
            data = await oscar_api.get_anime_details(int(item_id))
        return normalize(data, kind, details=True) if data else None
    except Exception as exc:
        logger.warning("cinema details failed %s/%s: %s", kind, item_id, exc)
        return None


async def episodes(kind: str, parent_id: int, season_id: Optional[int] = None, page: int = 1) -> List[dict]:
    try:
        if kind == "anime":
            return await oscar_api.get_anime_episodes(int(parent_id), page=page, per_page=20, season_id=season_id)
        if season_id:
            return await oscar_api.get_season_episodes(int(season_id), page=page)
        return []
    except Exception as exc:
        logger.warning("cinema episodes failed: %s", exc)
        return []


async def episode_details(kind: str, episode_id: int) -> Optional[dict]:
    try:
        data = await (oscar_api.get_anime_episode_details(int(episode_id)) if kind == "anime" else oscar_api.get_episode_details(int(episode_id)))
        if not data:
            return None
        data = dict(data)
        data["links"] = normalize_links(data)
        return data
    except Exception as exc:
        logger.warning("cinema episode details failed: %s", exc)
        return None
