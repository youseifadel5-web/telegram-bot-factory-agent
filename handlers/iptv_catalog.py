"""IPTV catalog UI — باقات القنوات (عالمي) مع تقسيم عربي / أجنبي / مترجم."""
from __future__ import annotations

import logging

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes

from services import iptv_catalog as cat
from utils.helpers import safe_edit_message

logger = logging.getLogger(__name__)

PER_ROW = 2
PER_PAGE = 24
PKGS_PER_PAGE = 18

LANG_LABELS = {
    "ara": "🇸🇦 قنوات عربية",
    "for": "🌍 قنوات أجنبية",
    "cc": "💬 قنوات مترجمة",
    "all": "🎬 كل القنوات",
}


def _rows(buttons, per_row=PER_ROW):
    return [buttons[i:i + per_row] for i in range(0, len(buttons), per_row)]


async def catalog_menu_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """قائمة الباقات (التصنيفات + الدول) — أيقونة لكل باقة."""
    query = update.callback_query
    try:
        await query.answer()
    except Exception:
        pass
    try:
        page = int(query.data.split(":")[1]) if ":" in query.data else 0
    except Exception:
        page = 0

    buttons = []
    # quick countries first (مصر وأهم الدول العربية)
    for key, icon, label in cat.COUNTRY_PACKAGES:
        buttons.append(InlineKeyboardButton(f"{icon} {label}", callback_data=f"cat_open:{key}"))
    rows = _rows(buttons, per_row=3)

    cat_buttons = [
        InlineKeyboardButton(f"{icon} {label}", callback_data=f"cat_open:{key}")
        for key, icon, label in cat.CATEGORY_PACKAGES
    ]
    cat_rows = _rows(cat_buttons, per_row=3)
    total_pkg_pages = max(1, (len(cat_rows) + PKGS_PER_PAGE - 1) // PKGS_PER_PAGE)
    page = max(0, min(page, total_pkg_pages - 1))
    cat_rows = cat_rows[page * PKGS_PER_PAGE:(page + 1) * PKGS_PER_PAGE]

    nav = []
    # لا تُعرض صفوف التنقّل عندما تكون صفحة واحدة (كان يظهر زر «1/1» بلا فائدة).
    if total_pkg_pages > 1:
        if page > 0:
            nav.append(InlineKeyboardButton("⬅️ السابق", callback_data=f"cat_menu:{page-1}"))
        nav.append(InlineKeyboardButton(f"{page+1}/{total_pkg_pages}", callback_data="noop"))
        if page < total_pkg_pages - 1:
            nav.append(InlineKeyboardButton("التالي ➡️", callback_data=f"cat_menu:{page+1}"))

    keyboard = rows + cat_rows + ([nav] if nav else []) + [[
        InlineKeyboardButton("🔄 تحديث الباقات", callback_data="cat_refresh"),
        InlineKeyboardButton("🔙 IPTV", callback_data="iptv_menu"),
    ]]

    await safe_edit_message(
        query,
        "🌍 <b>باقات القنوات — كل العالم</b>\n\n"
        "اختر باقة من التصنيفات أو دولة من الأعلى.\n"
        "جوه كل باقة تقدر تختار: قنوات عربية / أجنبية / مترجمة.\n"
        "<i>المصدر: iptv-org — يتحدث تلقائياً.</i>",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(keyboard),
    )


async def catalog_refresh_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer("جاري تحديث الباقات من المصدر...")
    await cat.refresh_all()
    # reopen the menu after clearing cache
    query.data = "cat_menu:0"
    await catalog_menu_callback(update, context)


async def catalog_open_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """داخل الباقة: اختيار عربي / أجنبي / مترجم / الكل."""
    query = update.callback_query
    try:
        await query.answer()
    except Exception:
        pass
    key = query.data.split(":", 1)[1]
    meta = cat.package_meta(key)
    if not meta:
        await query.answer("باقة غير معروفة", show_alert=True)
        return
    icon, label = meta

    # count cached channels (without fetching)
    cached = cat._load_cached_package(key) or []
    counts = {
        "all": len(cached),
        "ara": sum(1 for c in cached if c.get("arabic")),
        "for": sum(1 for c in cached if not c.get("arabic")),
        "cc": sum(1 for c in cached if cat.is_cc_channel(c)),
    }

    def row(lang):
        cnt = f" ({counts[lang]})" if counts["all"] else ""
        return [InlineKeyboardButton(LANG_LABELS[lang] + cnt, callback_data=f"cat_list:{key}:{lang}:0")]

    await safe_edit_message(
        query,
        f"{icon} <b>{label}</b>\n\nاختر نوع القنوات:",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup([
            row("ara"),
            row("for"),
            row("cc"),
            row("all"),
            [InlineKeyboardButton("🔙 باقات القنوات", callback_data="cat_menu")],
        ]),
    )


async def catalog_list_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """عرض قنوات الباقة حسب النوع مع ترقيم صفحات."""
    query = update.callback_query
    try:
        await query.answer()
    except Exception:
        pass
    try:
        _, key, lang, page = query.data.split(":")
        page = max(0, int(page))
    except Exception:
        await query.answer("طلب غير صالح", show_alert=True)
        return

    meta = cat.package_meta(key)
    if not meta:
        await query.answer("باقة غير معروفة", show_alert=True)
        return
    icon, label = meta

    try:
        channels = await cat.get_package(key)
    except Exception as e:
        logger.warning("catalog package fetch failed (%s): %s", key, e)
        await safe_edit_message(
            query,
            f"⚠️ تعذر تحميل باقة {label} الآن.\n"
            "المصدر قد يكون مشغولاً — جرّب «تحديث الباقات» أو أعد المحاولة بعد قليل.",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🔄 إعادة المحاولة", callback_data=f"cat_list:{key}:{lang}:0")],
                [InlineKeyboardButton("🔙 رجوع", callback_data=f"cat_open:{key}")],
            ]),
        )
        return

    channels = cat.filter_package(channels, lang)
    if not channels:
        await safe_edit_message(
            query,
            f"{icon} {label}\nلا توجد قنوات في هذا التصنيف حالياً.",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🔙 رجوع", callback_data=f"cat_open:{key}")],
            ]),
        )
        return

    total_pages = max(1, (len(channels) + PER_PAGE - 1) // PER_PAGE)
    page = min(page, total_pages - 1)
    chunk = channels[page * PER_PAGE:(page + 1) * PER_PAGE]

    btns = []
    for pos, ch in enumerate(chunk):
        idx = page * PER_PAGE + pos  # index inside the filtered list
        name = (ch.get("name") or "قناة")[:24]
        mark = "💬 " if cat.is_cc_channel(ch) else ""
        geo = " 🚫" if ch.get("geo_blocked") else ""
        btns.append(InlineKeyboardButton(
            f"▶️ {mark}{name}{geo}", callback_data=f"cat_play:{key}:{lang}:{idx}"
        ))

    nav = []
    if page > 0:
        nav.append(InlineKeyboardButton("⬅️", callback_data=f"cat_list:{key}:{lang}:{page-1}"))
    nav.append(InlineKeyboardButton(f"{page+1}/{total_pages}", callback_data="noop"))
    if page < total_pages - 1:
        nav.append(InlineKeyboardButton("➡️", callback_data=f"cat_list:{key}:{lang}:{page+1}"))

    keyboard = _rows(btns) + [nav] + [
        [InlineKeyboardButton("🔙 رجوع للباقة", callback_data=f"cat_open:{key}")],
        [InlineKeyboardButton("🌍 الباقات", callback_data="cat_menu")],
    ]
    await safe_edit_message(
        query,
        f"{icon} <b>{label}</b> — {LANG_LABELS.get(lang, '')}\n"
        f"عدد القنوات: <b>{len(channels)}</b>\n"
        "<i>💬 = قناة مترجمة · 🚫 = محجوبة جغرافياً</i>",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(keyboard),
    )


async def catalog_play_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """تشغيل قناة من الكتالوج — نفس مسار تشغيل IPTV."""
    query = update.callback_query
    try:
        await query.answer()
    except Exception:
        pass
    try:
        _, key, lang, idx = query.data.split(":")
        idx = int(idx)
    except Exception:
        await query.answer("طلب غير صالح", show_alert=True)
        return

    try:
        channels = cat.filter_package(await cat.get_package(key), lang)
        ch = channels[idx]
    except Exception:
        await query.answer("القناة غير موجودة — حدّث القائمة", show_alert=True)
        return

    src = (ch.get("url") or "").split("#")[0].strip()
    if not src:
        await query.answer("رابط القناة غير صالح", show_alert=True)
        return
    context.user_data["pending_stream_url"] = src
    context.user_data["pending_stream_title"] = ch.get("name") or "IPTV"
    # بعض القنوات تحتاج User-Agent / Referer خاصين لتمرير الحظر
    ua = ch.get("user_agent") or ""
    referrer = ch.get("referrer") or ""
    hdrs = {}
    if ua:
        hdrs["User-Agent"] = ua
    if referrer:
        hdrs["Referer"] = referrer
    context.user_data["pending_stream_headers"] = hdrs or None
    from handlers.streams import start_rtmp_setup_flags
    await start_rtmp_setup_flags(update, context)
