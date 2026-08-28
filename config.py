# -*- coding: utf-8 -*-
"""
إعدادات بوت السينما — Xtream Codes API
⚠️ لا تضع هنا BOT_TOKEN / API_ID / API_HASH — هذه تبقى في GitHub Secrets فقط.
"""

# الأدمن — قائمة فارغة = البوت يشتغل مع أي حد (كل المستخدمين أدمن)
# لتقييد الأدمن: ADMIN_IDS = [123456789]
ADMIN_IDS = []

# ── سيرفر Xtream الرئيسي ──
IPTV_USERNAME = "465487547"
IPTV_PASSWORD = "2150055510"
IPTV_BASE_URL = "http://fullahd.com:8000"

# ── سيرفرات احتياطية (يتم التبديل إليها تلقائياً عند فشل الرئيسي) ──
IPTV_BACKUP_URLS = [
    "http://boxahd.com:8000",
]

# ── إعدادات العرض والأداء ──
ITEMS_PER_PAGE = 10        # عدد العناصر في كل صفحة (5–15 مناسب)
CACHE_DURATION = 600       # مدة الكاش بالثواني (10 دقائق)
REQUEST_TIMEOUT = 30       # مهلة الطلب بالثواني
MAX_RETRIES = 3            # عدد محاولات إعادة الاتصال

# ── عام ──
BOT_NAME = "🎬 سينما بوت"
DB_PATH = "cinema_bot.db"
