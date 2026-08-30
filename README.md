# بوت سينماء — نظام البوتات الخارجي

البوت الأساسي يشغّل Telegram polling واحد فقط. كل بوت فرعي هو **ملف Python واحد** داخل `Add bot/`.

## إضافة بوت
لا تنشئ مجلدًا ولا تعدّل البوت الأساسي.

ضع فقط:

```text
Add bot/MyBot.py
```

أو أي اسم تريده:

```text
Add bot/A.py
Add bot/Movies2026.py
Add bot/Anything.py
```

عند إعادة التشغيل يتم اكتشاف كل ملفات `.py` مباشرة داخل `Add bot/` تلقائيًا.

## الواجهة
- `🎬 بوت سينماء` = قائمة كل البوتات الموجودة في `Add bot/`.
- `🔍 بحث` = بحث موحّد في كل البوتات التي توفر `search(query, context)`.

## ملف البوت الفرعي
أبسط عقدة متوافقة:

```python
PLUGIN_NAME = "اسم البوت"
PLUGIN_BUTTON = "🤖 اسم البوت"


def open_plugin(call, context):
    # افتح واجهة البوت داخل البوت الأساسي
    ...


def handle_callback(call, context):
    ...


def handle_message(update, context):
    ...


def search(query, context):
    # اختياري: إذا أضفته يظهر البوت في البحث الموحد
    ...
```

`PLUGIN_ID` اختياري؛ لو لم تضعه يستخدم اسم الملف.

**ممنوع تشغيل `polling()` أو `getUpdates()` داخل الملف الفرعي.** البوت الأساسي هو المسؤول عن استقبال التحديثات وتوجيهها.

## Secrets
```text
ADMIN_ID
API_HASH
API_ID
BOT_TOKEN
TMDB_API_KEY
```
