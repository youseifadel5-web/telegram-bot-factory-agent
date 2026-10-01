"""FFmpeg stream manager with a REAL audio watchdog for stable 24/7 Telegram RTMP.

Key upgrades vs the old version:
- Health is no longer "the ffmpeg process is still alive". We read ffmpeg's own
  `-progress pipe:1` machine-readable stream (out_time_ms / frame / bitrate) and
  only declare a stream "on air" once real encoded output is actually advancing.
  If output stalls (source froze, RTMP stopped accepting data, network died)
  while the process is technically still running, we treat it as unhealthy and
  restart — exactly the class of failure a plain "is the pid alive" check misses.
- Failover: each stream can carry a list of source URLs (primary + backups).
  After N consecutive failed connect attempts on the current source, the
  manager automatically switches to the next source in the list.
- Only one broadcast is allowed system-wide: starting a new stream stops any
  other stream currently running, and cleans up orphaned ffmpeg processes left
  behind by a previous crashed session.
"""
import logging
import os
import re
import signal
import subprocess
import shutil
import tarfile
import urllib.request
import threading
import time
from pathlib import Path
from typing import Optional, Dict, Any, List

from config import FFMPEG_PATH, MAX_STREAMS

logger = logging.getLogger(__name__)

# --------------------------------------------------------------------------- #
# DB log bridge (stream_logs) — watchdogs run in threads; events are forwarded
# to the asyncio loop main.py registers at startup. Never raises.
# --------------------------------------------------------------------------- #
_LOG_LOOP = None


def set_logging_loop(loop):
    global _LOG_LOOP
    _LOG_LOOP = loop


def log_stream_event(stream_id: int, event: str, message: str = "", user_id: int = None):
    try:
        if _LOG_LOOP is not None and _LOG_LOOP.is_running():
            import asyncio as _aio
            from database import db as _db
            _aio.run_coroutine_threadsafe(
                _db.add_stream_log(int(stream_id), int(user_id or 0), event, str(message)[:500]),
                _LOG_LOOP,
            )
    except Exception:
        pass


ROOT = Path(__file__).resolve().parent.parent
LOCAL_FFMPEG_DIR = ROOT / "bin"
LOCAL_FFMPEG = LOCAL_FFMPEG_DIR / "ffmpeg"
FFMPEG_STATIC_URL = (
    "https://johnvansickle.com/ffmpeg/releases/ffmpeg-release-amd64-static.tar.xz"
)

def _env_int(name: str, default: int) -> int:
    try:
        return max(1, int(os.getenv(name, "") or default))
    except Exception:
        return default


# After this many seconds of a running ffmpeg process with NO progress
# (out_time not advancing), we consider audio "stalled" and force a restart.
# All limits are configurable via .env (never hardcoded only).
STALL_TIMEOUT = _env_int("STALL_TIMEOUT", 45)
# Seconds of continuous, advancing progress before we call it healthy / ON AIR.
HEALTHY_AFTER = _env_int("HEALTHY_AFTER", 8)
# Consecutive failed connect attempts on one source before failing over.
MAX_FAILS_BEFORE_FAILOVER = _env_int("MAX_FAILS_BEFORE_FAILOVER", 3)

_FFMPEG_OPTION_CACHE: Dict[tuple, bool] = {}


_FFMPEG_HELP_CACHE: Dict[str, str] = {}
_FFMPEG_ENCODER_CACHE: Dict[str, str] = {}


def _ffmpeg_help_text(ffmpeg: str) -> str:
    """Fetch and cache full help output once per binary path."""
    key = str(ffmpeg or "")
    if key in _FFMPEG_HELP_CACHE:
        return _FFMPEG_HELP_CACHE[key]
    output = ""
    try:
        proc = subprocess.run(
            [ffmpeg, "-hide_banner", "-h", "full"],
            capture_output=True, text=True, timeout=12,
        )
        output = (proc.stdout or "") + "\n" + (proc.stderr or "")
    except Exception as exc:
        logger.debug("FFmpeg help probe failed: %s", exc)
    if output.strip():
        _FFMPEG_HELP_CACHE[key] = output
    # An empty result is NOT cached — retry on the next call, otherwise every
    # later stream silently loses -reconnect/-rw_timeout/-user_agent support.
    return output


def _ffmpeg_supports_option(ffmpeg: str, option: str) -> bool:
    """Check an option against the exact FFmpeg binary in use.

    Distribution/static builds differ. Probing the binary once prevents an
    unsupported input option from being misreported as a dead media URL.
    """
    key = (str(ffmpeg or ""), option)
    if key in _FFMPEG_OPTION_CACHE:
        return _FFMPEG_OPTION_CACHE[key]
    output = _ffmpeg_help_text(ffmpeg)
    supported = bool(re.search(rf"(?m)^\s*-{re.escape(option)}\b", output)) if output else False
    _FFMPEG_OPTION_CACHE[key] = supported
    return supported


def _pick_video_encoder(ffmpeg: str) -> str:
    """Prefer libx264; fall back to mpeg4 if the static build lacks x264."""
    key = str(ffmpeg or "")
    if key in _FFMPEG_ENCODER_CACHE:
        return _FFMPEG_ENCODER_CACHE[key]
    encoder = "libx264"
    try:
        proc = subprocess.run(
            [ffmpeg, "-hide_banner", "-encoders"],
            capture_output=True, text=True, timeout=10,
        )
        out = (proc.stdout or "") + (proc.stderr or "")
        if "libx264" in out:
            encoder = "libx264"
        elif "mpeg4" in out:
            encoder = "mpeg4"
        else:
            encoder = "libx264"  # hope for the best; error will surface in stderr
    except Exception as exc:
        logger.debug("encoder probe failed: %s", exc)
    _FFMPEG_ENCODER_CACHE[key] = encoder
    logger.info("FFmpeg video encoder selected: %s", encoder)
    return encoder


# --------------------------------------------------------------------------- #
# FFmpeg discovery / install
# --------------------------------------------------------------------------- #
def _try_apt_install() -> Optional[str]:
    """Best-effort apt install — works if the container has root/apt (not on
    most shared hosts like KataBump, but harmless to try first)."""
    try:
        if shutil.which("apt-get") is None:
            return None
        subprocess.run(["apt-get", "update", "-y"], capture_output=True, timeout=90)
        subprocess.run(["apt-get", "install", "-y", "ffmpeg"], capture_output=True, timeout=180)
        return shutil.which("ffmpeg")
    except Exception as e:
        logger.info("apt-get ffmpeg install skipped: %s", e)
        return None


def _try_download_static_ffmpeg() -> Optional[str]:
    """Downloads a static, self-contained ffmpeg binary — no root needed.
    This is the path that actually works on KataBump."""
    try:
        if LOCAL_FFMPEG.exists() and os.access(LOCAL_FFMPEG, os.X_OK):
            return str(LOCAL_FFMPEG)
        LOCAL_FFMPEG_DIR.mkdir(parents=True, exist_ok=True)
        archive = LOCAL_FFMPEG_DIR / "ffmpeg-static.tar.xz"
        logger.info("FFmpeg not found — downloading static build...")
        with urllib.request.urlopen(FFMPEG_STATIC_URL, timeout=180) as resp, open(archive, "wb") as out:
            shutil.copyfileobj(resp, out)
        with tarfile.open(archive, "r:xz") as tar:
            wanted = {"ffmpeg": None, "ffprobe": None}
            for m in tar.getmembers():
                for binname in wanted:
                    if m.isfile() and m.name.endswith("/" + binname):
                        wanted[binname] = m
            for binname, member in wanted.items():
                if not member:
                    continue
                member.name = binname
                try:
                    tar.extract(member, path=LOCAL_FFMPEG_DIR, filter="data")
                except TypeError:  # Python < 3.11.4 has no filter= kwarg
                    tar.extract(member, path=LOCAL_FFMPEG_DIR)
                (LOCAL_FFMPEG_DIR / binname).chmod(0o755)
        LOCAL_FFMPEG.chmod(0o755)
        try:
            archive.unlink()
        except Exception:
            pass
        return str(LOCAL_FFMPEG) if LOCAL_FFMPEG.exists() else None
    except Exception as e:
        logger.error("static ffmpeg download failed: %s", e)
        return None


