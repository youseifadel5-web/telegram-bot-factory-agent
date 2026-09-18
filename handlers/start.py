import logging
from telegram import Update, ReplyKeyboardRemove, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from database import db
from config import ADMIN_ID
from keyboards.menus import main_menu, main_reply_keyboard, phone_keyboard
from utils.helpers import is_admin, register_admin, clear_workflow_state

logger = logging.getLogger(__name__)
BOT_NAME = "Youseif"

# Require phone for non-admins (set False to disable)
REQUIRE_PHONE = True

WELCOME_TEXT = (
    "✨ <b>مرحباً بك في 𝑌𝑜𝑢𝑠𝑒𝑖𝑓 𝑆𝑡𝑟𝑒𝑎𝑚𝑖𝑛𝑔 𝐵𝑜𝑡</b> ✨\n\n"
    "🎬 سينما • 📡 بث مباشر • 📺 IPTV • 🎵 موسيقى • 📖 قرآن\n"
    "استمتع بكل الأدوات من القائمة الرئيسية."
)

async def _required_channels():
    try:
        value = await db.get_json_setting("required_channels", [])
        return value if isinstance(value, list) else []
    except Exception:
        return []

async def _subscription_gate(context, user_id: int):
    channels = await _required_channels()
    if not channels:
        return True, []
    missing = []
    for item in channels:
        if not isinstance(item, dict):
            continue
        chat_id = item.get("chat_id") or item.get("username")
        if not chat_id:
            continue
        try:
            member = await context.bot.get_chat_member(chat_id=chat_id, user_id=user_id)
            if getattr(member, "status", "") in ("left", "kicked"):
                missing.append(item)
        except Exception as exc:
            logger.warning("subscription check failed %s: %s", chat_id, exc)
            # If Telegram cannot inspect the channel, do not lock everyone out.
    return not missing, missing


async def _notify_admin_new_user(context: ContextTypes.DEFAULT_TYPE, user, is_new: bool):
    """Send admin a detailed card for every new user with approve/reject + view data."""
    if not ADMIN_ID or not is_new:
        return
    try:
        u = await db.get_user(user.id)
        phone = (u or {}).get("phone") or "—"
        uname = f"@{user.username}" if user.username else "—"
        name = user.full_name or user.first_name or "—"
        status = (u or {}).get("approval_status") or "pending"
        text = (
            f"👤 <b>مستخدم جديد دخل البوت</b>\n\n"
            f"📛 الاسم: <b>{name}</b>\n"
            f"🆔 ID: <code>{user.id}</code>\n"
            f"👤 يوزر: {uname}\n"
            f"📱 الهاتف: <code>{phone}</code>\n"
            f"📌 الحالة: <b>{status}</b>\n"
        )
        kb = InlineKeyboardMarkup([
            [
                InlineKeyboardButton("✅ موافقة", callback_data=f"admin_approve_{user.id}"),
                InlineKeyboardButton("❌ رفض", callback_data=f"admin_reject_{user.id}"),
            ],
            [InlineKeyboardButton("📋 عرض بيانات المستخدم", callback_data=f"admin_user_{user.id}")],
        ])
        await context.bot.send_message(ADMIN_ID, text, parse_mode="HTML", reply_markup=kb)
    except Exception as e:
        logger.warning("notify admin new user: %s", e)


