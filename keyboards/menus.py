from telegram import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    ReplyKeyboardMarkup,
    KeyboardButton,
    ReplyKeyboardRemove,
)
from typing import List
import json
import os
import time

LIBRARY_PATH = os.path.join(os.path.dirname(__file__), "..", "data", "library.json")
BOT_BRAND = "Youseif"

# rotating color emojis for buttons
_COLORS = ["🔴", "🟠", "🟡", "🟢", "🔵", "🟣", "🩷", "⚪"]


def _c(i: int = 0) -> str:
    return _COLORS[int(time.time() + i) % len(_COLORS)]


def load_library() -> dict:
    try:
        with open(LIBRARY_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        for alt in ("data/library.json", os.path.join(os.getcwd(), "data", "library.json")):
            try:
                with open(alt, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception:
                continue
        return {"categories": []}


def phone_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        [[KeyboardButton("📱 مشاركة رقم الهاتف", request_contact=True)]],
        resize_keyboard=True,
        one_time_keyboard=True,
    )


def main_reply_keyboard(is_admin: bool = False) -> ReplyKeyboardMarkup:
    """Main reply keyboard: exactly three buttons per row where possible.

    Keep every existing feature; only regroup the buttons for a cleaner layout.
    """
    # Rows are written visually left-to-right; Arabic users read the rightmost
    # primary action first. Main actions are separated from content and tools.
    rows = [
        [KeyboardButton("🚀 إنشاء بث"), KeyboardButton("📡 البث الحالي"), KeyboardButton("📺 IPTV")],
        [KeyboardButton("🎬 السينما"), KeyboardButton("📻 الراديو"), KeyboardButton("📡 البث")],
        [KeyboardButton("⭐ المفضلة"), KeyboardButton("📚 مكتبتي"), KeyboardButton("🔎 استخراج بث")],
        [KeyboardButton("📜 الأرشيف"), KeyboardButton("☁️ التخزين"), KeyboardButton("📂 ملفاتي")],
        [KeyboardButton("ℹ️ شرح البوت"), KeyboardButton("👤 حسابي"), KeyboardButton("⚙️ الإعدادات")],
    ]
    if is_admin:
        rows.append([KeyboardButton("👑 لوحة المدير"), KeyboardButton("🛡 إدارة الأدمن"), KeyboardButton("🖥 حالة السيرفر")])
    return ReplyKeyboardMarkup(
        rows, resize_keyboard=True, is_persistent=False, one_time_keyboard=False,
        input_field_placeholder="اختر قسماً...",
    )

def main_menu(is_admin: bool = False) -> InlineKeyboardMarkup:
    """Clean three-column inline main menu; all original sections remain available."""
    buttons = [
        [InlineKeyboardButton("🚀 إنشاء بث", callback_data="stream_new"), InlineKeyboardButton("📡 البث الحالي", callback_data="current_stream"), InlineKeyboardButton("📺 IPTV", callback_data="iptv_menu")],
        [InlineKeyboardButton("🎬 السينما", callback_data="cinema_menu"), InlineKeyboardButton("📻 الراديو", callback_data="section_radio"), InlineKeyboardButton("📡 البث", callback_data="section_stream")],
        [InlineKeyboardButton("⭐ المفضلة", callback_data="favorites_menu"), InlineKeyboardButton("📚 مكتبتي", callback_data="my_library"), InlineKeyboardButton("🔎 استخراج بث", callback_data="extract_menu")],
        [InlineKeyboardButton("📜 الأرشيف", callback_data="archive_menu"), InlineKeyboardButton("☁️ التخزين", callback_data="storage_menu"), InlineKeyboardButton("📂 ملفاتي", callback_data="my_files")],
        [InlineKeyboardButton("ℹ️ شرح البوت", callback_data="help_assistant"), InlineKeyboardButton("🤖 يوسف", callback_data="youseif_assistant"), InlineKeyboardButton("👤 حسابي", callback_data="my_account"), InlineKeyboardButton("⚙️ الإعدادات", callback_data="settings")],
    ]
    if is_admin:
        buttons.append([InlineKeyboardButton("👑 لوحة المدير", callback_data="admin_panel"), InlineKeyboardButton("🛡 إدارة الأدمن", callback_data="admin_manage"), InlineKeyboardButton("🖥 حالة السيرفر", callback_data="sys_monitor")])
    return InlineKeyboardMarkup(buttons)

def settings_menu() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("⚙️ إعدادات البث (RTMP)", callback_data="rtmp_settings")],
        [InlineKeyboardButton("📅 جدولة البث", callback_data="schedule_menu")],
        [InlineKeyboardButton("⭐ المفضلة", callback_data="favorites_menu")],
        [InlineKeyboardButton("🚀 بث احترافي", callback_data="pro_stream")],
        [InlineKeyboardButton("♻️ إعادة ضبط الإعدادات", callback_data="reset_stream_settings")],
        [InlineKeyboardButton("📱 التحقق من الهاتف", callback_data="verify_phone")],
        [InlineKeyboardButton("ℹ️ عن البوت", callback_data="about_bot")],
        [InlineKeyboardButton("🔙 رجوع", callback_data="main_menu")],
    ])


