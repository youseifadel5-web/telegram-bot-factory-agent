"""Unit tests for SSRF protection."""
import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from services.security.ssrf import is_safe_url, assert_safe_url


def test_blocks_localhost():
    assert is_safe_url("http://127.0.0.1/admin") is False
    assert is_safe_url("http://localhost:8080/") is False
    assert is_safe_url("http://[::1]/") is False


def test_blocks_metadata():
    assert is_safe_url("http://metadata.google.internal/") is False
    assert is_safe_url("http://169.254.169.254/latest/meta-data/") is False


def test_blocks_private_ips():
    assert is_safe_url("http://10.0.0.1/") is False
    assert is_safe_url("http://192.168.1.1/") is False
    assert is_safe_url("http://172.16.0.5/") is False


def test_allows_public_http():
    assert is_safe_url("https://example.com/stream.m3u8") is True
    assert is_safe_url("http://cdn.example.org/live/index.m3u8") is True


def test_blocks_bad_schemes():
    assert is_safe_url("file:///etc/passwd") is False
    assert is_safe_url("ftp://files.example.com/a") is False
    assert is_safe_url("javascript:alert(1)") is False


def test_assert_raises():
    try:
        assert_safe_url("http://127.0.0.1/")
        raise AssertionError("expected ValueError")
    except ValueError:
        pass


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            print("OK", name)
    print("all ssrf tests passed")
