import logging
import time
import asyncio
import hashlib
import html
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from database import db
from services.r2 import r2_service, load_resume_state
from keyboards.menus import my_files_keyboard, file_actions_keyboard, confirm_delete_keyboard
from utils.helpers import format_size, is_admin, safe_filename
from config import (
    ADMIN_ID, BOT_TOKEN,
    LOCAL_BOT_API_ENABLED, LOCAL_BOT_API_LOCAL_MODE,
    TELEGRAM_CLOUD_DOWNLOAD_LIMIT, LOCAL_BOT_API_DOWNLOAD_LIMIT,
)

logger = logging.getLogger(__name__)

BRAND = "Youseif"
# The active download ceiling depends on whether a Local Bot API Server is
# configured. Telegram cloud get_file may fail for large files — we always try
# can bypass that; a Local Bot API Server raises it to ~2GB (or effectively
# unlimited in --local mode). See config.py for details.
TG_MAX = LOCAL_BOT_API_DOWNLOAD_LIMIT  # soft display only — never block uploads by size
CHUNK = 256 * 1024  # 256 KB read chunks from network


def progress_bar(pct: float, width: int = 12) -> str:
    pct = max(0.0, min(100.0, pct))
    filled = int(round(width * pct / 100))
    return "▓" * filled + "░" * (width - filled)


def format_speed(bps: float) -> str:
    if bps < 1024:
        return f"{bps:.0f} B/s"
    if bps < 1024 ** 2:
        return f"{bps/1024:.1f} KB/s"
    return f"{bps/(1024**2):.2f} MB/s"


def format_eta(seconds: float) -> str:
    if seconds < 0 or seconds > 86400:
        return "--:--"
    m, s = divmod(int(seconds), 60)
    h, m = divmod(m, 60)
    if h:
        return f"{h:02d}:{m:02d}:{s:02d}"
    return f"{m:02d}:{s:02d}"


def brand_progress(
    stage: str,
    name: str,
    done: int,
    total: int,
    speed: float,
    elapsed: float,
    pct: float,
) -> str:
    """Youseif-branded progress panel (HTML) — shows size, %, speed, ETA."""
    bar = progress_bar(pct)
    eta = format_eta((total - done) / speed) if speed > 0 and total > done else "--:--"
    safe_name = html.escape(name[:40])
    return (
        f"🎬 <b>{BRAND} Upload</b>\n"
        f"━━━━━━━━━━━━━━━━\n"
        f"📄 <code>{safe_name}</code>\n"
        f"📡 {html.escape(stage)}\n\n"
        f"<code>{bar}</code> <b>{pct:.1f}%</b>\n\n"
        f"📦 {format_size(done)} / {format_size(total) if total else '?'}\n"
        f"⚡ {format_speed(speed)}\n"
        f"⏱ {format_eta(elapsed)}  |  ETA {eta}\n"
        f"━━━━━━━━━━━━━━━━\n"
        f"<i>{BRAND} Stream Bot</i>"
    )


async def my_files_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    try:
        files = await db.get_user_files(user_id)
        if not files:
            await query.edit_message_text(
                "📂 *ملفاتي*\n\nلا توجد ملفات.\nأرسل ملفاً أو رابط مباشر (`/upload <رابط>`).",
                parse_mode="Markdown",
                reply_markup=my_files_keyboard([]),
            )
            return
        await query.edit_message_text(
            f"📂 *ملفاتي* ({len(files)})\n\nاختر ملفاً:",
            parse_mode="Markdown",
            reply_markup=my_files_keyboard(files, page=1),
        )
    except Exception as e:
        logger.exception(e)
        await query.edit_message_text("❌ خطأ.")


async def files_page_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    try:
        page = int(query.data.split(":")[1])
        files = await db.get_user_files(query.from_user.id)
        await query.edit_message_text(
            f"📂 *ملفاتي* ({len(files)})",
            parse_mode="Markdown",
            reply_markup=my_files_keyboard(files, page=page),
        )
    except Exception as e:
        logger.exception(e)


async def file_info_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    try:
        file_id = int(query.data.split(":")[1])
        f = await db.get_file(file_id)
        if not f or (f["user_id"] != query.from_user.id and not is_admin(query.from_user.id, ADMIN_ID)):
            await query.edit_message_text("❌ غير موجود.")
            return
        await query.edit_message_text(
            f"📄 *{f['file_name']}*\n\n"
            f"📦 `{format_size(f['file_size'])}`\n"
            f"📅 `{f['uploaded_at'][:19]}`",
            parse_mode="Markdown",
            reply_markup=file_actions_keyboard(file_id, is_admin(query.from_user.id, ADMIN_ID)),
        )
    except Exception as e:
        logger.exception(e)


