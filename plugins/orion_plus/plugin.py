# -*- coding: utf-8 -*-
"""Orion Plus plugin adapter."""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from core.models import MediaItem, MediaSource, MediaType, SearchQuery
from core.plugin_base import MediaSourcePlugin

log = logging.getLogger("plugin.orion")


class Plugin(MediaSourcePlugin):
    id = "orion"
    name = "Orion Plus"
    version = "3.0.0"

    def __init__(self):
        self._vault = None

    def bind_vault(self, vault_api) -> None:
        self._vault = vault_api

    async def search(self, query: SearchQuery) -> List[MediaItem]:
        if not self._vault:
            return []
        out: List[MediaItem] = []
        q = query.text or ""
        try:
            if query.media_type in (None, "movie", "any"):
                items, _ = self._vault.list_content("movies", page=1, limit=15, search=q)
                for it in items or []:
                    iid = str(it.get("id") or "")
                    title = str(it.get("titleAr") or it.get("titleEn") or it.get("title") or "")
                    out.append(MediaItem(
                        id=f"orion:{iid}",
                        universal_id=f"orion:movie:{iid}",
                        title=title,
                        type=MediaType.MOVIE,
                        poster=str(it.get("poster") or it.get("image") or ""),
                        overview=str(it.get("overview") or it.get("description") or ""),
                        rating=float(it.get("rating") or 0) or 0.0,
                        source_ids=["orion"],
                        sources=[MediaSource(source_id="orion", external_id=iid)],
                    ))
            if query.media_type in (None, "series", "any"):
                items, _ = self._vault.list_content("series", page=1, limit=15, search=q)
                for it in items or []:
                    iid = str(it.get("id") or "")
                    title = str(it.get("titleAr") or it.get("titleEn") or it.get("title") or "")
                    out.append(MediaItem(
                        id=f"orion:{iid}",
                        universal_id=f"orion:series:{iid}",
                        title=title,
                        type=MediaType.SERIES,
                        poster=str(it.get("poster") or it.get("image") or ""),
                        overview=str(it.get("overview") or ""),
                        rating=float(it.get("rating") or 0) or 0.0,
                        source_ids=["orion"],
                        sources=[MediaSource(source_id="orion", external_id=iid)],
                        extra={"kind": "s"},
                    ))
        except Exception:
            log.exception("orion search failed")
        return out

    async def get_details(self, item_id: str) -> Optional[MediaItem]:
        return None

    async def get_sources(self, item_id: str, media_type: str = "movie") -> List[Dict[str, Any]]:
        return []

    async def get_categories(self) -> List[Dict[str, Any]]:
        return []

    async def health_check(self) -> Dict[str, Any]:
        return {"id": self.id, "ok": self._vault is not None, "bound": self._vault is not None}
