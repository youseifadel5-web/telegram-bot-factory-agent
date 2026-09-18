"""OscarTV unified HTTP client with Iron headers, retry, and cache."""
from __future__ import annotations

import asyncio
import logging
import time
from typing import Any, Dict, Optional
from urllib.parse import urlencode, urljoin

import aiohttp

from services.oscar.exceptions import (
    OscarAPIError,
    OscarAuthError,
    OscarInvalidResponse,
    OscarRateLimitError,
    OscarTimeoutError,
)

logger = logging.getLogger(__name__)

BASE = "https://ostvapp.cam"


class _TTLCache:
    def __init__(self):
        self._data: Dict[str, tuple] = {}

    def get(self, key: str):
        item = self._data.get(key)
        if not item:
            return None
        exp, val = item
        if time.time() > exp:
            self._data.pop(key, None)
            return None
        return val

    def set(self, key: str, value, ttl: float):
        self._data[key] = (time.time() + ttl, value)


class OscarClient:
    """Low-level Oscar API client. Use domain modules for endpoints."""

    def __init__(self, base: str = BASE, timeout: float = None):
        self.base = base.rstrip("/")
        try:
            from config import OSCAR_TIMEOUT, OSCAR_RETRIES
            self.timeout = float(timeout if timeout is not None else OSCAR_TIMEOUT or 25)
            self.default_attempts = int(OSCAR_RETRIES or 3)
        except Exception:
            self.timeout = float(timeout if timeout is not None else 25.0)
            self.default_attempts = 3
        self._cache = _TTLCache()

    def _iron_headers(self, full_url: str) -> Dict[str, str]:
        try:
            from services.iron_headers import iron_headers_for
            return iron_headers_for(full_url)
        except Exception as e:
            logger.warning("iron headers failed: %s", e)
            return {
                "User-Agent": "okhttp/4.12.0",
                "Accept": "application/json",
                "Accept-Encoding": "gzip",
                "Connection": "keep-alive",
            }

    def _url(self, path: str) -> str:
        if path.startswith("http"):
            return path
        return urljoin(self.base + "/", path.lstrip("/"))

    async def get(
        self,
        path: str,
        params: Optional[dict] = None,
        *,
        cache_ttl: float = 0,
        attempts: int = None,
    ) -> Any:
        url = self._url(path)
        cache_key = None
        if cache_ttl > 0:
            cache_key = f"GET:{url}?{urlencode(params or {}, doseq=True)}"
            hit = self._cache.get(cache_key)
            if hit is not None:
                return hit

        if attempts is None:
            attempts = getattr(self, "default_attempts", 3)
        last_err = None
        for i in range(attempts):
            try:
                full = url
                if params:
                    full = f"{url}?{urlencode({k: v for k, v in params.items() if v is not None})}"
                headers = self._iron_headers(full)
                timeout = aiohttp.ClientTimeout(total=self.timeout)
                async with aiohttp.ClientSession() as session:
                    async with session.get(url, headers=headers, params=params, timeout=timeout) as resp:
                        status = resp.status
                        if status == 401 or status == 403:
                            raise OscarAuthError(f"HTTP {status}", status=status)
                        if status == 429:
                            raise OscarRateLimitError("rate limited", status=429)
                        if status >= 500:
                            raise OscarAPIError(f"server {status}", status=status)
                        if status != 200:
                            text = await resp.text()
                            raise OscarAPIError(f"HTTP {status}: {text[:200]}", status=status)
                        try:
                            data = await resp.json(content_type=None)
                        except Exception as e:
                            raise OscarInvalidResponse(f"invalid json: {e}") from e
                if cache_key and cache_ttl > 0:
                    self._cache.set(cache_key, data, cache_ttl)
                return data
            except (OscarAuthError, OscarInvalidResponse):
                raise
            except asyncio.TimeoutError as e:
                last_err = OscarTimeoutError(str(e))
            except OscarRateLimitError as e:
                last_err = e
                await asyncio.sleep(min(2 ** i, 8))
                continue
            except OscarAPIError as e:
                last_err = e
                if e.status and e.status >= 500 and i + 1 < attempts:
                    await asyncio.sleep(min(2 ** i, 5))
                    continue
                raise
            except Exception as e:
                last_err = OscarAPIError(str(e))
                if i + 1 < attempts:
                    await asyncio.sleep(min(2 ** i, 5))
                    continue
        if last_err:
            raise last_err
        raise OscarAPIError("unknown error")

    async def post(self, path: str, data: Optional[dict] = None, attempts: int = 2) -> Any:
        url = self._url(path)
        last_err = None
        for i in range(attempts):
            try:
                headers = self._iron_headers(url)
                timeout = aiohttp.ClientTimeout(total=self.timeout)
                async with aiohttp.ClientSession() as session:
                    async with session.post(url, headers=headers, data=data or {}, timeout=timeout) as resp:
                        if resp.status >= 400:
                            text = await resp.text()
                            raise OscarAPIError(f"HTTP {resp.status}: {text[:200]}", status=resp.status)
                        try:
                            return await resp.json(content_type=None)
                        except Exception:
                            return {"raw": await resp.text()}
            except Exception as e:
                last_err = e
                if i + 1 < attempts:
                    await asyncio.sleep(1)
        raise OscarAPIError(str(last_err))


oscar_client = OscarClient()
