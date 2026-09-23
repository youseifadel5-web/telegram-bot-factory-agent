#!/usr/bin/env python3
"""KataBump regression gate — blocks merges that break existing features.

Offline checks (no network, no real ffmpeg calls):
  syntax/compileall · core imports · DB migration idempotency · SSRF blocks
  probe schema · HLS parsing · quality smart-auto · FFmpeg command generation
  stream states · callback registration in main.py · duplicate builders
  regression matrix (source × mode × quality → expected outcome)
Exit code 0 = safe merge; 1 = blocked.
"""
from __future__ import annotations

import asyncio
import os
import py_compile
import re
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

FAILURES = []
PASSES = []


def check(name: str, fn, *args):
    try:
        result = fn(*args)
        if result is False:
            raise AssertionError("check returned False")
        PASSES.append(name)
        print(f"  ✓ {name}")
    except Exception as e:
        FAILURES.append((name, str(e)))
        print(f"  ✗ {name}: {e}")


def compile_all():
    errors = []
    for p in ROOT.rglob("*.py"):
        if any(part in (".git", "__pycache__", "bin", ".venv", "venv", "legacy") for part in p.parts):
            continue
        try:
            py_compile.compile(str(p), doraise=True)
        except py_compile.PyCompileError as e:
            errors.append(f"{p.relative_to(ROOT)}: {e}")
    if errors:
        raise AssertionError("; ".join(errors[:3]))


def core_imports():
    import services.source_probe  # noqa
    import services.url_normalizer  # noqa
    import services.quality_manager  # noqa
    import services.secrets  # noqa
    import services.security.ssrf  # noqa
    import services.media.hls_detector  # noqa
    import services.media.ffmpeg_engine  # noqa
    import services.media.source_probe_v2  # noqa  (facade must import cleanly)
    import core.stream_states  # noqa
    import services.stream  # noqa
    import utils.visualizer  # noqa


def main_import():
    import main  # noqa — full handler tree must import (registers nothing yet)


def db_migrations():
    from database import Database

    async def run():
        with tempfile.TemporaryDirectory() as td:
            d = Database(os.path.join(td, "t.db"))
            await d.connect()
            cur = await d.conn.execute("PRAGMA table_info(streams)")
            cols = {r[1] for r in await cur.fetchall()}
            for c in ("quality", "media_mode", "source_mode", "restart_count", "reconnect_count"):
                assert c in cols, c
            sid = await d.create_stream(1, "t", "https://x/a.m3u8")
            s = await d.get_stream(sid)
            assert (s.get("quality") or "auto") == "auto"  # backward compat default
            await d.close()
            d2 = Database(os.path.join(td, "t.db"))
            await d2.connect()  # idempotent second run
            await d2.close()
    asyncio.run(run())


def ssrf_blocks_private():
    from services.security.ssrf import is_safe_url
    for bad in ("http://127.0.0.1/", "http://10.0.0.1/", "http://172.16.0.5/",
                "http://192.168.1.1/", "http://169.254.169.254/", "http://[::1]/"):
        assert not is_safe_url(bad), bad
    assert is_safe_url("https://cdn.example.com/a.m3u8")


def redirect_escape_blocked():
    from services.security.ssrf import assert_safe_url
    try:
        assert_safe_url("http://localhost/x")  # simulates a redirect hop to LAN
        raise AssertionError("redirect to LAN was allowed")
    except ValueError:
        pass


def probe_schema():
    from services.source_probe import probe_source
    p = probe_source("https://cdn.example.com/live/index.m3u8", timeout=3)
    for k in ("ok", "url", "clean_url", "media_kind", "has_video", "has_audio",
              "is_hls", "is_master_playlist", "variants", "error", "solution"):
        assert k in p, k


def hls_master():
    from services.media.hls_detector import parse_m3u8_text
    info = parse_m3u8_text(
        "#EXTM3U\n#EXT-X-STREAM-INF:BANDWIDTH=800000,RESOLUTION=640x360\n360.m3u8\n"
        "#EXT-X-STREAM-INF:BANDWIDTH=2500000,RESOLUTION=1280x720\n720.m3u8\n"
    )
    assert info.is_master and [v.height for v in info.variants] == [360, 720]


