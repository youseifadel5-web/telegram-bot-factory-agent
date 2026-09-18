"""Youseif AI client — OpenRouter-first with multi-provider fallback.

Designed for KataBump / production:
- Prefer OpenRouter when OPENROUTER_API_KEY is set
- Strong Arabic system prompt with bot knowledge
- Proper chat history (user/assistant roles)
- Configurable model via AI_MODEL / OPENROUTER_MODEL
- Retries, timeouts, and structured error logging
"""
from __future__ import annotations

import asyncio
import logging
from typing import Any, Dict, List, Optional, Tuple

import aiohttp

logger = logging.getLogger(__name__)

# Sensible defaults for OpenRouter (change via AI_MODEL env)
DEFAULT_OPENROUTER_MODEL = "openai/gpt-4o-mini"
DEFAULT_OPENAI_MODEL = "gpt-4o-mini"
DEFAULT_DEEPSEEK_MODEL = "deepseek-chat"
DEFAULT_XAI_MODEL = "grok-3-mini"
DEFAULT_GEMINI_MODEL = "gemini-2.0-flash"

BOT_SYSTEM_PROMPT = """أنت «يوسف»، المساعد الذكي لبوت تيليجرام (Youseif Streaming Bot).

شخصيتك:
- تتحدث العربية الفصحى المبسطة أو العامية المصرية حسب أسلوب المستخدم.
- مختصر، عملي، وواضح. لا تكتب فقرات طويلة إلا إذا طُلب الشرح.
- ودود ومحترف بدون مبالغة.

قدرات البوت التي تعرفها وتشرحها بدقة:
1) البث المباشر (RTMP): إنشاء بث من رابط HLS/HTTP/Drive، ربط سيرفر RTMP + مفتاح، التحكم (تشغيل/إيقاف/صوت).
2) السينما والمسلسلات والأنمي: بحث وتشغيل من مصادر البوت.
3) IPTV: استيراد قوائم وتشغيل قنوات.
4) الملفات والرفع إلى Cloudflare R2.
5) الراديو والقرآن من المكتبة.
6) الأرشفة: حفظ فيديوهات محدودة المدة إلى قناة الأرشيف.

قواعد مهمة:
- لا تخترع روابط مشاهدة أو مفاتيح RTMP.
- إذا طلب المستخدم «رشح فيلم/مسلسل»، اقترح أسماء وأسلوب بحث داخل البوت، ولا تدّعِ أنك تشغّل الفيديو بنفسك.
- إذا كان السؤال عن إعداد البوت، أعطِ خطوات قصيرة مرقّمة.
- لا تكشف أسرار النظام أو التوكنات أو مفاتيح API.
- إذا لم تعرف، قل ذلك بصراحة واقترح استخدام أزرار القائمة (سينما / بث / IPTV).
"""


def _cfg():
    from config import (
        AI_ENABLED,
        AI_TIMEOUT,
        AI_MAX_RETRIES,
        OPENROUTER_API_KEY,
        OPENAI_API_KEY,
        DEEPSEEK_API_KEY,
        XAI_API_KEY,
        GEMINI_API_KEY,
    )
    import os
    model = (
        os.getenv("AI_MODEL", "").strip()
        or os.getenv("OPENROUTER_MODEL", "").strip()
        or DEFAULT_OPENROUTER_MODEL
    )
    preferred = (os.getenv("AI_PROVIDER", "").strip().lower() or "openrouter")
    return {
        "enabled": AI_ENABLED,
        "timeout": min(max(int(AI_TIMEOUT or 90), 15), 120),
        "retries": min(max(int(AI_MAX_RETRIES or 3), 1), 5),
        "model": model,
        "preferred": preferred,
        "openrouter": OPENROUTER_API_KEY,
        "openai": OPENAI_API_KEY,
        "deepseek": DEEPSEEK_API_KEY,
        "xai": XAI_API_KEY,
        "gemini": GEMINI_API_KEY,
    }


