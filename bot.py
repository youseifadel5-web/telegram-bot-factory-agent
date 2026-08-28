# -*- coding: utf-8 -*-
"""
🎬 بوت تيليجرام سينما — Standalone (بدون أي خادم خارجي).
يشتغل من قاعدة بيانات SQLite مع محتوى جاهز، وكل زر مربوط بمعالج حقيقي.

التشغيل:
  - ضع BOT_TOKEN, API_ID, API_HASH في GitHub Secrets (3 قيم فقط).
  - باقي الإعدادات اختيارية في config.py (لو غير موجودة، يستخدم قيمًا افتراضية).
  - ارفع الكود ثم Actions → Run workflow → Run workflow.
"""

import asyncio
import logging
import os
import random
import sqlite3
import sys
from datetime import datetime
from html import escape
from typing import Any, Dict, List, Optional

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.constants import ParseMode
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

# ============ الأسرار الثلاثة فقط من GitHub Secrets ============
BOT_TOKEN = os.getenv("BOT_TOKEN", "")
API_ID = int(os.getenv("API_ID", "0") or 0)
API_HASH = os.getenv("API_HASH", "")

# ============ بقية الإعدادات من config.py (اختياري) ============
try:
    import config as _cfg
except ImportError:
    _cfg = None

def _cfg_attr(name: str, default: Any = None) -> Any:
    return getattr(_cfg, name, default) if _cfg else default

ITEMS_PER_PAGE = int(_cfg_attr("ITEMS_PER_PAGE", 8))
BOT_NAME        = str(_cfg_attr("BOT_NAME", "🎬 سينما بوت"))
DB_PATH         = str(_cfg_attr("DB_PATH", "cinema_bot.db"))

# ============ Logging ============
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

# ============ دوال مساعدة ============
def esc(t: Any) -> str:
    return escape(str(t)) if t is not None else "—"

def pi(v: Any, default: int = 0) -> int:
    try:
        return int(v)
    except Exception:
        return default

ICONS = {
    "live": "📡", "movie": "🎬", "series": "📺",
    "رياضة": "⚽", "أكشن": "💥", "كوميدي": "😂", "دراما": "🎭",
    "رعب": "👻", "رومانسي": "💕", "خيال": "🧙", "وثائقي": "📹",
    "أطفال": "🧸", "مصارعة": "🤼", "أفلام": "🎬", "مسلسلات": "📺",
    "مسلسل": "📺", "فيلم": "🎬", "أنمي": "⛩️", "تاريخي": "📜",
    "إخبارية": "📰", "منوعات": "📡",
}
def icon_for(text: str) -> str:
    if not text:
        return "🎞️"
    t = text.lower()
    for k, v in ICONS.items():
        if k in t:
            return v
    return "🎞️"


# ============ محتوى افتراضي (Seed Data) ============
DEFAULT_CATEGORIES = [
    ("أفلام عربية",   "movie",  "🎬"),
    ("أفلام أجنبية", "movie",  "🎬"),
    ("أكشن",          "movie",  "💥"),
    ("كوميدي",        "movie",  "😂"),
    ("مسلسلات عربية",  "series", "📺"),
    ("مسلسلات أجنبية","series", "📺"),
    ("أنمي",          "series", "⛩️"),
    ("قنوات إخبارية","live",   "📰"),
    ("قنوات رياضية",  "live",   "⚽"),
    ("قنوات منوعات",  "live",   "📡"),
]

