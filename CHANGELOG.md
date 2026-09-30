# Changelog — KataBump Stable vNext (Selective Merge)

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
