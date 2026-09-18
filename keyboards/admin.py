from telegram import InlineKeyboardButton, InlineKeyboardMarkup


def admin_panel_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("👥 المستخدمين", callback_data="admin_users"),
            InlineKeyboardButton("📁 الملفات", callback_data="admin_files"),
        ],
        [
            InlineKeyboardButton("📡 البثوث النشطة", callback_data="admin_streams"),
            InlineKeyboardButton("📊 إحصائيات", callback_data="admin_stats"),
        ],
        [
            InlineKeyboardButton("🛑 إيقاف كل البثوث", callback_data="admin_stop_all"),
        ],
        [
            InlineKeyboardButton("🔙 القائمة الرئيسية", callback_data="main_menu"),
        ],
    ])


def admin_users_keyboard(page: int = 0) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("◀️", callback_data=f"admin_users_page_{page-1}"),
            InlineKeyboardButton("▶️", callback_data=f"admin_users_page_{page+1}"),
        ],
        [InlineKeyboardButton("🔙 رجوع", callback_data="admin_panel")],
    ])


def admin_confirm_stop_all() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("✅ تأكيد الإيقاف", callback_data="admin_confirm_stop_all"),
            InlineKeyboardButton("❌ إلغاء", callback_data="admin_panel"),
        ]
    ])
