"""Handlers لقسم الأفلام — Hikaye TV API."""
import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes

from services import movies as movies_svc

logger = logging.getLogger(__name__)


def _chunk(buttons, n=2):
    return [buttons[i:i + n] for i in range(0, len(buttons), n)]


def _format_detail(m: dict) -> str:
    lines = [f"🎬 <b>{m.get('title') or 'فيلم'}</b>"]
    if m.get("title_en") and m["title_en"] != m.get("title"):
        lines.append(f"🏷 <i>{m['title_en']}</i>")
    lines.append("")
    if m.get("year"):
        lines.append(f"📅 السنة: {m['year']}")
    if m.get("rating"):
        lines.append(f"⭐ التقييم: {m['rating']}/10")
    if m.get("duration"):
        lines.append(f"⏱ المدة: {m['duration']} دقيقة")
    if m.get("genre"):
        lines.append(f"🎭 النوع: {m['genre']}")
    if m.get("view_count"):
        lines.append(f"👁 المشاهدات: {m['view_count']:,}")
    if m.get("description"):
        lines.append(f"\n📝 <i>{m['description'][:280]}</i>")
    srcs = m.get("sources") or []
    if srcs:
        lines.append("\n🎥 <b>السيرفرات:</b>")
        for i, s in enumerate(srcs[:6], 1):
            q = f" ({s['quality']})" if s.get("quality") else ""
            lines.append(f"  {i}. {s.get('label', 'سيرفر')}{q}")
    else:
        lines.append("\n⚠️ لا توجد روابط متاحة حالياً")
    return "\n".join(lines)


def _results_keyboard(results: list, prefix: str = "movie_pick") -> InlineKeyboardMarkup:
    btn_list = []
    for i, r in enumerate(results[:12]):
        label = f"▶️ {(r.get('title') or 'فيلم')[:18]}"
        if r.get("year"):
            label += f" ({r['year']})"
        btn_list.append(InlineKeyboardButton(label[:32], callback_data=f"{prefix}:{i}"))
    rows = _chunk(btn_list, 2)
    rows.append([
        InlineKeyboardButton("🔎 بحث جديد", callback_data="movies_search"),
        InlineKeyboardButton("🔙 رجوع", callback_data="movies_menu"),
    ])
    return InlineKeyboardMarkup(rows)


async def movies_menu_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    context.user_data.pop("await_movie_search", None)
    context.user_data.pop("movie_search_cat", None)
    buttons = [
        [InlineKeyboardButton("🔥 الأكثر مشاهدة", callback_data="movies_cat:most_viewed")],
        [InlineKeyboardButton("🔎 بحث بالاسم", callback_data="movies_search")],
        [
            InlineKeyboardButton("🇸🇦 أفلام عربية", callback_data="movies_cat:arabic_all"),
            InlineKeyboardButton("🌍 أفلام أجنبية", callback_data="movies_cat:foreign_general"),
        ],
        [
            InlineKeyboardButton("🎬 عربي أفلام", callback_data="movies_cat:arabic_movies"),
            InlineKeyboardButton("🎥 أجنبي أفلام", callback_data="movies_cat:foreign_movies"),
        ],
        [InlineKeyboardButton("⭐ أعلى تقييم", callback_data="movies_cat:top_rated")],
        [InlineKeyboardButton("🔙 القائمة الرئيسية", callback_data="main_menu")],
    ]
    await query.edit_message_text(
        "🎬 <b>الأفلام</b>\n\n"
        "ابحث بالاسم أو اختر فئة.\n"
        "بعد اختيار الفيلم تقدر تشغّله على RTMP مباشرة.",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(buttons),
    )


async def movies_search_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    context.user_data["await_movie_search"] = True
    context.user_data.pop("movie_search_cat", None)
    await query.edit_message_text(
        "🔎 <b>بحث عن فيلم</b>\n\n"
        "أرسل اسم الفيلم (عربي أو إنجليزي):\n"
        "مثال: <code>الزعيم</code> أو <code>Inception</code>",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(
            [[InlineKeyboardButton("🔙 إلغاء", callback_data="movies_menu")]]
        ),
    )


