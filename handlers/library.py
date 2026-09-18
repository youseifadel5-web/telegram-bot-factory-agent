import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from keyboards.menus import (
    quran_menu, music_menu, library_items_keyboard, load_library, main_menu
)

logger = logging.getLogger(__name__)


async def quran_menu_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if query:
        await query.answer()
        await query.edit_message_text(
            "📖 *القرآن الكريم*\n\nاختر القسم:",
            parse_mode="Markdown",
            reply_markup=quran_menu(),
        )
    else:
        await update.message.reply_text(
            "📖 *القرآن الكريم*\n\nاختر القسم:",
            parse_mode="Markdown",
            reply_markup=quran_menu(),
        )


async def music_menu_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if query:
        await query.answer()
        await query.edit_message_text(
            "🎵 *الأغاني والراديو*\n\nاختر القسم:",
            parse_mode="Markdown",
            reply_markup=music_menu(),
        )
    else:
        await update.message.reply_text(
            "🎵 *الأغاني والراديو*\n\nاختر القسم:",
            parse_mode="Markdown",
            reply_markup=music_menu(),
        )


async def lib_cat_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    try:
        cat_type = query.data.split(":")[1]
        lib = load_library()
        cat = next((c for c in lib.get("categories", []) if c["type"] == cat_type), None)
        if not cat or not cat.get("items"):
            await query.edit_message_text(
                "❌ هذا القسم فاضي أو ملف المكتبة غير موجود.\n"
                "تأكد من وجود `data/library.json` على السيرفر.",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("🔙 رجوع", callback_data="main_menu")]
                ]),
            )
            return
        title = cat["name"]
        await query.edit_message_text(
            f"{title}\n\nاختر للتشغيل:",
            reply_markup=library_items_keyboard(cat_type, page=1),
        )
    except Exception as e:
        logger.exception(e)
        await query.edit_message_text("❌ خطأ.")


async def lib_page_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    try:
        parts = query.data.split(":")
        cat_type, page = parts[1], int(parts[2])
        lib = load_library()
        cat = next((c for c in lib.get("categories", []) if c["type"] == cat_type), None)
        title = cat["name"] if cat else cat_type
        await query.edit_message_text(
            f"{title}\n\nاختر للتشغيل:",
            reply_markup=library_items_keyboard(cat_type, page=page),
        )
    except Exception as e:
        logger.exception(e)


async def play_lib_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    try:
        parts = query.data.split(":")
        cat_type, idx = parts[1], int(parts[2])
        lib = load_library()
        cat = next((c for c in lib.get("categories", []) if c["type"] == cat_type), None)
        if not cat or idx >= len(cat.get("items", [])):
            await query.edit_message_text("❌ العنصر غير موجود.")
            return
        item = cat["items"][idx]
        name, url = item["name"], item["url"]
        # إخفاء الرابط عن المستخدم — البوت يستخدمه داخلياً فقط
        context.user_data["pending_stream_url"] = url
        context.user_data["pending_stream_title"] = name

        # إيموجي حسب النوع
        emoji = "📖"
        if cat_type in ("modern", "classic", "radio_quran", "islamic"):
            emoji = "🕌"
        elif cat_type in ("music_artists", "music_radios"):
            emoji = "🎵"

        text = (
            f"{emoji} *{name}*\n\n"
            f"✅ المصدر جاهز داخلياً (الرابط مخفي).\n"
            f"اضغط لإنشاء البث مباشرة."
        )
        context.user_data["last_lib_item"] = {"title": name, "url": url, "type": cat_type}
        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("🚀 تشغيل البث الآن", callback_data="stream_from_url")],
            [InlineKeyboardButton("⭐ إضافة للمفضلة", callback_data="fav_add_last")],
            [InlineKeyboardButton("🔙 رجوع", callback_data=f"lib_cat:{cat_type}")],
        ])
        await query.edit_message_text(text, parse_mode="Markdown", reply_markup=kb)
    except Exception as e:
        logger.exception(e)
        await query.edit_message_text("❌ خطأ في التشغيل.")


async def fav_add_last_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    item = context.user_data.get("last_lib_item")
    if not item:
        await query.answer("لا يوجد عنصر", show_alert=True)
        return
    from database import db
    await db.add_favorite(
        query.from_user.id,
        item.get("type") or "library",
        item.get("title") or "",
        item.get("url") or "",
    )
    await query.answer("⭐ تمت الإضافة للمفضلة", show_alert=True)
