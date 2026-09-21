"""FFmpeg engine facade — the ONLY place handlers build FFmpeg commands.

services/stream.py stream_manager remains the process/runtime implementation;
this module is the stable interface handlers may import. Legacy direct calls
keep working because every method delegates to stream_manager.
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


class FFmpegEngine:
    def __init__(self):
        from services.stream import stream_manager
        self._sm = stream_manager

    # -- capabilities (cached inside stream_manager) -------------------------
    def has_ffmpeg(self) -> bool:
        return bool(self._sm.has_ffmpeg())

    def video_encoder(self) -> str:
        try:
            from services.stream import _pick_video_encoder
            return _pick_video_encoder(self._sm.ffmpeg or "ffmpeg")
        except Exception:
            return "libx264"

    # -- probing -------------------------------------------------------------
    def probe(self, url: str, headers: Optional[dict] = None) -> Dict[str, Any]:
        from services.source_probe import probe_source, sanitize_url_for_ffmpeg
        from services.url_normalizer import normalize_url
        clean, safe = normalize_url(url)
        return probe_source(safe, headers=headers)

    async def probe_async(self, url: str, headers: Optional[dict] = None, quality: str = "best") -> Dict[str, Any]:
        from services.media.source_probe_v2 import probe_media_url
        return await probe_media_url(url, headers=headers, quality=quality)

    # -- command building (single authority, delegates to services.stream) ---
    def build_command(
        self,
        *,
        source_url: str,
        rtmp_url: str,
        media_mode: str = "auto",
        quality: str = "auto",
        headers: Optional[dict] = None,
        volume: float = 1.0,
        audio_bitrate: str = "128k",
        with_video: bool = False,
        start_offset: float = 0.0,
        source_type: str = "",
        probe_result: Optional[dict] = None,
        force_video_for_audio: bool = False,
    ) -> List[str]:
        """Build one FFmpeg command from a structured request.

        Quality/bitrate parameters come exclusively from quality_manager —
        handlers must not construct raw FFmpeg args themselves.
        """
        from services.stream import build_ffmpeg_cmd, _validate_source_url
        from services.quality_manager import resolve_for_source
        from services.url_normalizer import sanitize_url_for_ffmpeg

        safe_source = _validate_source_url(sanitize_url_for_ffmpeg(source_url))
        probe = probe_result or {}
        mk = media_mode if media_mode in ("audio", "video") else (probe.get("media_kind") or ("audio" if media_mode == "audio" else "video"))
        prof = resolve_for_source(
            quality, probe.get("height"), str(mk).lower(), default="360p_stable"
        )
        effective_audio_br = prof.audio_bitrate if audio_bitrate in (None, "", "128k") else audio_bitrate
        return build_ffmpeg_cmd(
            self._sm.ffmpeg or "ffmpeg",
            safe_source,
            rtmp_url,
            audio_bitrate=effective_audio_br,
            volume=volume,
            with_video=with_video,
            start_offset=start_offset,
            extra_headers=headers,
            media_kind=str(mk),
            has_audio=probe.get("has_audio"),
            has_video=probe.get("has_video"),
            source_type=source_type or probe.get("source_type") or "",
            force_video_for_audio=force_video_for_audio,
            quality_profile=prof,
        )

    # -- runtime controls (delegated) ---------------------------------------
    def start_stream(self, stream_id: int, source_url: str, rtmp_url: str, **kwargs) -> Optional[int]:
        return self._sm.start_stream(stream_id, source_url, rtmp_url, **kwargs)

    def stop_stream(self, stream_id: int) -> bool:
        try:
            return bool(self._sm.stop_stream(stream_id))
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

    def get_state(self, stream_id: int) -> str:
        try:
            return str(self._sm.get_state(stream_id))
        except Exception:
            return "stopped"

    def get_meta(self, stream_id: int) -> dict:
        try:
            return self._sm.get_meta(stream_id) or {}
        except Exception:
            return {}

    def get_stats(self, stream_id: int) -> Dict[str, Any]:
        """Structured runtime stats for the Statistics panel."""
        meta = self.get_meta(stream_id)
        prog = meta.get("progress") or {}
        return {
            "state": self.get_state(stream_id),
            "pid": self._sm.get_pid(stream_id),
            "uptime_start": meta.get("last_start"),
            "restarts": meta.get("restarts", 0),
            "reconnects": meta.get("reconnect_count", meta.get("restarts", 0)),
            "bitrate": prog.get("bitrate_str") or "غير متاح",
            "speed": prog.get("speed_str") or "غير متاح",
            "frames": prog.get("frame"),
            "fps": meta.get("fps"),
            "resolution": meta.get("resolution"),
            "volume": meta.get("volume", 1.0),
            "quality": meta.get("quality"),
            "last_error": meta.get("last_error") or "",
        }


ffmpeg_engine = FFmpegEngine()
