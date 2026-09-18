"""Phase 2 — User account center: my profile, streams, files, storage."""
import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes

from database import db
from utils.helpers import is_admin, format_size
from config import ADMIN_ID

logger = logging.getLogger(__name__)

PROVIDERS = {
    "r2": "🟠 Cloudflare R2",
    "gcs": "🔵 Google Cloud",
    "b2": "🟣 Backblaze B2",
    "archive": "⚫ Archive.org",
}


async def my_account_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if query:
        await query.answer()
        user = query.from_user
        edit = query.edit_message_text
    else:
        user = update.effective_user
        edit = update.message.reply_text

    uid = user.id
    u = await db.get_user(uid) or {}
    n_streams = await db.count_user_streams(uid)
    n_files = await db.count_user_files(uid)
    storage_bytes = await db.sum_user_storage(uid)
    st = await db.get_user_storage(uid)
    prov = PROVIDERS.get(st.get("provider") or "r2", st.get("provider") or "r2")
    role = u.get("role") or "user"
    phone = u.get("phone") or "—"

    text = (
        f"👤 <b>حسابي</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"🆔 <code>{uid}</code>\n"
        f"👤 {user.first_name or ''} @{user.username or '—'}\n"
        f"📱 {phone}\n"
        f"🎖 الدور: <b>{role}</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"📡 بثوثي: <b>{n_streams}</b>\n"
        f"📂 ملفاتي: <b>{n_files}</b>\n"
        f"💾 التخزين المستخدم: <b>{format_size(storage_bytes)}</b>\n"
        f"☁️ مزود التخزين: {prov}\n"
    )
    kb = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("📡 بثوثي", callback_data="current_stream"),
            InlineKeyboardButton("📂 ملفاتي", callback_data="my_files"),
        ],
        [
            InlineKeyboardButton("☁️ تخزيني", callback_data="my_storage"),
            InlineKeyboardButton("⭐ المفضلة", callback_data="favorites_menu"),
        ],
        [InlineKeyboardButton("🗑 حذف كل ملفاتي", callback_data="delete_my_files")],
        [InlineKeyboardButton("🔙 رجوع", callback_data="main_menu")],
    ])
    await edit(text, parse_mode="HTML", reply_markup=kb)


async def my_storage_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    uid = query.from_user.id
    st = await db.get_user_storage(uid)
    current = st.get("provider") or "r2"
    lines = [
        "☁️ <b>تخزيني</b>\n",
        f"المزود الحالي: <b>{PROVIDERS.get(current, current)}</b>\n",
        "اختر مزود التخزين الافتراضي لملفاتك:\n",
        "<i>ملاحظة: ربط حساب GCS/B2/Archive يتطلب مفاتيح في الإعدادات لاحقاً. R2 يعمل من إعدادات السيرفر الحالية.</i>",
    ]
    buttons = []
    for key, label in PROVIDERS.items():
        mark = " ✅" if key == current else ""
        buttons.append([InlineKeyboardButton(f"{label}{mark}", callback_data=f"set_storage:{key}")])
    buttons.append([InlineKeyboardButton("🔙 رجوع", callback_data="my_account")])
    await query.edit_message_text(
        "\n".join(lines), parse_mode="HTML", reply_markup=InlineKeyboardMarkup(buttons)
    )


async def set_storage_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    provider = query.data.split(":")[1]
    if provider not in PROVIDERS:
        await query.answer("غير مدعوم", show_alert=True)
        return
    await db.set_user_storage(query.from_user.id, provider)
    await db.add_audit(query.from_user.id, "set_storage", provider, "")
    await query.answer(f"تم اختيار {PROVIDERS[provider]}", show_alert=True)
    await my_storage_callback(update, context)


async def delete_my_files_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    kb = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("✅ نعم احذف الكل", callback_data="delete_my_files_confirm"),
            InlineKeyboardButton("❌ إلغاء", callback_data="my_account"),
        ]
    ])
    await query.edit_message_text(
        "🗑 <b>حذف جميع ملفاتي</b>\n\nهل أنت متأكد؟ لا يمكن التراجع.",
        parse_mode="HTML",
        reply_markup=kb,
    )


async def delete_my_files_confirm_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    n = await db.delete_user_files(query.from_user.id)
    await db.add_audit(query.from_user.id, "delete_all_files", "", f"count={n}")
    await query.edit_message_text(
        f"✅ تم حذف {n} ملف من سجلاتك.",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 حسابي", callback_data="my_account")]]),
    )
