"""Stream creation conversation & RTMP setup."""
from __future__ import annotations

import html
import logging
import asyncio
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, ConversationHandler

from database import db
from services.stream import stream_manager
from keyboards.menus import stream_actions_keyboard, cancel_keyboard, main_menu, main_reply_keyboard
from utils.helpers import stream_uptime, is_admin, safe_edit_message, clear_workflow_state
from utils.decorators import rate_limit
from config import ADMIN_ID
from utils.visualizer import build_live_panel
from services.gdrive import extract_file_id, is_drive_url, direct_url, probe_drive
from services.source_probe import probe_source, format_probe_error, parse_time_offset
from services.security.ssrf import assert_safe_url, is_safe_url

from .finalize import finalize_stream as _finalize_stream
from .common import (
    WAITING_TITLE, WAITING_SOURCE, WAITING_OFFSET, WAITING_RTMP_URL, WAITING_STREAM_KEY,
    _safe_update_reply, cancel_conversation, build_rtmp_url, validate_rtmp_url,
)

logger = logging.getLogger(__name__)

@rate_limit(calls=4, period=45, key_prefix="stream_new")
async def stream_new_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if query:
        await query.answer()

    if context.user_data.get("pending_stream_url"):
        context.user_data["stream_source"] = context.user_data.pop("pending_stream_url")
        context.user_data["stream_title"] = context.user_data.pop("pending_stream_title", "بث جديد")
        user_id = (query.from_user if query else update.effective_user).id
        profile = await db.get_default_rtmp_profile(user_id)
        if profile:
            base_disp = profile["rtmp_base"]
            if len(base_disp) > 40:
                base_disp = base_disp[:30] + "…"
            text = (
                f"🚀 *إنشاء بث جديد*\n\n"
                f"العنوان: `{context.user_data['stream_title']}`\n"
                f"المصدر جاهز.\n\n"
                f"⚙️ إعدادات محفوظة:\n`{base_disp}`\n"
                f"أرسل *نعم* لاستخدامها، أو رابط RTMP جديد.\n"
                f"أو /skip"
            )
        else:
            text = (
                f"🚀 *إنشاء بث جديد*\n\n"
                f"العنوان: `{context.user_data['stream_title']}`\n"
                f"المصدر جاهز.\n\n"
                f"📡 أرسل *رابط سيرفر RTMP فقط* (بدون المفتاح):\n"
                f"مثال:\n`rtmps://dc4-1.rtmp.t.me/s/`\n"
                f"أو /skip لتخزين البث بدون تشغيل."
            )
        target = query.message if query else update.message
        await target.reply_text(text, parse_mode="Markdown", reply_markup=cancel_keyboard())
        return WAITING_RTMP_URL

    text = "🚀 *إنشاء بث جديد*\n\nأرسل عنوان البث (مثال: بث قرآن مباشر):"
    if query:
        await query.edit_message_text(text, parse_mode="Markdown", reply_markup=cancel_keyboard())
    else:
        await _safe_update_reply(update, text, parse_mode="Markdown", reply_markup=cancel_keyboard())
    return WAITING_TITLE