def find_ffmpeg() -> Optional[str]:
    """Resolution order: configured path -> already-downloaded static build ->
    system PATH -> apt install (if root) -> download static build."""
    if FFMPEG_PATH and shutil.which(FFMPEG_PATH):
        return FFMPEG_PATH
    if LOCAL_FFMPEG.exists() and os.access(LOCAL_FFMPEG, os.X_OK):
        return str(LOCAL_FFMPEG)
    for c in ("ffmpeg", "/usr/bin/ffmpeg", "/usr/local/bin/ffmpeg"):
        f = shutil.which(c)
        if f:
            return f
    apt = _try_apt_install()
    if apt:
        return apt
    return _try_download_static_ffmpeg()


def kill_orphan_ffmpeg():
    """Deprecated safety hook.

    A process discovered by name is not necessarily ours; killing it can stop
    another bot or user on a shared host. Current streams are terminated by
    their tracked process group in ``StreamManager.cleanup_all`` instead.
    """
    logger.info("Skipping unscoped FFmpeg cleanup; only tracked processes are managed")


# --------------------------------------------------------------------------- #
# ffmpeg command builder
# --------------------------------------------------------------------------- #

def _validate_source_url(url: str) -> str:
    """Clean and reject dangerous characters that break FFmpeg or enable injection."""
    if not url or not isinstance(url, str):
        raise ValueError("empty source")
    try:
        from services.source_probe import clean_url, sanitize_url_for_ffmpeg
        url = sanitize_url_for_ffmpeg(clean_url(url))
    except Exception:
        url = url.strip()
    # OscarTV / app players attach #t=timestamp — breaks ffmpeg
    if "#" in url and not url.startswith("file:"):
        url = url.split("#", 1)[0]
    # allow only expected schemes
    if not url.startswith(("http://", "https://", "rtmp://", "rtmps://", "/", "file:")):
        raise ValueError("unsupported source scheme")
    # Remote user-supplied sources must not reach private/metadata networks.
    if url.startswith(("http://", "https://", "rtmp://", "rtmps://")):
        try:
            from services.hls_relay import is_relay_url
            is_relay = is_relay_url(url)
        except Exception:
            is_relay = False
        if not is_relay:
            # الرابط الأصلي الخارجي تم فحصه بالفعل قبل تغليفه بالريلاي —
            # الرابط المحلي (127.0.0.1) خاص بالريلاي ولا يشكل خطراً.
            from services.security.ssrf import assert_safe_url
            assert_safe_url(url)
    elif url.startswith(("/", "file:")):
        # Local files are only valid inside this project data directory.
        local_path = url[5:] if url.startswith("file:") else url
        resolved = Path(local_path).expanduser().resolve()
        allowed_root = (ROOT / "data").resolve()
        if allowed_root != resolved and allowed_root not in resolved.parents:
            raise ValueError("local source path is outside project data")
    # block shell metacharacters even though we use argv list
    for bad in (";", "|", "`", "$(", "\n", "\r"):
        if bad in url:
            raise ValueError("invalid character in source URL")
    return url

def _build_safe_cmd(
    ffmpeg: str,
    source_url: str,
    rtmp_url: str,
    quality_profile=None,
    with_video: bool = False,
    media_kind: str = "unknown",
    has_audio: Optional[bool] = None,
    has_video: Optional[bool] = None,
    audio_bitrate: str = "128k",
    source_type: str = "",
    force_video_for_audio: bool = False,
) -> list:
    """الأمر المجرّب حرفياً (سكربت المستخدم العامل) — بلا أي خيارات متقدمة.

    يُستخدم كخطة بديلة تلقائية عندما يرفض بناء FFmpeg على السيرفر أحد
    الخيارات المتقدمة بخطأ «Error opening output files: Invalid argument».
    كل خيار هنا مأخوذ من سكربت مجرّب فعلياً (فيديو + صوت).
    """
    mk = (media_kind or "").lower()
    u = source_url.lower().split("?", 1)[0]
    if mk not in ("audio", "video"):
        mk = "audio" if any(x in u for x in (".mp3", ".aac", ".m4a", ".ogg", "/radio", "icecast", "shoutcast")) else "video"
    audio_only = (mk == "audio" and not has_video)
    is_http = source_url.startswith(("http://", "https://"))

    cmd = [ffmpeg, "-hide_banner", "-loglevel", "warning", "-nostdin"]
    st = (source_type or "").lower()
    is_live = any(x in st for x in ("hls", "m3u8", "live", "rtmp", "radio", "iptv")) or any(
        x in source_url.lower() for x in (".m3u8", "/hls", "/live", ".ts"))
    if not is_live:
        cmd += ["-re"]
    cmd += ["-thread_queue_size", "4096"]
    if is_http:
        # نفس ما يفعله السكربت المجرّب: وكيل مستخدم بسيط فقط.
        cmd += ["-user_agent", "Mozilla/5.0"]
    cmd += ["-i", source_url]

    if not audio_only:
        try:
            h = int(getattr(quality_profile, "height", 0) or 0) or 360
        except Exception:
            h = 360
        h = max(144, min(720, h))
        vb = str(getattr(quality_profile, "video_bitrate", None) or "700k")
        cmd += [
            "-map", "0:v:0?", "-map", "0:a:0?",
            "-vf", f"scale=-2:{h}",
            "-c:v", "libx264", "-preset", "veryfast", "-tune", "zerolatency",
            "-pix_fmt", "yuv420p",
            "-r", "25", "-g", "50",
            "-b:v", vb, "-maxrate", vb, "-bufsize", vb,
            "-c:a", "aac", "-b:a", "96k", "-ar", "44100", "-ac", "2",
        ]
    else:
        cmd += [
            "-map", "0:a:0?", "-vn",
            "-c:a", "aac", "-b:a", "128k", "-ar", "44100", "-ac", "2",
        ]
    cmd += [
        "-progress", "pipe:1", "-nostats",
        "-f", "flv", "-flvflags", "no_duration_filesize",
        rtmp_url,
    ]
    return cmd


