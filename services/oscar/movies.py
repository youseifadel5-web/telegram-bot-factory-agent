"""Oscar movies endpoints."""
from __future__ import annotations
from typing import Any, Dict, List, Optional
from services.oscar.client import oscar_client


def _items(data: Any) -> list:
    if isinstance(data, list):
        return data
    if isinstance(data, dict):
        if data.get("status") == "success" or "data" in data:
            d = data.get("data")
            if isinstance(d, list):
                return d
            if isinstance(d, dict):
                return [d]
        return data.get("results") or data.get("items") or []
    return []


async def movies(page: int = 1, limit: int = 20, search: str = None, sort_by: str = "most_viewed", **kw) -> List[Dict]:
    params = {"page": page, "limit": limit, "sort_by": sort_by, "app_version": 15, **kw}
    if search:
        params["search"] = search
    res = await oscar_client.get("/api/movies/", params)
    return _items(res)


async def movie(movie_id: int) -> Optional[Dict]:
    res = await oscar_client.get("/api/movies/show.php", {"id": movie_id})
    if isinstance(res, dict) and res.get("status") == "success":
        return res.get("data") or res
    return res if isinstance(res, dict) else None


async def movie_filters() -> Any:
    return await oscar_client.get("/api/movies/filters.php", cache_ttl=6 * 3600)


async def movie_collections() -> Any:
    return await oscar_client.get("/api/movies/collections.php", cache_ttl=3600)


async def movie_collection(collection_id: int) -> Any:
    return await oscar_client.get("/api/movies/collection.php", {"id": collection_id})


async def movie_collection_categories() -> Any:
    return await oscar_client.get("/api/movies/collection_categories.php", cache_ttl=6 * 3600)


async def movie_request_categories() -> Any:
    return await oscar_client.get("/api/movies/request_categories.php", cache_ttl=6 * 3600)