DEFAULT_ITEMS = [
    # أفلام عربية
    ("الكنز", "movie", "أفلام عربية", 2017, 7.5, "فيلم مصري عن صراع على كنز مدفون.", "HD", "ساعتين"),
    ("ولاد رزق", "movie", "أفلام عربية", 2015, 8.2, "أخوة في صراع مع تجار سلاح.", "HD", "ساعتين و20د"),
    # أفلام أجنبية
    ("Inception", "movie", "أفلام أجنبية", 2010, 8.8, "السطو على أحلام الآخرين عبر طبقات اللاوعي.", "4K", "ساعتين و28د"),
    ("The Dark Knight", "movie", "أفلام أجنبية", 2008, 9.0, "مواجهة باتمان مع الجوكر في جوثام.", "4K", "ساعتين و32د"),
    # أكشن
    ("Mad Max: Fury Road", "movie", "أكشن", 2015, 8.1, "مطاردة في عالم ما بعد الكارثة.", "4K", "ساعتين"),
    ("John Wick", "movie", "أكشن", 2014, 7.4, "قاتل سابق يطارد قتلة كلبه.", "HD", "ساعة و41د"),
    # كوميدي
    ("The Hangover", "movie", "كوميدي", 2009, 7.7, "رجال يبحثون عن صديقهم بعد ليلة مجنونة.", "HD", "ساعة و40د"),
    # مسلسلات عربية
    ("مسلسل اللعبة", "series", "مسلسلات عربية", 2020, 8.5, "كوميدي مصري عائلي.", "HD", 3, 60),
    ("مسلسل البرنس", "series", "مسلسلات عربية", 2020, 8.1, "دراما اجتماعية مصرية.", "HD", 1, 30),
    # مسلسلات أجنبية
    ("Breaking Bad", "series", "مسلسلات أجنبية", 2008, 9.5, "مدرس كيمياء يتحول لتاجر مخدرات.", "4K", 5, 62),
    ("Game of Thrones", "series", "مسلسلات أجنبية", 2011, 9.2, "صراع على عرش الممالك السبع.", "4K", 8, 73),
    # أنمي
    ("Attack on Titan", "series", "أنمي", 2013, 9.0, "البشرية في حرب مع التيتان.", "HD", 4, 75),
    # قنوات
    ("العربية", "live", "قنوات إخبارية", 2003, 0.0, "قناة إخبارية سعودية على مدار الساعة.", "HD", None, "https://www.alarabiya.net/live"),
    ("الجزيرة", "live", "قنوات إخبارية", 1996, 0.0, "قناة إخبارية قطرية على مدار الساعة.", "HD", None, "https://www.aljazeera.net/live"),
    ("بي إن سبورت", "live", "قنوات رياضية", 2003, 0.0, "قنوات رياضية متنوعة.", "4K", None, "https://www.beinsports.com"),
    ("SSC", "live", "قنوات رياضية", 2021, 0.0, "القناة السعودية الرياضية.", "HD", None, "https://ssc.sa"),
    ("MBC", "live", "قنوات منوعات", 1991, 0.0, "قنوات منوعات خليجية.", "HD", None, "https://www.mbc.net"),
]


