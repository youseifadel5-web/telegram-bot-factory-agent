"""Oscar taxonomy / general metadata endpoints."""
from __future__ import annotations
from typing import Any, Optional
from services.oscar.client import oscar_client


async def content_categories() -> Any:
    return await oscar_client.get("/api/content-categories.php", cache_ttl=6 * 3600)


async def genres() -> Any:
    return await oscar_client.get("/api/genres/", cache_ttl=6 * 3600)


async def countries() -> Any:
    return await oscar_client.get("/api/countries/", cache_ttl=24 * 3600)


async def actors(page: int = 1, limit: int = 50, search: str = None) -> Any:
    params = {"page": page, "limit": limit}
    if search:
        params["search"] = search
    return await oscar_client.get("/api/actors/", params, cache_ttl=3600)


async def actor_show(actor_id: int) -> Any:
    return await oscar_client.get("/api/actors/show.php", {"id": actor_id}, cache_ttl=3600)


async def channel_domains() -> Any:
    return await oscar_client.get("/api/app/channel-domains.php", cache_ttl=3600)


async def check_update() -> Any:
    return await oscar_client.get("/api/app/check-update.php", cache_ttl=300)


async def watch_links(**params) -> Any:
    return await oscar_client.get("/api/watch_links/", params or None)


async def download_links(**params) -> Any:
    return await oscar_client.get("/api/download_links/", params or None)