async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if not user:
        return
    try:
        # /start resets only an unfinished interaction; keep pagination, cached
        # results, and the assistant context available to the same user.
        clear_workflow_state(context.user_data)

        role = "admin" if user.id == ADMIN_ID else "user"
        is_new = await db.upsert_user(
            user_id=user.id,
            username=user.username,
            first_name=user.first_name,
            last_name=user.last_name,
            role=role,
            approval_status="approved" if user.id == ADMIN_ID else None,
        )
        if user.id == ADMIN_ID:
            await db.set_role(user.id, "admin")
            await db.set_approval_status(user.id, "approved")

        user_data = await db.get_user(user.id)
        if user_data and (user_data.get("role") in ("owner", "admin")):
            register_admin(user.id, True)
        if user_data and user_data.get("is_banned"):
            await update.message.reply_text("🚫 تم حظرك من استخدام البوت.")
            return

        admin = is_admin(user.id, ADMIN_ID)
        if is_new:
            await update.message.reply_text(WELCOME_TEXT, parse_mode="HTML")

        # Notify admin about brand-new users
        if is_new and not admin:
            await _notify_admin_new_user(context, user, True)

        # Approval gate (skip for admin)
        if not admin:
            approved = await db.is_approved(user.id)
            if not approved:
                status = (user_data or {}).get("approval_status") or "pending"
                if status == "rejected":
                    await update.message.reply_text(
                        "❌ تم رفض طلبك لاستخدام البوت.\nتواصل مع الأدمن إذا كنت تعتقد أن هذا خطأ."
                    )
                else:
                    await update.message.reply_text(
                        "⏳ <b>طلبك قيد المراجعة</b>\n\n"
                        "تم إرسال بياناتك للأدمن. لن تتمكن من استخدام البوت إلا بعد الموافقة.",
                        parse_mode="HTML",
                    )
                return

        # Mandatory channel subscription (skip for owner/admin).
        if not admin:
            subscribed, missing = await _subscription_gate(context, user.id)
            if not subscribed:
                rows = []
                for ch in missing:
                    label = ch.get("name") or ch.get("username") or "القناة المطلوبة"
                    link = ch.get("invite_link") or (
                        f"https://t.me/{str(ch.get('username')).lstrip('@')}"
                        if ch.get("username") else None
                    )
                    if link:
                        rows.append([InlineKeyboardButton(f"📢 {label}", url=link)])
                rows.append([InlineKeyboardButton("🔄 تحقق من الاشتراك", callback_data="check_subscription")])
                await update.message.reply_text(
                    "🔐 <b>الاشتراك مطلوب</b>\n\nاشترك في القنوات المطلوبة ثم اضغط تحقق.",
                    parse_mode="HTML", reply_markup=InlineKeyboardMarkup(rows),
                )
                return

        # Phone verification (skip for admin)
        if REQUIRE_PHONE and not admin:
            verified = await db.is_phone_verified(user.id)
            if not verified:
                await update.message.reply_text(
                    f"🎬 مرحباً بك في *{BOT_NAME}*\n\n"
                    f"للمتابعة، يرجى مشاركة رقم هاتفك للتحقق:",
                    parse_mode="Markdown",
                    reply_markup=phone_keyboard(),
                )
                return

        text = (
            f"🎬 *{BOT_NAME} Stream Bot*\n\n"
            f"أهلاً {user.first_name or ''}!\n\n"
            f"القائمة الرئيسية مختصرة — اختر من الأزرار:"
        )
        await update.message.reply_text(
            text,
            parse_mode="Markdown",
            reply_markup=main_reply_keyboard(admin),
        )
        await update.message.reply_text(
            "أو من الأزرار المضمنة:",
            reply_markup=main_menu(admin),
        )
    except Exception as e:
        logger.exception(e)
        await update.message.reply_text("❌ خطأ.")


