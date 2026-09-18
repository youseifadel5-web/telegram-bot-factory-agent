from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from typing import List, Dict


def stream_create_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🔗 رابط مباشر / HLS", callback_data="stream_source_direct")],
        [InlineKeyboardButton("📁 من ملفاتي", callback_data="stream_source_files")],
        [InlineKeyboardButton("🔙 رجوع", callback_data="main_menu")],
    ])


def current_streams_keyboard(streams: List[Dict]) -> InlineKeyboardMarkup:
    buttons = []
    for s in streams:
        status_emoji = "🟢" if s.get("status") == "running" else "🔴"
        title = (s.get("title") or "بث")[:25]
        buttons.append([
            InlineKeyboardButton(
                f"{status_emoji} {title}",
                callback_data=f"stream_status:{s['id']}"
            )
        ])
    if not buttons:
        buttons.append([InlineKeyboardButton("لا يوجد بث نشط", callback_data="noop")])
    buttons.append([
        InlineKeyboardButton("🚀 إنشاء بث جديد", callback_data="stream_new"),
        InlineKeyboardButton("🔙 رجوع", callback_data="main_menu"),
    ])
    return InlineKeyboardMarkup(buttons)


def stream_control_keyboard(stream_id: int, is_running: bool) -> InlineKeyboardMarkup:
    buttons = []
    if is_running:
        buttons.append([
            InlineKeyboardButton("⏹ إيقاف البث", callback_data=f"stream_stop:{stream_id}")
        ])
    else:
        buttons.append([
            InlineKeyboardButton("▶️ إعادة تشغيل", callback_data=f"stream_restart:{stream_id}")
        ])
    buttons.append([
        InlineKeyboardButton("🔙 رجوع", callback_data="current_stream")
    ])
    return InlineKeyboardMarkup(buttons)


def rtmp_input_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🔙 إلغاء", callback_data="stream_new")]
    ])
