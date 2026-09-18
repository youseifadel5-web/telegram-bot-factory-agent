"""FFmpeg input/output profiles, chosen by the REAL source type.

No single command for all sources. Live sources never get ``-re``; VOD/files do.
Audio-only never gets a synthetic black video unless explicitly forced. Mapping
is conditional so a missing stream never fails FFmpeg.
"""
from __future__ import annotations

import logging
from typing import Callable, List, Optional

logger = logging.getLogger(__name__)

UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
)
AUDIO_FILTER = "aresample=async=1:min_hard_comp=0.100:first_pts=0"

# max_height -> (max width, max height)
_RES_MAP = {1080: (1920, 1080), 720: (1280, 720), 480: (854, 480), 360: (640, 360), 240: (426, 240)}
_DEFAULT_BITRATE = {1080: "4500k", 720: "2500k", 480: "1200k", 360: "700k", 240: "400k"}


def _http_headers(source_url: str, extra: Optional[dict]) -> str:
    from urllib.parse import urlparse
    headers = {
        "User-Agent": UA,
        "Accept": "*/*",
        "Accept-Language": "ar,en-US;q=0.9,en;q=0.8",
        "Connection": "keep-alive",
        "Accept-Encoding": "identity",
    }
    try:
        host = urlparse(source_url).netloc
        if host:
            headers.setdefault("Referer", f"https://{host}/")
            headers.setdefault("Origin", f"https://{host}")
    except Exception:
        pass
    if extra:
        headers.update({str(k): str(v) for k, v in extra.items()})
    return "\r\n".join(f"{k}: {v}" for k, v in headers.items()) + "\r\n"


def build_input_args(
    info,
    *,
    supports: Callable[[str], bool],
    extra_headers: Optional[dict] = None,
    rw_timeout: str = "15000000",
    need_re: bool = False,
) -> List[str]:
    """Everything that goes BEFORE ``-i <source>``."""
    args: List[str] = []
    if need_re:
        args += ["-re"]
    transport = getattr(info, "transport", "http")
    if transport == "http":
        option_values = [
            ("rw_timeout", rw_timeout),
            ("timeout", rw_timeout),
            ("reconnect", "1"),
            ("reconnect_streamed", "1"),
            ("reconnect_at_eof", "1"),
            ("reconnect_delay_max", "10"),
            ("reconnect_on_network_error", "1"),
            ("reconnect_on_http_error", "5xx"),
        ]
        for option, value in option_values:
            if supports(option):
                args += [f"-{option}", value]
        if supports("protocol_whitelist"):
            args += ["-protocol_whitelist", "file,http,https,tcp,tls,crypto"]
        ua = UA
        if extra_headers and extra_headers.get("User-Agent"):
            ua = extra_headers["User-Agent"]
        if supports("user_agent"):
            args += ["-user_agent", ua]
        hdr = _http_headers(getattr(info, "url", ""), {k: v for k, v in (extra_headers or {}).items() if k != "User-Agent"})
        args += ["-headers", hdr]
        if getattr(info, "is_hls", False):
            if supports("allowed_extensions"):
                args += ["-allowed_extensions", "ALL"]
            if supports("live_start_index") and getattr(info, "is_live", True):
                args += ["-live_start_index", "-1"]
    elif transport in ("rtmp", "rtmps"):
        if supports("rw_timeout"):
            args += ["-rw_timeout", rw_timeout]
        args += ["-rtmp_live", "live"]
    args += [
        "-fflags", "+genpts+discardcorrupt+igndts",
        "-max_interleave_delta", "0",
        "-thread_queue_size", "512",
    ]
    return args


def video_encode_args(
    encoder: str,
    *,
    supports: Callable[[str], bool],
    bitrate: Optional[str] = None,
    max_height: int = 720,
) -> List[str]:
    max_w, max_h = _RES_MAP.get(int(max_height or 720), _RES_MAP[720])
    if not bitrate:
        bitrate = _DEFAULT_BITRATE.get(int(max_height or 720), "1500k")
    scale = (
        f"scale='min({max_w},iw)':'min({max_h},ih)':force_original_aspect_ratio=decrease,"
        "scale=trunc(iw/2)*2:trunc(ih/2)*2,"
        "setsar=1"
    )
    args = ["-c:v", encoder]
    if encoder in ("libx264", "h264"):
        args += ["-preset", "veryfast", "-tune", "zerolatency"]
    args += [
        "-b:v", bitrate,
        "-maxrate", bitrate,
        "-bufsize", "4000k",
        "-pix_fmt", "yuv420p",
        "-r", "25",
        "-vf", scale,
        "-g", "50",
        "-keyint_min", "50",
        "-sc_threshold", "0",
    ]
    if supports("fps_mode"):
        args += ["-fps_mode", "cfr"]
    elif supports("vsync"):
        args += ["-vsync", "cfr"]
    return args


