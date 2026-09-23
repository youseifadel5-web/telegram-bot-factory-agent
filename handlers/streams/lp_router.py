"""Unified router for the namespaced `lp:` callback family on the live stream
control panel. This keeps `main.py` registration to a SINGLE handler entry,
so adding new actions later only touches this file instead of the wiring.

Each callback_data has the shape `lp:<action>:<sid>[:extra]` so the bound
stream id is always the trailing positional field — easy to parse.
"""
from __future__ import annotations

import asyncio
import html
import logging

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes

from database import db
from services.stream import stream_manager
from services import playlist as playlist_service
from services import stations as stations_service
from utils.helpers import is_admin, safe_edit_message
from config import ADMIN_ID
from keyboards.menus import stream_actions_keyboard, stream_submenu_keyboard

from .status import _refresh_status, stream_status_callback

logger = logging.getLogger(__name__)


def _parse(data: str) -> tuple:
    """Returns (action, sid, extra) from a `lp:...` callback string."""
    parts = (data or "").split(":")
    action = parts[1] if len(parts) > 1 else ""
    try:
        sid = int(parts[2]) if len(parts) > 2 else 0
    except Exception:
        sid = 0
    extra = parts[3] if len(parts) > 3 else ""
    return action, sid, extra


async def _can_control(query, s: dict) -> bool:
    uid = query.from_user.id
    owner_id = s.get("user_id")
    return bool(s) and (str(owner_id) == str(uid) or is_admin(uid, ADMIN_ID))


async def _back_to_panel(query, context, s: dict):
    """Re-render the live panel after a successful action."""
    query.data = f"stream_status:{int(s['id'])}"
    await stream_status_callback(query if isinstance(query, Update) else query, context)


async def lp_router(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if not query:
        return
    try:
        await query.answer()
    except Exception:
        pass
    try:
        action, sid, extra = _parse(query.data or "")
        # This informational button intentionally has no stream id.
        if action == "change_na":
            await query.answer("أوقف البث أولاً لتغيير المصدر", show_alert=True)
            return
        if not action or not sid:
            return
        s = await db.get_stream(sid)
        if not s:
            try:
                await query.answer("❌ البث غير موجود", show_alert=True)
            except Exception:
                pass
            return
        if not await _can_control(query, s):
            try:
                await query.answer("غير مسموح", show_alert=True)
            except Exception:
                pass
            return

        # --- playback controls ---
        if action == "start":
            query.data = f"stream_start:{sid}"
            from .control import stream_start_callback
            await stream_start_callback(update, context)
            return
        if action == "stop":
            # Friendly confirm before actually killing a live stream.
            if stream_manager.is_running(sid):
                kb = InlineKeyboardMarkup([
                    [
                        InlineKeyboardButton("✅ نعم، أوقف", callback_data=f"lp:stop_confirm:{sid}"),
                        InlineKeyboardButton("↩️ إلغاء", callback_data=f"stream_status:{sid}"),
                    ],
                ])
                await safe_edit_message(
                    query,
                    f"⚠️ <b>تأكيد إيقاف البث #{sid}</b>\n\n"
                    f"{html.escape(str(s.get('title') or '—'))}\n"
                    "بعد الإيقاف يمكنك إعادة التشغيل من نفس اللوحة.",
                    parse_mode="HTML", reply_markup=kb,
                )
                return
            await query.answer("البث متوقف بالفعل")
            query.data = f"stream_status:{sid}"
            await stream_status_callback(update, context)
            return
        if action == "stop_confirm":
            from .control import stream_stop_callback
            query.data = f"stream_stop:{sid}"
            await stream_stop_callback(update, context)
            return
        if action == "restart":
            from .control import stream_restart_callback
            query.data = f"stream_restart:{sid}"
            await stream_restart_callback(update, context)
            return

        # --- volume ---
        if action == "vol_plus":
            from .control import stream_vol_up_callback
            query.data = f"stream_vol_up:{sid}"
            await stream_vol_up_callback(update, context)
            return
        if action == "vol_minus":
            from .control import stream_vol_down_callback
            query.data = f"stream_vol_down:{sid}"
            await stream_vol_down_callback(update, context)
            return
        if action == "mute":
            from .control import stream_mute_callback
            query.data = f"stream_mute:{sid}"
            await stream_mute_callback(update, context)
            return

        # --- bitrate (3 quick presets wired to the real ffmpeg path) ---
        if action == "br":
            from .control import stream_br_callback
            query.data = f"stream_br:{sid}:{extra}"
            await stream_br_callback(update, context)
            return

        # --- playlist ---
        if action == "pl_view":
            from .playlist import pl_view_callback
            query.data = f"pl_view:{sid}"
            await pl_view_callback(update, context)
            return
        if action == "pl_next":
            from .playlist import pl_next_callback
            query.data = f"pl_next:{sid}"
            await pl_next_callback(update, context)
            return
        if action == "pl_prev":
            from .playlist import pl_prev_callback
            query.data = f"pl_prev:{sid}"
            await pl_prev_callback(update, context)
            return
        if action == "pl_shuffle":
            from .playlist import pl_shuffle_callback
            query.data = f"pl_shuffle:{sid}"
            await pl_shuffle_callback(update, context)
            return
        if action == "pl_loop":
            from .playlist import pl_loop_callback
            query.data = f"pl_loop:{sid}"
            await pl_loop_callback(update, context)
            return

        # --- metadata actions ---
        if action == "logs":
            from .stations import stream_logs_callback
            query.data = f"stream_logs:{sid}"
            await stream_logs_callback(update, context)
            return
        if action == "stats":
            from .stations import stream_stats_callback
            query.data = f"stream_stats:{sid}"
            await stream_stats_callback(update, context)
            return
        if action == "clone":
            from .stations import stream_clone_callback
            query.data = f"stream_clone:{sid}"
            await stream_clone_callback(update, context)
            return
        if action == "fav":
            from .stations import stream_fav_callback
            query.data = f"stream_fav:{sid}"
            await stream_fav_callback(update, context)
            return
        if action == "archive":
            # archive-from-stream expects `arch_stream:<id>`
            from handlers.archive import archive_from_stream_callback
            query.data = f"arch_stream:{sid}"
            await archive_from_stream_callback(update, context)
            return
        if action == "delete":
            kb = InlineKeyboardMarkup([
                [
                    InlineKeyboardButton("✅ نعم، احذف", callback_data=f"lp:delete_confirm:{sid}"),
                    InlineKeyboardButton("↩️ إلغاء", callback_data=f"stream_status:{sid}"),
                ],
            ])
            await safe_edit_message(
                query,
                f"⚠️ <b>تأكيد حذف البث #{sid}</b>\n\nسيتم حذف السجل نهائياً.",
                parse_mode="HTML", reply_markup=kb,
            )
            return
        if action == "delete_confirm":
            from .control import stream_delete_callback
            query.data = f"stream_delete:{sid}"
            await stream_delete_callback(update, context)
            return

        # --- expand / collapse ---
        if action == "more":
            from .status import stream_submenu_callback
            query.data = f"stream_submenu:{sid}"
            await stream_submenu_callback(update, context)
            return

        # --- inline source change ---
        if action == "change_src":
            from .status import stream_change_source_callback
            query.data = f"stream_change_src:{sid}"
            await stream_change_source_callback(update, context)
            return
        await query.answer("⚠️ إجراء غير معروف", show_alert=True)
    except Exception as e:
        logger.exception("lp_router: %s", e)
        try:
            await query.answer("⚠️ تعذر تنفيذ الطلب", show_alert=True)
        except Exception:
            pass
