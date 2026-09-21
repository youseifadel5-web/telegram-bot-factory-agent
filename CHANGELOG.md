# Changelog — KataBump Stable vNext (Selective Merge)

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
