"""Oscar live channels endpoints."""
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


async def channels(page: int = 1, limit: int = 50, **kw) -> List[Dict]:
    params = {"page": page, "limit": limit, **kw}
    res = await oscar_client.get("/api/channels/", params, cache_ttl=120)
    return _items(res)


async def channel_show(channel_id: int) -> Optional[Dict]:
    res = await oscar_client.get("/api/channels/show.php", {"id": channel_id}, cache_ttl=60)
    if isinstance(res, dict) and res.get("status") == "success":
        return res.get("data") or res
    return res if isinstance(res, dict) else None


async def channel_collections() -> Any:
    return await oscar_client.get("/api/channels/collections.php", cache_ttl=600)
