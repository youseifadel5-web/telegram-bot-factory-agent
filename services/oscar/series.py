"""Oscar series / seasons / episodes endpoints."""
from __future__ import annotations
from typing import Any, Dict, List, Optional
from services.oscar.client import oscar_client


def _items(data: Any) -> list:
    if isinstance(data, list):
        return data
    if isinstance(data, dict):
        d = data.get("data")
        if isinstance(d, list):
            return d
        if isinstance(d, dict):
            return [d]
        return data.get("results") or data.get("items") or []
    return []


async def series(page: int = 1, limit: int = 20, search: str = None, sort_by: str = "most_viewed", **kw) -> List[Dict]:
    params = {"page": page, "limit": limit, "sort_by": sort_by, "app_version": 15, **kw}
    if search:
        params["search"] = search
    res = await oscar_client.get("/api/series/", params)
    return _items(res)


async def series_show(series_id: int) -> Optional[Dict]:
    res = await oscar_client.get("/api/series/show.php", {"id": series_id})
    if isinstance(res, dict) and res.get("status") == "success":
        return res.get("data") or res
    return res if isinstance(res, dict) else None


async def series_filters() -> Any:
    return await oscar_client.get("/api/series/filters.php", cache_ttl=6 * 3600)


async def seasons(series_id: int = None, **kw) -> List[Dict]:
    params = dict(kw)
    if series_id is not None:
        params["series_id"] = series_id
    res = await oscar_client.get("/api/seasons/", params)
    return _items(res)


async def episodes(season_id: int = None, page: int = 1, per_page: int = 20, **kw) -> List[Dict]:
    params = {"page": page, "per_page": per_page, "sort": "asc", **kw}
    if season_id is not None:
        params["season_id"] = season_id
    res = await oscar_client.get("/api/episodes/", params)
    return _items(res)


async def episode_show(episode_id: int) -> Optional[Dict]:
    res = await oscar_client.get("/api/episodes/show.php", {"id": episode_id})
    if isinstance(res, dict) and res.get("status") == "success":
        return res.get("data") or res
    return res if isinstance(res, dict) else None


async def latest_episodes(page: int = 1, limit: int = 20) -> List[Dict]:
    res = await oscar_client.get("/api/episodes/latest.php", {"page": page, "limit": limit})
    return _items(res)
