"""Stream start / stop / volume / bitrate controls."""
from __future__ import annotations

import asyncio
import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes

from database import db
from services.stream import stream_manager
from keyboards.menus import stream_actions_keyboard
from utils.helpers import is_admin, safe_edit_message
from utils.decorators import rate_limit
from config import ADMIN_ID
from utils.visualizer import build_live_panel

from .common import _safe_update_reply, _stop_auto_refresh
from .status import _ensure_auto_refresh, stream_status_callback
from services.source_probe import probe_source, format_probe_error, looks_like_video, looks_like_audio
from services import playlist as playlist_service

logger = logging.getLogger(__name__)


async def _refresh_status(update, context, stream_id: int):
    """Render status after an action; action callbacks are not status callbacks."""
    query = update.callback_query
    if query:
        original = query.data
        query.data = f"stream_status:{stream_id}"
        try:
            await stream_status_callback(update, context)
        finally:
            query.data = original

@rate_limit(calls=6, period=30, key_prefix="stream_ctrl")
async def stream_start_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    try:
        stream_id = int(query.data.split(":")[1])
        s = await db.get_stream(stream_id)
        if not s or s["user_id"] != query.from_user.id:
            await query.answer("غير مسموح", show_alert=True)
            return
        if not s.get("rtmp_url"):
            await query.answer("لا يوجد رابط RTMP كامل (سيرفر + مفتاح).", show_alert=True)
            return
        if not await asyncio.to_thread(stream_manager.has_ffmpeg):
            await query.answer("❌ FFmpeg غير مثبت على السيرفر.", show_alert=True)
            return
        if stream_manager.is_running(stream_id):
            await query.answer("يعمل بالفعل", show_alert=True)
            return

        # فحص المصدر قبل التشغيل خارج event loop، مع استخدام الرابط المنظف.
        src = s.get("source_url") or ""
        probe = await asyncio.to_thread(probe_source, src)
        src = probe.get("cleaned_url") or src
        src_l = src.lower()
        soft = (
            any(ext in src_l for ext in (".m3u8", ".mp4", ".mp3", ".aac", ".m4a", ".ts", ".flv", ".mkv"))
            or "drive.google" in src_l
            or src.startswith("/")
        )
        if not probe.get("ok") and not soft:
            await query.edit_message_text(
                format_probe_error(probe, source_url=src),
                parse_mode="HTML",
                reply_markup=stream_actions_keyboard(stream_id, False),
            )
            await db.update_stream_error(stream_id, probe.get("error") or "فحص فاشل")
            return

        offset = float(s.get("start_offset") or 0)
        use_video = not (probe.get("media_kind") == "audio" or looks_like_audio(src)) and (
            bool(probe.get("has_video")) or looks_like_video(src)
        )
        pid = await asyncio.to_thread(
            stream_manager.start_stream,
            stream_id, src, s["rtmp_url"],
            start_offset=offset,
            audio_bitrate=s.get("audio_bitrate") or "128k",
            volume=float(s.get("volume") or 1.0),
            with_video=use_video,
            media_kind=probe.get("media_kind") or ("video" if use_video else "audio"),
            has_audio=probe.get("has_audio"),
            has_video=probe.get("has_video"),
            source_type=probe.get("source_type") or "",
            probe_result=probe,
        )
        if pid:
            await db.update_stream_status(stream_id, "running", pid)
            await db.add_stream_log(stream_id, query.from_user.id, "started", "manual start")
            await query.answer("✅ تم التشغيل")
        else:
            await query.answer("❌ فشل التشغيل", show_alert=True)
            await db.update_stream_error(stream_id, "فشل تشغيل FFmpeg")
        await _refresh_status(update, context, stream_id)
    except Exception as e:
        logger.exception(e)