async def movies_cat_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    key = query.data.split(":", 1)[1]

    await query.edit_message_text("⏳ جاري التحميل...")

    try:
        if key == "most_viewed":
            results = await movies_svc.get_most_viewed(limit=12)
            title = "🔥 الأكثر مشاهدة"
        elif key == "top_rated":
            results = await movies_svc.get_top_rated(limit=12)
            title = "⭐ أعلى تقييم"
        elif key in movies_svc.CATEGORIES:
            results = await movies_svc.get_by_category(key, limit=12)
            title = movies_svc.CATEGORY_LABELS.get(key, key)
        else:
            # فئة للبحث لاحقاً
            context.user_data["await_movie_search"] = True
            context.user_data["movie_search_cat"] = key
            label = movies_svc.CATEGORY_LABELS.get(key, key)
            await query.edit_message_text(
                f"🔎 بحث في: <b>{label}</b>\n\nأرسل اسم الفيلم:",
                parse_mode="HTML",
                reply_markup=InlineKeyboardMarkup(
                    [[InlineKeyboardButton("🔙 إلغاء", callback_data="movies_menu")]]
                ),
            )
            return
    except Exception as e:
        logger.exception(e)
        await query.edit_message_text(f"❌ فشل التحميل: {e}")
        return

    if not results:
        await query.edit_message_text(
            "❌ لا توجد نتائج حالياً.",
            reply_markup=InlineKeyboardMarkup(
                [[InlineKeyboardButton("🔙 رجوع", callback_data="movies_menu")]]
            ),
        )
        return

    context.user_data["movie_results"] = results
    await query.edit_message_text(
        f"{title}\n<b>{len(results)}</b> فيلم — اختر واحداً:",
        parse_mode="HTML",
        reply_markup=_results_keyboard(results),
    )


async def run_movie_search(update: Update, context: ContextTypes.DEFAULT_TYPE, query_text: str):
    cat = context.user_data.pop("movie_search_cat", None)
    msg = await update.message.reply_text(f"🔍 جاري البحث عن «{query_text}» (جودة عالية)...")
    results = []
    try:
        # Oscar first (better quality links)
        from services.oscar_movies import oscar_api
        results = await oscar_api.search_movies(query_text, limit=12)
    except Exception as e:
        logger.warning("oscar search: %s", e)
    if not results:
        try:
            results = await movies_svc.search_movies(query_text, category_key=cat, limit=12)
        except Exception as e:
            logger.exception(e)
        await msg.edit_text(f"❌ فشل البحث: {e}")
        return

    if not results:
        await msg.edit_text(
            f"🔎 لا نتائج لـ «{query_text}»\nجرّب اسماً أقصر أو إنجليزي/عربي.",
            reply_markup=InlineKeyboardMarkup(
                [
                    [InlineKeyboardButton("🔎 بحث جديد", callback_data="movies_search")],
                    [InlineKeyboardButton("🎬 القائمة", callback_data="movies_menu")],
                ]
            ),
        )
        return

    context.user_data["movie_results"] = results
    await msg.edit_text(
        f"🎬 نتائج «{query_text}»: <b>{len(results)}</b>\nاختر فيلماً:",
        parse_mode="HTML",
        reply_markup=_results_keyboard(results),
    )


async def movie_pick_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    try:
        idx = int(query.data.split(":")[1])
    except Exception:
        await query.answer("خطأ", show_alert=True)
        return

    results = context.user_data.get("movie_results") or []
    if idx < 0 or idx >= len(results):
        await query.answer("غير موجود — ابحث من جديد", show_alert=True)
        return

    m = results[idx]
    # Fetch full details
    if m.get("id"):
        try:
            if m.get("source") == "oscar":
                from services.oscar_movies import oscar_api
                full = await oscar_api.get_movie_details(int(m["id"]))
                if full:
                    m = {**m, **full}
                    # map watch_links to sources for play compatibility
                    sources = []
                    for w in (full.get("watch_links") or []):
                        sources.append({
                            "label": w.get("label") or "سيرفر",
                            "quality": w.get("quality") or "",
                            "url": w.get("url"),
                        })
                    m["sources"] = sources
                    m["download_links"] = full.get("download_links") or []
                    results[idx] = m
                    context.user_data["movie_results"] = results
            else:
                full = await movies_svc.get_movie(m["id"])
                if full and full.get("sources"):
                    m = {**m, **full}
                    results[idx] = m
                    context.user_data["movie_results"] = results
        except Exception as e:
            logger.warning("movie detail: %s", e)

    text = _format_detail(m)
    srcs = m.get("sources") or []
    buttons = []
    src_btns = []
    for i, s in enumerate(srcs[:6]):
        q = f" [{s['quality']}]" if s.get("quality") else ""
        label = f"▶️ {(s.get('label') or 'سيرفر')[:14]}{q}"
        src_btns.append(InlineKeyboardButton(label[:28], callback_data=f"movie_play:{idx}:{i}"))
    buttons.extend(_chunk(src_btns, 2))
    if srcs:
        buttons.append([InlineKeyboardButton("📡 بث أول سيرفر على RTMP", callback_data=f"movie_play:{idx}:0")])
    # Download links in separate button (side / bottom)
    if m.get("download_links"):
        buttons.append([InlineKeyboardButton("📥 روابط التحميل", callback_data=f"movie_dl:{idx}")])
    buttons.append([
        InlineKeyboardButton("🔎 بحث جديد", callback_data="movies_search"),
        InlineKeyboardButton("🔙 الأفلام", callback_data="movies_menu"),
    ])
    await query.edit_message_text(text, parse_mode="HTML", reply_markup=InlineKeyboardMarkup(buttons), disable_web_page_preview=True)


