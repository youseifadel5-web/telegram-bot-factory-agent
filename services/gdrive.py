"""Google Drive link helpers for streaming / download."""
import logging
import re
import os
import uuid
import urllib.request
import urllib.error
from pathlib import Path
from typing import Optional, Tuple, Dict
from urllib.parse import urlparse, parse_qs

logger = logging.getLogger(__name__)

ROOT = Path(__file__).resolve().parent.parent
TEMP_DIR = ROOT / "data" / "tmp"
TEMP_DIR.mkdir(parents=True, exist_ok=True)

DRIVE_PATTERNS = [
    re.compile(r"drive\.google\.com/file/d/([a-zA-Z0-9_-]+)", re.I),
    re.compile(r"drive\.google\.com/open\?id=([a-zA-Z0-9_-]+)", re.I),
    re.compile(r"id=([a-zA-Z0-9_-]{20,})", re.I),
    re.compile(r"docs\.google\.com/.*?/d/([a-zA-Z0-9_-]+)", re.I),
]

AUDIO_EXT = {".mp3", ".m4a", ".aac", ".ogg", ".wav", ".flac"}
VIDEO_EXT = {".mp4", ".mkv", ".webm", ".mov"}
SUPPORTED_EXT = AUDIO_EXT | VIDEO_EXT


def extract_file_id(url: str) -> Optional[str]:
    if not url:
        return None
    for pat in DRIVE_PATTERNS:
        m = pat.search(url)
        if m:
            return m.group(1)
    return None


def is_drive_url(url: str) -> bool:
    if not url:
        return False
    u = url.lower()
    return "drive.google.com" in u or "docs.google.com" in u


def direct_url(file_id: str) -> str:
    return f"https://drive.google.com/uc?export=download&id={file_id}"


def confirm_url(file_id: str, confirm: str) -> str:
    return (
        f"https://drive.google.com/uc?export=download&id={file_id}&confirm={confirm}"
    )


def _parse_filename_from_cd(cd: str) -> Optional[str]:
    if not cd:
        return None
    # filename="..."
    m = re.search(r'filename\*=UTF-8\'\'([^\s;]+)', cd, re.I)
    if m:
        from urllib.parse import unquote
        return unquote(m.group(1))
    m = re.search(r'filename="([^"]+)"', cd, re.I)
    if m:
        return m.group(1)
    m = re.search(r'filename=([^\s;]+)', cd, re.I)
    if m:
        return m.group(1).strip('"')
    return None


def probe_drive(file_id: str, timeout: int = 25) -> Dict:
    """
    Check availability and gather metadata without full download.
    Returns dict: ok, name, size, content_type, direct_url, error
    """
    url = direct_url(file_id)
    result = {
        "ok": False,
        "file_id": file_id,
        "name": f"drive_{file_id[:8]}",
        "size": 0,
        "content_type": "",
        "ext": "",
        "direct_url": url,
        "error": "",
    }
    try:
        req = urllib.request.Request(
            url,
            headers={
                "User-Agent": "Mozilla/5.0 (compatible; YouseifBot/1.0)",
            },
            method="GET",
        )
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            ctype = (resp.headers.get("Content-Type") or "").lower()
            result["content_type"] = ctype
            size = int(resp.headers.get("Content-Length") or 0)
            result["size"] = size
            name = _parse_filename_from_cd(resp.headers.get("Content-Disposition") or "")
            # Virus scan interstitial HTML
            if "text/html" in ctype:
                body = resp.read(64 * 1024).decode("utf-8", errors="ignore")
                # confirm token for large files
                m = re.search(r'confirm=([0-9A-Za-z_-]+)', body)
                if not m:
                    m = re.search(r'name="confirm"\s+value="([^"]+)"', body)
                if not m:
                    m = re.search(r"confirm=([0-9A-Za-z_-]+)", body)
                if m:
                    url2 = confirm_url(file_id, m.group(1))
                    result["direct_url"] = url2
                    req2 = urllib.request.Request(
                        url2,
                        headers={"User-Agent": "Mozilla/5.0 (compatible; YouseifBot/1.0)"},
                    )
                    with urllib.request.urlopen(req2, timeout=timeout) as resp2:
                        ctype = (resp2.headers.get("Content-Type") or "").lower()
                        result["content_type"] = ctype
                        result["size"] = int(resp2.headers.get("Content-Length") or 0)
                        name2 = _parse_filename_from_cd(resp2.headers.get("Content-Disposition") or "")
                        if name2:
                            name = name2
                        if "text/html" in ctype:
                            result["error"] = "الملف غير متاح للتحميل العام (قيود Google Drive)"
                            return result
                else:
                    # try to find form download
                    if "uc-download-link" in body or "download_warning" in body:
                        result["error"] = "يحتاج تأكيد تحميل — تأكد أن الملف عام"
                        return result
                    result["error"] = "رابط Drive لا يعيد ملفاً مباشراً — اجعله «أي شخص لديه الرابط»"
                    return result

            if name:
                result["name"] = name
            ext = Path(result["name"]).suffix.lower()
            result["ext"] = ext
            # MIME fallback for extension
            if not ext:
                if "audio/mpeg" in ctype or "mp3" in ctype:
                    result["ext"] = ".mp3"
                    result["name"] += ".mp3"
                elif "audio/mp4" in ctype or "m4a" in ctype:
                    result["ext"] = ".m4a"
                    result["name"] += ".m4a"
                elif "audio/aac" in ctype:
                    result["ext"] = ".aac"
                    result["name"] += ".aac"
                elif "video/mp4" in ctype:
                    result["ext"] = ".mp4"
                    result["name"] += ".mp4"

            result["ok"] = True
            return result
    except urllib.error.HTTPError as e:
        result["error"] = f"HTTP {e.code}: الملف غير متاح أو خاص"
        logger.warning("Drive probe HTTPError %s for %s", e.code, file_id)
    except Exception as e:
        result["error"] = str(e)[:150]
        logger.warning("Drive probe error: %s", e)
    return result


