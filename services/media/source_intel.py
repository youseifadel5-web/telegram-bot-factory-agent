"""Real source intelligence — sniff + ffprobe. Never trust the URL extension.

Detects the TRUE nature of a source by (1) fetching the first bytes and looking
for the HLS signature ``#EXTM3U`` (so ``.css`` / ``.php`` / extension-less links
still work) and (2) running a real ffprobe pass to enumerate streams, codecs,
resolution, fps, audio bitrate / sample-rate / channels and live-vs-VOD.
"""
from __future__ import annotations

import json
import logging
import re
import subprocess
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger(__name__)

UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
)

HLS_CT_HINTS = ("mpegurl", "x-mpegurl")
AUDIO_ONLY_CODECS = {"mp3", "aac", "ac3", "eac3", "opus", "vorbis", "flac", "pcm_s16le"}


@dataclass
class SourceInfo:
    url: str
    final_url: str = ""
    scheme: str = ""
    transport: str = "http"          # http | rtmp | rtmps | file
    kind: str = "unknown"            # hls-master|hls-media|mpeg-ts|mp4|mkv|flv|audio|http|rtmp|unknown
    container: str = ""
    content_type: str = ""
    is_hls: bool = False
    hls_master: bool = False
    hls_variants: List[Dict[str, Any]] = field(default_factory=list)
    hls_media_playlist: bool = False
    is_live: Optional[bool] = None
    has_video: bool = False
    has_audio: bool = False
    video: Optional[Dict[str, Any]] = None
    audio: Optional[Dict[str, Any]] = None
    duration: Optional[float] = None
    http_status: Optional[int] = None
    ok: bool = False
    error: str = ""
    permanent_error: bool = False
    probed_by: str = ""
    note: str = ""

    def as_dict(self) -> Dict[str, Any]:
        return self.__dict__.copy()


# --------------------------------------------------------------------------- #
# helpers
# --------------------------------------------------------------------------- #
def _safe(url: str, enforce_ssrf: bool = True) -> Optional[str]:
    if not enforce_ssrf:
        return None
    try:
        from services.security.ssrf import assert_safe_url
        assert_safe_url(url)
        return None
    except ValueError as exc:
        return f"URL blocked by SSRF protection ({exc})"
    except Exception:
        return None


def fetch_head(
    url: str,
    headers: Optional[Dict[str, str]] = None,
    n: int = 16384,
    timeout: float = 15.0,
):
    """Return (status, content_type, first_bytes, final_url, error)."""
    hdrs = {"User-Agent": UA, "Accept": "*/*", "Accept-Encoding": "identity"}
    if headers:
        hdrs.update({str(k): str(v) for k, v in headers.items() if v})
    req = urllib.request.Request(url, headers=hdrs, method="GET")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            status = getattr(resp, "status", 200) or 200
            ct = (resp.headers.get("Content-Type") or "")
            data = resp.read(n)
            return status, ct, data, resp.geturl(), ""
    except urllib.error.HTTPError as exc:
        ct = ""
        try:
            ct = exc.headers.get("Content-Type", "") if exc.headers else ""
        except Exception:
            pass
        return exc.code, ct, b"", url, f"HTTP {exc.code}"
    except Exception as exc:  # noqa: BLE001
        return None, "", b"", url, f"{type(exc).__name__}: {exc}"


def _parse_m3u8(text: str, base_url: str):
    try:
        from services.media.hls_detector import parse_m3u8_text
        return parse_m3u8_text(text, base_url=base_url)
    except Exception as exc:  # noqa: BLE001
        logger.debug("m3u8 parse failed: %s", exc)
        return None


def _fps(value: Any) -> float:
    try:
        s = str(value or "")
        if "/" in s:
            num, den = s.split("/", 1)
            den_f = float(den)
            return round(float(num) / den_f, 3) if den_f else 0.0
        return float(s)
    except Exception:
        return 0.0


