"""Oscar sports / matches endpoints."""
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


async def matches(page: int = 1, limit: int = 30, **kw) -> List[Dict]:
    res = await oscar_client.get("/api/matches/", {"page": page, "limit": limit, **kw}, cache_ttl=45)
    return _items(res)


async def match_show(match_id: int) -> Optional[Dict]:
    res = await oscar_client.get("/api/matches/show.php", {"id": match_id}, cache_ttl=30)
    if isinstance(res, dict) and res.get("status") == "success":
        return res.get("data") or res
    return res if isinstance(res, dict) else None


async def matches_tv() -> Any:
    return await oscar_client.get("/api/matches/tv.php", cache_ttl=30)


async def leagues() -> Any:
    return await oscar_client.get("/api/matches/leagues.php", cache_ttl=3600)


async def teams(**kw) -> Any:
    return await oscar_client.get("/api/matches/teams.php", kw or None, cache_ttl=3600)


async def standings(**kw) -> Any:
    return await oscar_client.get("/api/matches/standings.php", kw or None, cache_ttl=300)


async def top_scorers(**kw) -> Any:
    return await oscar_client.get("/api/matches/top_scorers.php", kw or None, cache_ttl=300)


async def tournament_matches(**kw) -> Any:
    return await oscar_client.get("/api/matches/tournament_matches.php", kw or None, cache_ttl=60)


async def tournaments() -> Any:
    return await oscar_client.get("/api/matches/tournaments.php", cache_ttl=3600)
