# -*- coding: utf-8 -*-
"""Cinema Nova plugin adapter."""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from core.models import MediaItem, MediaSource, MediaType, SearchQuery
from core.plugin_base import MediaSourcePlugin

log = logging.getLogger("plugin.nova")


class Plugin(MediaSourcePlugin):
    id = "nova"
    name = "Cinema Nova"
    version = "3.0.0"

    def __init__(self):
        self._api = None

    def bind_api(self, api) -> None:
        self._api = api

    async def search(self, query: SearchQuery) -> List[MediaItem]:
        if not self._api:
            return []
        out: List[MediaItem] = []
        q = query.text or ""
        try:
            if query.media_type in (None, "movie", "any"):
                resp = self._api.search_movies(query=q, page=1, limit=15)
                items = (resp or {}).get("data") or [] if (resp or {}).get("status") == "success" else []
                for it in items:
                    iid = str(it.get("id") or "")
                    out.append(MediaItem(
                        id=f"nova:{iid}",
                        universal_id=f"nova:movie:{iid}",
                        title=str(it.get("title_ar") or it.get("title_en") or it.get("title") or ""),
                        original_title=str(it.get("title_en") or ""),
                        type=MediaType.MOVIE,
                        year=int(it["year"]) if str(it.get("year") or "").isdigit() else None,
                        poster=str(it.get("poster") or it.get("image") or ""),
                        overview=str(it.get("overview") or it.get("story") or ""),
                        rating=float(it.get("rating") or 0) or 0.0,
                        source_ids=["nova"],
                        sources=[MediaSource(source_id="nova", external_id=iid)],
                    ))
            if query.media_type in (None, "series", "any"):
                resp = self._api.search_series(query=q, page=1, limit=15)
                items = (resp or {}).get("data") or [] if (resp or {}).get("status") == "success" else []
                for it in items:
                    iid = str(it.get("id") or "")
                    out.append(MediaItem(
                        id=f"nova:{iid}",
                        universal_id=f"nova:series:{iid}",
                        title=str(it.get("title_ar") or it.get("title_en") or it.get("title") or ""),
                        type=MediaType.SERIES,
                        year=int(it["year"]) if str(it.get("year") or "").isdigit() else None,
                        poster=str(it.get("poster") or it.get("image") or ""),
                        overview=str(it.get("overview") or ""),
                        rating=float(it.get("rating") or 0) or 0.0,
                        source_ids=["nova"],
                        sources=[MediaSource(source_id="nova", external_id=iid)],
                    ))
        except Exception:
            log.exception("nova search failed")
        return out

    async def get_details(self, item_id: str) -> Optional[MediaItem]:
        return None

    async def get_sources(self, item_id: str, media_type: str = "movie") -> List[Dict[str, Any]]:
        return []

    async def get_categories(self) -> List[Dict[str, Any]]:
        return []

    async def health_check(self) -> Dict[str, Any]:
        return {"id": self.id, "ok": self._api is not None, "bound": self._api is not None}
