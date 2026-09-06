import asyncio
import hashlib
import hmac
import json
import logging
import os
import secrets
import sqlite3
import time
from collections import defaultdict
from pathlib import Path
from urllib.parse import urlparse

import aiohttp
from aiogram import Bot, Dispatcher, F, Router
from aiogram.filters import Command
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

# =========================================================
# إعدادات نسخة التجربة
# =========================================================
BOT_TOKEN = os.getenv("BOT_TOKEN", "8988500207:AAHB1QmzRi4J8iuRO8TZtv3aaWySB6ApPPc").strip()
ADMIN_ID = int(os.getenv("ADMIN_ID", "8358047016"))

# المضيف الذي استخدمه التطبيق في ملف HAR؛ يمكن تغييره من البيئة إن غيّر المصدر نطاقه لاحقاً.
CHANNELS_API_BASE = os.getenv("CHANNELS_API_BASE", "https://api.myychann.site").rstrip("/")
CHANNELS_URL = f"{CHANNELS_API_BASE}/api/channels/"
CHANNEL_DETAILS_URL = f"{CHANNELS_API_BASE}/api/channels/show.php"
CHANNEL_COLLECTIONS_URL = f"{CHANNELS_API_BASE}/api/channels/collections.php"
CERT_SHA256 = "6e2fcda8631eb49ebcba4ca8ef4c597abe84654c7d3e8096db32bdd21ecf763f"
PKG_NAME = "com.drama.mp4"
GUARD_1 = "OscarTVIronGuard"
GUARD_2 = "IronGuard"

CATALOG_FILE = Path("channels_catalog.json")
DB_FILE = "channels_bot.db"
CHANNELS_PER_PAGE = 10
CHANNEL_BUTTONS_PER_ROW = 2
# قيمة احتياطية قابلة للضبط فقط؛ المسار الأساسي يعتمد على pagination الرسمي ولا يفحص IDs عشوائياً.
CATALOG_MAX_ID = int(os.getenv("CATALOG_MAX_ID", "1000"))
CATALOG_CONCURRENCY = int(os.getenv("CATALOG_CONCURRENCY", "20"))
CATALOG_TTL = 6 * 60 * 60

logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s")
logger = logging.getLogger("channels-fast")

# =========================================================
# Iron headers
# =========================================================
def derive_key(cert_sha256: str, pkg_name: str) -> bytes:
    raw = f"{cert_sha256}|{pkg_name}".encode()
    first = bytes(byte ^ ord(GUARD_1[index % 7]) for index, byte in enumerate(raw))
    second = first[::-1]
    third = bytes(byte ^ ord(GUARD_2[index % 9]) for index, byte in enumerate(second))
    return hashlib.sha256(hashlib.sha256(hashlib.sha256(third).digest()).digest()).digest()


def iron_headers(url: str) -> dict:
    parsed_url = urlparse(url)
    path = parsed_url.path or "/"
    timestamp = str(int(time.time()))
    nonce = secrets.token_hex(4)
    payload = f"{path}|{timestamp}|{nonce}".encode()
    signature = hmac.new(derive_key(CERT_SHA256, PKG_NAME), payload, hashlib.sha256).hexdigest()
    fingerprint = CERT_SHA256[:8]
    return {
        "Host": parsed_url.netloc,
        "x-iron-sig": signature,
        "x-iron-ts": timestamp,
        "x-iron-nonce": nonce,
        "x-iron-diag": f"f={fingerprint} p={fingerprint} h=0",
        "accept-encoding": "gzip",
        "user-agent": "okhttp/4.12.0",
        "connection": "keep-alive",
    }

