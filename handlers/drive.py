import logging
import html
import asyncio
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, ConversationHandler
from services.gdrive import (
    extract_file_id,
    is_drive_url,
    probe_drive,
    download_to_temp,
    cleanup_temp,
    format_size,
    SUPPORTED_EXT,
    AUDIO_EXT,
)
from database import db
from services.stream import stream_manager
from keyboards.menus import cancel_keyboard, main_reply_keyboard
from utils.helpers import is_admin, has_active_workflow
from config import ADMIN_ID
from handlers.streams import WAITING_RTMP_URL, WAITING_STREAM_KEY, _finalize_stream

logger = logging.getLogger(__name__)

# last played per user
_LAST_PLAYED = {}  # user_id -> {file_id, name, direct_url, ...}


def drive_info_keyboard(file_id: str, has_last: bool = False) -> InlineKeyboardMarkup:
    rows = [
        [InlineKeyboardButton("▶️ تشغيل", callback_data=f"drive_play:{file_id}")],
        [InlineKeyboardButton("📡 بث إلى RTMP", callback_data=f"drive_rtmp:{file_id}")],
    ]
    if has_last:
        rows.append([InlineKeyboardButton("🔁 إعادة تشغيل الأخير", callback_data="drive_replay")])
    rows.append([InlineKeyboardButton("❌ إلغاء", callback_data="cancel")])
    return InlineKeyboardMarkup(rows)


async def handle_drive_link(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Triggered when user sends a Google Drive URL as a message."""
    text = (update.message.text or "").strip()
    if not is_drive_url(text):
        return
    # Let the active workflow router own this message. This handler is only for
    # standalone Drive links from the idle state.
    if has_active_workflow(context.user_data):
        return

    # If currently in stream conversation waiting for source, let streams handler deal — 
    # but ConversationHandler may consume first. This handler is for free messages.
    file_id = extract_file_id(text)
    if not file_id:
        await update.message.reply_text("❌ لم أستطع استخراج معرف الملف من رابط Drive.")
        return

    status = await update.message.reply_text("🔍 جاري فحص رابط Google Drive...")

    info = await asyncio.to_thread(probe_drive, file_id)
    if not info.get("ok"):
        await status.edit_text(
            f"❌ <b>فشل فحص Drive</b>\n\n"
            f"{html.escape(info.get('error') or 'غير متاح')}\n\n"
            f"تأكد أن الملف:\n"
            f"• مشاركة: <b>أي شخص لديه الرابط</b>\n"
            f"• نوع مدعوم: MP3 / M4A / AAC / MP4",
            parse_mode="HTML",
        )
        return

    name = info.get("name") or file_id
    size = info.get("size") or 0
    ext = (info.get("ext") or "").lower()
    ctype = info.get("content_type") or ""

    # type label
    if ext in AUDIO_EXT or "audio" in ctype:
        kind = "🎵 صوت"
    elif ext == ".mp4" or "video" in ctype:
        kind = "🎬 فيديو"
    else:
        kind = "📄 ملف"

    if ext and ext not in SUPPORTED_EXT and "audio" not in ctype and "video" not in ctype:
        await status.edit_text(
            f"⚠️ النوع <code>{html.escape(ext or ctype)}</code> قد لا يُدعم.\n"
            f"المدعوم: MP3, M4A, AAC, MP4",
            parse_mode="HTML",
        )

    # store in user_data
    context.user_data["drive_info"] = info
    _LAST_PLAYED[update.effective_user.id] = info

    # duration unknown without ffprobe — show —
    text_msg = (
        f"📁 <b>Google Drive</b>\n"
        f"━━━━━━━━━━━━━━━━\n"
        f"📄 الاسم: <code>{html.escape(name)}</code>\n"
        f"📦 الحجم: <b>{format_size(size)}</b>\n"
        f"{kind}\n"
        f"🆔 <code>{file_id}</code>\n"
        f"⏱ المدة: —\n"
        f"━━━━━━━━━━━━━━━━\n"
        f"✅ الملف متاح للتحميل\n\n"
        f"▶️ تشغيل = يبدأ بث عبر FFmpeg (يحتاج RTMP)\n"
        f"أو أرسل مفتاح القناة بعد اختيار البث"
    )
    await status.edit_text(
        text_msg,
        parse_mode="HTML",
        reply_markup=drive_info_keyboard(file_id, has_last=False),
    )


async def drive_play_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """▶️ تشغيل → ask RTMP then stream."""
    query = update.callback_query
    await query.answer()
    file_id = query.data.split(":")[1]
    info = context.user_data.get("drive_info")
    if not info or info.get("file_id") != file_id:
        info = await asyncio.to_thread(probe_drive, file_id)
        if not info.get("ok"):
            await query.edit_message_text(f"❌ {info.get('error') or 'غير متاح'}")
            return
        context.user_data["drive_info"] = info

    name = info.get("name") or "Drive"
    url = info.get("direct_url")
    context.user_data["stream_title"] = name[:80]
    context.user_data["stream_source"] = url
    context.user_data["drive_file_id"] = file_id
    context.user_data["pending_stream_url"] = url
    context.user_data["pending_stream_title"] = name[:80]
    _LAST_PLAYED[query.from_user.id] = info

    await query.edit_message_text(
        f"▶️ <b>تشغيل من Drive</b>\n\n"
        f"📄 <code>{html.escape(name)}</code>\n"
        f"✅ المصدر جاهز\n\n"
        f"📡 أرسل <b>رابط سيرفر RTMP</b>:\n"
        f"<code>rtmps://dc4-1.rtmp.t.me/s/</code>\n\n"
        f"ثم مفتاح البث.\nأو /skip",
        parse_mode="HTML",
        reply_markup=cancel_keyboard(),
    )
    # Enter conversation via stream_from_url entry by simulating — user sends RTMP next
    # We set state by returning WAITING_RTMP_URL only works inside ConversationHandler.
    # Use stream_from_url entry point: tell user to press button
    from telegram import InlineKeyboardButton, InlineKeyboardMarkup
    await query.message.reply_text(
        "اضغط للمتابعة:",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("🚀 إكمال وإدخال RTMP", callback_data="stream_from_url")],
        ]),
    )


async def drive_rtmp_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Same as play — explicit RTMP path."""
    await drive_play_callback(update, context)


async def drive_replay_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    info = _LAST_PLAYED.get(query.from_user.id)
    if not info:
        await query.edit_message_text("❌ لا يوجد رابط سابق.")
        return
    context.user_data["drive_info"] = info
    file_id = info.get("file_id")
    # fake data for play
    class _Q:
        pass
    # reuse play
    query.data = f"drive_play:{file_id}"
    await drive_play_callback(update, context)


async def try_drive_local_fallback(stream_id: int, file_id: str, rtmp_url: str) -> bool:
    """If remote Drive stream fails, download temp and play local path."""
    path, err = await asyncio.to_thread(download_to_temp, file_id)
    if not path:
        logger.error("Drive fallback download failed: %s", err)
        return False
    pid = await asyncio.to_thread(stream_manager.start_stream, stream_id, path, rtmp_url)
    if pid:
        # store path for later cleanup in meta — optional
        return True
    cleanup_temp(path)
    return False
