# -*- coding: utf-8 -*-
"""Universal plugin interface — plugins provide data, core owns UI."""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional

from core.models import MediaItem, SearchQuery, SeriesDetails


class MediaSourcePlugin(ABC):
    id: str = "base"
    name: str = "Base"
    version: str = "1.0.0"

    @abstractmethod
    async def search(self, query: SearchQuery) -> List[MediaItem]:
        ...

    @abstractmethod
    async def get_details(self, item_id: str) -> Optional[MediaItem]:
        ...

    async def get_series_details(self, item_id: str) -> Optional[SeriesDetails]:
        return None

    async def get_sources(self, item_id: str, media_type: str = "movie") -> List[Dict[str, Any]]:
        return []

    async def get_categories(self) -> List[Dict[str, Any]]:
        return []

    async def health_check(self) -> Dict[str, Any]:
        return {"id": self.id, "ok": True, "latency_ms": 0}

    async def close(self) -> None:
        pass
