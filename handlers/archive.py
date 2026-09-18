"""Handlers for smart video archive library."""
import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes

from database import db
from config import ADMIN_ID, ARCHIVE_CHANNEL_ID, ARCHIVE_MIN_DURATION_SEC, ARCHIVE_MAX_DURATION_SEC
from utils.helpers import is_admin
from services import archive as arch_svc

logger = logging.getLogger(__name__)


def _fmt_dur(sec) -> str:
    try:
        s = int(float(sec or 0))
    except Exception:
        return "—"
    if s < 60:
        return f"{s}ث"
    return f"{s // 60}د"


def _archive_list_kb(items: list, page: int = 0) -> InlineKeyboardMarkup:
    buttons = []
    for a in items:
        title = (a.get("title") or "فيديو")[:28]
        buttons.append([
            InlineKeyboardButton(
                f"🎬 {title} ({_fmt_dur(a.get('duration_sec'))})",
                callback_data=f"arch_send:{a['id']}",
            )
        ])
    nav = []
    if page > 0:
        nav.append(InlineKeyboardButton("⬅️", callback_data=f"arch_page:{page-1}"))
    nav.append(InlineKeyboardButton(f"ص {page+1}", callback_data="noop"))
    if len(items) >= 10:
        nav.append(InlineKeyboardButton("➡️", callback_data=f"arch_page:{page+1}"))
    if nav:
        buttons.append(nav)
    buttons.append([
        InlineKeyboardButton("🔎 بحث", callback_data="arch_search"),
        InlineKeyboardButton("🔙 رجوع", callback_data="main_menu"),
    ])
    return InlineKeyboardMarkup(buttons)


async def archive_menu_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    n = await db.count_archives()
    text = (
        "📚 <b>مكتبة الأرشيف</b>\n\n"
        f"عدد الفيديوهات المؤرشفة: <b>{n}</b>\n\n"
        "• البحث بالاسم يرسل الفيديو مباشرة من تليجرام (file_id)\n"
        "• التحويل يتم مرة واحدة فقط عند أرشفة فيديو كامل\n"
        "• لا يُخزَّن شيء على السيرفر بعد الرفع"
    )
    kb = [
        [InlineKeyboardButton("📋 آخر الأرشيف", callback_data="arch_page:0")],
        [InlineKeyboardButton("🔎 بحث في الأرشيف", callback_data="arch_search")],
        [InlineKeyboardButton("📥 أرشفة رابط HLS الآن", callback_data="arch_add_url")],
    ]
    if is_admin(query.from_user.id, ADMIN_ID):
        kb.append([InlineKeyboardButton("⚙️ حالة القناة", callback_data="arch_status")])
    kb.append([InlineKeyboardButton("🔙 القائمة", callback_data="main_menu")])
    await query.edit_message_text(text, parse_mode="HTML", reply_markup=InlineKeyboardMarkup(kb))


async def archive_page_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    try:
        page = int(query.data.split(":")[1])
    except Exception:
        page = 0
    items = await db.list_archives(limit=10, offset=page * 10)
    if not items:
        await query.edit_message_text(
            "📭 الأرشيف فارغ حالياً.",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("📥 أرشفة رابط", callback_data="arch_add_url")],
                [InlineKeyboardButton("🔙", callback_data="archive_menu")],
            ]),
        )
        return
    lines = [f"📚 <b>الأرشيف</b> — صفحة {page+1}\n"]
    for a in items:
        lines.append(f"• {a.get('title') or '—'} · {_fmt_dur(a.get('duration_sec'))} · {a.get('quality') or ''}")
    await query.edit_message_text(
        "\n".join(lines),
        parse_mode="HTML",
        reply_markup=_archive_list_kb(items, page),
    )


async def archive_search_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    context.user_data["await_archive_search"] = True
    await query.edit_message_text(
        "🔎 <b>ابحث في الأرشيف</b>\n\nأرسل اسم الفيلم أو الحلقة:",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("❌ إلغاء", callback_data="archive_menu")]
        ]),
    )


async def run_archive_search(update: Update, context: ContextTypes.DEFAULT_TYPE, text: str):
    results = await db.search_archive(text, limit=15)
    if not results:
        await update.message.reply_text(
            f"❌ لا نتائج لـ «{text}» في الأرشيف.",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("📚 الأرشيف", callback_data="archive_menu")],
                [InlineKeyboardButton("📥 أرشفة رابط", callback_data="arch_add_url")],
            ]),
        )
        return
    buttons = []
    for a in results:
        title = (a.get("title") or "فيديو")[:30]
        buttons.append([
            InlineKeyboardButton(
                f"▶️ {title} ({_fmt_dur(a.get('duration_sec'))})",
                callback_data=f"arch_send:{a['id']}",
            )
        ])
    buttons.append([InlineKeyboardButton("🔙 الأرشيف", callback_data="archive_menu")])
    await update.message.reply_text(
        f"🔎 نتائج «{text}»: <b>{len(results)}</b>\nاضغط للإرسال الفوري:",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(buttons),
    )


async def archive_send_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer("⏳ جاري الإرسال...")
    try:
        aid = int(query.data.split(":")[1])
    except Exception:
        return
    a = await db.get_archive(aid)
    if not a or not a.get("file_id"):
        await query.answer("غير موجود", show_alert=True)
        return
    ok = await arch_svc.send_archive_to_user(context.bot, query.message.chat_id, a)
    if ok:
        await query.answer("✅ تم الإرسال")
    else:
        await query.answer("❌ فشل الإرسال — قد يكون file_id منتهي", show_alert=True)


