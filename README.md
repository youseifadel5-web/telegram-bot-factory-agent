# Unified Telegram Bot

## الهيكل
- `bot.py` هو البوت الأساسي والـpolling الوحيد (Token واحد).
- `Add bot/` هو المكان الوحيد لإضافة البوتات الفرعية.
- كل ملف `.py` مباشر داخل `Add bot/` يُحمَّل تلقائيًا كبوت فرعي. اسم الملف لا يهم.
- لا تحتاج لإنشاء مجلد أو ملف إعداد إضافي للبوت الفرعي.
- بعد وضع الملف: من لوحة الأدمن → **إدارة البوتات** → **إعادة تحميل البوتات** (أو أعد تشغيل الخدمة).

## البوابة
- `🎬 بوت سينماء`: يعرض كل البوتات **المفعّلة** الموجودة في `Add bot/`.
- `🔍 بحث`: يبحث في كل البوتات المفعّلة التي توفر hook باسم `search`.
- `👑 لوحة التحكم`: تظهر للـ`ADMIN_ID` فقط في البوابة الخارجية، وتشمل:
  - إحصائيات / كاش / باسورد الكبار / رسالة جماعية (نظام يوسف)
  - **إدارة البوتات**: تفعيل/إيقاف أي بوت مكتشف + إعادة تحميل قائمة `Add bot/`

## طريقة إضافة بوت جديد
1. أنشئ ملفًا مثل `Add bot/MyBot.py` (بدون polling).
2. وفّر على الأقل:
   ```python
   PLUGIN_ID = "mybot"
   PLUGIN_NAME = "بوت تجريبي"
   PLUGIN_BUTTON = "🤖 بوت تجريبي"

   def open_plugin(call, context):
       # افتح واجهتك أو أرجع مسارًا معروفًا للمضيف
       # أمثلة جاهزة:
       # return "youseif"              # واجهة يوسف فيلم
       # return "cinema:hub_nova"      # واجهة سينما نوفا
       return "cinema:hub_orion"

   def handle_callback(call, context):
       # اختياري — إن كان البوت يعتمد على cinema_core
       return bool(context["cinema"].handle_callbacks(call))

   def handle_message(update, context):
       return False

   def search(query, context):
       # اختياري — للبحث الموحد
       return {"movie": [], "series": []}
   ```
3. من لوحة الأدمن اضغط **إعادة تحميل البوتات** ثم فعّله إن لزم.

> مهم: ملف البوت الفرعي **لا يجب** أن يبدأ `polling` أو `run_polling()` بنفسه.

## الأنظمة المدمجة
- **سينما نوفا / أوريون بلس**: عبر `cinema_core.py` + ملفات الإضافة في `Add bot/`.
- **Youseif Films**: عبر `youseif_core.py` + `Add bot/Youseif_Films.py` (بدون polling مستقل).

## الأسرار
```env
ADMIN_ID=
API_HASH=
API_ID=
BOT_TOKEN=
TMDB_API_KEY=
```

إعدادات IPTV/العرض تبقى في `config.py`.
