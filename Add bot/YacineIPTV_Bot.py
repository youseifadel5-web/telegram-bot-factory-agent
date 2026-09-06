"""
Yacine IPTV Bot
بوت قنوات IPTV مبني على واجهات API المصرح بها.

التثبيت في Pydroid:
    pip install -U aiogram aiohttp

اضبط BOT_TOKEN كمتغير بيئة قبل التشغيل، أو ضع قيمته مكان النص الفارغ أدناه.
"""

import asyncio
import base64
import html
import json
import logging
import os
import sqlite3
import time
from collections import defaultdict
from pathlib import Path
from typing import Any

import aiohttp
from aiogram import Bot, Dispatcher, F, Router
from aiogram.client.default import DefaultBotProperties
from aiogram.filters import Command
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

# ============================ الإعداد ============================
# ضع التوكن بين علامتي الاقتباس للتجربة في Pydroid، أو استخدم متغير BOT_TOKEN في النظام.
BOT_TOKEN = os.getenv("BOT_TOKEN", "8988500207:AAHB1QmzRi4J8iuRO8TZtv3aaWySB6ApPPc").strip()
ADMIN_ID = int(os.getenv("ADMIN_ID", "8358047016"))
API_BASE = os.getenv("IPTV_API_BASE", "https://def.yacinelive.com").rstrip("/")
API_KEY = os.getenv("IPTV_API_KEY", "c!xZj+N9&G@Ev@vw")
APP_USER_AGENT = os.getenv("IPTV_USER_AGENT", "okhttp/4.12.0")
APP_LOCALE = os.getenv("IPTV_LOCALE", "ar")
DB_FILE = Path(os.getenv("IPTV_DB_FILE", "yacine_iptv_bot.db"))
PAGE_SIZE = 10
CATALOG_TTL = 15 * 60
STREAM_TTL = 90

if not BOT_TOKEN:
    raise RuntimeError("BOT_TOKEN غير مضبوط.")

logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(name)s | %(message)s")
logger = logging.getLogger("yacine_iptv_bot")

# ============================ التخزين المحلي ============================
class Store:
    def __init__(self) -> None:
        self.conn = sqlite3.connect(DB_FILE, check_same_thread=False)
        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                username TEXT,
                first_name TEXT,
                last_seen INTEGER NOT NULL
            )
        """)
        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS favorites (
                user_id INTEGER NOT NULL,
                channel_id TEXT NOT NULL,
                name TEXT NOT NULL,
                category_id TEXT NOT NULL,
                logo TEXT,
                added_at INTEGER NOT NULL,
                PRIMARY KEY (user_id, channel_id)
            )
        """)
        self.conn.commit()

    def add_user(self, message: Message) -> None:
        if not message.from_user:
            return
        user = message.from_user
        self.conn.execute(
            """INSERT INTO users(user_id, username, first_name, last_seen) VALUES(?,?,?,?)
               ON CONFLICT(user_id) DO UPDATE SET username=excluded.username,
               first_name=excluded.first_name, last_seen=excluded.last_seen""",
            (user.id, user.username or "", user.first_name or "", int(time.time())),
        )
        self.conn.commit()

    def toggle_favorite(self, user_id: int, channel: dict, category_id: str) -> bool:
        channel_id = str(channel.get("id") or "")
        exists = self.conn.execute(
            "SELECT 1 FROM favorites WHERE user_id=? AND channel_id=?", (user_id, channel_id)
        ).fetchone()
        if exists:
            self.conn.execute("DELETE FROM favorites WHERE user_id=? AND channel_id=?", (user_id, channel_id))
            self.conn.commit()
            return False
        self.conn.execute(
            """INSERT OR REPLACE INTO favorites(user_id, channel_id, name, category_id, logo, added_at)
               VALUES(?,?,?,?,?,?)""",
            (
                user_id,
                channel_id,
                str(channel.get("name") or "قناة"),
                str(category_id or ""),
                str(channel.get("logo") or ""),
                int(time.time()),
            ),
        )
        self.conn.commit()
        return True

    def is_favorite(self, user_id: int, channel_id: Any) -> bool:
        return bool(
            self.conn.execute(
                "SELECT 1 FROM favorites WHERE user_id=? AND channel_id=?", (user_id, str(channel_id))
            ).fetchone()
        )

    def favorites(self, user_id: int) -> list[dict]:
        rows = self.conn.execute(
            "SELECT channel_id, name, category_id, logo FROM favorites WHERE user_id=? ORDER BY added_at DESC",
            (user_id,),
        ).fetchall()
        return [{"id": row[0], "name": row[1], "category_id": row[2], "logo": row[3]} for row in rows]

    def users_count(self) -> int:
        return int(self.conn.execute("SELECT COUNT(*) FROM users").fetchone()[0])

