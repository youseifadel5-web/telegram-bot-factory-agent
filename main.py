#!/usr/bin/env python3
"""Youseif Stream Bot — Telegram + Cloudflare R2 + RTMP."""

import logging
import sys
import os
import asyncio
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
os.chdir(ROOT)
(ROOT / "data").mkdir(parents=True, exist_ok=True)

# Dependencies are handled once by boot.py.
from telegram import Update, BotCommand, MenuButtonCommands
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    MessageHandler,
    ConversationHandler,
    filters,
    ApplicationHandlerStop,
)

from config import (
    BOT_TOKEN, ADMIN_ID, validate_config, LOG_LEVEL, DATABASE_PATH,
    LOCAL_BOT_API_URL, LOCAL_BOT_API_ENABLED, LOCAL_BOT_API_LOCAL_MODE,
)
from database import db
from services.stream import stream_manager
from utils.helpers import clear_workflow_state

from handlers.start import (
    start_command, main_menu_callback, contact_handler, match_reply_action, REPLY_MAP,
    check_subscription_callback,
    section_cinema_callback, section_stream_callback, section_iptv_callback,
    section_tools_callback, section_account_callback, section_audio_callback,
    section_radio_callback, youseif_assistant_callback, my_library_callback, radio_recent_callback,
)
from handlers.files import (
    my_files_callback, files_page_callback, file_info_callback,
    file_link_callback, file_delete_callback, file_delete_confirm_callback,
    handle_document, upload_url_command, file_play_callback,
)
from handlers.library import (
    quran_menu_callback, music_menu_callback, lib_cat_callback,
    lib_page_callback, play_lib_callback, fav_add_last_callback,
)
from handlers.streams import (
    stream_new_callback, stream_from_url_callback,
    receive_title, receive_source, receive_offset, receive_rtmp_url, receive_stream_key,
    cancel_conversation, current_stream_callback, stream_status_callback,
    stream_start_callback, stream_stop_callback, stream_delete_callback,
    stream_restart_callback, stream_vol_up_callback, stream_vol_down_callback,
    stream_mute_callback, stream_br_callback,
    pl_view_callback, pl_next_callback, pl_prev_callback, pl_shuffle_callback, pl_loop_callback,
    stations_menu_callback, stations_command, station_start_callback, station_rtmp_callback,
    station_rtmp_receive, station_rtmp_key_receive,
    WAITING_TITLE, WAITING_SOURCE, WAITING_OFFSET, WAITING_RTMP_URL, WAITING_STREAM_KEY,
    start_rtmp_setup_flags, handle_stream_rtmp_text, handle_stream_key_text,
    rtmp_use_saved_callback, rtmp_change_callback, rtmp_skip_callback,
    probe_continue_callback, probe_retry_callback, cancel_all_status_tasks,
    stream_history_callback, stream_fav_callback,
    stream_logs_callback, stream_stats_callback, stream_clone_callback,
    lp_router,
    current_stream_page_callback,
    stream_submenu_callback,
    stream_change_source_callback,
    change_source_receive,
)
from handlers.archive import (
    archive_menu_callback, archive_page_callback, archive_search_callback,
    archive_send_callback, archive_add_url_callback, run_archive_search,
    run_archive_url, archive_from_stream_callback, archive_status_callback,
)
from handlers.iptv_help import (
    iptv_menu_callback, iptv_import_callback, iptv_group_callback,
    iptv_play_callback, help_assistant_callback, answer_help_question,
    iptv_preset_callback, iptv_refresh_callback,
    iptv_search_callback, run_iptv_search, iptv_open_playlist_callback,
)
from handlers.cinema import (
    cinema_menu_callback, cinema_search_callback, cinema_list_callback, run_cinema_search,
    cinema_pick_callback, cinema_stream_callback, cinema_action_callback, cinema_quality_callback, cinema_season_callback, cinema_episode_callback,
    cinema_episode_action_callback, cinema_episode_quality_callback, cinema_episode_stream_callback, cinema_fav_callback, cinema_favs_callback, cinema_fav_pick_callback,
    cinema_search_page_callback, cinema_episode_page_callback, cinema_back_item_callback, cinema_back_episodes_callback,
    cinema_src_callback, cinema_list_src_callback, cinema_recent_callback,
)

from handlers.movies import (
    movies_menu_callback, movies_search_callback, movies_cat_callback,
    run_movie_search, movie_pick_callback, movie_m3u_all_callback, movie_play_callback, movie_downloads_callback,
)

from handlers.series import (
    series_menu_callback, run_series_search, series_pick_callback,
    series_season_callback, series_episode_callback, series_play_callback,
    series_back_eps_callback,
)

from handlers.account import (
    my_account_callback, my_storage_callback, set_storage_callback,
    delete_my_files_callback, delete_my_files_confirm_callback,
)
from handlers.drive import (
    handle_drive_link, drive_play_callback, drive_rtmp_callback, drive_replay_callback,
)
from handlers.youseif import (
    youseif_message_handler,
    youseif_chat_start_callback,
    youseif_chat_end_callback,
    youseif_help_callback,
)
from handlers.diagnostics import diagnose_command, probe_command, oscar_test_command, hls_command, streams_list_command
from handlers.admin import (
    admin_panel_callback, admin_stats_callback, admin_users_callback,
    admin_user_detail_callback, admin_approve_callback, admin_reject_callback,
    admin_files_callback, admin_streams_callback, settings_callback,
    sys_monitor_callback, storage_menu_callback, upload_help_callback,
    about_bot_callback, verify_phone_callback, admin_broadcast_callback,
    link_hidden_callback, rtmp_settings_callback, rtmp_default_callback,
    schedule_menu_callback, favorites_menu_callback, fav_play_callback,
    pro_stream_callback, schedule_command,
    extract_menu_callback, test_source_callback,
    reset_stream_settings_callback, reset_stream_confirm_callback,
    maintenance_callback, maint_on_callback, maint_off_callback,
    admin_stop_stream_callback, admin_ban_callback, admin_unban_callback, admin_logs_callback,
    admin_manage_callback, admin_add_callback, admin_remove_callback, admin_permissions_callback,
    admin_permission_toggle_callback, required_sub_callback, required_sub_add_callback,
    required_sub_del_callback, admin_management_text,
)