# =========================================================
# تخزين خفيف: مستخدمون ومفضلة فقط
# =========================================================
class Store:
    def __init__(self, path: str = DB_FILE):
        self.connection = sqlite3.connect(path, check_same_thread=False)
        self.connection.execute(
            "CREATE TABLE IF NOT EXISTS users (user_id INTEGER PRIMARY KEY, username TEXT, first_name TEXT)"
        )
        self.connection.execute(
            "CREATE TABLE IF NOT EXISTS favorites (user_id INTEGER, channel_id INTEGER, payload TEXT, "
            "PRIMARY KEY(user_id, channel_id))"
        )
        self.connection.commit()

    def add_user(self, message: Message) -> None:
        user = message.from_user
        self.connection.execute(
            "INSERT OR IGNORE INTO users(user_id, username, first_name) VALUES (?, ?, ?)",
            (user.id, user.username or "", user.first_name or ""),
        )
        self.connection.commit()

    def users_count(self) -> int:
        return self.connection.execute("SELECT COUNT(*) FROM users").fetchone()[0]

    def is_favorite(self, user_id: int, channel_id: int) -> bool:
        return self.connection.execute(
            "SELECT 1 FROM favorites WHERE user_id = ? AND channel_id = ?", (user_id, channel_id)
        ).fetchone() is not None

    def toggle_favorite(self, user_id: int, channel: dict) -> bool:
        channel_id = int(channel["id"])
        if self.is_favorite(user_id, channel_id):
            self.connection.execute("DELETE FROM favorites WHERE user_id = ? AND channel_id = ?", (user_id, channel_id))
            self.connection.commit()
            return False
        self.connection.execute(
            "INSERT OR REPLACE INTO favorites(user_id, channel_id, payload) VALUES (?, ?, ?)",
            (user_id, channel_id, json.dumps(channel, ensure_ascii=False)),
        )
        self.connection.commit()
        return True

    def favorites(self, user_id: int) -> list[dict]:
        rows = self.connection.execute("SELECT payload FROM favorites WHERE user_id = ?", (user_id,)).fetchall()
        result = []
        for (payload,) in rows:
            try:
                result.append(json.loads(payload))
            except json.JSONDecodeError:
                continue
        return result

