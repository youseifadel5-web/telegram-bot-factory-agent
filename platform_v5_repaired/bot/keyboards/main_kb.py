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

SOURCE_BOTS = [
    ("📺 بوت يوسف فيلم", "youseif"),
    ("🍿 سينما نوفا", "nova"),
    ("🎬 أوريون بلس", "orion"),
]


def _nav(back: str = "lib:home", home: str = "home") -> list:
    """Standard bottom row: رجوع + الرئيسية — always present."""
    return [[
        InlineKeyboardButton("⬅️ رجوع", callback_data=back),
        InlineKeyboardButton("🏠 الرئيسية", callback_data=home),
    ]]


def main_menu(is_admin: bool = False) -> InlineKeyboardMarkup:
    """القائمة الرئيسية — منصة موحدة + أقسام البوتات القديمة كاملة + قنوات مباشرة."""
    rows = [
        [InlineKeyboardButton("🏛️ المنصة الموحدة — كل المصادر", callback_data="lib:home")],
        [
            InlineKeyboardButton("🎬 أفلام", callback_data="lib:type:movie"),
            InlineKeyboardButton("📺 مسلسلات", callback_data="lib:type:series"),
            InlineKeyboardButton("📡 قنوات مباشرة", callback_data="lib:live"),
        ],
        [InlineKeyboardButton("🌍 حسب الدولة", callback_data="lib:countries")],
        [
            InlineKeyboardButton("🔍 بحث", callback_data="lib:search"),
            InlineKeyboardButton("🤖 اطلب من AI", callback_data="ai:start"),
        ],
        [
            InlineKeyboardButton("🕘 آخر مشاهدة", callback_data="user:hist"),
            InlineKeyboardButton("❤️ المفضلة", callback_data="user:fav"),
        ],
        [InlineKeyboardButton("────── البوتات القديمة ──────", callback_data="noop")],
    ]
    for label, sid in SOURCE_BOTS:
        rows.append([InlineKeyboardButton(label, callback_data=f"src:{sid}")])
    if is_admin:
        rows.append([InlineKeyboardButton("👑 لوحة الإدارة", callback_data="adm:home")])
    return InlineKeyboardMarkup(rows)


def library_home(is_admin: bool = False) -> InlineKeyboardMarkup:
    return main_menu(is_admin=is_admin)


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
    rows.extend(_nav(back="lib:home"))
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
    rows.extend(_nav(back="lib:home"))
    return InlineKeyboardMarkup(rows)


def results_kb(items, page: int, pages: int, prefix: str = "lib:open", back: str = "lib:home") -> InlineKeyboardMarkup:
    rows = []
    if not items:
        rows.append([InlineKeyboardButton("🔍 بحث بديل", callback_data="lib:search")])
    else:
        for i, it in enumerate(items):
            typ = it.type.value if hasattr(it.type, "value") else str(it.type)
            icon = "🎬" if typ == "movie" else ("📺" if typ == "series" else "📡")
            badge = ("🖼" if it.poster else "") + ("📝" if it.overview else "")
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


def item_kb(item_id: str, back: str = "lib:home") -> InlineKeyboardMarkup:
    """أزرار تفصيلية: مشاهدة + كل الروابط والجودات + مفضلة + مشابه."""
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("▶️ مشاهدة (فحص الجودة)", callback_data=f"play:start:{item_id}")],
        [InlineKeyboardButton("🎞️ كل الروابط والجودات", callback_data=f"play:links:{item_id}")],
        [
            InlineKeyboardButton("❤️ مفضلة", callback_data=f"user:addfav:{item_id}"),
            InlineKeyboardButton("🤖 مشابه", callback_data=f"ai:similar:{item_id}"),
        ],
        [
            InlineKeyboardButton("⬅️ رجوع للنتائج", callback_data="lib:results"),
            InlineKeyboardButton("🏠 الرئيسية", callback_data="home"),
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
    rows.append([
        InlineKeyboardButton("⬅️ رجوع", callback_data=f"lib:item:{item_id}"),
        InlineKeyboardButton("🏠 الرئيسية", callback_data="home"),
    ])
    return InlineKeyboardMarkup(rows)


def admin_home_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📊 الإحصائيات", callback_data="adm:stats")],
        [InlineKeyboardButton("📡 المصادر", callback_data="adm:plugins")],
        [InlineKeyboardButton("🚫 المحظور", callback_data="adm:blocks")],
        [InlineKeyboardButton("🧠 AI", callback_data="adm:ai")],
        [InlineKeyboardButton("📝 السجل", callback_data="adm:audit")],
        [InlineKeyboardButton("🗄 الكاش", callback_data="adm:cache")],
        [
            InlineKeyboardButton("⬅️ رجوع", callback_data="home"),
            InlineKeyboardButton("🏠 الرئيسية", callback_data="home"),
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
            InlineKeyboardButton("🏠 الرئيسية", callback_data="home"),
        ],
    ])


def back_home(back: str = "lib:home") -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(_nav(back=back))


def empty_results_kb(back: str = "lib:home") -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🔍 بحث", callback_data="lib:search")],
        [InlineKeyboardButton("📚 المكتبة", callback_data="lib:home")],
        [
            InlineKeyboardButton("⬅️ رجوع", callback_data=back),
            InlineKeyboardButton("🏠 الرئيسية", callback_data="home"),
        ],
    ])