async def archive_add_url_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if not ARCHIVE_CHANNEL_ID:
        await query.edit_message_text(
            "⚠️ <b>ARCHIVE_CHANNEL_ID</b> غير مضبوط في Environment.\n"
            "أضف رقم قناة خاصة (البوت Admin فيها) ثم أعد المحاولة.",
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🔙", callback_data="archive_menu")]
            ]),
        )
        return
    context.user_data["await_archive_url"] = True
    await query.edit_message_text(
        "📥 <b>أرشفة رابط HLS / فيديو</b>\n\n"
        "أرسل الرابط (m3u8 أو mp4).\n"
        "سيتم التحويل فقط إذا كان فيديو كامل بمدة حقيقية، ثم الرفع للقناة وحذف الملف المؤقت.",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("❌ إلغاء", callback_data="archive_menu")]
        ]),
    )


async def run_archive_url(update: Update, context: ContextTypes.DEFAULT_TYPE, url: str):
    user = update.effective_user
    title = context.user_data.pop("pending_archive_title", None) or "فيديو مؤرشف"
    status = await update.message.reply_text("⏳ جاري فحص المصدر وتحويله عند الحاجة...")
    result = await arch_svc.archive_url_to_channel(
        context.bot,
        url=url.strip(),
        title=title,
        channel_id=ARCHIVE_CHANNEL_ID,
        uploaded_by=user.id if user else None,
        quality="720",
        min_sec=ARCHIVE_MIN_DURATION_SEC,
        max_sec=ARCHIVE_MAX_DURATION_SEC,
        force=is_admin(user.id, ADMIN_ID) if user else False,
    )
    if result.get("ok"):
        a = result.get("archive") or {}
        if result.get("cached"):
            text = (
                f"✅ <b>موجود مسبقاً</b> — لن يُعاد التحويل\n\n"
                f"🎬 {a.get('title')}\n"
                f"⏱ {_fmt_dur(a.get('duration_sec'))} · {a.get('quality') or ''}"
            )
        else:
            text = (
                f"✅ <b>تمت الأرشفة</b>\n\n"
                f"🎬 {a.get('title')}\n"
                f"⏱ {_fmt_dur(a.get('duration_sec'))} · {a.get('quality') or ''}\n"
                f"تم الرفع للقناة وحذف الملف المؤقت من السيرفر."
            )
        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("▶️ إرسال لي الآن", callback_data=f"arch_send:{a.get('id')}")],
            [InlineKeyboardButton("📚 الأرشيف", callback_data="archive_menu")],
        ])
        await status.edit_text(text, parse_mode="HTML", reply_markup=kb)
    else:
        await status.edit_text(
            f"❌ فشل الأرشفة:\n{result.get('error') or 'سبب غير معروف'}",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🔙", callback_data="archive_menu")]
            ]),
        )


async def archive_from_stream_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Archive the source of a finished/stopped stream (stream_id in callback)."""
    query = update.callback_query
    await query.answer()
    if not ARCHIVE_CHANNEL_ID:
        await query.answer("ARCHIVE_CHANNEL_ID غير مضبوط", show_alert=True)
        return
    try:
        sid = int(query.data.split(":")[1])
    except Exception:
        return
    s = await db.get_stream(sid)
    if not s:
        await query.answer("البث غير موجود", show_alert=True)
        return
    uid = query.from_user.id
    if s["user_id"] != uid and not is_admin(uid, ADMIN_ID):
        await query.answer("غير مسموح", show_alert=True)
        return
    url = s.get("source_url") or ""
    title = s.get("title") or f"بث #{sid}"
    await query.edit_message_text(f"⏳ جاري أرشفة «{title}»...")
    result = await arch_svc.archive_url_to_channel(
        context.bot,
        url=url,
        title=title,
        channel_id=ARCHIVE_CHANNEL_ID,
        uploaded_by=uid,
        quality="720",
        min_sec=ARCHIVE_MIN_DURATION_SEC,
        max_sec=ARCHIVE_MAX_DURATION_SEC,
        force=is_admin(uid, ADMIN_ID),
    )
    if result.get("ok"):
        a = result.get("archive") or {}
        msg = "موجود مسبقاً" if result.get("cached") else "تمت الأرشفة ورفع للقناة"
        await query.edit_message_text(
            f"✅ {msg}\n🎬 {a.get('title')}\n⏱ {_fmt_dur(a.get('duration_sec'))}",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("▶️ إرسال", callback_data=f"arch_send:{a.get('id')}")],
                [InlineKeyboardButton("📡 البث", callback_data=f"stream_status:{sid}")],
            ]),
        )
    else:
        await query.edit_message_text(
            f"❌ {result.get('error')}",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🔙", callback_data=f"stream_status:{sid}")]
            ]),
        )


async def archive_status_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if not is_admin(query.from_user.id, ADMIN_ID):
        return
    n = await db.count_archives()
    ch = ARCHIVE_CHANNEL_ID or "—"
    text = (
        f"⚙️ <b>حالة الأرشيف</b>\n\n"
        f"📺 القناة: <code>{ch}</code>\n"
        f"📚 عدد العناصر: <b>{n}</b>\n"
        f"⏱ حد المدة: {ARCHIVE_MIN_DURATION_SEC}ث — {ARCHIVE_MAX_DURATION_SEC}ث\n"
    )
    await query.edit_message_text(
        text,
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("🔙", callback_data="archive_menu")]
        ]),
    )