# ============================ API ============================
class IPTVAPI:
    def __init__(self) -> None:
        self.session: aiohttp.ClientSession | None = None
        self._categories: list[dict] = []
        self._categories_updated = 0.0
        self._catalog: list[dict] = []
        self._catalog_updated = 0.0
        self._channels_by_category: dict[str, list[dict]] = {}
        self._category_children: dict[str, list[dict]] = {}
        self._streams: dict[str, tuple[float, list[dict]]] = {}
        self._config: dict[str, Any] = {}
        self._events: list[dict] = []
        self._catalog_lock = asyncio.Lock()

    @property
    def headers(self) -> dict[str, str]:
        return {
            "Accept": "application/json",
            "User-Agent": APP_USER_AGENT,
            "x-app-locale": APP_LOCALE,
        }

    async def get_session(self) -> aiohttp.ClientSession:
        if self.session is None or self.session.closed:
            timeout = aiohttp.ClientTimeout(total=20, connect=8)
            self.session = aiohttp.ClientSession(timeout=timeout)
        return self.session

    @staticmethod
    def decrypt(payload: str, timestamp: str) -> Any:
        """Base64 ثم XOR بمفتاح التطبيق مع ترويسة t لكل استجابة."""
        if not payload or not timestamp:
            raise ValueError("الاستجابة لا تحتوي البيانات أو ترويسة t")
        raw = base64.b64decode(payload + "=" * (-len(payload) % 4))
        key = (API_KEY + timestamp).encode("utf-8")
        plain = bytes(value ^ key[index % len(key)] for index, value in enumerate(raw))
        return json.loads(plain.decode("utf-8"))

    async def request(self, path: str) -> Any:
        """طلب مفكوك مع إعادة محاولة محدودة للمهلات العابرة."""
        session = await self.get_session()
        for attempt in range(3):
            try:
                async with session.get(f"{API_BASE}{path}", headers=self.headers) as response:
                    encoded = await response.text()
                    if response.status != 200:
                        logger.warning("API status %s for %s", response.status, path)
                    else:
                        timestamp = response.headers.get("t", "")
                        decoded = self.decrypt(encoded, timestamp)
                        return decoded.get("data") if isinstance(decoded, dict) and "data" in decoded else decoded
            except (aiohttp.ClientError, asyncio.TimeoutError, ValueError, UnicodeDecodeError, json.JSONDecodeError) as exc:
                logger.warning("API attempt %s failed for %s: %s", attempt + 1, path, type(exc).__name__)
            if attempt < 2:
                await asyncio.sleep(0.5 * (attempt + 1))
        return None

    async def categories(self, force: bool = False) -> list[dict]:
        if self._categories and not force and time.time() - self._categories_updated < CATALOG_TTL:
            return self._categories
        data = await self.request("/api/categories")
        if not isinstance(data, list):
            return self._categories
        self._categories = [item for item in data if isinstance(item, dict) and item.get("id") is not None]
        self._categories_updated = time.time()
        return self._categories

    async def category_children(self, category_id: Any, force: bool = False) -> list[dict]:
        key = str(category_id)
        if key in self._category_children and not force:
            return self._category_children[key]
        data = await self.request(f"/api/categories/{key}")
        children = [item for item in data if isinstance(item, dict) and item.get("id") is not None] if isinstance(data, list) else []
        self._category_children[key] = children
        return children

    async def config(self, force: bool = False) -> dict:
        if self._config and not force:
            return self._config
        data = await self.request("/api/config")
        self._config = data if isinstance(data, dict) else {}
        return self._config

    async def events(self, force: bool = False) -> list[dict]:
        if self._events and not force:
            return self._events
        data = await self.request("/api/events")
        self._events = [item for item in data if isinstance(item, dict)] if isinstance(data, list) else []
        return self._events

    async def category_channels(self, category_id: Any, force: bool = False) -> list[dict]:
        key = str(category_id)
        if key in self._channels_by_category and not force:
            return self._channels_by_category[key]
        data = await self.request(f"/api/categories/{key}/channels")
        if not isinstance(data, list):
            return self._channels_by_category.get(key, [])
        channels = [
            {**item, "category_id": key}
            for item in data
            if isinstance(item, dict) and item.get("id") is not None and not bool(item.get("is_hide"))
        ]
        channels.sort(key=lambda item: (int(item.get("priority") or 999999), str(item.get("name") or "").lower()))
        self._channels_by_category[key] = channels
        return channels

    async def all_channels(self, force: bool = False) -> list[dict]:
        if self._catalog and not force and time.time() - self._catalog_updated < CATALOG_TTL:
            return self._catalog
        async with self._catalog_lock:
            if self._catalog and not force and time.time() - self._catalog_updated < CATALOG_TTL:
                return self._catalog
            categories = await self.categories(force=force)
            semaphore = asyncio.Semaphore(6)

            async def load(category: dict) -> list[dict]:
                async with semaphore:
                    channels = await self.category_channels(category.get("id"), force=force)
                    if channels:
                        return channels
                    children = await self.category_children(category.get("id"), force=force)
                    if not children:
                        return []
                    nested = await asyncio.gather(
                        *(self.category_channels(child.get("id"), force=force) for child in children),
                        return_exceptions=True,
                    )
                    return [channel for group in nested if isinstance(group, list) for channel in group]

            groups = await asyncio.gather(*(load(category) for category in categories), return_exceptions=True)
            seen: set[str] = set()
            catalog: list[dict] = []
            for group in groups:
                if not isinstance(group, list):
                    continue
                for channel in group:
                    channel_id = str(channel.get("id") or "")
                    if channel_id and channel_id not in seen:
                        seen.add(channel_id)
                        catalog.append(channel)
            self._catalog = catalog
            self._catalog_updated = time.time()
            return catalog

    async def streams(self, channel_id: Any, force: bool = True) -> list[dict]:
        key = str(channel_id)
        cached = self._streams.get(key)
        if cached and not force and time.time() - cached[0] < STREAM_TTL:
            return cached[1]
        data = await self.request(f"/api/channel/{key}")
        raw = data if isinstance(data, list) else ([data] if isinstance(data, dict) else [])
        streams = []
        for item in raw:
            if not isinstance(item, dict):
                continue
            url = str(item.get("url") or "").strip()
            if not url.startswith(("https://", "http://")):
                continue
            streams.append(item)
        self._streams[key] = (time.time(), streams)
        return streams

    async def close(self) -> None:
        if self.session and not self.session.closed:
            await self.session.close()

