"""IPTV handlers + smart help assistant (Phase 3)."""
import logging
import asyncio
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, ConversationHandler

from database import db
from services import iptv as iptv_svc
from utils.helpers import is_admin
from config import ADMIN_ID

logger = logging.getLogger(__name__)

def chunk_buttons(items, per_row=2):
    """قسّم الأزرار على صفوف (افتراضي صفين)."""
    rows = []
    for i in range(0, len(items), per_row):
        rows.append(items[i:i + per_row])
    return rows


WAITING_IPTV_URL = 50


async def iptv_import_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """بدء استيراد قائمة M3U دون حذف أي قائمة محفوظة سابقاً."""
    query = update.callback_query
    await query.answer()
    context.user_data["await_iptv_url"] = True
    await query.edit_message_text(
        "📥 <b>استيراد قائمة IPTV</b>\n\n"
        "أرسل الآن رابط ملف M3U/M3U8 صالح.\n"
        "مثال: <code>https://example.com/playlist.m3u</code>",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup([[
            InlineKeyboardButton("🔙 إلغاء", callback_data="iptv_menu")
        ]]),
    )


# قوائم جاهزة من iptv-org (GitHub) — تُحدَّث باستمرار
IPTV_PRESETS = {
    "eg": ("🇪🇬 مصر", "https://iptv-org.github.io/iptv/countries/eg.m3u"),
    "sa": ("🇸🇦 السعودية", "https://iptv-org.github.io/iptv/countries/sa.m3u"),
    "ae": ("🇦🇪 الإمارات", "https://iptv-org.github.io/iptv/countries/ae.m3u"),
    "news": ("📰 أخبار", "https://iptv-org.github.io/iptv/categories/news.m3u"),
}


async def iptv_menu_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    uid = query.from_user.id
    playlists = iptv_svc.list_user_playlists(uid)
    # active playlist id stored in user_data
    active_id = context.user_data.get("iptv_active_pl")
    pl = iptv_svc.load_user_playlist(uid, active_id) if active_id else iptv_svc.load_user_playlist(uid)
    if pl and pl.get("id"):
        context.user_data["iptv_active_pl"] = pl.get("id")

    lines = ["📡 <b>IPTV — قنوات منظمة</b>\n"]
    buttons = [
        [InlineKeyboardButton("🔎 بحث عن قناة", callback_data="iptv_search")],
        [InlineKeyboardButton("📥 استيراد M3U (قائمة جديدة)", callback_data="iptv_import")],
        [InlineKeyboardButton("📺 OscarTV (تلقائي)", callback_data="iptv_preset:oscar")],
        [InlineKeyboardButton("🇪🇬 مصر (iptv-org)", callback_data="iptv_preset:eg")],
        [InlineKeyboardButton("🇸🇦 السعودية", callback_data="iptv_preset:sa"),
         InlineKeyboardButton("📰 أخبار", callback_data="iptv_preset:news")],
        [InlineKeyboardButton("🔄 تحديث القائمة النشطة", callback_data="iptv_refresh")],
    ]

    # Show all saved playlists — click to enter channels
    if playlists:
        lines.append(f"<b>قوائمك المحفوظة ({len(playlists)}):</b>")
        for p in playlists[:10]:
            mark = "▶️" if pl and str(pl.get("id")) == str(p["id"]) else "📁"
            lines.append(f"{mark} {p['name']} — {p['channel_count']} قناة")
            buttons.append([InlineKeyboardButton(
                f"{mark} {p['name'][:20]} ({p['channel_count']})",
                callback_data=f"iptv_openpl:{p['id']}"
            )])
        lines.append("")

    if pl and pl.get("channels"):
        n = len(pl["channels"])
        lines.append(f"النشطة: <b>{pl.get('name') or 'IPTV'}</b> — {n} قناة\n")
        groups = iptv_svc.groups_from_channels(pl["channels"])
        grp_btns = []
        for g in groups[:12]:
            cnt = sum(1 for c in pl["channels"] if (c.get("group") or "عام") == g)
            label = f"📺 {g[:14]} ({cnt})"
            grp_btns.append(InlineKeyboardButton(label, callback_data=f"iptv_group:{g[:40]}"))
        buttons.extend(chunk_buttons(grp_btns, per_row=2))
    else:
        lines.append("لا توجد قائمة نشطة.\nاختر قائمة جاهزة أو استورد رابط M3U (تُضاف بدون حذف القديمة).")

    buttons.append([InlineKeyboardButton("🔙 القائمة الرئيسية", callback_data="main_menu")])
    await query.edit_message_text(
        "\n".join(lines),
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(buttons),
    )