# =========================================================
# فهرس القنوات: محلي وسريع، والرابط يتحدث عند فتح القناة فقط
# =========================================================
class ChannelsAPI:
    def __init__(self):
        self.session: aiohttp.ClientSession | None = None
        self.channels: list[dict] = []
        self.by_id: dict[int, dict] = {}
        self.catalog_updated = 0.0
        self.refresh_task: asyncio.Task | None = None
        self.ready = asyncio.Event()

    async def get_session(self) -> aiohttp.ClientSession:
        if self.session is None or self.session.closed:
            timeout = aiohttp.ClientTimeout(total=12, connect=6)
            self.session = aiohttp.ClientSession(timeout=timeout)
        return self.session

    async def close(self) -> None:
        if self.session and not self.session.closed:
            await self.session.close()

    @staticmethod
    def normalize(channel: dict) -> dict:
        channel = dict(channel or {})
        channel_id = channel.get("id")
        if channel_id is not None:
            try:
                channel["id"] = int(channel_id)
            except (TypeError, ValueError):
                pass
        channel["name"] = str(channel.get("name") or channel.get("title") or "قناة بدون اسم")
        channel["category_label"] = str(channel.get("category_label") or channel.get("category") or "أخرى")
        channel["country_name"] = str(channel.get("country_name") or channel.get("country") or "غير محدد")
        channel["streams"] = channel.get("streams") if isinstance(channel.get("streams"), list) else []
        return channel

    def set_catalog(self, channels: list[dict], updated_at: float | None = None) -> None:
        unique: dict[int, dict] = {}
        for raw in channels:
            item = self.normalize(raw)
            if isinstance(item.get("id"), int):
                unique[item["id"]] = item
        self.by_id = unique
        self.channels = sorted(unique.values(), key=lambda item: item["name"].casefold())
        self.catalog_updated = updated_at or time.time()
        if self.channels:
            self.ready.set()

    def load_local_catalog(self) -> bool:
        if not CATALOG_FILE.exists():
            return False
        try:
            payload = json.loads(CATALOG_FILE.read_text(encoding="utf-8"))
            channels = payload.get("channels", [])
            self.set_catalog(channels, float(payload.get("updated_at") or 0))
            logger.info("Loaded %s channels from local catalog", len(self.channels))
            return bool(self.channels)
        except Exception as exc:
            logger.warning("Local catalog ignored: %s", exc)
            return False

    def save_local_catalog(self) -> None:
        payload = {"updated_at": self.catalog_updated, "channels": self.channels}
        CATALOG_FILE.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")

    async def fetch_channel(self, channel_id: int) -> dict | None:
        """طلب واحد للقناة المطلوبة فقط؛ يستعمل دائماً توقيعاً حديثاً."""
        try:
            session = await self.get_session()
            async with session.get(CHANNEL_DETAILS_URL, params={"id": channel_id}, headers=iron_headers(CHANNEL_DETAILS_URL)) as response:
                if response.status != 200:
                    return None
                data = await response.json(content_type=None)
                if isinstance(data, dict) and data.get("status") == "success" and data.get("data"):
                    return self.normalize(data["data"])
        except (aiohttp.ClientError, asyncio.TimeoutError, ValueError) as exc:
            logger.debug("Channel %s refresh failed: %s", channel_id, exc)
        return None

    async def get_channel_fresh(self, channel_id: int) -> dict | None:
        """يفرض تحديث البيانات والرابط عند فتح القناة أو اختيار الجودة."""
        fresh = await self.fetch_channel(channel_id)
        if fresh:
            self.by_id[channel_id] = fresh
            self.channels = sorted(self.by_id.values(), key=lambda item: item["name"].casefold())
            return fresh
        return self.by_id.get(channel_id)

    async def _catalog_page(self, page: int, limit: int = 100) -> dict:
        """يجلب صفحة واحدة مع بيانات pagination من واجهة القنوات."""
        try:
            session = await self.get_session()
            params = {"page": page, "limit": limit}
            async with session.get(CHANNELS_URL, params=params, headers=iron_headers(CHANNELS_URL)) as response:
                if response.status == 200:
                    payload = await response.json(content_type=None)
                    return payload if isinstance(payload, dict) else {}
        except (aiohttp.ClientError, asyncio.TimeoutError, ValueError) as exc:
            logger.warning("Catalog page %s failed: %s", page, type(exc).__name__)
        return {}

    async def _collection_channels(self) -> list[dict]:
        """يجلب القنوات المضمّنة في مجموعات التطبيق؛ قد تضيف مجموعة قناة قبل ظهورها في الفهرس العام."""
        try:
            session = await self.get_session()
            async with session.get(CHANNEL_COLLECTIONS_URL, headers=iron_headers(CHANNEL_COLLECTIONS_URL)) as response:
                if response.status != 200:
                    return []
                payload = await response.json(content_type=None)
                collections = payload.get("data", []) if isinstance(payload, dict) else []
                return [
                    channel
                    for collection in collections if isinstance(collection, dict)
                    for channel in (collection.get("channels", []) if isinstance(collection.get("channels"), list) else [])
                    if isinstance(channel, dict)
                ]
        except (aiohttp.ClientError, asyncio.TimeoutError, ValueError) as exc:
            logger.debug("Channel collections fetch failed: %s", type(exc).__name__)
        return []

    async def fetch_catalog(self) -> list[dict]:
        """يجلب كل صفحات القنوات ثم يدمج مجموعات التطبيق، مع إزالة التكرار بالمعرّف."""
        first = await self._catalog_page(1)
        first_items = first.get("data", []) if isinstance(first.get("data"), list) else []
        pagination = first.get("pagination", {}) if isinstance(first.get("pagination"), dict) else {}
        total_pages = max(1, int(pagination.get("total_pages") or 1))

        page_tasks = [self._catalog_page(page) for page in range(2, total_pages + 1)]
        pages = [first_items]
        if page_tasks:
            remaining = await asyncio.gather(*page_tasks)
            pages.extend(
                payload.get("data", [])
                for payload in remaining
                if isinstance(payload.get("data"), list)
            )
        collection_items = await self._collection_channels()

        unique: dict[int, dict] = {}
        for raw in (item for page_items in pages for item in page_items):
            if isinstance(raw, dict):
                item = self.normalize(raw)
                if isinstance(item.get("id"), int):
                    unique[item["id"]] = item
        catalog_count = len(unique)
        for raw in collection_items:
            item = self.normalize(raw)
            if isinstance(item.get("id"), int):
                unique.setdefault(item["id"], item)
        extra_from_collections = len(unique) - catalog_count
        logger.info(
            "Fetched %s/%s channels from %s API pages; collections added %s extra channels",
            len(unique), pagination.get("total", "?"), total_pages, extra_from_collections,
        )
        return list(unique.values())

    async def _scan_one(self, semaphore: asyncio.Semaphore, channel_id: int) -> dict | None:
        async with semaphore:
            return await self.fetch_channel(channel_id)

    async def refresh_catalog_now(self) -> list[dict]:
        """يجلب الفهرس الكامل الآن ويحفظه؛ مناسب لبدء البوت وإظهار كل القنوات."""
        found = await self.fetch_catalog()
        if found:
            self.set_catalog(found)
            self.save_local_catalog()
            logger.info("Full catalog ready: %s channels", len(found))
        return self.channels

    async def warm_catalog(self) -> None:
        """يبني فهرساً في الخلفية؛ لا ينتظر المستخدم ولا يعطل الضغط على الأزرار."""
        if self.refresh_task and not self.refresh_task.done():
            return

        async def runner():
            # المسار الرئيسي: طلبات صفحات متوازية تعيد جميع القنوات ولا تفوت الدفعات التالية.
            found = await self.fetch_catalog()
            if not found:
                # بديل احتياطي فقط إذا توقفت واجهة القائمة؛ يبقى متوازياً وفي الخلفية.
                semaphore = asyncio.Semaphore(CATALOG_CONCURRENCY)
                tasks = [self._scan_one(semaphore, channel_id) for channel_id in range(1, CATALOG_MAX_ID + 1)]
                found = []
                for task in asyncio.as_completed(tasks):
                    item = await task
                    if item:
                        found.append(item)
            if found:
                self.set_catalog(found)
                self.save_local_catalog()
                logger.info("Catalog refresh complete: %s channels", len(found))
            elif not self.channels:
                logger.warning("Catalog refresh returned no channels")

        self.refresh_task = asyncio.create_task(runner())

    async def catalog(self) -> list[dict] | None:
        if self.channels:
            if time.time() - self.catalog_updated > CATALOG_TTL:
                await self.warm_catalog()
            return self.channels
        await self.warm_catalog()
        return None

    def categories(self) -> list[tuple[str, int]]:
        counts: dict[str, int] = defaultdict(int)
        for channel in self.channels:
            counts[channel["category_label"]] += 1
        return sorted(counts.items(), key=lambda pair: (-pair[1], pair[0].casefold()))

