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
from utils.helpers import is_admin, safe_edit_message, clear_workflow_state
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
        for s in chunk:
            sid = s.get("id")
            title = html.escape(str(s.get("title") or "بث")[:36])
            status = str(s.get("status") or "")
            icon = "🟢" if status == "running" else "🔴"
            body += f"{icon} #{sid} {title}\n"
            buttons.append([
                InlineKeyboardButton(f"▶ #{sid}", callback_data=f"stream_status:{sid}"),
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
