# Youseif Streaming Bot (KataBump)

بوت تيليجرام متقدم للبث المباشر (RTMP + FFmpeg)، السينما، المسلسلات، IPTV، رفع الملفات إلى Cloudflare R2، الأرشفة، والمكتبة الصوتية.

**الإصدار:** BOT_ONLY (محسّن)

---

## المميزات الرئيسية

- 📡 **بث مباشر** عبر RTMP (يوتيوب، تليجرام لايف، فيسبوك...) مع دعم HLS / HTTP / Google Drive
- 🎬 **سينما ومسلسلات** عبر مصادر متعددة (Oscar وغيرها)
- 📺 **IPTV** مع قوائم واستيراد
- 📂 **رفع وإدارة ملفات** إلى Cloudflare R2
- 🗄️ **أرشفة** تلقائية أو يدوية للفيديوهات
- 📖 **مكتبة** قرآن وموسيقى
- 🛡️ **حماية SSRF** على الروابط المدخلة من المستخدم
- 🔐 **تشفير مفاتيح RTMP** (Fernet)
- 🤖 دعم اختياري لـ AI (OpenAI / Gemini / Grok / DeepSeek...)
- 📊 لوحة أدمن متقدمة + مراقبة النظام

---

## المتطلبات

- Python 3.10+
- FFmpeg مثبت على النظام (`ffmpeg` في PATH)
- حساب Telegram Bot + Bot Token
- (اختياري) Cloudflare R2
- (اختياري) Local Telegram Bot API Server لرفع ملفات كبيرة

### تثبيت الاعتماديات

```bash
pip install -r requirements.txt
```

أو استخدم `start.sh` / `boot.py` (يثبت تلقائيًا إن لزم).

---

## الإعداد السريع

1. انسخ ملف البيئة:
   ```bash
   cp .env.example .env
   ```

2. املأ القيم الأساسية في `.env`:

| المتغير | مطلوب؟ | الوصف |
|---------|--------|-------|
| `BOT_TOKEN` | ✅ | توكن البوت من @BotFather |
| `ADMIN_ID` | ✅ | رقم تيليجرام الخاص بك (للأدمن) |
| `R2_ENDPOINT` | للرفع | endpoint الخاص بـ R2 |
| `R2_ACCESS_KEY_ID` | للرفع | |
| `R2_SECRET_ACCESS_KEY` | للرفع | |
| `R2_BUCKET_NAME` | للرفع | |
| `RTMP_ENCRYPTION_KEY` | موصى به | مفتاح عشوائي طويل لتشفير مفاتيح الستريم |
| `API_ID` / `API_HASH` | لـ Pyrogram | من my.telegram.org |
| `ARCHIVE_CHANNEL_ID` | اختياري | قناة الأرشفة |
| `AI_ENABLED` | اختياري | `true` لتفعيل المساعد الذكي |

3. شغّل البوت:
   ```bash
   ./start.sh
   # أو
   python3 boot.py
   ```

---

## هيكل المشروع

```
.
├── boot.py              # نقطة التشغيل + تثبيت الاعتماديات
├── main.py              # تسجيل الـ Handlers
├── config.py            # الإعدادات من البيئة
├── database.py          # طبقة قاعدة البيانات (SQLite + aiosqlite)
├── handlers/            # معالجات الأوامر والكالباك
│   ├── streams/         # (مُقسّم) إنشاء/تحكم/حالة البث
│   ├── admin.py
│   ├── cinema.py
│   ├── files.py
│   └── ...
├── services/            # منطق الأعمال
│   ├── stream.py        # إدارة عمليات FFmpeg
│   ├── r2.py
│   ├── oscar/           # عميل مصادر السينما
│   ├── security/ssrf.py
│   └── media/
├── keyboards/           # لوحات المفاتيح
├── core/                # صلاحيات، طابور، لوجينج
├── utils/
├── data/                # قاعدة البيانات والملفات المؤقتة
└── requirements.txt
```

---

## الأمان

- كل الروابط المدخلة من المستخدم تمر عبر `services.security.ssrf.assert_safe_url`
- مفاتيح RTMP تُشفّر في قاعدة البيانات عند وجود `RTMP_ENCRYPTION_KEY`
- لا تضع التوكنات في الكود أو في git
- استخدم `ADMIN_ID` واحد أو نظام صلاحيات الأدمن الموجود

