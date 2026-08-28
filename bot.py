# -*- coding: utf-8 -*-
"""
🎬 بوت السينما — Xtream Codes API
يسحب كل القنوات المباشرة والأفلام والمسلسلات من سيرفر Xtream الحقيقي:
- تصنيفات + عناصر لكل نوع (live / movie / series)
- مواسم وحلقات المسلسلات مع عدد الحلقات (get_series_info)
- روابط مشاهدة m3u8 لكل المحتوى
- بحث شامل + عشوائي + مفضلة + لوحة أدمن
- تبديل تلقائي بين السيرفر الرئيسي والاحتياطي عند الفشل
- معالجة FloodWait وإعادة المحاولة

الأسرار (3 فقط) من البيئة / GitHub Secrets: BOT_TOKEN, API_ID, API_HASH
باقي الإعدادات من config.py
"""
import os
import sys
import json
import time
import html
import random
import sqlite3
import asyncio
import logging
from typing import Dict, List, Optional, Tuple

# ---------- إعدادات التليجرام (أسرار فقط) ----------
BOT_TOKEN = os.getenv("BOT_TOKEN", "").strip()
API_ID    = os.getenv("API_ID", "").strip()
API_HASH  = os.getenv("API_HASH", "").strip()

if not BOT_TOKEN:
    print("❌ BOT_TOKEN مفقود! ضعه في GitHub Secrets أو في البيئة.")
    sys.exit(1)

# ---------- إعدادات التشغيل من config.py ----------
try:
    import config as _cfg
except ImportError:
    print("⚠️ ملف config.py غير موجود — سيتم استخدام قيم افتراضية.")
    _cfg = None


def _c(name, default):
    return getattr(_cfg, name, default) if _cfg else default


ADMIN_IDS       = list(_c("ADMIN_IDS", []))          # [] = الكل أدمن
IPTV_USERNAME   = str(_c("IPTV_USERNAME", "")).strip()
IPTV_PASSWORD   = str(_c("IPTV_PASSWORD", "")).strip()
IPTV_BASE_URL   = str(_c("IPTV_BASE_URL", "")).strip().rstrip("/")
IPTV_BACKUP_URLS = [u.strip().rstrip("/") for u in _c("IPTV_BACKUP_URLS", []) if str(u).strip()]
ITEMS_PER_PAGE  = int(_c("ITEMS_PER_PAGE", 10))
CACHE_DURATION  = int(_c("CACHE_DURATION", 600))     # ثانية
REQUEST_TIMEOUT = int(_c("REQUEST_TIMEOUT", 30))
MAX_RETRIES     = int(_c("MAX_RETRIES", 3))
BOT_NAME        = str(_c("BOT_NAME", "🎬 سينما بوت"))
DB_PATH         = str(_c("DB_PATH", "cinema_bot.db"))

BASES = [b for b in [IPTV_BASE_URL] + IPTV_BACKUP_URLS if b]
if not IPTV_USERNAME or not IPTV_PASSWORD or not BASES:
    print("❌ بيانات IPTV ناقصة في config.py (IPTV_USERNAME / IPTV_PASSWORD / IPTV_BASE_URL)")
    sys.exit(1)

logging.basicConfig(
    format="%(asctime)s [%(levelname)s] %(message)s",
    level=logging.INFO,
)
log = logging.getLogger("cinema-bot")

try:
    import httpx
    from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
    from telegram.constants import ParseMode
    from telegram.ext import (
        Application, CommandHandler, CallbackQueryHandler,
        MessageHandler, ContextTypes, filters,
    )
    from telegram.error import RetryAfter, TimedOut, NetworkError
except ImportError:
    print("❌ ثبّت المتطلبات أولاً: pip install -r requirements.txt")
    sys.exit(1)


def esc(t) -> str:
    return html.escape(str(t or ""))


def is_admin(user_id: int) -> bool:
    return (not ADMIN_IDS) or (user_id in ADMIN_IDS)


