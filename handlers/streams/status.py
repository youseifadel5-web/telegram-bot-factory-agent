"""Stream status display and auto-refresh.

All callbacks here are live: the message is re-edited on an interval by a
background task keyed on (chat_id, message_id) because Telegram apps do not
animate inline messages themselves.
"""
from __future__ import annotations

import html
import asyncio
import logging
from typing import Iterable, List

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes

from database import db
from services.stream import stream_manager
from keyboards.menus import (
    stream_actions_keyboard,
    streams_list_keyboard,
    stream_submenu_keyboard,
)
from utils.helpers import stream_uptime, is_admin, safe_edit_message
from config import ADMIN_ID
from utils.visualizer import build_live_panel

from .common import _STATUS_TASKS, _STATUS_TICK, _stop_auto_refresh, _safe_update_reply

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _quality_label(meta: dict) -> str:
    """Human label for live panel quality row."""
    q = (meta or {}).get("quality")
    if q:
        try:
            from services.quality_manager import label_for
            return label_for(q)
        except Exception:
            return str(q)
    br = str((meta or {}).get("audio_bitrate") or "")
    if "192" in br:
        return "عالي"
    if "64" in br:
        return "منخفض"
    return "متوسط"


def _row_icon_and_state(stream: dict) -> tuple:
    """State derived purely from live process state (truthful, no animation)."""
    sid = int(stream.get("id") or 0)
    status = str(stream.get("status") or "stopped")
    state = stream_manager.get_state(sid) or "stopped"
    running = bool(stream_manager.is_running(sid))
    healthy = bool(stream_manager.is_healthy(sid)) if running else False
    if healthy:
        return "🟢", "ON AIR"
    if running or state in ("reconnecting", "restarting", "connecting", "starting"):
        if state in ("connecting", "starting"):
            return "🟡", "جاري الاتصال"
        if state == "reconnecting":
            return "🟠", "إعادة اتصال"
        return "🟡", "يعمل"
    if state == "stalled":
        return "🟠", "متوقف مؤقتاً"
    if state in ("failed", "error"):
        return "🔴", "فشل"
    return "🔴", "متوقف" if status in ("stopped", "") else "متوقف"


async def _refresh_status(update, context, stream_id: int):
    """Re-render the stream status panel after any action button."""
    query = update.callback_query
    if not query:
        return
    original = query.data
    query.data = f"stream_status:{stream_id}"
    try:
        await stream_status_callback(update, context)
    finally:
        query.data = original


