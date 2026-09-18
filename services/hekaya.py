"""Hekaya TV adapter.

The project previously contained an empty placeholder that always returned [].
This adapter supports a configured JSON API without inventing undocumented endpoints.
No .env values are changed by this module.
"""
from __future__ import annotations
import logging
import os
from typing import Any, Dict, List, Optional
from urllib.parse import urljoin

logger = logging.getLogger(__name__)
HEKAYA_BASE = (os.getenv("HEKAYA_BASE_URL") or os.getenv("HEKAYA_BASE") or "").strip().rstrip("/")
HEKAYA_SEARCH_PATH = os.getenv("HEKAYA_SEARCH_PATH", "/search").strip()
HEKAYA_MOVIES_PATH = os.getenv("HEKAYA_MOVIES_PATH", "/movies").strip()
HEKAYA_SERIES_PATH = os.getenv("HEKAYA_SERIES_PATH", "/series").strip()

def _items(payload: Any) -> List[Dict]:
    if isinstance(payload, list): return [x for x in payload if isinstance(x, dict)]
    if not isinstance(payload, dict): return []
    for key in ("results", "items", "data", "movies", "series"):
        value = payload.get(key)
        if isinstance(value, list): return [x for x in value if isinstance(x, dict)]
        if isinstance(value, dict):
            for k in ("results", "items"):
                if isinstance(value.get(k), list): return [x for x in value[k] if isinstance(x, dict)]
    return []

def _normalize(x: Dict, kind: str = "movie") -> Dict:
    return {
        **x,
        "id": x.get("id") or x.get("_id") or x.get("movie_id") or x.get("series_id"),
        "title": x.get("title") or x.get("name") or x.get("arabic_title") or "بدون عنوان",
        "kind": x.get("kind") or kind,
        "source": "hekaya",
    }

async def _get(path: str, params: Optional[dict] = None) -> List[Dict]:
    if not HEKAYA_BASE: return []
    import aiohttp
    url = urljoin(HEKAYA_BASE + "/", path.lstrip("/"))
    headers = {"User-Agent": "Mozilla/5.0 (compatible; KataBump/1.0)", "Accept": "application/json"}
    try:
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=15), headers=headers) as session:
            async with session.get(url, params=params or {}) as resp:
                if resp.status >= 400:
                    logger.warning("Hekaya HTTP %s", resp.status); return []
                return _items(await resp.json(content_type=None))
    except Exception as exc:
        logger.warning("Hekaya request failed: %s", exc)
        return []

async def get_movies(page: int = 1, limit: int = 10, sort: str = "most", **kw) -> List[Dict]:
    return [_normalize(x, "movie") for x in await _get(HEKAYA_MOVIES_PATH, {"page": page, "limit": limit, "sort": sort, **kw})]

async def get_series(page: int = 1, limit: int = 10, **kw) -> List[Dict]:
    return [_normalize(x, "series") for x in await _get(HEKAYA_SERIES_PATH, {"page": page, "limit": limit, **kw})]

async def search(query: str, page: int = 1, limit: int = 10) -> List[Dict]:
    if not HEKAYA_BASE or len((query or '').strip()) < 2: return []
    return [_normalize(x, x.get("kind") or "movie") for x in await _get(HEKAYA_SEARCH_PATH, {"q": query.strip(), "query": query.strip(), "page": page, "limit": limit})]

async def get_details(item_id: int, kind: str = "movie") -> Optional[Dict]:
    if not HEKAYA_BASE: return None
    path = f"/{kind}/{int(item_id)}"
    items = await _get(path)
    return _normalize(items[0], kind) if items else None