from core.logging_setup import setup_logging
setup_logging(LOG_LEVEL)
logger = logging.getLogger("main")

MENU_BUTTONS = [
    "📂 ملفاتي",
    "📡 البث الحالي",
    "📖 القرآن الكريم",
    "🎵 الأغاني والراديو",
    "⚙️ الإعدادات",
    "📊 لوحة التحكم",
]


async def noop_callback(update: Update, context):
    await update.callback_query.answer()


# Rate-limit admin error alerts (timestamp of last alert)
_last_admin_error_alert = 0.0


async def error_handler(update: object, context):
    import time as _time
    global _last_admin_error_alert
    err = context.error
    name = type(err).__name__ if err else ""
    # أخطاء شائعة لا يجب أن تسقط العملية أو تزعج المستخدم
    if name in ("BadRequest", "TimedOut", "NetworkError", "RetryAfter", "Conflict", "Forbidden"):
        logger.warning("Handled %s: %s", name, err)
        return
    logger.error("Exception while handling update: %s", err, exc_info=err)

    # Soft alert to admin (max 1 / 3 minutes) — never leak stack traces to end users
    try:
        now = _time.time()
        if ADMIN_ID and now - _last_admin_error_alert > 180:
            _last_admin_error_alert = now
            uid = getattr(getattr(update, "effective_user", None), "id", None) if update else None
            brief = f"⚠️ خطأ في البوت\n`{name}`: {str(err)[:180]}\nuser={uid or '-'}"
            await context.bot.send_message(ADMIN_ID, brief, parse_mode="Markdown")
    except Exception:
        pass

    if isinstance(update, Update) and update.callback_query:
        try:
            await update.callback_query.answer("⚠️ تعذر تنفيذ الطلب، حاول مرة أخرى.", show_alert=True)
        except Exception:
            pass
        return
    if isinstance(update, Update) and update.effective_message:
        try:
            await update.effective_message.reply_text(
                "❌ حدث خطأ غير متوقع.\nجرّب /start ثم أعد العملية."
            )
        except Exception:
            pass



async def _dispatch_menu(update: Update, context, action: str):
    """Call menu handlers from reply keyboard (no real callback_query)."""
    # clear await flags on menu
    for k in list((context.user_data or {}).keys()):
        if str(k).startswith("await_"):
            context.user_data.pop(k, None)
    class _Q:
        def __init__(self, update, action):
            self.from_user = update.effective_user
            self.message = update.message
            self.data = action
        async def answer(self, *a, **k):
            return None
        async def edit_message_text(self, text, **k):
            return await self.message.reply_text(
                text, parse_mode=k.get("parse_mode"), reply_markup=k.get("reply_markup")
            )

    class _U:
        def __init__(self, update, action):
            self.effective_user = update.effective_user
            self.effective_message = update.message
            self.message = update.message
            self.callback_query = _Q(update, action)

    fake = _U(update, action)
    handlers = {
        "my_files": my_files_callback,
        "current_stream": current_stream_callback,
        "quran_menu": quran_menu_callback,
        "music_menu": music_menu_callback,
        "settings": settings_callback,
        "admin_panel": admin_panel_callback,
        "storage_menu": storage_menu_callback,
        "stations_menu": stations_menu_callback,
        "my_account": my_account_callback,
        "movies_menu": movies_menu_callback,
        "series_menu": series_menu_callback,
        "iptv_menu": iptv_menu_callback,
        "cinema_menu": cinema_menu_callback,
        "archive_menu": archive_menu_callback,
        "extract_menu": extract_menu_callback,
        "test_source": test_source_callback,
        "help_assistant": help_assistant_callback,
        "favorites_menu": favorites_menu_callback,
        "admin_manage": admin_manage_callback,
        "section_cinema": section_cinema_callback,
        "section_stream": section_stream_callback,
        "stream_history": stream_history_callback,
        "section_iptv": section_iptv_callback,
        "section_tools": section_tools_callback,
        "section_account": section_account_callback,
        "section_audio": section_audio_callback,
        "section_radio": section_radio_callback,
        "youseif_assistant": youseif_assistant_callback,
        "my_library": my_library_callback,
    }
    fn = handlers.get(action)
    if fn:
        await fn(fake, context)


async def reply_menu_router(update: Update, context):
    text = (update.message.text or "").strip()
    action = match_reply_action(text)
    if not action or action == "stream_new":
        return
    # leave any stuck conversation
    clear_workflow_state(context.user_data)
    await _dispatch_menu(update, context, action)


async def conv_menu_fallback(update: Update, context):
    """If user presses a menu button while creating a stream, cancel and open menu."""
    text = (update.message.text or "").strip()
    action = match_reply_action(text)
    if not action or action == "stream_new":
        return ConversationHandler.END
    clear_workflow_state(context.user_data)
    await update.message.reply_text("❌ تم إلغاء إنشاء البث.")
    await _dispatch_menu(update, context, action)
    return ConversationHandler.END


