# 🎬 بوت تيليجرام سينما — Standalone

بوت تيليجرام يتصل بسيرفر Xtream ويعرض الأفلام والمسلسلات والقنوات المباشرة عبر روابط المصدر الأصلية.
ويستخدم SQLite للكاش والمفضلة والإحصائيات.

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
| TMDB_API_KEY  | مفتاح TMDB للبحث والبيانات |
| API_Read_Access_Token | TMDB API Read Access Token (Bearer) |
| ADMIN_ID | Telegram ID لمالك البوت |

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
