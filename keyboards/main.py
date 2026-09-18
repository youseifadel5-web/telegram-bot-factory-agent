from telegram import InlineKeyboardButton, InlineKeyboardMarkup


def main_menu_keyboard(is_admin: bool = False) -> InlineKeyboardMarkup:
    """Main menu: keep every existing feature, arranged in balanced 3-column rows."""
    items = [
        ("📡 البث الحالي", "current_stream"), ("🚀 إنشاء بث", "stream_new"), ("📺 IPTV", "iptv_menu"),
        ("🔎 استخراج بث", "extract_menu"), ("🧪 اختبار مصدر", "test_source"), ("☁️ التخزين", "storage_menu"),
        ("📂 ملفاتي", "my_files"), ("📻 المحطات", "stations_menu"), ("🎬 السينما", "cinema_menu"),
        ("🎬 الأفلام", "movies_menu"), ("📺 المسلسلات", "series_menu"), ("⭐ المفضلة", "favorites_menu"),
        ("📖 القرآن", "quran_menu"), ("🎵 الموسيقى", "music_menu"), ("ℹ️ شرح البوت", "help_assistant"),
        ("⚙️ الإعدادات", "settings"), ("👤 حسابي", "my_account"),
    ]
    if is_admin:
        items.extend([("👑 لوحة المدير", "admin_panel"), ("🛡 إدارة الأدمن", "admin_manage")])
    keyboard = [
        [InlineKeyboardButton(label, callback_data=data) for label, data in items[i:i+3]]
        for i in range(0, len(items), 3)
    ]
    return InlineKeyboardMarkup(keyboard)


def back_to_main_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([[InlineKeyboardButton("🔙 القائمة الرئيسية", callback_data="main_menu")]])


def confirm_keyboard(action: str, item_id: int = 0) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([[
        InlineKeyboardButton("✅ نعم", callback_data=f"confirm_{action}_{item_id}"),
        InlineKeyboardButton("❌ لا", callback_data="main_menu"),
    ]])


def settings_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("ℹ️ معلومات البوت", callback_data="about_bot")],
        [InlineKeyboardButton("🔙 رجوع", callback_data="main_menu")],
    ])