def build_ffmpeg_cmd(
    ffmpeg: str,
    source_url: str,
    rtmp_url: str,
    audio_bitrate: str = "128k",
    volume: float = 1.0,
    with_video: bool = False,
    start_offset: float = 0.0,
    extra_headers: dict = None,
    media_kind: str = "unknown",
    has_audio: Optional[bool] = None,
    has_video: Optional[bool] = None,
    source_type: str = "",
    force_video_for_audio: bool = False,
    quality_profile=None,
    allow_copy: bool = False,
    safe_mode: bool = False,
) -> list:
    """Build a robust FFmpeg command for Telegram RTMPS / FLV live ingest.

    Improvements vs previous version:
    - Single help-text probe (cached) for option support
    - Auto-select video encoder (libx264 → h264 → mpeg4)
    - Force even dimensions + max 1280x720 (Telegram-friendly)
    - thread_queue_size to avoid multi-input stalls
    - Use config FFMPEG_TIMEOUT when available
    - True audio-only output when source has no video; optional compatibility video fallback
    - FLV flags friendly to indefinite live streams
    """
    if safe_mode:
        return _build_safe_cmd(
            ffmpeg, source_url, rtmp_url, quality_profile=quality_profile,
            with_video=with_video, media_kind=media_kind, has_audio=has_audio,
            has_video=has_video, audio_bitrate=audio_bitrate, source_type=source_type,
            force_video_for_audio=force_video_for_audio,
        )
    try:
        from config import FFMPEG_TIMEOUT as _CFG_TIMEOUT
        rw_timeout = str(int(_CFG_TIMEOUT) if _CFG_TIMEOUT else 30_000_000)
    except Exception:
        rw_timeout = "30000000"

    vol_filter = f"volume={volume}" if abs(volume - 1.0) > 1e-6 else None
    af_parts = ["aresample=async=1:min_hard_comp=0.100:first_pts=0"]
    if vol_filter:
        af_parts.insert(0, vol_filter)
    af = ",".join(af_parts)

    # Central quality profile (quality_manager) — handlers never hardcode args.
    prof = quality_profile
    if prof is not None and audio_bitrate in (None, "", "128k"):
        ab = getattr(prof, "audio_bitrate", None)
        if ab:
            audio_bitrate = ab
    max_w = int(getattr(prof, "width", 0) or 0) or 1280
    max_h = int(getattr(prof, "height", 0) or 0) or 720

    # Even dimensions + cap resolution for stable RTMP ingest
    vf_scale = (
        f"scale='min({max_w},iw)':'min({max_h},ih)':force_original_aspect_ratio=decrease,"
        "scale=trunc(iw/2)*2:trunc(ih/2)*2,"
        "setsar=1"
    )

    v_encoder = _pick_video_encoder(ffmpeg)
    # mpeg4 does not support -tune / -preset the same way
    x264_style = v_encoder in ("libx264", "h264")

    cmd = [
        ffmpeg,
        "-hide_banner",
        "-loglevel", "warning",
        "-nostdin",
        "-analyzeduration", "20M",
        "-probesize", "20M",
        "-err_detect", "ignore_err",
    ]

    if start_offset and start_offset > 0:
        cmd += ["-ss", str(float(start_offset))]

    is_http = source_url.startswith(("http://", "https://"))
    if is_http:
        headers = {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
            ),
            "Accept": "*/*",
            "Accept-Language": "ar,en-US;q=0.9,en;q=0.8",
            "Connection": "keep-alive",
            "Accept-Encoding": "identity",
        }
        # Many CDN / egybest-style hosts require a Referer
        try:
            from urllib.parse import urlparse
            host = urlparse(source_url).netloc
            if host:
                headers.setdefault("Referer", f"https://{host}/")
                headers.setdefault("Origin", f"https://{host}")
        except Exception:
            pass
        if extra_headers:
            headers.update({str(k): str(v) for k, v in extra_headers.items()})

        option_values = [
            ("rw_timeout", rw_timeout),
            ("timeout", rw_timeout),
            ("reconnect", "1"),
            ("reconnect_streamed", "1"),
            ("reconnect_at_eof", "1"),
            ("reconnect_delay_max", "15"),
            ("reconnect_on_network_error", "1"),
            ("reconnect_on_http_error", "4xx,5xx"),
            # Do not pass http_persistent/http_seekable here. Some Ubuntu and
            # static FFmpeg builds list these in generic help, but reject them
            # for this input protocol with "Option ... not found".
        ]
        for option, value in option_values:
            if _ffmpeg_supports_option(ffmpeg, option):
                cmd += [f"-{option}", value]
        if _ffmpeg_supports_option(ffmpeg, "protocol_whitelist"):
            cmd += ["-protocol_whitelist", "file,http,https,tcp,tls,crypto"]
        ua = headers.pop("User-Agent", "Mozilla/5.0")
        if _ffmpeg_supports_option(ffmpeg, "user_agent"):
            cmd += ["-user_agent", ua]
        else:
            headers["User-Agent"] = ua
        hdr = "\r\n".join(f"{k}: {v}" for k, v in headers.items())
        if hdr:
            cmd += ["-headers", hdr + "\r\n"]
        if (".m3u8" in source_url.lower() or "/hls" in source_url.lower()) and _ffmpeg_supports_option(ffmpeg, "allowed_extensions"):
            cmd += ["-allowed_extensions", "ALL"]
        if (".m3u8" in source_url.lower() or "/hls" in source_url.lower()) and _ffmpeg_supports_option(ffmpeg, "live_start_index"):
            cmd += ["-live_start_index", "-1"]

    # Decide media mode from the actual probe when available. URL extension is only a fallback.
    mk = (media_kind or "").lower()
    u = source_url.lower().split("?", 1)[0]
    if mk not in ("audio", "video"):
        if any(x in u for x in (".mp3", ".aac", ".m4a", ".ogg", ".opus", ".wav", "/radio", "radio.", "icecast", "shoutcast")):
            mk = "audio"
        else:
            mk = "video"
    if has_audio is None:
        has_audio = True if mk in ("audio", "video") else bool(with_video)
    if has_video is None:
        has_video = (mk == "video" and bool(with_video))
    audio_only = (mk == "audio" and not has_video)
    video_only = (mk == "video" and not has_audio)
    effective_video = bool(with_video or has_video) and not audio_only
    if audio_only and force_video_for_audio:
        effective_video = True
    canvas = audio_only and force_video_for_audio

    # Live inputs must not be artificially throttled with -re. VOD/files may use it.
    is_live = any(x in (source_type or "").lower() for x in ("hls", "m3u8", "live", "rtmp", "radio", "iptv"))
    if not is_live:
        u = source_url.lower()
        is_live = any(x in u for x in (".m3u8", "/hls", "/live", "rtmp://", "rtmps://", "/radio", "icecast", "shoutcast"))
    if not is_live:
        cmd += ["-re"]

    # HLS manifests can have misleading extensions (e.g. .css/.php). The probe may
    # identify them by content; force the HLS demuxer in that case.
    st = (source_type or "").lower()
    # Force the HLS demuxer ONLY when the content sniff confirmed HLS or the URL
    # itself is an .m3u8 manifest. Guessing from substrings like "/hls" breaks
    # plain MP4/TS streams that merely contain it ("Invalid data found").
    is_hls = "hls" in st or "m3u8" in st or ".m3u8" in source_url.lower()
    if is_hls:
        cmd += ["-f", "hls"]

    cmd += [
        "-fflags", "+genpts+discardcorrupt+igndts",
        "-max_interleave_delta", "0",
        "-thread_queue_size", "4096",
        "-i", source_url,
    ]

    if allow_copy:
        # ── وضع البث المباشر (IPTV): نسخ بدون إعادة ترميز ──────────────
        # أسرع بكثير وأخف على المعالج: FFmpeg يقرأ h264/aac ويكتبه كما هو.
        # يُستخدم للمصادر المؤكدة (فحص HLS سريع) ويسقط تلقائياً إلى
        # إعادة الترميز إن فشل.
        cmd += [
            "-map", "0:v:0?",
            "-map", "0:a:0?",
            "-c", "copy",
            "-max_muxing_queue_size", "2048",
            "-progress", "pipe:1",
            "-nostats",
            "-f", "flv",
            "-flvflags", "no_duration_filesize",
            rtmp_url,
        ]
        return cmd

    if effective_video:
        if canvas:
            # Audio-only source forced into an RTMP that requires a video
            # track: tiny low-CPU black canvas (lavfi) — no heavy encode.
            cmd += ["-f", "lavfi", "-i", "color=c=black:s=320x180:r=5"]
        vcodec_block = [
            "-map", "1:v:0" if canvas else "0:v:0?",
        ]
        if has_audio is not False:
            vcodec_block += ["-map", "0:a:0?"]
        vcodec_block += ["-c:v", v_encoder]
        if x264_style:
            vcodec_block += ["-preset", "veryfast", "-tune", "zerolatency"]
        if canvas:
            v_b, v_mr, v_bs, out_fps = "150k", "200k", "300k", "10"
        else:
            v_b = getattr(prof, "video_bitrate", None) or "1000k"
            v_mr = getattr(prof, "maxrate_v", None) or "1200k"
            v_bs = getattr(prof, "bufsize_v", None) or "2000k"
            out_fps = "25"
        vcodec_block += [
            "-b:v", v_b, "-maxrate", v_mr, "-bufsize", v_bs,
            "-pix_fmt", "yuv420p", "-r", out_fps, "-vf", vf_scale,
        ]
        if has_audio is not False:
            vcodec_block += [
                "-c:a", "aac", "-b:a", audio_bitrate, "-ar", "44100", "-ac", "2",
                "-af", af,
            ]
        vcodec_block += [
            "-max_muxing_queue_size", "2048", "-g", "50", "-keyint_min", "50", "-sc_threshold", "0",
        ]
        if canvas:
            # The lavfi canvas is infinite; without -shortest the stream keeps
            # broadcasting silent black video long after the source ended.
            vcodec_block += ["-shortest"]
        if _ffmpeg_supports_option(ffmpeg, "fps_mode"):
            vcodec_block += ["-fps_mode", "cfr"]
        else:
            vcodec_block += ["-vsync", "cfr"]
        cmd += vcodec_block
    else:
        # Genuine audio-only output. No synthetic black video is created.
        cmd += [
            "-map", "0:a:0?",
            "-vn",
            "-c:a", "aac",
            "-b:a", audio_bitrate,
            "-ar", "44100",
            "-ac", "2",
            "-af", af,
            "-max_muxing_queue_size", "1024",
        ]

    # Machine-readable progress for the watchdog; FLV without bogus duration/size.
    cmd += [
        "-progress", "pipe:1",
        "-nostats",
        "-f", "flv",
        "-flvflags", "no_duration_filesize",
        rtmp_url,
    ]
    return cmd


