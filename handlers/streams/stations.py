"""Radio stations, stream history and favorites."""
from __future__ import annotations

import asyncio
import html
import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, ConversationHandler

from database import db
from services.stream import stream_manager
from keyboards.menus import stream_actions_keyboard, cancel_keyboard, main_menu, main_reply_keyboard
from utils.helpers import is_admin, safe_edit_message, clear_workflow_state, stream_uptime
from config import ADMIN_ID
from services import stations as stations_service

from .common import WAITING_RTMP_URL, WAITING_STREAM_KEY, _safe_update_reply, cancel_conversation

logger = logging.getLogger(__name__)

def _stations_keyboard(stations_list):
    rows = []
    for s in stations_list:
        n_backup = max(len(s["sources"]) - 1, 0)
        label = f"📻 {s['name']}" + (f" (+{n_backup} احتياطي)" if n_backup else "")
        rows.append([
            InlineKeyboardButton(label, callback_data=f"station_start:{s['id']}"),
            InlineKeyboardButton("📡 RTMP يدوي", callback_data=f"station_rtmp:{s['id']}"),
        ])
    rows.append([InlineKeyboardButton("🔙 رجوع", callback_data="main_menu")])
    return InlineKeyboardMarkup(rows)


async def station_rtmp_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Ask for an RTMP server + stream key for a station, without editing stations.json."""
    q = update.callback_query
    await q.answer()
    station_id = q.data.split(":", 1)[1]
    station = stations_service.get_station(station_id)
    if not station:
        await q.edit_message_text("❌ المحطة غير موجودة.")
        return
    context.user_data["station_manual_rtmp"] = station_id
    context.user_data["await_station_rtmp"] = True
    await q.edit_message_text(
        f"📡 <b>RTMP يدوي — {html.escape(station['name'])}</b>\n\n"
        "أرسل رابط سيرفر RTMP فقط (بدون المفتاح):\n"
        "<code>rtmps://dc4-1.rtmp.t.me/s/</code>\n\n"
        "بعدها سأطلب منك Stream Key.",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("❌ إلغاء", callback_data="stations_menu")]]),
    )


async def station_rtmp_receive(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = (update.message.text or "").strip()
    if not text.startswith(("rtmp://", "rtmps://")):
        await _safe_update_reply(update, "❌ أرسل رابط RTMP يبدأ بـ rtmp:// أو rtmps://")
        return
    context.user_data["station_rtmp_base"] = text.rstrip("/") + "/"
    context.user_data.pop("await_station_rtmp", None)
    context.user_data["await_station_key"] = True
    await _safe_update_reply(update, "🔑 أرسل Stream Key فقط:")


async def station_rtmp_key_receive(update: Update, context: ContextTypes.DEFAULT_TYPE):
    key = (update.message.text or "").strip().strip("/")
    base = context.user_data.get("station_rtmp_base")
    station_id = context.user_data.get("station_manual_rtmp")
    if not base or not station_id:
        context.user_data.pop("await_station_key", None)
        await _safe_update_reply(update, "❌ انتهت عملية RTMP اليدوي. افتح المحطات وحاول مرة أخرى.")
        return
    if "://" in key:
        key = key.rstrip("/").split("/")[-1]
    rtmp = base + key
    station = stations_service.get_station(station_id)
    if not station:
        await _safe_update_reply(update, "❌ المحطة غير موجودة.")
    elif not await asyncio.to_thread(stream_manager.has_ffmpeg):
        await _safe_update_reply(update, "❌ FFmpeg غير متاح على السيرفر.")
    else:
        try:
            user_id = update.effective_user.id
            stream_id = await db.create_stream(user_id, station["name"], station["sources"][0], rtmp)
            pid = await asyncio.to_thread(
                stream_manager.start_stream,
                stream_id, station["sources"][0], rtmp,
                with_video=station.get("with_video", False), sources=station["sources"],
            )
            if pid:
                await db.update_stream_status(stream_id, "running", pid)
                await _safe_update_reply(update, 
                    f"✅ تم تشغيل {station['name']}\n\n📡 RTMP: <code>{html.escape(rtmp)}</code>",
                    parse_mode="HTML",
                )
            else:
                await db.update_stream_error(stream_id, "فشل تشغيل FFmpeg")
                await _safe_update_reply(update, "❌ فشل تشغيل البث. تحقق من المصدر وRTMP.")
        except Exception as exc:
            logger.exception("manual station rtmp: %s", exc)
            await _safe_update_reply(update, f"❌ فشل تشغيل المحطة: {html.escape(str(exc)[:180])}")
    for k in ("await_station_key", "station_manual_rtmp", "station_rtmp_base"):
        context.user_data.pop(k, None)


async def stations_menu_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Lists stations configured in data/stations.json."""
    query = update.callback_query
    if query:
        await query.answer()
    stations_list = stations_service.load_stations()
    if not stations_list:
        text = (
            "📻 *المحطات*\n\n"
            "لا توجد محطات معرّفة بعد.\n"
            "أضف محطات في ملف `data/stations.json` "
            "(مصدر أساسي + مصادر احتياطية لكل محطة)."
        )
        target = query.message if query else update.message
        if query:
            await query.edit_message_text(text, parse_mode="Markdown")
        else:
            await _safe_update_reply(update, text, parse_mode="Markdown")
        return
    text = f"📻 *المحطات* ({len(stations_list)})\n\nاختر محطة للبدء (مع تبديل تلقائي للمصادر الاحتياطية عند الحاجة):"
    kb = _stations_keyboard(stations_list)
    if query:
        await query.edit_message_text(text, parse_mode="Markdown", reply_markup=kb)
    else:
        await _safe_update_reply(update, text, parse_mode="Markdown", reply_markup=kb)


