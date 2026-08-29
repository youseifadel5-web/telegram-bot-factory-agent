# -*- coding: utf-8 -*-
"""
إعدادات اختيارية لبوت السينما Standalone — كل القيم هنا اختيارية
(البوت يشتغل بدونها بقيم افتراضية معقولة). أسرار التليجرام الثلاثة فقط
(BOT_TOKEN / API_ID / API_HASH / ADMIN_ID) تيجي من GitHub Secrets.
"""

# مالك البوت — يفضّل وضعه في GitHub Secret باسم ADMIN_ID
ADMIN_ID = ""

# TMDB
TMDB_API_KEY = ""
API_Read_Access_Token = ""

# عدد العناصر بالصفحة الواحدة في القوائم — 5-20 مثالي
ITEMS_PER_PAGE = 8

# اسم البوت اللي يظهر للمستخدمين في /start و /help
BOT_NAME = "🎬 سينما بوت"

# مسار ملف قاعدة بيانات SQLite (لو غيّرته، استخدم اسم جديد فقط)
DB_PATH = "cinema_bot.db"
