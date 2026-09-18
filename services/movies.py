"""Hikaye TV movies client with resilient search and HLS-ready sources."""
from __future__ import annotations
import asyncio, json, logging, re, unicodedata
from typing import Any, Dict, List, Optional
import aiohttp

logger = logging.getLogger(__name__)
BASE_URL = "https://admin.golive-pro.online/api"

CATEGORIES = {
    "arabic_all": "a41d4764-d74e-4df3-a5aa-51e1725fe42e",
    "foreign_general": "7bd112fc-a3c2-49ab-a3d7-5287ffd1d045",
    "arabic_movies": "2185cd2d-f379-4584-8caa-5884bced7150",
    "foreign_movies": "9ec354e5-4707-4161-9dab-b51f899b29d8",
}
CATEGORY_LABELS = {
    "arabic_all": "🇸🇦 أفلام عربية",
    "foreign_general": "🌍 أفلام أجنبية",
    "arabic_movies": "🎬 أفلام عربية",
    "foreign_movies": "🎥 أفلام أجنبية",
    "most_viewed": "🔥 الأكثر مشاهدة",
    "top_rated": "⭐ أعلى تقييم",
}

def _norm(s: str) -> str:
    s = str(s or "").strip().lower()
    s = unicodedata.normalize("NFKD", s)
    s = "".join(c for c in s if not unicodedata.combining(c))
    s = re.sub(r"[\W_]+", " ", s, flags=re.UNICODE)
    # common Arabic variants
    return s.replace("أ","ا").replace("إ","ا").replace("آ","ا").strip()

def _parse_links(data: Dict[str, Any]) -> list:
    sources = []
    seen = set()
    raw_groups = [
        data.get("sources"), data.get("watch_links"), data.get("download_links"),
        data.get("streams"), data.get("servers")
    ]
    for group in raw_groups:
        if not isinstance(group, list):
            continue
        for s in group:
            if not isinstance(s, dict):
                continue
            url = (s.get("streamUrl") or s.get("url") or s.get("link") or s.get("stream_url") or "").strip()
            if not url or url in seen:
                continue
            seen.add(url)
            headers = s.get("headersJson") or s.get("headers") or {}
            if isinstance(headers, str):
                try: headers = json.loads(headers)
                except Exception: headers = {}
            sources.append({
                "id": s.get("id", ""),
                "label": s.get("label") or s.get("server_name") or s.get("server") or "سيرفر",
                "url": url,
                "quality": s.get("quality") or s.get("resolution") or "",
                "format": s.get("format") or "",
                "headers": headers if isinstance(headers, dict) else {},
            })
    return sources

def _parse_movie(data: Dict[str, Any]) -> Optional[Dict]:
    if not isinstance(data, dict):
        return None
    sources = _parse_links(data)
    title = data.get("titleAr") or data.get("title_ar") or data.get("title") or data.get("titleEn") or data.get("title_en") or "بدون عنوان"
    return {
        "id": data.get("id") or data.get("_id") or data.get("movieId") or "",
        "title": str(title)[:120],
        "title_en": data.get("titleEn") or data.get("title_en") or "",
        "year": data.get("year") or data.get("release_year") or data.get("releaseYear") or "",
        "rating": data.get("rating") or 0,
        "duration": data.get("duration"),
        "genre": data.get("genreAr") or data.get("genre") or "",
        "poster": data.get("posterUrl") or data.get("poster") or "",
        "description": (data.get("descriptionAr") or data.get("description") or "")[:500],
        "view_count": data.get("viewCount") or data.get("view_count") or 0,
        "sources": sources,
        "url": sources[0]["url"] if sources else "",
        "category": "",
    }

def _session_headers() -> Dict[str,str]:
    return {
        "User-Agent": "Mozilla/5.0 (Linux; Android 15) AppleWebKit/537.36 Chrome/131.0 Mobile Safari/537.36",
        "Accept": "application/json,text/plain,*/*",
        "Accept-Language": "ar,en;q=0.9",
        "Connection": "keep-alive",
    }

