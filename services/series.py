"""واجهة المسلسلات — تمرير رقيق لطبقة المصادر الجديدة (حكاية/GoLive).

نفس فكرة services/movies.py: نفس أسماء الدوال القديمة حتى لا تتغير الشاشات،
لكن الطلبات تمر عبر `services.app_sources` (بصمة Chrome ثم aiohttp).
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from services.app_sources import golive

logger = logging.getLogger(__name__)

BASE_URL = golive.BASE_URL

# ذاكرة مؤقتة بسيطة: season_id → قائمة الحلقات (تُملأ عند جلب المواسم)
_SEASON_EPISODES: Dict[str, List[Dict]] = {}
_EPISODE_LINKS: Dict[str, List[Dict]] = {}


async def search_series(q: str, limit: int = 20) -> List[Dict]:
    rows = await golive.series(search=q, limit=limit)
    out = []
    for r in rows or []:
        item = dict(r)
        item.setdefault("kind", "series")
        item["source"] = item.get("source") or "golive"
        out.append(item)
    return out


async def get_seasons(series_id: Any) -> List[Dict]:
    """يرجّع المواسم، ويخزّن حلقات كل موسم داخليًا لـ get_episodes."""
    detail = await golive.series_detail(series_id)
    if not detail:
        return []
    seasons_out: List[Dict] = []
    for season in detail.get("seasons") or []:
        sid = str(season.get("season") or season.get("id") or "")
        episodes = []
        for ep in season.get("episodes") or []:
            e = dict(ep)
            eid = str(e.get("id") or "")
            if eid:
                _EPISODE_LINKS[eid] = list(e.get("sources") or [])
            episodes.append(e)
        _SEASON_EPISODES[sid] = episodes
        seasons_out.append({
            "id": sid,
            "name": season.get("title") or f"الموسم {sid}",
            "episode_count": len(episodes),
        })
    return seasons_out


async def get_episodes(season_id: Any) -> List[Dict]:
    return list(_SEASON_EPISODES.get(str(season_id), []))


def _links_for(episode_id: Any) -> List[Dict]:
    return list(_EPISODE_LINKS.get(str(episode_id), []))


async def get_watch_links(episode_id: Any) -> List[Dict]:
    return _links_for(episode_id)


async def get_download_links(episode_id: Any) -> List[Dict]:
    return _links_for(episode_id)
