"""Probe media sources before starting a stream — clean URL, detect A/V, clear UI."""
from __future__ import annotations

import json
import logging
import re
import shutil
import subprocess
from typing import Any, Dict, Optional, Tuple
from urllib.parse import urlparse, quote, unquote, urlunparse

from services.url_normalizer import (
    clean_url,
    sanitize_url_for_ffmpeg,
    extract_wrapped_url,
)

logger = logging.getLogger(__name__)

# NOTE: clean_url / sanitize_url_for_ffmpeg now live in services/url_normalizer.py
# (the single URL-truth layer) and are re-exported here for backward compatibility.
# All legacy `from services.source_probe import clean_url` imports keep working.



def sniff_remote_content(url: str, headers: Optional[Dict[str, str]] = None, timeout: int = 8) -> Dict[str, Any]:
    """Lightweight content sniff for misleading live URLs (.css/.php/etc.).
    Only reads a small prefix and never treats the result as full media validation.
    """
    if not url.startswith(("http://", "https://")):
        return {}
    try:
        import urllib.request
        req_headers = {
            "User-Agent": "Mozilla/5.0 (Linux; Android 15) AppleWebKit/537.36 Chrome/131.0 Mobile Safari/537.36",
            "Accept": "*/*",
            "Accept-Encoding": "identity",
        }
        if headers:
            req_headers.update({str(k): str(v) for k, v in headers.items()})
        req = urllib.request.Request(url, headers=req_headers, method="GET")
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read(16384)
            ctype = str(resp.headers.get("Content-Type") or "").lower()
            final_url = str(getattr(resp, "url", url) or url)
        sample = raw.decode("utf-8", errors="ignore").lstrip("\ufeff \r\n\t")
        is_hls = sample.startswith("#EXTM3U") or "#EXT-X-" in sample[:16000]
        is_audio = ctype.startswith("audio/") or any(x in ctype for x in ("mpegurl", "aac", "mp3"))
        return {"content_type": ctype, "is_hls": is_hls, "is_audio": is_audio, "final_url": final_url}
    except Exception as e:
        logger.debug("content sniff failed: %s", e)
        return {}

def detect_source_type(url: str) -> str:
    u = (url or "").lower().split("?")[0]
    if u.endswith(".m3u8") or "/hls" in u or "m3u8" in u:
        return "M3U8 / HLS"
    if u.endswith(".m3u"):
        return "M3U / IPTV"
    if u.endswith(".mp4") or ".mp4" in u:
        return "MP4"
    if u.endswith((".mp3", ".aac", ".m4a", ".ogg", ".flac", ".wav")):
        return "MP3 / Audio"
    if any(h in u for h in ("qurango", "radiojar", "zeno.fm", "radioca.st", "mp3quran", "radio")):
        return "Radio / Audio Stream"
    if "drive.google" in u or "docs.google" in u:
        return "Google Drive"
    if u.startswith(("rtmp://", "rtmps://")):
        return "RTMP"
    if any(x in u for x in ("/live/", "playlist", "xtream", "xui")):
        return "IPTV / Live"
    return "HTTP Stream"


def detect_media_kind(url: str, probe: Optional[Dict[str, Any]] = None) -> str:
    """Return 'video' or 'audio' for stream mode selection."""
    if probe:
        if probe.get("has_video") and not probe.get("has_audio"):
            return "video"
        if probe.get("has_audio") and not probe.get("has_video"):
            return "audio"
        if probe.get("has_video"):
            return "video"
        if probe.get("has_audio"):
            return "audio"
    u = (url or "").lower()
    audio_ext = (".mp3", ".aac", ".m4a", ".ogg", ".flac", ".wav", ".opus")
    if any(u.split("?")[0].endswith(e) for e in audio_ext):
        return "audio"
    if any(h in u for h in (
        "qurango", "radiojar", "zeno.fm", "radioca.st", "mp3quran", "/radio", "audio",
        "tarat.com", "stream.radio", "radiostream", "icecast", "shoutcast",
        "nogoum", "nrj", "mixfm", "9090",
    )):
        return "audio"
    return "video"