async def stations_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await stations_menu_callback(update, context)


async def station_start_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Starts (or switches to) a station's stream, with its full failover
    source list wired into the watchdog."""
    query = update.callback_query
    await query.answer()
    try:
        station_id = query.data.split(":", 1)[1]
        station = stations_service.get_station(station_id)
        if not station:
            await query.answer("❌ المحطة غير موجودة", show_alert=True)
            return

        rtmp = station.get("rtmp_url") or await db.get_setting("default_rtmp_url", "")
        if not rtmp:
            await query.edit_message_text(
                "⚠️ لا يوجد رابط RTMP لهذه المحطة.\n"
                "أضف `rtmp_url` للمحطة في `data/stations.json`، "
                "أو أنشئ بثاً عادياً وأدخل RTMP يدوياً.",
            )
            return

        if not await asyncio.to_thread(stream_manager.has_ffmpeg):
            await query.edit_message_text("❌ FFmpeg غير متاح على السيرفر حالياً. حاول لاحقاً.")
            return

        user_id = query.from_user.id
        stream_id = await db.create_stream(user_id, station["name"], station["sources"][0], rtmp)
        pid = await asyncio.to_thread(
            stream_manager.start_stream,
            stream_id,
            station["sources"][0],
            rtmp,
            with_video=station.get("with_video", False),
            force_video_for_audio=not station.get("with_video", False),
            sources=station["sources"],
        )

        if pid:
            await db.update_stream_status(stream_id, "running", pid)
            n_backup = max(len(station["sources"]) - 1, 0)
            await query.edit_message_text(
                f"✅ بدأ تشغيل محطة *{station['name']}*\n"
                f"🆔 Stream `#{stream_id}`\n"
                + (f"♻️ {n_backup} مصدر احتياطي جاهز للتبديل التلقائي\n" if n_backup else "")
                + "\nسيظهر 🟢 ON AIR فقط بعد تأكيد وجود صوت فعلي.",
                parse_mode="Markdown",
            )
        else:
            await query.edit_message_text("❌ فشل بدء تشغيل المحطة.")
    except Exception as e:
        logger.exception(e)
        try:
            await query.edit_message_text("❌ خطأ أثناء بدء المحطة.")
        except Exception:
            pass



async def stream_history_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show user stream history with pagination."""
    query = update.callback_query
    if query:
        try:
            await query.answer()
        except Exception:
            pass
        msg = query.message
        user_id = query.from_user.id
        data = query.data or "stream_history"
        page = 1
        if ":" in data:
            try:
                page = max(1, int(data.split(":")[-1]))
            except Exception:
                page = 1
    else:
        msg = update.message
        user_id = update.effective_user.id
        page = 1

    try:
        streams = await db.get_user_streams(user_id) or []
    except Exception as e:
        logger.warning("stream history: %s", e)
        streams = []

    per = 10
    total = len(streams)
    pages = max(1, (total + per - 1) // per) if total else 1
    page = min(page, pages)
    chunk = streams[(page - 1) * per: page * per]

    if not chunk:
        body = "📜 <b>سجل البثوث</b>\n\nلا يوجد سجل بعد.\nشغّل بثاً ليظهر هنا."
        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("🚀 إنشاء بث", callback_data="stream_new")],
            [InlineKeyboardButton("🔙 رجوع", callback_data="section_stream")],
        ])
    else:
        body = f"📜 <b>سجل البثوث</b> — صفحة {page}/{pages}\n\n"
        buttons = []
        from keyboards.stream import stream_list_button_text
        for s in chunk:
            sid = s.get("id")
            title = html.escape(str(s.get("title") or "بث")[:36])
            status = str(s.get("status") or "")
            try:
                sid_i = int(sid or 0)
                live_now = stream_manager.is_running(sid_i)
                healthy = stream_manager.is_healthy(sid_i) if live_now else False
                state = stream_manager.get_state(sid_i) if sid_i else "stopped"
                up = stream_uptime(s.get("started_at")) if (status == "running" and live_now) else "—"
            except Exception:
                live_now = False
                healthy = False
                state = status or "stopped"
                up = "—"
            if healthy:
                icon = "🟢"
            elif live_now:
                icon = "🟡"
            else:
                icon = "🔴"
            body += f"{icon} <b>#{sid}</b> {title}\n"
            body += f"⏱ {up} · {('ON AIR' if healthy else ('يعمل' if live_now else 'متوقف'))}\n"
            # One rich button (≤64 chars) + favorite — opens same Live Panel
            btn_text = stream_list_button_text(
                int(sid or 0),
                s.get("title"),
                status=status,
                running=live_now,
                healthy=healthy,
                state=state,
                uptime=up if live_now else "—",
            )
            buttons.append([
                InlineKeyboardButton(btn_text, callback_data=f"stream_status:{sid}"),
                InlineKeyboardButton("⭐", callback_data=f"stream_fav:{sid}"),
            ])
        nav = []
        if page > 1:
            nav.append(InlineKeyboardButton("◀ السابق", callback_data=f"stream_history:{page-1}"))
        nav.append(InlineKeyboardButton(f"{page}/{pages}", callback_data="noop"))
        if page < pages:
            nav.append(InlineKeyboardButton("التالي ▶", callback_data=f"stream_history:{page+1}"))
        if nav:
            buttons.append(nav)
        buttons.append([InlineKeyboardButton("🔙 رجوع", callback_data="section_stream")])
        kb = InlineKeyboardMarkup(buttons)

    if query:
        from utils.helpers import safe_edit_message
        await safe_edit_message(query, body, parse_mode="HTML", reply_markup=kb)
    else:
        await msg.reply_text(body, parse_mode="HTML", reply_markup=kb)


