# -*- coding: utf-8 -*-
"""Parse natural language → structured AIIntent. Falls back without OpenRouter."""
from __future__ import annotations

import json
import re
from typing import Optional

from ai.openrouter import OpenRouterClient
from ai.schemas import AIIntent
from core.cache import ai_cache

SYSTEM = """You are a media intent parser for an Arabic Telegram movie bot.
Return ONLY valid JSON with keys:
type (movie|series|live|any), genres (list), countries (list),
year_min, year_max, sort (relevance|newest|rating|popular),
query_text, similar_to, needs_clarification (bool), clarification_question, explanation.
Map Egyptian Arabic: عايز/عاوز=want, رعب=horror, اكشن=action, تركي=Turkey, مصري=Egypt, جديد=newest.
Never invent movie titles. Never include code. JSON only."""


def _heuristic(text: str) -> AIIntent:
    t = (text or "").lower()
    intent = AIIntent(query_text=text)
    if any(w in t for w in ("مسلسل", "series", "show")):
        intent.type = "series"
    elif any(w in t for w in ("فيلم", "movie", "film")):
        intent.type = "movie"
    elif any(w in t for w in ("قناة", "channel", "live")):
        intent.type = "live"
    genre_map = {
        "رعب": "horror", "horror": "horror",
        "اكشن": "action", "أكشن": "action", "action": "action",
        "كوميدي": "comedy", "comedy": "comedy",
        "دراما": "drama", "drama": "drama",
        "رومانسي": "romance", "romance": "romance",
        "خيال": "scifi", "sci-fi": "scifi", "scifi": "scifi",
        "كرتون": "animation", "انيميشن": "animation", "anime": "animation",
    }
    for k, v in genre_map.items():
        if k in t and v not in intent.genres:
            intent.genres.append(v)
    country_map = {
        "مصري": "Egypt", "مصر": "Egypt", "egyptian": "Egypt",
        "تركي": "Turkey", "تركيا": "Turkey", "turkish": "Turkey",
        "امريكي": "USA", "أمريكي": "USA", "american": "USA",
        "هندي": "India", "indian": "India",
        "كوري": "Korea", "korean": "Korea",
        "ياباني": "Japan", "japanese": "Japan",
    }
    for k, v in country_map.items():
        if k in t and v not in intent.countries:
            intent.countries.append(v)
    if any(w in t for w in ("جديد", "حديث", "new", "latest")):
        intent.sort = "newest"
        intent.year_min = 2020
    if any(w in t for w in ("تقييم", "rating", "أفضل")):
        intent.sort = "rating"
    m = re.search(r"(?:شبه|like|similar to)\s+(.+)", t, re.I)
    if m:
        intent.similar_to = m.group(1).strip()[:80]
    if not intent.genres and not intent.countries and intent.type == "any" and len(t) < 8:
        intent.needs_clarification = True
        intent.clarification_question = "تحب يكون 🎬 فيلم ولا 📺 مسلسل؟"
    return intent


class IntentParser:
    def __init__(self, client: Optional[OpenRouterClient] = None):
        self.client = client or OpenRouterClient()

    async def parse(self, text: str, previous: Optional[AIIntent] = None) -> AIIntent:
        key = f"intent:{(text or '').strip().lower()}"
        cached = ai_cache.get(key)
        if cached:
            self.client.stats["cache_hits"] += 1
            intent = AIIntent.from_dict(cached)
        else:
            intent = await self._parse_ai(text) if self.client.enabled else _heuristic(text)
            ai_cache.set(key, {
                "type": intent.type, "genres": intent.genres, "countries": intent.countries,
                "year_min": intent.year_min, "year_max": intent.year_max, "sort": intent.sort,
                "query_text": intent.query_text, "similar_to": intent.similar_to,
                "needs_clarification": intent.needs_clarification,
                "clarification_question": intent.clarification_question,
                "explanation": intent.explanation,
            })

        # conversational refinement: merge with previous session
        if previous:
            if intent.type == "any" and previous.type != "any":
                intent.type = previous.type
            if not intent.genres and previous.genres:
                intent.genres = list(previous.genres)
            else:
                intent.genres = list(dict.fromkeys(previous.genres + intent.genres))
            if not intent.countries and previous.countries:
                intent.countries = list(previous.countries)
            else:
                intent.countries = list(dict.fromkeys(previous.countries + intent.countries))
            if intent.year_min is None and previous.year_min:
                intent.year_min = previous.year_min
            if intent.sort == "relevance" and previous.sort != "relevance":
                intent.sort = previous.sort
        return intent

    async def _parse_ai(self, text: str) -> AIIntent:
        raw = await self.client.chat([
            {"role": "system", "content": SYSTEM},
            {"role": "user", "content": text[:500]},
        ])
        if not raw:
            return _heuristic(text)
        raw = raw.strip()
        if raw.startswith("```"):
            raw = re.sub(r"^```(?:json)?\s*", "", raw)
            raw = re.sub(r"\s*```$", "", raw)
        try:
            data = json.loads(raw)
            intent = AIIntent.from_dict(data)
            if not intent.query_text:
                intent.query_text = text
            return intent
        except Exception:
            return _heuristic(text)
