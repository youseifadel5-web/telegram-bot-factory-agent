"""Unified URL normalization layer — the single source of URL truth.

Pipeline position:

    Input URL → SSRF validation → URL normalization → Source Probe

Responsibilities:
- clean / sanitize raw user input
- extract the real media URL from wrapper params (?url= ?src= ?source= ...)
- keep authentication query params (token/signature/expires/...) intact
- plausibility checks that NEVER trust extension or Content-Type alone
"""
from __future__ import annotations

import re
from typing import Optional, Tuple
from urllib.parse import urlparse, parse_qs, quote, unquote, urlunparse

# Characters that break FFmpeg / subprocess when left raw in URLs
_BAD_URL_CHARS = re.compile(r"[\x00-\x1f\x7f]")

# Wrapper query keys that commonly hide the real media URL
WRAPPER_KEYS = ("url", "src", "source", "file", "stream", "video", "play", "u", "m3u8")

# Auth params that MUST survive normalization (signed URLs break without them)
AUTH_PARAM_RE = re.compile(
    r"^(token|key|expires|expire|expiry|signature|sig|auth|authorization|hdnea|hmac|"
    r"st|e|md5|cdn|cloudfront|policy|km|sk|te|ja|wsSecret|wsTime|ov|oh|verify|t)$",
    re.I,
)

_AUDIO_HOSTS = (
    "qurango", "mp3quran", "radiojar", "zeno.fm", "radioca.st", "icecast",
    "shoutcast", "/radio", "radio.", "nogoumfm", "stream.zeno",
)
_AUDIO_EXTS = (".mp3", ".aac", ".m4a", ".ogg", ".oga", ".opus", ".wav", ".flac", ".wma")
_VIDEO_EXTS = (".mp4", ".mkv", ".avi", ".mov", ".webm", ".flv", ".ts", ".m3u8", ".mpd")


def clean_url(url: str) -> str:
    """Strip whitespace, control chars, angle brackets; keep valid URI form."""
    if not url:
        return ""
    u = str(url).strip().strip("<>\"'")
    u = _BAD_URL_CHARS.sub("", u)
    u = re.sub(r"\s+", "", u)
    u = re.sub(r"^(https?://)+", lambda m: "https://" if "https" in m.group(0) else "http://", u, flags=re.I)
    return u


def sanitize_url_for_ffmpeg(url: str) -> str:
    """Return a URL safe for FFmpeg -i argument (no invalid characters)."""
    u = clean_url(url)
    if not u:
        return u
    try:
        parsed = urlparse(u)
        path = quote(unquote(parsed.path), safe="/:@!$&'()*+,;=-._~")
        query = quote(unquote(parsed.query), safe="=&%:@!$&'()*+,;=-._~")
        return urlunparse((parsed.scheme, parsed.netloc, path, parsed.params, query, ""))
    except Exception:
        return u


def extract_wrapped_url(url: str) -> str:
    """If the real media URL hides inside ?url= / ?src= / ... return it.

    Preserves the original URL when the wrapper param is absent or empty,
    and never strips auth params from the extracted media URL.
    """
    u = clean_url(url)
    if not u.lower().startswith(("http://", "https://")):
        return u
    try:
        parsed = urlparse(u)
        qs = parse_qs(parsed.query, keep_blank_values=True)
    except Exception:
        return u
    for key in WRAPPER_KEYS:
        vals = qs.get(key)
        if not vals:
            continue
        candidate = clean_url(vals[0])
        if candidate.lower().startswith(("http://", "https://", "rtmp://", "rtmps://")):
            return candidate
    return u


def normalize_url(url: str) -> Tuple[str, str]:
    """Return (clean_url, sanitized_for_ffmpeg) after wrapper extraction."""
    u = extract_wrapped_url(url)
    return u, sanitize_url_for_ffmpeg(u)


def has_auth_params(url: str) -> bool:
    try:
        qs = parse_qs(urlparse(url).query)
    except Exception:
        return False
    return any(AUTH_PARAM_RE.match(k) for k in qs.keys())


def is_plausible_media_url(url: str) -> bool:
    """Cheap structural check BEFORE any network I/O.

    Accepts http(s)/rtmp(s) and local data paths. Extension alone is never
    decisive — misleading extensions (.css?...m3u8) still pass here; the
    content sniff + ffprobe decide the final truth.
    """
    u = clean_url(url)
    if not u:
        return False
    low = u.lower()
    if low.startswith(("http://", "https://", "rtmp://", "rtmps://")):
        try:
            parsed = urlparse(low)
        except Exception:
            return False
        return bool(parsed.netloc)
    if low.startswith(("file:", "/")):
        return True
    return False


def looks_like_audio_url(url: str) -> bool:
    """Heuristic audio hint only — real detection is probe's job."""
    low = (url or "").lower()
    path = low.split("?", 1)[0]
    if any(path.endswith(e) for e in _AUDIO_EXTS):
        return True
    if any(h in low for h in _AUDIO_HOSTS):
        return True
    return False


def looks_like_video_url(url: str) -> bool:
    low = (url or "").lower()
    path = low.split("?", 1)[0]
    return any(path.endswith(e) for e in _VIDEO_EXTS) or "/live/" in low
