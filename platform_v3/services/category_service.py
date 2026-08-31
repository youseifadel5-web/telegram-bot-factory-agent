# -*- coding: utf-8 -*-
"""Dynamic categories/countries from real content — never show empty buckets."""
from __future__ import annotations

from collections import Counter
from typing import Dict, List, Set

from core.models import MediaItem

# canonical genre keys used in UI
GENRE_ALIASES = {
    "horror": {"horror", "رعب"},
    "action": {"action", "اكشن", "أكشن"},
    "drama": {"drama", "دراما"},
    "comedy": {"comedy", "كوميدي", "كوميديا"},
    "romance": {"romance", "رومانسي", "romance"},
    "scifi": {"scifi", "sci-fi", "خيال علمي", "science fiction"},
    "animation": {"animation", "anime", "أنيميشن", "انيميشن", "كرتون"},
}

COUNTRY_ALIASES = {
    "Egypt": {"egypt", "مصر", "مصري", "egyptian"},
    "USA": {"usa", "us", "america", "أمريكا", "امريكي", "american"},
    "UK": {"uk", "britain", "british", "بريطانيا"},
    "Turkey": {"turkey", "turkish", "تركيا", "تركي"},
    "India": {"india", "indian", "الهند", "هندي"},
    "Korea": {"korea", "korean", "كوريا", "كوري"},
    "Japan": {"japan", "japanese", "اليابان", "ياباني"},
    "China": {"china", "chinese", "الصين"},
    "France": {"france", "french", "فرنسا"},
}


class CategoryService:
    def available_genres(self, items: List[MediaItem]) -> List[str]:
        found: Set[str] = set()
        for it in items:
            gset = {g.lower() for g in (it.genres or [])}
            for key, aliases in GENRE_ALIASES.items():
                if gset & aliases:
                    found.add(key)
        return sorted(found)

    def available_countries(self, items: List[MediaItem]) -> List[str]:
        found: Set[str] = set()
        for it in items:
            cset = {c.lower() for c in (it.countries or [])}
            for key, aliases in COUNTRY_ALIASES.items():
                if cset & aliases:
                    found.add(key)
            # free-form
            for c in it.countries or []:
                if c and c not in found:
                    found.add(c)
        return sorted(found)

    def counts_by_genre(self, items: List[MediaItem]) -> Dict[str, int]:
        c: Counter = Counter()
        for it in items:
            gset = {g.lower() for g in (it.genres or [])}
            for key, aliases in GENRE_ALIASES.items():
                if gset & aliases:
                    c[key] += 1
        return dict(c)

    def filter_genre(self, items: List[MediaItem], genre: str) -> List[MediaItem]:
        aliases = GENRE_ALIASES.get(genre, {genre.lower()})
        return [it for it in items if {g.lower() for g in (it.genres or [])} & aliases]

    def filter_country(self, items: List[MediaItem], country: str) -> List[MediaItem]:
        aliases = COUNTRY_ALIASES.get(country, {country.lower()})
        return [it for it in items if {c.lower() for c in (it.countries or [])} & aliases]
