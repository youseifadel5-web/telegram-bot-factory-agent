# -*- coding: utf-8 -*-
"""
🎬 بوت تيليجرام سينما — الإصدار الكامل
=========================================
دعم كامل لـ Xtream Codes API:
- قنوات مباشرة (Live TV)
- أفلام (VOD)
- مسلسلات + مواسم + حلقات (Series)
- مصادر متعددة (رئيسي + ثانوي) مع بروكسي اختياري
- كاش ذكي + إعادة محاولة + تبديل سيرفرات تلقائي
- مفضلة / سجل / بحث / عشوائي / لوحة أدمن / بث جماعي

التشغيل:
  1) ضع القيم في متغيرات البيئة (أو انسخ .env.example إلى .env)
  2) pip install -r requirements.txt
  3) python bot.py
"""

import logging
import asyncio
import json
import hashlib
import re
import sqlite3
import html
import os
import sys
import traceback
import random
from datetime import datetime, timedelta
from typing import Optional, Dict, Any, List, Tuple, Union

# تحميل .env اختياري (مفيد للتشغيل المحلي فقط)
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

# ============================================================================
# الإعدادات — فصل صارم:
#   - BOT_TOKEN, API_ID, API_HASH  ← من متغيرات البيئة فقط (GitHub Secrets)
#   - باقي القيم  ← من config.py (يُرفع مع المشروع، يتعدل بسهولة)
# ============================================================================

BOT_TOKEN = os.getenv("BOT_TOKEN", "")
API_ID = int(os.getenv("API_ID", "0") or 0)
API_HASH = os.getenv("API_HASH", "")

# استيراد ملف الإعدادات العادي. لو مش موجود أو فيه خطأ — نقف بوضوح
# بدل ما نخلي البوت يكمل بإعدادات سبتها فاضية.
try:
    import config as _cfg
    ADMIN_IDS         = list(getattr(_cfg, "ADMIN_IDS", []))
    IPTV_USERNAME     = str(getattr(_cfg, "IPTV_USERNAME", ""))
    IPTV_PASSWORD     = str(getattr(_cfg, "IPTV_PASSWORD", ""))
    IPTV_BASE_URL     = str(getattr(_cfg, "IPTV_BASE_URL", "")).rstrip("/")
    _raw_backup       = getattr(_cfg, "IPTV_BACKUP_URLS", []) or []
    IPTV_BACKUP_URLS  = [str(u).strip().rstrip("/") for u in _raw_backup if str(u).strip()]
    ATLAN_USERNAME    = str(getattr(_cfg, "ATLAN_USERNAME", ""))
    ATLAN_PASSWORD    = str(getattr(_cfg, "ATLAN_PASSWORD", ""))
    ATLAN_BASE_URL    = str(getattr(_cfg, "ATLAN_BASE_URL", "")).rstrip("/")
    PROXY_URL         = str(getattr(_cfg, "PROXY_URL", "")).rstrip("/")
    ITEMS_PER_PAGE    = int(getattr(_cfg, "ITEMS_PER_PAGE", 10))
    CACHE_DURATION    = int(getattr(_cfg, "CACHE_DURATION", 600))
    MAX_RETRIES       = int(getattr(_cfg, "MAX_RETRIES", 3))
    REQUEST_TIMEOUT   = int(getattr(_cfg, "REQUEST_TIMEOUT", 30))
    BOT_NAME          = str(getattr(_cfg, "BOT_NAME", "سينما بوت"))
    DB_PATH           = str(getattr(_cfg, "DB_PATH", "cinema_bot.db"))
except ImportError:
    logger_critical = lambda msg: print("❌", msg)
    logger_critical(
        "ملف config.py مش موجود.\n"
        "انسخ config.example.py إلى config.py وعدّل القيم، أو ارفع الكود مع config.py كامل."
    )
    sys.exit(1)

# ============================================================================
# استيراد مكتبة التليجرام
# ============================================================================

try:
    from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
    from telegram.constants import ParseMode
    from telegram.ext import (
        Application, CommandHandler, CallbackQueryHandler,
        MessageHandler, filters, ContextTypes,
    )
    import aiohttp
except ImportError as e:
    print("⚠️ مكتبة ناقصة:", e)
    print("ثبّت المتطلبات بالأمر:")
    print("  pip install -r requirements.txt")
    sys.exit(1)

# ============================================================================
# السجل
# ============================================================================

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

# ============================================================================
# دوال مساعدة
# ============================================================================

def esc(value: Any) -> str:
    if value is None:
        return "غير معروف"
    return html.escape(str(value))


def s(value: Any, default: str = "غير معروف") -> str:
    if value is None or str(value).strip() == "":
        return default
    return str(value)


def truncate(text: str, max_len: int = 120) -> str:
    if not text:
        return ""
    text = str(text)
    return text if len(text) <= max_len else text[: max_len - 3] + "..."


def format_size(size: Any) -> str:
    if size is None:
        return "غير معروف"
    try:
        size = int(size)
        for unit in ["B", "KB", "MB", "GB"]:
            if size < 1024:
                return f"{size:.1f} {unit}"
            size /= 1024
        return f"{size:.1f} GB"
    except Exception:
        return "غير معروف"


def format_duration(seconds: Any) -> str:
    if not seconds:
        return "غير معروف"
    try:
        seconds = int(seconds)
        minutes = seconds // 60
        hours = minutes // 60
        if hours > 0:
            return f"{hours}h {minutes % 60}m"
        return f"{minutes}m"
    except Exception:
        return "غير معروف"


