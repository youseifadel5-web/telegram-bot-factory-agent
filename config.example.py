# -*- coding: utf-8 -*-
"""
نسخة مثال من ملف الإعدادات — انسخها إلى config.py وعدّلها:

    cp config.example.py config.py

كل القيم هنا عادية وليست أسرار. القيم الوحيدة اللي تفضل كـ Secrets:
BOT_TOKEN, API_ID, API_HASH.
"""

# الأدمن — لو فاضية، الكل مشرف (للتجربة فقط)
ADMIN_IDS = []

# المصدر الرئيسي
IPTV_USERNAME  = "<iptv-username>"
IPTV_PASSWORD  = "<iptv-password>"
IPTV_BASE_URL  = "http://<host>:8000"
IPTV_BACKUP_URLS = []  # مثال: ["http://<backup1>:8000", "http://<backup2>:8000"]

# المصدر الثانوي (اختياري)
ATLAN_USERNAME = ""
ATLAN_PASSWORD = ""
ATLAN_BASE_URL = ""

# البروكسي (اختياري)
PROXY_URL = ""  # مثال: "https://<worker-domain>"

# الواجهة والأداء
ITEMS_PER_PAGE  = 10
CACHE_DURATION  = 600
MAX_RETRIES     = 3
REQUEST_TIMEOUT = 30
BOT_NAME        = "سينما بوت"

# قاعدة البيانات
DB_PATH = "cinema_bot.db"