async def receive_title(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = (update.message.text or "").strip()
    if not text or text.startswith("/"):
        await _safe_update_reply(update, "❌ أرسل عنوان البث أولاً.")
        return WAITING_TITLE
    context.user_data["stream_title"] = text[:180]
    await _safe_update_reply(update, 
        "📥 أرسل رابط المصدر:\n\n"
        "• رابط فيديو / ستريم HTTP(S)\n"
        "• رابط HLS / M3U8\n"
        "• رابط Google Drive\n"
        "• رابط ملف R2\n\n"
        "أو /cancel للإلغاء.",
        reply_markup=cancel_keyboard(),
    )
    return WAITING_SOURCE


async def receive_source(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = (update.message.text or "").strip()
    from services.source_probe import clean_url, probe_source, format_probe_panel
    from keyboards.menus import probe_continue_keyboard
    text = clean_url(text)
    if not text.startswith(("http://", "https://", "rtmp://", "rtmps://", "/", "file:")):
        await _safe_update_reply(update, "❌ رابط المصدر غير صالح. أرسل رابط HTTP/HTTPS أو M3U8 أو Google Drive.")
        return WAITING_SOURCE

    # SSRF protection for remote URLs
    if text.startswith(("http://", "https://", "rtmp://", "rtmps://")):
        try:
            assert_safe_url(text)
        except ValueError:
            await _safe_update_reply(update, "🚫 هذا الرابط محظور لأسباب أمنية (SSRF).")
            return WAITING_SOURCE

    status = await _safe_update_reply(update, "🔍 جاري فحص المصدر...")
    headers = context.user_data.get("pending_stream_headers")
    try:
        probe = await asyncio.get_event_loop().run_in_executor(
            None, lambda: probe_source(text, headers=headers)
        )
    except Exception as e:
        logger.exception("probe failed: %s: %s", type(e).__name__, e)
        probe = {"ok": False, "error": str(e), "solution": "أعد المحاولة", "cleaned_url": text}

    cleaned = probe.get("cleaned_url") or text
    context.user_data["stream_source"] = cleaned
    context.user_data["probe_result"] = probe
    context.user_data["media_kind"] = probe.get("media_kind") or "video"
    context.user_data["start_offset"] = 0

    panel = format_probe_panel(probe, cleaned)
    try:
        await status.edit_text(panel, parse_mode="HTML", reply_markup=probe_continue_keyboard(bool(probe.get("ok"))))
    except Exception:
        await _safe_update_reply(update, panel, parse_mode="HTML", reply_markup=probe_continue_keyboard(bool(probe.get("ok"))))

    if not probe.get("ok"):
        return WAITING_SOURCE  # allow retry by sending another URL

    # Wait for user to press continue (callback) OR they can type /skip offset flow
    context.user_data["await_probe_continue"] = True
    return WAITING_OFFSET  # offset step still available via text; continue via button


async def receive_offset(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = (update.message.text or "").strip()
    if text.lower() in ("/skip", "skip", "0", "0.0"):
        context.user_data["start_offset"] = 0
    else:
        try:
            value = float(text)
            if value < 0 or value > 86400:
                raise ValueError
            context.user_data["start_offset"] = value
        except Exception:
            await _safe_update_reply(update, "❌ أدخل عدد ثوانٍ صحيحاً، أو /skip.")
            return WAITING_OFFSET

    profile = await db.get_default_rtmp_profile(update.effective_user.id)
    if profile:
        base = profile.get("rtmp_base") or ""
        masked = f"***{str(profile.get('stream_key') or '')[-6:]}" if profile.get("stream_key") else "غير محفوظ"
        await _safe_update_reply(update, 
            f"⚙️ إعدادات RTMP محفوظة:\n<code>{html.escape(base)}</code>\nKey: <code>{html.escape(masked)}</code>\n\n"
            "أرسل <b>نعم</b> لاستخدامها، أو أرسل رابط RTMP جديد، أو /skip.",
            parse_mode="HTML", reply_markup=cancel_keyboard(),
        )
    else:
        await _safe_update_reply(update, 
            "📡 أرسل رابط سيرفر RTMP فقط (بدون المفتاح):\n<code>rtmps://dc4-1.rtmp.t.me/s/</code>\n\nأو /skip.",
            parse_mode="HTML", reply_markup=cancel_keyboard(),
        )
    return WAITING_RTMP_URL


async def handle_stream_rtmp_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """RTMP receiver for non-ConversationHandler flows (cinema/IPTV)."""
    text = (update.message.text or "").strip()
    if text.lower() in ("نعم", "استخدم", "yes", "y"):
        profile = await db.get_default_rtmp_profile(update.effective_user.id)
        if not profile:
            await _safe_update_reply(update, "❌ لا توجد إعدادات RTMP محفوظة. أرسل رابط RTMP:")
            return
        context.user_data["rtmp_base"] = profile.get("rtmp_base")
        context.user_data["stream_key"] = profile.get("stream_key")
        context.user_data.pop("await_stream_rtmp", None)
        await _finalize_stream(update, context)
        return
    if text.lower() in ("/skip", "skip"):
        context.user_data["rtmp_base"] = None
        context.user_data["stream_key"] = None
        context.user_data.pop("await_stream_rtmp", None)
        await _finalize_stream(update, context)
        return
    if not text.startswith(("rtmp://", "rtmps://")):
        await _safe_update_reply(update, "❌ رابط RTMP غير صالح. أرسل rtmp:// أو rtmps://")
        return
    context.user_data["rtmp_base"] = text.rstrip("/") + "/"
    context.user_data.pop("await_stream_rtmp", None)
    context.user_data["await_stream_key"] = True
    await _safe_update_reply(update, "🔑 أرسل Stream Key فقط:")


async def handle_stream_key_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = (update.message.text or "").strip()
    if text.lower() in ("/skip", "skip"):
        context.user_data["stream_key"] = None
    else:
        key = text.rstrip("/")
        if "://" in key:
            key = key.split("/")[-1]
        context.user_data["stream_key"] = key
    context.user_data.pop("await_stream_key", None)
    await _finalize_stream(update, context)


async def stream_new_from_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Entry from bottom reply keyboard."""
    return await stream_new_callback(update, context)


async def stream_from_url_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if not context.user_data.get("pending_stream_url"):
        await query.edit_message_text("❌ لا يوجد رابط محفوظ.")
        return ConversationHandler.END
    context.user_data["stream_source"] = context.user_data.pop("pending_stream_url")
    context.user_data["stream_title"] = context.user_data.pop("pending_stream_title", "بث مكتبي")
    await query.edit_message_text(
        f"🚀 *إنشاء بث*\n\n"
        f"العنوان: `{context.user_data['stream_title']}`\n\n"
        f"📡 أرسل *رابط سيرفر RTMP* (بدون المفتاح):\n"
        f"`rtmps://dc4-1.rtmp.t.me/s/`\n\n"
        f"أو /skip",
        parse_mode="Markdown",
        reply_markup=cancel_keyboard(),
    )
    return WAITING_RTMP_URL



# RTMP setup + finalize moved to rtmp_setup.py / finalize.py
