# -*- coding: utf-8 -*-
from __future__ import annotations

from typing import List

from core.models import MediaItem


def rank_items(items: List[MediaItem], prefer_poster: bool = True) -> List[MediaItem]:
    def score(it: MediaItem) -> int:
        s = 0
        if prefer_poster and it.poster:
            s += 50
        if it.overview:
            s += 30
        s += int(min(it.rating or 0, 10) * 3)
        s += len(it.sources) * 5
        if it.year and it.year >= 2020:
            s += 5
        return s

    return sorted(items, key=lambda x: (-score(x), x.title or ""))