async def file_link_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    try:
        if not is_admin(query.from_user.id, ADMIN_ID):
            await query.answer("🔒 الروابط للأدمن فقط", show_alert=True)
            return
        file_id = int(query.data.split(":")[1])
        f = await db.get_file(file_id)
        if not f:
            return
        url = f.get("r2_url") or ""
        if f.get("r2_key"):
            new_url = r2_service.generate_presigned_url(f["r2_key"], expires=86400)
            if new_url:
                url = new_url
        await query.message.reply_text(f"🔗 `{url}`", parse_mode="Markdown")
    except Exception as e:
        logger.exception(e)


async def file_delete_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    try:
        file_id = int(query.data.split(":")[1])
        await query.edit_message_text(
            "⚠️ حذف الملف؟",
            reply_markup=confirm_delete_keyboard(file_id),
        )
    except Exception as e:
        logger.exception(e)


async def file_delete_confirm_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    try:
        file_id = int(query.data.split(":")[1])
        f = await db.get_file(file_id)
        if not f or f["user_id"] != query.from_user.id:
            await query.edit_message_text("❌ غير مسموح.")
            return
        if f.get("r2_key"):
            r2_service.delete_object(f["r2_key"])
        await db.delete_file(file_id, query.from_user.id)
        await query.edit_message_text("✅ تم الحذف.")
    except Exception as e:
        logger.exception(e)


def _iter_url_chunks(url: str, headers: dict = None, start_byte: int = 0):
    """Yield chunks from an HTTP URL — never loads full file into RAM/disk.
    start_byte > 0 sends a Range header so an interrupted transfer can be
    resumed from where it left off instead of re-downloading everything."""
    import urllib.request
    req_headers = dict(headers or {})
    if start_byte > 0:
        req_headers["Range"] = f"bytes={start_byte}-"
    req = urllib.request.Request(url, headers=req_headers)
    with urllib.request.urlopen(req, timeout=120) as resp:
        while True:
            data = resp.read(CHUNK)
            if not data:
                break
            yield data


def _iter_local_file_chunks(path: str, start_byte: int = 0):
    """Reads a file already present on this disk — used when the Local Bot
    API Server runs in --local mode, so get_file() gives us a local path and
    we skip a redundant HTTP round-trip entirely."""
    with open(path, "rb") as f:
        if start_byte:
            f.seek(start_byte)
        while True:
            data = f.read(CHUNK)
            if not data:
                break
            yield data


def _resume_id(namespace: str, identifier: str, size: int) -> str:
    raw = f"{namespace}:{identifier}:{size}"
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()[:24]


async def _run_multipart_upload(
    status_msg,
    name: str,
    total: int,
    make_chunks_iter,
    mime: str,
    user_id: int,
    resume_id: str = None,
):
    """Runs multipart upload in executor + live UI updates. `make_chunks_iter`
    is a callable(start_byte) -> iterator, so a resume can restart the source
    read from the right offset."""
    resumed = load_resume_state(resume_id) if resume_id else None
    start_byte = resumed.get("uploaded_bytes", 0) if resumed else 0

    state = {"done": start_byte, "t0": time.time(), "start_byte": start_byte}
    loop = asyncio.get_event_loop()
    stop = asyncio.Event()

    def on_progress(done, total_sz):
        state["done"] = done

    async def ui_loop():
        while not stop.is_set():
            done = state["done"]
            elapsed = max(time.time() - state["t0"], 0.01)
            speed = max(done - state["start_byte"], 0) / elapsed
            pct = (done / total * 100) if total else 0
            stage = "☁️ استئناف الرفع → Cloudflare R2" if resumed else "☁️ رفع Streaming → Cloudflare R2"
            try:
                await status_msg.edit_text(
                    brand_progress(stage, name, done, total, speed, elapsed, pct),
                    parse_mode="HTML",
                )
            except Exception:
                pass
            try:
                await asyncio.wait_for(stop.wait(), timeout=1.5)
            except asyncio.TimeoutError:
                pass

    ui_task = asyncio.create_task(ui_loop())

    def do_upload():
        chunks_iter = make_chunks_iter(start_byte)
        return r2_service.multipart_upload_from_iter(
            chunks_iter,
            file_name=name,
            total_size=total,
            content_type=mime,
            progress_callback=on_progress,
            resume_id=resume_id,
            user_id=user_id,
        )

    r2_key, r2_url = await loop.run_in_executor(None, do_upload)
    stop.set()
    try:
        await ui_task
    except Exception:
        pass

    if not r2_key:
        detail = html.escape(r2_service.last_error or "خطأ غير معروف")
        resume_note = ""
        kb = None
        if resume_id and load_resume_state(resume_id):
            resume_note = "\n\n♻️ تم حفظ التقدم — يمكنك المتابعة من نفس النقطة بإعادة الإرسال."
        await status_msg.edit_text(
            f"❌ <b>{BRAND}</b> — فشل الرفع\n<code>{detail[:200]}</code>{resume_note}",
            parse_mode="HTML",
        )
        return None

    file_id = await db.add_file(
        user_id=user_id,
        file_name=name,
        file_size=total or state["done"],
        r2_key=r2_key,
        r2_url=r2_url or "",
        mime_type=mime,
    )
    elapsed = max(time.time() - state["t0"], 0.01)
    await status_msg.edit_text(
        brand_progress("✅ اكتمل الرفع", name, total or state["done"], total or state["done"],
                       (total or state["done"]) / elapsed, elapsed, 100)
        + f"\n\n🆔 <code>{file_id}</code>",
        parse_mode="HTML",
        reply_markup=file_actions_keyboard(file_id, is_admin(user_id, ADMIN_ID)),
    )
    return file_id