async def post_init(app: Application):
    await db.connect()
    try:
        import asyncio as _aio
        from services.stream import set_logging_loop
        set_logging_loop(_aio.get_running_loop())
    except Exception as e:
        logger.warning("stream log bridge not active: %s", e)
    try:
        from utils.helpers import register_admin
        for u in await db.get_all_users():
            if (u.get("role") or "") in ("owner", "admin"):
                register_admin(u.get("user_id"), True)
    except Exception as e:
        logger.warning("load admin cache: %s", e)
    stream_manager.cleanup_all()
    try:
        active = await db.get_active_streams()
        for s in active:
            await db.update_stream_status(s["id"], "stopped")
    except Exception as e:
        logger.warning(f"reset streams: {e}")

    # قائمة الأوامر الافتراضية (زر Menu في تيليجرام) + /start
    try:
        await app.bot.set_my_commands([
            BotCommand("start", "القائمة الرئيسية / إعادة التشغيل"),
            BotCommand("menu", "فتح القائمة الرئيسية"),
            BotCommand("stations", "المحطات الإذاعية"),
            BotCommand("schedule", "الجدول الزمني"),
            BotCommand("upload", "رفع ملف عبر رابط"),
            BotCommand("cancel", "إلغاء العملية الحالية"),
        ])
        await app.bot.set_chat_menu_button(menu_button=MenuButtonCommands())
        logger.info("Bot commands & menu button registered")
    except Exception as e:
        logger.warning("set_my_commands failed: %s", e)

    # verify library
    from keyboards.menus import load_library
    lib = load_library()
    n = sum(len(c.get("items", [])) for c in lib.get("categories", []))
    # Ensure DB is healthy after long platform sleep
    try:
        ok_db = await db.ensure_connected()
        if not ok_db:
            logger.error("Database not connected after ensure_connected()")
    except Exception as e:
        logger.error("db ensure at boot: %s", e)

    # Try resolve/download FFmpeg at boot (may take time once on KataBump)
    has_ff = await asyncio.to_thread(stream_manager.has_ffmpeg)
    try:
        from services.scheduler import start_scheduler
        start_scheduler()
        from plugins import load_plugins
        load_plugins(app)
        from services.api_server import start_api_server
        await start_api_server()
        from core.queue import start_queues
        await start_queues()
        try:
            from services import maintenance as maint
            maint.deactivate()  # لا تبدأ البوت ووضع الحماية مفعّل
        except Exception:
            pass
        try:
            from core.backup import run_backup
            run_backup('startup')
        except Exception as be:
            logger.warning('startup backup: %s', be)
    except Exception as e:
        logger.warning("scheduler start: %s", e)
    logger.info(
        "Ready | FFmpeg=%s | path=%s | library_items=%s | admin=%s",
        "yes" if has_ff else "NO",
        stream_manager.ffmpeg or "-",
        n,
        ADMIN_ID or "?",
    )
    if ADMIN_ID:
        try:
            await app.bot.send_message(
                ADMIN_ID,
                "🟢 <b>تم تشغيل Youseif Stream Bot بنجاح</b>\n"
                f"FFmpeg: {'✅ جاهز' if has_ff else '⚠️ غير متاح'}\n"
                "البوت جاهز لاستقبال الأوامر.",
                parse_mode="HTML",
            )
        except Exception as e:
            logger.warning("startup admin notification failed: %s", e)
    # Notify users in the background; startup must not wait on up to 200 API calls.
    async def _notify_startup_users():
        try:
            ids = await db.get_all_user_ids()
            msg = "🟢 *Youseif Bot* عاد للعمل.\nيمكنك استخدام البوت الآن."
            sent = 0
            for uid in ids[:200]:
                try:
                    await app.bot.send_message(uid, msg, parse_mode="Markdown")
                    sent += 1
                except Exception:
                    pass
                await asyncio.sleep(0.08)
            logger.info("Startup notify sent to %s users", sent)
        except asyncio.CancelledError:
            raise
        except Exception as e:
            logger.warning("startup notify: %s", e)

    asyncio.create_task(_notify_startup_users(), name="startup-user-notify")


async def post_shutdown(app: Application):
    try:
        await cancel_all_status_tasks()
    except Exception:
        pass
    try:
        from services.scheduler import stop_scheduler
        stop_scheduler()
        from services.api_server import stop_api_server
        await stop_api_server()
        from core.queue import stop_queues
        await stop_queues()
    except Exception:
        pass
    try:
        stream_manager.cleanup_all()
    except Exception:
        pass
    try:
        await db.close()
    except Exception:
        pass