async def _get(session, path, params=None, attempts=4):
    url = f"{BASE_URL}{path}"
    last = None
    for attempt in range(attempts):
        try:
            async with session.get(url, params=params or {}, timeout=aiohttp.ClientTimeout(total=20)) as resp:
                text = await resp.text()
                if resp.status != 200:
                    raise RuntimeError(f"HTTP {resp.status}")
                try:
                    return json.loads(text)
                except json.JSONDecodeError:
                    return None
        except (aiohttp.ClientError, asyncio.TimeoutError, RuntimeError) as e:
            last = e
            if attempt + 1 < attempts:
                await asyncio.sleep(min(2 ** attempt, 5))
    logger.warning("movies API failed %s params=%s: %s", path, params, last)
    return None

def _items(data):
    if isinstance(data, list): return data
    if isinstance(data, dict):
        for key in ("data", "movies", "results", "items"):
            if isinstance(data.get(key), list):
                return data[key]
    return []

async def search_movies(query: str, category_key: Optional[str] = None, limit: int = 15, page: int = 1) -> List[Dict]:
    query = (query or "").strip()
    if len(query) < 2: return []
    params_list = [
        {"search": query, "page": page, "limit": limit},
        {"search": query, "page": page, "limit": limit, "sortBy": "createdAt", "sortOrder": "desc"},
    ]
    if category_key in CATEGORIES:
        for p in params_list: p["categoryId"] = CATEGORIES[category_key]
    results, seen = [], set()
    async with aiohttp.ClientSession(headers=_session_headers()) as session:
        for params in params_list:
            data = await _get(session, "/content/movies", params)
            for item in _items(data):
                m = _parse_movie(item)
                key = str(m.get("id")) if m and m.get("id") else _norm(m.get("title") if m else "")
                if m and key and key not in seen:
                    seen.add(key); results.append(m)
            if len(results) >= limit:
                break
        # If the API returned too few matches, try a conservative second page.
        if len(results) < min(5, limit) and page == 1:
            data = await _get(session, "/content/movies", {"search": query, "page": 2, "limit": limit})
            for item in _items(data):
                m = _parse_movie(item)
                key = str(m.get("id")) if m and m.get("id") else _norm(m.get("title") if m else "")
                if m and key and key not in seen:
                    seen.add(key); results.append(m)
    # Prefer exact/contains matches, but never hide API results just because titles differ.
    nq = _norm(query)
    results.sort(key=lambda m: (0 if nq == _norm(m.get("title")) else 1 if nq in _norm(m.get("title")) else 2))
    if category_key:
        for m in results: m["category"] = CATEGORY_LABELS.get(category_key, category_key)
    return results[:limit]

async def get_most_viewed(limit=12):
    async with aiohttp.ClientSession(headers=_session_headers()) as session:
        data = await _get(session, "/content/movies/most-viewed", {"limit": limit})
    return [m for x in _items(data) if (m := _parse_movie(x))][:limit]

async def get_by_category(category_key, page=1, limit=20):
    if category_key not in CATEGORIES: return []
    params={"categoryId": CATEGORIES[category_key], "page": page, "limit": limit, "sortBy":"createdAt", "sortOrder":"desc"}
    async with aiohttp.ClientSession(headers=_session_headers()) as session:
        data=await _get(session, "/content/movies", params)
    out=[]
    for x in _items(data):
        m=_parse_movie(x)
        if m:
            m["category"]=CATEGORY_LABELS.get(category_key, category_key); out.append(m)
    return out

async def get_top_rated(page=1, limit=20, min_rating=7.0):
    params={"ratingMin":min_rating,"page":page,"limit":limit,"sortBy":"rating","sortOrder":"desc"}
    async with aiohttp.ClientSession(headers=_session_headers()) as session:
        data=await _get(session, "/content/movies", params)
    return [m for x in _items(data) if (m:=_parse_movie(x))]

async def get_movie_by_id(movie_id):
    async with aiohttp.ClientSession(headers=_session_headers()) as session:
        data=await _get(session, f"/content/movies/{movie_id}")
    return _parse_movie(data) if isinstance(data, dict) else None

async def get_by_year(year, page=1, limit=20):
    params={"year":year,"page":page,"limit":limit}
    async with aiohttp.ClientSession(headers=_session_headers()) as session:
        data=await _get(session, "/content/movies", params)
    return [m for x in _items(data) if (m:=_parse_movie(x))]