async def handle_document(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handles an uploaded Telegram file. Files within the active download
    limit stream straight to R2 (multipart, constant memory). Files above the
    limit get a clear explanation + working alternatives instead of a bare
    'File is too big' error — see config.py for the Local Bot API Server fix."""
    message = update.message
    user = update.effective_user
    if not message or not user:
        return

    doc = message.document or message.video or message.audio or message.voice
    if not doc:
        if message.photo:
            doc = message.photo[-1]
        else:
            await message.reply_text("❌ نوع غير مدعوم.")
            return

    original_name = getattr(doc, "file_name", None) or f"file_{doc.file_id[:12]}.bin"
    name = safe_filename(original_name)
    size = getattr(doc, "file_size", None) or 0
    mime = getattr(doc, "mime_type", None) or "application/octet-stream"

    # لا يوجد حد حجم — نحاول دائماً get_file / Local API / Pyrogram عند الفشل
    status = await message.reply_text(
        brand_progress("⏳ تحضير...", name, 0, size, 0, 0, 0),
        parse_mode="HTML",
    )

    try:
        resume_id = _resume_id("tg", doc.file_id, size)
        local_path = ""
        try:
            tg_file = await context.bot.get_file(doc.file_id)
            local_path = getattr(tg_file, "file_path", "") or ""
        except Exception as ge:
            logger.warning("get_file failed (%s) — trying Pyrogram", ge)
            try:
                from services.pyrogram_dl import is_configured, download_telegram_file
                if is_configured():
                    path, err = await download_telegram_file(doc.file_id, name)
                    if path:
                        make_iter = lambda start: _iter_local_file_chunks(path, start)
                        await _run_multipart_upload(status, name, size, make_iter, mime, user.id, resume_id=resume_id)
                        try:
                            from pathlib import Path as _P
                            _P(path).unlink(missing_ok=True)
                        except Exception:
                            pass
                        return
            except Exception as pe:
                logger.warning("pyrogram fallback unavailable: %s", pe)
            # last resort: ask for direct URL — no hard size gate
            await status.edit_text(
                f"📦 <b>{BRAND}</b>\n"
                f"تعذر تنزيل الملف من تيليجرام مباشرة.\n\n"
                f"✅ أرسل رابط مباشر:\n"
                f"<code>/upload https://رابط-الملف</code>\n\n"
                f"أو فعّل Local Bot API / API_ID+API_HASH في .env",
                parse_mode="HTML",
            )
            return

        if LOCAL_BOT_API_LOCAL_MODE and local_path and not local_path.startswith("http"):
            # Local Bot API server in --local mode already gave us the file
            # directly on this disk — read it straight from there.
            await status.edit_text(
                brand_progress("☁️ رفع مباشر (local mode) → R2", name, 0, size, 0, 0, 1),
                parse_mode="HTML",
            )
            make_iter = lambda start: _iter_local_file_chunks(local_path, start)
        else:
            file_url = local_path
            if not file_url.startswith("http"):
                base = f"{context.bot.base_file_url}" if hasattr(context.bot, "base_file_url") else f"https://api.telegram.org/file/bot{BOT_TOKEN}"
                file_url = f"{base}/{local_path}"
            await status.edit_text(
                brand_progress("⬇️ تنزيل Streaming من تيليجرام → R2", name, 0, size, 0, 0, 1),
                parse_mode="HTML",
            )
            make_iter = lambda start: _iter_url_chunks(file_url, start_byte=start)

        await _run_multipart_upload(status, name, size, make_iter, mime, user.id, resume_id=resume_id)

    except Exception as e:
        logger.exception(e)
        try:
            await status.edit_text(
                f"❌ <b>{BRAND}</b> خطأ:\n<code>{html.escape(str(e)[:180])}</code>",
                parse_mode="HTML",
            )
        except Exception:
            pass


async def upload_url_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    /upload <url>
    Streams any direct HTTP(S) file straight to R2 via multipart — this path
    never goes through Telegram's download limit at all, so it supports
    1GB / 2GB / 4GB / 10GB+ files regardless of Local Bot API Server setup,
    limited only by your R2 storage.
    """
    user = update.effective_user
    if not user or not update.message:
        return
    args = (update.message.text or "").split(maxsplit=1)
    if len(args) < 2 or not args[1].startswith("http"):
        await update.message.reply_text(
            f"🎬 <b>{BRAND}</b>\n\n"
            f"استخدم:\n<code>/upload https://example.com/file.mp3</code>\n\n"
            f"يدعم الملفات الكبيرة جداً (1GB / 2GB / 4GB / 10GB+) — رفع "
            f"Streaming مباشر للسحابة بدون المرور بحد تيليجرام.",
            parse_mode="HTML",
        )
        return

    url = args[1].strip()
    name = safe_filename(url.rstrip("/").split("/")[-1].split("?")[0] or "download.bin")
    status = await update.message.reply_text(
        brand_progress("⏳ فحص الرابط...", name, 0, 0, 0, 0, 0),
        parse_mode="HTML",
    )

    try:
        import urllib.request
        req = urllib.request.Request(url, method="HEAD")
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                size = int(resp.headers.get("Content-Length") or 0)
                mime = resp.headers.get("Content-Type") or "application/octet-stream"
        except Exception:
            size = 0
            mime = "application/octet-stream"

        await status.edit_text(
            brand_progress("☁️ Streaming Upload → R2", name, 0, size, 0, 0, 1),
            parse_mode="HTML",
        )

        resume_id = _resume_id("url", url, size)
        make_iter = lambda start: _iter_url_chunks(url, start_byte=start)
        await _run_multipart_upload(status, name, size, make_iter, mime, user.id, resume_id=resume_id)
    except Exception as e:
        logger.exception(e)
        await status.edit_text(
            f"❌ <b>{BRAND}</b>\n<code>{html.escape(str(e)[:180])}</code>",
            parse_mode="HTML",
        )


async def file_play_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Prepare stream from uploaded file — ask for RTMP next."""
    query = update.callback_query
    await query.answer()
    try:
        file_id = int(query.data.split(":")[1])
        f = await db.get_file(file_id)
        if not f or f["user_id"] != query.from_user.id:
            await query.answer("غير مسموح", show_alert=True)
            return

        url = f.get("r2_url") or ""
        if f.get("r2_key"):
            fresh = r2_service.generate_presigned_url(f["r2_key"], expires=86400 * 7)
            if fresh:
                url = fresh
        if not url:
            await query.edit_message_text("❌ لا يوجد رابط لهذا الملف.")
            return

        name = (f.get("file_name") or "بث ملف")[:80]
        context.user_data["stream_title"] = name
        context.user_data["stream_source"] = url
        context.user_data["pending_stream_url"] = url
        context.user_data["pending_stream_title"] = name

        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("🚀 إكمال البث (RTMP)", callback_data="stream_from_url")],
            [InlineKeyboardButton("🔙 رجوع", callback_data=f"file_info:{file_id}")],
        ])
        await query.edit_message_text(
            f"🎬 <b>Youseif</b> — تشغيل ملف\n\n"
            f"📄 <code>{name}</code>\n"
            f"✅ المصدر جاهز من R2\n\n"
            f"اضغط الزر لإدخال RTMP + مفتاح البث وبدء التشغيل.",
            parse_mode="HTML",
            reply_markup=kb,
        )
    except Exception as e:
        logger.exception(e)
