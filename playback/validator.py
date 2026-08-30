# -*- coding: utf-8 -*-
"""Validate real media sources — inspect response, not extension."""
from __future__ import annotations

import logging
import re
from typing import List, Optional, Tuple
from urllib.parse import urljoin

import httpx

from core.cache import playback_cache
from core.models import PlaybackStatus, QualityOption

log = logging.getLogger("playback")
HTTP_TIMEOUT = 8.0


async def _fetch_head_or_range(url: str) -> Tuple[int, str, bytes]:
    headers = {
        "User-Agent": "Mozilla/5.0 UnifiedMediaBot/3.0",
        "Range": "bytes=0-4095",
    }
    async with httpx.AsyncClient(timeout=httpx.Timeout(HTTP_TIMEOUT), follow_redirects=True) as client:
        try:
            r = await client.get(url, headers=headers)
            ctype = (r.headers.get("content-type") or "").lower()
            return r.status_code, ctype, r.content[:8000]
        except Exception as e:
            log.debug("fetch failed: %s", type(e).__name__)
            return 0, "", b""


def _detect_format(ctype: str, body: bytes, url: str) -> str:
    text = ""
    try:
        text = body.decode("utf-8", errors="ignore")
    except Exception:
        text = ""
    if "#EXTM3U" in text:
        return "hls"
    if b"ftyp" in body[:64] or "video/mp4" in ctype or url.lower().endswith(".mp4"):
        return "mp4"
    if "application/dash+xml" in ctype or "<MPD" in text or url.lower().endswith(".mpd"):
        return "dash"
    if "mpegurl" in ctype or url.lower().endswith(".m3u8"):
        return "hls"
    if "video/" in ctype or "application/octet-stream" in ctype:
        return "stream"
    return "unknown"


def parse_hls_qualities(playlist: str, base_url: str) -> List[QualityOption]:
    lines = playlist.splitlines()
    out: List[QualityOption] = []
    i = 0
    while i < len(lines):
        line = lines[i].strip()
        if line.startswith("#EXT-X-STREAM-INF:"):
            bw = 0
            res = ""
            m = re.search(r"BANDWIDTH=(\d+)", line)
            if m:
                bw = int(m.group(1))
            m = re.search(r"RESOLUTION=(\d+)x(\d+)", line)
            if m:
                res = f"{m.group(2)}p"
            if i + 1 < len(lines):
                uri = lines[i + 1].strip()
                if uri and not uri.startswith("#"):
                    full = urljoin(base_url, uri)
                    label = res or (f"{bw // 1000}k" if bw else "auto")
                    out.append(QualityOption(label=label, url=full, bandwidth=bw or None))
        i += 1
    # sort high → low
    def sort_key(q: QualityOption):
        m = re.search(r"(\d+)", q.label)
        return -int(m.group(1)) if m else 0

    out.sort(key=sort_key)
    # dedupe labels
    seen = set()
    uniq = []
    for q in out:
        if q.label in seen:
            continue
        seen.add(q.label)
        uniq.append(q)
    return uniq


async def validate_source(url: str) -> Tuple[PlaybackStatus, str, List[QualityOption]]:
    """Returns (status, format, qualities)."""
    if not url or not url.startswith(("http://", "https://")):
        return PlaybackStatus.INVALID, "unknown", []
    cache_key = f"pb:{url[:200]}"
    cached = playback_cache.get(cache_key)
    if cached:
        return cached

    status_code, ctype, body = await _fetch_head_or_range(url)
    if status_code == 0:
        result = (PlaybackStatus.TIMEOUT, "unknown", [])
        playback_cache.set(cache_key, result, ttl=60)
        return result
    if status_code in (401, 403):
        result = (PlaybackStatus.REQUIRES_AUTH, "unknown", [])
        playback_cache.set(cache_key, result)
        return result
    if status_code >= 400:
        result = (PlaybackStatus.UNAVAILABLE, "unknown", [])
        playback_cache.set(cache_key, result)
        return result

    fmt = _detect_format(ctype, body, url)
    qualities: List[QualityOption] = []
    if fmt == "hls":
        text = body.decode("utf-8", errors="ignore")
        if "#EXTM3U" not in text:
            result = (PlaybackStatus.INVALID, "hls", [])
            playback_cache.set(cache_key, result)
            return result
        qualities = parse_hls_qualities(text, url)
        if not qualities:
            qualities = [QualityOption(label="auto", url=url)]
        result = (PlaybackStatus.PLAYABLE, "hls", qualities)
    elif fmt in ("mp4", "stream", "dash"):
        label = "1080p" if "1080" in url else ("720p" if "720" in url else "default")
        qualities = [QualityOption(label=label, url=url)]
        result = (PlaybackStatus.PLAYABLE, fmt, qualities)
    else:
        # may still play — partial
        qualities = [QualityOption(label="default", url=url)]
        result = (PlaybackStatus.PARTIALLY_PLAYABLE, fmt, qualities)

    playback_cache.set(cache_key, result)
    return result
