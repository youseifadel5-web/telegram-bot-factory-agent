"""Central secret masking and error sanitization utilities.

Every log line, user-facing diagnostic, statistic panel and stored error must
pass through here before being shown or persisted. Never log:
BOT_TOKEN, API_HASH, RTMP keys, Authorization/Cookie headers, signed URLs.
"""
from __future__ import annotations

import re
from typing import Any, Dict, Iterable, List, Optional
from urllib.parse import parse_qs, urlencode, urlparse, urlunparse

_SECRET_ENV_KEYS = (
    "BOT_TOKEN", "TELEGRAM_BOT_TOKEN", "API_HASH", "API_ID", "OPENAI_API_KEY",
    "GEMINI_API_KEY", "DEEPSEEK_API_KEY", "OPENROUTER_API_KEY", "XAI_API_KEY",
    "GROK_API_KEY", "RTMP_ENCRYPTION_KEY", "R2_ACCESS_KEY_ID",
    "R2_SECRET_ACCESS_KEY", "R2_ENDPOINT", "CF_API_TOKEN", "TMDB_API_KEY",
)

_QUERY_SECRET_KEYS = re.compile(
    r"^(token|key|signature|sig|auth|authorization|hdnea|hmac|st|wssecret|wstime|policy|sk|password|passwd|pwd)$",
    re.I,
)

_HEADER_SECRET_KEYS = ("authorization", "cookie", "x-api-key", "proxy-authorization")


def mask_secret(value: Optional[str], keep: int = 4) -> str:
    v = str(value or "")
    if not v:
        return ""
    if len(v) <= keep:
        return "*" * len(v)
    return v[:keep] + "…" + "*" * 6


def sanitize_url(url: str) -> str:
    """Mask query-string secrets (token/signature/...) in a URL for display."""
    u = str(url or "")
    if not u:
        return u
    try:
        parsed = urlparse(u)
        qs = parse_qs(parsed.query, keep_blank_values=True)
        cleaned = []
        for k, vals in qs.items():
            if _QUERY_SECRET_KEYS.match(k):
                cleaned.append((k, "***"))
            else:
                cleaned.append((k, vals[0] if isinstance(vals, list) and vals else vals))
        return urlunparse((
            parsed.scheme, parsed.netloc, parsed.path, parsed.params,
            urlencode(cleaned), parsed.fragment,
        ))
    except Exception:
        return "***"


def sanitize_headers(headers: Optional[Dict[str, Any]]) -> Dict[str, str]:
    out: Dict[str, str] = {}
    for k, v in (headers or {}).items():
        kl = str(k).lower()
        if any(s in kl for s in _HEADER_SECRET_KEYS):
            out[str(k)] = "***"
        else:
            out[str(k)] = str(v)
    return out


def sanitize_command(cmd: Any) -> str:
    """Render an FFmpeg command safely: mask RTMP keys and header secrets."""
    if isinstance(cmd, (list, tuple)):
        text = " ".join(str(x) for x in cmd)
    else:
        text = str(cmd or "")
    return _mask_rtmp_and_secrets(text)


def _mask_rtmp_and_secrets(text: str) -> str:
    # rtmp(s)://host/path/KEY → rtmp(s)://host/path/***
    text = re.sub(
        r"(rtmps?://[^\s/]+/[^\s/]+/)\S+",
        r"\1***",
        text,
        flags=re.I,
    )
    # long tokens embedded anywhere
    text = re.sub(r"\b([A-Za-z0-9_-]{40,})\b", r"\1***", text)
    return text


def _safe_error_text(error: Any) -> str:
    """Central sanitizer for any exception text destined to users or logs."""
    text = str(error or "")
    import os

    for key in _SECRET_ENV_KEYS:
        val = os.getenv(key, "").strip()
        if val and len(val) >= 6 and val in text:
            text = text.replace(val, "***")
    text = _mask_rtmp_and_secrets(text)
    # bot token shape: 123456789:AA... → masked
    text = re.sub(r"\b\d{6,12}:[A-Za-z0-9_-]{20,}\b", "***BOT_TOKEN***", text)
    # signed query params
    text = re.sub(
        r"(\?|&)(token|signature|sig|auth|hdnea|hmac|key)=[^&\s]+",
        r"\1\2=***",
        text,
        flags=re.I,
    )
    # local filesystem paths
    text = re.sub(r"(/home/\S+|/root/\S+|/Users/\S+)", "***", text)
    return text.strip()


