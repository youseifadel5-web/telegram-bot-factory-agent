"""طلبات HTTP غير متزامنة صغيرة مع هيدرات لكل مضيف وفشل ناعم.

مهم: مصادر التطبيق (حكاية/فاصل/فايربيس) بترفض اتصال aiohttp من عناوين
الداتاسنتر (GitHub Actions) لأن بصمة TLS بتاعتها مختلفة — نفس مشكلة CDN
اللي حلّيناها في البث. الحل هنا: **curl_cffi ببصمة Chrome أولًا**، ثم
aiohttp كبديل. الفشل ناعم دائمًا: أي خطأ يرجّع None/[] ويسجّل تحذيرًا.
"""
from __future__ import annotations

import asyncio
import json
import logging
from typing import Any, Dict, List, Optional
from urllib.parse import urlparse

import aiohttp

from . import keys

logger = logging.getLogger(__name__)

DEFAULT_TIMEOUT = 15.0
MAX_ATTEMPTS = 2

try:  # اختياري: لو المكتبة مش موجودة نكمل بـ aiohttp
    from curl_cffi import requests as _cffi
    _HAS_CFFI = True
except Exception:  # noqa: BLE001
    _cffi = None
    _HAS_CFFI = False


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
        for key_name, hdrs in keys.HOST_HEADERS.items():
            if key_name in host:
                base = hdrs
                break
    if base is None:
        base = keys.GENERAL_HEADERS
    return _merge(base, extra)


def _cffi_get(url: str, headers: dict, params: Optional[dict], timeout: float):
    """طلب متزامن ببصمة Chrome — يُنادى داخل خيط منفصل."""
    return _cffi.get(
        url, headers=headers, params=params or {},
        impersonate="chrome", timeout=timeout, allow_redirects=True,
    )


def _cffi_post(url: str, data: dict, headers: dict, timeout: float):
    return _cffi.post(
        url, data=data, headers=headers,
        impersonate="chrome", timeout=timeout, allow_redirects=True,
    )


async def _text_via_cffi(url, headers, params, timeout) -> Optional[str]:
    if not _HAS_CFFI:
        return None
    try:
        resp = await asyncio.to_thread(_cffi_get, url, headers, params, timeout)
    except Exception as exc:  # noqa: BLE001
        logger.warning("GET(cffi) %s failed: %s", url, exc)
        return None
    code = getattr(resp, "status_code", 200)
    if code >= 400:
        logger.warning("GET(cffi) %s → HTTP %s", url, code)
        return None
    return getattr(resp, "text", None) or ""


async def _text_via_aiohttp(url, headers, params, timeout) -> Optional[str]:
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(
                url, headers=headers, params=params or {},
                timeout=aiohttp.ClientTimeout(total=timeout),
            ) as resp:
                if resp.status >= 400:
                    logger.warning("GET %s → HTTP %s", url, resp.status)
                    return None
                return await resp.text(errors="ignore")
    except Exception as exc:  # noqa: BLE001
        logger.warning("GET %s failed: %s", url, exc)
        return None


async def get_text(
    url: str,
    *,
    headers: Optional[dict] = None,
    params: Optional[dict] = None,
    host_key: Optional[str] = None,
    timeout: float = DEFAULT_TIMEOUT,
) -> Optional[str]:
    """GET ويرجّع نص الرد، أو None لو فشل الطلب.

    الترتيب: curl_cffi (بصمة Chrome) ثم aiohttp — لأن كثير من المضيفين
    يحجبون بصمة aiohttp من عناوين مراكز البيانات.
    """
    hdrs = headers_for(url, host_key, headers)
    for attempt in range(MAX_ATTEMPTS):
        if _HAS_CFFI:
            text = await _text_via_cffi(url, hdrs, params, timeout)
            if text is not None:
                return text
        text = await _text_via_aiohttp(url, hdrs, params, timeout)
        if text is not None:
            return text
        if attempt + 1 < MAX_ATTEMPTS:
            await asyncio.sleep(0.6 * (attempt + 1))
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
    if _HAS_CFFI:
        try:
            resp = await asyncio.to_thread(_cffi_post, url, data, hdrs, timeout)
            code = getattr(resp, "status_code", 200)
            if code < 400:
                return getattr(resp, "text", None) or ""
            logger.warning("POST(cffi) %s → HTTP %s", url, code)
        except Exception as exc:  # noqa: BLE001
            logger.warning("POST(cffi) %s failed: %s", url, exc)
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
    except Exception as exc:  # noqa: BLE001
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
    if _HAS_CFFI:
        try:
            resp = await asyncio.to_thread(_cffi_get, url, hdrs, None, timeout)
            if getattr(resp, "status_code", 200) < 400:
                return getattr(resp, "content", None)
        except Exception as exc:  # noqa: BLE001
            logger.warning("GET(bytes,cffi) %s failed: %s", url, exc)
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(
                url, headers=hdrs, timeout=aiohttp.ClientTimeout(total=timeout)
            ) as resp:
                if resp.status >= 400:
                    logger.warning("GET(bytes) %s → HTTP %s", url, resp.status)
                    return None
                return await resp.read()
    except Exception as exc:  # noqa: BLE001
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
