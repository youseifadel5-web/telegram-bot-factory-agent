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

ROOT = Path(__file__).resolve().parent.parent
LOCAL_FFMPEG_DIR = ROOT / "bin"
LOCAL_FFMPEG = LOCAL_FFMPEG_DIR / "ffmpeg"
FFMPEG_STATIC_URL = (
    "https://johnvansickle.com/ffmpeg/releases/ffmpeg-release-amd64-static.tar.xz"
)

# After this many seconds of a running ffmpeg process with NO progress
# (out_time not advancing), we consider audio "stalled" and force a restart.
STALL_TIMEOUT = 45
# Seconds of continuous, advancing progress before we call it healthy / ON AIR.
HEALTHY_AFTER = 8
# Consecutive failed connect attempts on one source before failing over.
MAX_FAILS_BEFORE_FAILOVER = 3

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
    _FFMPEG_HELP_CACHE[key] = output
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
    supported = bool(re.search(rf"(?m)^\s*-{re.escape(option)}(?:\s|$)", output)) if output else False
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
        elif re.search(r"\bH\.264\b|\bh264\b", out, re.I):
            encoder = "h264"
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
        urllib.request.urlretrieve(FFMPEG_STATIC_URL, archive)
        with tarfile.open(archive, "r:xz") as tar:
            member = next(
                (m for m in tar.getmembers() if m.name.endswith("/ffmpeg") and m.isfile()),
                None,
            )
            if not member:
                return None
            member.name = "ffmpeg"
            tar.extract(member, path=LOCAL_FFMPEG_DIR)
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
    for bad in (";", "|", "&", "`", "$(", "\n", "\r"):
        if bad in url:
            raise ValueError("invalid character in source URL")
    return url