def storage_menu() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📂 ملفاتي", callback_data="my_files")],
        [InlineKeyboardButton("☁️ رفع من رابط /upload", callback_data="upload_help")],
        [InlineKeyboardButton("🔙 رجوع", callback_data="main_menu")],
    ])


def admin_panel_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🖥 حالة السيرفر", callback_data="sys_monitor")],
        [InlineKeyboardButton("🛡 وضع الحماية", callback_data="maintenance")],
        [InlineKeyboardButton("📁 إدارة الملفات", callback_data="admin_files")],
        [InlineKeyboardButton("☁️ التخزين السحابي", callback_data="storage_menu")],
        [InlineKeyboardButton("👥 المستخدمون", callback_data="admin_users")],
        [InlineKeyboardButton("📡 كل البثوث", callback_data="admin_streams")],
        [InlineKeyboardButton("📊 إحصائيات", callback_data="admin_stats")],
        [InlineKeyboardButton("📜 سجل النظام", callback_data="admin_logs")],
        [InlineKeyboardButton("📢 إشعار للجميع", callback_data="admin_broadcast")],
        [InlineKeyboardButton("🛡 إدارة الأدمن والصلاحيات", callback_data="admin_manage"), InlineKeyboardButton("📢 الاشتراك الإجباري", callback_data="required_sub")],
        [InlineKeyboardButton("🔙 رجوع", callback_data="main_menu")],
    ])


def sys_monitor_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("🔄 تحديث", callback_data="sys_monitor"),
            InlineKeyboardButton("📁 الملفات", callback_data="admin_files"),
        ],
        [
            InlineKeyboardButton("☁️ التخزين", callback_data="storage_menu"),
            InlineKeyboardButton("👥 المستخدمون", callback_data="admin_users"),
        ],
        [InlineKeyboardButton("🔙 رجوع", callback_data="admin_panel")],
    ])


def back_button(callback: str = "main_menu") -> List[List[InlineKeyboardButton]]:
    return [[InlineKeyboardButton("🔙 رجوع", callback_data=callback)]]


def quran_menu() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🟢 شيوخ العصر الحديث", callback_data="lib_cat:modern")],
        [InlineKeyboardButton("🟤 شيوخ العصر القديم", callback_data="lib_cat:classic")],
        [InlineKeyboardButton("📚 إذاعات القرآن الكريم", callback_data="lib_cat:radio_quran")],
        [InlineKeyboardButton("🤲 الرقية والأذكار", callback_data="lib_cat:islamic")],
        [InlineKeyboardButton("🔙 رجوع", callback_data="main_menu")],
    ])


def music_menu() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🎤 المطربين", callback_data="lib_cat:music_artists")],
        [InlineKeyboardButton("📻 المحطات الموسيقية", callback_data="lib_cat:music_radios")],
        [InlineKeyboardButton("🔙 رجوع", callback_data="main_menu")],
    ])


