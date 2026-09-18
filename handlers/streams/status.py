"""Stream status display and auto-refresh."""
from __future__ import annotations

import asyncio
import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes

from database import db
from services.stream import stream_manager
from keyboards.menus import stream_actions_keyboard, main_menu, main_reply_keyboard
from utils.helpers import stream_uptime, is_admin, safe_edit_message
from config import ADMIN_ID
from utils.visualizer import build_live_panel

from .common import _STATUS_TASKS, _STATUS_TICK, _stop_auto_refresh, cancel_all_status_tasks, _safe_update_reply

logger = logging.getLogger(__name__)

async def current_stream_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    msg = None
    if query:
        try:
            await query.answer()
        except Exception:
            pass
        msg = query.message
        user_id = query.from_user.id
    else:
        msg = update.message
        user_id = update.effective_user.id

    try:
        streams = await db.get_active_streams() or []
        if not streams:
            text = "📡 <b>البث الحالي</b>\n\n🔴 لا يوجد بث يعمل حالياً.\n\nأنشئ بثاً من القائمة أو شغّل محطة/قناة."
            kb = InlineKeyboardMarkup([
                [InlineKeyboardButton("🚀 إنشاء بث", callback_data="stream_new")],
                [InlineKeyboardButton("🔙 رجوع", callback_data="main_menu")],
            ])
            if query:
                await safe_edit_message(query, text, parse_mode="HTML", reply_markup=kb)
            else:
                await msg.reply_text(text, parse_mode="HTML", reply_markup=kb)
            return

        text = "📡 <b>البثوث الحالية</b>\n\nكل البثوث النشطة تظهر هنا مع اسم صاحب البث.\n\n"
        buttons = []
        for s in streams[:10]:
            try:
                sid = int(s.get("id"))
                title = html.escape(str(s.get("title") or "بث بدون عنوان")[:40])
                status = str(s.get("status") or "stopped")
                state = stream_manager.get_state(sid) or "stopped"
                running = bool(stream_manager.is_running(sid))
                healthy = bool(stream_manager.is_healthy(sid))
                if status == "running" and not running and state == "stopped":
                    try:
                        await db.update_stream_status(sid, "stopped")
                    except Exception:
                        pass
                if healthy:
                    icon = "🟢"
                elif running or state == "reconnecting":
                    icon = "🟡"
                else:
                    icon = "🔴"
                try:
                    uptime = stream_uptime(s.get("started_at")) if running else "—"
                except Exception:
                    uptime = "—"
                owner = s.get("user_id")
                owner_user = await db.get_user(int(owner)) if owner else None
                owner_name = (owner_user or {}).get("first_name") or (owner_user or {}).get("username") or str(owner or "—")
                owner_name = html.escape(str(owner_name)[:22])
                text += f"{icon} <b>#{sid}</b> {title}\n👤 {owner_name}\n⏱ {uptime}\n\n"
                buttons.append([
                    InlineKeyboardButton(
                        f"{icon} #{sid} {str(s.get('title') or 'بث')[:20]}",
                        callback_data=f"stream_status:{sid}",
                    )
                ])
            except Exception as row_error:
                logger.warning("Skipping malformed stream row in current_stream: %s", row_error)
        buttons.append([
            InlineKeyboardButton("🔄 تحديث", callback_data="current_stream"),
            InlineKeyboardButton("🔙 رجوع", callback_data="main_menu"),
        ])
        if query:
            await safe_edit_message(query, text, parse_mode="HTML", reply_markup=InlineKeyboardMarkup(buttons))
        else:
            await msg.reply_text(text, parse_mode="HTML", reply_markup=InlineKeyboardMarkup(buttons))
    except Exception as e:
        logger.exception("current_stream_callback: %s", e)
        if "not modified" in str(e).lower():
            try:
                await query.answer("ℹ️ القائمة محدثة بالفعل")
            except Exception:
                pass
            return
        fallback = "📡 <b>البث الحالي</b>\n\nتعذر تحديث القائمة الآن. جرّب تحديثها بعد لحظات."
        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("🔄 تحديث", callback_data="current_stream")],
            [InlineKeyboardButton("🔙 رجوع", callback_data="main_menu")],
        ])
        if query:
            try:
                await safe_edit_message(query, fallback, parse_mode="HTML", reply_markup=kb)
            except Exception:
                try:
                    await query.answer("⚠️ تعذر تحديث القائمة", show_alert=True)
                except Exception:
                    pass
        else:
            try:
                await msg.reply_text(fallback, parse_mode="HTML", reply_markup=kb)
            except Exception:
                pass