ICONS = {
    "رياضة": "⚽", "فيلم": "🎬", "مسلسل": "📺", "أنمي": "⛩️",
    "مصارعة": "🤼", "أطفال": "🧸", "وثائقي": "📹", "أخبار": "📰",
    "موسيقى": "🎵", "كارتون": "🎨", "ديني": "🕌", "طبخ": "🍳",
    "سياسي": "🏛️", "اقتصاد": "💰", "صحي": "🏥", "علوم": "🔬",
    "طبيعة": "🌿", "حيوانات": "🐾", "مغامرات": "🗺️", "كوميدي": "😂",
    "رومانسي": "💕", "أكشن": "💥", "خيال": "🧙", "رعب": "👻",
    "جريمة": "🔪", "دراما": "🎭", "تاريخي": "📜", "حربي": "⚔️",
    "غربي": "🤠", "عائلي": "👨‍👩‍👧‍👦", "أفلام": "🎬", "مسلسلات": "📺",
}


def get_icon(name: str) -> str:
    name_lower = (name or "").lower()
    for key, icon in ICONS.items():
        if key in name_lower:
            return icon
    return "📡"


def parse_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


# ============================================================================
# قاعدة البيانات (SQLite)
# ============================================================================

class Database:
    def __init__(self, db_path: Optional[str] = None):
        self.db_path = db_path or DB_PATH
        self._init_db()

    def _get_connection(self):
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self):
        conn = self._get_connection()
        cur = conn.cursor()
        cur.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                telegram_id INTEGER UNIQUE NOT NULL,
                username TEXT, first_name TEXT, last_name TEXT,
                language_code TEXT DEFAULT 'ar',
                is_admin INTEGER DEFAULT 0, is_banned INTEGER DEFAULT 0,
                registered_at TEXT DEFAULT CURRENT_TIMESTAMP,
                last_active TEXT DEFAULT CURRENT_TIMESTAMP,
                settings TEXT DEFAULT '{}'
            )
        """)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS favorites (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                content_type TEXT NOT NULL,
                content_id TEXT NOT NULL,
                content_data TEXT NOT NULL,
                added_at TEXT DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(user_id, content_id)
            )
        """)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS watch_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                content_type TEXT NOT NULL,
                content_id TEXT NOT NULL,
                content_data TEXT NOT NULL,
                watched_at TEXT DEFAULT CURRENT_TIMESTAMP,
                progress INTEGER DEFAULT 0
            )
        """)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS statistics (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                stat_type TEXT UNIQUE NOT NULL,
                value INTEGER DEFAULT 0,
                updated_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
        """)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS api_cache (
                key TEXT PRIMARY KEY,
                data TEXT NOT NULL,
                expires_at TEXT NOT NULL
            )
        """)
        for stat in ["total_users", "total_views", "total_messages", "total_searches"]:
            cur.execute(
                "INSERT OR IGNORE INTO statistics (stat_type, value) VALUES (?, 0)",
                (stat,),
            )
        conn.commit()
        conn.close()
        logger.info("✅ قاعدة البيانات جاهزة")

    def add_user(self, telegram_id: int, **kwargs) -> Dict:
        conn = self._get_connection()
        cur = conn.cursor()
        try:
            cur.execute("SELECT * FROM users WHERE telegram_id = ?", (telegram_id,))
            user = cur.fetchone()
            if user:
                cur.execute(
                    "UPDATE users SET last_active = CURRENT_TIMESTAMP, "
                    "username = ?, first_name = ?, last_name = ? WHERE telegram_id = ?",
                    (kwargs.get("username"), kwargs.get("first_name"), kwargs.get("last_name"), telegram_id),
                )
                conn.commit()
                return dict(user)
            cur.execute(
                "INSERT INTO users (telegram_id, username, first_name, last_name, language_code) "
                "VALUES (?, ?, ?, ?, ?)",
                (telegram_id, kwargs.get("username"), kwargs.get("first_name"),
                 kwargs.get("last_name"), kwargs.get("language_code", "ar")),
            )
            cur.execute("UPDATE statistics SET value = value + 1 WHERE stat_type = 'total_users'")
            conn.commit()
            cur.execute("SELECT * FROM users WHERE telegram_id = ?", (telegram_id,))
            return dict(cur.fetchone())
        finally:
            conn.close()

    def get_user(self, telegram_id: int) -> Optional[Dict]:
        conn = self._get_connection()
        cur = conn.cursor()
        try:
            cur.execute("SELECT * FROM users WHERE telegram_id = ?", (telegram_id,))
            row = cur.fetchone()
            return dict(row) if row else None
        finally:
            conn.close()

    def get_all_users(self) -> List[Dict]:
        conn = self._get_connection()
        cur = conn.cursor()
        try:
            cur.execute("SELECT * FROM users WHERE is_banned = 0")
            return [dict(r) for r in cur.fetchall()]
        finally:
            conn.close()

    def add_favorite(self, user_id: int, content_type: str, content_id: str, content_data: Dict):
        conn = self._get_connection()
        cur = conn.cursor()
        try:
            cur.execute(
                "INSERT OR REPLACE INTO favorites (user_id, content_type, content_id, content_data) "
                "VALUES (?, ?, ?, ?)",
                (user_id, content_type, content_id, json.dumps(content_data, ensure_ascii=False)),
            )
            conn.commit()
        finally:
            conn.close()

    def remove_favorite(self, user_id: int, content_id: str):
        conn = self._get_connection()
        cur = conn.cursor()
        try:
            cur.execute("DELETE FROM favorites WHERE user_id = ? AND content_id = ?", (user_id, content_id))
            conn.commit()
        finally:
            conn.close()

    def is_favorite(self, user_id: int, content_id: str) -> bool:
        conn = self._get_connection()
        cur = conn.cursor()
        try:
            cur.execute("SELECT 1 FROM favorites WHERE user_id = ? AND content_id = ?", (user_id, content_id))
            return cur.fetchone() is not None
        finally:
            conn.close()

    def get_favorites(self, user_id: int, content_type: str = None) -> List[Dict]:
        conn = self._get_connection()
        cur = conn.cursor()
        try:
            if content_type:
                cur.execute(
                    "SELECT * FROM favorites WHERE user_id = ? AND content_type = ? ORDER BY added_at DESC",
                    (user_id, content_type),
                )
            else:
                cur.execute("SELECT * FROM favorites WHERE user_id = ? ORDER BY added_at DESC", (user_id,))
            out = []
            for row in cur.fetchall():
                row = dict(row)
                row["content_data"] = json.loads(row["content_data"])
                out.append(row)
            return out
        finally:
            conn.close()

    def add_history(self, user_id: int, content_type: str, content_id: str, content_data: Dict):
        conn = self._get_connection()
        cur = conn.cursor()
        try:
            cur.execute("DELETE FROM watch_history WHERE user_id = ? AND content_id = ?", (user_id, content_id))
            cur.execute(
                "INSERT INTO watch_history (user_id, content_type, content_id, content_data) VALUES (?, ?, ?, ?)",
                (user_id, content_type, content_id, json.dumps(content_data, ensure_ascii=False)),
            )
            cur.execute("UPDATE statistics SET value = value + 1 WHERE stat_type = 'total_views'")
            conn.commit()
        finally:
            conn.close()

    def get_history(self, user_id: int, limit: int = 30) -> List[Dict]:
        conn = self._get_connection()
        cur = conn.cursor()
        try:
            cur.execute(
                "SELECT * FROM watch_history WHERE user_id = ? ORDER BY watched_at DESC LIMIT ?",
                (user_id, limit),
            )
            out = []
            for row in cur.fetchall():
                row = dict(row)
                row["content_data"] = json.loads(row["content_data"])
                out.append(row)
            return out
        finally:
            conn.close()

    def get_statistics(self) -> Dict:
        conn = self._get_connection()
        cur = conn.cursor()
        try:
            stats = {}
            cur.execute("SELECT stat_type, value FROM statistics")
            for row in cur.fetchall():
                stats[row["stat_type"]] = row["value"]
            cur.execute("SELECT COUNT(DISTINCT user_id) FROM favorites")
            stats["total_favorites"] = cur.fetchone()[0] or 0
            cur.execute("SELECT COUNT(*) FROM users")
            stats["total_users_raw"] = cur.fetchone()[0] or 0
            return stats
        finally:
            conn.close()

    def increment_stat(self, stat_type: str):
        conn = self._get_connection()
        cur = conn.cursor()
        try:
            cur.execute("UPDATE statistics SET value = value + 1 WHERE stat_type = ?", (stat_type,))
            conn.commit()
        finally:
            conn.close()

    def save_api_cache(self, key: str, data: Any, duration: int = CACHE_DURATION):
        conn = self._get_connection()
        cur = conn.cursor()
        try:
            expires = (datetime.now() + timedelta(seconds=duration)).isoformat()
            cur.execute(
                "INSERT OR REPLACE INTO api_cache (key, data, expires_at) VALUES (?, ?, ?)",
                (key, json.dumps(data, ensure_ascii=False), expires),
            )
            conn.commit()
        finally:
            conn.close()

    def get_api_cache(self, key: str) -> Optional[Any]:
        conn = self._get_connection()
        cur = conn.cursor()
        try:
            cur.execute("SELECT data, expires_at FROM api_cache WHERE key = ?", (key,))
            row = cur.fetchone()
            if row and datetime.now().isoformat() < row["expires_at"]:
                return json.loads(row["data"])
            return None
        finally:
            conn.close()


# ============================================================================
# عميل الـ API — مصادر متعددة + بروكسي + كاش + تبديل تلقائي
# ============================================================================

import urllib.parse as _urlparse

class APIClient:
    def __init__(self):
        self.sources: Dict[str, Dict[str, Any]] = {}
        if IPTV_BASE_URL:
            self.sources["main"] = {
                "base_url": IPTV_BASE_URL,
                "username": IPTV_USERNAME, "password": IPTV_PASSWORD,
                "use_proxy": False,
            }
        for i, u in enumerate(IPTV_BACKUP_URLS):
            if u:
                self.sources[f"backup_{i}"] = {
                    "base_url": u,
                    "username": IPTV_USERNAME, "password": IPTV_PASSWORD,
                    "use_proxy": False,
                }
        if ATLAN_BASE_URL:
            self.sources["atlan"] = {
                "base_url": ATLAN_BASE_URL,
                "username": ATLAN_USERNAME, "password": ATLAN_PASSWORD,
                "use_proxy": bool(PROXY_URL),
            }
        self.proxy_url = PROXY_URL
        self.session: Optional[aiohttp.ClientSession] = None
        self.db = Database()

    async def _ensure_session(self):
        if self.session is None or self.session.closed:
            self.session = aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=REQUEST_TIMEOUT))

    async def close(self):
        if self.session and not self.session.closed:
            await self.session.close()

    def build_url(self, source: str, kind: str, item_id: int) -> str:
        src = self.sources.get(source) or next(iter(self.sources.values()))
        base = src["base_url"]
        user = src["username"]
        password = src["password"]
        if kind in ("movie",):
            target = f"{base}/movie/{user}/{password}/{item_id}.mkv"
        elif kind in ("series", "episode"):
            target = f"{base}/series/{user}/{password}/{item_id}.mp4"
        else:
            target = f"{base}/live/{user}/{password}/{item_id}.ts"
        if src.get("use_proxy") and self.proxy_url:
            return f"{self.proxy_url}?url={_urlparse.quote(target, safe='')}"
        return target

    async def _request(self, action: str, params: Optional[Dict] = None,
                       source: Optional[str] = None) -> Any:
        if params is None:
            params = {}
        sources = list(self.sources.keys())
        if source and source in self.sources:
            sources = [source] + [s for s in sources if s != source]

        cache_key = hashlib.md5(
            f"{action}|{json.dumps(params, sort_keys=True, ensure_ascii=False)}".encode()
        ).hexdigest()
        cached = self.db.get_api_cache(cache_key)
        if cached is not None:
            return cached

        await self._ensure_session()

        for src_name in sources:
            src = self.sources[src_name]
            base = src["base_url"]
            user = src.get("username", "")
            password = src.get("password", "")
            proxy = bool(src.get("use_proxy"))
            p = dict(params)
            p.setdefault("username", user)
            p.setdefault("password", password)
            p["action"] = action

            base_url = f"{base}/player_api.php"
            if proxy and self.proxy_url:
                inner = f"{base_url}?{_urlparse.urlencode(p)}"
                request_url = f"{self.proxy_url}?url={_urlparse.quote(inner, safe='')}"
            else:
                request_url = base_url

            for attempt in range(1, MAX_RETRIES + 1):
                try:
                    async with self.session.get(request_url, params=None if proxy else p) as resp:
                        if resp.status == 200:
                            try:
                                data = await resp.json(content_type=None)
                            except Exception:
                                text = await resp.text()
                                try:
                                    data = json.loads(text)
                                except Exception:
                                    data = []
                            self.db.save_api_cache(cache_key, data)
                            return data
                except asyncio.CancelledError:
                    raise
                except Exception as e:
                    logger.warning(f"⚠️ محاولة {attempt}/{MAX_RETRIES} لـ {src_name}: {e}")
                    await asyncio.sleep(2 ** (attempt - 1))
        return []

    @staticmethod
    def normalize(data: Any) -> List[Dict]:
        if isinstance(data, list):
            return [x for x in data if isinstance(x, dict)]
        if isinstance(data, dict):
            if isinstance(data.get("data"), list):
                return [x for x in data["data"] if isinstance(x, dict)]
            if isinstance(data.get("episodes"), list):
                return [x for x in data["episodes"] if isinstance(x, dict)]
            if data.get("info") or data.get("seasons") or data.get("episodes"):
                return [data]
            if data:
                return [data]
        return []

    async def get_live_categories(self) -> List[Dict]:
        return self.normalize(await self._request("get_live_categories"))

    async def get_live_streams(self, category_id: Optional[int] = None) -> List[Dict]:
        params = {}
        if category_id:
            params["category_id"] = str(category_id)
        return self.normalize(await self._request("get_live_streams", params))

    async def get_vod_categories(self) -> List[Dict]:
        return self.normalize(await self._request("get_vod_categories"))

    async def get_vod_streams(self, category_id: Optional[int] = None) -> List[Dict]:
        params = {}
        if category_id:
            params["category_id"] = str(category_id)
        return self.normalize(await self._request("get_vod_streams", params))

    async def get_series_categories(self) -> List[Dict]:
        return self.normalize(await self._request("get_series_categories"))

    async def get_series(self, category_id: Optional[int] = None) -> List[Dict]:
        params = {}
        if category_id:
            params["category_id"] = str(category_id)
        return self.normalize(await self._request("get_series", params))

    async def get_series_info(self, series_id: int) -> Dict:
        data = self.normalize(await self._request("get_series_info", {"series_id": str(series_id)}))
        return data[0] if data else {}

    async def search_all(self, query: str) -> Dict[str, List]:
        q = query.lower().strip()
        live, movies, series = [], [], []
        try:
            live, movies, series = await asyncio.gather(
                self.get_live_streams(), self.get_vod_streams(), self.get_series()
            )
        except Exception as e:
            logger.error(f"البحث الشامل فشل جزئيًا: {e}")
        results = {"live": [], "movies": [], "series": []}
        if not q:
            return results
        for item in live:
            if q in str(item.get("name", "")).lower():
                results["live"].append(item)
        for item in movies:
            if q in str(item.get("name", "")).lower():
                results["movies"].append(item)
        for item in series:
            if q in str(item.get("name", "")).lower() or q in str(item.get("alias", "")).lower():
                results["series"].append(item)
        return results


# ============================================================================
# البوت الرئيسي — المعالجات
# ============================================================================

def is_admin(user_id: int) -> bool:
    return (not ADMIN_IDS) or user_id in ADMIN_IDS


class CinemaBot:
    def __init__(self):
        self.db = Database()
        self.client = APIClient()
        self._initialized = False

    async def initialize(self):
        if self._initialized:
            return
        try:
            live = await self.client.get_live_categories()
            vod = await self.client.get_vod_categories()
            series = await self.client.get_series_categories()
            logger.info(f"✅ تهيئة: {len(live)} قناة / {len(vod)} فيلم / {len(series)} مسلسل")
        except Exception as e:
            logger.error(f"❌ تهيئة جزئية: {e}")
        self._initialized = True

    async def get_main_menu(self) -> InlineKeyboardMarkup:
        kb = []
        try:
            live = await self.client.get_live_categories()
            vod = await self.client.get_vod_categories()
            series = await self.client.get_series_categories()
            if live:
                kb.append([InlineKeyboardButton("📡 القنوات المباشرة", callback_data="menu_live")])
            if vod:
                kb.append([InlineKeyboardButton("🎬 الأفلام", callback_data="menu_movies")])
            if series:
                kb.append([InlineKeyboardButton("📺 المسلسلات", callback_data="menu_series")])
        except Exception as e:
            logger.error(f"خطأ ببناء القائمة: {e}")
        kb.append([
            InlineKeyboardButton("🔍 بحث", callback_data="menu_search"),
            InlineKeyboardButton("❤️ مفضلة", callback_data="menu_favorites"),
        ])
        kb.append([
            InlineKeyboardButton("🕒 سجل", callback_data="menu_history"),
            InlineKeyboardButton("🎲 عشوائي", callback_data="menu_random"),
        ])
        kb.append([InlineKeyboardButton("⚙️ إعدادات", callback_data="menu_settings")])
        return InlineKeyboardMarkup(kb)

    async def show_categories(self, query, category_type: str):
        try:
            if category_type == "live":
                cats = await self.client.get_live_categories()
                title, prefix = "📡 تصنيفات القنوات المباشرة", "live_cat"
            elif category_type == "movies":
                cats = await self.client.get_vod_categories()
                title, prefix = "🎬 تصنيفات الأفلام", "vod_cat"
            else:
                cats = await self.client.get_series_categories()
                title, prefix = "📺 تصنيفات المسلسلات", "series_cat"
            if not cats:
                return await query.edit_message_text(
                    "❌ لا توجد تصنيفات.",
                    reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 رجوع", callback_data="menu_back")]]),
                )
            kb = []
            for c in cats:
                name = c.get("category_name") or c.get("name") or "قسم"
                cid = parse_int(c.get("category_id") or c.get("id"), 0)
                count = parse_int(c.get("stream_count") or c.get("count"), 0)
                label = f"{get_icon(name)} {esc(name)}"
                if count:
                    label += f" ({count})"
                kb.append([InlineKeyboardButton(label, callback_data=f"{prefix}_{cid}")])
            kb.append([InlineKeyboardButton("🔙 رجوع", callback_data="menu_back")])
            await query.edit_message_text(
                f"**{title}**\nاختر التصنيف:",
                reply_markup=InlineKeyboardMarkup(kb),
                parse_mode=ParseMode.MARKDOWN,
            )
        except Exception as e:
            logger.error(f"خطأ بالتصنيفات: {e}")
            await query.edit_message_text(
                "❌ حدث خطأ، حاول مجددًا.",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 رجوع", callback_data="menu_back")]]),
            )

    async def show_items(self, query, context, items: List[Dict], title: str, item_type: str, page: int = 0):
        if not items:
            return await query.edit_message_text(
                "❌ لا توجد عناصر.",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 رجوع", callback_data="menu_back")]]),
            )
        total = len(items)
        per_page = ITEMS_PER_PAGE
        total_pages = max(1, (total + per_page - 1) // per_page)
        page = max(0, min(page, total_pages - 1))
        start, end = page * per_page, min((page + 1) * per_page, total)
        page_items = items[start:end]
        kb = []
        for it in page_items:
            name = esc(it.get("name") or it.get("title") or "عنصر")
            iid = it.get("stream_id") or it.get("series_id") or it.get("id") or 0
            stype = it.get("_stype") or item_type
            if len(name) > 42:
                name = name[:39] + "..."
            icon = "🎬" if stype == "movie" else ("📺" if stype == "series" else "📡")
            kb.append([InlineKeyboardButton(f"{icon} {name}", callback_data=f"view_{stype}_{iid}")])
        nav = []
        if page > 0:
            nav.append(InlineKeyboardButton("⬅️", callback_data=f"page_{page-1}"))
        nav.append(InlineKeyboardButton(f"📄 {page+1}/{total_pages}", callback_data="page_info"))
        if page < total_pages - 1:
            nav.append(InlineKeyboardButton("➡️", callback_data=f"page_{page+1}"))
        if nav:
            kb.append(nav)
        kb.append([InlineKeyboardButton("🔙 رجوع", callback_data="menu_back")])
        context.user_data["current_items"] = items
        context.user_data["current_title"] = title
        context.user_data["current_page"] = page
        context.user_data["item_type"] = item_type
        await query.edit_message_text(
            f"**{title}** ({page+1}/{total_pages}) — {total} عنصر",
            reply_markup=InlineKeyboardMarkup(kb),
            parse_mode=ParseMode.MARKDOWN,
        )

    async def show_details(self, query, context, item: Dict, item_type: str, source: str = "main"):
        name = esc(item.get("name") or item.get("title") or "عنصر")
        iid = item.get("stream_id") or item.get("series_id") or item.get("id") or 0
        text = f"🎬 **{name}**\n\n"
        fields = [
            ("التصنيف", item.get("category_name")),
            ("السنة", item.get("year") or item.get("release_date")),
            ("التقييم", item.get("rating")),
            ("المدة", item.get("duration")),
            ("الجودة", item.get("quality")),
            ("الحجم", format_size(item.get("size"))),
            ("اللغة", item.get("language")),
            ("القصة", item.get("description") or item.get("plot") or item.get("story")),
        ]
        for label, value in fields:
            if value and str(value).strip():
                v = esc(truncate(str(value).strip(), 180))
                text += f"**{label}:** {v}\n"
        kb = []
        if item_type == "series":
            url = self.client.build_url(source, "series", iid)
            kb.append([
                InlineKeyboardButton("📺 الحلقات", callback_data=f"episodes_{iid}"),
                InlineKeyboardButton("▶️ تشغيل", url=url),
            ])
        elif item_type == "movie":
            url = self.client.build_url(source, "movie", iid)
            kb.append([
                InlineKeyboardButton("▶️ مشاهدة", url=url),
                InlineKeyboardButton("📥 تحميل", url=url),
            ])
        else:
            url = self.client.build_url(source, "live", iid)
            kb.append([InlineKeyboardButton("▶️ مشاهدة مباشرة", url=url)])
        kb.append([
            InlineKeyboardButton("❤️ مفضلة", callback_data=f"fav_toggle_{item_type}_{iid}"),
            InlineKeyboardButton("🔙 رجوع", callback_data="menu_back"),
        ])
        self.db.add_history(query.from_user.id, item_type, str(iid), {"name": name, "type": item_type})
        await query.edit_message_text(
            text, reply_markup=InlineKeyboardMarkup(kb),
            parse_mode=ParseMode.MARKDOWN, disable_web_page_preview=True,
        )

    async def show_episodes(self, query, series_id: int):
        try:
            info = await self.client.get_series_info(series_id)
            series_name = esc(info.get("name") or "المسلسل")
            raw_eps = info.get("episodes") or {}
            ep_list = []
            if isinstance(raw_eps, dict):
                for season_num in sorted(raw_eps.keys(), key=lambda x: parse_int(x, 0)):
                    for ep in raw_eps[season_num] or []:
                        ep["season"] = season_num
                        ep_list.append(ep)
            elif isinstance(raw_eps, list):
                ep_list = raw_eps
            if not ep_list:
                ep_list = self.client.normalize(
                    await self.client._request("get_series_episodes", {"series_id": str(series_id)})
                )
            if not ep_list:
                return await query.edit_message_text(
                    f"❌ لا توجد حلقات لـ {series_name}",
                    reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 رجوع", callback_data="menu_back")]]),
                )
            kb = []
            for ep in ep_list[:50]:
                ep_num = ep.get("episode_num") or ep.get("num") or 0
                ep_name = esc(ep.get("title") or ep.get("name") or f"حلقة {ep_num}")
                eid = ep.get("id") or 0
                kb.append([InlineKeyboardButton(f"▶️ {ep_name}", callback_data=f"watch_episode_{eid}_{series_id}")])
            kb.append([InlineKeyboardButton("🔙 رجوع", callback_data="menu_back")])
            await query.edit_message_text(
                f"📺 **{series_name}** — الحلقات ({len(ep_list)})",
                reply_markup=InlineKeyboardMarkup(kb),
                parse_mode=ParseMode.MARKDOWN,
            )
        except Exception as e:
            logger.error(f"خطأ بالحلقات: {e}")
            await query.edit_message_text(
                "❌ حدث خطأ.",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 رجوع", callback_data="menu_back")]]),
            )

    async def start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        user = update.effective_user
        self.db.add_user(user.id, username=user.username, first_name=user.first_name, last_name=user.last_name)
        self.db.increment_stat("total_messages")
        await self.initialize()
        kb = await self.get_main_menu()
        await update.message.reply_text(
            f"🎬 **مرحبًا بك في {BOT_NAME}!**\n\n"
            "📡 مشاهدة:\n"
            "• 📡 القنوات المباشرة\n"
            "• 🎬 الأفلام\n"
            "• 📺 المسلسلات والحلقات\n\n"
            "🔽 اختر القسم:",
            reply_markup=kb, parse_mode=ParseMode.MARKDOWN,
        )

    async def help_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        self.db.increment_stat("total_messages")
        await update.message.reply_text(
            "📖 **المساعدة**\n\n"
            "📡 القنوات — البث المباشر\n"
            "🎬 الأفلام — استعراض وتشغيل\n"
            "📺 المسلسلات — مواسم وحلقات\n"
            "🔍 بحث — ابحث بالاسم\n"
            "❤️ مفضلة — محتواك المحفوظ\n"
            "🕒 سجل — آخر المشاهدات\n"
            "🎲 عشوائي — اقتراح سريع\n\n"
            "👑 /admin — لوحة الإدارة (للمشرفين)",
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 القائمة الرئيسية", callback_data="menu_back")]]),
        )

    async def admin_panel(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not is_admin(update.effective_user.id):
            return await update.message.reply_text("❌ غير مصرح لك.")
        stats = self.db.get_statistics()
        await update.message.reply_text(
            "👑 **لوحة الإدارة**\n\n"
            f"👤 المستخدمون: {stats.get('total_users', 0)}\n"
            f"📊 المشاهدات: {stats.get('total_views', 0)}\n"
            f"💬 الرسائل: {stats.get('total_messages', 0)}\n"
            f"🔍 عمليات البحث: {stats.get('total_searches', 0)}\n"
            f"❤️ المفضلة: {stats.get('total_favorites', 0)}\n\n"
            "أوامر الإدارة:\n"
            "/broadcast <رسالة> — بث جماعي\n"
            "/stats — إحصائيات",
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("📣 بث رسالة", callback_data="admin_broadcast")],
                [InlineKeyboardButton("🔙 رجوع", callback_data="menu_back")],
            ]),
        )

    async def broadcast_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not is_admin(update.effective_user.id):
            return await update.message.reply_text("❌ غير مصرح لك.")
        text = " ".join(context.args) if context.args else ""
        if not text:
            return await update.message.reply_text("استخدم: /broadcast <الرسالة>")
        users = self.db.get_all_users()
        ok, fail = 0, 0
        for u in users:
            try:
                await context.bot.send_message(u["telegram_id"], f"📢 **إعلان**\n\n{text}", parse_mode=ParseMode.MARKDOWN)
                ok += 1
            except Exception:
                fail += 1
            await asyncio.sleep(0.05)
        await update.message.reply_text(f"✅ تم الإرسال لـ {ok} مستخدمين، فشل {fail}.")

    async def handle_menu(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        query = update.callback_query
        await query.answer()
        self.db.increment_stat("total_messages")
        await self.initialize()
        menu_id = query.data.replace("menu_", "")
        if menu_id == "back":
            kb = await self.get_main_menu()
            return await query.edit_message_text("🎬 **القائمة الرئيسية**", reply_markup=kb, parse_mode=ParseMode.MARKDOWN)
        if menu_id == "live":
            return await self.show_categories(query, "live")
        if menu_id == "movies":
            return await self.show_categories(query, "movies")
        if menu_id == "series":
            return await self.show_categories(query, "series")
        if menu_id == "search":
            context.user_data["search_mode"] = True
            return await query.edit_message_text(
                "🔍 **البحث**\n\nأرسل كلمة البحث أو اسم الفيلم/المسلسل:",
                parse_mode=ParseMode.MARKDOWN,
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 رجوع", callback_data="menu_back")]]),
            )
        if menu_id == "favorites":
            return await self.show_favorites(query, context)
        if menu_id == "history":
            return await self.show_history(query, context)
        if menu_id == "random":
            return await self.show_random(query, context)
        if menu_id == "settings":
            return await self.show_settings(query)

    async def handle_category(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        query = update.callback_query
        await query.answer()
        parts = query.data.split("_", 2)
        if len(parts) < 3:
            return
        cat_type = f"{parts[0]}_{parts[1]}"
        cat_id = parse_int(parts[2], 0)
        try:
            if cat_type == "live_cat":
                items = await self.client.get_live_streams(cat_id)
                await self.show_items(query, context, items, "📡 القنوات المباشرة", "live", 0)
            elif cat_type == "vod_cat":
                items = await self.client.get_vod_streams(cat_id)
                await self.show_items(query, context, items, "🎬 الأفلام", "movie", 0)
            elif cat_type == "series_cat":
                items = await self.client.get_series(cat_id)
                await self.show_items(query, context, items, "📺 المسلسلات", "series", 0)
        except Exception as e:
            logger.error(f"خطأ بالتصنيف: {e}")
            await query.edit_message_text(
                "❌ حدث خطأ.",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 رجوع", callback_data="menu_back")]]),
            )

    async def handle_view(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        query = update.callback_query
        await query.answer()
        parts = query.data.replace("view_", "").split("_", 1)
        if len(parts) != 2:
            return
        item_type, item_id = parts
        items = context.user_data.get("current_items", [])
        item = None
        for i in items:
            iid = str(i.get("stream_id") or i.get("series_id") or i.get("id") or "")
            if iid == item_id:
                item = i
                break
        if not item:
            return await query.edit_message_text(
                "❌ العنصر غير موجود.",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 رجوع", callback_data="menu_back")]]),
            )
        await self.show_details(query, context, item, item_type)

    async def handle_episodes(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        query = update.callback_query
        await query.answer()
        try:
            series_id = parse_int(query.data.replace("episodes_", ""), 0)
        except ValueError:
            return
        await self.show_episodes(query, series_id)

    async def handle_watch_episode(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        query = update.callback_query
        await query.answer()
        parts = query.data.replace("watch_episode_", "").split("_")
        if len(parts) < 2:
            return
        ep_id, series_id = parts[0], parts[1]
        url = self.client.build_url("main", "episode", parse_int(ep_id, 0))
        self.db.add_history(query.from_user.id, "series", series_id, {"name": f"حلقة {ep_id}", "type": "series"})
        await query.edit_message_text(
            f"▶️ **جاري التشغيل…**\n\n🔗 [اضغط هنا للمشاهدة]({url})",
            parse_mode=ParseMode.MARKDOWN, disable_web_page_preview=True,
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 رجوع", callback_data="menu_back")]]),
        )

    async def handle_page(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        query = update.callback_query
        await query.answer()
        try:
            page = parse_int(query.data.replace("page_", ""), 0)
        except ValueError:
            return
        items = context.user_data.get("current_items", [])
        title = context.user_data.get("current_title", "العناصر")
        item_type = context.user_data.get("item_type", "live")
        await self.show_items(query, context, items, title, item_type, page)

    async def show_favorites(self, query, context):
        favs = self.db.get_favorites(query.from_user.id)
        if not favs:
            return await query.edit_message_text(
                "❤️ **المفضلة**\n\nلا توجد عناصر بعد.",
                parse_mode=ParseMode.MARKDOWN,
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 رجوع", callback_data="menu_back")]]),
            )
        items = [f["content_data"] for f in favs]
        await self.show_items(query, context, items, "❤️ المفضلة", "favorite", 0)

    async def handle_favorite_toggle(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        query = update.callback_query
        await query.answer()
        parts = query.data.replace("fav_toggle_", "").split("_", 1)
        if len(parts) != 2:
            return
        item_type, item_id = parts
        user_id = query.from_user.id
        items = context.user_data.get("current_items", [])
        item = next((i for i in items if str(i.get("stream_id") or i.get("series_id") or i.get("id") or "") == item_id), None)
        if not item:
            return await query.answer("❌ العنصر غير موجود")
        if self.db.is_favorite(user_id, item_id):
            self.db.remove_favorite(user_id, item_id)
            await query.answer("🗑️ أُزيل من المفضلة")
        else:
            self.db.add_favorite(user_id, item_type, item_id, item)
            await query.answer("❤️ أُضيف إلى المفضلة")

    async def show_history(self, query, context):
        hist = self.db.get_history(query.from_user.id)
        if not hist:
            return await query.edit_message_text(
                "🕒 **سجل المشاهدة**\n\nلا توجد مشاهدات.",
                parse_mode=ParseMode.MARKDOWN,
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 رجوع", callback_data="menu_back")]]),
            )
        items = [h["content_data"] for h in hist]
        await self.show_items(query, context, items, "🕒 سجل المشاهدة", "history", 0)

    async def show_random(self, query, context):
        try:
            all_items = []
            live, movies, series = await asyncio.gather(
                self.client.get_live_streams(), self.client.get_vod_streams(), self.client.get_series()
            )
            all_items.extend(live or [])
            all_items.extend(movies or [])
            all_items.extend(series or [])
            if not all_items:
                return await query.edit_message_text(
                    "❌ لا توجد محتويات.",
                    reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 رجوع", callback_data="menu_back")]]),
                )
            item = random.choice(all_items)
            if "series_id" in item:
                item_type = "series"
            elif "stream_id" in item:
                item_type = "movie"
            else:
                item_type = "live"
            await self.show_details(query, context, item, item_type)
        except Exception as e:
            logger.error(f"خطأ بالعشوائي: {e}")
            await query.edit_message_text(
                "❌ حدث خطأ.",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 رجوع", callback_data="menu_back")]]),
            )

    async def show_settings(self, query):
        await query.edit_message_text(
            "⚙️ **الإعدادات**\n\n"
            f"📊 العناصر بالصفحة: {ITEMS_PER_PAGE}\n"
            f"⏱️ مدة الكاش: {CACHE_DURATION} ثانية",
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 رجوع", callback_data="menu_back")]]),
        )

    async def handle_admin_broadcast_button(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        query = update.callback_query
        await query.answer("استخدم الأمر: /broadcast <الرسالة>", show_alert=True)

    async def search_text(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not context.user_data.get("search_mode"):
            return
        q = (update.message.text or "").strip()
        if not q:
            return
        context.user_data["search_mode"] = False
        self.db.increment_stat("total_searches")
        waiting = await update.message.reply_text("🔍 **جاري البحث…**", parse_mode=ParseMode.MARKDOWN)
        try:
            results = await self.client.search_all(q)
            combined = []
            for it in results.get("live", []):
                it["_stype"] = "live"
                combined.append(it)
            for it in results.get("movies", []):
                it["_stype"] = "movie"
                combined.append(it)
            for it in results.get("series", []):
                it["_stype"] = "series"
                combined.append(it)
            if not combined:
                await waiting.delete()
                return await update.message.reply_text(
                    f"❌ لا توجد نتائج لـ **{esc(q)}**",
                    parse_mode=ParseMode.MARKDOWN,
                    reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 رجوع", callback_data="menu_back")]]),
                )
            await waiting.delete()
            await self.send_items_message(
                update.effective_chat.id, context, combined,
                f"نتائج البحث: {esc(q)}", "movie", 0,
            )
        except Exception as e:
            logger.error(f"خطأ بالبحث: {e}")
            await waiting.edit_text(
                "❌ حدث خطأ أثناء البحث.",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 رجوع", callback_data="menu_back")]]),
            )

    async def send_items_message(self, chat_id, context, items, title, item_type, page=0):
        if not items:
            return
        total = len(items)
        per_page = ITEMS_PER_PAGE
        total_pages = max(1, (total + per_page - 1) // per_page)
        page = max(0, min(page, total_pages - 1))
        start, end = page * per_page, min((page + 1) * per_page, total)
        page_items = items[start:end]
        kb = []
        for it in page_items:
            name = esc(it.get("name") or it.get("title") or "عنصر")
            iid = it.get("stream_id") or it.get("series_id") or it.get("id") or 0
            stype = it.get("_stype") or item_type
            if len(name) > 42:
                name = name[:39] + "..."
            icon = "🎬" if stype == "movie" else ("📺" if stype == "series" else "📡")
            kb.append([InlineKeyboardButton(f"{icon} {name}", callback_data=f"view_{stype}_{iid}")])
        nav = []
        if page > 0:
            nav.append(InlineKeyboardButton("⬅️", callback_data=f"page_{page-1}"))
        nav.append(InlineKeyboardButton(f"📄 {page+1}/{total_pages}", callback_data="page_info"))
        if page < total_pages - 1:
            nav.append(InlineKeyboardButton("➡️", callback_data=f"page_{page+1}"))
        if nav:
            kb.append(nav)
        kb.append([InlineKeyboardButton("🔙 رجوع", callback_data="menu_back")])
        context.user_data["current_items"] = items
        context.user_data["current_title"] = title
        context.user_data["current_page"] = page
        context.user_data["item_type"] = item_type
        await context.bot.send_message(
            chat_id,
            f"**{title}** ({page+1}/{total_pages}) — {total} عنصر",
            reply_markup=InlineKeyboardMarkup(kb),
            parse_mode=ParseMode.MARKDOWN,
        )


# ============================================================================
# نقطة التشغيل
# ============================================================================

def make_app() -> Application:
    if not BOT_TOKEN or not API_ID or not API_HASH:
        logger.error(
            "❌ واحد من الـ Secrets ناقص: BOT_TOKEN / API_ID / API_HASH.\n"
            "ضع القيمة في GitHub Secrets (أو في .env للتشغيل المحلي)."
        )
        sys.exit(1)
    if not IPTV_USERNAME or not IPTV_PASSWORD or not IPTV_BASE_URL:
        logger.error(
            "❌ بيانات IPTV ناقصة في config.py.\n"
            "افتح config.py وعدّل: IPTV_USERNAME / IPTV_PASSWORD / IPTV_BASE_URL."
        )
        sys.exit(1)
    app = Application.builder().token(BOT_TOKEN).build()
    bot = CinemaBot()
    app.bot_data["cinema"] = bot
    app.add_handler(CommandHandler("start", bot.start))
    app.add_handler(CommandHandler("help", bot.help_command))
    app.add_handler(CommandHandler("admin", bot.admin_panel))
    app.add_handler(CommandHandler("stats", bot.admin_panel))
    app.add_handler(CommandHandler("broadcast", bot.broadcast_command))
    app.add_handler(CallbackQueryHandler(bot.handle_menu, pattern=r"^menu_"))
    app.add_handler(CallbackQueryHandler(bot.handle_category, pattern=r"^(live_cat|vod_cat|series_cat)_"))
    app.add_handler(CallbackQueryHandler(bot.handle_view, pattern=r"^view_"))
    app.add_handler(CallbackQueryHandler(bot.handle_episodes, pattern=r"^episodes_"))
    app.add_handler(CallbackQueryHandler(bot.handle_watch_episode, pattern=r"^watch_episode_"))
    app.add_handler(CallbackQueryHandler(bot.handle_page, pattern=r"^page_\d+$"))
    app.add_handler(CallbackQueryHandler(bot.handle_favorite_toggle, pattern=r"^fav_toggle_"))
    app.add_handler(CallbackQueryHandler(bot.handle_admin_broadcast_button, pattern=r"^admin_broadcast$"))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, bot.search_text))
    return app


def main():
    logging.getLogger("httpx").setLevel(logging.WARNING)
    app = make_app()
    logger.info("🚀 بوت السينما يعمل الآن…")
    app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()
