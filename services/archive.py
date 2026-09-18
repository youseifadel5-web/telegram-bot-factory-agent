"""Smart video archive: finite HLS/video → temp MP4 → Telegram channel → file_id.

- Never keeps files on disk after upload.
- Deduplicates by source_hash so the same video is not converted twice.
- Only archives "complete" videos (probe has real duration within limits).
"""
from __future__ import annotations

import asyncio
import hashlib
import logging
import os
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

logger = logging.getLogger(__name__)

ROOT = Path(__file__).resolve().parent.parent
LOCAL_FFMPEG = ROOT / "bin" / "ffmpeg"


def _ffmpeg_bin() -> str:
    if LOCAL_FFMPEG.exists() and os.access(LOCAL_FFMPEG, os.X_OK):
        return str(LOCAL_FFMPEG)
    which = shutil.which("ffmpeg")
    return which or "ffmpeg"


def source_hash(url: str) -> str:
    """Stable hash for dedup (strip query noise where safe)."""
    u = (url or "").strip()
    # keep essential query for signed URLs but normalize whitespace
    return hashlib.sha256(u.encode("utf-8")).hexdigest()[:40]


def probe_duration(url: str, timeout: int = 25) -> Optional[float]:
    """Return duration in seconds if media is finite, else None (live/unknown)."""
    ff = _ffmpeg_bin()
    # use ffprobe if available next to ffmpeg
    probe = ff.replace("ffmpeg", "ffprobe") if "ffmpeg" in ff else "ffprobe"
    if not shutil.which(probe) and not Path(probe).exists():
        probe = "ffprobe"
    cmd = [
        probe, "-v", "error",
        "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1",
        "-user_agent", "Mozilla/5.0",
        url,
    ]
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        out = (r.stdout or "").strip()
        if not out or out.lower() in ("n/a", "nan"):
            return None
        dur = float(out)
        if dur <= 0 or dur != dur:  # NaN
            return None
        return dur
    except Exception as e:
        logger.info("probe_duration failed: %s", e)
        return None


def is_archivable(
    url: str,
    duration_sec: Optional[float] = None,
    min_sec: float = 60,
    max_sec: float = 14400,
) -> Tuple[bool, Optional[float], str]:
    """Decide if source is a complete VOD (movie/episode), not live."""
    url_l = (url or "").lower()
    # obvious live patterns — skip auto
    live_hints = ("/live/", "livestream", "mode=live", "type=live")
    if any(h in url_l for h in live_hints) and "movie" not in url_l and "vod" not in url_l:
        return False, None, "يبدو بثاً مباشراً (live)"

    dur = duration_sec if duration_sec is not None else probe_duration(url)
    if dur is None:
        return False, None, "لا توجد مدة معروفة (قد يكون live أو غير قابل للقراءة)"
    if dur < min_sec:
        return False, dur, f"قصير جداً ({int(dur)}ث)"
    if dur > max_sec:
        return False, dur, f"طويل جداً ({int(dur/60)}د) — غالباً live"
    return True, dur, "ok"


def convert_hls_to_mp4(
    url: str,
    out_path: str,
    quality: str = "720",
    timeout: int = 7200,
) -> Dict[str, Any]:
    """
    Convert HLS/HTTP media to MP4 on disk (caller must delete file).
    quality: 480 | 720 | 1080 | copy
    """
    try:
        from services.security.ssrf import assert_safe_url
        from services.source_probe import clean_url, sanitize_url_for_ffmpeg
        url = sanitize_url_for_ffmpeg(clean_url(url))
        if url.startswith(("http://", "https://")):
            assert_safe_url(url)
    except ValueError as e:
        return {"ok": False, "error": f"رابط مرفوض: {e}"}
    except Exception:
        pass

    ff = _ffmpeg_bin()
    # Even dimensions to avoid encoder failures on odd-width sources
    scale_map = {
        "480": "scale=-2:480,scale=trunc(iw/2)*2:trunc(ih/2)*2",
        "720": "scale=-2:720,scale=trunc(iw/2)*2:trunc(ih/2)*2",
        "1080": "scale=-2:1080,scale=trunc(iw/2)*2:trunc(ih/2)*2",
    }
    cmd = [
        ff, "-y",
        "-hide_banner",
        "-loglevel", "error",
        "-user_agent", "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "-rw_timeout", "30000000",
        "-reconnect", "1",
        "-reconnect_streamed", "1",
        "-reconnect_at_eof", "1",
        "-reconnect_delay_max", "10",
        "-i", url,
        "-c:a", "aac", "-b:a", "128k", "-ar", "48000", "-ac", "2",
        "-movflags", "+faststart",
    ]
    if quality == "copy":
        cmd.extend(["-c:v", "copy"])
    else:
        vf = scale_map.get(str(quality), scale_map["720"])
        cmd.extend([
            "-c:v", "libx264",
            "-preset", "veryfast",
            "-crf", "23",
            "-pix_fmt", "yuv420p",
            "-vf", vf,
        ])
    cmd.append(out_path)

    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        if r.returncode != 0 or not os.path.isfile(out_path) or os.path.getsize(out_path) < 1000:
            err = (r.stderr or r.stdout or "ffmpeg failed")[:500]
            # Retry once without reconnect flags if the binary rejects them
            if "option" in err.lower() and "reconnect" in err.lower():
                cmd2 = [x for x in cmd if not str(x).startswith("reconnect") and x not in ("1", "10")]
                # simpler rebuild without reconnect
                cmd2 = [
                    ff, "-y", "-hide_banner", "-loglevel", "error",
                    "-user_agent", "Mozilla/5.0",
                    "-i", url,
                    "-c:a", "aac", "-b:a", "128k",
                    "-movflags", "+faststart",
                ]
                if quality == "copy":
                    cmd2.extend(["-c:v", "copy"])
                else:
                    cmd2.extend(["-c:v", "libx264", "-preset", "veryfast", "-crf", "23",
                                 "-pix_fmt", "yuv420p", "-vf", scale_map.get(str(quality), scale_map["720"])])
                cmd2.append(out_path)
                r = subprocess.run(cmd2, capture_output=True, text=True, timeout=timeout)
                if r.returncode != 0 or not os.path.isfile(out_path) or os.path.getsize(out_path) < 1000:
                    return {"ok": False, "error": (r.stderr or r.stdout or err)[:500]}
            else:
                return {"ok": False, "error": err}
        return {"ok": True, "path": out_path, "size": os.path.getsize(out_path)}
    except subprocess.TimeoutExpired:
        return {"ok": False, "error": "انتهت مهلة التحويل"}
    except Exception as e:
        return {"ok": False, "error": str(e)}