async def iptv_open_playlist_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """فتح قائمة محفوظة وعرض تصنيفاتها."""
    query = update.callback_query
    await query.answer()
    pl_id = query.data.split(":", 1)[1]
    context.user_data["iptv_active_pl"] = pl_id
    # reuse menu
    await iptv_menu_callback(update, context)


async def iptv_search_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """طلب كلمة البحث عن قناة IPTV."""
    query = update.callback_query
    await query.answer()
    pl = iptv_svc.load_user_playlist(query.from_user.id, context.user_data.get("iptv_active_pl"))
    if not pl or not pl.get("channels"):
        await query.edit_message_text(
            "🔎 <b>بحث القنوات</b>\n\n"
            "لا توجد قائمة بعد.\n"
            "حمّل أولاً قائمة (مصر / استيراد M3U) ثم ابحث.",
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🇪🇬 تحميل مصر", callback_data="iptv_preset:eg")],
                [InlineKeyboardButton("🔙 رجوع", callback_data="iptv_menu")],
            ]),
        )
        return
    context.user_data["await_iptv_search"] = True
    n = len(pl["channels"])
    await query.edit_message_text(
        f"🔎 <b>بحث في {n} قناة</b>\n\n"
        "اكتب اسم القناة أو جزء منه:\n"
        "مثال: <code>MBC</code> أو <code>cbc</code> أو <code>قرآن</code>",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 إلغاء", callback_data="iptv_menu")]]),
    )


async def run_iptv_search(update: Update, context: ContextTypes.DEFAULT_TYPE, query_text: str):
    """تنفيذ البحث وعرض النتائج كأزرار تشغيل."""
    uid = update.effective_user.id
    pl = iptv_svc.load_user_playlist(uid, context.user_data.get("iptv_active_pl"))
    if not pl or not pl.get("channels"):
        await update.message.reply_text("❌ لا توجد قائمة قنوات. افتح IPTV وحمّل قائمة أولاً.")
        return
    results = iptv_svc.search_channels(pl["channels"], query_text, limit=20)
    if not results:
        await update.message.reply_text(
            f"🔎 لا نتائج لـ «{query_text}»\nجرّب كلمة أقصر أو حدّث القائمة.",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🔎 بحث جديد", callback_data="iptv_search")],
                [InlineKeyboardButton("📡 قائمة IPTV", callback_data="iptv_menu")],
            ]),
        )
        return
    btn_list = []
    for r in results:
        idx = r.get("_index", 0)
        name = (r.get("name") or "قناة")[:22]
        label = f"▶️ {name}"
        btn_list.append(InlineKeyboardButton(label, callback_data=f"iptv_play:{idx}"))
    buttons = chunk_buttons(btn_list, per_row=2)
    buttons.append([InlineKeyboardButton("🔎 بحث جديد", callback_data="iptv_search"),
                    InlineKeyboardButton("🔙 IPTV", callback_data="iptv_menu")])
    await update.message.reply_text(
        f"🔎 نتائج «{query_text}»: <b>{len(results)}</b> قناة\nاختر للتشغيل:",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(buttons),
    )


