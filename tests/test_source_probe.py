"""Tests for the unified source probe (schema + misleading extensions + errors)."""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from services.source_probe import probe_source, resolve_source_mode, format_probe_panel
from services.secrets import _diagnose_ffmpeg_error as _diagnose_error_keys

UNIFIED_KEYS = (
    "ok", "url", "clean_url", "media_kind", "has_video", "has_audio",
    "is_hls", "is_master_playlist", "variants", "content_type", "error", "solution",
)


def _offline_probe(url: str):
    """probe_source without network: sniff fails fast, ffmpeg missing → unprobed.
    Works both with and without ffmpeg installed on the test machine."""
    return probe_source(url, timeout=2)


def test_unified_schema_present():
    p = _offline_probe("https://cdn.example.com/live/index.m3u8")
    for k in UNIFIED_KEYS:
        assert k in p, f"missing key {k}"
    assert p["is_hls"] is True or ".m3u8" in p["cleaned_url"]


def test_invalid_url_clear_error():
    p = _offline_probe("")
    assert p["ok"] is False or p["error"] or p["note"]


def test_private_ip_blocked_by_probe():
    p = _offline_probe("http://127.0.0.1:8080/stream.m3u8")
    assert p["ok"] is False
    assert "أمنية" in (p["error"] or "") or "SSRF" in (p["error"] or "")


def test_private_lan_blocked():
    p = _offline_probe("http://192.168.1.10/live.m3u8")
    assert p["ok"] is False


def test_metadata_endpoint_blocked():
    p = _offline_probe("http://169.254.169.254/latest/meta-data")
    assert p["ok"] is False


def test_error_solution_pair_on_404_shape():
    # _diagnose_error_keys maps ffmpeg stderr categories → {error, solution}
    diag = _diagnose_error_keys("server returned 404 Not Found")
    assert "404" in diag["error"]
    assert diag["solution"]


def test_403_diagnosis():
    diag = _diagnose_error_keys("HTTP error 403 Forbidden")
    assert "403" in diag["error"]
    assert "Referer" in diag["solution"] or "Headers" in diag["solution"] or "منتهي" in diag["solution"]


def test_signed_url_cleaned_but_auth_kept():
    p = _offline_probe("https://cdn.example.com/a.m3u8?token=abc123&expires=999")
    # token/expires must survive normalization (needed for playback)
    assert "token=abc123" in p["cleaned_url"]


def test_radio_host_is_audio_without_probe():
    p = _offline_probe("https://qurango.net/radio/tarateel")
    assert resolve_source_mode("auto", p, "https://qurango.net/radio/tarateel") == "audio"


def test_probe_panel_never_crashes():
    p = _offline_probe("https://cdn.example.com/x.m3u8")
    text = format_probe_panel(p, "https://cdn.example.com/x.m3u8")
    assert "فحص المصدر" in text


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            print("OK", name)
    print("all source_probe tests passed")