def audio_encode_args(audio_bitrate: str, volume: float = 1.0) -> List[str]:
    af_parts = []
    if abs(volume - 1.0) > 1e-6:
        af_parts.append(f"volume={volume}")
    af_parts.append(AUDIO_FILTER)
    return [
        "-c:a", "aac",
        "-b:a", audio_bitrate,
        "-ar", "48000",
        "-ac", "2",
        "-af", ",".join(af_parts),
    ]


def build_output_args(
    *,
    has_video: bool,
    has_audio: bool,
    encoder: str,
    supports: Callable[[str], bool],
    audio_bitrate: str,
    volume: float,
    force_black_video: bool,
    black_video_index: Optional[int] = None,
    max_height: int = 720,
    video_bitrate: Optional[str] = None,
) -> List[str]:
    """Map + encode. Never fails because one of the streams is missing."""
    args: List[str] = []
    if has_video:
        args += ["-map", "0:v:0"]
        if has_audio:
            args += ["-map", "0:a:0?"]
        args += video_encode_args(encoder, supports=supports, bitrate=video_bitrate, max_height=max_height)
    elif force_black_video and black_video_index is not None:
        args += ["-map", f"{black_video_index}:v:0"]
        if has_audio:
            args += ["-map", "0:a:0?"]
        args += video_encode_args(encoder, supports=supports, bitrate="300k", max_height=max_height)
    if has_audio:
        if not has_video:
            args += ["-map", "0:a:0?"]
        args += audio_encode_args(audio_bitrate, volume)
    args += ["-max_muxing_queue_size", "2048"]
    return args


def build_ffmpeg_command(
    ffmpeg: str,
    info,
    rtmp_url: str,
    *,
    encoder: str = "libx264",
    audio_bitrate: str = "128k",
    volume: float = 1.0,
    with_video: bool = True,
    force_black_video: bool = False,
    start_offset: float = 0.0,
    extra_headers: Optional[dict] = None,
    supports: Optional[Callable[[str], bool]] = None,
    rw_timeout: str = "15000000",
    max_height: int = 720,
    video_bitrate: Optional[str] = None,
) -> List[str]:
    if supports is None:
        def supports(_opt: str) -> bool:  # noqa: E306
            return True

    has_video = bool(getattr(info, "has_video", False)) and with_video
    has_audio = bool(getattr(info, "has_audio", False))
    is_live = getattr(info, "is_live", None)
    need_re = bool(getattr(info, "transport", "http") == "file" or is_live is False)

    cmd: List[str] = [
        ffmpeg,
        "-hide_banner",
        "-loglevel", "warning",
        "-nostdin",
        "-progress", "pipe:1",
        "-nostats",
        "-analyzeduration", "15M",
        "-probesize", "15M",
        "-err_detect", "ignore_err",
    ]
    if start_offset and start_offset > 0:
        cmd += ["-ss", str(float(start_offset))]

    cmd += build_input_args(
        info, supports=supports, extra_headers=extra_headers,
        rw_timeout=rw_timeout, need_re=need_re,
    )
    cmd += ["-i", getattr(info, "url", "")]

    black_index: Optional[int] = None
    if force_black_video and not has_video:
        cmd += ["-f", "lavfi", "-thread_queue_size", "512", "-i", "color=c=black:s=1280x720:r=25"]
        black_index = 1

    cmd += build_output_args(
        has_video=has_video,
        has_audio=has_audio,
        encoder=encoder,
        supports=supports,
        audio_bitrate=audio_bitrate,
        volume=volume,
        force_black_video=force_black_video,
        black_video_index=black_index,
        max_height=max_height,
        video_bitrate=video_bitrate,
    )
    cmd += ["-f", "flv", "-flvflags", "no_duration_filesize", rtmp_url]
    return cmd