async def archive_url_to_channel(
    bot,
    *,
    url: str,
    title: str,
    channel_id: int,
    uploaded_by: int = None,
    quality: str = "720",
    min_sec: float = 60,
    max_sec: float = 14400,
    force: bool = False,
) -> Dict[str, Any]:
    """
    Full pipeline:
    1) dedup by hash
    2) probe duration (skip live unless force)
    3) convert to temp MP4
    4) upload to channel
    5) save file_id in DB
    6) delete temp file
    """
    from database import db
    from config import ARCHIVE_CHANNEL_ID

    ch = channel_id or ARCHIVE_CHANNEL_ID
    if not ch:
        return {"ok": False, "error": "ARCHIVE_CHANNEL_ID غير مضبوط"}

    h = source_hash(url)
    existing = await db.find_archive_by_hash(h)
    if existing and existing.get("file_id"):
        return {
            "ok": True,
            "cached": True,
            "archive": existing,
            "message": "موجود مسبقاً في الأرشيف — لن يُحوَّل مرة أخرى",
        }

    ok, dur, reason = is_archivable(url, min_sec=min_sec, max_sec=max_sec)
    if not ok and not force:
        return {"ok": False, "error": f"غير قابل للأرشفة: {reason}", "duration": dur}

    tmp_dir = tempfile.mkdtemp(prefix="arch_")
    out_path = os.path.join(tmp_dir, "video.mp4")
    try:
        # convert in thread pool (blocking ffmpeg)
        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(
            None, lambda: convert_hls_to_mp4(url, out_path, quality=quality)
        )
        if not result.get("ok"):
            return {"ok": False, "error": result.get("error") or "فشل التحويل"}

        caption = (
            f"🎬 {title}\n"
            f"⏱ المدة: {int(dur or 0) // 60} د\n"
            f"📺 الجودة: {quality}p\n"
            f"#archive"
        )
        with open(out_path, "rb") as f:
            msg = await bot.send_video(
                chat_id=ch,
                video=f,
                caption=caption[:1024],
                supports_streaming=True,
                read_timeout=300,
                write_timeout=300,
                connect_timeout=60,
            )

        video = msg.video or msg.document
        if not video:
            return {"ok": False, "error": "رفع للقناة نجح لكن بدون file_id"}

        file_id = video.file_id
        file_unique = getattr(video, "file_unique_id", None)
        size = getattr(video, "file_size", None) or result.get("size")

        aid = await db.add_archive(
            title=title or "فيديو",
            source_url=url,
            source_hash=h,
            duration_sec=float(dur or 0),
            quality=f"{quality}p",
            file_id=file_id,
            file_unique_id=file_unique,
            message_id=msg.message_id,
            channel_id=ch,
            size_bytes=size,
            uploaded_by=uploaded_by,
        )
        arch = await db.get_archive(aid)
        return {"ok": True, "cached": False, "archive": arch, "message": "تم الأرشفة بنجاح"}
    except Exception as e:
        logger.exception("archive_url_to_channel")
        return {"ok": False, "error": str(e)}
    finally:
        try:
            shutil.rmtree(tmp_dir, ignore_errors=True)
        except Exception:
            pass


async def send_archive_to_user(bot, chat_id: int, archive: Dict) -> bool:
    """Send archived video by file_id (no re-download)."""
    file_id = archive.get("file_id")
    if not file_id:
        return False
    title = archive.get("title") or "فيديو"
    dur = archive.get("duration_sec") or 0
    q = archive.get("quality") or ""
    caption = f"🎬 {title}\n⏱ {int(dur)//60} د · {q}"
    try:
        await bot.send_video(
            chat_id=chat_id,
            video=file_id,
            caption=caption[:1024],
            supports_streaming=True,
        )
        return True
    except Exception as e:
        logger.warning("send_archive failed, try document: %s", e)
        try:
            await bot.send_document(chat_id=chat_id, document=file_id, caption=caption[:1024])
            return True
        except Exception as e2:
            logger.error("send_archive document failed: %s", e2)
            return False