def _parse_progress_line(line: str, state: dict):
    """Parses one `key=value` line from ffmpeg's -progress output."""
    if "=" not in line:
        return
    key, _, val = line.partition("=")
    key, val = key.strip(), val.strip()
    if key == "out_time_ms":
        try:
            state["out_time_ms"] = int(val)
        except ValueError:
            pass
    elif key == "frame":
        try:
            state["frame"] = int(val)
        except ValueError:
            pass
    elif key == "bitrate":
        state["bitrate_str"] = val
    elif key == "speed":
        state["speed_str"] = val
    elif key == "progress":
        state["progress"] = val  # "continue" | "end"


class StreamManager:
    def __init__(self):
        self.processes: Dict[int, subprocess.Popen] = {}
        self._meta: Dict[int, Dict[str, Any]] = {}
        self.ffmpeg: Optional[str] = None
        self._watchdogs: Dict[int, threading.Thread] = {}
        self._readers: Dict[int, threading.Thread] = {}
        self._lock = threading.Lock()

    def ensure_ffmpeg(self) -> bool:
        if self.ffmpeg and (shutil.which(self.ffmpeg) or Path(self.ffmpeg).exists()):
            return True
        self.ffmpeg = find_ffmpeg()
        if not self.ffmpeg:
            return False
        # Quick sanity: binary runs and reports a version
        try:
            proc = subprocess.run(
                [self.ffmpeg, "-version"],
                capture_output=True, text=True, timeout=8,
            )
            if proc.returncode != 0:
                logger.error("FFmpeg binary found but -version failed: %s", (proc.stderr or "")[:200])
                self.ffmpeg = None
                return False
            ver_line = (proc.stdout or "").splitlines()[0] if proc.stdout else "?"
            logger.info("FFmpeg ready: %s (%s)", self.ffmpeg, ver_line[:80])
            # Warm encoder + option caches
            _pick_video_encoder(self.ffmpeg)
            _ffmpeg_help_text(self.ffmpeg)
        except Exception as e:
            logger.error("FFmpeg probe failed: %s", e)
            self.ffmpeg = None
            return False
        return True

    def has_ffmpeg(self) -> bool:
        return self.ensure_ffmpeg()

    def _current_source(self, meta: dict) -> str:
        sources: List[str] = meta.get("sources") or [meta.get("source")]
        idx = meta.get("source_index", 0) % max(len(sources), 1)
        return sources[idx]

    def _spawn(self, stream_id: int) -> Optional[int]:
        meta = self._meta.get(stream_id)
        if not meta:
            return None
        source = _validate_source_url(self._current_source(meta))
        try:
            from services.quality_manager import resolve_for_source
            _prof = resolve_for_source(
                str(meta.get("quality") or "auto"), None, str(meta.get("media_kind") or "video")
            )
        except Exception:
            _prof = None
        # ── قرار وضع النسخ (بدون ترميز) لمصادر IPTV ──────────────────
        vc = str(meta.get("video_codec") or "").lower()
        st = (meta.get("source_type") or "").lower()
        ac = str(meta.get("audio_codec") or "").lower()
        allow_copy = (
            bool(meta.get("with_video"))
            and ac in ("", "aac", "mp3")
            and not meta.get("force_video_for_audio")
            and not meta.get("copy_failed")
            and abs(float(meta.get("volume", 1.0)) - 1.0) < 1e-6
            and (meta.get("quality") in (None, "", "auto"))
            and not meta.get("start_offset")
            and vc in ("", "h264", "avc1")
            and ("hls" in st or "m3u8" in st)
        )
        meta["copy_mode"] = bool(allow_copy)

        cmd = build_ffmpeg_cmd(
            self.ffmpeg,
            source,
            meta["rtmp"],
            quality_profile=_prof,
            allow_copy=allow_copy,
            audio_bitrate=meta.get("audio_bitrate", "128k"),
            volume=meta.get("volume", 1.0),
            with_video=meta.get("with_video", False),
            start_offset=meta.get("start_offset", 0.0),
            extra_headers=meta.get("extra_headers") or None,
            media_kind=meta.get("media_kind", "unknown"),
            has_audio=meta.get("has_audio"),
            has_video=meta.get("has_video"),
            source_type=meta.get("source_type", ""),
            force_video_for_audio=bool(meta.get("force_video_for_audio", False)),
            safe_mode=bool(meta.get("safe_mode")),
        )
        logger.info(
            "FFmpeg start stream=%s source_idx=%s vol=%.2f br=%s safe=%s",
            stream_id, meta.get("source_index", 0), meta.get("volume", 1),
            meta.get("audio_bitrate"), bool(meta.get("safe_mode")),
        )
        try:
            process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,   # FFmpeg -progress pipe:1
                stderr=subprocess.PIPE,   # warnings / connection errors
                preexec_fn=os.setsid if os.name != "nt" else None,
            )
            self.processes[stream_id] = process
            meta["pid"] = process.pid
            meta["last_start"] = time.time()
            meta["restarts"] = meta.get("restarts", 0)
            meta["last_error"] = ""
            meta["healthy"] = False
            meta["state"] = "connecting"
            meta["progress"] = {"out_time_ms": 0, "frame": 0, "bitrate_str": "", "speed_str": ""}
            meta["last_progress_ts"] = time.time()
            meta["last_out_time_ms"] = -1
            meta["output_progress_count"] = 0
            meta["data_flow"] = False
            meta["cmd"] = " ".join(cmd[:8]) + " ..."
            meta["cmd_full"] = cmd

            t = threading.Thread(
                target=self._reader_loop, args=(stream_id, process), daemon=True,
                name=f"reader-{stream_id}",
            )
            self._readers[stream_id] = t
            t.start()
            # اقرأ stderr في خلفية لاستخراج سبب الفشل
            te = threading.Thread(
                target=self._stderr_loop, args=(stream_id, process), daemon=True,
                name=f"stderr-{stream_id}",
            )
            te.start()
            # Brief check: only catch instant crash (bad binary/args). Slow
            # radio/HLS sources need several seconds — watchdog handles those.
            time.sleep(0.4)
            if process.poll() is not None:
                rc = process.returncode
                err = (meta.get("last_error") or f"FFmpeg exited immediately (code {rc})")
                meta["last_error"] = err
                meta["state"] = "error"
                meta["healthy"] = False
                if meta.get("copy_mode"):
                    # الخروج الفوري في وضع النسخ: انزل لإعادة الترميز في المحاولة
                    # القادمة (كودكس غير متوافق مع FLV مثلاً).
                    meta["copy_failed"] = True
                    meta["copy_mode"] = False
                logger.error("Stream %s early exit: %s", stream_id, err[:200])
                self.processes.pop(stream_id, None)
                try:
                    self._kill_proc(process)
                except Exception:
                    pass
                return None
            log_stream_event(stream_id, "rtmp_start", f"FFmpeg spawned pid={process.pid}")
            return process.pid
        except Exception as e:
            logger.error("spawn failed: %s", e)
            meta["last_error"] = str(e)
            meta["state"] = "error"
            return None

    def _reader_loop(self, stream_id: int, process: subprocess.Popen):
        """Read FFmpeg's machine-readable progress from stdout and track
        advancing encoded output. This is stronger evidence than PID state."""
        try:
            if not process.stdout:
                return
            for raw in iter(process.stdout.readline, b""):
                meta = self._meta.get(stream_id)
                if not meta or self.processes.get(stream_id) is not process:
                    break
                line = raw.decode("utf-8", errors="ignore").strip()
                if not line:
                    continue
                prog = meta.setdefault("progress", {})
                _parse_progress_line(line, prog)
                if line.startswith("out_time_ms="):
                    try:
                        current = int(line.split("=", 1)[1].strip())
                    except Exception:
                        current = -1
                    previous = meta.get("last_out_time_ms", -1)
                    if current > previous:
                        meta["last_out_time_ms"] = current
                        meta["last_progress_ts"] = time.time()
                        meta["output_progress_count"] = meta.get("output_progress_count", 0) + 1
                        # Once encoded output is advancing, this is real data flow.
                        if meta.get("output_progress_count", 0) >= 2:
                            meta["data_flow"] = True
        except Exception as e:
            logger.debug("reader loop ended for %s: %s", stream_id, e)

    def _kill_proc(self, process: subprocess.Popen):
        """Terminate process group and close pipes to avoid zombie / deadlock."""
        try:
            if os.name != "nt":
                try:
                    os.killpg(os.getpgid(process.pid), signal.SIGTERM)
                except (ProcessLookupError, PermissionError, OSError):
                    try:
                        process.terminate()
                    except Exception:
                        pass
            else:
                process.terminate()
            try:
                process.wait(timeout=4)
            except subprocess.TimeoutExpired:
                if os.name != "nt":
                    try:
                        os.killpg(os.getpgid(process.pid), signal.SIGKILL)
                    except (ProcessLookupError, PermissionError, OSError):
                        try:
                            process.kill()
                        except Exception:
                            pass
                else:
                    try:
                        process.kill()
                    except Exception:
                        pass
                try:
                    process.wait(timeout=2)
                except Exception:
                    pass
        except Exception as e:
            logger.error("kill error: %s", e)
        finally:
            for pipe in (process.stdout, process.stderr, process.stdin):
                try:
                    if pipe:
                        pipe.close()
                except Exception:
                    pass

    def _classify_ffmpeg_error(self, line: str) -> str:
        """Map raw FFmpeg stderr to a short Arabic + technical debug message."""
        low = (line or "").lower()
        # رفض خيار عند تجهيز الإخراج (كان يُصنَّف خطأً كـ «إصدار قديم»)
        if any(x in low for x in ("failed to set value", "matches no streams", "error parsing options")):
            return f"خيار غير مدعوم عند فتح الإخراج — سيتحول البوت للأمر المجرّب: {line[:160]}"
        if any(x in low for x in ("option not found", "unrecognized option", "unknown option")):
            return f"إصدار FFmpeg لا يدعم أحد الخيارات المطلوبة: {line[:180]}"
        if "invalid argument" in low:
            return f"خيار/قيمة مرفوضة عند الإخراج — سيتحول البوت للأمر المجرّب: {line[:160]}"
        if any(x in low for x in ("error opening output", "failed to open output", "rtmp", "flv muxer")):
            return f"رفض خادم RTMP الإخراج (تحقق من السيرفر والمفتاح): {line[:160]}"
        if any(x in low for x in ("unknown encoder", "encoder not found", "error while opening encoder")):
            return f"مُرمّز الفيديو غير متوفر في FFmpeg (جرّب تثبيت بناء كامل مع libx264): {line[:140]}"
        if "broken pipe" in low or "connection reset" in low:
            return f"انقطع اتصال RTMP (تحقق من المفتاح/السيرفر): {line[:140]}"
        if any(x in low for x in ("500", "502", "503", "504", "server returned 5")):
            return f"خطأ خادم المصدر (5XX): {line[:120]}"
        if "404" in low or "not found" in low:
            return f"الرابط غير موجود (404): {line[:120]}"
        if "403" in low or "forbidden" in low:
            return f"الوصول مرفوض (403): {line[:120]}"
        if any(x in low for x in ("timed out", "timeout", "connection timed out", "operation timed out")):
            return f"انتهت مهلة الاتصال (Timeout): {line[:120]}"
        if "connection refused" in low or "refused" in low:
            return f"رفض الاتصال: {line[:120]}"
        if "invalid data" in low or "invalid argument" in low:
            return f"بيانات تالفة أو صيغة غير صالحة: {line[:120]}"
        if "end of file" in low or "input/output error" in low:
            return f"انقطع المصدر فجأة: {line[:120]}"
        if any(x in low for x in ("error", "failed", "unable to", "cannot", "http error")):
            return line[:160]
        return line[:160]

    def _stderr_loop(self, stream_id: int, process: subprocess.Popen):
        """Collect ffmpeg stderr for useful error messages (does not crash the bot)."""
        try:
            if not process.stderr:
                return
            lines = []
            for raw in iter(process.stderr.readline, b""):
                try:
                    line = raw.decode("utf-8", errors="ignore").strip()
                except Exception:
                    continue
                if not line:
                    continue
                lines.append(line)
                low = line.lower()
                if any(k in low for k in (
                    "error", "failed", "404", "403", "500", "502", "503", "504",
                    "refused", "timed out", "timeout", "invalid", "server returned",
                    "connection", "http error", "no such file", "unable to",
                    "cannot", "not found", "end of file", "input/output",
                )):
                    meta = self._meta.get(stream_id)
                    if meta:
                        meta["last_error"] = self._classify_ffmpeg_error(line)
                        meta["last_error_raw"] = line[:300]
                if len(lines) > 50:
                    lines = lines[-50:]
            meta = self._meta.get(stream_id)
            if meta and lines:
                if not meta.get("last_error"):
                    # Prefer a line that actually contains the input/HTTP failure.
                    candidates = [
                        x for x in lines
                        if any(k in x.lower() for k in (
                            "http", "server", "invalid", "error", "failed", "unable",
                            "forbidden", "not found", "tls", "ssl", "playlist", "m3u8",
                        ))
                    ]
                    chosen = candidates[-1] if candidates else lines[-1]
                    meta["last_error"] = self._classify_ffmpeg_error(chosen)
                # احفظ ذيل stderr دائماً للتشخيص (يكشف الخيار/القيمة المرفوضة).
                meta["last_error_raw"] = " | ".join(lines[-10:])[:1500]
        except Exception as e:
            logger.debug("stderr loop: %s", e)

    def _watchdog_loop(self, stream_id: int):
        """
        Continuous monitor covering FOUR things, not just "pid alive":
          1) process alive
          2) source health (progress advancing at all -> source is producing data)
          3) RTMP health (ffmpeg would exit/stall if the RTMP endpoint refuses data)
          4) data flow (out_time_ms strictly increasing = real audio frames muxed)
        A stalled stream (alive but frozen output) is treated the same as a
        dead one: restart, and after MAX_FAILS_BEFORE_FAILOVER consecutive
        failures, fail over to the next source in the station's list.
        """
        logger.info("Audio watchdog started for stream %s", stream_id)
        while True:
            meta = self._meta.get(stream_id)
            if not meta or not meta.get("watchdog"):
                break

            process = self.processes.get(stream_id)
            alive = process is not None and process.poll() is None

            if not alive:
                self._handle_death(stream_id, process)
                meta = self._meta.get(stream_id)
                if not meta or not meta.get("watchdog"):
                    break
                self._restart_with_backoff(stream_id)
                continue

            uptime = time.time() - meta.get("last_start", time.time())
            last_progress = meta.get("last_progress_ts", meta.get("last_start", time.time()))
            stalled = uptime >= HEALTHY_AFTER and (time.time() - last_progress) > STALL_TIMEOUT
            data_flow = bool(meta.get("data_flow"))

            if data_flow and not stalled:
                if not meta.get("healthy"):
                    logger.info("Stream %s healthy: FFmpeg output is advancing", stream_id)
                    log_stream_event(stream_id, "on_air", "تأكيد تدفق البيانات (ON AIR)")
                meta["healthy"] = True
                meta["state"] = "on_air"
                meta["fail_count"] = 0
                # A stream that is flowing again must get its restart budget back,
                # otherwise 3 recoveries across weeks kill it permanently.
                meta["restarts"] = 0
                try:
                    from core.stream_states import restart_tracker
                    restart_tracker.reset(stream_id)
                except Exception:
                    pass
            elif stalled:
                meta["healthy"] = False
                meta["state"] = "reconnecting"
                meta["last_error"] = "توقف تدفق بيانات FFmpeg — إعادة الاتصال تلقائياً"
                logger.warning("Stream %s output stalled for %.1fs", stream_id, time.time() - last_progress)
                self._kill_proc(process)
                self.processes.pop(stream_id, None)
                # A stall is a source failure like any other: count it and give
                # the failover logic a chance to switch to a backup source.
                meta["fail_count"] = meta.get("fail_count", 0) + 1
                self._maybe_failover(stream_id, meta)
                self._restart_with_backoff(stream_id)
                continue
            else:
                meta["healthy"] = False
                meta["state"] = "connecting"

            time.sleep(2)

        logger.info("Audio watchdog stopped for stream %s", stream_id)
        self._watchdogs.pop(stream_id, None)

    def _apply_relay_default(self, meta: dict) -> None:
        """حوّل كل مصادر HLS في البث إلى الريلاي المحلي عند الإنشاء."""
        headers = meta.get("extra_headers") or None

        def looks_hls(u: str) -> bool:
            low = str(u or "").lower()
            return low.startswith(("http://", "https://")) and (
                ".m3u8" in low or "hls" in low or "mpegurl" in low
            )

        st = (meta.get("source_type") or "").lower()
        primary = self._current_source(meta) or ""
        if not (looks_hls(primary) or "hls" in st or "m3u8" in st):
            return
        if meta.get("relay_mode"):
            return
        try:
            from services.hls_relay import is_relay_url
            if is_relay_url(primary):
                return  # مُغلّف بالفعل — لا تغليف مزدوج
        except Exception:
            pass
        try:
            from services.hls_relay import get_relay_url
            sources = meta.get("sources") or []
            if sources:
                meta["sources"] = [
                    get_relay_url(u, headers=headers) if looks_hls(u) else u
                    for u in sources
                ]
            elif looks_hls(primary):
                meta["source"] = get_relay_url(primary, headers=headers)
            else:
                return
            meta["relay_mode"] = True
            meta["relay_original"] = primary
            logger.info("IPTV source routed through local relay: %s", primary[:100])
        except Exception as e:
            logger.warning("relay default skipped: %s", e)

    def _try_relay_fallback(self, stream_id: int, meta: dict) -> bool:
        """حوّل مصدر HLS إلى الريلاي المحلي (مرة واحدة لكل مصدر)."""
        if meta.get("relay_mode"):
            return False
        src = self._current_source(meta) or ""
        low = src.lower()
        if not low.startswith(("http://", "https://")):
            return False
        st = (meta.get("source_type") or "").lower()
        if not (".m3u8" in low or "hls" in st or "m3u8" in st or "mpegurl" in st):
            return False
        try:
            from services.hls_relay import get_relay_url
            proxied = get_relay_url(src, headers=meta.get("extra_headers") or None)
        except Exception as e:
            logger.warning("relay start failed for stream %s: %s", stream_id, e)
            return False
        meta["relay_mode"] = True
        meta["relay_original"] = src
        sources = meta.get("sources")
        if sources:
            idx = meta.get("source_index", 0) % len(sources)
            sources[idx] = proxied
        else:
            meta["source"] = proxied
        logger.warning(
            "Stream %s: CDN blocked direct FFmpeg — switching to local relay", stream_id
        )
        return True

    def _handle_death(self, stream_id: int, process: Optional[subprocess.Popen]):
        meta = self._meta.get(stream_id)
        if not meta:
            return
        meta["healthy"] = False
        meta["state"] = "reconnecting"
        if meta.get("copy_mode"):
            # وضع النسخ فشل — المحاولة القادمة تعيد الترميز (أكثر توافقاً)
            meta["copy_failed"] = True
            meta["copy_mode"] = False
        # NOTE: no post-mortem process.stderr.read() here — the _stderr_loop
        # thread already owns that pipe and keeps feeding meta["last_error"];
        # reading it here raced and could swallow/garbage the tail.
        self.processes.pop(stream_id, None)
        meta["fail_count"] = meta.get("fail_count", 0) + 1
        log_stream_event(stream_id, "reconnecting", str(meta.get("last_error") or "process died"))
        self._maybe_failover(stream_id, meta)

    def _maybe_failover(self, stream_id: int, meta: dict):
        """After enough consecutive failures on the current source, switch to
        the next backup source configured for this stream/station."""
        sources = meta.get("sources") or []
        if len(sources) <= 1:
            return
        if meta.get("fail_count", 0) < MAX_FAILS_BEFORE_FAILOVER:
            return
        old_idx = meta.get("source_index", 0)
        new_idx = (old_idx + 1) % len(sources)
        meta["source_index"] = new_idx
        meta["fail_count"] = 0
        meta["failover_count"] = meta.get("failover_count", 0) + 1
        meta["last_error"] = f"تم التحويل تلقائياً إلى مصدر احتياطي #{new_idx + 1}"
        logger.warning(
            "Stream %s: failing over from source #%s to backup #%s",
            stream_id, old_idx + 1, new_idx + 1,
        )

    def _restart_with_backoff(self, stream_id: int):
        """Smart restart: 5s → 30s → 5min then give up (Phase 4).
        Permanent HTTP errors (403/404/401) do NOT restart forever.
        """
        meta = self._meta.get(stream_id)
        if not meta or not meta.get("watchdog"):
            return
        try:
            from core.stream_states import next_restart_delay, MAX_RESTARTS, RESTARTING, FAILED
            from core.stream_states import restart_tracker
        except Exception:
            next_restart_delay = lambda a: min(3 + a * 2, 20)
            MAX_RESTARTS = 5
            RESTARTING, FAILED = "reconnecting", "error"
            restart_tracker = None

        # Permanent client/source errors — stop immediately
        last_err = str(meta.get("last_error") or "")
        low = last_err.lower()
        permanent = any(x in low for x in (
            "403", "404", "401", "forbidden", "not found", "unauthorized",
            "invalid character", "no such file",
        ))
        # 5xx still retries a few times, but not forever
        server_err = any(x in low for x in ("500", "502", "503", "504"))
        invalid_data = "invalid data" in low or "invalid argument" in low

        restarts = meta.get("restarts", 0)

        # فشل فتح الإخراج / خيار غير مدعوم في بناء FFmpeg على السيرفر:
        # انتقل فوراً للأمر المجرّب (safe mode) وسجّل الأمر الكامل للتشخيص.
        raw_all = f"{last_err} {meta.get('last_error_raw') or ''}".lower()
        output_fail = any(x in raw_all for x in (
            "failed to set value", "matches no streams", "error parsing options",
            "error opening output", "invalid argument",
        ))
        if output_fail and not meta.get("safe_mode"):
            meta["safe_mode"] = True
            logger.warning(
                "Stream %s: switching to SAFE ffmpeg command after output error. cmd=%s",
                stream_id, " ".join(str(x) for x in (meta.get("cmd_full") or [])),
            )
        elif restarts >= 2 and not meta.get("safe_mode") and not meta.get("data_flow"):
            # فشلين متتاليين بلا أي تدفق بيانات → جرّب الأمر المجرّب أيضاً.
            meta["safe_mode"] = True
            logger.warning(
                "Stream %s: no data flow after %s restarts — trying SAFE ffmpeg command",
                stream_id, restarts,
            )
        # A CDN/IPTV endpoint can return a non-media response on one request
        # and succeed after a fresh connection. Retry boundedly before failing.
        if invalid_data and restarts < 3:
            meta["last_error"] = last_err or "FFmpeg لم يتعرف على البيانات — إعادة المحاولة باتصال جديد"
        if permanent:
            # حظر CDN لاتصال FFmpeg (403/401): جرّب الريلاي المحلي قبل الاستسلام —
            # كثير من مصادر IPTV (nrpstream/Cloudflare) تقبل Python وترفض FFmpeg.
            if self._try_relay_fallback(stream_id, meta):
                permanent = False
                meta["restarts"] = 0
                meta["last_error"] = "إعادة المحاولة عبر الريلاي المحلي لتمرير حظر المصدر"
                log_stream_event(stream_id, "relay", "تحويل التشغيل عبر الريلاي المحلي (حظر 403)")
        if permanent:
            meta["state"] = FAILED if isinstance(FAILED, str) else "error"
            meta["watchdog"] = False
            meta["last_error"] = last_err or "خطأ دائم في المصدر (403/404) — توقف إعادة التشغيل"
            log_stream_event(stream_id, "failed", meta["last_error"])
            logger.error("Stream %s: permanent source error, not restarting: %s", stream_id, last_err[:120])
            return
        if server_err and restarts >= 3:
            meta["state"] = FAILED if isinstance(FAILED, str) else "error"
            meta["watchdog"] = False
            meta["last_error"] = last_err or "خطأ خادم متكرر (5xx) — توقف"
            logger.error("Stream %s: repeated 5xx, stopping restarts", stream_id)
            return

        delay = next_restart_delay(restarts)
        if delay is None:
            meta["state"] = FAILED if isinstance(FAILED, str) else "error"
            meta["last_error"] = f"استنفدت محاولات إعادة التشغيل ({MAX_RESTARTS})"
            meta["watchdog"] = False
            logger.error("Stream %s: max restarts reached", stream_id)
            return
        meta["state"] = RESTARTING if isinstance(RESTARTING, str) else "reconnecting"
        if restart_tracker:
            restart_tracker.record_fail(stream_id, meta.get("last_error") or "stall")
        logger.info("Stream %s smart-restart in %ss (attempt %s/%s)", stream_id, delay, restarts + 1, MAX_RESTARTS)
        time.sleep(delay)
        meta = self._meta.get(stream_id)
        if not meta or not meta.get("watchdog"):
            return
        meta["restarts"] = restarts + 1
        meta["reconnect_count"] = meta.get("reconnect_count", 0) + 1
        log_stream_event(stream_id, "reconnecting", f"restart attempt {restarts + 1}/{MAX_RESTARTS}")
        pid = self._spawn(stream_id)
        if not pid:
            meta["state"] = FAILED if isinstance(FAILED, str) else "error"
            time.sleep(8)

    def start_stream(
        self,
        stream_id: int,
        source_url: str,
        rtmp_url: str,
        audio_bitrate: str = "128k",
        volume: float = 1.0,
        with_video: bool = False,
        sources: Optional[List[str]] = None,
        start_offset: float = 0.0,
        extra_headers: Optional[dict] = None,
        media_kind: str = "unknown",
        has_audio: Optional[bool] = None,
        has_video: Optional[bool] = None,
        source_type: str = "",
        probe_result: Optional[dict] = None,
        force_video_for_audio: bool = False,
        quality: str = "auto",
        source_mode: str = "auto",
        user_id: Optional[int] = None,
    ) -> Optional[int]:
        """Start one stream without stopping other active streams.

        The configured ``MAX_STREAMS`` limit applies per bot process (four in
        GitHub Actions), so a radio stream and new user-created broadcasts can
        run together. Re-starting the same stream id replaces only that id.
        """
        if not self.ensure_ffmpeg():
            return None
        with self._lock:
            if stream_id not in self.processes and len(self.processes) >= max(1, int(MAX_STREAMS or 1)):
                logger.warning("Stream limit reached (%s); refusing stream=%s", MAX_STREAMS, stream_id)
                return None
            if stream_id in self.processes:
                self._stop_stream_locked(stream_id)

            src_list = sources or [source_url]
            self._meta[stream_id] = {
                "source": source_url,
                "sources": src_list,
                "source_index": 0,
                "rtmp": rtmp_url,
                "audio_bitrate": audio_bitrate,
                "volume": volume,
                "with_video": with_video,
                "media_kind": media_kind or (probe_result or {}).get("media_kind") or "unknown",
                "has_audio": has_audio if has_audio is not None else (probe_result or {}).get("has_audio"),
                "has_video": has_video if has_video is not None else (probe_result or {}).get("has_video"),
                "source_type": source_type or (probe_result or {}).get("source_type") or "",
                "force_video_for_audio": bool(force_video_for_audio),
                "start_offset": float(start_offset or 0),
                "extra_headers": extra_headers or {},
                "watchdog": True,
                "restarts": 0,
                "fail_count": 0,
                "failover_count": 0,
                "healthy": False,
                "state": "connecting",
                "last_error": "",
                "muted": False,
                "volume_before_mute": volume,
                "codec_info": f"AAC {audio_bitrate} · 48kHz Stereo",
                "quality": quality or (probe_result or {}).get("quality") or "auto",
                "resolution": (probe_result or {}).get("quality"),
                "fps": (probe_result or {}).get("fps"),
                "audio_codec": (probe_result or {}).get("audio_codec") or (probe_result or {}).get("codec"),
                "sample_rate": (probe_result or {}).get("sample_rate") or "48kHz",
                "channels": (probe_result or {}).get("channels") or "Stereo",
                "bitrate": (probe_result or {}).get("bitrate") or audio_bitrate,
                "pid": None,
                "reconnect_count": 0,
                "source_mode": source_mode or "auto",
                "user_id": user_id,
                "video_codec": (probe_result or {}).get("video_codec")
                or (probe_result or {}).get("codec"),
            }
            # ── IPTV/HLS: مرّر المصدر عبر الريلاي المحلي من البداية ─────
            # شبكات CDN كثيرة (nrpstream/Cloudflare...) تحظر اتصال FFmpeg
            # المباشر (403) وتقبل اتصال Python — المرور عبر الريلاي يوفر
            # محاولة الفشل الأولى ويجعل التشغيل أسرع وأثبت.
            self._apply_relay_default(self._meta[stream_id])
            pid = self._spawn(stream_id)
            if not pid and not self._meta[stream_id].get("safe_mode"):
                # الأمر المتقدم فشل فوراً (خروج خلال 0.4 ث) — جرّب الأمر المجرّب
                # (safe mode) مرة واحدة قبل الاستسلام. هذا كان يضيّع الحل تماً
                # للبثوث التي تفشل من أول لحظة (لم يكن هناك watchdog بعد).
                self._meta[stream_id]["safe_mode"] = True
                logger.warning(
                    "Stream %s: first spawn failed (%s) — retrying with SAFE ffmpeg command",
                    stream_id, str(self._meta[stream_id].get("last_error") or "")[:120],
                )
                pid = self._spawn(stream_id)
            if not pid:
                self._meta.pop(stream_id, None)
                return None
            t = threading.Thread(
                target=self._watchdog_loop,
                args=(stream_id,),
                daemon=True,
                name=f"watchdog-{stream_id}",
            )
            self._watchdogs[stream_id] = t
            t.start()
            return pid

    def rtmp_in_use(self, rtmp_url: str, exclude_stream_id: Optional[int] = None) -> Optional[int]:
        """يرجع رقم بث شغّال يستخدم نفس رابط RTMP، أو None.

        تليجرام (وغيره) يسمح باتصال ingest واحد فقط لكل مفتاح بث — بثّان بنفس
        المفتاح يعني أن الثاني سيُرفض ويبدو «متوقفاً» بلا سبب واضح. نكشف ذلك
        مبكراً ونقول للمستخدم بدل فشل صامت.
        """
        target = (rtmp_url or "").strip()
        if not target:
            return None
        for sid, meta in list(self._meta.items()):
            if exclude_stream_id is not None and sid == exclude_stream_id:
                continue
            if sid not in self.processes:
                continue
            if (meta.get("rtmp") or "").strip() == target:
                return sid
        return None

    def _stop_stream_locked(self, stream_id: int) -> bool:
        meta = self._meta.get(stream_id)
        if meta:
            meta["watchdog"] = False
            meta["healthy"] = False
            meta["state"] = "stopped"
        process = self.processes.pop(stream_id, None)
        self._meta.pop(stream_id, None)
        if process:
            self._kill_proc(process)
            log_stream_event(stream_id, "stopped", "تم إيقاف البث")
            logger.info("Stopped stream %s", stream_id)
            return True
        return False

    def stop_stream(self, stream_id: int) -> bool:
        with self._lock:
            return self._stop_stream_locked(stream_id)

    def restart_stream(self, stream_id: int) -> Optional[int]:
        meta = self._meta.get(stream_id)
        if not meta:
            return None
        source, rtmp = meta["source"], meta["rtmp"]
        sources = meta.get("sources")
        br = meta.get("audio_bitrate", "128k")
        vol = meta.get("volume", 1.0)
        wv = meta.get("with_video", False)
        offset = meta.get("start_offset", 0.0)
        relay_original = meta.get("relay_original")
        relay_mode = bool(meta.get("relay_mode"))
        copy_failed = bool(meta.get("copy_failed"))
        self.stop_stream(stream_id)
        pid = self.start_stream(
            stream_id, source, rtmp, br, vol, wv,
            sources=sources, start_offset=offset,
            extra_headers=meta.get("extra_headers") or None,
            media_kind=meta.get("media_kind", "unknown"),
            has_audio=meta.get("has_audio"),
            has_video=meta.get("has_video"),
            source_type=meta.get("source_type", ""),
            force_video_for_audio=bool(meta.get("force_video_for_audio", False)),
            quality=meta.get("quality") or "auto",
            source_mode=meta.get("source_mode") or "auto",
            user_id=meta.get("user_id"),
        )
        if pid:
            m2 = self._meta.get(stream_id) or {}
            if relay_mode and m2:
                # استعد رابط الأصل الأصلي للعرض، واحتفظ بقرار النسخ الفاشل
                m2["relay_original"] = relay_original or m2.get("relay_original")
                if copy_failed:
                    m2["copy_failed"] = True
        return pid

    def set_volume(self, stream_id: int, volume: float) -> bool:
        meta = self._meta.get(stream_id)
        if not meta:
            return False
        volume = max(0.0, min(2.0, volume))
        meta["volume"] = volume
        meta["muted"] = volume <= 0.01
        return bool(self.restart_stream(stream_id))

    def volume_delta(self, stream_id: int, delta: float) -> Optional[float]:
        meta = self._meta.get(stream_id)
        if not meta:
            return None
        new_vol = max(0.0, min(2.0, meta.get("volume", 1.0) + delta))
        self.set_volume(stream_id, new_vol)
        return new_vol

    def mute(self, stream_id: int, muted: bool = True) -> bool:
        meta = self._meta.get(stream_id)
        if not meta:
            return False
        if muted:
            meta["volume_before_mute"] = meta.get("volume", 1.0)
            return self.set_volume(stream_id, 0.0)
        return self.set_volume(stream_id, meta.get("volume_before_mute", 1.0))

    def set_bitrate(self, stream_id: int, br: str) -> bool:
        meta = self._meta.get(stream_id)
        if not meta:
            return False
        meta["audio_bitrate"] = br
        return bool(self.restart_stream(stream_id))

    def is_running(self, stream_id: int) -> bool:
        process = self.processes.get(stream_id)
        if not process:
            return False
        if process.poll() is not None:
            return False
        return True

    def is_healthy(self, stream_id: int) -> bool:
        """True only when real audio data has been confirmed flowing —
        this is what should gate showing 🟢 ON AIR to the user."""
        meta = self._meta.get(stream_id)
        return bool(meta and meta.get("healthy") and self.is_running(stream_id))

    def get_state(self, stream_id: int) -> str:
        meta = self._meta.get(stream_id) or {}
        if self.is_healthy(stream_id):
            return "on_air"
        if self.is_running(stream_id):
            return meta.get("state") or "connecting"
        if meta.get("state") in ("reconnecting", "error", "failed"):
            return meta["state"]
        return "stopped"

    def get_meta(self, stream_id: int) -> Dict:
        """Copy of metadata safe for UI/panels — RTMP key and header secrets
        are stripped/masked so they can never leak into Telegram or logs."""
        meta = dict(self._meta.get(stream_id) or {})
        meta.pop("rtmp", None)
        hdrs = meta.get("extra_headers")
        if isinstance(hdrs, dict):
            try:
                from services.secrets import sanitize_headers
                meta["extra_headers"] = sanitize_headers(hdrs)
            except Exception:
                meta.pop("extra_headers", None)
        return meta

    def get_pid(self, stream_id: int) -> Optional[int]:
        p = self.processes.get(stream_id)
        return p.pid if p and p.poll() is None else None

    def get_active_stream_id(self) -> Optional[int]:
        """Since only one broadcast runs at a time, this returns it (if any)."""
        for sid in self.processes.keys():
            return sid
        return None

    def cleanup_all(self):
        for sid in list(self._meta.keys()):
            if self._meta.get(sid):
                self._meta[sid]["watchdog"] = False
        for sid in list(self.processes.keys()):
            self.stop_stream(sid)
        # Never kill untracked FFmpeg processes on a shared host.
        kill_orphan_ffmpeg()


stream_manager = StreamManager()
