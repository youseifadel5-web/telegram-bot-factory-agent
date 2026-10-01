"""طلبات HTTP غير متزامنة صغيرة (aiohttp) مع هيدرات لكل مضيف وفشل ناعم.

قاعدة أساسية هنا: أي دالة بترجّع [] أو None وتسجّل تحذير بس، ولا بترمي
استثناء للخارج أبداً — عشان البوت ميقفعش لو مصدر وقع.
"""
from __future__ import annotations

import json
import logging
from typing import Any, Dict, List, Optional
from urllib.parse import urlparse

import aiohttp

from . import keys

logger = logging.getLogger(__name__)

# مدة الانتظار الافتراضية لكل طلب (ثواني)
DEFAULT_TIMEOUT = 15.0


def _merge(base: Optional[dict], extra: Optional[dict]) -> Dict[str, str]:
    out: Dict[str, str] = {}
    for src in (base, extra):
        if not src:
            continue
        for k, v in src.items():
            if v is None:
                continue
            out[str(k)] = str(v)
    return out


def headers_for(url: str, host_key: Optional[str] = None, extra: Optional[dict] = None) -> Dict[str, str]:
    """يختار حزمة الهيدرات المناسبة للمضيف، مع إمكانية تمرير هيدرات إضافية."""
    base: Optional[dict] = None
    if host_key:
        base = keys.HOST_HEADERS.get(host_key)
    if base is None:
        host = (urlparse(url).netloc or "").lower()
        # مطابقة الجزء الأخير من النطاق (مثال: www.fashd.com → fashd.com)
        for key_name, hdrs in keys.HOST_HEADERS.items():
            if key_name in host:
                base = hdrs
                break
    if base is None:
        base = keys.GENERAL_HEADERS
    return _merge(base, extra)


async def get_text(
    url: str,
    *,
    headers: Optional[dict] = None,
    params: Optional[dict] = None,
    host_key: Optional[str] = None,
    timeout: float = DEFAULT_TIMEOUT,
) -> Optional[str]:
    """GET ويرجّع نص الرد، أو None لو فشل الطلب."""
    hdrs = headers_for(url, host_key, headers)
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(
                url, headers=hdrs, params=params or {},
                timeout=aiohttp.ClientTimeout(total=timeout),
            ) as resp:
                if resp.status >= 400:
                    logger.warning("GET %s → HTTP %s", url, resp.status)
                    return None
                return await resp.text(errors="ignore")
    except Exception as exc:  # فشل ناعم: أي خطأ شبكة يترجم لـ None
        logger.warning("GET %s failed: %s", url, exc)
        return None


async def get_json(
    url: str,
    *,
    headers: Optional[dict] = None,
    params: Optional[dict] = None,
    host_key: Optional[str] = None,
    timeout: float = DEFAULT_TIMEOUT,
) -> Any:
    """GET ويرجّع JSON مفكوك، أو None لو فشل الطلب أو الرد مش JSON."""
    text = await get_text(url, headers=headers, params=params, host_key=host_key, timeout=timeout)
    if not text:
        return None
    try:
        return json.loads(text)
    except Exception:
        logger.warning("GET %s → غير JSON", url)
        return None


async def post_form(
    url: str,
    data: Dict[str, Any],
    *,
    headers: Optional[dict] = None,
    host_key: Optional[str] = None,
    timeout: float = DEFAULT_TIMEOUT,
) -> Optional[str]:
    """POST بجسم form-urlencoded ويرجّع النص، أو None لو فشل."""
    hdrs = headers_for(url, host_key, headers)
    hdrs.setdefault("Content-Type", "application/x-www-form-urlencoded")
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(
                url, data=data, headers=hdrs,
                timeout=aiohttp.ClientTimeout(total=timeout),
            ) as resp:
                if resp.status >= 400:
                    logger.warning("POST %s → HTTP %s", url, resp.status)
                    return None
                return await resp.text(errors="ignore")
    except Exception as exc:
        logger.warning("POST %s failed: %s", url, exc)
        return None


async def get_bytes(
    url: str,
    *,
    headers: Optional[dict] = None,
    host_key: Optional[str] = None,
    timeout: float = DEFAULT_TIMEOUT,
) -> Optional[bytes]:
    """GET ويرجّع البايتات الخام، أو None لو فشل."""
    hdrs = headers_for(url, host_key, headers)
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(
                url, headers=hdrs, timeout=aiohttp.ClientTimeout(total=timeout)
            ) as resp:
                if resp.status >= 400:
                    logger.warning("GET(bytes) %s → HTTP %s", url, resp.status)
                    return None
                return await resp.read()
    except Exception as exc:
        logger.warning("GET(bytes) %s failed: %s", url, exc)
        return None


def as_list(payload: Any) -> List[dict]:
    """تطبيع ردود القوائم: قائمة مباشرة أو {data|results|items: [...]}."""
    if isinstance(payload, list):
        return [x for x in payload if isinstance(x, dict)]
    if isinstance(payload, dict):
        for key in ("data", "results", "items"):
            value = payload.get(key)
            if isinstance(value, list):
                return [x for x in value if isinstance(x, dict)]
    return []
