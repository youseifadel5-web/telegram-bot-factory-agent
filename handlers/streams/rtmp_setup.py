"""RTMP setup callbacks for stream creation conversation."""
from __future__ import annotations

import html
import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, ConversationHandler

from database import db
from keyboards.menus import cancel_keyboard, stream_actions_keyboard
from utils.helpers import is_admin, safe_edit_message, clear_workflow_state
from config import ADMIN_ID

from .common import (
    WAITING_TITLE, WAITING_SOURCE, WAITING_OFFSET, WAITING_RTMP_URL, WAITING_STREAM_KEY,
    _safe_update_reply, cancel_conversation, build_rtmp_url, validate_rtmp_url,
)

logger = logging.getLogger(__name__)

# finalize is imported lazily to avoid circular imports
async def _call_finalize(update, context):
    from .finalize import finalize_stream
    return await finalize_stream(update, context)

async def start_rtmp_setup_flags(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Start RTMP collection without ConversationHandler (IPTV / favorites / search).

    States via user_data flags:
      await_stream_rtmp → await_stream_key → _finalize_stream
    Always asks before reusing saved RTMP settings.
    """
    query = update.callback_query
    source = context.user_data.get("pending_stream_url") or context.user_data.get("stream_source")
    title = context.user_data.get("pending_stream_title") or context.user_data.get("stream_title") or "بث"
    if not source:
        if query:
            from utils.helpers import safe_edit_message
            await safe_edit_message(query, "❌ لا يوجد مصدر.")
        return

    # Probe source before RTMP setup
    from services.source_probe import clean_url, probe_source, format_probe_panel
    from keyboards.menus import rtmp_confirm_keyboard, probe_continue_keyboard
    source = clean_url(str(source))
    context.user_data["stream_source"] = context.user_data.pop("pending_stream_url", source)
    context.user_data["stream_source"] = source
    context.user_data["stream_title"] = context.user_data.pop("pending_stream_title", title)
    context.user_data["start_offset"] = 0

    target = query.message if query else update.message
    headers = context.user_data.get("pending_stream_headers")
    try:
        status_msg = await target.reply_text("🔍 جاري فحص المصدر...")
    except Exception:
        status_msg = None
    try:
        probe = await asyncio.get_event_loop().run_in_executor(
            None, lambda: probe_source(source, headers=headers)
        )
    except Exception as e:
        logger.exception("probe: %s", e)
        probe = {
            "ok": False,
            "cleaned_url": source,
            "media_kind": "video",
            "ffmpeg_ready": True,
            "error": f"تعذر فحص المصدر: {type(e).__name__}",
            "solution": "أعد الفحص أو تابع التشغيل يدويًا إذا كان الرابط موثوقًا",
        }
    context.user_data["probe_result"] = probe
    from services.source_probe import looks_like_audio
    context.user_data["media_kind"] = probe.get("media_kind") or (
        "audio" if looks_like_audio(source) else "video"
    )
    if probe.get("cleaned_url"):
        context.user_data["stream_source"] = probe["cleaned_url"]

    panel = format_probe_panel(probe, source)
    try:
        if status_msg:
            await status_msg.edit_text(panel, parse_mode="HTML")
        else:
            await target.reply_text(panel, parse_mode="HTML")
    except Exception:
        pass

    if not probe.get("ok"):
        try:
            await target.reply_text(
                "⚠️ المصدر قد لا يعمل. يمكنك المتابعة على مسؤوليتك أو إلغاء العملية.",
                reply_markup=probe_continue_keyboard(True),
            )
            context.user_data["await_probe_continue"] = True
            return
        except Exception:
            pass

    profile = await db.get_default_rtmp_profile(update.effective_user.id)
    context.user_data["await_stream_rtmp"] = True
    if profile:
        base_disp = profile.get("rtmp_base") or ""
        masked = f"***{str(profile.get('stream_key') or '')[-6:]}" if profile.get("stream_key") else "غير محفوظ"
        text = (
            f"🚀 <b>بث: {html.escape(str(title))}</b>\n\n"
            f"⚙️ <b>إعدادات RTMP محفوظة:</b>\n"
            f"RTMP:\n<code>{html.escape(base_disp)}</code>\n"
            f"KEY:\n<code>{html.escape(masked)}</code>\n\n"
            "هل تريد استخدامها؟"
        )
        await target.reply_text(text, parse_mode="HTML", reply_markup=rtmp_confirm_keyboard())
    else:
        await target.reply_text(
            "📡 <b>إعداد البث</b>\n\n"
            "أرسل رابط سيرفر RTMP فقط (بدون المفتاح):\n\n"
            "<code>rtmps://dc4-1.rtmp.t.me/s/</code>\n"
            "<code>rtmp://live.twitch.tv/app/</code>\n"
            "<code>rtmp://a.rtmp.youtube.com/live2/</code>\n\n"
            "بعدها سأطلب Stream Key.\nأو /skip للتخزين فقط.",
            parse_mode="HTML", reply_markup=cancel_keyboard(),
        )
    return WAITING_RTMP_URL


async def rtmp_use_saved_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    try:
        await q.answer()
    except Exception:
        pass
    profile = await db.get_default_rtmp_profile(q.from_user.id)
    if not profile:
        from utils.helpers import safe_edit_message
        await safe_edit_message(q, "❌ لا توجد إعدادات محفوظة. أرسل رابط RTMP:")
        context.user_data["await_stream_rtmp"] = True
        return
    context.user_data["rtmp_base"] = profile.get("rtmp_base")
    context.user_data["stream_key"] = profile.get("stream_key")
    context.user_data.pop("await_stream_rtmp", None)
    from utils.helpers import safe_edit_message
    await safe_edit_message(q, "✅ تم استخدام إعدادات RTMP المحفوظة.\nجاري بدء البث...")
    await _call_finalize(update, context)
    return ConversationHandler.END


async def rtmp_change_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    try:
        await q.answer()
    except Exception:
        pass
    context.user_data["await_stream_rtmp"] = True
    from utils.helpers import safe_edit_message
    await safe_edit_message(
        q,
        "📡 أرسل رابط سيرفر RTMP فقط (بدون المفتاح):\n"
        "<code>rtmps://dc4-1.rtmp.t.me/s/</code>",
        parse_mode="HTML",
    )
    return WAITING_RTMP_URL


async def rtmp_skip_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    try:
        await q.answer()
    except Exception:
        pass
    context.user_data["rtmp_base"] = None
    context.user_data["stream_key"] = None
    context.user_data.pop("await_stream_rtmp", None)
    from utils.helpers import safe_edit_message
    await safe_edit_message(q, "⏭ تم التخطي — جاري المتابعة بدون RTMP...")
    await _call_finalize(update, context)
    return ConversationHandler.END



# probe_continue / probe_retry live in .probe_flow (re-exported from package)
async def receive_rtmp_url(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = (update.message.text or "").strip()
    if text.lower() in ("/skip", "skip"):
        context.user_data["rtmp_base"] = None
        context.user_data["stream_key"] = None
        return await _call_finalize(update, context)

    # Allow user to type "نعم" / "استخدم" to reuse saved profile
    if text in ("نعم", "استخدم", "✅", "yes", "y"):
        profile = await db.get_default_rtmp_profile(update.effective_user.id)
        if profile:
            context.user_data["rtmp_base"] = profile["rtmp_base"]
            context.user_data["stream_key"] = profile["stream_key"]
            return await _call_finalize(update, context)
        await _safe_update_reply(update, "لا توجد إعدادات محفوظة. أرسل رابط RTMP:")
        return WAITING_RTMP_URL

    if not text.startswith(("rtmp://", "rtmps://")):
        await _safe_update_reply(update, 
            "❌ رابط RTMP غير صالح. يجب أن يبدأ بـ rtmp:// أو rtmps://\nأعد الإرسال أو /skip:"
        )
        return WAITING_RTMP_URL

    base = text.rstrip("/") + "/"
    context.user_data["rtmp_base"] = base
    await _safe_update_reply(update, 
        "🔑 أرسل الآن *مفتاح البث (Stream Key)* فقط:\n\n"
        "مثال:\n`1234567890abcdefgh`\n\n"
        "سيتم دمج الرابط + المفتاح تلقائياً وحفظه للاستخدام لاحقاً.\n"
        "أو /skip للمتابعة بدون مفتاح.",
        parse_mode="Markdown",
        reply_markup=cancel_keyboard(),
    )
    return WAITING_STREAM_KEY


async def receive_stream_key(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = (update.message.text or "").strip()
    if text.lower() in ("/skip", "skip"):
        context.user_data["stream_key"] = None
    else:
        # strip accidental full URLs pasted as key
        key = text
        if "://" in key:
            key = key.rstrip("/").split("/")[-1]
        context.user_data["stream_key"] = key
    return await _call_finalize(update, context)

