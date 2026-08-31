# -*- coding: utf-8 -*-
from __future__ import annotations

import os
from telegram import InlineKeyboardButton, InlineKeyboardMarkup

GENRES = [
    ("👻 رعب", "horror"),
    ("💥 أكشن", "action"),
    ("🎭 دراما", "drama"),
    ("😂 كوميدي", "comedy"),
    ("❤️ رومانسي", "romance"),
    ("🚀 خيال علمي", "scifi"),
    ("🧸 أنيميشن", "animation"),
]

COUNTRIES = [
    ("🇪🇬 مصر", "Egypt"),
    ("🇺🇸 أمريكا", "USA"),
    ("🇬🇧 بريطانيا", "UK"),
    ("🇹🇷 تركيا", "Turkey"),
    ("🇮🇳 الهند", "India"),
    ("🇰🇷 كوريا", "Korea"),
    ("🇯🇵 اليابان", "Japan"),
    ("🇨🇳 الصين", "China"),
    ("🇫🇷 فرنسا", "France"),
    ("🌍 أخرى", "Other"),
]


def unified_enabled() -> bool:
    """المنصة الموحّدة اختيارية — env أو ملف .unified_enabled"""
    env = os.getenv("UNIFIED_PLATFORM_ENABLED", "").strip().lower()
    if env in ("1", "true", "yes", "on"):
        return True
    if env in ("0", "false", "no", "off"):
        return False
    try:
        from pathlib import Path as _P
        return (_P(__file__).resolve().parent.parent / ".unified_enabled").exists()
    except Exception:
        return False


def _nav(back: str = "hub_home", home: str = "hub_home") -> list:
    return [[
        InlineKeyboardButton("⬅️ رجوع", callback_data=back),
        InlineKeyboardButton("🏠 البوابة", callback_data=home),
    ]]


def hub_home(is_admin: bool = False) -> InlineKeyboardMarkup:
    """البوابة القديمة: 3 منصات + منصة موحّدة اختيارية."""
    rows = [
        [InlineKeyboardButton("🎬 يوسف فيلمز", callback_data="plat:youseif")],
        [InlineKeyboardButton("🎞️ سينما نوفا", callback_data="plat:nova")],
        [InlineKeyboardButton("🌟 أوريون بلس", callback_data="plat:orion")],
    ]
    if unified_enabled():
        rows.append([InlineKeyboardButton("✨ المنصة الموحّدة (تجريبي)", callback_data="plat:unified")])
    rows.append([
        InlineKeyboardButton("🔍 بحث سريع", callback_data="lib:search"),
        InlineKeyboardButton("🕘 آخر مشاهدة", callback_data="user:hist"),
    ])
    if is_admin:
        rows.append([InlineKeyboardButton("👑 لوحة الإدارة", callback_data="adm:home")])
        # أدمن يقدر يشغّل/يوقف الموحّدة من اللوحة
        flag = "🟢 مفعّلة" if unified_enabled() else "🔴 متوقفة"
        rows.append([InlineKeyboardButton(f"⚙️ الموحّدة: {flag}", callback_data="adm:toggle_unified")])
    return InlineKeyboardMarkup(rows)


def main_menu(is_admin: bool = False) -> InlineKeyboardMarkup:
    """للتوافق — /start يفتح البوابة."""
    return hub_home(is_admin=is_admin)


def library_home(is_admin: bool = False) -> InlineKeyboardMarkup:
    return hub_home(is_admin=is_admin)