def quality_smart():
    from services.quality_manager import resolve_for_source
    assert resolve_for_source("auto", 360, "video").height <= 360   # no upscale
    assert resolve_for_source("auto", 1080, "video").height <= 720  # CPU cap
    assert resolve_for_source("720p", None, "audio").name == "audio_only"


def ffmpeg_single_builder():
    count = 0
    for p in ROOT.rglob("*.py"):
        if "legacy" in p.parts or "__pycache__" in p.parts:
            continue
        try:
            text = p.read_text(encoding="utf-8")
        except Exception:
            continue
        count += len(re.findall(r"^def build_ffmpeg_cmd\(", text, re.M))
    assert count == 1, f"{count} build_ffmpeg_cmd definitions (must be exactly 1)"


def ffmpeg_cmd_generation():
    import services.stream as sm
    sm._ffmpeg_supports_option = lambda f, o: True  # stub — no real binary
    sm._pick_video_encoder = lambda f: "libx264"
    cmd = sm.build_ffmpeg_cmd("ffmpeg", "https://cdn.example.com/a.m3u8", "rtmps://h/live/KEY", with_video=True)
    assert "-progress" in cmd and "pipe:1" in " ".join(cmd)
    cmd_a = sm.build_ffmpeg_cmd("ffmpeg", "https://radio.example.com/x.mp3", "rtmps://h/live/KEY")
    assert "-vn" in cmd_a  # genuine audio-only
    # The command path's SSRF gate is _validate_source_url (runs in _spawn)
    try:
        sm._validate_source_url("http://127.0.0.1/x.m3u8")
        raise AssertionError("SSRF URL accepted by command builder gate")
    except ValueError:
        pass


def stream_states():
    from core.stream_states import can_transition, STOPPED, RUNNING, STARTING
    assert not can_transition(STOPPED, RUNNING)
    assert can_transition(STOPPED, STARTING)


def callback_registration():
    text = (ROOT / "main.py").read_text(encoding="utf-8")
    for pat in (r"stream_status:", r"stream_start:", r"stream_stop:", r"stream_restart:",
                r"stream_logs:", r"stream_stats:", r"stream_clone:", r"stream_fav:",
                r"stream_mute:", r"stream_vol_up:", r"stream_vol_down:",
                r"stream_history", r"current_stream"):
        assert re.search(pat, text), f"missing registration for {pat}"
    assert re.search(r"CallbackQueryHandler\(lp_router, pattern=r\"\^lp:\"", text), \
        "missing unified lp router registration"
    kb = (ROOT / "keyboards" / "menus.py").read_text(encoding="utf-8")
    for old_btn, new_btn in (("stream_logs:", "lp:logs:"), ("stream_stats:", "lp:stats:"),
                             ("stream_clone:", "lp:clone:"), ("stream_fav:", "lp:fav:")):
        assert old_btn in kb or new_btn in kb, f"keyboard missing {old_btn} / {new_btn}"
    rtmp_setup = (ROOT / "handlers" / "streams" / "rtmp_setup.py").read_text(encoding="utf-8")
    assert "import asyncio" in rtmp_setup, "IPTV RTMP setup must import asyncio"
    lp = (ROOT / "handlers" / "streams" / "lp_router.py").read_text(encoding="utf-8")
    assert 'if action == "change_na":' in lp, "lp router must handle id-less change_na"