# ============ عميل Xtream Codes API ============
class Xtream:
    """عميل async لسيرفر Xtream مع تبديل تلقائي بين السيرفرات."""

    def __init__(self, bases: List[str], user: str, password: str):
        self.bases = bases
        self.user = user
        self.pw = password
        self.base_idx = 0
        self._client: Optional[httpx.AsyncClient] = None

    @property
    def base(self) -> str:
        return self.bases[self.base_idx]

    async def client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                timeout=httpx.Timeout(REQUEST_TIMEOUT, read=60),
                follow_redirects=True,
                headers={"User-Agent": "Mozilla/5.0 (CinemaBot)"},
            )
        return self._client

    def _switch(self):
        if len(self.bases) > 1:
            old = self.base
            self.base_idx = (self.base_idx + 1) % len(self.bases)
            log.warning("🔁 تبديل السيرفر: %s → %s", old, self.base)

    async def api(self, action: str = "", **params) -> Optional[object]:
        """نداء player_api.php مع retries وتبديل سيرفر عند فشل الاتصال."""
        q = {"username": self.user, "password": self.pw}
        if action:
            q["action"] = action
        q.update({k: v for k, v in params.items() if v is not None})
        last_err = None
        for attempt in range(1, MAX_RETRIES + 1):
            try:
                c = await self.client()
                r = await c.get(f"{self.base}/player_api.php", params=q)
                if r.status_code == 200:
                    try:
                        return r.json()
                    except Exception:
                        return None
                last_err = f"HTTP {r.status_code}"
            except Exception as e:
                last_err = f"{type(e).__name__}: {e}"
                log.warning("⚠️ محاولة %d/%d فشلت (%s) — %s", attempt, MAX_RETRIES, self.base, last_err)
                self._switch()
                await asyncio.sleep(1.5 * attempt)
        log.error("❌ فشل نداء API (%s) بعد %d محاولات: %s", action or "login", MAX_RETRIES, last_err)
        return None

    # ---- روابط المشاهدة (m3u8 / mp4) ----
    def live_url(self, stream_id) -> str:
        return f"{self.base}/live/{self.user}/{self.pw}/{stream_id}.m3u8"

    def movie_url(self, stream_id, ext: str = "mp4") -> str:
        return f"{self.base}/movie/{self.user}/{self.pw}/{stream_id}.{ext or 'mp4'}"

    def movie_m3u8(self, stream_id) -> str:
        return f"{self.base}/movie/{self.user}/{self.pw}/{stream_id}.m3u8"

    def episode_url(self, episode_id, ext: str = "mp4") -> str:
        return f"{self.base}/series/{self.user}/{self.pw}/{episode_id}.{ext or 'mp4'}"

    def episode_m3u8(self, episode_id) -> str:
        return f"{self.base}/series/{self.user}/{self.pw}/{episode_id}.m3u8"

    async def close(self):
        if self._client and not self._client.is_closed:
            await self._client.aclose()


# ============ قاعدة البيانات (كاش + مفضلة + مستخدمون) ============
class DB:
    def __init__(self, path: str = DB_PATH):
        self.path = path
        self._init()

    def _con(self):
        c = sqlite3.connect(self.path)
        c.row_factory = sqlite3.Row
        return c

    def _init(self):
        with self._con() as c:
            c.executescript("""
                CREATE TABLE IF NOT EXISTS users (
                    telegram_id INTEGER PRIMARY KEY,
                    username TEXT, first_name TEXT,
                    joined_at TEXT DEFAULT CURRENT_TIMESTAMP
                );
                CREATE TABLE IF NOT EXISTS favorites (
                    user_id INTEGER NOT NULL,
                    item_type TEXT NOT NULL,
                    item_id TEXT NOT NULL,
                    title TEXT NOT NULL,
                    added_at TEXT DEFAULT CURRENT_TIMESTAMP,
                    PRIMARY KEY (user_id, item_type, item_id)
                );
                CREATE TABLE IF NOT EXISTS cache (
                    key TEXT PRIMARY KEY,
                    data TEXT NOT NULL,
                    ts INTEGER NOT NULL
                );
            """)

    # ---- كاش ----
    def cache_get(self, key: str):
        with self._con() as c:
            row = c.execute("SELECT data, ts FROM cache WHERE key=?", (key,)).fetchone()
            if row and (time.time() - row["ts"]) < CACHE_DURATION:
                try:
                    return json.loads(row["data"])
                except Exception:
                    return None
            return None

    def cache_set(self, key: str, data):
        with self._con() as c:
            c.execute(
                "INSERT OR REPLACE INTO cache (key, data, ts) VALUES (?,?,?)",
                (key, json.dumps(data, ensure_ascii=False), int(time.time())),
            )

    # ---- مستخدمون ----
    def add_user(self, uid: int, username: str, first_name: str):
        with self._con() as c:
            c.execute(
                "INSERT OR IGNORE INTO users (telegram_id, username, first_name) VALUES (?,?,?)",
                (uid, username or "", first_name or ""),
            )

    def users_count(self) -> int:
        with self._con() as c:
            return c.execute("SELECT COUNT(*) FROM users").fetchone()[0]

    def all_user_ids(self) -> List[int]:
        with self._con() as c:
            return [r[0] for r in c.execute("SELECT telegram_id FROM users").fetchall()]

    # ---- مفضلة ----
    def toggle_fav(self, uid: int, item_type: str, item_id: str, title: str) -> bool:
        """يرجع True لو اتضاف، False لو اتشال."""
        with self._con() as c:
            row = c.execute(
                "SELECT 1 FROM favorites WHERE user_id=? AND item_type=? AND item_id=?",
                (uid, item_type, str(item_id)),
            ).fetchone()
            if row:
                c.execute(
                    "DELETE FROM favorites WHERE user_id=? AND item_type=? AND item_id=?",
                    (uid, item_type, str(item_id)),
                )
                return False
            c.execute(
                "INSERT INTO favorites (user_id, item_type, item_id, title) VALUES (?,?,?,?)",
                (uid, item_type, str(item_id), title),
            )
            return True

    def is_fav(self, uid: int, item_type: str, item_id: str) -> bool:
        with self._con() as c:
            return c.execute(
                "SELECT 1 FROM favorites WHERE user_id=? AND item_type=? AND item_id=?",
                (uid, item_type, str(item_id)),
            ).fetchone() is not None

    def get_favs(self, uid: int) -> List[Dict]:
        with self._con() as c:
            return [dict(r) for r in c.execute(
                "SELECT item_type, item_id, title FROM favorites WHERE user_id=? ORDER BY added_at DESC",
                (uid,),
            ).fetchall()]