def library_items_keyboard(category_type: str, page: int = 1, per_page: int = 8) -> InlineKeyboardMarkup:
    lib = load_library()
    category = next((c for c in lib.get("categories", []) if c["type"] == category_type), None)
    if not category:
        return InlineKeyboardMarkup(back_button("main_menu"))
    items = category.get("items", [])
    total = len(items)
    total_pages = max(1, (total + per_page - 1) // per_page)
    page = max(1, min(page, total_pages))
    start = (page - 1) * per_page
    page_items = items[start:start + per_page]
    # إيموجي حسب التصنيف بدون إظهار الروابط
    emoji_map = {
        "modern": "🕌", "classic": "🕌", "radio_quran": "📻", "islamic": "🤲",
        "music_artists": "🎤", "music_radios": "🎵",
    }
    emoji = emoji_map.get(category_type, "▶️")
    buttons = []
    for idx, item in enumerate(page_items):
        global_idx = start + idx
        buttons.append([
            InlineKeyboardButton(f"{emoji} {item['name']}", callback_data=f"play_lib:{category_type}:{global_idx}")
        ])
    nav = []
    if page > 1:
        nav.append(InlineKeyboardButton("⬅️", callback_data=f"lib_page:{category_type}:{page-1}"))
    nav.append(InlineKeyboardButton(f"{page}/{total_pages}", callback_data="noop"))
    if page < total_pages:
        nav.append(InlineKeyboardButton("➡️", callback_data=f"lib_page:{category_type}:{page+1}"))
    if nav:
        buttons.append(nav)
    parent = "quran_menu" if category_type in ("modern", "classic", "radio_quran", "islamic") else "music_menu"
    buttons.append([InlineKeyboardButton("🔙 رجوع", callback_data=parent)])
    return InlineKeyboardMarkup(buttons)


def my_files_keyboard(files: list, page: int = 1, per_page: int = 6) -> InlineKeyboardMarkup:
    total = len(files)
    total_pages = max(1, (total + per_page - 1) // per_page)
    page = max(1, min(page, total_pages))
    start = (page - 1) * per_page
    page_files = files[start:start + per_page]
    buttons = []
    for f in page_files:
        buttons.append([InlineKeyboardButton(f"📄 {f['file_name'][:30]}", callback_data=f"file_info:{f['id']}")])
    nav = []
    if page > 1:
        nav.append(InlineKeyboardButton("⬅️", callback_data=f"files_page:{page-1}"))
    if total_pages > 1:
        nav.append(InlineKeyboardButton(f"{page}/{total_pages}", callback_data="noop"))
    if page < total_pages:
        nav.append(InlineKeyboardButton("➡️", callback_data=f"files_page:{page+1}"))
    if nav:
        buttons.append(nav)
    buttons.append([InlineKeyboardButton("🔙 رجوع", callback_data="main_menu")])
    return InlineKeyboardMarkup(buttons)


def file_actions_keyboard(file_id: int, is_admin: bool = False) -> InlineKeyboardMarkup:
    rows = [
        [InlineKeyboardButton("▶️ تشغيل", callback_data=f"file_play:{file_id}")],
    ]
    if is_admin:
        rows.append([InlineKeyboardButton("🔗 نسخ الرابط", callback_data=f"file_link:{file_id}")])
    else:
        rows.append([InlineKeyboardButton("🔒 الرابط (أدمن فقط)", callback_data="link_hidden")])
    rows.append([InlineKeyboardButton("🗑 حذف", callback_data=f"file_delete:{file_id}")])
    rows.append([InlineKeyboardButton("🔙 رجوع", callback_data="my_files")])
    return InlineKeyboardMarkup(rows)


def stream_actions_keyboard(stream_id: int, is_running: bool, can_control: bool = True) -> InlineKeyboardMarkup:
    """Rich control panel — legacy V6 ecosystem (logs/stats/clone/fav) merged
    with the current playlist/volume/bitrate controls. Nothing removed."""
    sid = stream_id
    if not can_control:
        return InlineKeyboardMarkup([
            [InlineKeyboardButton("📊 تحديث الحالة", callback_data=f"stream_status:{sid}")],
            [InlineKeyboardButton("🔙 البثوث الحالية", callback_data="current_stream")],
        ])
    control_row = (
        [InlineKeyboardButton("⏹ إيقاف", callback_data=f"stream_stop:{sid}"),
         InlineKeyboardButton("🔄 إعادة", callback_data=f"stream_restart:{sid}")]
        if is_running else
        [InlineKeyboardButton("▶️ تشغيل", callback_data=f"stream_start:{sid}"),
         InlineKeyboardButton("🔄 إعادة", callback_data=f"stream_restart:{sid}")]
    )
    buttons = [
        control_row,
        [
            InlineKeyboardButton("📜 سجلات", callback_data=f"stream_logs:{sid}"),
            InlineKeyboardButton("📈 إحصائيات", callback_data=f"stream_stats:{sid}"),
        ],
        [
            InlineKeyboardButton("📋 استنساخ", callback_data=f"stream_clone:{sid}"),
            InlineKeyboardButton("⭐ مفضلة", callback_data=f"stream_fav:{sid}"),
        ],
        [
            InlineKeyboardButton("⬅️ السابق", callback_data=f"pl_prev:{sid}"),
            InlineKeyboardButton("📃 القائمة", callback_data=f"pl_view:{sid}"),
            InlineKeyboardButton("➡️ التالي", callback_data=f"pl_next:{sid}"),
        ],
        [
            InlineKeyboardButton("🔀 عشوائي", callback_data=f"pl_shuffle:{sid}"),
            InlineKeyboardButton("🔁 تكرار", callback_data=f"pl_loop:{sid}"),
        ],
        [
            InlineKeyboardButton("🔊 +", callback_data=f"stream_vol_up:{sid}"),
            InlineKeyboardButton("🔉 -", callback_data=f"stream_vol_down:{sid}"),
            InlineKeyboardButton("🔇 كتم", callback_data=f"stream_mute:{sid}"),
        ],
        [
            InlineKeyboardButton("64k", callback_data=f"stream_br:{sid}:64k"),
            InlineKeyboardButton("128k ⭐", callback_data=f"stream_br:{sid}:128k"),
            InlineKeyboardButton("192k", callback_data=f"stream_br:{sid}:192k"),
        ],
        [InlineKeyboardButton("📊 تحديث الحالة", callback_data=f"stream_status:{sid}")],
        [InlineKeyboardButton("📚 أرشفة الفيديو", callback_data=f"arch_stream:{sid}")],
        [InlineKeyboardButton("🗑 حذف البث", callback_data=f"stream_delete:{sid}")],
        [InlineKeyboardButton("🔙 رجوع", callback_data="current_stream")],
    ]
    return InlineKeyboardMarkup(buttons)


def cancel_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([[InlineKeyboardButton("❌ إلغاء", callback_data="cancel")]])


def confirm_delete_keyboard(file_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("✅ نعم احذف", callback_data=f"file_delete_confirm:{file_id}"),
            InlineKeyboardButton("❌ لا", callback_data=f"file_info:{file_id}"),
        ]
    ])