async def contact_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Receive shared phone contact."""
    contact = update.message.contact if update.message else None
    user = update.effective_user
    if not contact or not user:
        return
    phone = contact.phone_number or ""
    await db.set_phone(user.id, phone)
    # Re-notify admin with phone now available
    try:
        if ADMIN_ID and user.id != ADMIN_ID:
            u = await db.get_user(user.id)
            uname = f"@{user.username}" if user.username else "—"
            name = user.full_name or user.first_name or "—"
            status = (u or {}).get("approval_status") or "pending"
            text = (
                f"📱 <b>تم تحديث هاتف مستخدم</b>\n\n"
                f"📛 الاسم: <b>{name}</b>\n"
                f"🆔 ID: <code>{user.id}</code>\n"
                f"👤 يوزر: {uname}\n"
                f"📱 الهاتف: <code>{phone}</code>\n"
                f"📌 الحالة: <b>{status}</b>\n"
            )
            kb = InlineKeyboardMarkup([
                [
                    InlineKeyboardButton("✅ موافقة", callback_data=f"admin_approve_{user.id}"),
                    InlineKeyboardButton("❌ رفض", callback_data=f"admin_reject_{user.id}"),
                ],
                [InlineKeyboardButton("📋 عرض بيانات المستخدم", callback_data=f"admin_user_{user.id}")],
            ])
            await context.bot.send_message(ADMIN_ID, text, parse_mode="HTML", reply_markup=kb)
    except Exception as e:
        logger.warning("phone notify: %s", e)

    # Still need approval
    if user.id != ADMIN_ID and not await db.is_approved(user.id):
        await update.message.reply_text(
            f"✅ تم حفظ الرقم: `{phone}`\n\n"
            "⏳ طلبك قيد مراجعة الأدمن. انتظر الموافقة.",
            parse_mode="Markdown",
            reply_markup=ReplyKeyboardRemove(),
        )
        return

    admin = is_admin(user.id, ADMIN_ID)
    await update.message.reply_text(
        f"✅ تم التحقق من الرقم: `{phone}`\n\nمرحباً بك في *{BOT_NAME}*!",
        parse_mode="Markdown",
        reply_markup=main_reply_keyboard(admin),
    )


async def check_subscription_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    ok, missing = await _subscription_gate(context, q.from_user.id)
    if not ok:
        await q.answer("❌ لم يكتمل الاشتراك بعد", show_alert=True)
        return
    await q.message.reply_text("✅ تم التحقق من الاشتراك.", reply_markup=main_reply_keyboard(is_admin(q.from_user.id, ADMIN_ID)))


async def main_menu_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    try:
        await query.answer()
    except Exception:
        pass
    user = query.from_user
    try:
        await db.upsert_user(user.id, user.username, user.first_name, user.last_name)
        admin = is_admin(user.id, ADMIN_ID)

        if not admin:
            if not await db.is_approved(user.id):
                from utils.helpers import safe_edit_message
                await safe_edit_message(
                    query,
                    "⏳ طلبك قيد المراجعة من الأدمن.\nأرسل /start للمتابعة بعد الموافقة.",
                )
                return
            if REQUIRE_PHONE and not await db.is_phone_verified(user.id):
                from utils.helpers import safe_edit_message
                await safe_edit_message(query, "⚠️ يجب التحقق من رقم الهاتف أولاً — أرسل /start")
                return

        from utils.helpers import safe_edit_message
        await safe_edit_message(
            query,
            f"🎬 <b>{BOT_NAME}</b> — القائمة الرئيسية\n\nاختر القسم:",
            parse_mode="HTML",
            reply_markup=main_menu(admin),
        )
    except Exception as e:
        logger.exception(e)


async def section_cinema_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    try:
        await q.answer()
    except Exception:
        pass
    from keyboards.menus import section_cinema_menu
    from utils.helpers import safe_edit_message
    await safe_edit_message(q, "🎬 <b>قسم السينما</b>\n\nأفلام · مسلسلات · أنمي · بحث", parse_mode="HTML", reply_markup=section_cinema_menu())


async def section_stream_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    try:
        await q.answer()
    except Exception:
        pass
    from keyboards.menus import section_stream_menu
    from utils.helpers import safe_edit_message
    await safe_edit_message(q, "📡 <b>قسم البث</b>\n\nالبث الحالي · إنشاء · IPTV · استخراج", parse_mode="HTML", reply_markup=section_stream_menu())


async def section_audio_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    try:
        await q.answer()
    except Exception:
        pass
    from keyboards.menus import section_audio_menu
    from utils.helpers import safe_edit_message
    await safe_edit_message(q, "🎵 <b>الصوتيات</b>\n\nقرآن · موسيقى · إذاعات", parse_mode="HTML", reply_markup=section_audio_menu())


async def section_iptv_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    try:
        await q.answer()
    except Exception:
        pass
    from keyboards.menus import section_iptv_menu
    from utils.helpers import safe_edit_message
    await safe_edit_message(q, "📺 <b>قسم IPTV</b>\n\nالمصادر · إضافة M3U · بحث", parse_mode="HTML", reply_markup=section_iptv_menu())


async def section_tools_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    try:
        await q.answer()
    except Exception:
        pass
    from keyboards.menus import section_tools_menu
    from utils.helpers import safe_edit_message
    await safe_edit_message(q, "🛠 <b>الأدوات</b>\n\nالتخزين والاستخراج والاختبار:", parse_mode="HTML", reply_markup=section_tools_menu())


async def section_account_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    try:
        await q.answer()
    except Exception:
        pass
    from keyboards.menus import section_account_menu
    from utils.helpers import safe_edit_message
    await safe_edit_message(q, "👤 <b>الحساب</b>\n\nملفاتي · المفضلة · الإعدادات", parse_mode="HTML", reply_markup=section_account_menu())



async def section_radio_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    try:
        await q.answer()
    except Exception:
        pass
    from keyboards.menus import section_radio_menu
    from utils.helpers import safe_edit_message
    await safe_edit_message(
        q,
        "📻 <b>الراديو</b>\n\nمحطات · إذاعات · موسيقى · قرآن",
        parse_mode="HTML",
        reply_markup=section_radio_menu(),
    )


async def youseif_assistant_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    from handlers.youseif import youseif_assistant_entry
    await youseif_assistant_entry(update, context)



async def my_library_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    try:
        await q.answer()
    except Exception:
        pass
    from utils.helpers import safe_edit_message
    from telegram import InlineKeyboardMarkup, InlineKeyboardButton
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("⭐ المفضلة", callback_data="favorites_menu")],
        [InlineKeyboardButton("📂 ملفاتي", callback_data="my_files"),
         InlineKeyboardButton("📚 الأرشيف", callback_data="archive_menu")],
        [InlineKeyboardButton("🎬 السينما", callback_data="cinema_menu"),
         InlineKeyboardButton("📻 الراديو", callback_data="section_radio")],
        [InlineKeyboardButton("🔙 القائمة", callback_data="main_menu")],
    ])
    await safe_edit_message(
        q,
        "📚 <b>مكتبتي</b>\n\nالمفضلة · الملفات · الأرشيف · السينما · الراديو",
        parse_mode="HTML",
        reply_markup=kb,
    )



async def radio_recent_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    try:
        await q.answer()
    except Exception:
        pass
    from utils.helpers import safe_edit_message
    from telegram import InlineKeyboardMarkup, InlineKeyboardButton
    recent = context.user_data.get("radio_recent") or []
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("📻 الراديو", callback_data="section_radio")],
        [InlineKeyboardButton("🔙 القائمة", callback_data="main_menu")],
    ])
    if not recent:
        await safe_edit_message(q, "🕒 <b>الأخيرة — الراديو</b>\n\nلا يوجد تشغيل حديث.", parse_mode="HTML", reply_markup=kb)
        return
    lines = ["🕒 <b>الأخيرة — الراديو</b>", ""]
    for i, r in enumerate(recent[:10]):
        lines.append(f"{i+1}. {r.get('title') or '—'}")
    await safe_edit_message(q, "\n".join(lines), parse_mode="HTML", reply_markup=kb)


REPLY_MAP = {
    # Direct actions (classic layout)
    "📡 البث الحالي": "current_stream",
    "البث الحالي": "current_stream",
    "📡 بث مباشر": "current_stream",
    "📡 إدارة البث": "current_stream",
    "🚀 إنشاء بث": "stream_new",
    "إنشاء بث": "stream_new",
    "إنشاء بث جديد": "stream_new",
    "📺 IPTV": "iptv_menu",
    "IPTV": "iptv_menu",
    "🎬 السينما": "cinema_menu",
    "السينما": "cinema_menu",
    "🎬 الأفلام": "movies_menu",
    "🎬 أفلام": "movies_menu",
    "أفلام": "movies_menu",
    "📺 المسلسلات": "series_menu",
    "مسلسلات": "series_menu",
    "🔎 استخراج بث": "extract_menu",
    "استخراج بث": "extract_menu",
    "🧪 اختبار مصدر": "test_source",
    "اختبار مصدر": "test_source",
    "⭐ المفضلة": "favorites_menu",
    "المفضلة": "favorites_menu",
    "📖 القرآن": "quran_menu",
    "القرآن": "quran_menu",
    "القرآن الكريم": "quran_menu",
    "🎵 الموسيقى": "music_menu",
    "الموسيقى": "music_menu",
    "الأغاني": "music_menu",
    "الأغاني والراديو": "music_menu",
    "📻 المحطات": "stations_menu",
    "المحطات": "stations_menu",
    "📻 الإذاعات": "stations_menu",
    "الإذاعات": "stations_menu",
    "📻 الراديو": "section_radio",
    "الراديو": "section_radio",
    "📚 مكتبتي": "my_library",
    "مكتبتي": "my_library",
    "📂 ملفاتي": "my_files",
    "ملفاتي": "my_files",
    "☁️ التخزين": "storage_menu",
    "التخزين": "storage_menu",
    "ℹ️ شرح البوت": "help_assistant",
    "شرح البوت": "help_assistant",
    "💬 شرح البوت": "help_assistant",
    "💬 شرح استخدام البوت": "help_assistant",
    "المساعدة": "help_assistant",
    "💬 المساعدة": "help_assistant",
    "⚙️ الإعدادات": "settings",
    "الإعدادات": "settings",
    "👤 حسابي": "my_account",
    "حسابي": "my_account",
    # Admin
    "👑 لوحة المدير": "admin_panel",
    "لوحة المدير": "admin_panel",
    "لوحة التحكم": "admin_panel",
    "🛠 الأدمن": "admin_panel",
    "الأدمن": "admin_panel",
    "🛡 إدارة الأدمن": "admin_manage",
    "📚 الأرشيف": "archive_menu",
    "الأرشيف": "archive_menu",
    # Optional sections (old messages still work)
    "📡 البث": "section_stream",
    "البث": "section_stream",
    "🎵 الصوتيات": "section_audio",
    "الصوتيات": "section_audio",
    "👤 الحساب": "section_account",
    "الحساب": "section_account",
    "🛠 الأدوات": "section_tools",
    "الأدوات": "section_tools",
}



def match_reply_action(text: str):
    """Match reply keyboard text even with emoji prefix."""
    if not text:
        return None
    for key, action in sorted(REPLY_MAP.items(), key=lambda x: -len(x[0])):
        if key in text:
            return action
    return None