# ============ طبقة البيانات (API + كاش) ============
class Store:
    def __init__(self, xt: Xtream, db: DB):
        self.xt = xt
        self.db = db

    async def _cached(self, key: str, action: str, **params):
        hit = self.db.cache_get(key)
        if hit is not None:
            return hit
        data = await self.xt.api(action, **params)
        if data is None:
            data = []
        self.db.cache_set(key, data)
        return data

    async def categories(self, type_: str) -> List[Dict]:
        action = {"live": "get_live_categories", "movie": "get_vod_categories", "series": "get_series_categories"}[type_]
        data = await self._cached(f"cats:{type_}", action)
        return data if isinstance(data, list) else []

    async def streams(self, type_: str, cat_id=None) -> List[Dict]:
        action = {"live": "get_live_streams", "movie": "get_vod_streams", "series": "get_series"}[type_]
        key = f"streams:{type_}:{cat_id or 'all'}"
        params = {} if cat_id in (None, "", "all") else {"category_id": cat_id}
        data = await self._cached(key, action, **params)
        return data if isinstance(data, list) else []

    async def series_info(self, series_id) -> Dict:
        data = await self._cached(f"sinfo:{series_id}", "get_series_info", series_id=series_id)
        return data if isinstance(data, dict) else {}

    async def vod_info(self, vod_id) -> Dict:
        data = await self._cached(f"vinfo:{vod_id}", "get_vod_info", vod_id=vod_id)
        return data if isinstance(data, dict) else {}

    async def all_items(self, type_: str) -> List[Dict]:
        return await self.streams(type_, None)

    async def search(self, query: str) -> List[Tuple[str, Dict]]:
        q = (query or "").strip().lower()
        if not q:
            return []
        results: List[Tuple[str, Dict]] = []
        for type_ in ("movie", "series", "live"):
            try:
                items = await self.all_items(type_)
            except Exception:
                items = []
            id_key = "series_id" if type_ == "series" else "stream_id"
            for it in items:
                name = str(it.get("name") or it.get("title") or "")
                if q in name.lower() and it.get(id_key) is not None:
                    results.append((type_, it))
                if len(results) >= 60:
                    return results
        return results


# ============ لوحات المفاتيح ============
TYPE_LABEL = {"live": "📡 القنوات المباشرة", "movie": "🎬 الأفلام", "series": "📺 المسلسلات"}
ITEM_ICON = {"live": "📡", "movie": "🎞️", "series": "📺"}


def main_menu_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🎬 الأفلام", callback_data="t:movie"),
         InlineKeyboardButton("📺 المسلسلات", callback_data="t:series")],
        [InlineKeyboardButton("📡 القنوات المباشرة", callback_data="t:live")],
        [InlineKeyboardButton("🔍 بحث", callback_data="act:search"),
         InlineKeyboardButton("🎲 عشوائي", callback_data="act:random")],
        [InlineKeyboardButton("❤️ المفضلة", callback_data="act:fav"),
         InlineKeyboardButton("👑 لوحة الأدمن", callback_data="act:admin")],
    ])


def back_main_row() -> List[InlineKeyboardButton]:
    return [InlineKeyboardButton("🔙 القائمة الرئيسية", callback_data="main")]