def section_cinema_menu() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🎬 الأفلام", callback_data="cinema_list:movie"),
         InlineKeyboardButton("🎞 المسلسلات", callback_data="cinema_list:series")],
        [InlineKeyboardButton("🎌 الأنمي", callback_data="cinema_list:anime"),
         InlineKeyboardButton("🧒 الكرتون", callback_data="cinema_src:cartoon")],
        [InlineKeyboardButton("🥊 المصارعة", callback_data="cinema_src:wrestling")],
        [InlineKeyboardButton("🔥 الأكثر مشاهدة", callback_data="cinema_src:most"),
         InlineKeyboardButton("⭐ الأعلى تقييماً", callback_data="cinema_src:top")],
        [InlineKeyboardButton("🆕 الأحدث", callback_data="cinema_src:latest"),
         InlineKeyboardButton("🎭 التصنيفات", callback_data="cinema_src:genres")],
        [InlineKeyboardButton("📅 حسب السنة", callback_data="cinema_src:year"),
         InlineKeyboardButton("🔍 البحث", callback_data="cinema_search")],
        [InlineKeyboardButton("⭐ المفضلة", callback_data="favorites_menu"),
         InlineKeyboardButton("🕒 المشاهدة الأخيرة", callback_data="cinema_recent")],
        [InlineKeyboardButton("🔙 القائمة الرئيسية", callback_data="main_menu")],
    ])