# ---------------------------------------------------------------------------
# List picker (both running and stopped) — auto-refreshes while any live
# ---------------------------------------------------------------------------
async def current_stream_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show ALL broadcasts (running + stopped) so the user can pick any of them."""
    query = update.callback_query
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
        # Combine DB-known running + any in-memory process the DB hasn't seen yet
        streams_db = await db.get_user_streams(user_id) or []
        active_sid = stream_manager.get_active_stream_id()
        seen_ids = {int(s.get("id") or 0) for s in streams_db if s.get("id") is not None}
        if active_sid and active_sid not in seen_ids:
            try:
                active_row = await db.get_stream(active_sid)
                if active_row:
                    streams_db.append(active_row)
                    seen_ids.add(active_sid)
            except Exception:
                pass
        # Final sort: running first, then recently stopped, oldest last
        def _sort_key(s):
            sid = int(s.get("id") or 0)
            running = 0 if stream_manager.is_running(sid) else 1
            return (running, -sid)
        streams_db.sort(key=_sort_key)
        await _render_streams_list(update, context, streams_db, user_id=user_id, page=1)
    except Exception as e:
        logger.exception("current_stream_callback: %s", e)
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


async def _render_streams_list(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    streams: Iterable[dict],
    *,
    user_id: int,
    page: int = 1,
):
    """Render the paginated list selector. Auto-refreshes while any process is live."""
    query = update.callback_query
    msg = (query.message if query else update.message)
    per = 8
    streams = list(streams or [])
    total = len(streams)
    pages = max(1, (total + per - 1) // per)
    page = max(1, min(page, pages))
    chunk = streams[(page - 1) * per: page * per]
    any_live = any(stream_manager.is_running(int(s.get("id") or 0)) for s in streams)

    if not chunk:
        text = "📡 <b>حالة البث</b>\n\n🔴 لا يوجد أي بث (لا يعمل ولا متوقف).\n\nأنشئ بثاً جديداً من القائمة أو شغّل محطة/قناة."
        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("🚀 إنشاء بث جديد", callback_data="stream_new")],
            [InlineKeyboardButton("🔄 تحديث", callback_data="current_stream"),
             InlineKeyboardButton("🔙 القائمة", callback_data="main_menu")],
        ])
    else:
        live_count = sum(1 for s in streams if stream_manager.is_running(int(s.get("id") or 0)))
        stopped_count = total - live_count
        text = (
            "📡 <b>حالة البث</b>\n\n"
            f"🟢 يعمل الآن: <b>{live_count}</b> · 🔴 متوقف/فشل: <b>{stopped_count}</b>\n"
            f"صفحة {page}/{pages}\n\n"
            "اختر بثاً للتحكم به أو لمتابعة التفاصيل:"
        )
        buttons: List[List[InlineKeyboardButton]] = []
        for s in chunk:
            sid = int(s.get("id") or 0)
            icon, state_ar = _row_icon_and_state(s)
            try:
                uptime = stream_uptime(s.get("started_at")) if stream_manager.is_running(sid) else "—"
            except Exception:
                uptime = "—"
            title = html.escape(str(s.get("title") or "بث")[:30])
            up_short = (uptime if uptime not in ("—", "00:00:00") else state_ar)
            btn_text = f"{icon} #{sid} {title} · {up_short}"[:64]
            buttons.append([InlineKeyboardButton(btn_text, callback_data=f"stream_status:{sid}")])
        nav: List[InlineKeyboardButton] = []
        if page > 1:
            nav.append(InlineKeyboardButton("◀ السابق", callback_data=f"current_stream:p{page-1}"))
        if pages > 1:
            nav.append(InlineKeyboardButton(f"{page}/{pages}", callback_data="noop"))
        if page < pages:
            nav.append(InlineKeyboardButton("التالي ▶", callback_data=f"current_stream:p{page+1}"))
        if nav:
            buttons.append(nav)
        buttons.append([
            InlineKeyboardButton("🔄 تحديث", callback_data="current_stream"),
            InlineKeyboardButton("🚀 إنشاء", callback_data="stream_new"),
            InlineKeyboardButton("🔙 القائمة", callback_data="main_menu"),
        ])
        kb = InlineKeyboardMarkup(buttons)

    if query:
        await safe_edit_message(query, text, parse_mode="HTML", reply_markup=kb)
    else:
        await msg.reply_text(text, parse_mode="HTML", reply_markup=kb)

    # Auto-refresh the list every ~3 s while at least one broadcast is live
    if any_live:
        await _ensure_list_refresh(context, msg.chat_id, msg.message_id, user_id, page)


async def current_stream_page_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Paginate streams list — wired to current_stream:p{n}."""
    query = update.callback_query
    await query.answer()
    try:
        page = int(query.data.split("p")[-1])
        user_id = query.from_user.id
        streams = await db.get_user_streams(user_id) or []
        active_sid = stream_manager.get_active_stream_id()
        seen_ids = {int(s.get("id") or 0) for s in streams if s.get("id") is not None}
        if active_sid and active_sid not in seen_ids:
            try:
                active_row = await db.get_stream(active_sid)
                if active_row:
                    streams.append(active_row)
                    seen_ids.add(active_sid)
            except Exception:
                pass
        def _sort_key(s):
            sid = int(s.get("id") or 0)
            running = 0 if stream_manager.is_running(sid) else 1
            return (running, -sid)
        streams.sort(key=_sort_key)
        await _render_streams_list(update, context, streams, user_id=user_id, page=page)
    except Exception as e:
        logger.exception("current_stream_page: %s", e)