# ============================ واجهة البوت ============================
store = Store()
api = IPTVAPI()
bot = Bot(BOT_TOKEN, default=DefaultBotProperties(parse_mode="HTML"))
dp = Dispatcher()
router = Router()
dp.include_router(router)
SEARCHING: set[int] = set()
SEARCH_RESULTS: dict[int, list[dict]] = {}


def clean(text: Any, limit: int = 42) -> str:
    value = " ".join(str(text or "").split())
    return value if len(value) <= limit else value[: limit - 1] + "…"


def esc(value: Any) -> str:
    return html.escape(str(value or ""))


def channel_button(channel: dict, category_id: str, page: int, prefix: str = "open") -> InlineKeyboardButton:
    name = clean(channel.get("name") or "قناة", 28)
    return InlineKeyboardButton(text=f"📺 {name}", callback_data=f"{prefix}:{channel.get('id')}:{category_id}:{page}")


def two_columns(buttons: list[InlineKeyboardButton]) -> list[list[InlineKeyboardButton]]:
    return [buttons[index:index + 2] for index in range(0, len(buttons), 2)]


def home_keyboard(categories: list[dict]) -> InlineKeyboardMarkup:
    category_buttons = [
        InlineKeyboardButton(
            text=f"📂 {clean(category.get('name'), 22)}",
            callback_data=f"cat:{category.get('id')}:1",
        )
        for category in categories
    ]
    rows = two_columns(category_buttons)
    rows.extend([
        [InlineKeyboardButton(text="📡 جميع القنوات", callback_data="all:1")],
        [
            InlineKeyboardButton(text="🔍 بحث", callback_data="search"),
            InlineKeyboardButton(text="⭐ المفضلة", callback_data="favorites:1"),
        ],
        [InlineKeyboardButton(text="⚽ الأحداث المباشرة", callback_data="events")],
        [InlineKeyboardButton(text="🔄 تحديث التصنيفات", callback_data="refresh")],
    ])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def page_callback(source: str, category_id: str, page: int) -> str:
    if source == "all":
        return f"all:{page}"
    if source == "favorites":
        return f"favorites:{page}"
    if source == "searchpage":
        return f"searchpage:{page}"
    return f"cat:{category_id}:{page}"


