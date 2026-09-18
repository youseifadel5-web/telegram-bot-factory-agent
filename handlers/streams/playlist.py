"""Playlist controls for active streams."""
from __future__ import annotations

import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes

from database import db
from services.stream import stream_manager
from keyboards.menus import stream_actions_keyboard
from utils.helpers import is_admin, safe_edit_message
from config import ADMIN_ID

logger = logging.getLogger(__name__)
from services import playlist as playlist_service

async def _get_or_create_pl(user_id: int, stream_id: int, s: dict) -> int:
    return await playlist_service.ensure_playlist_for_stream(
        user_id, stream_id, s.get("title"), s.get("source_url"),
    )


async def pl_view_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    try:
        sid = int(query.data.split(":")[1])
        s = await db.get_stream(sid)
        if not s or (s["user_id"] != query.from_user.id and not is_admin(query.from_user.id, ADMIN_ID)):
            await query.answer("غير مسموح", show_alert=True)
            return
        pid = await _get_or_create_pl(query.from_user.id, sid, s)
        text = await playlist_service.format_playlist_text(pid)
        kb = InlineKeyboardMarkup([
            [
                InlineKeyboardButton("⬅️", callback_data=f"pl_prev:{sid}"),
                InlineKeyboardButton("➡️", callback_data=f"pl_next:{sid}"),
            ],
            [
                InlineKeyboardButton("🔀", callback_data=f"pl_shuffle:{sid}"),
                InlineKeyboardButton("🔁", callback_data=f"pl_loop:{sid}"),
            ],
            [InlineKeyboardButton("🔙 رجوع للبث", callback_data=f"stream_status:{sid}")],
        ])
        await query.edit_message_text(text, parse_mode="Markdown", reply_markup=kb)
    except Exception as e:
        logger.exception(e)


async def pl_next_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    try:
        sid = int(query.data.split(":")[1])
        s = await db.get_stream(sid)
        if not s or s["user_id"] != query.from_user.id:
            await query.answer("غير مسموح", show_alert=True)
            return
        pid = await _get_or_create_pl(query.from_user.id, sid, s)
        item = await playlist_service.next_item(pid)
        if not item:
            await query.answer("وصلت لنهاية القائمة", show_alert=True)
            return
        # switch source and restart if running
        await db.update_stream_meta(sid, source_url=item["source_url"], title=item.get("title") or s.get("title"))
        if stream_manager.is_running(sid) and s.get("rtmp_url"):
            stream_manager.stop_stream(sid)
            from services.source_probe import looks_like_video as _llv
            pid_ff = await asyncio.to_thread(
                stream_manager.start_stream,
                sid, item["source_url"], s["rtmp_url"],
                with_video=_llv(item.get("source_url") or ""),
            )
            if pid_ff:
                await db.update_stream_status(sid, "running", pid_ff)
        await query.answer(f"➡️ {item.get('title') or 'التالي'}")
        await stream_status_callback(update, context)
    except Exception as e:
        logger.exception(e)
        await query.answer("خطأ", show_alert=True)


async def pl_prev_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    try:
        sid = int(query.data.split(":")[1])
        s = await db.get_stream(sid)
        if not s or s["user_id"] != query.from_user.id:
            await query.answer("غير مسموح", show_alert=True)
            return
        pid = await _get_or_create_pl(query.from_user.id, sid, s)
        item = await playlist_service.prev_item(pid)
        if not item:
            await query.answer("لا يوجد عنصر سابق", show_alert=True)
            return
        await db.update_stream_meta(sid, source_url=item["source_url"], title=item.get("title") or s.get("title"))
        if stream_manager.is_running(sid) and s.get("rtmp_url"):
            stream_manager.stop_stream(sid)
            from services.source_probe import looks_like_video as _llv
            pid_ff = await asyncio.to_thread(
                stream_manager.start_stream,
                sid, item["source_url"], s["rtmp_url"],
                with_video=_llv(item.get("source_url") or ""),
            )
            if pid_ff:
                await db.update_stream_status(sid, "running", pid_ff)
        await query.answer(f"⬅️ {item.get('title') or 'السابق'}")
        await stream_status_callback(update, context)
    except Exception as e:
        logger.exception(e)
        await query.answer("خطأ", show_alert=True)


async def pl_shuffle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    try:
        sid = int(query.data.split(":")[1])
        s = await db.get_stream(sid)
        if not s or s["user_id"] != query.from_user.id:
            await query.answer("غير مسموح", show_alert=True)
            return
        pid = await _get_or_create_pl(query.from_user.id, sid, s)
        on = await playlist_service.toggle_shuffle(pid)
        await query.answer("🔀 عشوائي: تشغيل" if on else "🔀 عشوائي: إيقاف")
    except Exception as e:
        logger.exception(e)


async def pl_loop_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    try:
        sid = int(query.data.split(":")[1])
        s = await db.get_stream(sid)
        if not s or s["user_id"] != query.from_user.id:
            await query.answer("غير مسموح", show_alert=True)
            return
        pid = await _get_or_create_pl(query.from_user.id, sid, s)
        mode = await playlist_service.cycle_loop(pid)
        labels = {"none": "بدون تكرار", "all": "تكرار الكل", "one": "تكرار العنصر"}
        await query.answer(f"🔁 {labels.get(mode, mode)}")
    except Exception as e:
        logger.exception(e)


# --------------------------------------------------------------------------- #
# Stations (JSON-defined channels with backup/failover sources)
# --------------------------------------------------------------------------- #
from services import stations as stations_service


