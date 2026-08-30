# -*- coding: utf-8 -*-
"""Youseif Films as a MediaSourcePlugin (data only — no Telegram)."""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from core.models import MediaItem, MediaSource, MediaType, SearchQuery
from core.plugin_base import MediaSourcePlugin

log = logging.getLogger("plugin.youseif")


class Plugin(MediaSourcePlugin):
    id = "youseif"
    name = "Youseif Films"
    version = "3.0.0"

    def __init__(self):
        self._store = None
        self._ready = False

    def bind_store(self, store) -> None:
        """Optional: bind existing youseif_core Store at runtime."""
        self._store = store
        self._ready = store is not None

    async def search(self, query: SearchQuery) -> List[MediaItem]:
        if not self._store:
            return []
        try:
            raw = await self._store.search(query.text or "")
        except Exception:
            log.exception("youseif search failed")
            return []
        out: List[MediaItem] = []
        for typ, it in raw or []:
            if query.media_type and typ != query.media_type:
                continue
            id_key = "series_id" if typ == "series" else "stream_id"
            iid = str(it.get(id_key) or it.get("id") or "")
            title = str(it.get("name") or it.get("title") or "")
            poster = str(it.get("stream_icon") or it.get("cover") or "")
            mt = MediaType.SERIES if typ == "series" else (MediaType.LIVE if typ == "live" else MediaType.MOVIE)
            out.append(MediaItem(
                id=f"youseif:{iid}",
                universal_id=f"youseif:{typ}:{iid}",
                title=title,
                type=mt,
                poster=poster,
                overview=str(it.get("plot") or ""),
                rating=float(it.get("rating") or it.get("rating_5based") or 0) or 0.0,
                source_ids=["youseif"],
                sources=[MediaSource(source_id="youseif", external_id=iid, extra={"raw": True})],
                extra={"raw_type": typ},
            ))
        return out

    async def get_details(self, item_id: str) -> Optional[MediaItem]:
        # item_id like youseif:123
        return None

    async def get_sources(self, item_id: str, media_type: str = "movie") -> List[Dict[str, Any]]:
        return []

    async def get_categories(self) -> List[Dict[str, Any]]:
        return []

    async def health_check(self) -> Dict[str, Any]:
        return {"id": self.id, "ok": self._ready, "bound": self._ready}
