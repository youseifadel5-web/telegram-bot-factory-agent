# 🎬 بوت تيليجرام سينما — Standalone

بوت تيليجرام يشتغل بدون أي خادم IPTV خارجي. كل المحتوى محفوظ في SQLite
مع بيانات جاهزة (تصنيفات وأفلام ومسلسلات وقنوات مباشرة).

## ✨ المزايا

- 🎬 تصفح الأفلام حسب التصنيف مع pagination
- 📺 تصفح المسلسلات (مع عدد المواسم والحلقات)
- 📡 القنوات المباشرة (يفتح رابط البث)
- 🔍 بحث بالعنوان أو الوصف
- 🎲 اقتراح عشوائي
- ❤️ المفضلة (لكل مستخدم)
- 👑 أوامر الأدمن: `/add`, `/addcat`, `/stats`

## 🚀 التشغيل

### الأسرار في GitHub (Settings → Secrets and variables → Actions)
أضف هذه الـ Secrets فقط (لا تضع المفاتيح داخل الملفات):

| Name          | Source                                      |
|---------------|---------------------------------------------|
| BOT_TOKEN     | من @BotFather على تيليجرام                  |
| API_ID        | من my.telegram.org                          |
| API_HASH      | من my.telegram.org                          |
| TMDB_API_KEY  | من themoviedb.org → Settings → API (اختياري للبوسترات) |

### خطوات الرفع

1. ارفع الملفات كلها على الريبو (ارفع `config.py` أو أنشئه داخل GitHub بالقيم أعلاه).
2. Actions → "تشغيل بوت السينما" → **Run workflow**.
3. افتح تيليجرام وأرسل `/start`.

### محتويات الريبو

```
cinema-bot/
├── bot.py              # البوت الرئيسي (يقرأ 3 أسرار فقط)
├── config.py           # إعدادات اختيارية (3 قيم فقط)
├── config.example.py   # قالب لـ config.py
├── .env.example        # استخدام محلي فقط
├── .gitignore          # يمنع رفع .env و cinema_bot.db
├── requirements.txt    # python-telegram-bot
└── .github/workflows/bot.yml
```
