"""Tests for real media detection (no blind 'video' fallback)."""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from services.source_probe import detect_media_kind, resolve_source_mode
from services.url_normalizer import looks_like_audio_url, looks_like_video_url


def test_probe_audio_only_is_audio():
    probe = {"has_video": False, "has_audio": True}
    assert detect_media_kind("https://x.com/anything", probe) == "audio"
    assert resolve_source_mode("auto", probe, "https://x.com/anything") == "audio"


def test_probe_video_with_audio_is_video():
    probe = {"has_video": True, "has_audio": True}
    assert resolve_source_mode("auto", probe, "https://x.com/a.m3u8") == "video"


def test_unknown_falls_to_url_heuristics_not_blind_video():
    # radio host in URL → audio even without probe data
    assert resolve_source_mode("auto", {}, "https://qurango.net/radio/x") == "audio"
    assert resolve_source_mode("auto", None, "https://radio.example.com/stream") == "audio"


def test_explicit_mode_wins():
    probe = {"has_video": False, "has_audio": True}
    assert resolve_source_mode("video", probe, "https://x.com/r.mp3") == "video"
    probe2 = {"has_video": True, "has_audio": True}
    assert resolve_source_mode("audio", probe2, "https://x.com/a.m3u8") == "audio"


def test_quran_and_radio_hosts_detected():
    for u in (
        "https://mp3quran.net/api/x.m3u8",
        "https://qurango.net/radio/tarateel",
        "https://zeno.fm/radio/x",
        "https://server.com/radio/8000/stream",
    ):
        assert detect_media_kind(u) == "audio", u


def test_extension_audio_detection():
    for u in ("https://x.com/a.mp3", "https://x.com/a.aac", "https://x.com/a.m4a", "https://x.com/a.ogg"):
        assert detect_media_kind(u) == "audio", u


def test_helpers_consistency():
    assert looks_like_audio_url("https://x.com/a.mp3")
    assert looks_like_video_url("https://x.com/a.mp4")
    assert looks_like_video_url("https://x.com/live/index.m3u8")


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            print("OK", name)
    print("all media_detection tests passed")
