"""Enhanced media URL probe: redirects, content-type, HLS, FFprobe summary."""
from __future__ import annotations

import logging
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)


async def probe_media_url(
    url: str,
    headers: Optional[Dict[str, str]] = None,
    quality: str = "best",
) -> Dict[str, Any]:
    """
    Full diagnostic probe for a stream URL.
    Returns structured result for /diagnose and preflight.
    """
    from services.security.ssrf import is_safe_url
    from services.media.hls_detector import detect_hls, pick_variant
    from services.source_probe import (
        clean_url,
        sanitize_url_for_ffmpeg,
        probe_source,
        format_probe_panel,
    )

    result: Dict[str, Any] = {
        "ok": False,
        "url": url,
        "final_url": url,
        "type": "unknown",
        "http_status": None,
        "content_type": "",
        "hls": None,
        "variant": None,
        "ffprobe": None,
        "error": None,
        "stage": "init",
        "panel": "",
    }

    try:
        url = clean_url(url)
        result["url"] = url
        if not is_safe_url(url):
            result["error"] = "URL blocked (SSRF)"
            result["stage"] = "ssrf"
            return result

        result["stage"] = "hls_detect"
        hls = await detect_hls(url, headers=headers)
        result["final_url"] = hls.final_url or url
        result["content_type"] = hls.content_type or ""
        result["hls"] = {
            "is_hls": hls.is_hls,
            "is_master": hls.is_master,
            "is_media": hls.is_media,
            "variants": len(hls.variants),
            "segment_count": hls.segment_count,
            "first_segment": hls.first_segment[:120] if hls.first_segment else "",
            "error": hls.error,
        }
        if hls.error and not hls.is_hls:
            result["error"] = hls.error
            # continue to ffprobe soft path

        stream_url = result["final_url"]
        if hls.is_hls:
            result["type"] = "hls"
            if hls.is_master and hls.variants:
                variant = pick_variant(hls, quality)
                if variant:
                    result["variant"] = {
                        "uri": variant.uri,
                        "bandwidth": variant.bandwidth,
                        "resolution": variant.resolution,
                        "codecs": variant.codecs,
                    }
                    stream_url = variant.uri
            elif hls.first_segment:
                # media playlist — use playlist itself for FFmpeg
                stream_url = result["final_url"]
        elif "mp4" in (hls.content_type or "") or ".mp4" in url.lower():
            result["type"] = "mp4"
        elif "mpeg" in (hls.content_type or "") or ".mp3" in url.lower():
            result["type"] = "audio"
        else:
            result["type"] = hls.raw_type or "http"

        result["stage"] = "ffprobe"
        stream_url = sanitize_url_for_ffmpeg(stream_url)
        probe = probe_source(stream_url, headers=headers)
        result["ffprobe"] = {
            "ok": probe.get("ok"),
            "has_video": probe.get("has_video"),
            "has_audio": probe.get("has_audio"),
            "media_kind": probe.get("media_kind"),
            "format": probe.get("format"),
            "codec": probe.get("codec"),
            "quality": probe.get("quality"),
            "duration": probe.get("duration"),
            "error": probe.get("error"),
            "solution": probe.get("solution"),
        }
        result["ok"] = bool(probe.get("ok") or hls.is_hls)
        result["panel"] = format_probe_panel(probe, stream_url)
        if not result["ok"]:
            result["error"] = probe.get("error") or hls.error or "probe failed"
            result["stage"] = "ffprobe_fail" if probe.get("error") else result["stage"]
        else:
            result["stage"] = "done"
            result["error"] = None
    except Exception as e:
        logger.exception("probe_media_url: %s", e)
        result["error"] = f"{type(e).__name__}: {e}"
        result["stage"] = "exception"
    return result