def back_callback(category_id: str, page: int) -> str:
    if category_id == "all":
        return f"all:{page}"
    if category_id == "fav":
        return f"favorites:{page}"
    if category_id == "search":
        return f"searchpage:{page}"
    return f"cat:{category_id}:{page}"


def channels_keyboard(channels: list[dict], category_id: str, page: int, total: int, source: str) -> InlineKeyboardMarkup:
    start = (page - 1) * PAGE_SIZE
    current = channels[start:start + PAGE_SIZE]
    rows = two_columns([channel_button(channel, category_id, page) for channel in current])
    nav: list[InlineKeyboardButton] = []
    if page > 1:
        nav.append(InlineKeyboardButton(text="◀️ السابق", callback_data=page_callback(source, category_id, page - 1)))
    if start + PAGE_SIZE < total:
        nav.append(InlineKeyboardButton(text="التالي ▶️", callback_data=page_callback(source, category_id, page + 1)))
    if nav:
        rows.append(nav)
    rows.append([InlineKeyboardButton(text="🔙 الأقسام", callback_data="home")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def details_keyboard(user_id: int, channel: dict, category_id: str, page: int) -> InlineKeyboardMarkup:
    channel_id = str(channel.get("id") or "")
    favorite = store.is_favorite(user_id, channel_id)
    rows = [
        [InlineKeyboardButton(text="▶️ مشاهدة والجودات", callback_data=f"watch:{channel_id}:{category_id}:{page}")],
        [InlineKeyboardButton(
            text="⭐ إزالة من المفضلة" if favorite else "⭐ إضافة للمفضلة",
            callback_data=f"fav:{channel_id}:{category_id}:{page}",
        )],
        [InlineKeyboardButton(text="🔙 رجوع للقنوات", callback_data=back_callback(category_id, page))],
        [InlineKeyboardButton(text="🏠 الأقسام", callback_data="home")],
    ]
    return InlineKeyboardMarkup(inline_keyboard=rows)


def qualities_keyboard(streams: list[dict], channel: dict, category_id: str, page: int) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    seen: set[str] = set()
    for stream in streams:
        url = str(stream.get("url") or "").strip()
        if url in seen or not url.startswith(("https://", "http://")):
            continue
        seen.add(url)
        label = clean(stream.get("name") or stream.get("quality") or stream.get("url_type") or "HD", 26)
        is_hls = ".m3u8" in url.lower()
        rows.append([InlineKeyboardButton(text=f"▶️ {'HLS ' if is_hls else ''}{label}", url=url)])
    if not rows:
        rows.append([InlineKeyboardButton(text="⚠️ لا يوجد رابط متاح", callback_data="noop")])
    rows.append([InlineKeyboardButton(text="🔙 رجوع للتفاصيل", callback_data=f"open:{channel.get('id')}:{category_id}:{page}")])
    rows.append([InlineKeyboardButton(text="🏠 الأقسام", callback_data="home")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def channel_text(channel: dict) -> str:
    name = esc(channel.get("name") or "قناة")
    return f"<b>📺 {name}</b>\n\nاختر <b>مشاهدة والجودات</b> ليتم تحديث رابط البث الآن ثم تظهر الأزرار المباشرة."


async def edit(callback: CallbackQuery, text: str, markup: InlineKeyboardMarkup) -> None:
    try:
        await callback.message.edit_text(text, reply_markup=markup)
    except Exception:
        await callback.message.answer(text, reply_markup=markup)


async def home_view(force: bool = False) -> tuple[str, InlineKeyboardMarkup]:
    categories = await api.categories(force=force)
    if not categories:
        return (
            "❌ تعذر تحميل التصنيفات الآن. تحقق من الإنترنت ثم أعد المحاولة.",
            InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="🔄 إعادة المحاولة", callback_data="refresh")]]),
        )
    config = await api.config(force=force)
    app_info = config.get("app") if isinstance(config.get("app"), dict) else {}
    app_name = clean(app_info.get("name") or app_info.get("title") or "IPTV Live", 32)
    return (
        f"<b>📡 {esc(app_name)}</b>\n\nالتصنيفات المتاحة: <b>{len(categories)}</b>\nاختر تصنيفاً أو ابحث عن قناة.",
        home_keyboard(categories),
    )


