"""Optional media helpers layered over the project's canonical source probe."""
from services.source_probe import probe_source
from services.media.source_probe_v2 import probe_media_url
from services.media.hls_detector import HLSInfo, detect_hls, parse_m3u8_text, pick_variant

async def probe_source_async(url, headers=None, quality="best"):
    """Async-compatible facade; the canonical probe is synchronous in this build."""
    import asyncio
    return await asyncio.to_thread(probe_source, url, headers=headers)

__all__ = [
    "probe_source", "probe_source_async", "probe_media_url",
    "HLSInfo", "detect_hls", "parse_m3u8_text", "pick_variant",
]