# =========================================================
# واجهة نظيفة
# =========================================================
store = Store()
api = ChannelsAPI()
bot = Bot(BOT_TOKEN)
dp = Dispatcher()
router = Router()
dp.include_router(router)

CATEGORY_TOKENS: dict[str, str] = {}
QUALITY_TOKENS: dict[tuple[int, int], dict[str, str]] = {}


def cut(text: str, size: int = 46) -> str:
    text = str(text)
    return text if len(text) <= size else text[: size - 1] + "…"


CATEGORY_ORDER = [
    ("عام", "📺"),
    ("رياضة", "⚽"),
    ("أفلام", "🎬"),
    ("مسلسلات", "📺"),
    ("موسيقى", "🎵"),
    ("أخبار", "📰"),
    ("ترفيه", "🎭"),
    ("وثائقي", "📚"),
    ("ديني", "🕌"),
    ("أطفال", "👶"),
    ("دراما", "🎭"),
]


def back_main() -> list[list[InlineKeyboardButton]]:
    return [[InlineKeyboardButton(text="🏠 الأقسام", callback_data="home")]]


def channels_keyboard(channels: list[dict], page: int, title_context: str = "all") -> InlineKeyboardMarkup:
    pages = max(1, (len(channels) + CHANNELS_PER_PAGE - 1) // CHANNELS_PER_PAGE)
    page = min(max(page, 1), pages)
    start = (page - 1) * CHANNELS_PER_PAGE
    rows: list[list[InlineKeyboardButton]] = []
    page_channels = channels[start:start + CHANNELS_PER_PAGE]
    buttons = [
        InlineKeyboardButton(
            text=f"📺 {cut(channel['name'], 30)}",
            callback_data=f"channel:{channel['id']}:{page}:{title_context}",
        )
        for channel in page_channels
    ]
    # صفّان متوازيان: قناتان في كل صف، مع بقاء 10 قنوات في الصفحة (5 صفوف فقط).
    rows.extend([buttons[index:index + CHANNEL_BUTTONS_PER_ROW] for index in range(0, len(buttons), CHANNEL_BUTTONS_PER_ROW)])
    nav = []
    if page > 1:
        nav.append(InlineKeyboardButton(text="◀️ السابق", callback_data=f"list:{title_context}:{page - 1}"))
    nav.append(InlineKeyboardButton(text=f"{page}/{pages}", callback_data="noop"))
    if page < pages:
        nav.append(InlineKeyboardButton(text="التالي ▶️", callback_data=f"list:{title_context}:{page + 1}"))
    rows.append(nav)
    rows.extend(back_main())
    return InlineKeyboardMarkup(inline_keyboard=rows)


def category_keyboard(categories: list[tuple[str, int]]) -> InlineKeyboardMarkup:
    """شبكة تصنيفات مرتبة ومطابقة لتسميات API العربية."""
    counts = dict(categories)
    CATEGORY_TOKENS.clear()
    cells: list[InlineKeyboardButton] = []
    for label, icon in CATEGORY_ORDER:
        count = counts.get(label, 0)
        if not count:
            continue
        token = hashlib.sha1(label.encode()).hexdigest()[:10]
        CATEGORY_TOKENS[token] = label
        cells.append(InlineKeyboardButton(text=f"{icon} {label} ({count})", callback_data=f"category:{token}"))
    known = {label for label, _icon in CATEGORY_ORDER}
    for label, count in sorted(counts.items(), key=lambda item: item[0].casefold()):
        if label in known:
            continue
        token = hashlib.sha1(label.encode()).hexdigest()[:10]
        CATEGORY_TOKENS[token] = label
        cells.append(InlineKeyboardButton(text=f"📂 {cut(label, 20)} ({count})", callback_data=f"category:{token}"))
    rows = [cells[index:index + 2] for index in range(0, len(cells), 2)]
    rows.append([InlineKeyboardButton(text=f"📡 جميع القنوات ({sum(counts.values())})", callback_data="all")])
    rows.append([
        InlineKeyboardButton(text="🔍 بحث", callback_data="search"),
        InlineKeyboardButton(text="⭐ المفضلة", callback_data="favorites"),
    ])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def main_keyboard() -> InlineKeyboardMarkup:
    return category_keyboard(api.categories()) if api.channels else InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📡 تحميل القنوات", callback_data="all")],
        [InlineKeyboardButton(text="🔍 بحث", callback_data="search"), InlineKeyboardButton(text="⭐ المفضلة", callback_data="favorites")],
    ])