def categories_kb(cats: List[Dict], type_: str) -> InlineKeyboardMarkup:
    rows = []
    for cat in cats:
        cid = cat.get("category_id")
        name = cat.get("category_name") or "بدون اسم"
        cnt = cat.get("stream_count")
        label = f"{name} ({cnt})" if cnt else name
        rows.append([InlineKeyboardButton(label[:60], callback_data=f"c:{type_}:{cid}:0")])
    rows.append(back_main_row())
    return InlineKeyboardMarkup(rows)


def _page_slice(items: List, page: int) -> Tuple[List, int, int]:
    total = len(items)
    pages = max(1, (total + ITEMS_PER_PAGE - 1) // ITEMS_PER_PAGE)
    page = max(0, min(page, pages - 1))
    return items[page * ITEMS_PER_PAGE:(page + 1) * ITEMS_PER_PAGE], page, pages


def items_kb(items: List[Dict], type_: str, cat_id: str, page: int) -> InlineKeyboardMarkup:
    slice_, page, pages = _page_slice(items, page)
    id_key = "series_id" if type_ == "series" else "stream_id"
    rows = []
    for it in slice_:
        iid = it.get(id_key)
        name = str(it.get("name") or it.get("title") or "بدون عنوان")
        rows.append([InlineKeyboardButton(f"{ITEM_ICON[type_]} {name[:55]}", callback_data=f"i:{type_}:{iid}:{cat_id}:{page}")])
    nav = []
    if page > 0:
        nav.append(InlineKeyboardButton("◀️ السابق", callback_data=f"c:{type_}:{cat_id}:{page - 1}"))
    if pages > 1:
        nav.append(InlineKeyboardButton(f"{page + 1}/{pages}", callback_data="noop"))
    if page < pages - 1:
        nav.append(InlineKeyboardButton("التالي ▶️", callback_data=f"c:{type_}:{cat_id}:{page + 1}"))
    if nav:
        rows.append(nav)
    rows.append([InlineKeyboardButton(f"🔙 {TYPE_LABEL[type_]}", callback_data=f"t:{type_}")])
    rows.append(back_main_row())
    return InlineKeyboardMarkup(rows)


def item_detail_kb(uid: int, db: DB, type_: str, item: Dict, cat_id: str, page: int, xt: Xtream) -> InlineKeyboardMarkup:
    rows = []
    id_key = "series_id" if type_ == "series" else "stream_id"
    iid = item.get(id_key)
    if type_ == "live":
        rows.append([InlineKeyboardButton("▶️ مشاهدة البث (m3u8)", url=xt.live_url(iid))])
    elif type_ == "movie":
        ext = item.get("container_extension") or "mp4"
        rows.append([InlineKeyboardButton("▶️ مشاهدة الفيلم (m3u8)", url=xt.movie_m3u8(iid))])
        rows.append([InlineKeyboardButton(f"⬇️ تحميل مباشر ({ext})", url=xt.movie_url(iid, ext))])
    elif type_ == "series":
        rows.append([InlineKeyboardButton("📀 عرض المواسم والحلقات", callback_data=f"s:{iid}:0")])
    if item.get("stream_icon") or item.get("cover"):
        rows.append([InlineKeyboardButton("🖼 البوستر", url=item.get("stream_icon") or item.get("cover"))])
    fav = db.is_fav(uid, type_, str(iid))
    rows.append([InlineKeyboardButton(
        "💔 إزالة من المفضلة" if fav else "❤️ إضافة للمفضلة",
        callback_data=f"f:{type_}:{iid}:{cat_id}:{page}",
    )])
    rows.append([InlineKeyboardButton("🔙 رجوع للقائمة", callback_data=f"c:{type_}:{cat_id}:{page}")])
    rows.append(back_main_row())
    return InlineKeyboardMarkup(rows)


def seasons_kb(info: Dict, series_id) -> InlineKeyboardMarkup:
    rows = []
    seasons = info.get("seasons") or []
    episodes_map = info.get("episodes") or {}
    for s in seasons:
        snum = s.get("season_number")
        cnt = s.get("episode_count")
        if cnt is None:
            cnt = len(episodes_map.get(str(snum), []))
        name = s.get("name") or f"الموسم {snum}"
        rows.append([InlineKeyboardButton(f"📀 {name} — {cnt} حلقة", callback_data=f"e:{series_id}:{snum}:0")])
    rows.append(back_main_row())
    return InlineKeyboardMarkup(rows)


def episodes_kb(info: Dict, series_id, season: int, page: int) -> InlineKeyboardMarkup:
    eps = (info.get("episodes") or {}).get(str(season), [])
    slice_, page, pages = _page_slice(eps, page)
    rows = []
    for ep in slice_:
        num = ep.get("episode_num", "?")
        title = str(ep.get("title") or f"الحلقة {num}")
        eid = ep.get("id")
        rows.append([InlineKeyboardButton(f"🎞️ ح{num}: {title[:48]}", callback_data=f"p:{eid}:{series_id}:{season}:{page}")])
    nav = []
    if page > 0:
        nav.append(InlineKeyboardButton("◀️ السابق", callback_data=f"e:{series_id}:{season}:{page - 1}"))
    if pages > 1:
        nav.append(InlineKeyboardButton(f"{page + 1}/{pages}", callback_data="noop"))
    if page < pages - 1:
        nav.append(InlineKeyboardButton("التالي ▶️", callback_data=f"e:{series_id}:{season}:{page + 1}"))
    if nav:
        rows.append(nav)
    rows.append([InlineKeyboardButton("🔙 المواسم", callback_data=f"s:{series_id}:0")])
    rows.append(back_main_row())
    return InlineKeyboardMarkup(rows)


def episode_play_kb(ep: Dict, series_id, season: int, page: int, xt: Xtream) -> InlineKeyboardMarkup:
    eid = ep.get("id")
    ext = ep.get("container_extension") or "mp4"
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("▶️ مشاهدة الحلقة (m3u8)", url=xt.episode_m3u8(eid))],
        [InlineKeyboardButton(f"⬇️ تحميل مباشر ({ext})", url=xt.episode_url(eid, ext))],
        [InlineKeyboardButton("🔙 الحلقات", callback_data=f"e:{series_id}:{season}:{page}")],
        back_main_row(),
    ])