def download_to_temp(file_id: str, direct: str = None, max_bytes: int = 500 * 1024 * 1024) -> Tuple[Optional[str], str]:
    """
    Download Drive file to temp path. Returns (path, error).
    Limited max size for KataBump disk.
    """
    url = direct or direct_url(file_id)
    out = TEMP_DIR / f"{file_id}_{uuid.uuid4().hex[:8]}"
    try:
        req = urllib.request.Request(
            url,
            headers={"User-Agent": "Mozilla/5.0 (compatible; YouseifBot/1.0)"},
        )
        with urllib.request.urlopen(req, timeout=120) as resp:
            ctype = (resp.headers.get("Content-Type") or "").lower()
            if "text/html" in ctype:
                body = resp.read(128 * 1024)
                text = body.decode("utf-8", errors="ignore")
                m = re.search(r'confirm=([0-9A-Za-z_-]+)', text) or re.search(r'name="confirm"\s+value="([^"]+)"', text)
                if m:
                    return download_to_temp(file_id, confirm_url(file_id, m.group(1)), max_bytes)
                return None, "Google Drive أعاد صفحة HTML وليس الملف"

            name = _parse_filename_from_cd(resp.headers.get("Content-Disposition") or "")
            ext = Path(name).suffix.lower() if name else ""
            if not ext:
                if "mpeg" in ctype:
                    ext = ".mp3"
                elif "mp4" in ctype and "audio" in ctype:
                    ext = ".m4a"
                elif "mp4" in ctype:
                    ext = ".mp4"
                else:
                    ext = ".bin"
            out = out.with_suffix(ext)

            written = 0
            with open(out, "wb") as f:
                while True:
                    chunk = resp.read(256 * 1024)
                    if not chunk:
                        break
                    written += len(chunk)
                    if written > max_bytes:
                        f.close()
                        try:
                            out.unlink()
                        except Exception:
                            pass
                        return None, f"الملف أكبر من الحد المؤقت ({max_bytes // (1024*1024)}MB)"
                    f.write(chunk)

            return str(out), ""
    except Exception as e:
        logger.exception("Drive download failed")
        return None, str(e)[:150]


def cleanup_temp(path: str):
    try:
        if path and os.path.isfile(path):
            os.remove(path)
    except Exception:
        pass


def format_size(n: int) -> str:
    if not n:
        return "؟"
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024:
            return f"{n:.1f} {unit}" if unit != "B" else f"{n} B"
        n /= 1024
    return f"{n:.1f} TB"
