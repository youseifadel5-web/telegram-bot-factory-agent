# -*- coding: utf-8 -*-
"""Unified search across plugins — parallel, moderated, deduped."""
from __future__ import annotations

import asyncio
import logging
from typing import List, Optional

from core.cache import search_cache
from core.deduplicator import dedupe_items, normalize_title
from core.models import MediaItem, SearchQuery
from core.moderation import ModerationService
from core.plugin_manager import PluginManager

log = logging.getLogger("search")

PLUGIN_TIMEOUT = 12.0


class SearchEngine:
    def __init__(self, plugins: PluginManager, moderation: ModerationService):
        self.plugins = plugins
        self.moderation = moderation

    async def search(
        self,
        query: SearchQuery,
        is_admin: bool = False,
        plugin_ids: Optional[List[str]] = None,
    ) -> List[MediaItem]:
        cache_key = f"s:{normalize_title(query.text)}:{query.media_type}:{query.year_min}:{','.join(query.genres)}:{','.join(query.countries)}"
        cached = search_cache.get(cache_key)
        if cached is not None and not is_admin:
            return self.moderation.filter_items(list(cached), is_admin=is_admin)

        targets = self.plugins.all()
        if plugin_ids:
            targets = [p for p in targets if p.id in plugin_ids]

        async def _one(plugin):
            try:
                return await asyncio.wait_for(plugin.search(query), timeout=PLUGIN_TIMEOUT)
            except asyncio.TimeoutError:
                log.warning("Plugin timeout: %s", plugin.id)
                return []
            except Exception:
                log.exception("Plugin search failed: %s", plugin.id)
                return []

        results = await asyncio.gather(*[_one(p) for p in targets], return_exceptions=False)
        merged: List[MediaItem] = []
        for batch in results:
            if batch:
                merged.extend(batch)

        # client-side filters
        if query.media_type:
            merged = [m for m in merged if (m.type.value if hasattr(m.type, "value") else m.type) == query.media_type]
        if query.genres:
            gset = {g.lower() for g in query.genres}
            merged = [m for m in merged if gset & {x.lower() for x in (m.genres or [])}]
        if query.countries:
            cset = {c.lower() for c in query.countries}
            merged = [m for m in merged if cset & {x.lower() for x in (m.countries or [])}]
        if query.year_min:
            merged = [m for m in merged if m.year and m.year >= query.year_min]
        if query.year_max:
            merged = [m for m in merged if m.year and m.year <= query.year_max]

        merged = dedupe_items(merged)
        if query.sort == "newest":
            merged.sort(key=lambda x: -(x.year or 0))
        elif query.sort == "rating":
            merged.sort(key=lambda x: -(x.rating or 0))

        merged = self.moderation.filter_items(merged, is_admin=is_admin)
        search_cache.set(cache_key, merged)
        return merged[: query.limit]