async def find_channel(channel_id: Any, category_id: Any = "") -> dict | None:
    target = str(channel_id)
    if category_id:
        channels = await api.category_channels(category_id)
        for channel in channels:
            if str(channel.get("id")) == target:
                return channel
    catalog = await api.all_channels()
    return next((channel for channel in catalog if str(channel.get("id")) == target), None)


async def show_category(callback: CallbackQuery, category_id: str, page: int) -> None:
    channels = await api.category_channels(category_id)
    categories = await api.categories()
    category = next((item for item in categories if str(item.get("id")) == str(category_id)), {})
    title = esc(category.get("name") or "القنوات")
    if not channels:
        children = await api.category_children(category_id)
        if children:
            child_buttons = [
                InlineKeyboardButton(text=f"📂 {clean(child.get('name'), 24)}", callback_data=f"cat:{child.get('id')}:1")
                for child in children
            ]
            markup = InlineKeyboardMarkup(inline_keyboard=two_columns(child_buttons) + [[InlineKeyboardButton(text="🔙 الأقسام", callback_data="home")]])
            await edit(callback, f"<b>📂 {title}</b>\n\nاختر التصنيف الفرعي:", markup)
            return
        await edit(callback, f"<b>📂 {title}</b>\n\nلا توجد قنوات ظاهرة حالياً.", InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="🔙 الأقسام", callback_data="home")]]))
        return
    await edit(
        callback,
        f"<b>📂 {title}</b>\nالقنوات: <b>{len(channels)}</b> | الصفحة: <b>{page}</b>",
        channels_keyboard(channels, str(category_id), page, len(channels), "cat"),
    )


async def show_all(callback: CallbackQuery, page: int) -> None:
    await edit(callback, "⏳ جارٍ تحميل كل القنوات مرة واحدة…", InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="⏳ جاري التحميل", callback_data="noop")]]))
    channels = await api.all_channels()
    if not channels:
        await edit(callback, "❌ تعذر تحميل فهرس القنوات.", InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="🔙 الأقسام", callback_data="home")]]))
        return
    await edit(
        callback,
        f"<b>📡 جميع القنوات</b>\nالمتاح: <b>{len(channels)}</b> | الصفحة: <b>{page}</b>",
        channels_keyboard(channels, "all", page, len(channels), "all"),
    )


async def show_search_results(callback: CallbackQuery, page: int) -> None:
    channels = SEARCH_RESULTS.get(callback.from_user.id, [])
    if not channels:
        await callback.answer("انتهت جلسة البحث؛ ابدأ بحثاً جديداً.", show_alert=True)
        return
    await edit(
        callback,
        f"<b>🔍 نتائج البحث</b>\nالنتائج: <b>{len(channels)}</b> | الصفحة: <b>{page}</b>",
        channels_keyboard(channels, "search", page, len(channels), "searchpage"),
    )


