"""Probe continue / retry callbacks for stream creation flow."""
from __future__ import annotations

import logging
from telegram import Update
from telegram.ext import ContextTypes

from .common import (
    WAITING_OFFSET, WAITING_SOURCE, WAITING_RTMP_URL, _safe_update_reply,
)
from keyboards.menus import cancel_keyboard
from database import db
import html

logger = logging.getLogger(__name__)

async def probe_continue_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    try:
        await q.answer()
    except Exception:
        pass
    context.user_data.pop("await_probe_continue", None)
    # Continue to RTMP / offset flow
    profile = await db.get_default_rtmp_profile(q.from_user.id)
    from keyboards.menus import rtmp_confirm_keyboard
    from utils.helpers import safe_edit_message
    context.user_data["await_stream_rtmp"] = True
    if profile:
        base_disp = profile.get("rtmp_base") or ""
        masked = f"***{str(profile.get('stream_key') or '')[-6:]}" if profile.get("stream_key") else "غير محفوظ"
        text = (
            f"⚙️ <b>إعدادات RTMP محفوظة:</b>\n"
            f"RTMP:\n<code>{html.escape(base_disp)}</code>\n"
            f"KEY:\n<code>{html.escape(masked)}</code>\n\n"
            "هل تريد استخدامها؟"
        )
        await safe_edit_message(q, text, parse_mode="HTML", reply_markup=rtmp_confirm_keyboard())
    else:
        await safe_edit_message(
            q,
            "📡 أرسل رابط سيرفر RTMP فقط، أو /skip\n"
            "<code>rtmps://dc4-1.rtmp.t.me/s/</code>",
            parse_mode="HTML",
        )
    return WAITING_RTMP_URL


async def probe_retry_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    try:
        await q.answer("أرسل الرابط من جديد")
    except Exception:
        pass
    from utils.helpers import safe_edit_message
    await safe_edit_message(q, "🔄 أرسل رابط المصدر مرة أخرى للفحص:")
    context.user_data["await_probe_continue"] = False
    return WAITING_SOURCE