# ============ قاعدة البيانات ============
class DB:
    def __init__(self, path: str = DB_PATH):
        self.path = path
        self._init_schema()
        self._seed_if_empty()

    def _con(self):
        c = sqlite3.connect(self.path)
        c.row_factory = sqlite3.Row
        c.execute("PRAGMA foreign_keys = ON")
        return c

    def _init_schema(self):
        with self._con() as c:
            c.executescript("""
                CREATE TABLE IF NOT EXISTS categories (
                    id   INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT UNIQUE NOT NULL,
                    type TEXT NOT NULL,
                    icon TEXT DEFAULT '🎞️'
                );
                CREATE TABLE IF NOT EXISTS items (
                    id         INTEGER PRIMARY KEY AUTOINCREMENT,
                    title      TEXT NOT NULL,
                    type       TEXT NOT NULL,
                    cat_id     INTEGER,
                    year       INTEGER,
                    rating     REAL DEFAULT 0,
                    desc       TEXT DEFAULT '',
                    quality    TEXT DEFAULT '',
                    duration   TEXT DEFAULT '',
                    seasons    INTEGER DEFAULT 0,
                    episodes   INTEGER DEFAULT 0,
                    url        TEXT DEFAULT '',
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY(cat_id) REFERENCES categories(id) ON DELETE SET NULL
                );
                CREATE TABLE IF NOT EXISTS users (
                    telegram_id INTEGER UNIQUE NOT NULL,
                    username    TEXT,
                    first_name  TEXT,
                    joined_at   TEXT DEFAULT CURRENT_TIMESTAMP
                );
                CREATE TABLE IF NOT EXISTS favorites (
                    user_id INTEGER NOT NULL,
                    item_id INTEGER NOT NULL,
                    added_at TEXT DEFAULT CURRENT_TIMESTAMP,
                    PRIMARY KEY(user_id, item_id)
                );
            """)

    def _seed_if_empty(self):
        with self._con() as c:
            if c.execute("SELECT COUNT(*) FROM categories").fetchone()[0] == 0:
                for name, t, ic in DEFAULT_CATEGORIES:
                    c.execute("INSERT INTO categories (name,type,icon) VALUES (?,?,?)", (name, t, ic))
            if c.execute("SELECT COUNT(*) FROM items").fetchone()[0] == 0:
                for row in DEFAULT_ITEMS:
                    title, t, cname, year, rating, desc, q, dur = row[:8]
                    seasons  = row[8] if len(row) > 8 else 0
                    episodes = row[9] if len(row) > 9 else 0
                    url      = row[10] if len(row) > 10 else ""
                    cat_id = c.execute("SELECT id FROM categories WHERE name=?", (cname,)).fetchone()
                    cat_id = cat_id["id"] if cat_id else None
                    c.execute("""
                        INSERT INTO items (title,type,cat_id,year,rating,desc,
                                           quality,duration,seasons,episodes,url)
                        VALUES (?,?,?,?,?,?,?,?,?,?,?)
                    """, (title, t, cat_id, year, rating, desc, q, dur, seasons, episodes, url))

    # ---- استعلامات ----
    def categories(self, type_: str) -> List[Dict]:
        with self._con() as c:
            return [dict(r) for r in c.execute(
                "SELECT * FROM categories WHERE type=? ORDER BY name", (type_,)).fetchall()]

    def items_in_cat(self, cat_id: int) -> List[Dict]:
        with self._con() as c:
            return [dict(r) for r in c.execute(
                "SELECT * FROM items WHERE cat_id=? ORDER BY id", (cat_id,)).fetchall()]

    def item(self, item_id: int) -> Optional[Dict]:
        with self._con() as c:
            r = c.execute("SELECT * FROM items WHERE id=?", (item_id,)).fetchone()
            return dict(r) if r else None

    def search(self, q: str) -> List[Dict]:
        with self._con() as c:
            return [dict(r) for r in c.execute(
                "SELECT * FROM items WHERE title LIKE ? OR desc LIKE ? ORDER BY id",
                (f"%{q}%", f"%{q}%")).fetchall()]

    def all_items(self) -> List[Dict]:
        with self._con() as c:
            return [dict(r) for r in c.execute("SELECT * FROM items ORDER BY id").fetchall()]

    def add_user(self, tid: int, username: str, first: str):
        with self._con() as c:
            c.execute(
                "INSERT OR IGNORE INTO users (telegram_id, username, first_name) VALUES (?,?,?)",
                (tid, username, first),
            )

    def add_favorite(self, uid: int, item_id: int) -> bool:
        with self._con() as c:
            cur = c.execute("INSERT OR IGNORE INTO favorites (user_id, item_id) VALUES (?,?)", (uid, item_id))
            return cur.rowcount > 0

    def remove_favorite(self, uid: int, item_id: int) -> bool:
        with self._con() as c:
            cur = c.execute("DELETE FROM favorites WHERE user_id=? AND item_id=?", (uid, item_id))
            return cur.rowcount > 0

    def is_favorite(self, uid: int, item_id: int) -> bool:
        with self._con() as c:
            return c.execute(
                "SELECT 1 FROM favorites WHERE user_id=? AND item_id=?",
                (uid, item_id)).fetchone() is not None

    def favorites_of(self, uid: int) -> List[Dict]:
        with self._con() as c:
            return [dict(r) for r in c.execute("""
                SELECT i.* FROM items i JOIN favorites f ON i.id = f.item_id
                WHERE f.user_id=? ORDER BY f.added_at DESC
            """, (uid,)).fetchall()]

    def add_category(self, name: str, type_: str, icon: str = "🎞️") -> bool:
        try:
            with self._con() as c:
                c.execute(
                    "INSERT INTO categories (name, type, icon) VALUES (?,?,?)",
                    (name, type_, icon),
                )
            return True
        except sqlite3.IntegrityError:
            return False

    def add_item(self, title: str, type_: str, cat_id: int, year=0, rating=0,
                 desc="", quality="", duration="", seasons=0, episodes=0, url="") -> int:
        with self._con() as c:
            cur = c.execute("""
                INSERT INTO items (title,type,cat_id,year,rating,desc,quality,duration,
                                   seasons,episodes,url)
                VALUES (?,?,?,?,?,?,?,?,?,?,?)
            """, (title, type_, cat_id, year, rating, desc, quality, duration,
                  seasons, episodes, url))
            return cur.lastrowid

    def stats(self) -> Dict:
        with self._con() as c:
            return {
                "users":  c.execute("SELECT COUNT(*) FROM users").fetchone()[0],
                "items":  c.execute("SELECT COUNT(*) FROM items").fetchone()[0],
                "cats":   c.execute("SELECT COUNT(*) FROM categories").fetchone()[0],
                "favs":   c.execute("SELECT COUNT(*) FROM favorites").fetchone()[0],
            }