# ---------------------------------------------------------------------------
# Per-stream detail panel — auto-refreshes while ON AIR
# ---------------------------------------------------------------------------
async def stream_status_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Render detailed live panel for a specific stream."""
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

        # Reconcile DB status with real process state — keeps the UI truthful
        if not running and s["status"] == "running":
            try:
                await db.update_stream_status(stream_id, "stopped")
            except Exception:
                pass

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
            quality=_quality_label(meta),
            meta=meta,
        )
        await safe_edit_message(
            query,
            text,
            parse_mode="HTML",
            reply_markup=stream_actions_keyboard(stream_id, running, can_control=can_control),
        )

        if running:
            await _ensure_auto_refresh(context, query.message.chat_id, query.message.message_id, stream_id, can_control)
        else:
            await _stop_auto_refresh(query.message.chat_id, query.message.message_id)
            # For stopped streams — start a slower refresh so PID/restart_count stay fresh
            await _ensure_stopped_refresh(context, query.message.chat_id, query.message.message_id, stream_id, can_control)
    except Exception as e:
        logger.exception(e)


# ---------------------------------------------------------------------------
# Submenu: a single page with change-stream / stop / quality / shuffle / loop
# ---------------------------------------------------------------------------
async def stream_submenu_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Open the collapsible ⬇️ submenu for one stream (handler alias for lp_router)."""
    query = update.callback_query
    await query.answer("⬇️ فتح القائمة الفرعية")
    try:
        stream_id = int(query.data.split(":")[1])
        s = await db.get_stream(stream_id)
        if not s or (s.get("user_id") != query.from_user.id and not is_admin(query.from_user.id, ADMIN_ID)):
            await query.answer("غير مسموح", show_alert=True)
            return
        running = stream_manager.is_running(stream_id)
        meta = stream_manager.get_meta(stream_id) or {}
        # Header echoes the live state so the user sees what they're controlling
        q_label = _quality_label(meta)
        vol = int(round(float(meta.get("volume", 1.0)) * 100))
        state_ar, _ = _row_icon_and_state(s)
        text = (
            "🎛 <b>قائمة التحكم المتقدمة</b>\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"📌 <b>#{stream_id}</b> {html.escape(str(s.get('title') or 'بث')[:40])}\n"
            f"الحالة: {state_ar} · 🎚 {vol}% · 🎵 {meta.get('audio_bitrate', '128k')} · 🎞 {q_label}\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            "اختر إجراءً من الأزرار بالأسفل:"
        )
        kb = stream_submenu_keyboard(stream_id, running, can_control=True)
        await safe_edit_message(query, text, parse_mode="HTML", reply_markup=kb)
    except Exception as e:
        logger.exception("stream_submenu: %s", e)


# ---------------------------------------------------------------------------
# Quality / volume / mute / change-source inline helpers
# ---------------------------------------------------------------------------
async def stream_change_source_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    try:
        stream_id = int(query.data.split(":")[1])
        s = await db.get_stream(stream_id)
        if not s or (s.get("user_id") != query.from_user.id and not is_admin(query.from_user.id, ADMIN_ID)):
            await query.answer("غير مسموح", show_alert=True)
            return
        # Stop current stream and queue a re-prompt for new source
        if stream_manager.is_running(stream_id):
            stream_manager.stop_stream(stream_id)
        context.user_data["await_change_stream_id"] = stream_id
        await query.edit_message_text(
            f"🔁 <b>تغيير المصدر للبث #{stream_id}</b>\n\n"
            "أرسل رابط المصدر الجديد (HLS / MP4 / M3U8 / رابط مباشر):\n"
            "أو ألغِ بالضغط على 🔙 رجوع للبث.",
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🔙 رجوع للبث", callback_data=f"stream_status:{stream_id}")],
            ]),
        )
    except Exception as e:
        logger.exception("change_source: %s", e)