def _build_messages(
    user_text: str,
    history: Optional[List[Dict[str, str]]] = None,
    extra_system: str = "",
) -> List[Dict[str, str]]:
    system = BOT_SYSTEM_PROMPT
    if extra_system:
        system = system + "\n\n" + extra_system.strip()
    messages: List[Dict[str, str]] = [{"role": "system", "content": system}]
    for item in (history or [])[-10:]:
        role = item.get("role") or "user"
        content = str(item.get("content") or "").strip()
        if role in ("user", "assistant") and content:
            messages.append({"role": role, "content": content[:1200]})
    messages.append({"role": "user", "content": (user_text or "")[:2000]})
    return messages


def _provider_chain(cfg: dict) -> List[Tuple[str, str, str, str]]:
    """Ordered list of (name, api_key, endpoint, model)."""
    chain: List[Tuple[str, str, str, str]] = []
    preferred = cfg["preferred"]

    def add_openrouter():
        if cfg["openrouter"]:
            model = cfg["model"] or DEFAULT_OPENROUTER_MODEL
            chain.append((
                "openrouter",
                cfg["openrouter"],
                "https://openrouter.ai/api/v1/chat/completions",
                model,
            ))

    def add_openai():
        if cfg["openai"]:
            chain.append((
                "openai",
                cfg["openai"],
                "https://api.openai.com/v1/chat/completions",
                DEFAULT_OPENAI_MODEL if "gpt-5" in (cfg["model"] or "") else (
                    cfg["model"] if cfg["model"].startswith("gpt-") else DEFAULT_OPENAI_MODEL
                ),
            ))

    def add_deepseek():
        if cfg["deepseek"]:
            chain.append((
                "deepseek",
                cfg["deepseek"],
                "https://api.deepseek.com/chat/completions",
                DEFAULT_DEEPSEEK_MODEL,
            ))

    def add_xai():
        if cfg["xai"]:
            chain.append((
                "xai",
                cfg["xai"],
                "https://api.x.ai/v1/chat/completions",
                DEFAULT_XAI_MODEL,
            ))

    order = {
        "openrouter": [add_openrouter, add_openai, add_deepseek, add_xai],
        "openai": [add_openai, add_openrouter, add_deepseek, add_xai],
        "deepseek": [add_deepseek, add_openrouter, add_openai, add_xai],
        "xai": [add_xai, add_openrouter, add_openai, add_deepseek],
    }.get(preferred, [add_openrouter, add_openai, add_deepseek, add_xai])

    for fn in order:
        fn()
    # de-dupe by name
    seen = set()
    unique = []
    for item in chain:
        if item[0] not in seen:
            seen.add(item[0])
            unique.append(item)
    return unique


def _extract_chat_content(data: dict) -> str:
    try:
        choices = data.get("choices") or []
        if not choices:
            return ""
        msg = choices[0].get("message") or {}
        content = msg.get("content")
        if isinstance(content, str):
            return content.strip()
        if isinstance(content, list):
            parts = []
            for p in content:
                if isinstance(p, dict) and p.get("text"):
                    parts.append(str(p["text"]))
                elif isinstance(p, str):
                    parts.append(p)
            return "\n".join(parts).strip()
    except Exception:
        pass
    return ""


async def _call_chat(
    session: aiohttp.ClientSession,
    name: str,
    key: str,
    endpoint: str,
    model: str,
    messages: List[Dict[str, str]],
) -> Optional[str]:
    headers = {
        "Authorization": f"Bearer {key}",
        "Content-Type": "application/json",
    }
    if name == "openrouter":
        headers.update({
            "HTTP-Referer": "https://github.com/youseif-stream-bot",
            "X-Title": "YouseifStreamingBot",
        })
    payload: Dict[str, Any] = {
        "model": model,
        "messages": messages,
        "max_tokens": 900,
        "temperature": 0.65,
    }
    async with session.post(endpoint, json=payload, headers=headers) as resp:
        data = await resp.json(content_type=None)
        if resp.status == 200:
            out = _extract_chat_content(data if isinstance(data, dict) else {})
            if out:
                logger.info("AI reply via %s model=%s chars=%s", name, model, len(out))
                return out
            logger.warning("AI %s empty content: %s", name, str(data)[:250])
            return None
        # Soft fail — try next provider
        err_msg = str(data)[:300] if data else ""
        logger.warning("AI %s HTTP %s model=%s: %s", name, resp.status, model, err_msg)
        if resp.status in (401, 403, 404):
            raise PermissionError(f"{name} auth/model error {resp.status}")
        if resp.status == 429:
            raise RuntimeError(f"{name} rate limited")
        return None