# ============ بناء الأزرار ============
def main_menu_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🎬 الأفلام", callback_data="t:movie"),
         InlineKeyboardButton("📺 المسلسلات", callback_data="t:series")],
        [InlineKeyboardButton("📡 القنوات المباشرة", callback_data="t:live")],
        [InlineKeyboardButton("🔍 البحث", callback_data="act:search"),
         InlineKeyboardButton("🎲 عشوائي", callback_data="act:random")],
        [InlineKeyboardButton("❤️ المفضلة", callback_data="act:fav")],
        [InlineKeyboardButton("👑 لوحة الأدمن", callback_data="act:admin")],
    ])

def back_kb(target: str = "main") -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([[InlineKeyboardButton("🔙 رجوع", callback_data=target)]])

def categories_kb(type_: str, db: DB) -> InlineKeyboardMarkup:
    cats = db.categories(type_)
    rows = []
    for c in cats:
        rows.append([InlineKeyboardButton(
            f"{c['icon']} {esc(c['name'])}", callback_data=f"c:{type_}:{c['id']}:0"
        )])
    rows.append([InlineKeyboardButton("🔙 رجوع", callback_data="main")])
    return InlineKeyboardMarkup(rows)

def items_page_kb(items: List[Dict], type_: str, page: int) -> InlineKeyboardMarkup:
    per = ITEMS_PER_PAGE
    total_pages = max(1, (len(items) + per - 1) // per)
    page = max(0, min(page, total_pages - 1))
    chunk = items[page*per:(page+1)*per]
    rows = []
    for it in chunk:
        ic = icon_for(it["title"])
        title = it["title"]
        if len(title) > 32:
            title = title[:29] + "..."
        rows.append([InlineKeyboardButton(f"{ic} {esc(title)}", callback_data=f"v:{type_}:{it['id']}")])
    nav = []
    if page > 0:
        nav.append(InlineKeyboardButton("◀️ السابق", callback_data=f"pg:{type_}:{page-1}"))
    if total_pages > 1:
        nav.append(InlineKeyboardButton(f"📄 {page+1}/{total_pages}", callback_data="noop"))
    if page < total_pages - 1:
        nav.append(InlineKeyboardButton("التالي ▶️", callback_data=f"pg:{type_}:{page+1}"))
    if nav:
        rows.append(nav)
    rows.append([InlineKeyboardButton("🔙 رجوع", callback_data="main")])
    return InlineKeyboardMarkup(rows)


# ============ البوت الرئيسي ============
class CinemaBot:
    def __init__(self):
        self.db = DB()

    # ---------- عرض عنصر ----------
    async def _show_item(self, update_or_msg, ctx: ContextTypes.DEFAULT_TYPE,
                         item: Dict, edit: bool = False):
        text_lines = [
            f"{icon_for(item['title'])} <b>{esc(item['title'])}</b>",
        ]
        if item.get("year"):    text_lines.append(f"📅 السنة: {item['year']}")
        if item.get("rating"):  text_lines.append(f"⭐ التقييم: {item['rating']}/10")
        if item.get("quality"): text_lines.append(f"🎥 الجودة: {esc(item['quality'])}")
        if item.get("duration"):text_lines.append(f"⏱️ المدة: {esc(item['duration'])}")
        if item.get("seasons"): text_lines.append(f"📀 المواسم: {item['seasons']}")
        if item.get("episodes"):text_lines.append(f"🎞️ الحلقات: {item['episodes']}")
        if item.get("desc"):    text_lines.append(f"\n📝 {esc(item['desc'])}")
        if item.get("url") and item.get("type") == "live":
            text_lines.append(f"\n🔗 <a href=\"{esc(item['url'])}\">اضغط لمشاهدة البث</a>")
        text = "\n".join(text_lines)

        kb_rows: List[List[InlineKeyboardButton]] = []
        if item.get("url") and item.get("type") == "live":
            kb_rows.append([InlineKeyboardButton("📡 فتح البث", url=item["url"])])
        else:
            kb_rows.append([InlineKeyboardButton("📥 مشاهدة/تحميل", callback_data="noop")])
        is_fav = self.db.is_favorite(update_or_msg.from_user.id if update_or_msg.from_user else 0, item["id"])
        kb_rows.append([InlineKeyboardButton(
            "💔 إزالة من المفضلة" if is_fav else "❤️ إضافة للمفضلة",
            callback_data=f"fav:{item['id']}"
        )])
        kb_rows.append([InlineKeyboardButton("🔙 القائمة الرئيسية", callback_data="main")])
        kb = InlineKeyboardMarkup(kb_rows)

        if edit and hasattr(update_or_msg, "edit_message_text"):
            try:
                await update_or_msg.edit_message_text(text, parse_mode=ParseMode.HTML, reply_markup=kb,
                                                     disable_web_page_preview=True)
                return
            except Exception:
                pass
        # fallback: رساله جديده
        chat_id = update_or_msg.chat_id if hasattr(update_or_msg, "chat_id") else update_or_msg.chat.id
        await ctx.bot.send_message(chat_id, text, parse_mode=ParseMode.HTML, reply_markup=kb,
                                   disable_web_page_preview=True)

    # ---------- Commands ----------
    async def cmd_start(self, update: Update, ctx: ContextTypes.DEFAULT_TYPE):
        u = update.effective_user
        self.db.add_user(u.id, u.username, u.first_name)
        await update.message.reply_text(
            f"🎬 أهلاً {esc(u.first_name or 'بك')} في *{esc(BOT_NAME)}*!\n\nاختر من الأزرار:",
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=main_menu_kb(),
        )

    async def cmd_help(self, update: Update, ctx: ContextTypes.DEFAULT_TYPE):
        await update.message.reply_text(
            "🎬 <b>المساعدة</b>\n\n"
            "🎬 الأفلام • 📺 المسلسلات • 📡 القنوات\n"
            "🔍 البحث • 🎲 عشوائي • ❤️ مفضلة\n\n"
            "👑 <b>للأدمن:</b>\n"
            "/add أضف عنصر جديد\n"
            "/addcat أضف تصنيف جديد\n"
            "/stats الإحصائيات\n",
            parse_mode=ParseMode.HTML,
            reply_markup=back_kb("main"),
        )

    async def cmd_stats(self, update: Update, ctx: ContextTypes.DEFAULT_TYPE):
        s = self.db.stats()
        await update.message.reply_text(
            f"📊 <b>الإحصائيات</b>\n"
            f"👥 المستخدمون: {s['users']}\n"
            f"🎞️ العناصر: {s['items']}\n"
            f"📁 التصنيفات: {s['cats']}\n"
            f"❤️ المفضلات: {s['favs']}",
            parse_mode=ParseMode.HTML,
            reply_markup=back_kb("main"),
        )

    async def cmd_addcat(self, update: Update, ctx: ContextTypes.DEFAULT_TYPE):
        ctx.user_data["awaiting"] = "cat"
        await update.message.reply_text(
            "📁 أرسل التصنيف الجديد بالصيغة:\n"
            "<code>اسم | نوع | أيقونة</code>\n"
            "النوع: movie / series / live",
            parse_mode=ParseMode.HTML,
            reply_markup=back_kb("main"),
        )

    async def cmd_add(self, update: Update, ctx: ContextTypes.DEFAULT_TYPE):
        ctx.user_data["awaiting"] = "item"
        await update.message.reply_text(
            "➕ أضف عنصر جديد بالصيغة:\n\n"
            "<code>عنوان | نوع | اسم التصنيف | سنة | تقييم | وصف | جودة | مدة | مواسم | حلقات | رابط</code>\n\n"
            "النوع: movie / series / live\n"
            "اسم التصنيف يجب أن يكون موجودًا مسبقًا (استخدم /addcat).",
            parse_mode=ParseMode.HTML,
            reply_markup=back_kb("main"),
        )

    # ---------- Callback Query ----------
    async def on_callback(self, update: Update, ctx: ContextTypes.DEFAULT_TYPE):
        q = update.callback_query
        data = q.data or ""
        if data in ("", "noop"):
            await q.answer()
            return

        # main menu
        if data == "main":
            await q.edit_message_text(f"🎬 {esc(BOT_NAME)} — اختر:", reply_markup=main_menu_kb())
            await q.answer()
            return

        # type (movie/series/live) → categories list
        if data.startswith("t:"):
            type_ = data.split(":", 1)[1]
            cats = self.db.categories(type_)
            label = {"movie":"الأفلام","series":"المسلسلات","live":"القنوات المباشرة"}.get(type_, type_)
            if not cats:
                await q.edit_message_text(
                    f"📁 لا توجد تصنيفات من نوع {label} بعد.\nالأدمن يقدر يضيف بـ /addcat.",
                    reply_markup=back_kb("main"),
                )
                await q.answer()
                return
            await q.edit_message_text(
                f"📁 <b>اختر تصنيف {label}:</b>",
                parse_mode=ParseMode.HTML,
                reply_markup=categories_kb(type_, self.db),
            )
            await q.answer()
            return

        # category clicked → items in category (first page)
        if data.startswith("c:"):
            _, type_, cat_id, page = data.split(":")
            items = self.db.items_in_cat(pi(cat_id))
            ctx.user_data["current_items"] = items
            ctx.user_data["current_type"] = type_
            with self.db._con() as conn:
                row = conn.execute("SELECT name FROM categories WHERE id=?", (pi(cat_id),)).fetchone()
            name = row["name"] if row else "القسم"
            if not items:
                await q.edit_message_text(
                    f"📁 <b>{esc(name)}</b>\n\nلا توجد عناصر بعد.\nالأدمن يضيف بـ /add.",
                    parse_mode=ParseMode.HTML,
                    reply_markup=back_kb(f"t:{type_}"),
                )
                await q.answer()
                return
            await q.edit_message_text(
                f"📁 <b>{esc(name)}</b> ({len(items)} عنصر)",
                parse_mode=ParseMode.HTML,
                reply_markup=items_page_kb(items, type_, pi(page)),
            )
            await q.answer()
            return

        # pagination
        if data.startswith("pg:"):
            _, type_, page = data.split(":")
            items = ctx.user_data.get("current_items") or []
            if not items:
                # fallback
                cats = self.db.categories(type_)
                if not cats:
                    await q.edit_message_text("❌ لا توجد عناصر.", reply_markup=main_menu_kb())
                    await q.answer()
                    return
                items = self.db.items_in_cat(cats[0]["id"])
                ctx.user_data["current_items"] = items
                ctx.user_data["current_type"] = type_
            await q.edit_message_text(
                "📄 اختر عنصرًا:",
                reply_markup=items_page_kb(items, type_, pi(page)),
            )
            await q.answer()
            return

        # view item
        if data.startswith("v:"):
            _, type_, item_id = data.split(":")
            item = self.db.item(pi(item_id))
            if not item:
                await q.edit_message_text("❌ العنصر غير موجود.",
                                          reply_markup=main_menu_kb())
                await q.answer()
                return
            ctx.user_data["current_type"] = type_
            await self._show_item(q.message, ctx, item, edit=True)
            await q.answer()
            return

        # toggle favorite
        if data.startswith("fav:"):
            item_id = pi(data.split(":", 1)[1])
            uid = q.from_user.id
            if self.db.is_favorite(uid, item_id):
                self.db.remove_favorite(uid, item_id)
                await q.answer("🗑️ أُزيل من المفضلة")
            else:
                self.db.add_favorite(uid, item_id)
                await q.answer("❤️ أُضيف للمفضلة")
            # حدّث عرض العنصر
            item = self.db.item(item_id)
            if item:
                await self._show_item(q.message, ctx, item, edit=True)
            return

        # actions: search / random / fav / admin
        if data.startswith("act:"):
            act = data.split(":", 1)[1]
            if act == "search":
                ctx.user_data["awaiting"] = "search"
                await q.edit_message_text("🔍 اكتب كلمة البحث:", reply_markup=back_kb("main"))
                await q.answer()
                return
            if act == "random":
                items = self.db.all_items()
                if not items:
                    await q.edit_message_text("❌ لا يوجد محتوى.", reply_markup=main_menu_kb())
                    await q.answer()
                    return
                await self._show_item(q.message, ctx, random.choice(items), edit=True)
                await q.answer()
                return
            if act == "fav":
                uid = q.from_user.id
                favs = self.db.favorites_of(uid)
                if not favs:
                    await q.edit_message_text(
                        "❤️ المفضلة فارغة.\nافتح أي عنصر واضغط ❤️ لإضافته.",
                        reply_markup=back_kb("main"),
                    )
                    await q.answer()
                    return
                ctx.user_data["current_items"] = favs
                ctx.user_data["current_type"] = "fav"
                await q.edit_message_text(
                    f"❤️ المفضلة ({len(favs)} عنصر)",
                    reply_markup=items_page_kb(favs, "fav", 0),
                )
                await q.answer()
                return
            if act == "admin":
                await q.edit_message_text(
                    "👑 <b>لوحة الأدمن</b>\n\n"
                    "/add أضف عنصر\n"
                    "/addcat أضف تصنيف\n"
                    "/stats إحصائيات\n",
                    parse_mode=ParseMode.HTML,
                    reply_markup=back_kb("main"),
                )
                await q.answer()
                return

        await q.answer("❓ أمر غير معروف.")

    # ---------- Text Router ----------
    async def text_router(self, update: Update, ctx: ContextTypes.DEFAULT_TYPE):
        mode = ctx.user_data.get("awaiting")
        if not mode:
            # لا نستجيب لأي نص عادي لتفادي spam
            return

        text = (update.message.text or "").strip()
        ctx.user_data["awaiting"] = None

        if mode == "search":
            if not text:
                await update.message.reply_text("❌ كلمه فارغة.", reply_markup=back_kb("main"))
                return
            results = self.db.search(text)
            if not results:
                await update.message.reply_text(
                    f"❌ لا نتائج لـ: <b>{esc(text)}</b>",
                    parse_mode=ParseMode.HTML,
                    reply_markup=back_kb("main"),
                )
                return
            ctx.user_data["current_items"] = results
            ctx.user_data["current_type"] = "search"
            await update.message.reply_text(
                f"🔍 نتائج '<b>{esc(text)}</b>' ({len(results)})",
                parse_mode=ParseMode.HTML,
                reply_markup=items_page_kb(results, "search", 0),
            )
            return

        if mode == "cat":
            parts = [p.strip() for p in text.split("|")]
            if len(parts) < 2:
                return await update.message.reply_text(
                    "❌ استخدم: اسم | نوع | أيقونة (اختياري)",
                    reply_markup=back_kb("main"),
                )
            name, type_ = parts[0], parts[1]
            icon = parts[2] if len(parts) > 2 else icon_for(name)
            if type_ not in ("movie", "series", "live"):
                return await update.message.reply_text(
                    "❌ النوع لازم يكون: movie أو series أو live",
                    reply_markup=back_kb("main"),
                )
            ok = self.db.add_category(name, type_, icon)
            if ok:
                await update.message.reply_text(
                    f"✅ تمت إضافة التصنيف <b>{esc(name)}</b>.",
                    parse_mode=ParseMode.HTML,
                    reply_markup=back_kb("main"),
                )
            else:
                await update.message.reply_text(
                    f"⚠️ التصنيف <b>{esc(name)}</b> موجود فعلاً.",
                    parse_mode=ParseMode.HTML,
                    reply_markup=back_kb("main"),
                )
            return

        if mode == "item":
            parts = [p.strip() for p in text.split("|")]
            if len(parts) < 3:
                return await update.message.reply_text(
                    "❌ على الأقل: عنوان | نوع | تصنيف",
                    reply_markup=back_kb("main"),
                )
            title, type_, cname = parts[0], parts[1], parts[2]
            year      = pi(parts[3]) if len(parts) > 3 else 0
            rating    = float(parts[4]) if len(parts) > 4 and parts[4] else 0
            desc      = parts[5] if len(parts) > 5 else ""
            quality   = parts[6] if len(parts) > 6 else ""
            duration  = parts[7] if len(parts) > 7 else ""
            seasons   = pi(parts[8]) if len(parts) > 8 else 0
            episodes  = pi(parts[9]) if len(parts) > 9 else 0
            url       = parts[10] if len(parts) > 10 else ""
            if type_ not in ("movie", "series", "live"):
                return await update.message.reply_text(
                    "❌ النوع لازم يكون movie / series / live",
                    reply_markup=back_kb("main"),
                )
            with self.db._con() as c:
                row = c.execute(
                    "SELECT id FROM categories WHERE name=? AND type=?",
                    (cname, type_),
                ).fetchone()
            if not row:
                return await update.message.reply_text(
                    f"❌ التصنيف '{esc(cname)}' غير موجود من نوع '{esc(type_)}'.\nأضفه أولاً عبر /addcat.",
                    reply_markup=back_kb("main"),
                )
            new_id = self.db.add_item(title, type_, row["id"], year=year, rating=rating,
                                      desc=desc, quality=quality, duration=duration,
                                      seasons=seasons, episodes=episodes, url=url)
            await update.message.reply_text(
                f"✅ تمت إضافة <b>{esc(title)}</b> (ID={new_id}).",
                parse_mode=ParseMode.HTML,
                reply_markup=back_kb("main"),
            )
            return


# ============ نقطة التشغيل ============
def build_app() -> Application:
    if not BOT_TOKEN:
        logger.error("❌ BOT_TOKEN فاضي. ضعه في GitHub Secrets.")
        sys.exit(1)
    bot = CinemaBot()
    app = Application.builder().token(BOT_TOKEN).build()
    app.bot_data["cinema"] = bot
    app.add_handler(CommandHandler("start", bot.cmd_start))
    app.add_handler(CommandHandler("help", bot.cmd_help))
    app.add_handler(CommandHandler("stats", bot.cmd_stats))
    app.add_handler(CommandHandler("addcat", bot.cmd_addcat))
    app.add_handler(CommandHandler("add", bot.cmd_add))
    app.add_handler(CallbackQueryHandler(bot.on_callback))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, bot.text_router))
    return app


def main():
    logging.getLogger("httpx").setLevel(logging.WARNING)
    app = build_app()
    logger.info("🚀 بوت السينما يعمل الآن (Standalone، بدون خادم خارجي).")
    app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()