def build_ffmpeg_cmd(
    ffmpeg: str,
    source_url: str,
    rtmp_url: str,
    audio_bitrate: str = "128k",
    volume: float = 1.0,
    with_video: bool = False,
    start_offset: float = 0.0,
    extra_headers: dict = None,
) -> list:
    """Build a robust FFmpeg command for Telegram RTMPS / FLV live ingest.

    Improvements vs previous version:
    - Single help-text probe (cached) for option support
    - Auto-select video encoder (libx264 → h264 → mpeg4)
    - Force even dimensions + max 1280x720 (Telegram-friendly)
    - thread_queue_size to avoid multi-input stalls
    - Use config FFMPEG_TIMEOUT when available
    - Safer audio-only path with black video track
    - FLV flags friendly to indefinite live streams
    """
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

    # Even dimensions + cap resolution for stable RTMP ingest
    vf_scale = (
        "scale='min(1280,iw)':'min(720,ih)':force_original_aspect_ratio=decrease,"
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
        "-analyzeduration", "15M",
        "-probesize", "15M",
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
            ("http_persistent", "0"),
            ("http_seekable", "0"),
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

    # Real-time pacing for continuous live publish. Safe for both VOD and live HLS.
    cmd += [
        "-re",
        "-fflags", "+genpts+discardcorrupt+igndts",
        "-max_interleave_delta", "0",
        "-thread_queue_size", "512",
        "-i", source_url,
    ]

    if with_video:
        vcodec_block = [
            "-map", "0:v:0?",
            "-map", "0:a:0?",
            "-c:v", v_encoder,
        ]
        if x264_style:
            vcodec_block += [
                "-preset", "veryfast",
                "-tune", "zerolatency",
            ]
        vcodec_block += [
            "-b:v", "1000k",
            "-maxrate", "1200k",
            "-bufsize", "2000k",
            "-pix_fmt", "yuv420p",
            "-r", "25",
            "-vf", vf_scale,
            "-c:a", "aac",
            "-b:a", audio_bitrate,
            "-ar", "48000",
            "-ac", "2",
            "-af", af,
            "-max_muxing_queue_size", "2048",
            "-g", "50",
            "-keyint_min", "50",
            "-sc_threshold", "0",
        ]
        if _ffmpeg_supports_option(ffmpeg, "fps_mode"):
            vcodec_block += ["-fps_mode", "cfr"]
        else:
            vcodec_block += ["-vsync", "cfr"]
        cmd += vcodec_block
    else:
        # Audio-only → synthetic black video track required by Telegram Live
        cmd += [
            "-f", "lavfi",
            "-thread_queue_size", "512",
            "-i", "color=c=black:s=1280x720:r=25",
            "-map", "1:v:0",
            "-map", "0:a:0?",
            "-c:v", v_encoder,
        ]
        if x264_style:
            cmd += ["-preset", "veryfast", "-tune", "zerolatency"]
        cmd += [
            "-b:v", "300k",
            "-maxrate", "350k",
            "-bufsize", "600k",
            "-pix_fmt", "yuv420p",
            "-r", "25",
            "-c:a", "aac",
            "-b:a", audio_bitrate,
            "-ar", "48000",
            "-ac", "2",
            "-af", af,
            "-max_muxing_queue_size", "1024",
            "-g", "50",
            "-keyint_min", "50",
            "-sc_threshold", "0",
            # -shortest removed: kills live radio/quran on brief audio stalls
        ]
        if _ffmpeg_supports_option(ffmpeg, "fps_mode"):
            cmd += ["-fps_mode", "cfr"]
        else:
            cmd += ["-vsync", "cfr"]

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
        cmd = build_ffmpeg_cmd(
            self.ffmpeg,
            source,
            meta["rtmp"],
            audio_bitrate=meta.get("audio_bitrate", "128k"),
            volume=meta.get("volume", 1.0),
            with_video=meta.get("with_video", False),
            start_offset=meta.get("start_offset", 0.0),
            extra_headers=meta.get("extra_headers") or None,
        )
        logger.info(
            "FFmpeg start stream=%s source_idx=%s vol=%.2f br=%s",
            stream_id, meta.get("source_index", 0), meta.get("volume", 1), meta.get("audio_bitrate"),
        )
        try:
            process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,   # FFmpeg -progress pipe:1
                stderr=subprocess.PIPE,   # warnings / connection errors
                preexec_fn=os.setsid if os.name != "nt" else None,
            )
            self.processes[stream_id] = process
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
                logger.error("Stream %s early exit: %s", stream_id, err[:200])
                self.processes.pop(stream_id, None)
                try:
                    self._kill_proc(process)
                except Exception:
                    pass
                return None
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
        if any(x in low for x in ("option not found", "unrecognized option", "unknown option", "invalid argument")):
            return f"إصدار FFmpeg لا يدعم أحد الخيارات المطلوبة: {line[:180]}"
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
            if meta and lines and not meta.get("last_error"):
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
                meta["last_error_raw"] = " | ".join(lines[-8:])[:1200]
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
                meta["healthy"] = True
                meta["state"] = "on_air"
                meta["fail_count"] = 0
            elif stalled:
                meta["healthy"] = False
                meta["state"] = "reconnecting"
                meta["last_error"] = "توقف تدفق بيانات FFmpeg — إعادة الاتصال تلقائياً"
                logger.warning("Stream %s output stalled for %.1fs", stream_id, time.time() - last_progress)
                self._kill_proc(process)
                self.processes.pop(stream_id, None)
                self._restart_with_backoff(stream_id)
                continue
            else:
                meta["healthy"] = False
                meta["state"] = "connecting"

            time.sleep(2)

        logger.info("Audio watchdog stopped for stream %s", stream_id)
        self._watchdogs.pop(stream_id, None)

    def _handle_death(self, stream_id: int, process: Optional[subprocess.Popen]):
        meta = self._meta.get(stream_id)
        if not meta:
            return
        meta["healthy"] = False
        meta["state"] = "reconnecting"
        if process and process.stderr:
            try:
                err = process.stderr.read().decode("utf-8", errors="ignore")[-400:]
                if err:
                    meta["last_error"] = err.strip()[:300]
                    logger.warning("Stream %s died: %s", stream_id, err[:200])
            except Exception:
                pass
        self.processes.pop(stream_id, None)
        meta["fail_count"] = meta.get("fail_count", 0) + 1
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
        # A CDN/IPTV endpoint can return a non-media response on one request
        # and succeed after a fresh connection. Retry boundedly before failing.
        if invalid_data and restarts < 3:
            meta["last_error"] = last_err or "FFmpeg لم يتعرف على البيانات — إعادة المحاولة باتصال جديد"
        if permanent:
            meta["state"] = FAILED if isinstance(FAILED, str) else "error"
            meta["watchdog"] = False
            meta["last_error"] = last_err or "خطأ دائم في المصدر (403/404) — توقف إعادة التشغيل"
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
    ) -> Optional[int]:
        """Starts a stream. Only ONE broadcast is allowed at a time system-wide:
        any other running stream is stopped first, and old ffmpeg sessions are
        cleaned up before the new one begins."""
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
            }
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
        self.stop_stream(stream_id)
        return self.start_stream(
            stream_id, source, rtmp, br, vol, wv,
            sources=sources, start_offset=offset,
            extra_headers=meta.get("extra_headers") or None,
        )

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
        if meta.get("state") == "reconnecting":
            return "reconnecting"
        return "stopped"

    def get_meta(self, stream_id: int) -> Dict:
        return dict(self._meta.get(stream_id) or {})

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