async def stream_stop_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    try:
        stream_id = int(query.data.split(":")[1])
        s = await db.get_stream(stream_id)
        if not s or s["user_id"] != query.from_user.id:
            await query.answer("غير مسموح", show_alert=True)
            return
        stream_manager.stop_stream(stream_id)
        await db.update_stream_status(stream_id, "stopped")
        await query.answer("⏹ تم الإيقاف")
        # Optional auto-archive for complete VOD sources only
        try:
            from config import AUTO_ARCHIVE_ON_STOP, ARCHIVE_CHANNEL_ID
            if AUTO_ARCHIVE_ON_STOP and ARCHIVE_CHANNEL_ID and s.get("source_url"):
                from services import archive as arch_svc
                ok, dur, reason = arch_svc.is_archivable(s["source_url"])
                if ok:
                    # fire-and-forget background archive
                    import asyncio
                    async def _bg():
                        try:
                            await arch_svc.archive_url_to_channel(
                                context.bot,
                                url=s["source_url"],
                                title=s.get("title") or f"بث #{stream_id}",
                                channel_id=ARCHIVE_CHANNEL_ID,
                                uploaded_by=query.from_user.id,
                            )
                        except Exception as ex:
                            logger.warning("auto-archive: %s", ex)
                    asyncio.create_task(_bg())
        except Exception as ex:
            logger.debug("auto-archive skip: %s", ex)
        await _refresh_status(update, context, stream_id)
    except Exception as e:
        logger.exception(e)


async def stream_delete_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """حذف بث نهائياً من قاعدة البيانات بعد إيقافه."""
    query = update.callback_query
    await query.answer()
    try:
        stream_id = int(query.data.split(":")[1])
        s = await db.get_stream(stream_id)
        if not s:
            await query.answer("غير موجود", show_alert=True)
            return
        uid = query.from_user.id
        if s["user_id"] != uid and not is_admin(uid, ADMIN_ID):
            await query.answer("غير مسموح", show_alert=True)
            return
        # stop first if running
        if stream_manager.is_running(stream_id):
            stream_manager.stop_stream(stream_id)
        ok = await db.delete_stream(stream_id, user_id=None if is_admin(uid, ADMIN_ID) else uid)
        if ok:
            await query.answer("🗑 تم حذف البث")
            await query.edit_message_text(
                f"✅ تم حذف البث #{stream_id} بنجاح.",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("📡 البثوث", callback_data="current_stream")],
                    [InlineKeyboardButton("🔙 القائمة", callback_data="main_menu")],
                ]),
            )
        else:
            await query.answer("فشل الحذف", show_alert=True)
    except Exception as e:
        logger.exception(e)


async def stream_restart_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer("🔄 إعادة تشغيل...")
    try:
        sid = int(query.data.split(":")[1])
        s = await db.get_stream(sid)
        if not s or s["user_id"] != query.from_user.id:
            await query.answer("غير مسموح", show_alert=True)
            return
        # stop_stream removes in-memory metadata, so restart_stream cannot
        # restart it. Reuse the DB-backed start path instead.
        query.data = f"stream_start:{sid}"
        await stream_start_callback(update, context)
    except Exception as e:
        logger.exception(e)


async def stream_vol_up_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    sid = int(query.data.split(":")[1])
    vol = stream_manager.volume_delta(sid, 0.1)
    await query.answer(f"🔊 {int((vol or 0)*100)}%")
    await _refresh_status(update, context, sid)


async def stream_vol_down_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    sid = int(query.data.split(":")[1])
    vol = stream_manager.volume_delta(sid, -0.1)
    await query.answer(f"🔉 {int((vol or 0)*100)}%")
    await _refresh_status(update, context, sid)


async def stream_mute_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    sid = int(query.data.split(":")[1])
    meta = stream_manager.get_meta(sid)
    muted = not meta.get("muted", False)
    stream_manager.mute(sid, muted)
    await query.answer("🔇 مكتوم" if muted else "🔈 الصوت عاد")
    await _refresh_status(update, context, sid)


async def stream_br_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    parts = query.data.split(":")
    sid, br = int(parts[1]), parts[2]
    stream_manager.set_bitrate(sid, br)
    await query.answer(f"🎵 {br}")
    await _refresh_status(update, context, sid)


# --------------------------------------------------------------------------- #
# Playlist controls
# --------------------------------------------------------------------------- #
