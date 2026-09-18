"""FFmpeg engine facade — wraps existing stream_manager without removing it.

Handlers may import from here; services.stream.stream_manager remains the
implementation so old imports keep working.
"""
from __future__ import annotations

import logging
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)


class FFmpegEngine:
    def __init__(self):
        from services.stream import stream_manager
        self._sm = stream_manager

    def has_ffmpeg(self) -> bool:
        return bool(self._sm.has_ffmpeg())

    def probe(self, url: str, headers: Optional[dict] = None) -> Dict[str, Any]:
        from services.source_probe import probe_source, sanitize_url_for_ffmpeg
        url = sanitize_url_for_ffmpeg(url)
        return probe_source(url, headers=headers)

    async def probe_async(self, url: str, headers: Optional[dict] = None, quality: str = "best") -> Dict[str, Any]:
        from services.media.source_probe_v2 import probe_media_url
        return await probe_media_url(url, headers=headers, quality=quality)

    def start_stream(
        self,
        stream_id: int,
        source_url: str,
        rtmp_url: str,
        *,
        with_video: bool = True,
        start_offset: float = 0.0,
        extra_headers: Optional[dict] = None,
        audio_bitrate: str = "128k",
        volume: float = 1.0,
    ) -> Optional[int]:
        return self._sm.start_stream(
            stream_id,
            source_url,
            rtmp_url,
            audio_bitrate=audio_bitrate,
            volume=volume,
            with_video=with_video,
            start_offset=start_offset,
            extra_headers=extra_headers,
        )

    def stop_stream(self, stream_id: int) -> bool:
        try:
            self._sm.stop_stream(stream_id)
            return True
        except Exception as e:
            logger.warning("stop_stream: %s", e)
            return False

    def restart_stream(self, stream_id: int) -> Optional[int]:
        return self._sm.restart_stream(stream_id)

    def is_running(self, stream_id: int) -> bool:
        return bool(self._sm.is_running(stream_id))

    def is_healthy(self, stream_id: int) -> bool:
        try:
            return bool(self._sm.is_healthy(stream_id))
        except Exception:
            return self.is_running(stream_id)

    def get_meta(self, stream_id: int) -> dict:
        try:
            return self._sm.get_meta(stream_id) or {}
        except Exception:
            return {}


ffmpeg_engine = FFmpegEngine()