def _human_size(n: Any) -> str:
    try:
        n = int(n)
    except Exception:
        return "—"
    if n <= 0:
        return "—"
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024:
            return f"{n:.1f} {unit}" if unit != "B" else f"{n} B"
        n /= 1024
    return f"{n:.1f} TB"


def _human_duration(seconds: Any) -> str:
    try:
        s = float(seconds)
    except Exception:
        return "—"
    if s <= 0 or s > 86400 * 30:
        return "مباشر / غير محدد" if s <= 0 else "—"
    h = int(s // 3600)
    m = int((s % 3600) // 60)
    sec = int(s % 60)
    if h:
        return f"{h:02d}:{m:02d}:{sec:02d}"
    return f"{m:02d}:{sec:02d}"


def _ffmpeg_bin() -> Optional[str]:
    try:
        from services.stream import stream_manager
        stream_manager.ensure_ffmpeg()
        return stream_manager.ffmpeg or shutil.which("ffmpeg")
    except Exception:
        return shutil.which("ffmpeg")


def _supports_ffmpeg_option(ffmpeg: Optional[str], option: str) -> bool:
    if not ffmpeg:
        return False
    try:
        from services.stream import _ffmpeg_supports_option
        return _ffmpeg_supports_option(ffmpeg, option)
    except Exception:
        return False


def _fetch_master_variants(url: str, headers: Optional[Dict[str, str]] = None, timeout: int = 8) -> Dict[str, Any]:
    """Fetch a (small) HLS playlist and parse master variants. Sync, bounded."""
    try:
        from services.media.hls_detector import parse_m3u8_text
    except Exception:
        return {}
    if not url.lower().startswith(("http://", "https://")):
        return {}
    try:
        import urllib.request
        req_headers = {
            "User-Agent": "Mozilla/5.0 (Linux; Android 15) AppleWebKit/537.36 Chrome/131.0 Mobile Safari/537.36",
            "Accept": "*/*",
            "Accept-Encoding": "identity",
        }
        if headers:
            req_headers.update({str(k): str(v) for k, v in headers.items() if k.lower() != "accept-encoding"})
        req = urllib.request.Request(url, headers=req_headers, method="GET")
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read(512 * 1024)
            final_url = str(getattr(resp, "url", url) or url)
        text = raw.decode("utf-8", errors="ignore")
        if not text.lstrip().startswith("#EXTM3U"):
            return {}
        info = parse_m3u8_text(text, base_url=final_url)
        variants = []
        for v in sorted(info.variants, key=lambda x: x.bandwidth):
            variants.append({
                "quality": v.quality_label or (f"{v.height}p" if v.height else ""),
                "width": v.width,
                "height": v.height,
                "bandwidth": v.bandwidth,
                "fps": v.frame_rate or None,
                "codecs": v.codecs or "",
                "url": v.uri,
            })
        return {"is_master": info.is_master, "variants": variants}
    except Exception as e:
        logger.debug("_fetch_master_variants: %s", e)
        return {}


def probe_source(
    url: str,
    timeout: int = 35,
    headers: Optional[Dict[str, str]] = None,
) -> Dict[str, Any]:
    """
    Returns dict with ok, has_audio, has_video, media_kind, source_type,
    duration, size, quality, format, codec, bitrate, cleaned_url, error, solution.
    """
    result: Dict[str, Any] = {
        "ok": False,
        "error": None,
        "solution": None,
        # Unified probe schema (new) — kept alongside legacy keys
        "url": url,
        "clean_url": "",
        "media_kind": "video",
        "has_audio": False,
        "has_video": False,
        "is_hls": False,
        "is_master_playlist": False,
        "variants": [],
        "width": None,
        "height": None,
        "fps": None,
        "video_codec": None,
        "audio_codec": None,
        "bitrate": None,
        "content_type": "",
        "headers": dict(headers or {}),
        "cloudflare": False,
        # Legacy keys (must not disappear)
        "source_type": "HTTP Stream",
        "duration": None,
        "size": None,
        "quality": None,
        "format": None,
        "codec": None,
        "sample_rate": None,
        "channels": None,
        "cleaned_url": "",
        "ffmpeg_ready": bool(_ffmpeg_bin()),
        "note": None,
        "resolved_url": "",
    }

    raw = url
    try:
        # URL normalization: unwrap ?url=/?src=/... wrappers, then sanitize
        url = clean_url(url)
        url = extract_wrapped_url(url)
        url = sanitize_url_for_ffmpeg(url)
    except Exception as e:
        result["error"] = f"رابط غير صالح: {e}"
        result["solution"] = "أزل الرموز الغريبة من الرابط وأعد الإرسال"
        return result

    result["cleaned_url"] = url
    result["clean_url"] = url
    result["url"] = raw
    result["source_type"] = detect_source_type(url)

    # SSRF FIRST — a private/metadata URL must never be sniffed or probed.
    if url.startswith(("http://", "https://", "rtmp://", "rtmps://")):
        try:
            from services.security.ssrf import assert_safe_url
            assert_safe_url(url)
        except ValueError:
            result["error"] = "الرابط محظور لأسباب أمنية (SSRF)"
            result["solution"] = "استخدم رابطاً عاماً وليس عنواناً داخلياً"
            return result
        except Exception:
            pass

    # Cloudflare / R2 / Workers detection — affects header hints only,
    # it NEVER changes the FFmpeg command by itself (validation first).
    try:
        _host = urlparse(url).netloc.lower()
        result["cloudflare"] = any(
            d in _host for d in ("cloudflare", "r2.dev", "r2.cloudflarestorage.com", "workers.dev")
        )
        if result["cloudflare"] and result["source_type"] == "HTTP Stream":
            result["source_type"] = "Cloudflare / R2"
    except Exception:
        pass

    # Detect HLS/audio from content even when the URL extension is misleading.
    if url.startswith(("http://", "https://")):
        sniff = sniff_remote_content(url, headers=headers, timeout=min(8, timeout))
        result["content_type"] = sniff.get("content_type") or ""
        if sniff.get("final_url") and sniff.get("final_url") != url:
            result["resolved_url"] = sniff["final_url"]
        if sniff.get("is_hls"):
            result["source_type"] = "M3U8 / HLS"
            result["is_hls"] = True
        elif sniff.get("is_audio"):
            result["source_type"] = "Radio / Audio Stream"
            result["media_kind"] = "audio"

    # HLS master playlist variant discovery (resolutions/bandwidth/codecs).
    # Runs even when the extension is misleading — sniff already confirmed HLS.
    if result.get("is_hls") or ".m3u8" in url.lower():
        try:
            _m = _fetch_master_variants(url, headers=headers, timeout=min(8, timeout))
            if _m:
                result["is_master_playlist"] = _m.get("is_master", False)
                result["variants"] = _m.get("variants") or []
        except Exception as e:
            logger.debug("master variants: %s", e)

    if not url:
        result["error"] = "الرابط فارغ"
        result["solution"] = "أرسل رابط مصدر صحيح"
        return result

    # (second SSRF pass for URL-local paths kept below; networked URLs already validated)

    # Google Drive
    is_drive = "drive.google.com" in url.lower() or "docs.google.com" in url.lower()
    if is_drive:
        try:
            from services.gdrive import extract_file_id, direct_url, probe_drive
            fid = extract_file_id(url)
            if fid:
                info = probe_drive(fid)
                if info.get("ok") and info.get("direct_url"):
                    url = info["direct_url"]
                    result["cleaned_url"] = url
                else:
                    url = direct_url(fid)
                    result["cleaned_url"] = url
                if info.get("ok"):
                    result["ok"] = True
                    result["has_audio"] = True
                    result["has_video"] = True
                    result["format"] = info.get("content_type") or "drive"
                    result["codec"] = "drive"
                    result["size"] = info.get("size")
                    result["media_kind"] = detect_media_kind(url, result)
                    return result
        except Exception as e:
            logger.debug("drive convert: %s", e)
            result["ok"] = True
            result["has_audio"] = True
            result["has_video"] = True
            result["format"] = "drive"
            result["media_kind"] = "video"
            return result

    if url.startswith(("http://", "https://", "rtmp://", "rtmps://")):
        parsed = urlparse(url)
        if not parsed.netloc:
            result["error"] = "الرابط غير صالح (لا يوجد نطاق)"
            result["solution"] = "تأكد من كتابة الرابط كاملاً"
            return result
        try:
            from services.security.ssrf import assert_safe_url
            assert_safe_url(url)
        except ValueError as exc:
            result["error"] = "تم حظر الرابط لأسباب أمنية"
            result["solution"] = "استخدم مصدر بث عامًا يمكن الوصول إليه من الخادم"
            logger.warning("Blocked unsafe probe URL: %s", type(exc).__name__)
            return result

    ffmpeg = _ffmpeg_bin()
    result["ffmpeg_ready"] = bool(ffmpeg)
    if not ffmpeg:
        u = url.lower()
        result["ok"] = True
        result["has_audio"] = True
        result["has_video"] = any(x in u for x in (".m3u8", ".mp4", ".mkv", "/live", "video"))
        result["format"] = "unprobed"
        result["note"] = "FFmpeg غير متوفر — تم تخطي الفحص العميق"
        result["media_kind"] = detect_media_kind(url, result)
        return result

    probe = shutil.which("ffprobe") or ffmpeg
    is_ffprobe = "ffprobe" in (probe or "")

    try:
        is_http = url.startswith(("http://", "https://"))
        http_args = []
        if is_http:
            ua = "Mozilla/5.0 (Linux; Android 15) AppleWebKit/537.36 Chrome/131.0 Mobile Safari/537.36"
            if headers and headers.get("User-Agent"):
                ua = headers["User-Agent"]
            http_args = [
                "-user_agent", ua,
                "-protocol_whitelist", "file,http,https,tcp,tls,crypto",
            ]
            if headers:
                hdr_lines = []
                for k, v in headers.items():
                    if str(k).lower() in ("user-agent",):
                        continue
                    hdr_lines.append(f"{k}: {v}")
                if hdr_lines:
                    http_args += ["-headers", "\r\n".join(hdr_lines) + "\r\n"]
            if (result.get("is_hls") or ".m3u8" in url.lower() or "/hls" in url.lower()) and _supports_ffmpeg_option(probe, "allowed_extensions"):
                http_args += ["-allowed_extensions", "ALL"]

        if is_ffprobe:
            input_format_args = ["-f", "hls"] if result.get("is_hls") else []
            cmd = [
                probe, "-v", "quiet",
                *http_args,
                *input_format_args,
                "-print_format", "json",
                "-show_format", "-show_streams",
                "-analyzeduration", "10000000",
                "-probesize", "10000000",
                url,
            ]
        else:
            cmd = [
                probe, "-hide_banner", "-loglevel", "error",
                *http_args,
                "-analyzeduration", "10000000",
                "-probesize", "10000000",
                "-i", url,
                "-t", "2", "-f", "null", "-",
            ]

        proc = subprocess.run(
            cmd, capture_output=True, text=True, timeout=timeout + 5,
        )

        if is_ffprobe and proc.returncode == 0 and proc.stdout and proc.stdout.strip():
            try:
                data = json.loads(proc.stdout)
                fmt = data.get("format") or {}
                streams = data.get("streams") or []
                audio_streams = [s for s in streams if s.get("codec_type") == "audio"]
                video_streams = [s for s in streams if s.get("codec_type") == "video"]
                result["has_audio"] = len(audio_streams) > 0
                result["has_video"] = len(video_streams) > 0
                result["format"] = fmt.get("format_name")
                if fmt.get("size"):
                    try:
                        result["size"] = int(fmt["size"])
                    except Exception:
                        pass
                if video_streams:
                    v = video_streams[0]
                    result["codec"] = v.get("codec_name")
                    result["video_codec"] = v.get("codec_name")
                    fr = v.get("r_frame_rate") or v.get("avg_frame_rate")
                    if fr and "/" in str(fr):
                        try:
                            a, b = str(fr).split("/", 1)
                            result["fps"] = round(float(a) / float(b), 2) if float(b) else None
                        except Exception:
                            pass
                    w, h = v.get("width"), v.get("height")
                    if w and h:
                        result["width"], result["height"] = int(w), int(h)
                        result["quality"] = f"{w}x{h}"
                        if h >= 1080:
                            result["quality"] = f"1080p ({w}x{h})"
                        elif h >= 720:
                            result["quality"] = f"720p ({w}x{h})"
                        elif h >= 480:
                            result["quality"] = f"480p ({w}x{h})"
                if audio_streams:
                    a = audio_streams[0]
                    result["audio_codec"] = a.get("codec_name")
                    result["sample_rate"] = a.get("sample_rate")
                    result["channels"] = a.get("channels")
                    if not result["codec"]:
                        result["codec"] = a.get("codec_name")
                    br = a.get("bit_rate") or fmt.get("bit_rate")
                    if br:
                        try:
                            result["bitrate"] = f"{int(br) // 1000}k"
                        except Exception:
                            result["bitrate"] = str(br)
                dur = fmt.get("duration")
                if dur:
                    try:
                        result["duration"] = float(dur)
                    except Exception:
                        pass
                if result["has_audio"] or result["has_video"]:
                    result["ok"] = True
                else:
                    result["error"] = "لا يوجد مسار صوت أو فيديو في المصدر"
                    result["solution"] = "استخدم رابط m3u8 / فيديو / صوت صالح"
                result["media_kind"] = detect_media_kind(url, result)
                return result
            except Exception as e:
                logger.debug("ffprobe parse: %s", e)
                if ".m3u8" in url.lower():
                    result["ok"] = True
                    result["has_video"] = True
                    result["format"] = "hls"
                    result["media_kind"] = "video"
                    return result

        err = (proc.stderr or "") + (proc.stdout or "")
        err_l = err.lower()

        if proc.returncode == 0 or "stream #" in err_l or "audio" in err_l or "video" in err_l:
            result["ok"] = True
            result["has_audio"] = "audio" in err_l or "aac" in err_l or "mp3" in err_l
            result["has_video"] = "video" in err_l or "h264" in err_l or ".m3u8" in url.lower()
            result["media_kind"] = detect_media_kind(url, result)
            return result

        if ".m3u8" in url.lower() and ("403" not in err and "404" not in err):
            result["ok"] = True
            result["has_video"] = True
            result["format"] = "hls"
            result["media_kind"] = "video"
            return result

        if any(x in err for x in ("500", "502", "503", "504")) or "server returned 5" in err_l:
            result["error"] = "خطأ خادم المصدر (5XX)"
            result["solution"] = "السيرفر المصدر معطل مؤقتاً — جرّب لاحقاً أو رابط بديل"
        elif "404" in err or "not found" in err_l:
            result["error"] = "الرابط غير موجود (404)"
            result["solution"] = "تأكد أن الرابط يعمل في المتصفح"
        elif "403" in err or "forbidden" in err_l:
            result["error"] = "الوصول مرفوض (403)"
            result["solution"] = "الرابط محمي — قد يحتاج Headers / Referer"
        elif "timed out" in err_l or "timeout" in err_l:
            result["error"] = "انتهت مهلة الاتصال (Timeout)"
            result["solution"] = "المصدر بطيء أو متوقف"
        elif "invalid data" in err_l:
            result["error"] = "صيغة غير مدعومة أو تالفة"
            result["solution"] = "استخدم MP3/AAC/MP4/M3U8"
        elif "invalid character" in err_l or "invalid url" in err_l:
            result["error"] = "رموز غير صالحة في الرابط"
            result["solution"] = "تم تنظيف الرابط — أعد المحاولة أو انسخ الرابط من جديد"
        else:
            short = err.strip().split("\n")[-1][:100] if err.strip() else "غير معروف"
            if short.strip() in ("}", "{", "[]", "]", "["):
                short = "تعذر قراءة بيانات المصدر"
            u = url.lower()
            soft_hosts = (
                "qurango", "mp3quran", "radio", "stream", "live", "hls",
                "workers.dev", "cloudfront", "cdn", "m3u8",
                "dramalaly", "movie", "vod", "xtream", "xui",
                ":8080", ":25461", ":8880", "playlist", "series",
                "zeno.fm", "radiojar", "radioca.st",
            )
            soft_ext = (".m3u8", ".mp3", ".aac", ".m4a", ".mp4", ".ts", ".flv", ".mkv")
            path_only = u.split("?")[0]
            if (
                any(h in u for h in soft_hosts)
                or any(path_only.endswith(e) for e in soft_ext)
                or "/movie/" in u or "/series/" in u or "/live/" in u
            ):
                result["ok"] = True
                result["has_audio"] = True
                result["has_video"] = True
                result["format"] = "soft"
                result["media_kind"] = detect_media_kind(url, result)
                return result
            if short in ("تعذر قراءة بيانات المصدر", "غير معروف") or "json" in short.lower():
                result["ok"] = True
                result["has_audio"] = True
                result["has_video"] = True
                result["format"] = "soft-unknown"
                result["media_kind"] = detect_media_kind(url, result)
                return result
            result["error"] = f"فشل فحص المصدر: {short}"
            result["solution"] = "تحقق من الرابط"
    except subprocess.TimeoutExpired:
        if ".m3u8" in url.lower():
            result["ok"] = True
            result["has_video"] = True
            result["media_kind"] = "video"
            return result
        result["error"] = "انتهت مهلة فحص المصدر (Timeout)"
        result["solution"] = "المصدر بطيء — جرّب لاحقاً"
    except ValueError as e:
        result["error"] = f"رابط غير صالح: {e}"
        result["solution"] = "نظّف الرابط من الرموز الغريبة"
    except Exception as e:
        logger.debug("probe_source exception: %s", e)
        result["error"] = f"خطأ أثناء الفحص: {type(e).__name__}"
        result["solution"] = "أعد المحاولة أو استخدم رابطاً آخر"

    result["media_kind"] = detect_media_kind(url, result)
    return result


def format_probe_panel(probe: Dict[str, Any], source_url: str = "") -> str:
    """Rich status panel shown before streaming."""
    url = probe.get("cleaned_url") or source_url or ""
    disp = url if len(url) <= 80 else url[:70] + "…"
    kind = probe.get("media_kind") or "video"
    kind_label = "🎬 فيديو" if kind == "video" else "🎵 صوت"
    src_type = probe.get("source_type") or "—"
    size = _human_size(probe.get("size"))
    dur = _human_duration(probe.get("duration"))
    quality = probe.get("quality") or probe.get("bitrate") or "—"
    status = "🟢 يعمل" if probe.get("ok") else "🔴 لا يعمل"
    ff = "جاهز" if probe.get("ffmpeg_ready") else "غير متوفر"
    codec = probe.get("codec") or "—"
    fmt = probe.get("format") or "—"

    lines = [
        "🔍 <b>نتيجة فحص المصدر</b>",
        "━━━━━━━━━━━━",
        f"🌐 <b>الرابط:</b>\n<code>{disp}</code>",
        "",
        f"📡 <b>نوع المصدر:</b> {src_type}",
        f"🎞 <b>النوع:</b> {kind_label}",
        *([
            f"📺 <b>Master Playlist:</b> {len(probe.get('variants') or [])} جودة — "
            + " · ".join(filter(None, [str((v or {}).get('quality') or '') for v in (probe.get('variants') or [])[:5]]))
        ] if probe.get("is_master_playlist") else []),
        f"📦 <b>الحجم:</b> {size}",
        f"⏱ <b>المدة:</b> {dur}",
        f"📶 <b>الجودة:</b> {quality}",
        f"🎛 <b>الترميز:</b> {codec} · {fmt}",
        f"{status}",
        f"⚙️ <b>FFmpeg:</b> {ff}",
    ]
    if probe.get("note"):
        lines.append(f"ℹ️ {probe['note']}")
    if not probe.get("ok"):
        if probe.get("error"):
            lines.append(f"\n❌ <b>السبب:</b> {probe['error']}")
        if probe.get("solution"):
            lines.append(f"💡 <b>الحل:</b> {probe['solution']}")
    return "\n".join(lines)


def format_probe_error(probe: Dict[str, Any], source_url: str = "") -> str:
    lines = ["❌ <b>فشل فحص/تشغيل المصدر</b>\n"]
    url = probe.get("cleaned_url") or source_url or ""
    if url:
        src = url if len(url) <= 160 else url[:140] + "…"
        lines.append(f"<b>الرابط:</b>\n<code>{src}</code>\n")
    if probe.get("error"):
        lines.append(f"<b>السبب:</b>\n{probe['error']}\n")
    if probe.get("solution"):
        lines.append(f"<b>الحل:</b>\n{probe['solution']}")
    if not probe.get("error") and not probe.get("solution"):
        lines.append("تعذر تحديد السبب — جرّب رابطاً آخر.")
    return "\n".join(lines)


def parse_time_offset(text: str) -> Optional[float]:
    text = (text or "").strip()
    if not text:
        return None
    if re.fullmatch(r"\d+(\.\d+)?", text):
        return float(text)
    parts = text.split(":")
    try:
        parts = [float(p) for p in parts]
        if len(parts) == 3:
            return parts[0] * 3600 + parts[1] * 60 + parts[2]
        if len(parts) == 2:
            return parts[0] * 60 + parts[1]
        if len(parts) == 1:
            return parts[0]
    except Exception:
        return None
    return None


def looks_like_video(url: str) -> bool:
    return detect_media_kind(url) == "video"


def looks_like_audio(url: str) -> bool:
    return detect_media_kind(url) == "audio"


# --------------------------------------------------------------------------- #
# Async probe + global probe concurrency limit (MAX_PROBES / semaphore)
# --------------------------------------------------------------------------- #
import asyncio as _asyncio

_probe_semaphore: Optional["_asyncio.Semaphore"] = None


def _get_probe_semaphore():
    global _probe_semaphore
    if _probe_semaphore is None:
        try:
            from config import MAX_PROBES as _MP
            _probe_semaphore = _asyncio.Semaphore(max(1, int(_MP or 5)))
        except Exception:
            _probe_semaphore = _asyncio.Semaphore(5)
    return _probe_semaphore


async def probe_source_async(
    url: str,
    timeout: int = 35,
    headers: Optional[Dict[str, str]] = None,
    quality: str = "best",
) -> Dict[str, Any]:
    """Async probe (executor + semaphore) — never blocks the event loop."""
    async with _get_probe_semaphore():
        return await _asyncio.to_thread(probe_source, url, timeout, headers)


def resolve_source_mode(user_mode: str, probe: Optional[Dict[str, Any]] = None, url: str = "") -> str:
    """Deterministic Source Mode (video/audio/auto) resolution.

    Never a blind 'video' fallback: when the probe is inconclusive, URL
    heuristics (radio/quran hosts, audio extensions) decide.
    """
    um = str(user_mode or "auto").lower().strip()
    if um in ("video", "audio"):
        return um
    p = probe or {}
    hv, ha = p.get("has_video"), p.get("has_audio")
    if hv is True:
        return "video"
    if hv is False and ha is True:
        return "audio"
    kind = detect_media_kind(url or str(p.get("cleaned_url") or ""), p)
    return kind if kind in ("audio", "video") else "video"