async def movie_downloads_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """عرض روابط التحميل في قائمة منفصلة."""
    query = update.callback_query
    await query.answer()
    try:
        idx = int(query.data.split(":")[1])
    except Exception:
        return
    results = context.user_data.get("movie_results") or []
    if idx < 0 or idx >= len(results):
        await query.answer("انتهت الجلسة", show_alert=True)
        return
    m = results[idx]
    dls = m.get("download_links") or []
    if not dls:
        await query.answer("لا توجد روابط تحميل", show_alert=True)
        return
    from telegram import InlineKeyboardButton, InlineKeyboardMarkup
    buttons = []
    for d in dls[:10]:
        url = d.get("url")
        if not url:
            continue
        q = d.get("quality") or ""
        size = d.get("size") or ""
        label = f"📥 {q} {size}".strip() or "تحميل"
        buttons.append([InlineKeyboardButton(label[:40], url=url)])
    buttons.append([InlineKeyboardButton("🔙 رجوع للتفاصيل", callback_data=f"movie_pick:{idx}")])
    await query.edit_message_text(
        f"📥 <b>روابط تحميل — {m.get('title') or 'فيلم'}</b>\nاختر جودة:",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(buttons),
    )


async def movie_play_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """تشغيل رابط الفيلم عبر إعدادات RTMP الحالية."""
    query = update.callback_query
    await query.answer()
    parts = query.data.split(":")
    try:
        mi, si = int(parts[1]), int(parts[2])
    except Exception:
        await query.answer("خطأ", show_alert=True)
        return

    results = context.user_data.get("movie_results") or []
    if mi < 0 or mi >= len(results):
        await query.answer("انتهت الجلسة — ابحث من جديد", show_alert=True)
        return
    m = results[mi]
    srcs = m.get("sources") or []
    if si < 0 or si >= len(srcs):
        await query.answer("سيرفر غير موجود", show_alert=True)
        return

    src = srcs[si]
    url = (src.get("url") or "").split("#")[0].strip()
    title = m.get("title") or "فيلم"
    if src.get("quality"):
        title = f"{title} [{src['quality']}]"

    context.user_data["pending_stream_url"] = url
    context.user_data["pending_stream_title"] = title
    # headers اختيارية للمصدر
    if src.get("headers"):
        context.user_data["pending_stream_headers"] = src["headers"]

    from handlers.streams import start_rtmp_setup_flags
    await start_rtmp_setup_flags(update, context)


async def movie_m3u_all_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    results = context.user_data.get("movie_results") or []
    if not results:
        await query.answer("لا نتائج", show_alert=True)
        return
    lines = ["#EXTM3U"]
    for m in results:
        for s in m.get("sources") or []:
            url = s.get("url")
            if not url:
                continue
            name = m.get("title") or "فيلم"
            if s.get("quality"):
                name += f" [{s['quality']}]"
            lines.append(f'#EXTINF:-1,{name}')
            lines.append(url)
    text = "\n".join(lines)
    if len(text) > 3500:
        text = "\n".join(lines[:80]) + "\n# ... truncated"
    await query.message.reply_text(f"<pre>{text[:3500]}</pre>", parse_mode="HTML")
