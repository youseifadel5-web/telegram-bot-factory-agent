"""Backward-compatible facade over the canonical media probe."""
from __future__ import annotations
from typing import Any, Dict, Optional

async def probe_media_url(url: str, headers: Optional[Dict[str, str]] = None, quality: str = "best") -> Dict[str, Any]:
    from services.source_probe import probe_source_async, format_probe_panel
    probe = await probe_source_async(url, headers=headers, quality=quality)
    playback_url = probe.get("playback_url") or probe.get("cleaned_url") or url
    hls = probe.get("hls") if isinstance(probe.get("hls"), dict) else None
    return {
        "ok": bool(probe.get("ok")), "url": probe.get("original_url") or url,
        "final_url": probe.get("cleaned_url") or url, "playback_url": playback_url,
        "type": str(probe.get("source_type") or "unknown"),
        "http_status": None, "content_type": (hls or {}).get("content_type", ""),
        "hls": hls, "variant": (hls or {}).get("selected_variant"),
        "ffprobe": probe, "error": probe.get("error"),
        "stage": "done" if probe.get("ok") else "probe_failed",
        "media_state": probe.get("media_state") or "UNKNOWN",
        "media_kind": probe.get("media_kind") or "unknown",
        "panel": format_probe_panel(probe, playback_url),
    }
