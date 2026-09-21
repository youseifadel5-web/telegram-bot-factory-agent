"""Tests for the unified URL normalization layer (services/url_normalizer.py)."""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from services.url_normalizer import (
    clean_url, sanitize_url_for_ffmpeg, extract_wrapped_url, normalize_url,
    has_auth_params, is_plausible_media_url, looks_like_audio_url,
)


def test_clean_url_strips_junk():
    assert clean_url("  https://a.b/x.m3u8  ") == "https://a.b/x.m3u8"
    assert clean_url("https://a.b/x") == "https://a.b/x"  # double scheme fix
    assert "\n" not in clean_url("https://a.b/x\ny")


def test_wrapped_param_extraction():
    assert extract_wrapped_url("https://page.com/play?url=https://cdn.com/v.m3u8") == "https://cdn.com/v.m3u8"
    assert extract_wrapped_url("https://page.com/?src=https://cdn.com/a.mp4") == "https://cdn.com/a.mp4"
    assert extract_wrapped_url("https://page.com/?video=https://cdn.com/a.ts").endswith(".ts")
    # no wrapper → unchanged
    assert extract_wrapped_url("https://cdn.com/direct.m3u8") == "https://cdn.com/direct.m3u8"


def test_auth_params_survive():
    signed = "https://cdn.com/live.m3u8?token=abc&expires=999&hdnea=x"
    assert has_auth_params(signed) is True
    clean, safe = normalize_url(signed)
    assert "token=abc" in safe and "expires=999" in safe and "hdnea=x" in safe


def test_plain_url_has_no_auth():
    assert has_auth_params("https://cdn.com/a.m3u8") is False


def test_plausible_media_url():
    assert is_plausible_media_url("https://a.b/x.m3u8")
    assert is_plausible_media_url("rtmp://server/live/key")
    assert is_plausible_media_url("/data/file.mp4")
    assert not is_plausible_media_url("")
    assert not is_plausible_media_url("not a url")


def test_misleading_extension_is_structurally_plausible():
    # .css?...m3u8 passes the structural check — content sniff decides later
    assert is_plausible_media_url("https://a.b/style.css?q=/live/x.m3u8")


def test_audio_heuristics():
    assert looks_like_audio_url("https://qurango.net/radio/tarateel")
    assert looks_like_audio_url("https://x.com/radio.mp3")
    assert not looks_like_audio_url("https://x.com/video.mp4")


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            print("OK", name)
    print("all url_normalization tests passed")