async def show_events(callback: CallbackQuery) -> None:
    events = await api.events(force=True)
    if not events:
        await edit(callback, "⚽ لا توجد أحداث ظاهرة حالياً.", InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="🔙 الأقسام", callback_data="home")]]))
        return
    lines = ["<b>⚽ الأحداث المباشرة</b>", ""]
    for event in events[:12]:
        first = event.get("team_1") if isinstance(event.get("team_1"), dict) else {}
        second = event.get("team_2") if isinstance(event.get("team_2"), dict) else {}
        first_name = clean(first.get("name") or event.get("team_1") or "فريق 1", 22)
        second_name = clean(second.get("name") or event.get("team_2") or "فريق 2", 22)
        championship = clean(event.get("champions") or "", 32)
        commentary = clean(event.get("commentary") or "", 28)
        line = f"• <b>{esc(first_name)} × {esc(second_name)}</b>"
        if championship:
            line += f"\n  {esc(championship)}"
        if commentary:
            line += f" — {esc(commentary)}"
        lines.append(line)
    await edit(callback, "\n".join(lines), InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔄 تحديث الأحداث", callback_data="events")],
        [InlineKeyboardButton(text="🔙 الأقسام", callback_data="home")],
    ]))


async def show_favorites(callback: CallbackQuery, page: int) -> None:
    channels = store.favorites(callback.from_user.id)
    if not channels:
        text, markup = await home_view()
        await edit(callback, "<b>⭐ المفضلة فارغة حالياً.</b>\n\n" + text, markup)
        return
    await edit(
        callback,
        f"<b>⭐ المفضلة</b>\nالقنوات المحفوظة: <b>{len(channels)}</b>",
        channels_keyboard(channels, "fav", page, len(channels), "favorites"),
    )

# ============================ المعالجات ============================
@router.message(Command("start"))
async def start(message: Message) -> None:
    store.add_user(message)
    loading = await message.answer("⏳ جاري تجهيز IPTV…")
    text, markup = await home_view()
    await loading.edit_text(text, reply_markup=markup)


@router.message(Command("ping"))
async def ping(message: Message) -> None:
    await message.answer("✅ البوت يعمل. أرسل /start لفتح القنوات.")


@router.message(Command("admin"))
async def admin(message: Message) -> None:
    if not ADMIN_ID or not message.from_user or message.from_user.id != ADMIN_ID:
        await message.answer("⛔ غير مصرح.")
        return
    await message.answer(f"⚙️ حالة البوت\n👥 المستخدمون: {store.users_count()}\n📚 كاش الفهرس: {len(api._catalog)} قناة")


@router.callback_query(F.data == "home")
async def home(callback: CallbackQuery) -> None:
    await callback.answer()
    text, markup = await home_view()
    await edit(callback, text, markup)


@router.callback_query(F.data == "refresh")
async def refresh(callback: CallbackQuery) -> None:
    await callback.answer("جاري تحديث التصنيفات…")
    api._channels_by_category.clear()
    api._category_children.clear()
    api._catalog = []
    api._config = {}
    api._events = []
    text, markup = await home_view(force=True)
    await edit(callback, text, markup)


@router.callback_query(F.data.startswith("cat:"))
async def category(callback: CallbackQuery) -> None:
    await callback.answer()
    _, category_id, page_text = callback.data.split(":", 2)
    await show_category(callback, category_id, max(1, int(page_text)))


@router.callback_query(F.data.startswith("all:"))
async def all_channels(callback: CallbackQuery) -> None:
    await callback.answer()
    _, page_text = callback.data.split(":", 1)
    await show_all(callback, max(1, int(page_text)))


@router.callback_query(F.data == "events")
async def events(callback: CallbackQuery) -> None:
    await callback.answer("جاري تحميل الأحداث…")
    await show_events(callback)


@router.callback_query(F.data.startswith("favorites:"))
async def favorites(callback: CallbackQuery) -> None:
    await callback.answer()
    _, page_text = callback.data.split(":", 1)
    await show_favorites(callback, max(1, int(page_text)))


