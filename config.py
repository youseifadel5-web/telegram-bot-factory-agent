# -*- coding: utf-8 -*-
"""
⚙️ إعدادات 𝑌𝑜𝑢𝑠𝑒𝑖𝑓 𝐹𝑖𝑙𝑚𝑠
⚠️ BOT_TOKEN / API_ID / API_HASH تبقى في GitHub Secrets فقط — لا تضعها هنا.
"""

# ── الأدمن: قائمة فارغة = البوت مفتوح للكل ──
# لتقييد لوحة الأدمن بأشخاص معينين: ADMIN_IDS = [123456789, 987654321]
ADMIN_IDS = []

# ── سيرفر Xtream الرئيسي + الاحتياطي ──
IPTV_USERNAME = "465487547"
IPTV_PASSWORD = "2150055510"
IPTV_BASE_URL = "http://fullahd.com:8000"
IPTV_BACKUP_URLS = [
    "http://boxahd.com:8000",
]

# ── 🎬 المشغل الرسمي (المحرك العالمي) ──
PLAYER_URL = "https://youseifstream.youseif.workers.dev/"

# ── 🔐 حماية روابط المشاهدة (توكن مؤقت) ──
# غيّر هذا النص لأي سلسلة سرية طويلة خاصة بك (تُستخدم لتوقيع الروابط)
LINK_SECRET = "youseif-films-secret-2026"
# مدة صلاحية الرابط بالثواني: 86400 = 24 ساعة
LINK_TTL = 86400

# ── 🎞️ TMDB (اختياري): بوسترات + قصة بالعربية + تقييم ──
# سجّل مجاناً على themoviedb.org → Settings → API → انسخ المفتاح هنا
# لو فاضي: البوت يشتغل عادي ويستخدم بوسترات السيرفر
TMDB_API_KEY = ""

# ── عرض وأداء ──
ITEMS_PER_PAGE = 10        # عناصر كل صفحة (5–15)
CACHE_DURATION = 600       # كاش بالثواني (10 دقائق)
REQUEST_TIMEOUT = 30
MAX_RETRIES = 3

# ── عام ──
BOT_NAME = "𝑌𝑜𝑢𝑠𝑒𝑖𝑓 𝐹𝑖𝑙𝑚𝑠 🎬"
DB_PATH = "cinema_bot.db"
