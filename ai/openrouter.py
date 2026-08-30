# -*- coding: utf-8 -*-
"""OpenRouter client — key from env only, never logged."""
from __future__ import annotations

import json
import logging
import os
from typing import Any, Dict, List, Optional

import httpx

log = logging.getLogger("ai.openrouter")

OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
AI_TIMEOUT = float(os.getenv("AI_TIMEOUT", "25"))


class OpenRouterClient:
    def __init__(self):
        self.api_key = (os.getenv("OPENROUTER_API_KEY") or "").strip()
        self.model = (os.getenv("OPENROUTER_MODEL") or "openai/gpt-4o-mini").strip()
        self._client: Optional[httpx.AsyncClient] = None
        self.stats = {"requests": 0, "success": 0, "fail": 0, "cache_hits": 0}

    @property
    def enabled(self) -> bool:
        return bool(self.api_key)

    async def _client_get(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(timeout=httpx.Timeout(AI_TIMEOUT))
        return self._client

    async def chat(self, messages: List[Dict[str, str]], temperature: float = 0.2) -> Optional[str]:
        if not self.enabled:
            return None
        self.stats["requests"] += 1
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "HTTP-Referer": "https://localhost",
            "X-Title": "Unified Media Bot",
        }
        body = {
            "model": self.model,
            "messages": messages,
            "temperature": temperature,
        }
        try:
            c = await self._client_get()
            r = await c.post(OPENROUTER_URL, headers=headers, json=body)
            if r.status_code != 200:
                self.stats["fail"] += 1
                log.warning("OpenRouter HTTP %s", r.status_code)
                return None
            data = r.json()
            content = (((data.get("choices") or [{}])[0]).get("message") or {}).get("content")
            self.stats["success"] += 1
            return content
        except Exception as e:
            self.stats["fail"] += 1
            log.warning("OpenRouter error: %s", type(e).__name__)
            return None

    async def close(self):
        if self._client and not self._client.is_closed:
            await self._client.aclose()
