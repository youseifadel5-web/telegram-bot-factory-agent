"""Tests for secret masking / sanitization (services/secrets.py)."""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from services.secrets import (
    mask_secret, sanitize_url, sanitize_headers, sanitize_command,
    _safe_error_text, _diagnose_ffmpeg_error, _validate_rtmp_url,
)


def test_mask_secret():
    assert mask_secret("supersecretkey") != "supersecretkey"
    assert "supersecretkey" not in mask_secret("supersecretkey")
    assert mask_secret("") == ""


def test_sanitize_url_hides_token():
    u = sanitize_url("https://cdn.com/a.m3u8?token=SECRET123&x=1")
    assert "SECRET123" not in u
    assert "x=1" in u


def test_sanitize_headers_hides_auth():
    h = sanitize_headers({"User-Agent": "UA", "Authorization": "Bearer xyz", "Cookie": "a=b"})
    assert h["Authorization"] == "***"
    assert h["Cookie"] == "***"
    assert h["User-Agent"] == "UA"


def test_sanitize_command_hides_rtmp_key():
    cmd = "ffmpeg -i src -f flv rtmps://dc4-1.rtmp.t.me/s/SECRETKEY123"
    out = sanitize_command(cmd)
    assert "SECRETKEY123" not in out
    assert "rtmps://dc4-1.rtmp.t.me/s/" in out


def test_safe_error_text_masks_bot_token():
    text = _safe_error_text("bad request for token 123456789:AAABCDEFGHIJKLMNOPQRSTUVWXYZaa")
    assert "AAABCDEFGHIJKLMNOPQRSTUVWXYZ" not in text


def test_safe_error_text_masks_local_paths():
    assert "/home/user" not in _safe_error_text("error at /home/user/secret/file")


def test_diagnose_ffmpeg_error_categories():
    cases = {
        "Server returned 404 Not Found": "404",
        "HTTP 403 Forbidden": "403",
        "Connection timed out": "مهلة",
        "RTMP_Connect0 auth failed": "مصادقة",
        "Invalid data found": "M3U8",
    }
    for raw, marker in cases.items():
        diag = _diagnose_ffmpeg_error(raw)
        assert marker in diag["error"], (raw, diag)
        assert diag["solution"]


def test_validate_rtmp_url():
    ok, _ = _validate_rtmp_url("rtmps://dc4-1.rtmp.t.me/s/KEY")
    assert ok
    ok2, msg = _validate_rtmp_url("https://not-rtmp")
    assert not ok2 and msg
    ok3, _2 = _validate_rtmp_url("")
    assert not ok3


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            print("OK", name)
    print("all headers/secrets tests passed")