def admin_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📊 الإحصائيات", callback_data="adm:stats")],
        [InlineKeyboardButton("🔄 تحديث الكاش", callback_data="adm:flush")],
        [InlineKeyboardButton("📢 رسالة جماعية", callback_data="adm:cast")],
        back_main_row(),
    ])


# ============ البوت ============
class CinemaBot:
    def __init__(self):
        self.db = DB()
        self.xt = Xtream(BASES, IPTV_USERNAME, IPTV_PASSWORD)
        self.store = Store(self.xt, self.db)

    # ---------- أدوات إرسال آمنة ----------
    async def _safe_edit(self, q, text: str, kb=None):
        try:
            await q.edit_message_text(text, parse_mode=ParseMode.HTML,
                                      reply_markup=kb, disable_web_page_preview=True)
        except Exception as e:
            if "not modified" not in str(e).lower():
                try:
                    await q.message.reply_text(text, parse_mode=ParseMode.HTML,
                                               reply_markup=kb, disable_web_page_preview=True)
                except Exception:
                    pass

    # ---------- /start ----------
    async def cmd_start(self, update: Update, ctx: ContextTypes.DEFAULT_TYPE):
        u = update.effective_user
        self.db.add_user(u.id, u.username, u.first_name)
        await update.message.reply_text(
            f"🎬 أهلاً <b>{esc(u.first_name or 'بك')}</b> في <b>{esc(BOT_NAME)}</b>!\n\n"
            "كل المحتوى مباشر من السيرفر — اختر من الأزرار:",
            parse_mode=ParseMode.HTML,
            reply_markup=main_menu_kb(),
        )

    async def cmd_help(self, update: Update, ctx: ContextTypes.DEFAULT_TYPE):
        await update.message.reply_text(
            "📖 <b>طريقة الاستخدام:</b>\n"
            "• 🎬 الأفلام / 📺 المسلسلات / 📡 القنوات — تصفح بالتصنيفات\n"
            "• 🔍 بحث — ابعت اسم الفيلم أو المسلسل أو القناة\n"
            "• 🎲 عشوائي — اقتراح عشوائي\n"
            "• ❤️ المفضلة — قائمتك الخاصة\n\n"
            "أوامر الأدمن: /stats /broadcast",
            parse_mode=ParseMode.HTML,
        )

    async def cmd_stats(self, update: Update, ctx: ContextTypes.DEFAULT_TYPE):
        if not is_admin(update.effective_user.id):
            return
        await self._send_stats(update.message)

    async def _send_stats(self, msg):
        lines = ["📊 <b>إحصائيات البوت</b>\n"]
        lines.append(f"👥 المستخدمون: {self.db.users_count()}")
        for t in ("live", "movie", "series"):
            cats = await self.store.categories(t)
            lines.append(f"{TYPE_LABEL[t]}: {len(cats)} تصنيف")
        lines.append(f"\n🌐 السيرفر الحالي: <code>{esc(self.xt.base)}</code>")
        await msg.reply_text("\n".join(lines), parse_mode=ParseMode.HTML)

    async def cmd_broadcast(self, update: Update, ctx: ContextTypes.DEFAULT_TYPE):
        if not is_admin(update.effective_user.id):
            return
        text = " ".join(ctx.args) if ctx.args else ""
        if not text:
            await update.message.reply_text("استخدم: /broadcast نص الرسالة")
            return
        ok = fail = 0
        for uid in self.db.all_user_ids():
            try:
                await ctx.bot.send_message(uid, f"📢 {esc(text)}", parse_mode=ParseMode.HTML)
                ok += 1
            except RetryAfter as e:
                await asyncio.sleep(e.retry_after + 1)
            except Exception:
                fail += 1
            await asyncio.sleep(0.05)
        await update.message.reply_text(f"✅ تم الإرسال: {ok} | ❌ فشل: {fail}")

    # ---------- عرض الأقسام والعناصر ----------
    async def _show_categories(self, q, type_: str):
        await self._safe_edit(q, f"⏳ جاري تحميل {TYPE_LABEL[type_]}...")
        cats = await self.store.categories(type_)
        if not cats:
            await self._safe_edit(q, f"❌ لا توجد تصنيفات في {TYPE_LABEL[type_]} حالياً.\n"
                                     "جرّب لاحقاً أو حدّث الكاش من لوحة الأدمن.",
                                  InlineKeyboardMarkup([back_main_row()]))
            return
        await self._safe_edit(q, f"{TYPE_LABEL[type_]} — اختر التصنيف:", categories_kb(cats, type_))

    async def _show_items(self, q, type_: str, cat_id: str, page: int):
        await self._safe_edit(q, "⏳ جاري تحميل العناصر...")
        items = await self.store.streams(type_, cat_id)
        if not items:
            await self._safe_edit(q, "❌ لا توجد عناصر في هذا التصنيف.",
                                  InlineKeyboardMarkup([[InlineKeyboardButton("🔙 رجوع", callback_data=f"t:{type_}")], back_main_row()]))
            return
        _, page, pages = _page_slice(items, page)
        await self._safe_edit(
            q,
            f"{TYPE_LABEL[type_]} — {len(items)} عنصر (صفحة {page + 1}/{pages}):",
            items_kb(items, type_, cat_id, page),
        )

    async def _find_item(self, type_: str, iid: str) -> Optional[Dict]:
        id_key = "series_id" if type_ == "series" else "stream_id"
        items = await self.store.streams(type_, None)
        for it in items:
            if str(it.get(id_key)) == str(iid):
                return it
        return None

    async def _show_item(self, q, uid: int, type_: str, iid: str, cat_id: str, page: int):
        item = await self._find_item(type_, iid)
        if not item:
            await self._safe_edit(q, "❌ العنصر غير موجود.", InlineKeyboardMarkup([back_main_row()]))
            return
        name = str(item.get("name") or item.get("title") or "بدون عنوان")
        lines = [f"{ITEM_ICON[type_]} <b>{esc(name)}</b>"]
        rating = item.get("rating") or item.get("rating_5based")
        if rating:
            lines.append(f"⭐ التقييم: {rating}")
        if type_ == "series":
            info = await self.store.series_info(iid)
            seasons = info.get("seasons") or []
            eps_map = info.get("episodes") or {}
            total_eps = sum(len(v) for v in eps_map.values()) if eps_map else sum(
                s.get("episode_count", 0) for s in seasons)
            if seasons:
                lines.append(f"📀 المواسم: {len(seasons)}")
            if total_eps:
                lines.append(f"🎞️ الحلقات: {total_eps}")
            plot = (info.get("info") or {}).get("plot") or item.get("plot")
            if plot:
                lines.append(f"\n📝 {esc(str(plot)[:300])}")
        elif type_ == "movie":
            ext = item.get("container_extension")
            if ext:
                lines.append(f"🎥 الصيغة: {ext}")
        await self._safe_edit(q, "\n".join(lines),
                              item_detail_kb(uid, self.db, type_, item, cat_id, page, self.xt))

    async def _show_seasons(self, q, series_id: str):
        await self._safe_edit(q, "⏳ جاري تحميل المواسم...")
        info = await self.store.series_info(series_id)
        seasons = info.get("seasons") or []
        if not seasons:
            await self._safe_edit(q, "❌ لا توجد مواسم لهذا المسلسل.",
                                  InlineKeyboardMarkup([back_main_row()]))
            return
        name = esc((info.get("info") or {}).get("name") or "المسلسل")
        await self._safe_edit(q, f"📺 <b>{name}</b>\nاختر الموسم:", seasons_kb(info, series_id))

    async def _show_episodes(self, q, series_id: str, season: int, page: int):
        await self._safe_edit(q, "⏳ جاري تحميل الحلقات...")
        info = await self.store.series_info(series_id)
        eps = (info.get("episodes") or {}).get(str(season), [])
        if not eps:
            await self._safe_edit(q, "❌ لا توجد حلقات في هذا الموسم.",
                                  InlineKeyboardMarkup([[InlineKeyboardButton("🔙 المواسم", callback_data=f"s:{series_id}:0")], back_main_row()]))
            return
        _, page, pages = _page_slice(eps, page)
        await self._safe_edit(
            q,
            f"📀 الموسم {season} — {len(eps)} حلقة (صفحة {page + 1}/{pages}):",
            episodes_kb(info, series_id, season, page),
        )

    async def _play_episode(self, q, episode_id: str, series_id: str, season: int, page: int):
        info = await self.store.series_info(series_id)
        eps = (info.get("episodes") or {}).get(str(season), [])
        ep = next((e for e in eps if str(e.get("id")) == str(episode_id)), None)
        if not ep:
            await self._safe_edit(q, "❌ الحلقة غير موجودة.",
                                  InlineKeyboardMarkup([[InlineKeyboardButton("🔙 الحلقات", callback_data=f"e:{series_id}:{season}:{page}")]]))
            return
        title = esc(str(ep.get("title") or f"الحلقة {ep.get('episode_num', '?')}"))
        dur = ep.get("info", {}).get("duration") if isinstance(ep.get("info"), dict) else None
        lines = [f"🎞️ <b>{title}</b>"]
        if dur:
            lines.append(f"⏱️ المدة: {esc(dur)}")
        await self._safe_edit(q, "\n".join(lines), episode_play_kb(ep, series_id, season, page, self.xt))

    async def _show_favs(self, q, uid: int):
        favs = self.db.get_favs(uid)
        if not favs:
            await self._safe_edit(q, "❤️ مفضلتك فارغة حالياً.\nأضف عناصر من زر ❤️ في صفحة أي محتوى.",
                                  InlineKeyboardMarkup([back_main_row()]))
            return
        rows = []
        for f in favs[:30]:
            t, iid, title = f["item_type"], f["item_id"], f["title"]
            rows.append([InlineKeyboardButton(f"{ITEM_ICON.get(t, '🎞️')} {title[:50]}",
                                              callback_data=f"i:{t}:{iid}:fav:0")])
        rows.append(back_main_row())
        await self._safe_edit(q, f"❤️ <b>مفضلتك</b> ({len(favs)} عنصر):", InlineKeyboardMarkup(rows))

    async def _random_pick(self, q):
        await self._safe_edit(q, "🎲 جاري اختيار عشوائي...")
        type_ = random.choice(["movie", "series", "live"])
        items = await self.store.streams(type_, None)
        if not items:
            await self._safe_edit(q, "❌ لا يوجد محتوى حالياً.", InlineKeyboardMarkup([back_main_row()]))
            return
        it = random.choice(items)
        id_key = "series_id" if type_ == "series" else "stream_id"
        await self._show_item(q, q.from_user.id, type_, str(it.get(id_key)), "all", 0)

    async def _show_admin(self, q):
        if not is_admin(q.from_user.id):
            await self._safe_edit(q, "🚫 هذه اللوحة للأدمن فقط.", InlineKeyboardMarkup([back_main_row()]))
            return
        await self._safe_edit(q, "👑 <b>لوحة الأدمن</b>\nاختر إجراء:", admin_kb())

    # ---------- راوتر الأزرار ----------
    async def on_callback(self, update: Update, ctx: ContextTypes.DEFAULT_TYPE):
        q = update.callback_query
        data = q.data or ""
        uid = q.from_user.id
        try:
            await q.answer()
        except Exception:
            pass

        try:
            if data in ("", "noop"):
                return
            if data == "main":
                await self._safe_edit(q, f"🎬 <b>{esc(BOT_NAME)}</b> — القائمة الرئيسية:", main_menu_kb())
            elif data.startswith("t:"):
                await self._show_categories(q, data.split(":", 1)[1])
            elif data.startswith("c:"):
                _, t, cid, page = data.split(":")
                await self._show_items(q, t, cid, int(page))
            elif data.startswith("i:"):
                _, t, iid, cid, page = data.split(":")
                await self._show_item(q, uid, t, iid, cid, int(page))
            elif data.startswith("f:"):
                _, t, iid, cid, page = data.split(":")
                item = await self._find_item(t, iid)
                title = str((item or {}).get("name") or (item or {}).get("title") or iid)
                added = self.db.toggle_fav(uid, t, iid, title)
                try:
                    await q.answer("❤️ أُضيف للمفضلة" if added else "💔 أُزيل من المفضلة", show_alert=False)
                except Exception:
                    pass
                if item:
                    await self._show_item(q, uid, t, iid, cid, int(page))
            elif data.startswith("s:"):
                await self._show_seasons(q, data.split(":")[1])
            elif data.startswith("e:"):
                _, sid, season, page = data.split(":")
                await self._show_episodes(q, sid, int(season), int(page))
            elif data.startswith("p:"):
                _, eid, sid, season, page = data.split(":")
                await self._play_episode(q, eid, sid, int(season), int(page))
            elif data == "act:search":
                ctx.user_data["awaiting_search"] = True
                await self._safe_edit(q, "🔍 ابعت الآن اسم الفيلم أو المسلسل أو القناة:",
                                      InlineKeyboardMarkup([back_main_row()]))
            elif data == "act:random":
                await self._random_pick(q)
            elif data == "act:fav":
                await self._show_favs(q, uid)
            elif data == "act:admin":
                await self._show_admin(q)
            elif data == "adm:stats":
                if is_admin(uid):
                    lines = ["📊 <b>إحصائيات البوت</b>\n", f"👥 المستخدمون: {self.db.users_count()}"]
                    for t in ("live", "movie", "series"):
                        cats = await self.store.categories(t)
                        lines.append(f"{TYPE_LABEL[t]}: {len(cats)} تصنيف")
                    lines.append(f"\n🌐 السيرفر: <code>{esc(self.xt.base)}</code>")
                    await self._safe_edit(q, "\n".join(lines), admin_kb())
            elif data == "adm:flush":
                if is_admin(uid):
                    with self.db._con() as c:
                        c.execute("DELETE FROM cache")
                    await self._safe_edit(q, "🔄 تم مسح الكاش — سيتم تحميل البيانات من جديد.", admin_kb())
            elif data == "adm:cast":
                if is_admin(uid):
                    await self._safe_edit(q, "📢 أرسل الرسالة بالأمر:\n/broadcast نص الرسالة", admin_kb())
            else:
                await self._safe_edit(q, "❓ أمر غير معروف.", main_menu_kb())
        except RetryAfter as e:
            await asyncio.sleep(e.retry_after + 1)
        except (TimedOut, NetworkError) as e:
            log.warning("مشكلة شبكة: %s", e)
        except Exception as e:
            log.exception("خطأ في معالجة الزر %s: %s", data, e)
            try:
                await self._safe_edit(q, "❌ حدث خطأ مؤقت — حاول مرة أخرى.", main_menu_kb())
            except Exception:
                pass

    # ---------- البحث النصي ----------
    async def text_router(self, update: Update, ctx: ContextTypes.DEFAULT_TYPE):
        if not update.message or not update.message.text:
            return
        text = update.message.text.strip()
        if text.startswith("/"):
            return
        if not ctx.user_data.get("awaiting_search"):
            ctx.user_data["awaiting_search"] = True  # أي نص = بحث مباشر
        ctx.user_data["awaiting_search"] = False

        msg = await update.message.reply_text(f"🔍 جاري البحث عن: <b>{esc(text)}</b>...",
                                              parse_mode=ParseMode.HTML)
        results = await self.store.search(text)
        if not results:
            await msg.edit_text(f"❌ لا توجد نتائج لـ «{esc(text)}».",
                                parse_mode=ParseMode.HTML,
                                reply_markup=InlineKeyboardMarkup([back_main_row()]))
            return
        rows = []
        for t, it in results[:25]:
            id_key = "series_id" if t == "series" else "stream_id"
            iid = it.get(id_key)
            name = str(it.get("name") or it.get("title") or "بدون عنوان")
            rows.append([InlineKeyboardButton(f"{ITEM_ICON[t]} {name[:52]}",
                                              callback_data=f"i:{t}:{iid}:all:0")])
        rows.append(back_main_row())
        await msg.edit_text(f"🔍 <b>نتائج البحث</b> ({len(results)} نتيجة):",
                            parse_mode=ParseMode.HTML,
                            reply_markup=InlineKeyboardMarkup(rows))

    # ---------- تشغيل ----------
    def run(self):
        app = Application.builder().token(BOT_TOKEN).build()
        app.add_handler(CommandHandler("start", self.cmd_start))
        app.add_handler(CommandHandler("help", self.cmd_help))
        app.add_handler(CommandHandler("stats", self.cmd_stats))
        app.add_handler(CommandHandler("broadcast", self.cmd_broadcast))
        app.add_handler(CallbackQueryHandler(self.on_callback))
        app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, self.text_router))
        log.info("🚀 %s يعمل الآن — السيرفر: %s", BOT_NAME, self.xt.base)
        app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    CinemaBot().run()