def details_text(channel: dict) -> str:
    return (
        f"<b>📺 {channel['name']}</b>\n\n"
        f"🏷️ التصنيف: {channel['category_label']}\n"
        f"🌍 الدولة: {channel['country_name']}\n"
        f"👁️ المشاهدات: {channel.get('views_count') or 0}\n"
        f"📡 التردد: {channel.get('frequency') or 'غير محدد'}\n\n"
        "اختر الجودة؛ زر المشاهدة يفتح الرابط مباشرة. تُحدّث القناة عند فتحها."
    )


def channel_keyboard(user_id: int, channel: dict, context: str) -> InlineKeyboardMarkup:
    """الجودة زر رابط مباشر؛ لا توجد شاشة تأكيد بعد الاختيار."""
    rows: list[list[InlineKeyboardButton]] = []
    seen_qualities = set()
    for stream in channel.get("streams", []):
        quality = str(stream.get("quality") or "Auto")
        stream_url = str(stream.get("stream_url") or stream.get("url") or "").strip()
        if stream_url and quality not in seen_qualities:
            seen_qualities.add(quality)
            rows.append([InlineKeyboardButton(text=f"▶️ مشاهدة {quality}", url=stream_url)])
    if not seen_qualities:
        rows.append([InlineKeyboardButton(text="⚠️ لا توجد جودة متاحة حالياً", callback_data="noop")])
    favorite_text = "⭐ إزالة من المفضلة" if store.is_favorite(user_id, channel["id"]) else "⭐ إضافة للمفضلة"
    rows.append([InlineKeyboardButton(text=favorite_text, callback_data=f"fav:{channel['id']}:{context}")])
    rows.append([InlineKeyboardButton(text="🔙 رجوع للقنوات", callback_data=f"list:{context}:1")])
    rows.extend(back_main())
    return InlineKeyboardMarkup(inline_keyboard=rows)