async def stream_fav_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    try:
        await q.answer()
    except Exception:
        pass
    try:
        sid = int((q.data or "").split(":")[-1])
    except Exception:
        try:
            await q.answer("معرف غير صالح", show_alert=True)
        except Exception:
            pass
        return
    try:
        streams = await db.get_user_streams(q.from_user.id) or []
        s = next((x for x in streams if int(x.get("id") or 0) == sid), None)
        if not s:
            await q.answer("غير موجود", show_alert=True)
            return
        await db.add_favorite(
            q.from_user.id,
            "stream",
            str(s.get("title") or f"stream-{sid}"),
            str(s.get("source_url") or ""),
            meta=str(sid),
        )
        await q.answer("⭐ تمت الإضافة للمفضلة", show_alert=False)
    except Exception as e:
        logger.warning("stream_fav: %s", e)
        try:
            await q.answer("تعذر الإضافة", show_alert=True)
        except Exception:
            pass


# --------------------------------------------------------------------------- #
# Logs & Statistics panels (restored legacy V6/CLASSIC_IRON callbacks)
# --------------------------------------------------------------------------- #
_LOG_ICONS = {
    "started": "🟢", "on_air": "🟢", "rtmp_start": "🟢", "source_connected": "🟢",
    "stopped": "⏹", "failed": "🔴", "probe_fail": "🔴", "start_fail": "🔴",
    "reconnecting": "⚠️", "cloned": "📋", "created": "✨",
}


