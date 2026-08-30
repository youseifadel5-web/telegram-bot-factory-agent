# -*- coding: utf-8 -*-
from __future__ import annotations

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


def main_menu(is_admin: bool = False) -> InlineKeyboardMarkup:
    rows = [
        [InlineKeyboardButton("📚 المكتبة", callback_data="lib:home")],
        [
            InlineKeyboardButton("🎬 أفلام", callback_data="lib:type:movie"),
            InlineKeyboardButton("📺 مسلسلات", callback_data="lib:type:series"),
        ],
        [InlineKeyboardButton("📡 القنوات", callback_data="lib:type:live")],
        [InlineKeyboardButton("🌍 حسب الدولة", callback_data="lib:countries")],
        [InlineKeyboardButton("🔍 بحث", callback_data="lib:search")],
        [InlineKeyboardButton("🤖 اطلب من AI", callback_data="ai:start")],
        [
            InlineKeyboardButton("❤️ المفضلة", callback_data="user:fav"),
            InlineKeyboardButton("🕘 آخر مشاهدة", callback_data="user:hist"),
        ],
    ]
    # genres row
    g_row = []
    for label, gid in GENRES[:4]:
        g_row.append(InlineKeyboardButton(label, callback_data=f"lib:genre:{gid}"))
    rows.append(g_row)
    g_row2 = []
    for label, gid in GENRES[4:]:
        g_row2.append(InlineKeyboardButton(label, callback_data=f"lib:genre:{gid}"))
    if g_row2:
        rows.append(g_row2)
    if is_admin:
        rows.append([InlineKeyboardButton("👑 لوحة التحكم", callback_data="adm:home")])
    return InlineKeyboardMarkup(rows)


def library_home() -> InlineKeyboardMarkup:
    return main_menu()


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
    rows.append([InlineKeyboardButton("🏠 الرئيسية", callback_data="home")])
    return InlineKeyboardMarkup(rows)


def country_genres_kb(country: str) -> InlineKeyboardMarkup:
    rows = [
        [InlineKeyboardButton("🎬 أفلام", callback_data=f"lib:cotype:{country}:movie"),
         InlineKeyboardButton("📺 مسلسلات", callback_data=f"lib:cotype:{country}:series")],
    ]
    row = []
    for label, gid in GENRES:
        row.append(InlineKeyboardButton(label, callback_data=f"lib:cogenre:{country}:{gid}"))
        if len(row) == 2:
            rows.append(row)
            row = []
    if row:
        rows.append(row)
    rows.append([
        InlineKeyboardButton("⬅️ رجوع", callback_data="lib:countries"),
        InlineKeyboardButton("🏠 الرئيسية", callback_data="home"),
    ])
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
        InlineKeyboardButton("🔥 الأكثر", callback_data=f"lib:gensort:{genre}:popular"),
        InlineKeyboardButton("🆕 الأحدث", callback_data=f"lib:gensort:{genre}:newest"),
        InlineKeyboardButton("⭐ تقييم", callback_data=f"lib:gensort:{genre}:rating"),
    ])
    rows.append([
        InlineKeyboardButton("⬅️ رجوع", callback_data="lib:home"),
        InlineKeyboardButton("🏠 الرئيسية", callback_data="home"),
    ])
    return InlineKeyboardMarkup(rows)


def results_kb(items, page: int, pages: int, prefix: str = "lib:open") -> InlineKeyboardMarkup:
    rows = []
    for i, it in enumerate(items):
        icon = "🎬" if it.type.value == "movie" else ("📺" if it.type.value == "series" else "📡")
        badge = ("🖼" if it.poster else "") + ("📝" if it.overview else "")
        rows.append([InlineKeyboardButton(
            f"{icon} {it.title[:30]} {badge}",
            callback_data=f"{prefix}:{page}:{i}",
        )])
    if pages > 1:
        nav = []
        if page > 0:
            nav.append(InlineKeyboardButton("⬅️", callback_data=f"lib:page:{page-1}"))
        nav.append(InlineKeyboardButton(f"{page+1}/{pages}", callback_data="noop"))
        if page < pages - 1:
            nav.append(InlineKeyboardButton("➡️", callback_data=f"lib:page:{page+1}"))
        rows.append(nav)
    rows.append([
        InlineKeyboardButton("⬅️ رجوع", callback_data="lib:home"),
        InlineKeyboardButton("🏠 الرئيسية", callback_data="home"),
    ])
    return InlineKeyboardMarkup(rows)


def item_kb(item_id: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("▶️ مشاهدة", callback_data=f"play:start:{item_id}")],
        [InlineKeyboardButton("❤️ مفضلة", callback_data=f"user:addfav:{item_id}"),
         InlineKeyboardButton("🤖 مشابه", callback_data=f"ai:similar:{item_id}")],
        [InlineKeyboardButton("⬅️ رجوع", callback_data="lib:home"),
         InlineKeyboardButton("🏠 الرئيسية", callback_data="home")],
    ])


def qualities_kb(item_id: str, qualities) -> InlineKeyboardMarkup:
    rows = []
    row = []
    for q in qualities:
        row.append(InlineKeyboardButton(q.label, callback_data=f"play:q:{item_id}:{q.label}"))
        if len(row) == 2:
            rows.append(row)
            row = []
    if row:
        rows.append(row)
    rows.append([InlineKeyboardButton("⬅️ رجوع", callback_data=f"lib:item:{item_id}")])
    return InlineKeyboardMarkup(rows)


def admin_home_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📊 الإحصائيات", callback_data="adm:stats")],
        [InlineKeyboardButton("📡 المصادر", callback_data="adm:plugins")],
        [InlineKeyboardButton("🚫 المحظور", callback_data="adm:blocks")],
        [InlineKeyboardButton("🧠 AI", callback_data="adm:ai")],
        [InlineKeyboardButton("📝 السجل", callback_data="adm:audit")],
        [InlineKeyboardButton("🗄 الكاش", callback_data="adm:cache")],
        [InlineKeyboardButton("🏠 الرئيسية", callback_data="home")],
    ])


def admin_blocks_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📋 عرض المحظور", callback_data="adm:blocklist:0")],
        [InlineKeyboardButton("➕ حظر محتوى", callback_data="adm:blockadd")],
        [InlineKeyboardButton("📦 حظر جماعي", callback_data="adm:blockbulk")],
        [InlineKeyboardButton("🔓 فك حظر", callback_data="adm:unblock")],
        [InlineKeyboardButton("⬅️ رجوع", callback_data="adm:home")],
    ])


def back_home() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([[
        InlineKeyboardButton("⬅️ رجوع", callback_data="lib:home"),
        InlineKeyboardButton("🏠 الرئيسية", callback_data="home"),
    ]])