def platform_menu(platform: str, is_admin: bool = False) -> InlineKeyboardMarkup:
    """قائمة داخل منصة واحدة (شكل قديم)."""
    if platform == "youseif":
        rows = [
            [InlineKeyboardButton("🎬 الأفلام", callback_data="y:type:movie"),
             InlineKeyboardButton("📺 المسلسلات", callback_data="y:type:series")],
            [InlineKeyboardButton("📡 القنوات المباشرة", callback_data="y:type:live")],
            [InlineKeyboardButton("🔍 بحث", callback_data="lib:search")],
            [InlineKeyboardButton("❤️ المفضلة", callback_data="user:fav"),
             InlineKeyboardButton("🕘 آخر مشاهدة", callback_data="user:hist")],
        ]
    elif platform == "nova":
        rows = [
            [InlineKeyboardButton("🎬 أفلام", callback_data="lib:type:movie"),
             InlineKeyboardButton("📺 مسلسلات", callback_data="lib:type:series")],
            [InlineKeyboardButton("🔍 بحث نوفا", callback_data="lib:search")],
        ]
    elif platform == "orion":
        rows = [
            [InlineKeyboardButton("🎬 أفلام", callback_data="lib:type:movie"),
             InlineKeyboardButton("📺 مسلسلات", callback_data="lib:type:series")],
            [InlineKeyboardButton("🔍 بحث أوريون", callback_data="lib:search")],
        ]
    else:
        # unified library
        rows = [
            [InlineKeyboardButton("🎬 أفلام", callback_data="lib:type:movie"),
             InlineKeyboardButton("📺 مسلسلات", callback_data="lib:type:series")],
            [InlineKeyboardButton("📡 قنوات", callback_data="lib:type:live")],
            [InlineKeyboardButton("🌍 حسب الدولة", callback_data="lib:countries")],
            [InlineKeyboardButton("🔍 بحث", callback_data="lib:search"),
             InlineKeyboardButton("🤖 اطلب من AI", callback_data="ai:start")],
        ]
        g_row = []
        for label, gid in GENRES[:4]:
            g_row.append(InlineKeyboardButton(label, callback_data=f"lib:genre:{gid}"))
        rows.append(g_row)
        g_row2 = []
        for label, gid in GENRES[4:]:
            g_row2.append(InlineKeyboardButton(label, callback_data=f"lib:genre:{gid}"))
        if g_row2:
            rows.append(g_row2)
    rows.extend(_nav(back="hub_home", home="hub_home"))
    return InlineKeyboardMarkup(rows)


def countries_kb() -> InlineKeyboardMarkup:
    rows = []
    row = []
    for label, cid in COUNTRIES:
        row.append(InlineKeyboardButton(label, callback_data=f"lib:country:{cid}"))
        if len(row) == 2:
            rows.append(row)
            row = []
    if row:
        rows.append(row)
    rows.extend(_nav(back="hub_home"))
    return InlineKeyboardMarkup(rows)


def country_genres_kb(country: str) -> InlineKeyboardMarkup:
    rows = [
        [
            InlineKeyboardButton("🎬 أفلام", callback_data=f"lib:cotype:{country}:movie"),
            InlineKeyboardButton("📺 مسلسلات", callback_data=f"lib:cotype:{country}:series"),
        ],
    ]
    row = []
    for label, gid in GENRES:
        row.append(InlineKeyboardButton(label, callback_data=f"lib:cogenre:{country}:{gid}"))
        if len(row) == 2:
            rows.append(row)
            row = []
    if row:
        rows.append(row)
    rows.extend(_nav(back="lib:countries"))
    return InlineKeyboardMarkup(rows)


def genre_countries_kb(genre: str) -> InlineKeyboardMarkup:
    rows = []
    row = []
    for label, cid in COUNTRIES:
        row.append(InlineKeyboardButton(label, callback_data=f"lib:gencountry:{genre}:{cid}"))
        if len(row) == 2:
            rows.append(row)
            row = []
    if row:
        rows.append(row)
    rows.append([
        InlineKeyboardButton("📋 عرض الكل", callback_data=f"lib:gensort:{genre}:rating"),
        InlineKeyboardButton("🔥 الأكثر", callback_data=f"lib:gensort:{genre}:popular"),
    ])
    rows.append([
        InlineKeyboardButton("🆕 الأحدث", callback_data=f"lib:gensort:{genre}:newest"),
        InlineKeyboardButton("⭐ تقييم", callback_data=f"lib:gensort:{genre}:rating"),
    ])
    rows.extend(_nav(back="hub_home"))
    return InlineKeyboardMarkup(rows)


