"""Finalize stream creation: probe, save, and start FFmpeg."""
from __future__ import annotations

import html
import logging
import asyncio
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, ConversationHandler

from database import db
from services.stream import stream_manager
from keyboards.menus import stream_actions_keyboard, cancel_keyboard, main_menu, main_reply_keyboard
from utils.helpers import stream_uptime, is_admin, safe_edit_message, clear_workflow_state
from config import ADMIN_ID
from utils.visualizer import build_live_panel
from services.gdrive import extract_file_id, is_drive_url, direct_url, probe_drive
from services.source_probe import probe_source, format_probe_error, parse_time_offset
from services.security.ssrf import assert_safe_url, is_safe_url

from .common import (
    WAITING_TITLE, WAITING_SOURCE, WAITING_OFFSET, WAITING_RTMP_URL, WAITING_STREAM_KEY,
    _safe_update_reply, cancel_conversation, build_rtmp_url, validate_rtmp_url,
)

logger = logging.getLogger(__name__)

async def finalize_stream(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Smart maintenance: block new streams under pressure
    try:
        from services import maintenance as maint
        from config import ADMIN_ID as _AID2
        maint.auto_evaluate()
        # الأدمن يتجاوز وضع الحماية اليدوي
        if maint.blocks_new_streams() and update.effective_user.id != _AID2:
            st = maint.get_status()
            await _safe_update_reply(update, 
                f"🛡 وضع الحماية مفعّل حالياً.\nالسبب: {st.get('reason') or '-'}\n"
                "لا يمكن إنشاء بث جديد الآن. البثوث الحالية مستمرة.\n"
                "للأدمن: ألغِ الحماية من لوحة المدير."
            )
            clear_workflow_state(context.user_data)
            return ConversationHandler.END
    except Exception:
        pass
    user_id = update.effective_user.id
    # RBAC
    try:
        from core.permissions import check_user_permission
        from config import ADMIN_ID as _AID
        if not await check_user_permission(user_id, "stream.create", _AID):
            await _safe_update_reply(update, "⛔ ليس لديك صلاحية إنشاء بث (stream.create)")
            clear_workflow_state(context.user_data)
            return ConversationHandler.END
    except Exception:
        pass
    title = context.user_data.get("stream_title", "بث")
    
    source = context.user_data.get("stream_source")
    base = context.user_data.get("rtmp_base")
    key = context.user_data.get("stream_key")
    user_id = update.effective_user.id
    start_offset = float(context.user_data.get("start_offset") or 0)
    drive_fid = context.user_data.get("drive_file_id")

    rtmp = build_rtmp_url(base, key)
    if rtmp:
        ok_rtmp, rtmp_err = validate_rtmp_url(rtmp)
        if not ok_rtmp:
            await _safe_update_reply(update, f"❌ رابط RTMP غير صالح: {rtmp_err}")
            return WAITING_RTMP_URL

    # Save RTMP profile for future use
    if base and key:
        try:
            await db.save_rtmp_profile(user_id, base, key, name="الافتراضي", is_default=True)
        except Exception as e:
            logger.warning("save rtmp profile: %s", e)

    try:
        # ── Source probe before starting ──
        ffmpeg_ready = await asyncio.to_thread(stream_manager.has_ffmpeg)
        if rtmp and source and ffmpeg_ready:
            await _safe_update_reply(update, "🔍 جاري فحص المصدر قبل التشغيل...")
            # Google Drive: resolve + optional local download if probe fails
            if is_drive_url(source):
                fid = extract_file_id(source) or drive_fid
                if fid:
                    drive_fid = fid
                    context.user_data["drive_file_id"] = fid
                    info = await asyncio.to_thread(probe_drive, fid)
                    if info.get("ok") and info.get("direct_url"):
                        source = info["direct_url"]
                        context.user_data["stream_source"] = source
                    elif not info.get("ok"):
                        # try temp download instead of hard fail
                        await _safe_update_reply(update, "⬇️ جاري تنزيل ملف Drive مؤقتاً...")
                        from services.gdrive import download_to_temp
                        path, err = await asyncio.to_thread(download_to_temp, fid)
                        if path:
                            source = path
                            context.user_data["stream_source"] = source
                        else:
                            await _safe_update_reply(update, 
                                f"❌ فشل Google Drive: {err or info.get('error') or 'الملف غير متاح'}\n"
                                "تأكد أن المشاركة: أي شخص لديه الرابط."
                            )
                            stream_id = await db.create_stream(user_id, title, source, rtmp)
                            clear_workflow_state(context.user_data)
                            return ConversationHandler.END
            # إذا كان رابط صفحة ويب (ليس ميديا مباشر) جرّب الاستخراج أولاً
            if source.startswith("http") and not any(x in source.lower() for x in (".m3u8", ".mp3", ".mp4", ".aac", "drive.google")):
                try:
                    from services.stream_extractor import extract_stream_urls
                    # run extractor
                    loop = asyncio.get_event_loop()
                    extracted = loop.create_task(extract_stream_urls(source)) if False else None
                except Exception:
                    pass
                try:
                    from services.stream_extractor import extract_stream_urls as _ex
                    data = await _ex(source)
                    if data.get("ok") and data.get("streams"):
                        source = data["streams"][0]["url"]
                        context.user_data["stream_source"] = source
                        # رسالة استخراج المصدر للأدمن فقط
                        if update.effective_user and update.effective_user.id == ADMIN_ID:
                            await _safe_update_reply(update, f"🔎 تم استخراج مصدر البث:\n<code>{source[:80]}</code>", parse_mode="HTML")
                except Exception as e:
                    logger.warning("auto-extract: %s", e)

            # Reuse the probe already completed by receive_source/start flow.
            # If the source changed (for example after Drive/extraction), probe
            # once in a worker thread and pass the same headers to playback.
            probe = context.user_data.get("probe_result") or {}
            probe_url = probe.get("cleaned_url") if isinstance(probe, dict) else None
            if not probe or not probe_url or probe_url != source:
                headers_for_probe = context.user_data.get("pending_stream_headers") or {}
                probe = await asyncio.to_thread(probe_source, source, headers=headers_for_probe)
            # Keep the actual media type discovered by ffprobe. URL-based
            # detection alone misses many IPTV/Xtream links that have no
            # ".m3u8" or ".mp4" in the URL.
            context.user_data["_probe_has_video"] = bool(probe.get("has_video"))
            context.user_data["_probe_has_audio"] = bool(probe.get("has_audio"))
            if not probe.get("ok"):
                # soft: still try start for m3u8 / drive / local
                src_l = (source or "").lower()
                soft = (
                    ".m3u8" in src_l
                    or ".mp3" in src_l
                    or ".aac" in src_l
                    or ".mp4" in src_l
                    or ".mkv" in src_l
                    or (source or "").startswith("/")
                    or "drive.google" in src_l
                    or "qurango" in src_l
                    or "mp3quran" in src_l
                    or "/live" in src_l
                    or "/movie/" in src_l
                    or "/series/" in src_l
                    or "radio" in src_l
                    or "workers.dev" in src_l
                    or "stream" in src_l
                    or "dramalaly" in src_l
                    or "vod" in src_l
                    or ":8080" in src_l
                    or ":25461" in src_l
                    or context.user_data.get("pending_stream_headers") is not None
                )
                # أي رابط http(s) نحاول تشغيله حتى لو الفحص فشل (أفلام XUI غالباً)
                if not soft and (source or "").startswith(("http://", "https://", "rtmp://")):
                    soft = True
                if not soft:
                    msg = format_probe_error(probe, source_url=source or "")
                    await _safe_update_reply(update, msg, parse_mode="HTML")
                    stream_id = await db.create_stream(user_id, title, source, rtmp)
                    await db.update_stream_error(stream_id, probe.get("error") or "فحص فاشل")
                    await db.add_stream_log(stream_id, user_id, "probe_fail", probe.get("error") or "", probe.get("solution") or "")
                    clear_workflow_state(context.user_data)
                    await _safe_update_reply(update, 
                        f"⏸ تم حفظ البث #{stream_id} بدون تشغيل.\nيمكنك إعادة المحاولة من «📡 البث الحالي»",
                        reply_markup=main_reply_keyboard(is_admin(user_id, ADMIN_ID)),
                    )
                    return ConversationHandler.END
                else:
                    await _safe_update_reply(update, "⚠️ الفحص غير حاسم — سيتم تجربة التشغيل...")

        stream_id = await db.create_stream(user_id, title, source, rtmp)
        if start_offset:
            await db.update_stream_meta(stream_id, start_offset=start_offset)
        # إنشاء قائمة تشغيل مرتبطة بالبث
        try:
            from services import playlist as playlist_service
            await playlist_service.ensure_playlist_for_stream(user_id, stream_id, title, source)
        except Exception as e:
            logger.warning("playlist seed: %s", e)

        if rtmp:
            if not ffmpeg_ready:
                status = (
                    "⏸ محفوظ بدون تشغيل فعلي\n"
                    "⚠️ FFmpeg غير متوفر على هذا السيرفر\n"
                    "البث يحتاج VPS فيه FFmpeg ليشتغل على القناة"
                )
            else:
                # فيديو فقط إن كان المصدر فيديو — صوت فقط لملفات/راديو صوتية (توفير إنترنت)
                try:
                    from services.source_probe import looks_like_video, detect_media_kind
                    kind = context.user_data.get("media_kind") or detect_media_kind(source or "")
                    probe = context.user_data.get("probe_result") or {}
                    if probe.get("has_video") is False and probe.get("has_audio"):
                        use_video = False
                    elif kind == "audio":
                        use_video = False
                    else:
                        use_video = bool(context.user_data.get("_probe_has_video")) or looks_like_video(source or "") or bool(probe.get("has_video"))
                except Exception:
                    use_video = bool(context.user_data.get("_probe_has_video")) or ".m3u8" in (source or "").lower()
                extra_hdr = context.user_data.pop("pending_stream_headers", None) or {}
                # Always use cleaned URL from probe when available
                try:
                    from services.source_probe import sanitize_url_for_ffmpeg
                    source = sanitize_url_for_ffmpeg(source or "")
                except Exception:
                    pass
                pid = await asyncio.to_thread(
                    stream_manager.start_stream,
                    stream_id, source, rtmp,
                    start_offset=start_offset,
                    with_video=use_video,
                    extra_headers=extra_hdr,
                )

                import asyncio as _asyncio
                await _asyncio.sleep(8.0)
                # If the first FFmpeg process really exited, retry the SAME
                # video pipeline once.  Do not switch a working video source
                # to black-screen/audio-only: that can hide the real HLS error.
                if pid and not stream_manager.is_running(stream_id) and use_video:
                    meta1 = stream_manager.get_meta(stream_id)
                    err1 = (meta1 or {}).get("last_error") or "سبب غير مسجل"
                    # Preserve the first failure because start_stream() replaces
                    # the in-memory metadata on the retry.
                    await _safe_update_reply(update, 
                        "⚠️ انقطع FFmpeg في المحاولة الأولى — إعادة تشغيل الفيديو...\n"
                        f"🔎 السبب: <code>{html.escape(str(err1)[:300])}</code>",
                        parse_mode="HTML",
                    )
                    pid = await asyncio.to_thread(
                        stream_manager.start_stream,
                        stream_id, source, rtmp,
                        start_offset=start_offset,
                        with_video=True,
                        extra_headers=extra_hdr,
                    )
                    await _asyncio.sleep(5.0)
                # ON AIR فقط لو healthy؛ لو شغال لسه بدون healthy → أصفر
                if pid and stream_manager.is_healthy(stream_id):
                    await db.update_stream_status(stream_id, "running", pid)
                    status = "🟢 ON AIR — تم تأكيد تدفق البيانات"
                    await db.add_stream_log(stream_id, user_id, "started", "ON AIR confirmed")
                elif pid and stream_manager.is_running(stream_id):
                    await db.update_stream_status(stream_id, "running", pid)
                    status = "🟡 جاري الاتصال... افتح «البث الحالي» خلال 15 ثانية"
                    await db.add_stream_log(stream_id, user_id, "started", "connecting")
                else:
                    if drive_fid:
                        await _safe_update_reply(update, 
                            "⚠️ فشل البث المباشر من Drive — جاري التنزيل المؤقت..."
                        )
                        from services.gdrive import download_to_temp, cleanup_temp
                        path, err = await asyncio.to_thread(download_to_temp, drive_fid)

                        if path:
                            stream_manager.stop_stream(stream_id)
                            pid2 = await asyncio.to_thread(
                                stream_manager.start_stream,
                                stream_id, path, rtmp,
                                start_offset=start_offset,
                                with_video=True,
                            )
                            await _asyncio.sleep(2.0)
                            if pid2 and stream_manager.is_running(stream_id):
                                await db.update_stream_status(stream_id, "running", pid2)
                                status = "🟢 يعمل (تنزيل Drive مؤقت)"
                            else:
                                cleanup_temp(path)
                                await db.update_stream_status(stream_id, "stopped")
                                status = "🔴 فشل التشغيل حتى بعد التنزيل المؤقت"
                                await db.update_stream_error(stream_id, status)
                        else:
                            await db.update_stream_status(stream_id, "stopped")
                            status = f"🔴 فشل Drive: {err or 'غير معروف'}"
                            await db.update_stream_error(stream_id, status)
                    else:
                        # Read the FFmpeg error BEFORE stop_stream(), because
                        # stop_stream() removes the in-memory metadata.
                        meta = stream_manager.get_meta(stream_id) or {}
                        err_detail = meta.get("last_error") or "تحقق من رابط المصدر ومفتاح RTMP"
                        src_dbg = (source or "")[:180]
                        if len(source or "") > 180:
                            src_dbg += "…"
                        stream_manager.stop_stream(stream_id)
                        await db.update_stream_status(stream_id, "stopped")
                        status = (
                            f"🔴 فشل التشغيل\n"
                            f"🔗 المصدر: <code>{html.escape(src_dbg)}</code>\n"
                            f"🔎 السبب: {html.escape(str(err_detail)[:280])}"
                        )
                        await db.update_stream_error(stream_id, err_detail)
                        await db.add_stream_log(stream_id, user_id, "start_fail", err_detail)
        else:
            status = "⏸ محفوظ بدون تشغيل"

        rtmp_display = rtmp if rtmp else "—"
        if rtmp and len(rtmp) > 60:
            rtmp_display = rtmp[:40] + "…" + rtmp[-12:]

        safe_title = html.escape(str(title))
        safe_rtmp = html.escape(str(rtmp_display))
        safe_status = html.escape(str(status))
        offset_note = f"\n⏱ بداية من: {start_offset:.0f} ثانية" if start_offset else ""
        fail = ("فشل" in str(status)) or ("🔴" in str(status)) or ("غير متوفر" in str(status))
        kb = main_reply_keyboard(is_admin(user_id, ADMIN_ID))
        if fail:
            try:
                from handlers.youseif import store_help_context, youseif_help_button
                from telegram import InlineKeyboardMarkup, InlineKeyboardButton
                store_help_context(
                    context,
                    f"بث #{stream_id} | {title}\nالحالة: {status}\nالمصدر: {(source or '')[:220]}",
                )
                kb = InlineKeyboardMarkup(
                    youseif_help_button()
                    + [[InlineKeyboardButton("📡 البث الحالي", callback_data="current_stream")]]
                    + [[InlineKeyboardButton("🔙 القائمة", callback_data="main_menu")]]
                )
            except Exception:
                pass
        tip = "اضغط «استعن بيوسف» لشرح السبب والحل." if fail else "يمكنك إدارة البث من «📡 البث الحالي»"
        await _safe_update_reply(
            update,
            f"{'⚠️' if fail else '✅'} تم إنشاء البث #{stream_id}\n\n"
            f"📌 العنوان: {safe_title}\n"
            f"📤 RTMP: <code>{safe_rtmp}</code>\n"
            f"📡 الحالة: {safe_status}{offset_note}\n\n"
            f"{tip}",
            parse_mode="HTML",
            reply_markup=kb,
        )
        clear_workflow_state(context.user_data)
    except Exception as e:
        logger.exception(e)
        await _safe_update_reply(update, f"❌ خطأ: {e}")
        clear_workflow_state(context.user_data)
    return ConversationHandler.END