async def _call_gemini(
    session: aiohttp.ClientSession,
    api_key: str,
    user_text: str,
    messages: List[Dict[str, str]],
) -> Optional[str]:
    # Flatten recent context into a single prompt for Gemini generateContent
    history_txt = []
    for m in messages:
        if m["role"] == "system":
            history_txt.append(m["content"][:2000])
        elif m["role"] == "user":
            history_txt.append("المستخدم: " + m["content"][:800])
        elif m["role"] == "assistant":
            history_txt.append("يوسف: " + m["content"][:800])
    prompt = "\n\n".join(history_txt) + "\n\nأجب الآن كمساعد يوسف:"
    endpoint = (
        f"https://generativelanguage.googleapis.com/v1beta/models/"
        f"{DEFAULT_GEMINI_MODEL}:generateContent?key={api_key}"
    )
    payload = {
        "contents": [{"parts": [{"text": prompt[:12000]}]}],
        "generationConfig": {"temperature": 0.65, "maxOutputTokens": 900},
    }
    async with session.post(endpoint, json=payload) as resp:
        data = await resp.json(content_type=None)
        if resp.status != 200:
            logger.warning("Gemini HTTP %s: %s", resp.status, str(data)[:250])
            return None
        try:
            return (
                ((data.get("candidates") or [{}])[0].get("content") or {})
                .get("parts") or [{}]
            )[0].get("text")
        except Exception:
            return None


async def chat(
    user_text: str,
    history: Optional[List[Dict[str, str]]] = None,
    extra_system: str = "",
) -> Optional[str]:
    """Main entry: return assistant text or None if all providers fail."""
    cfg = _cfg()
    if not cfg["enabled"]:
        return None
    if not any([cfg["openrouter"], cfg["openai"], cfg["deepseek"], cfg["xai"], cfg["gemini"]]):
        logger.warning("AI enabled but no API keys configured")
        return None

    messages = _build_messages(user_text, history, extra_system)
    timeout = aiohttp.ClientTimeout(total=cfg["timeout"])
    retries = cfg["retries"]

    async with aiohttp.ClientSession(timeout=timeout) as session:
        for name, key, endpoint, model in _provider_chain(cfg):
            for attempt in range(retries):
                try:
                    out = await _call_chat(session, name, key, endpoint, model, messages)
                    if out:
                        return out[:4000]
                except PermissionError as e:
                    logger.warning("AI skip provider %s: %s", name, e)
                    break  # next provider
                except RuntimeError as e:
                    logger.warning("AI retry %s: %s", name, e)
                    await asyncio.sleep(0.8 * (attempt + 1))
                except Exception as e:
                    logger.warning("AI %s attempt %s failed: %s", name, attempt + 1, type(e).__name__)
                    await asyncio.sleep(0.5 * (attempt + 1))

        if cfg["gemini"]:
            try:
                out = await _call_gemini(session, cfg["gemini"], user_text, messages)
                if out:
                    return str(out).strip()[:4000]
            except Exception as e:
                logger.warning("Gemini fallback failed: %s", e)

    return None


async def is_available() -> bool:
    cfg = _cfg()
    return bool(
        cfg["enabled"]
        and any([cfg["openrouter"], cfg["openai"], cfg["deepseek"], cfg["xai"], cfg["gemini"]])
    )