def _diagnose_ffmpeg_error(raw_line: str) -> Dict[str, str]:
    """Classify raw FFmpeg stderr → {error, reason, solution} (Arabic UI)."""
    line = str(raw_line or "")
    low = line.lower()
    table: List[tuple] = [
        (("authentication", "auth failed", "Unauthorized", "401"), "مصادقة RTMP فشلت", "تحقق من مفتاح البث وسيرفر RTMP"),
        (("403", "forbidden"), "الوصول مرفوض (403)", "المصدر يحتاج Referer/User-Agent مناسب أو رابط منتهي"),
        (("404", "not found"), "الرابط غير موجود (404)", "تأكد أن الرابط يعمل في المتصفح"),
        (("m3u8", "playlist", "invalid data"), "ملف M3U8 غير صالح أو بيانات تالفة", "جرّب رابط HLS آخر أو أعد نسخ الرابط"),
        (("timed out", "timeout"), "انتهت مهلة الاتصال", "المصدر بطيء أو محجوب — جرّب لاحقاً"),
        (("connection refused", "refused"), "رفض الاتصال", "السيرفر المصدر غير متاح"),
        (("broken pipe", "connection reset"), "انقطع اتصال RTMP", "تحقق من مفتاح البث واستقرار الشبكة"),
        (("unknown encoder", "encoder not found", "error while opening encoder"), "مُرمّز الفيديو غير متوفر في FFmpeg", "استخدم بناء FFmpeg كامل مع libx264"),
        (("option not found", "unrecognized option"), "إصدار FFmpeg لا يدعم أحد الخيارات", "حدّث FFmpeg أو استخدم بناء static حديث"),
        (("invalid url", "invalid character"), "رموز غير صالحة في الرابط", "أعد نسخ الرابط كما هو من المصدر"),
        (("end of file", "input/output error"), "انقطع المصدر فجأة", "سيُعاد الاتصال تلقائياً إن توفر مصدر بديل"),
        (("no such file",), "ملف محلي غير موجود", "تأكد من مسار الملف"),
        (("address already in use",), "منفذ مستخدم مسبقاً", "أوقف بثاً آخر أو غيّر المنفذ"),
        (("500", "502", "503", "504", "server returned 5"), "خطأ خادم المصدر (5XX)", "السيرفر المصدر معطل مؤقتاً — جرّب رابطاً بديلاً"),
    ]
    for needles, error, solution in table:
        for n in needles:
            if str(n).lower() in low:
                return {"error": error, "reason": line[:220], "solution": solution}
    return {"error": "فشل FFmpeg", "reason": line[:220], "solution": "راجع سجل البث لتفاصيل الخطأ"}


def _record_error(meta: dict, raw_line: str) -> str:
    """Store a diagnosed error into stream meta (masked). Returns the message."""
    diag = _diagnose_ffmpeg_error(raw_line)
    msg = f"{diag['error']} — {diag['solution']}"
    meta["last_error"] = _safe_error_text(msg)
    meta["last_error_raw"] = _safe_error_text(diag.get("reason") or "")[:300]
    return meta["last_error"]


def _validate_rtmp_url(url: str) -> tuple:
    """Return (ok, normalized_or_error) — strict RTMP(S) publish URL check."""
    u = str(url or "").strip()
    if not u:
        return False, "الرابط فارغ"
    low = u.lower()
    if not (low.startswith("rtmp://") or low.startswith("rtmps://")):
        return False, "يجب أن يبدأ الرابط بـ rtmp:// أو rtmps://"
    if " " in u or "\n" in u or "\r" in u:
        return False, "الرابط يحتوي مسافات غير صالحة"
    for bad in (";", "|", "&", "`", "$("):
        if bad in u:
            return False, "رموز غير مسموحة في الرابط"
    return True, u
