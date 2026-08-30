# -*- coding: utf-8 -*-
"""
إعدادات اختيارية لبوت السينما Standalone — كل القيم هنا اختيارية
(البوت يشتغل بدونها بقيم افتراضية معقولة). أسرار التليجرام الثلاثة فقط
(BOT_TOKEN / API_ID / API_HASH) تيجي من GitHub Secrets.
"""

# عدد العناصر بالصفحة الواحدة في القوائم — 5-20 مثالي
ITEMS_PER_PAGE = 8

# اسم البوت اللي يظهر للمستخدمين في /start و /help
BOT_NAME = "🎬 سينما بوت"

# مسار ملف قاعدة بيانات SQLite (لو غيّرته، استخدم اسم جديد فقط)
DB_PATH = "cinema_bot.db"

# معرف مالك البوت (الأولوية لـ Environment/Secrets ADMIN_ID)
ADMIN_ID = 123456789

# بيانات IPTV
IPTV_USERNAME = "your_username"
IPTV_PASSWORD = "your_password"
IPTV_BASE_URL = "http://example.com:8080"

# TMDB (يمكن وضعها في Secrets بدلاً من الملف)
TMDB_API_KEY = "your_tmdb_api_key_here"
API_Read_Access_Token = "your_tmdb_read_access_token_here"