def search_results(channels: list[dict], term: str) -> list[dict]:
    needle = term.casefold().strip()
    return [
        channel for channel in channels
        if needle in channel["name"].casefold()
        or needle in channel["category_label"].casefold()
        or needle in channel["country_name"].casefold()
    ]

async def edit(callback: CallbackQuery, text: str, markup: InlineKeyboardMarkup) -> None:
    try:
        await callback.message.edit_text(text, reply_markup=markup)
    except Exception:
        await callback.message.answer(text, reply_markup=markup)

async def require_catalog(callback: CallbackQuery) -> list[dict] | None:
    channels = await api.catalog()
    if channels:
        return channels
    await callback.answer("جاري تحميل الفهرس الكامل…")
    channels = await api.refresh_catalog_now()
    if channels:
        return channels
    await callback.message.answer("❌ تعذر تحميل القنوات حالياً. جرّب بعد قليل.", reply_markup=main_keyboard())
    return None

# =========================================================
# الأوامر والمعالجات
# =========================================================
@router.message(Command("start"))
async def start(message: Message):
    store.add_user(message)
    loading = await message.answer("⏳ جاري تحميل القنوات والتصنيفات…")
    channels = await api.refresh_catalog_now()
    if not channels:
        await loading.edit_text("❌ تعذر تحميل القنوات حالياً. جرّب /start بعد قليل.", reply_markup=main_keyboard())
        return
    await loading.edit_text(
        f"<b>📡 القنوات</b>\n\nتم تحميل <b>{len(channels)}</b> قناة. اختر التصنيف:",
        reply_markup=category_keyboard(api.categories()),
    )

@router.message(Command("admin"))
async def admin(message: Message):
    if message.from_user.id != ADMIN_ID:
        await message.answer("⛔ غير مصرح.")
        return
    await message.answer(f"⚙️ لوحة مختصرة\n👥 المستخدمون: {store.users_count()}\n📺 القنوات في الكاش: {len(api.channels)}")

@router.callback_query(F.data == "home")
async def home(callback: CallbackQuery):
    await callback.answer()
    await edit(callback, f"<b>📡 القنوات</b>\nتم تحميل <b>{len(api.channels)}</b> قناة. اختر التصنيف:", category_keyboard(api.categories()))

@router.callback_query(F.data == "all")
async def all_channels(callback: CallbackQuery):
    await callback.answer()
    channels = await require_catalog(callback)
    if channels:
        await edit(callback, f"<b>📡 كل القنوات</b>\nالمتاح: {len(channels)} قناة", channels_keyboard(channels, 1, "all"))

@router.callback_query(F.data == "categories")
async def categories(callback: CallbackQuery):
    await callback.answer()
    channels = await require_catalog(callback)
    if channels:
        await edit(callback, "<b>📂 التصنيفات الدقيقة</b>\nالتصنيفات مستخرجة من القنوات المتاحة فعلياً:", category_keyboard(api.categories()))

@router.callback_query(F.data.startswith("category:"))
async def category(callback: CallbackQuery):
    await callback.answer()
    channels = await require_catalog(callback)
    if not channels:
        return
    token = callback.data.split(":", 1)[1]
    label = CATEGORY_TOKENS.get(token)
    if not label:
        await callback.answer("انتهت صلاحية التصنيفات، افتحها مجدداً.", show_alert=True)
        return
    filtered = [channel for channel in channels if channel["category_label"] == label]
    context = f"cat-{token}"
    await edit(callback, f"<b>📂 {label}</b>\n{len(filtered)} قناة", channels_keyboard(filtered, 1, context))

