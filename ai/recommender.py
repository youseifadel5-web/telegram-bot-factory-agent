# -*- coding: utf-8 -*-
"""Deterministic recommendation engine — independent of OpenRouter."""
from __future__ import annotations

from typing import List, Optional

from core.models import MediaItem
from core.ranking import rank_items


class RecommendationEngine:
    def similar(self, seed: MediaItem, pool: List[MediaItem], limit: int = 6) -> List[MediaItem]:
        gset = {g.lower() for g in (seed.genres or [])}
        cset = {c.lower() for c in (seed.countries or [])}
        scored = []
        for it in pool:
            if it.id == seed.id or it.universal_id == seed.universal_id:
                continue
            score = 0
            if gset & {x.lower() for x in (it.genres or [])}:
                score += 40
            if cset & {x.lower() for x in (it.countries or [])}:
                score += 25
            if seed.type == it.type:
                score += 15
            if seed.year and it.year and abs(seed.year - it.year) <= 5:
                score += 10
            if it.poster:
                score += 5
            if score > 0:
                scored.append((score, it))
        scored.sort(key=lambda x: -x[0])
        return [x[1] for x in scored[:limit]]

    def from_intent_pool(self, items: List[MediaItem], limit: int = 12) -> List[MediaItem]:
        return rank_items(items)[:limit]