async def iptv_preset_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    key = query.data.split(":", 1)[1]

    # --- OscarTV special source ---
    if key == "oscar":
        await query.edit_message_text(
            "📺 جاري جلب OscarTV بسرعة...\n"
            "سيتم فحص عدد كبير بالتوازي مع إبقاء البوت مستجيباً."
        )
        try:
            cached = iptv_svc.load_oscar_cache()
            if cached:
                channels = iptv_svc.filter_visible_channels(cached)
                await query.edit_message_text(
                    f"📂 تم تحميل الكاش: {len(channels)} رابط\nجاري الحفظ في قائمتك..."
                )
            else:
                async def progress(cid, total, n):
                    try:
                        await query.edit_message_text(
                            f"📺 OscarTV: جاري الجلب... {cid}/{total}\nتم العثور على {n} رابط"
                        )
                    except Exception:
                        pass
                channels = iptv_svc.filter_visible_channels(await iptv_svc.fetch_oscar_channels(progress_cb=progress))
            if not channels:
                await query.edit_message_text("❌ لم يتم العثور على قنوات OscarTV.")
                return
            iptv_svc.save_user_playlist(query.from_user.id, "OscarTV", channels)
            context.user_data["iptv_source_url"] = "oscar://auto"
            try:
                from pathlib import Path
                import json
                meta = Path(__file__).resolve().parent.parent / "data" / "iptv" / f"user_{query.from_user.id}_meta.json"
                meta.write_text(json.dumps({"url": "oscar://auto", "name": "OscarTV"}, ensure_ascii=False), encoding="utf-8")
            except Exception:
                pass
            await db.add_audit(query.from_user.id, "iptv_preset", "oscar", f"n={len(channels)}")
            await query.edit_message_text(
                f"✅ تم استيراد <b>{len(channels)}</b> رابط من OscarTV\n"
                f"يمكنك البحث والتشغيل من قائمة IPTV.",
                parse_mode="HTML",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("📡 فتح التصنيفات", callback_data="iptv_menu")]]),
            )
        except Exception as e:
            logger.exception("OscarTV import failed")
            await query.edit_message_text(f"❌ فشل جلب OscarTV: {e}")
        return

    preset = IPTV_PRESETS.get(key)
    if not preset:
        await query.answer("غير متوفر", show_alert=True)
        return
    name, url = preset
    await query.edit_message_text(f"📥 جاري تحميل {name}...")
    try:
        channels = iptv_svc.filter_visible_channels(await iptv_svc.fetch_m3u(url))
        if not channels:
            await query.edit_message_text("❌ القائمة فارغة أو الرابط متوقف.")
            return
        iptv_svc.save_user_playlist(query.from_user.id, name, channels)
        context.user_data["iptv_source_url"] = url
        try:
            from pathlib import Path
            import json
            meta = Path(__file__).resolve().parent.parent / "data" / "iptv" / f"user_{query.from_user.id}_meta.json"
            meta.write_text(json.dumps({"url": url, "name": name}, ensure_ascii=False), encoding="utf-8")
        except Exception:
            pass
        await db.add_audit(query.from_user.id, "iptv_preset", key, f"n={len(channels)}")
        await query.edit_message_text(
            f"✅ تم استيراد <b>{len(channels)}</b> قناة من {name}",
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("📡 فتح التصنيفات", callback_data="iptv_menu")]]),
        )
    except Exception as e:
        await query.edit_message_text(f"❌ فشل التحميل: {e}")


async def iptv_refresh_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    url = context.user_data.get("iptv_source_url")
    if not url:
        try:
            from pathlib import Path
            import json
            meta = Path(__file__).resolve().parent.parent / "data" / "iptv" / f"user_{query.from_user.id}_meta.json"
            if meta.exists():
                url = json.loads(meta.read_text(encoding="utf-8")).get("url")
        except Exception:
            url = None
    if not url:
        await query.answer("لا يوجد مصدر محفوظ — استورد قائمة أولاً", show_alert=True)
        return
    await query.edit_message_text("🔄 جاري التحديث من المصدر...")
    try:
        if url.startswith("oscar://"):
            channels = await iptv_svc.fetch_oscar_channels()
            name = "OscarTV محدّث"
        else:
            channels = iptv_svc.filter_visible_channels(await iptv_svc.fetch_m3u(url))
            name = "IPTV محدّث"
        iptv_svc.save_user_playlist(query.from_user.id, name, channels)
        await query.edit_message_text(
            f"✅ تم التحديث — {len(channels)} قناة",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("📡 فتح", callback_data="iptv_menu")]]),
        )
    except Exception as e:
        await query.edit_message_text(f"❌ فشل التحديث: {e}")