---

## Rate Limiting

تم إضافة نظام بسيط لتحديد معدل الطلبات الثقيلة (إنشاء بث، رفع، probe) لمنع الإساءة.

---

## ملاحظات KataBump / الاستضافة

- ضع المتغيرات في لوحة Environment Variables
- تأكد أن FFmpeg متوفر على السيرفر
- للملفات الكبيرة استخدم Local Bot API (`TELEGRAM_LOCAL_API=true`)

---

## التطوير

```bash
# تشغيل مع لوج أكثر تفصيلاً
LOG_LEVEL=DEBUG python3 boot.py
```

عند إضافة handlers جديدة سجّلها في `main.py`.

---



## FFmpeg — التشغيل واستكشاف الأخطاء

البوت يعتمد على FFmpeg للبث الحي والتحويل.

### ترتيب البحث عن FFmpeg
1. `FFMPEG_PATH` من البيئة
2. `bin/ffmpeg` (نسخة static يتم تنزيلها تلقائياً)
3. النظام (`PATH`)
4. محاولة `apt-get install ffmpeg` (إن وُجدت صلاحيات)
5. تنزيل static من johnvansickle

### إعدادات مفيدة
| المتغير | الافتراضي | الوصف |
|---------|-----------|--------|
| `FFMPEG_PATH` | `ffmpeg` | مسار ثنائي FFmpeg |
| `FFMPEG_TIMEOUT` | `15000000` | مهلة الشبكة (ميكروثانية) |
| `FFMPEG_RECONNECT` | `true` | إعادة الاتصال عند انقطاع المصدر |
| `MAX_STREAMS` | `4` | أقصى عدد بث متزامن |

### تحسينات هذا الإصدار
- اكتشاف خيارات FFmpeg مرة واحدة (cache) بدل استدعاء `-h full` لكل خيار
- اختيار تلقائي للمُرمّز: `libx264` → `h264` → `mpeg4`
- فرض أبعاد زوجية + حد أقصى 1280×720 لاستقرار RTMP
- `thread_queue_size` لتقليل التعليق مع مدخلات متعددة
- إغلاق pipes عند إيقاف العملية (منع deadlock / zombies)
- فحص مبكر إذا خرج FFmpeg فوراً بعد التشغيل
- رسائل خطأ عربية أوضح (403/404/encoder/RTMP broken pipe)
- أرشفة HLS مع reconnect + حماية SSRF

### أعطال شائعة
| العرض | السبب المحتمل | الحل |
|-------|---------------|------|
| FFmpeg exited immediately | رابط ميت أو مفتاح RTMP خاطئ | تحقق من المصدر والمفتاح |
| option not found | بناء FFmpeg قديم/ناقص | اترك البوت ينزل static أو حدّث FFmpeg |
| unknown encoder libx264 | بناء بدون x264 | static من johnvansickle يتضمنه |
| broken pipe / connection reset | RTMP رفض الاتصال | تأكد من `rtmps://...` + stream key |
| stall / إعادة تشغيل متكررة | مصدر متقطع أو بطء شبكة | زد المصادر الاحتياطية أو تحقق من الـ CDN |


## الترخيص

مشروع خاص / للاستخدام الشخصي أو حسب اتفاق الفريق.

---

**تحسينات هذا الإصدار:**
- تقسيم منطق البث إلى حزم أصغر
- README كامل
- .gitignore محسّن
- Rate limiting أساسي
- تنظيف معالجة الأخطاء في المسارات الحرجة

**تحسينات إضافية (متابعة):**
- `database.ensure_connected()` + WAL checkpoint عند الإغلاق
- تنبيه الأدمن عند الأخطاء الحرجة (بحد أقصى مرة كل 3 دقائق)
- التحقق من روابط RTMP قبل التشغيل
- فصل callbacks الفحص (`probe_flow.py`)
- Rate limit على حظر المستخدمين وإيقاف البث من الأدمن
- مجلد `bin/` جاهز لنسخة FFmpeg الثابتة

- تحسينات هيكلية عامة
