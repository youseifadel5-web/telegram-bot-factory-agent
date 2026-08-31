# -*- coding: utf-8 -*-
from __future__ import annotations

from typing import List, Optional

from core.models import MediaItem, SearchQuery
from core.moderation import ModerationService
from core.ranking import rank_items
from core.search_engine import SearchEngine
from services.category_service import CategoryService


class MediaService:
    def __init__(self, search: SearchEngine, moderation: ModerationService):
        self.search = search
        self.moderation = moderation
        self.categories = CategoryService()

    async def browse(
        self,
        text: str = "",
        media_type: Optional[str] = None,
        genre: Optional[str] = None,
        country: Optional[str] = None,
        sort: str = "relevance",
        is_admin: bool = False,
        limit: int = 40,
    ) -> List[MediaItem]:
        genres = [genre] if genre else []
        countries = [country] if country else []
        q = SearchQuery(
            text=text or genre or country or media_type or "",
            media_type=media_type,
            genres=genres,
            countries=countries,
            sort=sort,
            limit=limit * 2,
        )
        items = await self.search.search(q, is_admin=is_admin)
        if genre:
            items = self.categories.filter_genre(items, genre) or items
        if country:
            items = self.categories.filter_country(items, country) or items
        items = self.moderation.filter_items(items, is_admin=is_admin)
        return rank_items(items)[:limit]