@router.callback_query(F.data.startswith("list:"))
async def list_page(callback: CallbackQuery):
    await callback.answer()
    _, context, page_text = callback.data.split(":", 2)
    page = int(page_text)
    channels = await require_catalog(callback)
    if not channels:
        return
    if context == "all":
        selected, title = channels, "<b>📡 كل القنوات</b>"
    elif context.startswith("cat-"):
        label = CATEGORY_TOKENS.get(context.removeprefix("cat-"), "")
        selected, title = [item for item in channels if item["category_label"] == label], f"<b>📂 {label}</b>"
    elif context.startswith("search-"):
        term = context.removeprefix("search-")
        selected, title = search_results(channels, term), f"<b>🔍 نتائج: {term}</b>"
    elif context == "fav":
        selected, title = store.favorites(callback.from_user.id), "<b>⭐ المفضلة</b>"
    else:
        selected, title = channels, "<b>📡 كل القنوات</b>"
    await edit(callback, title, channels_keyboard(selected, page, context))

@router.callback_query(F.data == "search")
async def search(callback: CallbackQuery):
    await callback.answer()
    await callback.message.answer("🔍 أرسل اسم القناة أو التصنيف أو الدولة:")
    SEARCHING.add(callback.from_user.id)

SEARCHING: set[int] = set()

@router.message(lambda message: message.from_user.id in SEARCHING)
async def search_message(message: Message):
    SEARCHING.discard(message.from_user.id)
    term = (message.text or "").strip()
    channels = await api.catalog()
    if not channels:
        await message.answer("⏳ لا يزال الفهرس يُبنى. جرّب بعد لحظات.", reply_markup=main_keyboard())
        return
    results = search_results(channels, term)
    context = f"search-{term[:28]}"
    await message.answer(f"<b>🔍 نتائج: {term}</b>\n{len(results)} قناة", reply_markup=channels_keyboard(results, 1, context))

@router.callback_query(F.data == "favorites")
async def favorites(callback: CallbackQuery):
    await callback.answer()
    items = store.favorites(callback.from_user.id)
    if not items:
        await edit(callback, "⭐ لا توجد قنوات في المفضلة.", main_keyboard())
        return
    await edit(callback, "<b>⭐ المفضلة</b>", channels_keyboard(items, 1, "fav"))

@router.callback_query(F.data.startswith("channel:"))
async def channel_details(callback: CallbackQuery):
    await callback.answer("جاري تحديث بيانات القناة…")
    _, channel_id_text, _page, context = callback.data.split(":", 3)
    channel_id = int(channel_id_text)
    # هنا فقط يحدث الرابط والبيانات من المصدر.
    channel = await api.get_channel_fresh(channel_id)
    if not channel:
        await edit(callback, "❌ تعذر تحديث القناة الآن. جرّب لاحقاً.", main_keyboard())
        return
    await edit(callback, details_text(channel), channel_keyboard(callback.from_user.id, channel, context))

@router.callback_query(F.data.startswith("fav:"))
async def favorite(callback: CallbackQuery):
    await callback.answer()
    _, channel_id_text, context = callback.data.split(":", 2)
    channel = await api.get_channel_fresh(int(channel_id_text))
    if not channel:
        await callback.answer("تعذر جلب القناة.", show_alert=True)
        return
    active = store.toggle_favorite(callback.from_user.id, channel)
    await edit(callback, ("✅ أضيفت للمفضلة\n\n" if active else "✅ أزيلت من المفضلة\n\n") + details_text(channel), channel_keyboard(callback.from_user.id, channel, context))

@router.callback_query(F.data == "noop")
async def noop(callback: CallbackQuery):
    await callback.answer()

async def startup() -> None:
    api.load_local_catalog()
    # تُحدّث القائمة من API عند التشغيل؛ الواجهة تعرض الفهرس الكامل لا كاشاً قديماً.
    await api.refresh_catalog_now()

async def shutdown() -> None:
    await api.close()

async def main() -> None:
    await startup()
    try:
        await dp.start_polling(bot, skip_updates=True)
    finally:
        await shutdown()

if __name__ == "__main__":
    asyncio.run(main())