async def extract_or_test_text(update: Update, context):
    """Handle pending extract/test URL messages + IPTV + help. Ignore if no pending state."""
    ud = context.user_data or {}
    if ud.get("admin_manage_action"):
        if await admin_management_text(update, context):
            return
    pending = any(ud.get(k) for k in (
        "await_help_q", "await_archive_search", "await_archive_url", "await_iptv_url", "await_iptv_search", "await_extract_url", "await_test_url", "await_broadcast", "await_stream_rtmp", "await_stream_key", "await_movie_search", "await_series_search", "await_cinema_search", "await_station_rtmp", "await_station_key",
    ))
    if not pending:
        return  # do not swallow normal messages
    # help assistant free text
    if context.user_data.get("await_help_q"):
        handled = await answer_help_question(update, context)
        if handled:
            return
    text = (update.message.text or "").strip().strip("<>")
    # Manual RTMP for radio stations. This is intentionally separate from the
    # normal stream conversation so a station can be started with a custom target.
    if context.user_data.get("await_station_key"):
        await station_rtmp_key_receive(update, context)
        raise ApplicationHandlerStop
    if context.user_data.get("await_station_rtmp"):
        await station_rtmp_receive(update, context)
        raise ApplicationHandlerStop
    # RTMP/Key for IPTV & quick stream (outside ConversationHandler)
    if context.user_data.get("await_stream_key"):
        await handle_stream_key_text(update, context)
        raise ApplicationHandlerStop
    if context.user_data.get("await_stream_rtmp"):
        await handle_stream_rtmp_text(update, context)
        raise ApplicationHandlerStop
    if context.user_data.pop("await_cinema_search", None):
        if not text or text.startswith("/"):
            await update.message.reply_text("🔍 أرسل اسم الفيلم أو المسلسل أو الأنمي.")
            context.user_data["await_cinema_search"] = True
            return
        await run_cinema_search(update, context, text)
        raise ApplicationHandlerStop
    if context.user_data.pop("await_series_search", None):
        if not text or text.startswith("/"):
            await update.message.reply_text("📺 أرسل اسم المسلسل.")
            context.user_data["await_series_search"] = True
            return
        await run_series_search(update, context, text)
        raise ApplicationHandlerStop
    if context.user_data.pop("await_movie_search", None):
        if not text or text.startswith("/"):
            await update.message.reply_text("🔎 أرسل اسم الفيلم.")
            context.user_data["await_movie_search"] = True
            return
        await run_movie_search(update, context, text)
        raise ApplicationHandlerStop
    # بحث قنوات IPTV
    
    if context.user_data.pop("await_archive_search", None):
        if not text:
            context.user_data["await_archive_search"] = True
            return
        await run_archive_search(update, context, text)
        raise ApplicationHandlerStop
    if context.user_data.pop("await_archive_url", None):
        if not text or not text.startswith(("http://", "https://")):
            context.user_data["await_archive_url"] = True
            await update.message.reply_text("أرسل رابط http/https صالح للأرشفة.")
            return
        await run_archive_url(update, context, text)
        raise ApplicationHandlerStop

    if context.user_data.pop("await_iptv_search", None):
        if not text or text.startswith("/"):
            await update.message.reply_text("🔎 أرسل كلمة البحث (اسم القناة).")
            context.user_data["await_iptv_search"] = True
            return
        await run_iptv_search(update, context, text)
        raise ApplicationHandlerStop
    if context.user_data.pop("await_iptv_url", None):
        from services import iptv as iptv_svc
        from telegram import InlineKeyboardButton, InlineKeyboardMarkup
        if not text.startswith(("http://", "https://")):
            await update.message.reply_text(
                "❌ أرسل رابط HTTP لملف M3U/M3U8 فقط.\n"
                "مثال: https://iptv-org.github.io/iptv/countries/eg.m3u"
            )
            return
        if text.startswith(("rtmp://", "rtmps://")):
            await update.message.reply_text("❌ هذا رابط RTMP وليس قائمة IPTV.")
            return
        msg = await update.message.reply_text("📥 جاري تحميل قائمة IPTV...")
        try:
            channels = await iptv_svc.fetch_m3u(text)
            if not channels:
                await msg.edit_text(
                    "❌ لم يتم العثور على قنوات.\n"
                    "تأكد أن الرابط ملف M3U (مثل قائمة iptv-org)."
                )
                return
            iptv_svc.save_user_playlist(update.effective_user.id, "IPTV", channels)
            await db.add_audit(update.effective_user.id, "iptv_import", "", f"channels={len(channels)}")
            await msg.edit_text(
                f"✅ تم استيراد <b>{len(channels)}</b> قناة.",
                parse_mode="HTML",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("📡 فتح IPTV", callback_data="iptv_menu")]]),
            )
        except Exception as e:
            await msg.edit_text(f"❌ فشل الاستيراد: {e}")
        return
    if context.user_data.pop("await_extract_url", None):
        from services.stream_extractor import extract_stream_urls, format_extract_result
        from telegram import InlineKeyboardButton, InlineKeyboardMarkup
        msg = await update.message.reply_text("🔎 جاري التحليل...")
        data = await extract_stream_urls(text)
        context.user_data["extracted_streams"] = data.get("streams") or []
        kb_rows = []
        if data.get("ok") and data.get("streams"):
            first = data["streams"][0]["url"]
            context.user_data["pending_stream_url"] = first
            context.user_data["pending_stream_title"] = "بث مستخرج"
            kb_rows.append([InlineKeyboardButton("🚀 تشغيل أول رابط", callback_data="stream_from_url")])
        kb_rows.append([InlineKeyboardButton("🔙 القائمة", callback_data="main_menu")])
        await msg.edit_text(format_extract_result(data), parse_mode="HTML", reply_markup=InlineKeyboardMarkup(kb_rows))
        return
    if context.user_data.pop("await_test_url", None):
        from services.source_probe import probe_source, format_probe_error
        from telegram import InlineKeyboardButton, InlineKeyboardMarkup
        msg = await update.message.reply_text("🧪 جاري الفحص...")
        probe = await asyncio.to_thread(probe_source, text)
        if probe.get("ok"):
            body = (
                "🟢 <b>المصدر جاهز</b>\n\n"
                f"الصوت: {'✅' if probe.get('has_audio') else '⚠️'}\n"
                f"الصيغة: {probe.get('format') or '-'}\n"
                f"الترميز: {probe.get('codec') or '-'}\n"
                f"Bitrate: {probe.get('bitrate') or '-'}\n"
            )
            if probe.get("duration"):
                body += f"المدة: {probe['duration']:.0f} ث\n"
        else:
            body = format_probe_error(probe, source_url=text or "")
        await msg.edit_text(body, parse_mode="HTML", reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("🔙 القائمة", callback_data="main_menu")]
        ]))
        return