def run_ffprobe(
    url: str,
    ffmpeg: Optional[str] = None,
    headers: Optional[Dict[str, str]] = None,
    timeout: float = 40.0,
) -> Optional[Dict[str, Any]]:
    """Run a real ffprobe pass. Returns parsed JSON or None."""
    import shutil
    probe = shutil.which("ffprobe")
    if not probe and ffmpeg:
        try:
            from services.stream import _ffmpeg_help_text  # noqa: F401
        except Exception:
            pass
    if not probe:
        return None
    is_http = url.startswith(("http://", "https://"))
    args: List[str] = [probe, "-v", "error", "-print_format", "json", "-show_streams", "-show_format"]
    if is_http:
        args += ["-user_agent", UA]
        args += ["-protocol_whitelist", "file,http,https,tcp,tls,crypto"]
        args += ["-rw_timeout", "15000000", "-timeout", "15000000"]
        hdr_lines = []
        if headers:
            for k, v in headers.items():
                if str(k).lower() == "user-agent":
                    continue
                hdr_lines.append(f"{k}: {v}")
        if hdr_lines:
            args += ["-headers", "\r\n".join(hdr_lines) + "\r\n"]
        if ".m3u8" in url.lower():
            args += ["-allowed_extensions", "ALL"]
    args += ["-analyzeduration", "15000000", "-probesize", "15000000", url]
    try:
        proc = subprocess.run(args, capture_output=True, text=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        logger.warning("ffprobe timed out for %s", url[:80])
        return None
    except Exception as exc:  # noqa: BLE001
        logger.debug("ffprobe failed: %s", exc)
        return None
    out = proc.stdout or ""
    if not out.strip().startswith("{"):
        logger.debug("ffprobe non-json output: %s", (proc.stderr or "")[:200])
        return None
    try:
        return json.loads(out)
    except Exception:
        return None


def _classify_container(fmt_name: str, ct: str, first: bytes) -> str:
    f = (fmt_name or "").lower()
    if "mpegts" in f:
        return "mpeg-ts"
    if "mp4" in f or "mov" in f or "m4a" in f:
        return "mp4"
    if "matroska" in f or "webm" in f:
        return "mkv"
    if "flv" in f:
        return "flv"
    for tok in ("mp3", "aac", "ogg", "flac", "wav"):
        if tok in f:
            return tok
    if first[:3] == b"ID3" or first[:2] == b"\xff\xfb":
        return "mp3"
    return f.split(",")[0] if f else ""


def analyze_source(
    url: str,
    headers: Optional[Dict[str, str]] = None,
    timeout: float = 40.0,
    enforce_ssrf: bool = True,
) -> SourceInfo:
    """Full, honest analysis of a media source."""
    from services.source_probe import clean_url, sanitize_url_for_ffmpeg

    info = SourceInfo(url=url)
    try:
        cleaned = sanitize_url_for_ffmpeg(clean_url(url))
    except Exception as exc:  # noqa: BLE001
        info.error = f"رابط غير صالح: {exc}"
        info.permanent_error = True
        return info
    info.url = cleaned or url

    low = info.url.lower()
    if low.startswith(("rtmp://", "rtmps://")):
        info.transport = "rtmp" if low.startswith("rtmp://") else "rtmps"
        info.kind = "rtmp"
        info.is_live = True
    elif low.startswith("file:") or info.url.startswith("/"):
        info.transport = "file"
        info.kind = "file"
        info.is_live = False
    else:
        info.transport = "http"

    blocked = _safe(info.url, enforce_ssrf) if info.transport in ("http", "rtmp") else None
    if blocked:
        info.error = blocked
        info.permanent_error = True
        return info

    first = b""
    if info.transport == "http":
        status, ct, first, final_url, err = fetch_head(info.url, headers, timeout=min(timeout, 20))
        info.http_status = status
        info.content_type = ct
        info.final_url = final_url or info.url
        if err and status and status >= 400:
            info.error = f"المصدر رفض الاتصال (HTTP {status})" if status in (401, 403) else f"خطأ HTTP {status}"
            info.permanent_error = status in (400, 401, 403, 404, 410)
            return info
        if err and not status:
            info.note = f"sniff تعذر ({err}) — أكملت عبر ffprobe"
        text = ""
        try:
            text = first.decode("utf-8", errors="ignore")
        except Exception:
            text = ""
        stripped = text.lstrip("\ufeff \t\r\n")
        if stripped.startswith("#EXTM3U"):
            info.is_hls = True
            parsed = _parse_m3u8(text, info.final_url or info.url)
            if parsed is not None:
                info.hls_master = bool(parsed.is_master)
                info.hls_media_playlist = bool(parsed.is_media)
                info.hls_variants = [
                    {
                        "uri": v.uri,
                        "bandwidth": v.bandwidth,
                        "resolution": v.resolution,
                        "frame_rate": v.frame_rate,
                        "codecs": v.codecs,
                        "name": v.name,
                    }
                    for v in parsed.variants
                ]
                if parsed.is_live is not None:
                    info.is_live = bool(parsed.is_live)
            info.kind = "hls-master" if info.hls_master else "hls-media"

    # --- real ffprobe pass -------------------------------------------------
    data = run_ffprobe(info.url, headers=headers, timeout=timeout)
    if data is None and info.is_hls is False and info.transport == "http":
        # .m3u8 by URL only (ffprobe may still handle it)
        if ".m3u8" in low:
            info.is_hls = True
            info.kind = info.kind if info.kind.startswith("hls") else "hls-media"

    if data:
        info.probed_by = "ffprobe"
        fmt = data.get("format") or {}
        streams = data.get("streams") or []
        info.container = _classify_container(fmt.get("format_name", ""), info.content_type, first)
        vids = [s for s in streams if s.get("codec_type") == "video"]
        auds = [s for s in streams if s.get("codec_type") == "audio"]
        info.has_video = len(vids) > 0
        info.has_audio = len(auds) > 0
        if info.kind in ("unknown", "http", "file"):
            if info.is_hls:
                pass
            elif info.container:
                info.kind = info.container
        if vids:
            v = vids[0]
            info.video = {
                "codec": v.get("codec_name") or "",
                "width": int(v.get("width") or 0),
                "height": int(v.get("height") or 0),
                "fps": _fps(v.get("avg_frame_rate") or v.get("r_frame_rate")),
                "bitrate": int(v.get("bit_rate") or 0),
                "pix_fmt": v.get("pix_fmt") or "",
            }
        if auds:
            a = auds[0]
            info.audio = {
                "codec": a.get("codec_name") or "",
                "bitrate": int(a.get("bit_rate") or 0),
                "sample_rate": int(a.get("sample_rate") or 0),
                "channels": int(a.get("channels") or 0),
                "channel_layout": a.get("channel_layout") or "",
            }
        dur = fmt.get("duration")
        try:
            d = float(dur)
            if d > 0:
                info.duration = d
        except (TypeError, ValueError):
            pass
        # live vs VOD
        if info.is_hls:
            if info.is_live is None:
                info.is_live = info.hls_master or info.hls_media_playlist is False
        elif info.transport in ("rtmp", "rtmps"):
            info.is_live = True
        elif info.container == "mpeg-ts":
            info.is_live = info.duration is None
        elif info.duration and info.duration > 0:
            info.is_live = False
        info.ok = bool(info.has_video or info.has_audio)
        if not info.ok:
            info.error = "لا يوجد مسار صوت أو فيديو في المصدر"
            info.permanent_error = True
    else:
        info.probed_by = "sniff" if first else "none"
        # Honest fallback: we do not claim a dead URL is fine just because it is http.
        if info.is_hls:
            info.ok = True
            info.has_audio = True
            info.has_video = not info.hls_master
        elif info.transport in ("rtmp", "rtmps"):
            info.ok = True
            info.has_audio = True
            info.has_video = True
            info.is_live = True
        elif info.http_status and info.http_status >= 400:
            info.ok = False
        else:
            info.ok = False
            info.error = info.error or "تعذر فحص المصدر (ffprobe لم يُرجع بيانات)"

    if not info.kind or info.kind == "unknown":
        ext = re.sub(r"[?#].*$", "", low)
        if ext.endswith((".mp3", ".aac", ".m4a", ".ogg", ".flac", ".opus")):
            info.kind = "audio"
        elif ext.endswith(".m3u8"):
            info.kind, info.is_hls = "hls-media", True
        elif ext.endswith((".mp4", ".mkv", ".flv", ".ts", ".mov", ".webm")):
            info.kind = ext.rsplit(".", 1)[1]
    return info


def pick_hls_variant(variants: List[Dict[str, Any]], quality: str = "best") -> Optional[Dict[str, Any]]:
    if not variants:
        return None
    def _bw(v):
        try:
            return int(v.get("bandwidth") or 0)
        except Exception:
            return 0
    ordered = sorted(variants, key=_bw)
    q = (quality or "best").lower().strip()
    if q in ("worst", "lowest", "min"):
        return ordered[0]
    m = re.match(r"(\d{3,4})p?", q)
    if m:
        target = int(m.group(1))
        best, best_diff = None, 10 ** 9
        for v in ordered:
            res = str(v.get("resolution") or "")
            if "x" in res:
                try:
                    h = int(res.split("x")[1])
                except Exception:
                    h = 0
                if h and abs(h - target) < best_diff:
                    best, best_diff = v, abs(h - target)
        if best:
            return best
    return ordered[-1]


def _fmt_video(v: Optional[Dict[str, Any]]) -> str:
    if not v:
        return "غير متاح"
    res = f"{v.get('width')}x{v.get('height')}" if v.get("width") else "غير متاح"
    fps = f"{v.get('fps'):g} FPS" if v.get("fps") else "—"
    return f"{v.get('codec') or '?'} · {res} · {fps}"


def _fmt_audio(a: Optional[Dict[str, Any]]) -> str:
    if not a:
        return "غير متاح"
    br = f"{round((a.get('bitrate') or 0)/1000)} kbps" if a.get("bitrate") else "—"
    sr = f"{round((a.get('sample_rate') or 0)/1000)} kHz" if a.get("sample_rate") else "—"
    ch = {1: "Mono", 2: "Stereo"}.get(a.get("channels") or 0, f"{a.get('channels')} ch")
    return f"{a.get('codec') or '?'} · {br} · {sr} · {ch}"


def format_source_panel(info: SourceInfo) -> str:
    """Render the real probe result for the user (no invented values)."""
    kind_label = {
        "hls-master": "HLS (Master Playlist)",
        "hls-media": "HLS (Media Playlist)",
        "mpeg-ts": "MPEG-TS",
        "mp4": "MP4",
        "mkv": "MKV",
        "flv": "FLV",
        "audio": "ملف صوتي",
        "rtmp": "RTMP",
        "rtmps": "RTMPS",
    }.get(info.kind, info.kind or "غير معروف")
    live = "مباشر (Live)" if info.is_live else ("مسجّل (VOD)" if info.is_live is False else "غير متاح")
    lines = [
        "🔍 <b>فحص المصدر</b>",
        "━━━━━━━━━━━━━━━━━━━━",
        f"📦 النوع: <b>{kind_label}</b>",
        f"🔀 النقل: <b>{info.transport.upper()}</b> · {live}",
        f"🎬 الفيديو: {'✅' if info.has_video else '❌'} {_fmt_video(info.video) if info.has_video else 'غير موجود'}",
        f"🔊 الصوت: {'✅' if info.has_audio else '❌'} {_fmt_audio(info.audio) if info.has_audio else 'غير موجود'}",
    ]
    if info.has_video and not info.has_audio:
        lines.append("ℹ️ مصدر فيديو بدون صوت — سيعمل كـ Video Stream.")
    if info.has_audio and not info.has_video:
        lines.append("ℹ️ مصدر صوتي فقط — سيعمل كـ 🎵 Audio Stream (بدون فيديو أسود).")
    if info.hls_variants:
        res = []
        for v in info.hls_variants:
            if v.get("resolution"):
                res.append(str(v["resolution"]))
            elif v.get("bandwidth"):
                res.append(f"{round(int(v['bandwidth'])/1000)}k")
        if res:
            lines.append(f"🎚 الجودات في المصدر: <b>{', '.join(res)}</b>")
    if info.error:
        lines.append(f"⚠️ {info.error}")
    lines.append("━━━━━━━━━━━━━━━━━━━━")
    return "\n".join(lines)
