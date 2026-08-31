# -*- coding: utf-8 -*-
"""Strict AI intent schema — validated, never executed as code."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


ALLOWED_TYPES = {"movie", "series", "live", "any"}
ALLOWED_SORT = {"relevance", "newest", "rating", "popular"}
ALLOWED_GENRES = {
    "horror", "action", "drama", "comedy", "romance", "scifi", "animation",
    "thriller", "documentary", "sport", "kids", "crime", "fantasy",
    "رعب", "اكشن", "دراما", "كوميدي", "رومانسي", "خيال علمي", "انيميشن",
}


@dataclass
class AIIntent:
    type: str = "any"
    genres: List[str] = field(default_factory=list)
    countries: List[str] = field(default_factory=list)
    year_min: Optional[int] = None
    year_max: Optional[int] = None
    sort: str = "relevance"
    query_text: str = ""
    similar_to: str = ""
    needs_clarification: bool = False
    clarification_question: str = ""
    explanation: str = ""

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "AIIntent":
        if not isinstance(data, dict):
            return cls()
        typ = str(data.get("type") or "any").lower()
        if typ not in ALLOWED_TYPES:
            typ = "any"
        genres = [str(g) for g in (data.get("genres") or []) if str(g)][:8]
        countries = [str(c) for c in (data.get("countries") or []) if str(c)][:8]
        sort = str(data.get("sort") or "relevance")
        if sort not in ALLOWED_SORT:
            sort = "relevance"
        year_min = data.get("year_min")
        year_max = data.get("year_max")
        try:
            year_min = int(year_min) if year_min is not None else None
        except Exception:
            year_min = None
        try:
            year_max = int(year_max) if year_max is not None else None
        except Exception:
            year_max = None
        return cls(
            type=typ,
            genres=genres,
            countries=countries,
            year_min=year_min,
            year_max=year_max,
            sort=sort,
            query_text=str(data.get("query_text") or "")[:200],
            similar_to=str(data.get("similar_to") or "")[:120],
            needs_clarification=bool(data.get("needs_clarification")),
            clarification_question=str(data.get("clarification_question") or "")[:200],
            explanation=str(data.get("explanation") or "")[:300],
        )