async def iptv_group_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    group = query.data.split(":", 1)[1]
    pl = iptv_svc.load_user_playlist(query.from_user.id, context.user_data.get("iptv_active_pl"))
    if not pl:
        await query.answer("لا قائمة", show_alert=True)
        return
    channels = [c for c in pl["channels"] if (c.get("group") or "عام") == group]
    btn_list = []
    for i, c in enumerate(channels[:30]):
        full_idx = pl["channels"].index(c)
        name = (c.get("name") or "قناة")[:20]
        btn_list.append(InlineKeyboardButton(
            f"▶️ {name}",
            callback_data=f"iptv_play:{full_idx}",
        ))
    buttons = chunk_buttons(btn_list, per_row=2)
    buttons.append([InlineKeyboardButton("🔙 رجوع", callback_data="iptv_menu")])
    await query.edit_message_text(
        f"📺 <b>{group}</b> ({len(channels)} قناة)",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(buttons),
    )


async def iptv_play_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    try:
        idx = int(query.data.split(":")[1])
        pl = iptv_svc.load_user_playlist(query.from_user.id, context.user_data.get("iptv_active_pl"))
        if not pl or idx >= len(pl["channels"]):
            await query.answer("غير موجود", show_alert=True)
            return
        ch = pl["channels"][idx]
        src = (ch.get("url") or "").split("#")[0].strip()
        context.user_data["pending_stream_url"] = src
        context.user_data["pending_stream_title"] = ch.get("name") or "IPTV"
        from handlers.streams import start_rtmp_setup_flags
        await start_rtmp_setup_flags(update, context)
    except Exception as e:
        logger.exception(e)
        await query.answer("خطأ", show_alert=True)


async def help_assistant_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """💬 مساعد يجيب من الـ Logs."""
    query = update.callback_query
    await query.answer()
    uid = query.from_user.id
    logs = await db.get_stream_logs(limit=15)
    audit = await db.get_audit_logs(limit=10, user_id=uid)
    lines = ["💬 <b>المساعد</b>\n"]
    if not logs and not audit:
        lines.append("لا توجد سجلات حديثة.\nإذا توقف بث، أعد التشغيل من «البث الحالي».")
    else:
        lines.append("<b>آخر أحداث البث:</b>")
        for L in logs[:5]:
            lines.append(f"• #{L.get('stream_id')} {L.get('event')}: {(L.get('message') or '')[:40]}")
        if audit:
            lines.append("\n<b>نشاطك الأخير:</b>")
            for a in audit[:5]:
                lines.append(f"• {a.get('action')} {a.get('target') or ''}")
    lines.append("\n<i>اكتب سؤالاً مثل: لماذا توقف البث؟</i>")
    context.user_data["await_help_q"] = True
    await query.edit_message_text(
        "\n".join(lines),
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 رجوع", callback_data="main_menu")]]),
    )


async def answer_help_question(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.user_data.pop("await_help_q", None):
        return False
    q = (update.message.text or "").strip().lower()
    uid = update.effective_user.id
    logs = await db.get_stream_logs(limit=20)
    reply = "لم أجد سبباً واضحاً في السجلات. جرّب إعادة تشغيل البث من لوحة البث الحالي."
    if any(w in q for w in ("توقف", "وقف", "فشل", "stop", "fail", "error", "خطأ")):
        fails = [L for L in logs if L.get("event") in ("start_fail", "probe_fail") or "fail" in (L.get("event") or "")]
        if fails:
            f = fails[0]
            reply = (
                f"⚠️ آخر مشكلة مسجلة:\n"
                f"البث #{f.get('stream_id')}\n"
                f"الحدث: {f.get('event')}\n"
                f"التفاصيل: {f.get('message') or f.get('details') or '—'}\n\n"
                f"الحل المقترح: تحقق من رابط المصدر ومفتاح RTMP ثم أعد التشغيل."
            )
        else:
            reply = "لا يوجد فشل مسجل حديثاً. إذا البث توقف، قد يكون انقطاع المصدر — اضغط إعادة تشغيل."
    elif any(w in q for w in ("ffmpeg", "اف اف", "ترميز")):
        from services.stream import stream_manager
        reply = "FFmpeg: " + ("🟢 متوفر" if await asyncio.to_thread(stream_manager.has_ffmpeg) else "🔴 غير متوفر — ثبّته أو استخدم VPS")
    elif any(w in q for w in ("rtmp", "مفتاح", "key")):
        prof = await db.get_default_rtmp_profile(uid)
        reply = "لديك إعدادات RTMP محفوظة ✅" if prof else "لا توجد إعدادات RTMP — أنشئ بثاً مرة ليحفظها."
    await update.message.reply_text(reply)
    return True
