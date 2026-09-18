"""Shared constants, state and helpers for stream handlers."""
from __future__ import annotations

import asyncio
import logging
from telegram import Update
from telegram.ext import ContextTypes, ConversationHandler

from utils.helpers import is_admin, clear_workflow_state
from keyboards.menus import main_reply_keyboard
from config import ADMIN_ID

logger = logging.getLogger(__name__)

# chat_id:msg_id -> asyncio.Task for auto-refresh
_STATUS_TASKS: dict = {}
_STATUS_TICK: dict = {}

WAITING_TITLE, WAITING_SOURCE, WAITING_OFFSET, WAITING_RTMP_URL, WAITING_STREAM_KEY = range(5)


async def _safe_update_reply(update: Update, text: str, **kwargs):
    """Reply safely for both Message and CallbackQuery updates."""
    message = update.effective_message
    if message is None:
        logger.warning("Cannot reply: update has no effective_message")
        return None
    try:
        return await message.reply_text(text, **kwargs)
    except Exception as exc:
        logger.warning("reply_text failed: %s", type(exc).__name__)
        return None


async def cancel_conversation(update: Update, context: ContextTypes.DEFAULT_TYPE):
    clear_workflow_state(context.user_data)
    admin = is_admin(update.effective_user.id, ADMIN_ID)
    if update.callback_query:
        await update.callback_query.answer()
        try:
            await update.callback_query.edit_message_text("❌ تم الإلغاء.")
        except Exception:
            pass
        if update.callback_query.message:
            await update.callback_query.message.reply_text(
                "القائمة:", reply_markup=main_reply_keyboard(admin)
            )
    else:
        await _safe_update_reply(
            update, "❌ تم الإلغاء.", reply_markup=main_reply_keyboard(admin)
        )
    return ConversationHandler.END


async def _stop_auto_refresh(chat_id: int, message_id: int):
    key = (chat_id, message_id)
    task = _STATUS_TASKS.pop(key, None)
    _STATUS_TICK.pop(key, None)
    if task and not task.done():
        task.cancel()


async def cancel_all_status_tasks():
    """Cancel auto-refresh tasks during application shutdown."""
    tasks = list(_STATUS_TASKS.values())
    _STATUS_TASKS.clear()
    _STATUS_TICK.clear()
    for task in tasks:
        if task and not task.done():
            task.cancel()
    if tasks:
        await asyncio.gather(*tasks, return_exceptions=True)


def build_rtmp_url(base: str | None, key: str | None) -> str | None:
    """Join RTMP base + stream key safely."""
    base = (base or "").strip()
    key = (key or "").strip()
    if base and key:
        return base.rstrip("/") + "/" + key.lstrip("/")
    if base:
        return base.rstrip("/")
    if key:
        return key
    return None


def validate_rtmp_url(url: str) -> tuple[bool, str]:
    """Basic validation for RTMP(S) publish URLs."""
    u = (url or "").strip()
    if not u:
        return False, "الرابط فارغ"
    low = u.lower()
    if not (low.startswith("rtmp://") or low.startswith("rtmps://")):
        return False, "يجب أن يبدأ الرابط بـ rtmp:// أو rtmps://"
    if " " in u or "\n" in u or "\r" in u:
        return False, "الرابط يحتوي مسافات غير صالحة"
    if len(u) < 12:
        return False, "الرابط قصير جداً"
    return True, ""