def main():
    # Python 3.14 no longer creates a default event loop automatically.
    # python-telegram-bot 21.x expects one to exist when run_polling() starts.
    try:
        asyncio.get_event_loop()
    except RuntimeError:
        asyncio.set_event_loop(asyncio.new_event_loop())

    try:
        validate_config()
    except ValueError as e:
        logger.critical("Config error: %s", e)
        sys.exit(1)

    builder = Application.builder().token(BOT_TOKEN)
    if LOCAL_BOT_API_ENABLED:
        # Route through a self-hosted Local Bot API Server so file downloads
        # aren't capped at Telegram cloud's 20MB — see config.py for details.
        base_url = f"{LOCAL_BOT_API_URL}/bot"
        base_file_url = f"{LOCAL_BOT_API_URL}/file/bot"
        builder = builder.base_url(base_url).base_file_url(base_file_url)
        if LOCAL_BOT_API_LOCAL_MODE:
            builder = builder.local_mode(True)
        logger.info("Using Local Bot API Server at %s (local_mode=%s)", LOCAL_BOT_API_URL, LOCAL_BOT_API_LOCAL_MODE)
    else:
        logger.info("Using Telegram cloud Bot API — file downloads capped at 20MB (see README for Local Bot API Server setup)")

    app = (
        builder
        .post_init(post_init)
        .post_shutdown(post_shutdown)
        .build()
    )

    menu_regex = r"(الراديو|مكتبتي|يوسف|البث الحالي|بث مباشر|إنشاء بث|ملفاتي|القرآن|الموسيقى|المحطات|التخزين|الإعدادات|حسابي|لوحة المدير|لوحة التحكم|أفلام|السينما|مسلسلات|IPTV|استخراج بث|اختبار مصدر|المساعدة|شرح البوت|شرح استخدام البوت|المفضلة|إدارة الأدمن|الأدوات|الأرشيف|إدارة البث|الصوتيات|الحساب|الأدمن|الإذاعات)"

    stream_conv = ConversationHandler(
        entry_points=[
            CallbackQueryHandler(stream_new_callback, pattern="^stream_new$"),
            CallbackQueryHandler(stream_from_url_callback, pattern="^stream_from_url$"),
            MessageHandler(filters.Regex(r"إنشاء بث"), stream_new_callback),
        ],
            states={
            WAITING_TITLE: [
                MessageHandler(filters.Regex(menu_regex), conv_menu_fallback),
                MessageHandler(filters.TEXT & ~filters.COMMAND, receive_title),
                CallbackQueryHandler(cancel_conversation, pattern="^cancel$"),
            ],
            WAITING_SOURCE: [
                MessageHandler(filters.Regex(menu_regex), conv_menu_fallback),
                MessageHandler(filters.TEXT & ~filters.COMMAND, receive_source),
                CallbackQueryHandler(probe_retry_callback, pattern="^probe_retry$"),
                CallbackQueryHandler(cancel_conversation, pattern="^cancel$"),
            ],
            WAITING_OFFSET: [
                MessageHandler(filters.Regex(menu_regex), conv_menu_fallback),
                MessageHandler(filters.TEXT & ~filters.COMMAND, receive_offset),
                CommandHandler("skip", receive_offset),
                CallbackQueryHandler(probe_continue_callback, pattern="^probe_continue$"),
                CallbackQueryHandler(probe_retry_callback, pattern="^probe_retry$"),
                CallbackQueryHandler(cancel_conversation, pattern="^cancel$"),
            ],
            WAITING_RTMP_URL: [
                MessageHandler(filters.Regex(menu_regex), conv_menu_fallback),
                MessageHandler(filters.TEXT & ~filters.COMMAND, receive_rtmp_url),
                CommandHandler("skip", receive_rtmp_url),
                CallbackQueryHandler(rtmp_use_saved_callback, pattern="^rtmp_use_saved$"),
                CallbackQueryHandler(rtmp_change_callback, pattern="^rtmp_change$"),
                CallbackQueryHandler(rtmp_skip_callback, pattern="^rtmp_skip$"),
                CallbackQueryHandler(cancel_conversation, pattern="^cancel$"),
            ],
            WAITING_STREAM_KEY: [
                MessageHandler(filters.Regex(menu_regex), conv_menu_fallback),
                MessageHandler(filters.TEXT & ~filters.COMMAND, receive_stream_key),
                CommandHandler("skip", receive_stream_key),
                CallbackQueryHandler(cancel_conversation, pattern="^cancel$"),
            ],
        },
        fallbacks=[
            CommandHandler("cancel", cancel_conversation),
            CommandHandler("start", cancel_conversation),
            CallbackQueryHandler(cancel_conversation, pattern="^cancel$"),
            MessageHandler(filters.Regex(menu_regex), conv_menu_fallback),
        ],
        allow_reentry=True,
    )

    app.add_handler(CommandHandler("start", start_command))
    app.add_handler(MessageHandler(filters.CONTACT, contact_handler))
    app.add_handler(CommandHandler("menu", start_command))
    app.add_handler(CommandHandler("upload", upload_url_command))
    app.add_handler(CommandHandler("stations", stations_command))
    app.add_handler(CommandHandler("diagnose", diagnose_command))
    app.add_handler(CommandHandler("probe", probe_command))
    app.add_handler(CommandHandler("oscar_test", oscar_test_command))
    app.add_handler(CommandHandler("hls", hls_command))
    app.add_handler(CommandHandler("streams", streams_list_command))
    app.add_handler(stream_conv)

    app.add_handler(MessageHandler(filters.Regex(menu_regex), reply_menu_router))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, youseif_message_handler), group=2)

    app.add_handler(CallbackQueryHandler(main_menu_callback, pattern="^main_menu$"))
    app.add_handler(CallbackQueryHandler(section_cinema_callback, pattern="^section_cinema$"))
    app.add_handler(CallbackQueryHandler(section_stream_callback, pattern="^section_stream$"))
    app.add_handler(CallbackQueryHandler(stream_history_callback, pattern=r"^stream_history"))
    app.add_handler(CallbackQueryHandler(stream_fav_callback, pattern=r"^stream_fav:"))
    app.add_handler(CallbackQueryHandler(stream_clone_callback, pattern=r"^stream_clone:\d+$"))
    app.add_handler(CallbackQueryHandler(stream_logs_callback, pattern=r"^stream_logs:\d+$"))
    app.add_handler(CallbackQueryHandler(stream_stats_callback, pattern=r"^stream_stats:\d+$"))
    app.add_handler(CallbackQueryHandler(section_audio_callback, pattern="^section_audio$"))
    app.add_handler(CallbackQueryHandler(section_iptv_callback, pattern="^section_iptv$"))
    app.add_handler(CallbackQueryHandler(section_tools_callback, pattern="^section_tools$"))
    app.add_handler(CallbackQueryHandler(section_account_callback, pattern="^section_account$"))
    app.add_handler(CallbackQueryHandler(section_radio_callback, pattern="^section_radio$"))
    app.add_handler(CallbackQueryHandler(radio_recent_callback, pattern="^radio_recent$"))
    app.add_handler(CallbackQueryHandler(youseif_assistant_callback, pattern="^youseif_assistant$"))
    app.add_handler(CallbackQueryHandler(youseif_chat_start_callback, pattern="^youseif_chat_start$"))
    app.add_handler(CallbackQueryHandler(youseif_chat_end_callback, pattern="^youseif_chat_end$"))
    app.add_handler(CallbackQueryHandler(youseif_help_callback, pattern="^youseif_help$"))
    app.add_handler(CallbackQueryHandler(my_library_callback, pattern="^my_library$"))
    app.add_handler(CallbackQueryHandler(check_subscription_callback, pattern="^check_subscription$"))
    app.add_handler(CallbackQueryHandler(admin_manage_callback, pattern="^admin_manage$"))
    app.add_handler(CallbackQueryHandler(admin_add_callback, pattern="^admin_add$"))
    app.add_handler(CallbackQueryHandler(admin_remove_callback, pattern="^admin_remove$"))
    app.add_handler(CallbackQueryHandler(admin_permissions_callback, pattern=r"^admin_perms:\d+$"))
    app.add_handler(CallbackQueryHandler(admin_permission_toggle_callback, pattern=r"^admin_perm_toggle:\d+:[a-z.]+$"))
    app.add_handler(CallbackQueryHandler(required_sub_callback, pattern="^required_sub$"))
    app.add_handler(CallbackQueryHandler(required_sub_add_callback, pattern="^required_sub_add$"))
    app.add_handler(CallbackQueryHandler(required_sub_del_callback, pattern=r"^required_sub_del:\d+$"))
    app.add_handler(CallbackQueryHandler(settings_callback, pattern="^settings$"))

    app.add_handler(CallbackQueryHandler(my_files_callback, pattern="^my_files$"))
    app.add_handler(CallbackQueryHandler(files_page_callback, pattern=r"^files_page:\d+$"))
    app.add_handler(CallbackQueryHandler(file_info_callback, pattern=r"^file_info:\d+$"))
    app.add_handler(CallbackQueryHandler(file_link_callback, pattern=r"^file_link:\d+$"))
    app.add_handler(CallbackQueryHandler(file_delete_callback, pattern=r"^file_delete:\d+$"))
    app.add_handler(CallbackQueryHandler(file_delete_confirm_callback, pattern=r"^file_delete_confirm:\d+$"))
    app.add_handler(CallbackQueryHandler(file_play_callback, pattern=r"^file_play:\d+$"))

    app.add_handler(CallbackQueryHandler(quran_menu_callback, pattern="^quran_menu$"))
    app.add_handler(CallbackQueryHandler(music_menu_callback, pattern="^music_menu$"))
    app.add_handler(CallbackQueryHandler(lib_cat_callback, pattern=r"^lib_cat:\w+$"))
    app.add_handler(CallbackQueryHandler(lib_page_callback, pattern=r"^lib_page:\w+:\d+$"))
    app.add_handler(CallbackQueryHandler(play_lib_callback, pattern=r"^play_lib:\w+:\d+$"))
    app.add_handler(CallbackQueryHandler(fav_add_last_callback, pattern="^fav_add_last$"))

    app.add_handler(CallbackQueryHandler(current_stream_callback, pattern="^current_stream$"))
    app.add_handler(CallbackQueryHandler(current_stream_page_callback, pattern=r"^current_stream:p\d+$"))
    app.add_handler(CallbackQueryHandler(stream_status_callback, pattern=r"^stream_status:\d+$"))
    app.add_handler(CallbackQueryHandler(stream_start_callback, pattern=r"^stream_start:\d+$"))
    app.add_handler(CallbackQueryHandler(stream_stop_callback, pattern=r"^stream_stop:\d+$"))
    app.add_handler(CallbackQueryHandler(stream_delete_callback, pattern=r"^stream_delete:\d+$"))
    app.add_handler(CallbackQueryHandler(stream_restart_callback, pattern=r"^stream_restart:\d+$"))
    app.add_handler(CallbackQueryHandler(stream_vol_up_callback, pattern=r"^stream_vol_up:\d+$"))
    app.add_handler(CallbackQueryHandler(stream_vol_down_callback, pattern=r"^stream_vol_down:\d+$"))
    app.add_handler(CallbackQueryHandler(stream_mute_callback, pattern=r"^stream_mute:\d+$"))
    app.add_handler(CallbackQueryHandler(stream_br_callback, pattern=r"^stream_br:\d+:"))
    # Single unified router for the namespaced live-panel callback family
    app.add_handler(CallbackQueryHandler(lp_router, pattern=r"^lp:"))
    app.add_handler(CallbackQueryHandler(stream_submenu_callback, pattern=r"^stream_submenu:\d+$"))
    app.add_handler(CallbackQueryHandler(stream_change_source_callback, pattern=r"^stream_change_src:\d+$"))
    app.add_handler(CallbackQueryHandler(pl_view_callback, pattern=r"^pl_view:\d+$"))
    app.add_handler(CallbackQueryHandler(pl_next_callback, pattern=r"^pl_next:\d+$"))
    app.add_handler(CallbackQueryHandler(pl_prev_callback, pattern=r"^pl_prev:\d+$"))
    app.add_handler(CallbackQueryHandler(pl_shuffle_callback, pattern=r"^pl_shuffle:\d+$"))
    app.add_handler(CallbackQueryHandler(pl_loop_callback, pattern=r"^pl_loop:\d+$"))
    app.add_handler(CallbackQueryHandler(stations_menu_callback, pattern="^stations_menu$"))
    app.add_handler(CallbackQueryHandler(station_start_callback, pattern=r"^station_start:"))
    app.add_handler(CallbackQueryHandler(station_rtmp_callback, pattern=r"^station_rtmp:"))

    app.add_handler(CallbackQueryHandler(admin_panel_callback, pattern="^admin_panel$"))

    app.add_handler(CallbackQueryHandler(storage_menu_callback, pattern="^storage_menu$"))
    app.add_handler(CallbackQueryHandler(sys_monitor_callback, pattern="^sys_monitor$"))
    app.add_handler(CallbackQueryHandler(upload_help_callback, pattern="^upload_help$"))
    app.add_handler(CallbackQueryHandler(about_bot_callback, pattern="^about_bot$"))
    app.add_handler(CallbackQueryHandler(verify_phone_callback, pattern="^verify_phone$"))
    app.add_handler(CallbackQueryHandler(admin_broadcast_callback, pattern="^admin_broadcast$"))
    app.add_handler(CallbackQueryHandler(link_hidden_callback, pattern="^link_hidden$"))

    app.add_handler(CallbackQueryHandler(admin_stats_callback, pattern="^admin_stats$"))
    app.add_handler(CallbackQueryHandler(admin_users_callback, pattern="^admin_users$"))
    app.add_handler(CallbackQueryHandler(admin_user_detail_callback, pattern=r"^admin_user_\d+$"))
    app.add_handler(CallbackQueryHandler(admin_approve_callback, pattern=r"^admin_approve_\d+$"))
    app.add_handler(CallbackQueryHandler(admin_reject_callback, pattern=r"^admin_reject_\d+$"))
    app.add_handler(CallbackQueryHandler(admin_files_callback, pattern="^admin_files$"))
    app.add_handler(CallbackQueryHandler(admin_streams_callback, pattern="^admin_streams$"))
    app.add_handler(CallbackQueryHandler(rtmp_settings_callback, pattern="^rtmp_settings$"))
    app.add_handler(CallbackQueryHandler(rtmp_default_callback, pattern=r"^rtmp_default:\d+$"))
    app.add_handler(CallbackQueryHandler(rtmp_use_saved_callback, pattern="^rtmp_use_saved$"))
    app.add_handler(CallbackQueryHandler(rtmp_change_callback, pattern="^rtmp_change$"))
    app.add_handler(CallbackQueryHandler(rtmp_skip_callback, pattern="^rtmp_skip$"))
    app.add_handler(CallbackQueryHandler(probe_continue_callback, pattern="^probe_continue$"))
    app.add_handler(CallbackQueryHandler(probe_retry_callback, pattern="^probe_retry$"))
    app.add_handler(CallbackQueryHandler(schedule_menu_callback, pattern="^schedule_menu$"))
    app.add_handler(CallbackQueryHandler(favorites_menu_callback, pattern="^favorites_menu$"))
    app.add_handler(CallbackQueryHandler(fav_play_callback, pattern=r"^fav_play:\d+$"))
    app.add_handler(CallbackQueryHandler(pro_stream_callback, pattern="^pro_stream$"))
    app.add_handler(CommandHandler("schedule", schedule_command))
    app.add_handler(CallbackQueryHandler(extract_menu_callback, pattern="^extract_menu$"))
    app.add_handler(CallbackQueryHandler(test_source_callback, pattern="^test_source$"))
    app.add_handler(CallbackQueryHandler(reset_stream_settings_callback, pattern="^reset_stream_settings$"))
    app.add_handler(CallbackQueryHandler(reset_stream_confirm_callback, pattern="^reset_stream_confirm$"))
    app.add_handler(CallbackQueryHandler(maintenance_callback, pattern="^maintenance$"))
    app.add_handler(CallbackQueryHandler(maint_on_callback, pattern="^maint_on$"))
    app.add_handler(CallbackQueryHandler(maint_off_callback, pattern="^maint_off$"))
    app.add_handler(CallbackQueryHandler(my_account_callback, pattern="^my_account$"))
    app.add_handler(CallbackQueryHandler(my_storage_callback, pattern="^my_storage$"))
    app.add_handler(CallbackQueryHandler(set_storage_callback, pattern=r"^set_storage:\w+$"))
    app.add_handler(CallbackQueryHandler(delete_my_files_callback, pattern="^delete_my_files$"))
    app.add_handler(CallbackQueryHandler(delete_my_files_confirm_callback, pattern="^delete_my_files_confirm$"))
    app.add_handler(CallbackQueryHandler(admin_stop_stream_callback, pattern=r"^admin_stop:\d+$"))
    app.add_handler(CallbackQueryHandler(admin_ban_callback, pattern=r"^admin_ban:\d+$"))
    app.add_handler(CallbackQueryHandler(admin_unban_callback, pattern=r"^admin_unban:\d+$"))
    app.add_handler(CallbackQueryHandler(admin_logs_callback, pattern="^admin_logs$"))

    
    app.add_handler(CallbackQueryHandler(cinema_menu_callback, pattern="^cinema_menu$"))
    app.add_handler(CallbackQueryHandler(cinema_src_callback, pattern=r"^cinema_src:"))
    app.add_handler(CallbackQueryHandler(cinema_list_src_callback, pattern=r"^cinema_list_src:"))
    app.add_handler(CallbackQueryHandler(cinema_recent_callback, pattern="^cinema_recent$"))
    app.add_handler(CallbackQueryHandler(cinema_search_callback, pattern="^cinema_search$"))
    app.add_handler(CallbackQueryHandler(cinema_search_page_callback, pattern=r"^cinema_search_page:\d+$"))
    app.add_handler(CallbackQueryHandler(cinema_list_callback, pattern=r"^cinema_list:(movie|series|anime)(?::\d+)?$"))
    app.add_handler(CallbackQueryHandler(cinema_pick_callback, pattern=r"^cinema_pick:\d+$"))
    app.add_handler(CallbackQueryHandler(cinema_action_callback, pattern=r"^cinema_action:(watch|download|stream)$"))
    app.add_handler(CallbackQueryHandler(cinema_quality_callback, pattern=r"^cinema_quality:(watch|download|stream):\d+$"))
    app.add_handler(CallbackQueryHandler(cinema_stream_callback, pattern="^cinema_stream$"))
    app.add_handler(CallbackQueryHandler(cinema_season_callback, pattern=r"^cinema_season:\d+$"))
    app.add_handler(CallbackQueryHandler(cinema_episode_callback, pattern=r"^cinema_episode:\d+$"))
    app.add_handler(CallbackQueryHandler(cinema_episode_action_callback, pattern=r"^cinema_episode_action:(watch|download|stream)$"))
    app.add_handler(CallbackQueryHandler(cinema_episode_quality_callback, pattern=r"^cinema_episode_quality:(watch|download|stream):\d+$"))
    app.add_handler(CallbackQueryHandler(cinema_episode_page_callback, pattern=r"^cinema_episode_page:\d+$"))
    app.add_handler(CallbackQueryHandler(cinema_back_item_callback, pattern="^cinema_back_item$"))
    app.add_handler(CallbackQueryHandler(cinema_back_episodes_callback, pattern="^cinema_back_episodes$"))
    app.add_handler(CallbackQueryHandler(cinema_episode_stream_callback, pattern="^cinema_episode_stream$"))
    app.add_handler(CallbackQueryHandler(cinema_fav_callback, pattern="^cinema_fav$"))
    app.add_handler(CallbackQueryHandler(cinema_favs_callback, pattern="^cinema_favs$"))
    app.add_handler(CallbackQueryHandler(cinema_fav_pick_callback, pattern=r"^cinema_fav_pick:\d+$"))
    app.add_handler(CallbackQueryHandler(movies_menu_callback, pattern="^movies_menu$"))
    app.add_handler(CallbackQueryHandler(movies_search_callback, pattern="^movies_search$"))
    app.add_handler(CallbackQueryHandler(movies_cat_callback, pattern=r"^movies_cat:"))
    app.add_handler(CallbackQueryHandler(movie_pick_callback, pattern=r"^movie_pick:\d+$"))
    app.add_handler(CallbackQueryHandler(movie_downloads_callback, pattern=r"^movie_dl:\d+$"))
    app.add_handler(CallbackQueryHandler(movie_play_callback, pattern=r"^movie_play:\d+:\d+$"))
    app.add_handler(CallbackQueryHandler(movie_m3u_all_callback, pattern="^movie_m3u_all$"))
    app.add_handler(CallbackQueryHandler(series_menu_callback, pattern="^series_menu$"))
    app.add_handler(CallbackQueryHandler(series_pick_callback, pattern=r"^series_pick:\d+$"))
    app.add_handler(CallbackQueryHandler(series_season_callback, pattern=r"^series_season:\d+$"))
    app.add_handler(CallbackQueryHandler(series_episode_callback, pattern=r"^series_episode:\d+$"))
    app.add_handler(CallbackQueryHandler(series_play_callback, pattern=r"^series_play:\d+$"))
    app.add_handler(CallbackQueryHandler(series_back_eps_callback, pattern="^series_back_eps$"))
    
    app.add_handler(CallbackQueryHandler(archive_menu_callback, pattern="^archive_menu$"))
    app.add_handler(CallbackQueryHandler(archive_page_callback, pattern=r"^arch_page:\d+$"))
    app.add_handler(CallbackQueryHandler(archive_search_callback, pattern="^arch_search$"))
    app.add_handler(CallbackQueryHandler(archive_send_callback, pattern=r"^arch_send:\d+$"))
    app.add_handler(CallbackQueryHandler(archive_add_url_callback, pattern="^arch_add_url$"))
    app.add_handler(CallbackQueryHandler(archive_from_stream_callback, pattern=r"^arch_stream:\d+$"))
    app.add_handler(CallbackQueryHandler(archive_status_callback, pattern="^arch_status$"))

    app.add_handler(CallbackQueryHandler(iptv_menu_callback, pattern="^iptv_menu$"))
    app.add_handler(CallbackQueryHandler(iptv_open_playlist_callback, pattern=r"^iptv_openpl:"))
    app.add_handler(CallbackQueryHandler(iptv_import_callback, pattern="^iptv_import$"))
    app.add_handler(CallbackQueryHandler(iptv_group_callback, pattern=r"^iptv_group:"))
    app.add_handler(CallbackQueryHandler(iptv_play_callback, pattern=r"^iptv_play:\d+$"))
    app.add_handler(CallbackQueryHandler(iptv_preset_callback, pattern=r"^iptv_preset:"))
    app.add_handler(CallbackQueryHandler(iptv_refresh_callback, pattern="^iptv_refresh$"))
    app.add_handler(CallbackQueryHandler(iptv_search_callback, pattern="^iptv_search$"))
    app.add_handler(CallbackQueryHandler(help_assistant_callback, pattern="^help_assistant$"))

    app.add_handler(CallbackQueryHandler(drive_play_callback, pattern=r"^drive_play:"))
    app.add_handler(CallbackQueryHandler(drive_rtmp_callback, pattern=r"^drive_rtmp:"))
    app.add_handler(CallbackQueryHandler(drive_replay_callback, pattern=r"^drive_replay$"))
    app.add_handler(CallbackQueryHandler(noop_callback, pattern="^noop$"))
    app.add_handler(MessageHandler(
        filters.TEXT & filters.Regex(r"drive\\.google\\.com|docs\\.google\\.com"),
        handle_drive_link,
    ))

    app.add_handler(MessageHandler(
        filters.Document.ALL | filters.VIDEO | filters.AUDIO | filters.VOICE | filters.PHOTO,
        handle_document,
    ))

    # extract / test / iptv / help free-text
    app.add_handler(MessageHandler(
        filters.TEXT & ~filters.COMMAND,
        extract_or_test_text,
    ))

    app.add_error_handler(error_handler)
    logger.info("Starting Youseif Stream Bot...")
    try:
        app.run_polling(
            allowed_updates=Update.ALL_TYPES,
            drop_pending_updates=True,
            close_loop=False,
        )
    except Exception as e:
        # Conflict = another instance with same token; exit cleanly for platform restart
        name = type(e).__name__
        logger.critical("Polling stopped (%s): %s", name, e)
        sys.exit(1)


if __name__ == "__main__":
    main()