async def stream_logs_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    try:
        await query.answer()
    except Exception:
        pass
    try:
        sid = int((query.data or "").split(":")[1])
        s = await db.get_stream(sid)
        if not s or (s.get("user_id") != query.from_user.id and not is_admin(query.from_user.id, ADMIN_ID)):
            try:
                await query.answer("غير مسموح", show_alert=True)
            except Exception:
                pass
            return
        logs = await db.get_stream_logs(sid, limit=30) or []
        lines = [f"📜 <b>سجلات البث #{sid}</b>", "━━━━━━━━━━━━━━"]
        if not logs:
            lines.append("لا توجد سجلات بعد.")
        for item in logs[:30]:
            ev = str(item.get("event") or "")
            ts = str(item.get("created_at") or "")[:19]
            msg = str(item.get("message") or item.get("details") or "")[:120]
            lines.append(f"<code>{html.escape(ts)}</code> {_LOG_ICONS.get(ev, '•')} {html.escape(ev)}")
            if msg:
                lines.append(html.escape(msg))
        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("📊 الحالة", callback_data=f"stream_status:{sid}"),
             InlineKeyboardButton("📈 إحصائيات", callback_data=f"stream_stats:{sid}")],
            [InlineKeyboardButton("🔙 رجوع", callback_data=f"stream_status:{sid}")],
        ])
        await safe_edit_message(query, "\n".join(lines)[:3900], parse_mode="HTML", reply_markup=kb)
    except Exception as e:
        logger.exception("stream_logs: %s", e)


async def stream_stats_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    try:
        await query.answer()
    except Exception:
        pass
    try:
        sid = int((query.data or "").split(":")[1])
        s = await db.get_stream(sid)
        if not s or (s.get("user_id") != query.from_user.id and not is_admin(query.from_user.id, ADMIN_ID)):
            try:
                await query.answer("غير مسموح", show_alert=True)
            except Exception:
                pass
            return
        running = stream_manager.is_running(sid)
        meta = stream_manager.get_meta(sid) or {}
        prog = meta.get("progress") or {}
        stats = [
            ("⏱ Uptime", stream_uptime(s.get("started_at")) if running else "—"),
            ("🔄 Restarts", str(meta.get("restarts", s.get("restart_count") or 0))),
            ("📊 Bitrate", str(prog.get("bitrate_str") or meta.get("bitrate") or "غير متاح")),
            ("🎞 FPS", str(meta.get("fps") or "غير متاح")),
            ("🧮 Frames", str(prog.get("frame") or "غير متاح")),
            ("⚡ Speed", str(prog.get("speed_str") or "غير متاح")),
            ("🧭 الحالة", str(stream_manager.get_state(sid))),
            ("📡 المصدر", str(meta.get("source_type") or s.get("source_type") or "—")),
            ("🆔 PID", str(stream_manager.get_pid(sid) or "—")),
        ]
        lines = [f"📈 <b>إحصائيات البث #{sid}</b>", "━━━━━━━━━━━━━━", f"📌 {html.escape(str(s.get('title') or '—'))}", ""]
        lines += [f"{k}: <code>{html.escape(v)}</code>" for k, v in stats]
        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("📜 سجلات", callback_data=f"stream_logs:{sid}"),
             InlineKeyboardButton("🔙 اللوحة", callback_data=f"stream_status:{sid}")],
        ])
        await safe_edit_message(query, "\n".join(lines)[:3900], parse_mode="HTML", reply_markup=kb)
    except Exception as e:
        logger.exception("stream_stats: %s", e)