async def stream_status_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    try:
        stream_id = int(query.data.split(":")[1])
        s = await db.get_stream(stream_id)
        if not s:
            await safe_edit_message(query, "❌ البث غير موجود.")
            return
        can_control = (s.get("user_id") == query.from_user.id or is_admin(query.from_user.id, ADMIN_ID))
        running = stream_manager.is_running(stream_id)
        if running != (s["status"] == "running"):
            await db.update_stream_status(stream_id, "running" if running else "stopped")

        uptime = stream_uptime(s.get("started_at")) if running else "00:00:00"
        key = (query.message.chat_id, query.message.message_id)
        tick = _STATUS_TICK.get(key, 0)
        _STATUS_TICK[key] = tick + 1

        meta = stream_manager.get_meta(stream_id)
        state = stream_manager.get_state(stream_id)
        healthy = stream_manager.is_healthy(stream_id) if running else False
        text = build_live_panel(
            title=s.get("title") or "بث",
            stream_id=stream_id,
            running=running,
            uptime=uptime,
            tick=tick,
            state=state,
            volume=meta.get("volume", 1.0),
            bitrate=meta.get("audio_bitrate", "128k"),
            restarts=meta.get("restarts", 0),
            last_error=meta.get("last_error", "") or (s.get("last_error") or ""),
            ffmpeg_ok=running and await asyncio.to_thread(stream_manager.has_ffmpeg),
            rtmp_ok=healthy,
            source_ok=bool(meta.get("data_flow")),
            codec_info=meta.get("codec_info", f"AAC {meta.get('audio_bitrate', '128k')} · 48kHz Stereo"),
            quality="عالي" if "192" in str(meta.get("audio_bitrate", "")) else ("منخفض" if "64" in str(meta.get("audio_bitrate", "")) else "متوسط"),
        )
        await safe_edit_message(
            query,
            text,
            parse_mode="HTML",
            reply_markup=stream_actions_keyboard(stream_id, running, can_control=can_control),
        )

        # Auto-refresh while ON AIR
        if running:
            await _ensure_auto_refresh(context, query.message.chat_id, query.message.message_id, stream_id, can_control)
        else:
            await _stop_auto_refresh(query.message.chat_id, query.message.message_id)
    except Exception as e:
        logger.exception(e)


async def _ensure_auto_refresh(context, chat_id: int, message_id: int, stream_id: int, can_control: bool = False):
    key = (chat_id, message_id)
    old = _STATUS_TASKS.get(key)
    if old and not old.done():
        return  # already refreshing

    async def _loop():
        try:
            for _ in range(240):  # ~6 min at 1.5s
                await asyncio.sleep(1.5)
                s = await db.get_stream(stream_id)
                if not s:
                    break
                running = stream_manager.is_running(stream_id)
                state = stream_manager.get_state(stream_id)
                if not running and state == "stopped":
                    uptime = "00:00:00"
                    text = build_live_panel(
                        s.get("title") or "بث", stream_id, False, uptime, 0,
                        state="stopped", ffmpeg_ok=False, rtmp_ok=False, source_ok=False,
                    )
                    try:
                        await context.bot.edit_message_text(
                            chat_id=chat_id,
                            message_id=message_id,
                            text=text,
                            parse_mode="HTML",
                            reply_markup=stream_actions_keyboard(stream_id, False, can_control=can_control),
                        )
                    except Exception:
                        pass
                    break
                uptime = stream_uptime(s.get("started_at"))
                tick = _STATUS_TICK.get(key, 0) + 1
                _STATUS_TICK[key] = tick
                meta = stream_manager.get_meta(stream_id)
                healthy = stream_manager.is_healthy(stream_id)
                text = build_live_panel(
                    s.get("title") or "بث", stream_id, True, uptime, tick,
                    state=stream_manager.get_state(stream_id),
                    volume=meta.get("volume", 1.0),
                    bitrate=meta.get("audio_bitrate", "128k"),
                    restarts=meta.get("restarts", 0),
                    last_error=meta.get("last_error", ""),
                    ffmpeg_ok=True,
                    rtmp_ok=healthy,
                    source_ok=bool(meta.get("data_flow")),
                    codec_info=meta.get("codec_info", f"AAC {meta.get('audio_bitrate', '128k')} · 48kHz Stereo"),
                    quality="عالي" if "192" in str(meta.get("audio_bitrate", "")) else ("منخفض" if "64" in str(meta.get("audio_bitrate", "")) else "متوسط"),
                )
                try:
                    await context.bot.edit_message_text(
                        chat_id=chat_id,
                        message_id=message_id,
                        text=text,
                        parse_mode="HTML",
                        reply_markup=stream_actions_keyboard(stream_id, True),
                    )
                except Exception as e:
                    # message deleted or not modified
                    err = str(e).lower()
                    if "not found" in err or "message to edit not found" in err:
                        break
            _STATUS_TASKS.pop(key, None)
        except asyncio.CancelledError:
            pass
        except Exception as e:
            logger.exception("auto-refresh error: %s", e)
            _STATUS_TASKS.pop(key, None)

    _STATUS_TASKS[key] = asyncio.create_task(_loop())


