# Youseif Player Pro — GitHub APK Builder

النسخة دي مجهزة للبناء من **GitHub Actions** بدون الحاجة إلى Android Studio أو Gradle على الهاتف.

## 1) ارفع المشروع إلى GitHub

ارفع كل محتويات هذا المجلد إلى Repository جديد، ثم اعمل Push إلى `main` أو `master`.

الـWorkflow موجود هنا:

`.github/workflows/build-apk.yml`

سيقوم GitHub بتجهيز Java 17 + Android SDK + Gradle 9.3.1 ثم يبني APK Release موقّعًا بالمفتاح المضمّن في المشروع. استخدمت Gradle Action لتثبيت نسخة Gradle محددة لأن المشروع لا يحتوي Gradle Wrapper حاليًا.

## 2) إرسال APK إلى Telegram

من Repository على GitHub:

**Settings → Secrets and variables → Actions → New repository secret**

في حال Secrets الموجودة عندك بالفعل مثل الصورة، **مش محتاج تضيف Secrets جديدة**. الـWorkflow يستخدم:

- `BOT_TOKEN` = توكن البوت
- `ADMIN_ID` = الـChat ID الذي سيستقبل الـAPK

والـWorkflow فيه fallback اختياري للأسماء `TELEGRAM_BOT_TOKEN` و`TELEGRAM_CHAT_ID` لو كانت هي الموجودة عندك بدلاً منها.

**مهم:** لا تحتاج `OPENAI_API_KEY` أو `GEMINI_API_KEY` أو `TMDB_API_KEY` أو باقي مفاتيح البوت لبناء APK وإرساله إلى Telegram؛ لا تضفها للـWorkflow بدون حاجة.

لا تضع التوكن داخل الكود أو داخل `build.gradle`.

بعدها أي Push إلى `main` سيبني APK ويرسله تلقائيًا إلى Telegram.

ويمكنك أيضًا تشغيله يدويًا من:

**Actions → Build APK and Send to Telegram → Run workflow**

## 3) تقليل حجم APK

تم تجهيز Release ليستخدم:

- R8 / minification
- `shrinkResources`
- عدم تضمين dependency metadata داخل APK
- إزالة dependencies غير المستخدمة من build configuration
- إبقاء Media3/HLS/DASH/RTSP المطلوبة للتشغيل
- إبقاء VideoPlayerView وYouseifPlayerController كما هما في النسخة الحالية

الـAPK الناتج هو Release signed sideload build، وليس توقيع Play Store.

## 4) أين تجد APK؟

بعد نجاح Action:

**Actions → آخر تشغيل → Artifacts → YouseifPlayerPro-APK-...**

وسيصل نفس الـAPK إلى Telegram إذا أضفت الـSecrets.
