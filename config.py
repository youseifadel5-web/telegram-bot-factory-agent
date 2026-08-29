# -*- coding: utf-8 -*-
"""
⚙️ إعدادات 𝑌𝑜𝑢𝑠𝑒𝑖𝑓 𝐹𝑖𝑙𝑚𝑠
⚠️ BOT_TOKEN / API_ID / API_HASH تبقى في GitHub Secrets فقط — لا تضعها هنا.
"""

# ── الأدمن ──
# يقرأ ADMIN_ID من Environment / GitHub Secrets. يمكن إبقاء القائمة الفارغة كاحتياطي محلي.
ADMIN_ID = ""
ADMIN_IDS = []

# ── سيرفر Xtream الرئيسي + الاحتياطي ──
IPTV_USERNAME = "465487547"
IPTV_PASSWORD = "2150055510"
IPTV_BASE_URL = "http://fullahd.com:8000"
IPTV_BACKUP_URLS = [
    "http://boxahd.com:8000",
]


# ── 🎞️ TMDB ──
# يفضل وضع القيمتين في GitHub Secrets / Environment:
# TMDB_API_KEY و API_Read_Access_Token
TMDB_API_KEY = ""
API_Read_Access_Token = ""

# ── عرض وأداء ──
ITEMS_PER_PAGE = 10        # عناصر كل صفحة (5–15)
CACHE_DURATION = 600       # كاش بالثواني (10 دقائق)
REQUEST_TIMEOUT = 30
MAX_RETRIES = 3

# ── عام ──
BOT_NAME = "𝑌𝑜𝑢𝑠𝑒𝑖𝑓 𝐹𝑖𝑙𝑚𝑠 🎬"
DB_PATH = "cinema_bot.db"