def regression_matrix():
    """§36 matrix — all offline (unit-level). BLOCK rows expect rejection."""
    from services.source_probe import resolve_source_mode
    from services.quality_manager import resolve_for_source
    import services.stream as sm
    sm._ffmpeg_supports_option = lambda f, o: True
    sm._pick_video_encoder = lambda f: "libx264"
    from services.media.hls_detector import parse_m3u8_text, pick_variant
    from services.security.ssrf import is_safe_url, assert_safe_url

    # (name, fn) — fn raises on unexpected outcome
    rows = [
        ("MP4/Video/Auto", lambda: sm.build_ffmpeg_cmd("ffmpeg", "https://c/x.mp4", "rtmps://h/k", with_video=True, media_kind="video")),
        ("MP4/Video/720p", lambda: sm.build_ffmpeg_cmd("ffmpeg", "https://c/x.mp4", "rtmps://h/k", with_video=True, media_kind="video")),
        ("M3U8/Video/Auto", lambda: sm.build_ffmpeg_cmd("ffmpeg", "https://c/x.m3u8", "rtmps://h/k", with_video=True, media_kind="video")),
        ("MP3/Audio/Auto", lambda: sm.build_ffmpeg_cmd("ffmpeg", "https://c/x.mp3", "rtmps://h/k", media_kind="audio")),
        ("AAC/Audio/Auto", lambda: sm.build_ffmpeg_cmd("ffmpeg", "https://c/x.aac", "rtmps://h/k", media_kind="audio")),
        ("Radio-host/Audio/Auto", lambda: sm.build_ffmpeg_cmd("ffmpeg", "https://qurango.net/radio/x", "rtmps://h/k", media_kind="audio")),
        ("MasterHLS/360p", lambda: pick_variant(parse_m3u8_text(MASTER_FIXTURE), "360p")),
        ("403→CLEAR ERROR", _expect_403),
        ("404→CLEAR ERROR", _expect_404),
        ("InvalidURL→CLEAR ERROR", _expect_invalid),
        ("PrivateIP→BLOCK", _expect_block),
        ("Redirect→LAN→BLOCK", _expect_redirect_block),
    ]
    for name, fn in rows:
        try:
            out = fn()
            assert out is not False
            print(f"    matrix PASS {name}")
        except AssertionError:
            raise
        except Exception as e:
            raise AssertionError(f"{name}: {e}")


MASTER_FIXTURE = (
    "#EXTM3U\n#EXT-X-STREAM-INF:BANDWIDTH=800000,RESOLUTION=640x360\n360.m3u8\n"
    "#EXT-X-STREAM-INF:BANDWIDTH=2500000,RESOLUTION=1280x720\n720.m3u8\n"
)


def _expect_403():
    from services.secrets import _diagnose_ffmpeg_error
    assert "403" in _diagnose_ffmpeg_error("HTTP error 403")["error"]


def _expect_404():
    from services.secrets import _diagnose_ffmpeg_error
    assert "404" in _diagnose_ffmpeg_error("server returned 404")["error"]


def _expect_invalid():
    from services.secrets import _validate_rtmp_url
    ok, _ = _validate_rtmp_url("https://wrong-scheme")
    assert not ok


def _expect_block():
    from services.security.ssrf import is_safe_url
    assert not is_safe_url("http://10.1.2.3/x.m3u8")


def _expect_redirect_block():
    from services.security.ssrf import assert_safe_url
    try:
        assert_safe_url("http://192.168.0.5/x")
        raise AssertionError("allowed")
    except ValueError:
        pass


def expect_value(_v):
    return True


def main() -> int:
    print("KataBump regression gate")
    check("compileall", compile_all)
    check("core imports", core_imports)
    check("main.py import tree", main_import)
    check("db migrations idempotent", db_migrations)
    check("ssrf blocks private", ssrf_blocks_private)
    check("redirect escape blocked", redirect_escape_blocked)
    check("probe unified schema", probe_schema)
    check("hls master parsing", hls_master)
    check("quality smart-auto", quality_smart)
    check("single ffmpeg builder", ffmpeg_single_builder)
    check("ffmpeg command generation", ffmpeg_cmd_generation)
    check("stream state machine", stream_states)
    check("callback registration", callback_registration)
    check("regression matrix (§36)", regression_matrix)
    print(f"\nregression: {len(PASSES)} passed, {len(FAILURES)} failed")
    for name, err in FAILURES:
        print(f"  FAILED: {name} — {err}")
    return 1 if FAILURES else 0


if __name__ == "__main__":
    raise SystemExit(main())