def results_kb(items, page: int, pages: int, prefix: str = "lib:open", back: str = "hub_home") -> InlineKeyboardMarkup:
    rows = []
    if not items:
        rows.append([InlineKeyboardButton("🔍 بحث بديل", callback_data="lib:search")])
    else:
        for i, it in enumerate(items):
            typ = it.type.value if hasattr(it.type, "value") else str(it.type)
            icon = "🎬" if typ == "movie" else ("📺" if typ == "series" else "📡")
            badge = ("🖼" if getattr(it, "poster", None) else "")
            title = (it.title or "بدون عنوان")[:30]
            rows.append([InlineKeyboardButton(
                f"{icon} {title} {badge}".strip(),
                callback_data=f"{prefix}:{page}:{i}",
            )])
        if pages > 1:
            nav = []
            if page > 0:
                nav.append(InlineKeyboardButton("⬅️ السابق", callback_data=f"lib:page:{page-1}"))
            nav.append(InlineKeyboardButton(f"{page+1}/{pages}", callback_data="noop"))
            if page < pages - 1:
                nav.append(InlineKeyboardButton("التالي ➡️", callback_data=f"lib:page:{page+1}"))
            rows.append(nav)
    rows.extend(_nav(back=back))
    return InlineKeyboardMarkup(rows)


def item_kb(item_id: str, back: str = "hub_home") -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("▶️ مشاهدة", callback_data=f"play:start:{item_id}")],
        [
            InlineKeyboardButton("❤️ مفضلة", callback_data=f"user:addfav:{item_id}"),
            InlineKeyboardButton("🤖 مشابه", callback_data=f"ai:similar:{item_id}"),
        ],
        [
            InlineKeyboardButton("⬅️ رجوع للنتائج", callback_data="lib:results"),
            InlineKeyboardButton("🏠 البوابة", callback_data="hub_home"),
        ],
    ])


def qualities_kb(item_id: str, qualities) -> InlineKeyboardMarkup:
    rows = []
    row = []
    for q in qualities:
        row.append(InlineKeyboardButton(str(q.label), callback_data=f"play:q:{item_id}:{q.label}"))
        if len(row) == 2:
            rows.append(row)
            row = []
    if row:
        rows.append(row)
    if not rows:
        rows.append([InlineKeyboardButton("▶️ تشغيل", callback_data=f"play:q:{item_id}:default")])
    rows.append([
        InlineKeyboardButton("⬅️ رجوع", callback_data=f"lib:item:{item_id}"),
        InlineKeyboardButton("🏠 البوابة", callback_data="hub_home"),
    ])
    return InlineKeyboardMarkup(rows)


def admin_home_kb() -> InlineKeyboardMarkup:
    flag = "🟢 مفعّلة" if unified_enabled() else "🔴 متوقفة"
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📊 الإحصائيات", callback_data="adm:stats")],
        [InlineKeyboardButton("📡 المصادر", callback_data="adm:plugins")],
        [InlineKeyboardButton("🚫 المحظور", callback_data="adm:blocks")],
        [InlineKeyboardButton("🧠 AI", callback_data="adm:ai")],
        [InlineKeyboardButton("📝 السجل", callback_data="adm:audit")],
        [InlineKeyboardButton("🗄 الكاش", callback_data="adm:cache")],
        [InlineKeyboardButton(f"⚙️ المنصة الموحّدة: {flag}", callback_data="adm:toggle_unified")],
        [
            InlineKeyboardButton("⬅️ رجوع", callback_data="hub_home"),
            InlineKeyboardButton("🏠 البوابة", callback_data="hub_home"),
        ],
    ])


def admin_blocks_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📋 عرض المحظور", callback_data="adm:blocklist:0")],
        [InlineKeyboardButton("➕ حظر محتوى", callback_data="adm:blockadd")],
        [InlineKeyboardButton("📦 حظر جماعي", callback_data="adm:blockbulk")],
        [InlineKeyboardButton("🔓 فك حظر", callback_data="adm:unblock")],
        [
            InlineKeyboardButton("⬅️ رجوع", callback_data="adm:home"),
            InlineKeyboardButton("🏠 البوابة", callback_data="hub_home"),
        ],
    ])


def back_home(back: str = "hub_home") -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(_nav(back=back))


def empty_results_kb(back: str = "hub_home") -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🔍 بحث", callback_data="lib:search")],
        [InlineKeyboardButton("🏠 البوابة", callback_data="hub_home")],
        [
            InlineKeyboardButton("⬅️ رجوع", callback_data=back),
            InlineKeyboardButton("🏠 البوابة", callback_data="hub_home"),
        ],
    ])
