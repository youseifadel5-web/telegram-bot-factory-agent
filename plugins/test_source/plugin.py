# -*- coding: utf-8 -*-
"""Hypothetical future plugin — auto-discovered, no core rewrite needed."""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from core.models import MediaItem, MediaSource, MediaType, SearchQuery
from core.plugin_base import MediaSourcePlugin

_CATALOG = [
    MediaItem(
        id="test-1",
        universal_id="test:movie:1",
        title="Test Horror Egypt",
        type=MediaType.MOVIE,
        year=2025,
        countries=["Egypt"],
        genres=["horror"],
        overview="فيلم رعب مصري تجريبي للاختبار.",
        poster="https://via.placeholder.com/300x450.png?text=Horror",
        rating=7.5,
        source_ids=["test_source"],
        sources=[MediaSource(source_id="test_source", external_id="1", url="https://test-streams.mux.dev/x36xhzz/x36xhzz.m3u8")],
    ),
    MediaItem(
        id="test-2",
        universal_id="test:series:2",
        title="Test Turkish Romance",
        type=MediaType.SERIES,
        year=2024,
        countries=["Turkey"],
        genres=["romance", "drama"],
        overview="مسلسل تركي رومانسي تجريبي.",
        poster="https://via.placeholder.com/300x450.png?text=Romance",
        rating=8.0,
        source_ids=["test_source"],
        sources=[MediaSource(source_id="test_source", external_id="2")],
    ),
]


class Plugin(MediaSourcePlugin):
    id = "test_source"
    name = "Test Source"
    version = "1.0.0"

    async def search(self, query: SearchQuery) -> List[MediaItem]:
        q = (query.text or "").lower()
        out = []
        for it in _CATALOG:
            if query.media_type and it.type.value != query.media_type:
                continue
            if q and q not in it.title.lower() and q not in (it.overview or "").lower():
                if not any(g in q for g in it.genres):
                    continue
            out.append(it)
        return out or list(_CATALOG)

    async def get_details(self, item_id: str) -> Optional[MediaItem]:
        eid = (item_id or "").split(":")[-1]
        for it in _CATALOG:
            if it.id == item_id or it.id.endswith(eid) or any(s.external_id == eid for s in it.sources):
                return it
        return None

    async def get_sources(self, item_id: str, media_type: str = "movie") -> List[Dict[str, Any]]:
        it = await self.get_details(item_id)
        if not it:
            return []
        return [{"url": s.url, "quality": s.quality, "source_id": s.source_id} for s in it.sources if s.url]

    async def get_categories(self) -> List[Dict[str, Any]]:
        return [
            {"id": "horror", "name": "رعب", "count": 1},
            {"id": "romance", "name": "رومانسي", "count": 1},
        ]

    async def health_check(self) -> Dict[str, Any]:
        return {"id": self.id, "ok": True, "items": len(_CATALOG)}
