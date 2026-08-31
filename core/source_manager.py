# -*- coding: utf-8 -*-
"""Source manager — orchestrates plugins with isolation."""
from __future__ import annotations

import asyncio
import logging
from typing import Any, Dict, List, Optional

from core.models import MediaItem, SearchQuery
from core.plugin_manager import PluginManager

log = logging.getLogger("source-manager")
DEFAULT_TIMEOUT = 12.0


class SourceManager:
    def __init__(self, plugins: PluginManager, timeout: float = DEFAULT_TIMEOUT):
        self.plugins = plugins
        self.timeout = timeout

    async def parallel_search(self, query: SearchQuery, plugin_ids: Optional[List[str]] = None) -> Dict[str, List[MediaItem]]:
        targets = self.plugins.all()
        if plugin_ids:
            targets = [p for p in targets if p.id in plugin_ids]
        out: Dict[str, List[MediaItem]] = {}

        async def one(p):
            try:
                items = await asyncio.wait_for(p.search(query), timeout=self.timeout)
                return p.id, items or []
            except Exception as e:
                log.warning("source %s failed: %s", p.id, type(e).__name__)
                return p.id, []

        pairs = await asyncio.gather(*[one(p) for p in targets])
        for pid, items in pairs:
            out[pid] = items
        return out

    async def health(self) -> Dict[str, Any]:
        return await self.plugins.health_all()
