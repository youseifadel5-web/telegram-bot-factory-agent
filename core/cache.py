# -*- coding: utf-8 -*-
"""Lightweight memory cache with TTL."""
from __future__ import annotations

import time
from typing import Any, Dict, Optional, Tuple


class TTLCache:
    def __init__(self, default_ttl: int = 300, max_size: int = 5000):
        self.default_ttl = default_ttl
        self.max_size = max_size
        self._store: Dict[str, Tuple[float, Any]] = {}

    def get(self, key: str) -> Optional[Any]:
        item = self._store.get(key)
        if not item:
            return None
        exp, val = item
        if time.time() > exp:
            self._store.pop(key, None)
            return None
        return val

    def set(self, key: str, value: Any, ttl: Optional[int] = None) -> None:
        if len(self._store) >= self.max_size:
            # drop expired / oldest-ish
            now = time.time()
            expired = [k for k, (e, _) in self._store.items() if e < now]
            for k in expired[: max(1, len(expired))]:
                self._store.pop(k, None)
            if len(self._store) >= self.max_size:
                for k in list(self._store.keys())[:50]:
                    self._store.pop(k, None)
        self._store[key] = (time.time() + (ttl or self.default_ttl), value)

    def clear(self) -> None:
        self._store.clear()

    def stats(self) -> Dict[str, int]:
        return {"size": len(self._store), "max": self.max_size}


# shared instances
nav_cache = TTLCache(default_ttl=120)
search_cache = TTLCache(default_ttl=180)
ai_cache = TTLCache(default_ttl=600)
meta_cache = TTLCache(default_ttl=600)
playback_cache = TTLCache(default_ttl=120)