def section_stream_menu() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📡 البث الحالي", callback_data="current_stream"),
         InlineKeyboardButton("🚀 إنشاء بث", callback_data="stream_new")],
        [InlineKeyboardButton("📜 سجل البثوث", callback_data="stream_history"),
         InlineKeyboardButton("📺 IPTV", callback_data="iptv_menu")],
        [InlineKeyboardButton("🔎 استخراج بث", callback_data="extract_menu"),
         InlineKeyboardButton("🧪 اختبار مصدر", callback_data="test_source")],
        [InlineKeyboardButton("⚙️ إعدادات RTMP", callback_data="rtmp_settings")],
        [InlineKeyboardButton("🔙 القائمة الرئيسية", callback_data="main_menu")],
    ])


def section_radio_menu() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📺 المحطات / القنوات", callback_data="stations_menu")],
        [InlineKeyboardButton("📻 الإذاعات", callback_data="stations_menu"),
         InlineKeyboardButton("🎵 الموسيقى", callback_data="music_menu")],
        [InlineKeyboardButton("📖 القرآن / الشيوخ", callback_data="quran_menu")],
        [InlineKeyboardButton("⭐ المفضلة", callback_data="favorites_menu"),
         InlineKeyboardButton("🕒 الأخيرة", callback_data="radio_recent")],
        [InlineKeyboardButton("🔙 القائمة الرئيسية", callback_data="main_menu")],
    ])


def section_audio_menu() -> InlineKeyboardMarkup:
    return section_radio_menu()


def section_iptv_menu() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📂 مصادر IPTV", callback_data="iptv_menu")],
        [InlineKeyboardButton("🔗 إضافة M3U", callback_data="iptv_import")],
        [InlineKeyboardButton("⭐ المفضلة", callback_data="favorites_menu"),
         InlineKeyboardButton("🔍 بحث", callback_data="iptv_search")],
        [InlineKeyboardButton("🔎 استخراج بث", callback_data="extract_menu"),
         InlineKeyboardButton("🧪 اختبار مصدر", callback_data="test_source")],
        [InlineKeyboardButton("🔙 القائمة الرئيسية", callback_data="main_menu")],
    ])


def section_tools_menu() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("☁️ التخزين", callback_data="storage_menu"),
         InlineKeyboardButton("📂 ملفاتي", callback_data="my_files")],
        [InlineKeyboardButton("🔎 استخراج بث", callback_data="extract_menu"),
         InlineKeyboardButton("🧪 اختبار مصدر", callback_data="test_source")],
        [InlineKeyboardButton("💬 شرح البوت", callback_data="help_assistant")],
        [InlineKeyboardButton("🔙 القائمة الرئيسية", callback_data="main_menu")],
    ])


def section_account_menu() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📂 ملفاتي", callback_data="my_files"),
         InlineKeyboardButton("⭐ المفضلة", callback_data="favorites_menu")],
        [InlineKeyboardButton("☁️ التخزين", callback_data="storage_menu"),
         InlineKeyboardButton("⚙️ الإعدادات", callback_data="settings")],
        [InlineKeyboardButton("👤 حسابي", callback_data="my_account"),
         InlineKeyboardButton("ℹ️ عن البوت", callback_data="about_bot")],
        [InlineKeyboardButton("🔙 القائمة الرئيسية", callback_data="main_menu")],
    ])


def rtmp_confirm_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("✅ نعم — استخدم المحفوظ", callback_data="rtmp_use_saved")],
        [InlineKeyboardButton("🔄 تغيير", callback_data="rtmp_change"),
         InlineKeyboardButton("⏭ تخطي", callback_data="rtmp_skip")],
        [InlineKeyboardButton("❌ إلغاء", callback_data="cancel")],
    ])


def probe_continue_keyboard(ok: bool = True) -> InlineKeyboardMarkup:
    rows = []
    if ok:
        rows.append([InlineKeyboardButton("✅ متابعة البث", callback_data="probe_continue")])
    rows.append([
        InlineKeyboardButton("🔄 إعادة الفحص", callback_data="probe_retry"),
        InlineKeyboardButton("❌ إلغاء", callback_data="cancel"),
    ])
    return InlineKeyboardMarkup(rows)

