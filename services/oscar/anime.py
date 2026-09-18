"""Oscar anime endpoints."""
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
        return data.get("results") or data.get("items") or []
    return []


async def anime_home() -> Any:
    return await oscar_client.get("/api/anime/home.php", cache_ttl=300)


async def anime_list(page: int = 1, limit: int = 20, search: str = None, anime_type: str = None, **kw) -> List[Dict]:
    params = {"page": page, "limit": limit, **kw}
    if search:
        params["search"] = search
    if anime_type:
        params["anime_type"] = anime_type
    res = await oscar_client.get("/api/anime/", params)
    return _items(res)


async def anime_show(anime_id: int) -> Optional[Dict]:
    res = await oscar_client.get("/api/anime/show.php", {"id": anime_id})
    if isinstance(res, dict) and res.get("status") == "success":
        return res.get("data") or res
    return res if isinstance(res, dict) else None


async def anime_episodes(anime_id: int, page: int = 1, per_page: int = 20, season_id: int = None) -> List[Dict]:
    params = {"anime_id": anime_id, "page": page, "per_page": per_page}
    if season_id:
        params["season_id"] = season_id
    res = await oscar_client.get("/api/anime/episodes/", params)
    return _items(res)


async def anime_episode(episode_id: int) -> Optional[Dict]:
    res = await oscar_client.get("/api/anime/episodes/show.php", {"id": episode_id})
    if isinstance(res, dict) and res.get("status") == "success":
        return res.get("data") or res
    return res if isinstance(res, dict) else None


async def anime_latest_episodes(page: int = 1, limit: int = 20) -> List[Dict]:
    res = await oscar_client.get("/api/anime/episodes/latest.php", {"page": page, "limit": limit})
    return _items(res)


async def anime_filters() -> Any:
    return await oscar_client.get("/api/anime/filters.php", cache_ttl=6 * 3600)


async def anime_genres() -> Any:
    return await oscar_client.get("/api/anime/genres/", cache_ttl=6 * 3600)


async def anime_studios() -> Any:
    return await oscar_client.get("/api/anime/studios/", cache_ttl=6 * 3600)


async def anime_schedule() -> Any:
    return await oscar_client.get("/api/anime/schedule.php", cache_ttl=300)