async def change_source_receive(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Text handler that finishes the change-source flow."""
    sid = context.user_data.pop("await_change_stream_id", None)
    if not sid:
        return False
    url = (update.message.text or "").strip()
    if not url.startswith(("http://", "https://", "rtmp://", "rtmps://")):
        await update.message.reply_text("❌ أرسل رابط صالح يبدأ بـ http(s):// أو rtmp(s)://")
        context.user_data["await_change_stream_id"] = sid
        return True
    s = await db.get_stream(int(sid))
    if not s or (s.get("user_id") != update.effective_user.id and not is_admin(update.effective_user.id, ADMIN_ID)):
        await update.message.reply_text("❌ البث غير موجود أو غير مصرح لك.")
        return True
    await db.update_stream_meta(int(sid), source_url=url)
    await update.message.reply_text(
        f"✅ تم تحديث المصدر للبث <code>#{sid}</code>.\nإذا كان يعمل سيتم تشغيل العنصر الجديد تلقائياً.",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("📊 فتح اللوحة", callback_data=f"stream_status:{sid}")],
            [InlineKeyboardButton("🔙 القائمة", callback_data="main_menu")],
        ]),
    )
    # If still running, stop & restart so the new source is picked up
    if stream_manager.is_running(int(sid)) and s.get("rtmp_url"):
        from handlers.streams.control import stream_start_callback
        class _Q:
            def __init__(self):
                self.from_user = update.effective_user
                self.message = update.message
                self.data = f"stream_start:{sid}"
            async def answer(self, *a, **k): return None
            async def edit_message_text(self, *a, **k): return None
        class _U:
            def __init__(self):
                self.effective_user = update.effective_user
                self.effective_message = update.message
                self.message = update.message
                self.callback_query = _Q()
        await stream_start_callback(_U(), context)
    return True


# ---------------------------------------------------------------------------
# Auto-refresh loops (real animation: re-edits the same message on an interval)
# ---------------------------------------------------------------------------
async def _ensure_auto_refresh(context, chat_id: int, message_id: int, stream_id: int, can_control: bool = False):
    key = (chat_id, message_id)
    old = _STATUS_TASKS.get(key)
    if old and not old.done():
        # Already refreshing — make sure it targets the current stream
        old._target_stream_ids = {stream_id}
        return  # already refreshing

    async def _loop():
        try:
            # While the stream is live, edit on a tight interval (~2 s).
            for _ in range(720):  # ~24 min before expiry
                await asyncio.sleep(2.0)
                s = await db.get_stream(stream_id)
                if not s:
                    break
                running = stream_manager.is_running(stream_id)
                state = stream_manager.get_state(stream_id)
                if not running and state == "stopped":
                    # Last frame showing the "stopped" status, then exit
                    text = build_live_panel(
                        s.get("title") or "بث", stream_id, False, "00:00:00", 0,
                        state="stopped", ffmpeg_ok=False, rtmp_ok=False, source_ok=False,
                    )
                    try:
                        await context.bot.edit_message_text(
                            chat_id=chat_id, message_id=message_id,
                            text=text, parse_mode="HTML",
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
                    quality=_quality_label(meta),
                    meta=meta,
                )
                try:
                    await context.bot.edit_message_text(
                        chat_id=chat_id, message_id=message_id,
                        text=text, parse_mode="HTML",
                        reply_markup=stream_actions_keyboard(stream_id, True, can_control=can_control),
                    )
                except Exception as e:
                    err = str(e).lower()
                    if "message is not modified" in err:
                        continue  # benign
                    if "not found" in err or "message to edit not found" in err:
                        break
                    # rate limit / flood wait
                    if "retry after" in err or "too many requests" in err:
                        await asyncio.sleep(2.0)
            _STATUS_TASKS.pop(key, None)
        except asyncio.CancelledError:
            pass
        except Exception as e:
            logger.exception("auto-refresh error: %s", e)
            _STATUS_TASKS.pop(key, None)

    task = asyncio.create_task(_loop())
    task._target_stream_ids = {stream_id}
    _STATUS_TASKS[key] = task


async def _ensure_stopped_refresh(context, chat_id: int, message_id: int, stream_id: int, can_control: bool = False):
    """Slow refresh (~5 s) for stopped streams so changes propagate without noise."""
    key = (chat_id, message_id)
    old = _STATUS_TASKS.get(key)
    if old and not old.done():
        old._target_stream_ids = {stream_id}
        return

    async def _loop():
        try:
            for _ in range(60):  # ~5 min, then leave the panel alone
                await asyncio.sleep(5.0)
                s = await db.get_stream(stream_id)
                if not s:
                    break
                running = stream_manager.is_running(stream_id)
                if running:
                    # Promote to the live-refresh loop
                    await _ensure_auto_refresh(context, chat_id, message_id, stream_id, can_control)
                    return
                _STATUS_TICK[key] = _STATUS_TICK.get(key, 0) + 1
                meta = stream_manager.get_meta(stream_id)
                text = build_live_panel(
                    s.get("title") or "بث", stream_id, False, "00:00:00", 0,
                    state=stream_manager.get_state(stream_id),
                    volume=meta.get("volume", 1.0),
                    bitrate=meta.get("audio_bitrate", "128k"),
                    restarts=meta.get("restarts", 0),
                    last_error=meta.get("last_error", ""),
                    ffmpeg_ok=False, rtmp_ok=False, source_ok=False,
                    meta=meta,
                )
                try:
                    await context.bot.edit_message_text(
                        chat_id=chat_id, message_id=message_id,
                        text=text, parse_mode="HTML",
                        reply_markup=stream_actions_keyboard(stream_id, False, can_control=can_control),
                    )
                except Exception as e:
                    err = str(e).lower()
                    if "message is not modified" in err:
                        continue
                    if "not found" in err or "message to edit not found" in err:
                        break
            _STATUS_TASKS.pop(key, None)
        except asyncio.CancelledError:
            pass
        except Exception as e:
            logger.exception("stopped-refresh error: %s", e)
            _STATUS_TASKS.pop(key, None)

    _STATUS_TASKS[key] = asyncio.create_task(_loop())


async def _ensure_list_refresh(context, chat_id: int, message_id: int, user_id: int, page: int):
    """Refresh the running-streams list every ~3 s while any process is live."""
    key = (chat_id, message_id)
    old = _STATUS_TASKS.get(key)
    if old and not old.done():
        return

    async def _loop():
        try:
            for _ in range(120):
                await asyncio.sleep(3.0)
                streams = await db.get_user_streams(user_id) or []
                active_sid = stream_manager.get_active_stream_id()
                seen = {int(s.get("id") or 0) for s in streams if s.get("id") is not None}
                if active_sid and active_sid not in seen:
                    try:
                        row = await db.get_stream(active_sid)
                        if row:
                            streams.append(row)
                            seen.add(active_sid)
                    except Exception:
                        pass
                any_live = any(stream_manager.is_running(int(s.get("id") or 0)) for s in streams)
                if not any_live:
                    break
                per = 8
                total = len(streams)
                pages = max(1, (total + per - 1) // per)
                page_use = max(1, min(page, pages))
                chunk = streams[(page_use - 1) * per: page_use * per]
                live_count = sum(1 for s in streams if stream_manager.is_running(int(s.get("id") or 0)))
                stopped_count = total - live_count
                text = (
                    "📡 <b>حالة البث</b>\n\n"
                    f"🟢 يعمل الآن: <b>{live_count}</b> · 🔴 متوقف/فشل: <b>{stopped_count}</b>\n"
                    f"صفحة {page_use}/{pages}\n\n"
                    "اختر بثاً للتحكم به أو لمتابعة التفاصيل:"
                )
                buttons: List[List[InlineKeyboardButton]] = []
                for s in chunk:
                    sid = int(s.get("id") or 0)
                    icon, state_ar = _row_icon_and_state(s)
                    try:
                        up = stream_uptime(s.get("started_at")) if stream_manager.is_running(sid) else state_ar
                    except Exception:
                        up = state_ar
                    title = html.escape(str(s.get("title") or "بث")[:30])
                    btn_text = f"{icon} #{sid} {title} · {up}"[:64]
                    buttons.append([InlineKeyboardButton(btn_text, callback_data=f"stream_status:{sid}")])
                nav: List[InlineKeyboardButton] = []
                if page_use > 1:
                    nav.append(InlineKeyboardButton("◀ السابق", callback_data=f"current_stream:p{page_use-1}"))
                if pages > 1:
                    nav.append(InlineKeyboardButton(f"{page_use}/{pages}", callback_data="noop"))
                if page_use < pages:
                    nav.append(InlineKeyboardButton("التالي ▶", callback_data=f"current_stream:p{page_use+1}"))
                if nav:
                    buttons.append(nav)
                buttons.append([
                    InlineKeyboardButton("🔄 تحديث", callback_data="current_stream"),
                    InlineKeyboardButton("🚀 إنشاء", callback_data="stream_new"),
                    InlineKeyboardButton("🔙 القائمة", callback_data="main_menu"),
                ])
                try:
                    await context.bot.edit_message_text(
                        chat_id=chat_id, message_id=message_id,
                        text=text, parse_mode="HTML",
                        reply_markup=InlineKeyboardMarkup(buttons),
                    )
                except Exception as e:
                    err = str(e).lower()
                    if "message is not modified" in err:
                        continue
                    if "not found" in err or "message to edit not found" in err:
                        break
            _STATUS_TASKS.pop(key, None)
        except asyncio.CancelledError:
            pass
        except Exception as e:
            logger.exception("list-refresh error: %s", e)
            _STATUS_TASKS.pop(key, None)

    _STATUS_TASKS[key] = asyncio.create_task(_loop())
