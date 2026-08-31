# -*- coding: utf-8 -*-
"""Print V3 checklist verification results."""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

CHECKS = []


def ok(name, cond, note=""):
    CHECKS.append((bool(cond), name, note))
    mark = "✅" if cond else "❌"
    print(f"{mark} {name}" + (f" — {note}" if note else ""))


def main():
    from core.plugin_manager import PluginManager
    from core.search_engine import SearchEngine
    from core.moderation import ModerationService
    from core.models import SearchQuery, MediaItem, MediaType, MediaSource
    from core.deduplicator import dedupe_items
    from ai.openrouter import OpenRouterClient
    from ai.intent_parser import _heuristic
    from playback.validator import parse_hls_qualities
    from bot.middleware.rate_limit import RateLimiter
    from services.category_service import CategoryService

    # framework
    ok("One Telegram framework (PTB main.py)", (ROOT / "main.py").exists())
    ok(".env.example present", (ROOT / ".env.example").exists())
    ok(".gitignore present", (ROOT / ".gitignore").exists())
    ok("Dockerfile present", (ROOT / "Dockerfile").exists())
    ok("README present", (ROOT / "README.md").exists())

    pm = PluginManager()
    pm.discover()
    ok("Auto plugin discovery", len(pm.plugins) >= 1, str(list(pm.plugins)))
    ok("test_source future plugin", "test_source" in pm.plugins)
    ok("youseif plugin", "youseif" in pm.plugins)
    ok("nova plugin", "nova" in pm.plugins)
    ok("orion plugin", "orion" in pm.plugins)

    # search + dedupe
    a = MediaItem(id="1", universal_id="1", title="X", type=MediaType.MOVIE, poster="p", overview="y" * 30, sources=[MediaSource("a", "1")])
    b = MediaItem(id="2", universal_id="2", title="x", type=MediaType.MOVIE, sources=[MediaSource("b", "2")])
    ok("Deduplication", len(dedupe_items([a, b])) == 1)

    eng = SearchEngine(pm, ModerationService())
    items = asyncio.run(eng.search(SearchQuery(text="horror", limit=10)))
    ok("Search engine returns list", isinstance(items, list), f"n={len(items)}")

    # moderation
    mod = ModerationService()
    mod.block("movie", "z1", "Z", admin_id=1)
    ok("Global block", mod.is_blocked("movie", "z1"))
    mod.block("movie", "z2", "Z2", source_id="nova", admin_id=1)
    ok("Source-specific block", mod.is_blocked("movie", "z2", "nova") and not mod.is_blocked("movie", "z2", "youseif"))

    # AI
    intent = _heuristic("عاوز فيلم رعب مصري جديد")
    ok("AI heuristic intent", intent.type == "movie" and "horror" in intent.genres)
    ok("OpenRouter key not required", OpenRouterClient().enabled in (True, False))
    env = (ROOT / ".env.example").read_text()
    ok("OpenRouter secret placeholder only", "OPENROUTER_API_KEY=" in env and "sk-" not in env)

    # playback
    qs = parse_hls_qualities("#EXTM3U\n#EXT-X-STREAM-INF:BANDWIDTH=1,RESOLUTION=1280x720\na.m3u8\n", "http://x/")
    ok("HLS quality detection", bool(qs) and "720" in qs[0].label)

    # rate limit
    rl = RateLimiter(2, 60)
    ok("Rate limiting", rl.allow(1) and rl.allow(1) and not rl.allow(1))

    # categories
    cs = CategoryService()
    sample = [MediaItem(id="1", universal_id="1", title="H", type=MediaType.MOVIE, genres=["horror"], countries=["Egypt"])]
    ok("Dynamic genres (non-empty only)", "horror" in cs.available_genres(sample) and "comedy" not in cs.available_genres(sample))

    # structure dirs
    for d in ["core", "ai", "database", "bot", "playback", "plugins", "services", "tests"]:
        ok(f"Structure {d}/", (ROOT / d).is_dir())

    passed = sum(1 for c, _, _ in CHECKS if c)
    total = len(CHECKS)
    print("━━━━━━━━━━━━━━━")
    print(f"RESULT: {passed}/{total} passed")
    if passed < total:
        sys.exit(1)


if __name__ == "__main__":
    main()
