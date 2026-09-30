# Changelog — KataBump Stable vNext (Selective Merge)

## 2026-09-30 (5) — إصلاح حرج + مراجعة شاملة للنظام والشكل

### Fixed — حرج
- **إصلاح «URL blocked by SSRF protection» عند بدء أي بث HLS/IPTV**: تغليف المصدر بالريلاي المحلي كان يصطدم بحماية SSRF الخاصة بالبوت نفسه (127.0.0.1) — الآن روابط الريلاي معتمدة، والأصل الخارجي يظل مفحوصاً بالكامل.
- سقوط وضع النسخ (-c copy) عند موت FFmpeg الفوري: ينزل تلقائياً لإعادة الترميز في المحاولة التالية (كان يفشل نهائياً).
- الفحص السريع كان يعرض أسوأ جودة (426x240 بدل 720p): يقرأ الآن أعلى جودة من الـ master playlist.
- كشف القنوات الصوتية فقط (audio-only HLS) من وسوم CODECS بدل افتراض وجود فيديو دائماً.
- إعادة تشغيل البث كانت تفقد حقول الريلاي وتغلف مزدوجاً — محفوظة الآن.
- نسخ وضع البث عند كودكس صوت غير متوافق مع FLV (AC3/EAC3/Opus): يرمز بدلاً من النسخ.
- أمان الريلاي: فحص SSRF على كل رابط تطلبه القوائم + الهيدرات الخاصة تُرسل لخادمها الأصلي فقط.

### Changed — ترتيب ونظام وشكل (مراجعة 27 ملاحظة)
- **القائمة الرئيسية أعيد بناؤها**: ترتيب عربي RTL (الزر الأساسي أقصى اليمين)، إزالة كل التكرار (📡 البث المكرر، مصادر IPTV المكررة، الإذاعات/المحطات المكررة)، وإضافة القرآن والموسيقى مباشرة.
- **إصلاح الأزرار الميتة**: «📡 البث» و«🖥 حالة السيرفر» من لوحة الرد لم يكونا يعملان — الآن يعملان.
- **منع خطف الرسائل**: كتابة «أفلام أكشن» أثناء البحث كانت تفتح قائمة الأفلام — المطابقة أصبحت تامة، والإدخال المعلق له الأولوية.
- **السينما اكتملت**: الكرتون والمصارعة والأكثر مشاهدة والأعلى تقييماً والأحدث والتصنيفات وحسب السنة والمشاهدة الأخيرة — كانت مخفية تماماً، أصبحت مرئية.
- **أزرار مجموعات IPTV بالفهرس** بدل الاسم: كانت تكسر لوحة المفاتيح لأسماء المجموعات العربية الطويلة (حد 64 بايت).
- /start يرسل رسالة واحدة بدل رسالتين متتاليتين.
- توحيد صياغة أزرار الرجوع (🔙 رجوع / 🏠 الرئيسية) والإلغاء (❌ إلغاء) في كل الشاشات.
- حذف 4 وحدات لوحات مفاتيح ميتة كانت تنشئ ازدواجية وتربك التعديل (keyboards/main, library, files, admin).
- صف الجودة في مشغل الراديو: 3 أزرار + زر المزيد منفصلاً (بدل 4 مزدحمة).
- تحسين موت خادم الريلاي: إعادة إنشاء تلقائية بدل تعطل كل البثوث.

## 2026-09-30 (4) — إصلاح شامل لمسار IPTV: نسخ بدون ترميز + فحص فوري + تأكيد تشغيل حقيقي

### Changed — كود FFmpeg لمصادر IPTV بالكامل
- **وضع النسخ (stream copy)**: مصادر HLS/IPTV المؤكدة (h264/aac) تُبَث الآن بـ `-c copy` بدون أي إعادة ترميز — أسرع بكثير وأخف بكثير على المعالج. لو فشل النسخ لأي سبب يعود تلقائياً لإعادة الترميز في المحاولة التالية.
- **الريلاي المحلي افتراضياً لمصادر HLS**: كل بث HLS يمر عبر الريلاي من اللحظة الأولى (بدل محاولة فاشلة بـ 403 ثم إعادة) — تشغيل أسرع وأثبت مع شبكات CDN الحاجبة.
- تخزين video_codec/audio_codec من نتيجة الفحص في الـ stream metadata لاتخاذ قرار النسخ.

