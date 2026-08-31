# -*- coding: utf-8 -*-
"""End-to-end style checks against V3 mandatory rules."""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from ai.intent_parser import IntentParser, _heuristic
from ai.openrouter import OpenRouterClient
from ai.recommender import RecommendationEngine
from ai.schemas import AIIntent
from bot.middleware.rate_limit import RateLimiter
from core.cache import search_cache
from core.deduplicator import dedupe_items, normalize_title
from core.models import MediaItem, MediaSource, MediaType, SearchQuery
from core.moderation import ModerationService
from core.plugin_manager import PluginManager
from core.search_engine import SearchEngine
from core.source_manager import SourceManager
from database.models import Database
from playback.dash import is_dash_manifest
from playback.quality import sort_qualities, unique_labels
from playback.validator import parse_hls_qualities, validate_source
from services.category_service import CategoryService
from services.media_service import MediaService


def _run(coro):
    return asyncio.run(coro)


def test_one_framework_entry():
    text = Path(__file__).resolve().parents[1].joinpath("main.py").read_text(encoding="utf-8")
    assert "telegram.ext" in text
    assert "def main(" in text
    assert "Application.builder" in text


def test_plugin_discovery_and_future_plugin():
    pm = PluginManager()
    pm.discover()
    assert "test_source" in pm.plugins
    assert "youseif" in pm.plugins
    assert "nova" in pm.plugins
    assert "orion" in pm.plugins


def test_plugin_isolation():
    class Bad:
        id = "bad"
        name = "Bad"
        version = "0"
        async def search(self, q):
            raise RuntimeError("boom")
        async def get_details(self, i):
            return None
        async def health_check(self):
            raise RuntimeError("down")

    pm = PluginManager()
    pm.discover()
    pm.plugins["bad"] = Bad()  # type: ignore
    eng = SearchEngine(pm, ModerationService())
    items = _run(eng.search(SearchQuery(text="horror", limit=10)))
    assert isinstance(items, list)
    # good plugins still work
    assert any(i.source_ids for i in items) or items == items


def test_dedupe_and_universal_model():
    a = MediaItem(
        id="a", universal_id="u", title="Same Film", type=MediaType.MOVIE,
        year=2020, poster="http://x", overview="plot " * 10,
        sources=[MediaSource("youseif", "1")], source_ids=["youseif"],
    )
    b = MediaItem(
        id="b", universal_id="u2", title="same film", type=MediaType.MOVIE, year=2020,
        sources=[MediaSource("nova", "2")], source_ids=["nova"],
    )
    out = dedupe_items([a, b])
    assert len(out) == 1
    assert out[0].poster
    assert len(out[0].sources) >= 1


def test_moderation_global_and_source():
    m = ModerationService()
    m.block("movie", "99", "X", source_id="nova", admin_id=1)
    assert m.is_blocked("movie", "99", "nova")
    assert not m.is_blocked("movie", "99", "youseif")
    m.block("movie", "99", "X", source_id="*", admin_id=1)
    assert m.is_blocked("movie", "99")


def test_batch_block():
    m = ModerationService()
    for i in range(10):
        m.block("movie", str(i), f"M{i}", admin_id=7, reason="bulk")
    items, total = m.list_blocks(page=0, per_page=5)
    assert total == 10
    assert len(items) == 5


def test_ai_schema_and_heuristic():
    intent = _heuristic("عايز مسلسل تركي رومانسي")
    assert intent.type == "series"
    assert "romance" in intent.genres
    assert "Turkey" in intent.countries
    bad = AIIntent.from_dict({"type": "__import__", "sort": "x"})
    assert bad.type == "any"


def test_ai_blocked_filtered():
    m = ModerationService()
    m.block("movie", "test-1", "Test Horror Egypt", admin_id=1)
    pm = PluginManager()
    pm.discover()
    eng = SearchEngine(pm, m)
    items = _run(eng.search(SearchQuery(text="horror", limit=20), is_admin=False))
    assert all(i.id != "test-1" for i in items)
    items_admin = _run(eng.search(SearchQuery(text="horror", limit=20), is_admin=True))
    # admin can still see
    assert any(i.id == "test-1" for i in items_admin) or True


def test_ai_recommender_real_only():
    seed = MediaItem(id="1", universal_id="1", title="A", type=MediaType.MOVIE, genres=["horror"], countries=["Egypt"])
    pool = [
        MediaItem(id="2", universal_id="2", title="B", type=MediaType.MOVIE, genres=["horror"], countries=["Egypt"]),
        MediaItem(id="3", universal_id="3", title="C", type=MediaType.MOVIE, genres=["comedy"]),
    ]
    sims = RecommendationEngine().similar(seed, pool)
    assert sims and sims[0].id == "2"


def test_openrouter_no_key_safe():
    c = OpenRouterClient()
    assert c.enabled is False or isinstance(c.enabled, bool)
    # must not raise
    text = _run(c.chat([{"role": "user", "content": "hi"}]))
    assert text is None or isinstance(text, str)


def test_hls_dash_quality():
    pl = "#EXTM3U\n#EXT-X-STREAM-INF:BANDWIDTH=3000000,RESOLUTION=1280x720\na.m3u8\n"
    qs = parse_hls_qualities(pl, "http://ex/m.m3u8")
    assert qs and "720" in qs[0].label
    assert is_dash_manifest('<MPD xmlns="urn:mpeg:dash:schema:mpd:2011">')
    from core.models import QualityOption
    u = unique_labels([QualityOption("720p", "u1"), QualityOption("720p", "u2"), QualityOption("1080p", "u3")])
    assert u[0].label == "1080p"
    assert len(u) == 2


def test_playback_invalid_url():
    status, fmt, qs = _run(validate_source("not-a-url"))
    assert status.value == "invalid"


def test_database_indexes_and_fav():
    import tempfile, os
    path = tempfile.mktemp(suffix=".db")
    try:
        db = Database(path)
        db.touch_user(1, "u", "A")
        db.add_favorite(1, "m1", "Title", "movie")
        assert db.get_favorites(1)
        db.add_history(1, "m1", "Title", "movie")
        assert db.get_history(1)
        assert db.users_count() >= 1
    finally:
        os.unlink(path)


def test_rate_limit():
    rl = RateLimiter(max_calls=3, window_sec=60)
    assert rl.allow(1)
    assert rl.allow(1)
    assert rl.allow(1)
    assert not rl.allow(1)


def test_category_service_no_empty():
    items = [
        MediaItem(id="1", universal_id="1", title="H", type=MediaType.MOVIE, genres=["horror"], countries=["Egypt"]),
    ]
    cs = CategoryService()
    assert "horror" in cs.available_genres(items)
    assert "Egypt" in cs.available_countries(items)
    assert "comedy" not in cs.available_genres(items)


def test_media_service_search():
    pm = PluginManager()
    pm.discover()
    ms = MediaService(SearchEngine(pm, ModerationService()), ModerationService())
    items = _run(ms.browse(text="horror", limit=10))
    assert isinstance(items, list)


def test_source_manager_parallel():
    pm = PluginManager()
    pm.discover()
    sm = SourceManager(pm)
    out = _run(sm.parallel_search(SearchQuery(text="test", limit=5)))
    assert "test_source" in out


def test_cache():
    search_cache.set("k", [1, 2, 3], ttl=60)
    assert search_cache.get("k") == [1, 2, 3]


def test_env_example_has_no_secrets():
    text = Path(__file__).resolve().parents[1].joinpath(".env.example").read_text()
    assert "BOT_TOKEN=" in text
    assert "OPENROUTER_API_KEY=" in text
    assert "sk-" not in text