@router.callback_query(F.data.startswith("searchpage:"))
async def search_page(callback: CallbackQuery) -> None:
    await callback.answer()
    _, page_text = callback.data.split(":", 1)
    await show_search_results(callback, max(1, int(page_text)))


@router.callback_query(F.data.startswith("open:"))
async def open_channel(callback: CallbackQuery) -> None:
    await callback.answer("جاري تحميل القناة…")
    _, channel_id, category_id, page_text = callback.data.split(":", 3)
    page = max(1, int(page_text))
    channel = await find_channel(channel_id, "" if category_id in {"all", "fav"} else category_id)
    if not channel:
        await callback.answer("تعذر العثور على القناة. افتح القائمة مجدداً.", show_alert=True)
        return
    await edit(callback, channel_text(channel), details_keyboard(callback.from_user.id, channel, category_id, page))


@router.callback_query(F.data.startswith("watch:"))
async def watch(callback: CallbackQuery) -> None:
    await callback.answer("جاري تحديث روابط البث…")
    _, channel_id, category_id, page_text = callback.data.split(":", 3)
    page = max(1, int(page_text))
    channel = await find_channel(channel_id, "" if category_id in {"all", "fav"} else category_id)
    if not channel:
        await callback.answer("تعذر العثور على القناة.", show_alert=True)
        return
    streams = await api.streams(channel_id, force=True)
    if not streams:
        await edit(callback, "⚠️ لا توجد روابط بث متاحة لهذه القناة حالياً.", details_keyboard(callback.from_user.id, channel, category_id, page))
        return
    await edit(
        callback,
        f"<b>▶️ {esc(channel.get('name') or 'مشاهدة')}</b>\n\nاختر الجودة؛ الزر يفتح رابط البث مباشرة.",
        qualities_keyboard(streams, channel, category_id, page),
    )


@router.callback_query(F.data.startswith("fav:"))
async def favorite(callback: CallbackQuery) -> None:
    await callback.answer()
    _, channel_id, category_id, page_text = callback.data.split(":", 3)
    page = max(1, int(page_text))
    channel = await find_channel(channel_id, "" if category_id in {"all", "fav"} else category_id)
    if not channel:
        await callback.answer("تعذر العثور على القناة.", show_alert=True)
        return
    active = store.toggle_favorite(callback.from_user.id, channel, category_id)
    state = "✅ أضيفت إلى المفضلة.\n\n" if active else "✅ أزيلت من المفضلة.\n\n"
    await edit(callback, state + channel_text(channel), details_keyboard(callback.from_user.id, channel, category_id, page))


@router.callback_query(F.data == "search")
async def search(callback: CallbackQuery) -> None:
    await callback.answer()
    SEARCHING.add(callback.from_user.id)
    await callback.message.answer("🔍 أرسل اسم القناة للبحث فيها:")


@router.message(lambda message: bool(message.from_user) and message.from_user.id in SEARCHING)
async def search_message(message: Message) -> None:
    SEARCHING.discard(message.from_user.id)
    term = (message.text or "").strip()
    if len(term) < 2:
        await message.answer("اكتب حرفين على الأقل للبحث.")
        return
    loading = await message.answer("⏳ جاري البحث في كل القنوات…")
    catalog = await api.all_channels()
    needle = term.casefold()
    results = [channel for channel in catalog if needle in str(channel.get("name") or "").casefold()]
    SEARCH_RESULTS[message.from_user.id] = results
    if not results:
        await loading.edit_text("🔎 لم أجد قناة مطابقة. جرّب كلمة أخرى.", reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="🔙 الأقسام", callback_data="home")]]))
        return
    await loading.edit_text(
        f"<b>🔍 نتائج البحث: {esc(clean(term, 35))}</b>\nالنتائج: <b>{len(results)}</b>",
        reply_markup=channels_keyboard(results, "search", 1, len(results), "searchpage"),
    )


@router.callback_query(F.data == "noop")
async def noop(callback: CallbackQuery) -> None:
    await callback.answer()


async def on_shutdown() -> None:
    await api.close()


async def main() -> None:
    logger.info("IPTV bot is starting")
    try:
        await dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types())
    finally:
        await on_shutdown()


if __name__ == "__main__":
    asyncio.run(main())