### Changed — سرعة فحص المصدر
- **مسار فحص فوري لمصادر HLS**: القائمة المؤكدة عبر HTTP (#EXTM3U) تُعَد فحصاً ناجحاً فوراً — الكودكس والجودة تُقرأ من وسوم CODECS/RESOLUTION في الـ master playlist — بدون تشغيل ffprobe نهائياً (من 20-35 ثانية إلى أقل من ثانية).
- كشف الترجمة من CODECS (stpp/ttml) مباشرة.
- مهلة فحص ffprobe للمصادر غير المؤكدة انخفضت إلى 15 ثانية.
- **إصلاح SSRF البطيء**: فحص DNS كان يعلّق حتى 20+ ثانية على النطاقات الميتة (getaddrinfo بلا مهلة) — الآن مهلة 4 ثوانٍ + كاش 5 دقائق لكل نطاق.

### Changed — تأكيد التشغيل الفعلي
- لا رسالة «تم إنشاء البث / جاري الاتصال» إلا بعد نتيجة حقيقية: 🟢 ON AIR فقط عند تأكيد تدفق البيانات فعلياً، 🔴 فشل مع السبب عند الفشل — انتظار حتى 40 ثانية للنتيجة بدل إعلان متسرع.

## 2026-09-30 (3) — موثوقية الكتالوج: مرآة CDN

### Fixed
- كتالوج الباقات يجلب الآن من مصدرين: iptv-org.github.io ثم مرآة jsdelivr CDN لنفس الملفات تلقائياً عند الفشل — لا مزيد من «تعذر تحميل الباقة» بسبب بطء github.io.
- قائمة اللغة العربية لها نفس المرآة الاحتياطية.
- ملاحظة مهمة: زر «🌍 باقات القنوات» هو مصدر الـ 750+ قناة للأفلام؛ القوائم المحفوظة القديمة (استيراد M3U) تظهر منفصلة في نفس القائمة.

## 2026-09-30 (2) — الريلاي المحلي: حل حظر CDN لقنوات IPTV

### Added
- services/hls_relay.py — **ريلاي HLS محلي**: خادم HTTP صغير على 127.0.0.1 يمرر قوائم وقطع HLS عبر Python بهيدرات متصفح كاملة، فيستطيع FFmpeg تشغيل المصادر التي تحظر اتصاله المباشر بخطأ 403 (nrpstream، Cloudflare وأمثالها — سبب «القنوات تظهر ولا تعمل»).
- عند فشل البث بخطأ 403/401 دائم: المحرك يحوّل المصدر تلقائياً إلى الريلاي ويعيد التشغيل (مرة واحدة لكل مصدر) — التشغيل المباشر يظل المسار الافتراضي الأسرع.
- إعادة كتابة كل الروابط داخل القوائم (متغيرات الجودة، القطع، مفاتيح التشفير EXT-X-KEY) لتمر عبر الريلاي بنفس الهيدرات.

### Notes
- فحص شامل لكل أزرار الواجهة (callback <-> تسجيل handler): كل الأزرار الظاهرة للمستخدم مسجلة وتعمل؛ ملفات keyboards القديمة غير المستخدمة (files.py/library.py/admin.py) لم تعد مرجعاً.

## 2026-09-30 — إصلاحات وتطوير شامل

### Removed
- حذف الذكاء الاصطناعي بالكامل: services/ai.py، services/ai_tools.py، handlers/youseif.py (مساعد «يوسف»)، كل مفاتيح وإعدادات الـ AI من config.py و .env.example و services/secrets.py، وزر «🤖 يوسف» من القائمة الرئيسية.

### Added
- 🌍 كتالوج باقات القنوات (services/iptv_catalog.py + handlers/iptv_catalog.py) من iptv-org:
  - باقات بتصنيفات وأيقونات (أفلام، مسلسلات، أخبار، رياضة...) + باقات دول (مصر، السعودية، ...).
  - داخل كل باقة: قنوات عربية / أجنبية / مترجمة / الكل.
  - «مترجم» = اسم القناة يحمل علامة ترجمة، أو ffprobe اكتشف مسار ترجمة أثناء التشغيل (يُحفظ في data/iptv/catalog/catalog_cc.json).
  - تخزين مؤقت لكل باقة (6 ساعات) + مجموعة اللغة العربية (24 ساعة) مع زر «تحديث الباقات».
  - دعم user_agent/referrer لكل قناة عند التشغيل.

### Fixed (FFmpeg / streaming)
- قبول `&` في روابط المصادر (كان يرفض روابط CDN/IPTV الموقعة خطأً).
- canvas الصوت: إضافة `-shortest` حتى لا يستمر البث الأسود بعد انتهاء المصدر.
- تنزيل ffprobe مع ffmpeg الثابت + تفضيله في الفحص + `-loglevel info` في فحص ffmpeg الاحتياطي (كان يخفي أسطر Stream# التي يعتمد عليها المحلل).
- تصفير عداد إعادة التشغيل عند عودة البث للصحة (كان يموت نهائياً بعد 3 استرجاعات).
- الـ stall يحسب فشلاً ويشغّل failover للمصدر الاحتياطي (كان يعيد نفس المصدر للأبد).
- عدم كَش نص المساعدة الفارغ (كان يقفل خيارات reconnect/user_agent للأبد).
- حذف fallback الترميز «h264» غير الموجود (libx264 → mpeg4).
- regex خيارات FFmpeg يقبل `-fps_mode[:stream]`.
- `-f hls` يُفرض فقط عند تأكيد الفحص (كان يفسد MP4/TS بروابط فيها /hls).
- إزالة قراءة stderr المتسابقة عند موت العملية.
- تنزيل static بمهلة زمنية + استخراج آمن (filter="data").
- get_state يعرض failed/error بدل stopped.
- تحديث لوحة الحالة يستهدف البث الصحيح (كان يجدد بثاً قديماً).
- soft-pass في الفحص يتطلب تأكيد HTTP (روابط الموت لا تمرر الآن) + مهلة شبكة rw_timeout.
- كشف مسارات الترجمة في الفحص (has_subtitles).

### Fixed (OscarTV / Cloudflare)
- تمرير هيدرات متصفح (User-Agent + Referer) عند تشغيل قنوات أوسكار — كانت تظهر ولا تعمل بسبب حظر Cloudflare ليوزر-إيجنت ffmpeg.
- رسالة عربية واضحة عند فشل جلب أوسكار مع اقتراح باقات iptv-org كبديل.
- حفظ user_agent/referrer لكل رابط من API أوسكار عند توفره.

المشروع الحالي (telegram-bot-factory-agent-main) هو Source of Truth؛ كل ما يلي دمج انتقائي من نسخ KataBump القديمة (V6_REBUILT / STREAM_FIXES / UI_FINAL / CLASSIC_IRON) مع الحفاظ على كل الميزات القائمة.

## Added
- services/url_normalizer.py — طبقة توحيد URL (sanitize/normalize/unwrap ?url= ?src= ... مع الحفاظ على token/signature/expires/hdnea/hmac).
- services/secrets.py — masking موحد (mask_secret/sanitize_url/sanitize_headers/sanitize_command/_safe_error_text/_diagnose_ffmpeg_error/_validate_rtmp_url).
- HLS Master Playlist parsing: variants مرتبة (quality/width/height/bandwidth/fps/codecs/URI) عبر services/media/hls_detector.py + حقنها في نتيجة probe (is_master_playlist, variants[]).
- Source Mode (video/audio/auto) بدقة حقيقية: resolve_source_mode — لا fallback أعمى إلى video.
- Clone Stream (stream_clone:<id>) — نسخ configuration فقط بدون PID/process/runtime state.
- لوحات 📜 سجلات البث (stream_logs:<id>) و 📈 إحصائيات (stream_stats:<id>) بأرقام حقيقية من -progress pipe:1.
- أزرار المفضلة ⭐ في لوحة التحكم + منع تكرار المفضلة في DB.
- Black-video canvas منخفض الموارد (320x180@10) للمصادر الصوتية على RTMP يتطلب video track (force_video_for_audio).
- نظام اختبارات جديد: test_source_probe / test_hls_detector / test_quality_manager / test_media_detection / test_stream_state / test_url_normalization / test_headers / test_database_migrations.
- tools/regression_test.py — بوابة دمج (imports, DB, SSRF, probe, HLS, quality, FFmpeg builder واحد, states, callback registration, مصفوفة §36).
- VERSION + CHANGELOG.md.

## UI / Telegram (2026-09-21)
- توحيد لوحة التحكم: `stream_control_keyboard` أصبح wrapper فقط يستدعي `stream_actions_keyboard` (لا يوجد نظام أزرار مزدوج).
- إثراء أزرار قائمة البث الحالي وسجل البثوث: `#id + عنوان مختصر + uptime/حالة` مع احترام حد تيليجرام 64 حرفاً للنص و64 بايت لـ callback_data.
- `stream_list_button_text` + `current_streams_keyboard(..., live_meta)` في keyboards/stream.py.
- نص قائمة البث الحالي يعرض الحالة العربية (ON AIR / جاري الاتصال / إعادة اتصال / متوقف مؤقتاً / فشل / متوقف) مع ⏱ uptime.

## Changed
- services/security/ssrf.py — تغطية كاملة (127/8, 10/8, 172.16/12, 192.168/16, 169.254/16, ::1, fc00::/7, fe80::/10, metadata endpoints, IPv4-mapped IPv6) مع عدم حظر CDN العام.
- core/stream_states.py — آلة حالات صريحة (can_transition) مع PROBING/READY/STALLED/ON_AIR ورفض STOPPED→RUNNING المباشر.
- services/quality_manager.py — PROFILES مركزية + resolve_for_source (لا upscale، سقف 720p في auto، audio_only للمصادر الصوتية).
- services/media/ffmpeg_engine.py — الواجهة الوحيدة لبناء الأوامر (build_command) والقدرات (encoder cache).
- services/stream.py — قيود الجودة من Quality Manager، أحداث stream_logs (rtmp_start/on_air/reconnecting/failed/stopped)، reconnect_count، get_meta آمن (بدون RTMP key/headers سرية).
- database.py — أعمدة streams الجديدة (quality/media_mode/source_mode/restart_count/reconnect_count) بـ ALTER idempotent + indexes + dedupe favorites.
- keyboards/menus.py — stream_actions_keyboard يضم صفوف سجلات/إحصائيات/استنساخ/مفضلة مع الحفاظ على كل الأزرار السابقة (قائمة التشغيل، الصوت، Bitrate، أرشفة، حذف).
- utils/visualizer.py — صف مستوى الصوت في اللوحة الحية (formatting فقط، بلا IO).

## Fixed
- ImportError كامن: source_probe_v2 كان يستدعي probe_source_async غير الموجودة — أصبحت موجودة (async + semaphore + to_thread).
- تسريب محتمل لـ RTMP key/Authorization عبر get_meta — أصبح mask/stripped مركزيًا.
- تكرار المفضلة عند الضغط المتكرر.

## Security
- SSRF قبل كل عملية شبكة، تعقيم كل رسائل المستخدم من BOT_TOKEN/API keys/RTMP keys/مسارات النظام.

## Performance
- probe بـ semaphore (MAX_PROBES) عبر asyncio.to_thread — لا حجب لـ event loop.

## Backward Compatible
- كل imports القديمة تعمل (clean_url/sanitize_url_for_ffmpeg تُصدَّر من source_probe كما كانت)، أسماء الجودة القديمة (144p..1080p) صالحة، بيانات DB القديمة تُقرأ بـ defaults آمنة.
