from functools import wraps
from telegram import Update
from telegram.ext import ContextTypes
from database import db
from config import ADMIN_ID


def admin_only(func):
    @wraps(func)
    async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE, *args, **kwargs):
        user_id = update.effective_user.id
        if user_id != ADMIN_ID and not await db.is_admin(user_id):
            if update.callback_query:
                await update.callback_query.answer("🚫 هذا الأمر للأدمن فقط", show_alert=True)
            else:
                await update.message.reply_text("🚫 هذا الأمر للأدمن فقط")
            return
        return await func(update, context, *args, **kwargs)
    return wrapper


def not_banned(func):
    @wraps(func)
    async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE, *args, **kwargs):
        user_id = update.effective_user.id
        user = await db.get_user(user_id)
        if user and user.get("is_banned"):
            if update.callback_query:
                await update.callback_query.answer("🚫 تم حظرك من استخدام البوت", show_alert=True)
            else:
                await update.message.reply_text("🚫 تم حظرك من استخدام البوت")
            return
        return await func(update, context, *args, **kwargs)
    return wrapper


# ---------------------------------------------------------------------------
# Simple in-memory rate limiter (per user)
# ---------------------------------------------------------------------------
import time
from collections import defaultdict
from typing import Callable, Any

_rate_buckets: dict[str, list[float]] = defaultdict(list)


def rate_limit(calls: int = 5, period: float = 60.0, key_prefix: str = "rl"):
    """
    Limit a handler to `calls` invocations per `period` seconds per user.

    Usage:
        @rate_limit(calls=3, period=30)
        async def heavy_handler(...):
            ...
    """
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE, *args, **kwargs) -> Any:
            user = update.effective_user
            if not user:
                return await func(update, context, *args, **kwargs)

            bucket_key = f"{key_prefix}:{user.id}:{func.__name__}"
            now = time.monotonic()
            window = _rate_buckets[bucket_key]

            # drop expired timestamps
            while window and window[0] <= now - period:
                window.pop(0)

            if len(window) >= calls:
                wait = int(period - (now - window[0])) + 1
                msg = f"⏳ تم تجاوز الحد المسموح. حاول بعد {wait} ثانية."
                if update.callback_query:
                    await update.callback_query.answer(msg, show_alert=True)
                elif update.effective_message:
                    await update.effective_message.reply_text(msg)
                return None

            window.append(now)
            return await func(update, context, *args, **kwargs)
        return wrapper
    return decorator
