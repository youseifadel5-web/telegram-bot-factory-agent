from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from typing import List, Dict


def my_files_keyboard(files: List[Dict], page: int = 0, per_page: int = 6) -> InlineKeyboardMarkup:
    total = len(files)
    total_pages = max(1, (total + per_page - 1) // per_page)
    page = max(0, min(page, total_pages - 1))
    start = page * per_page
    end = start + per_page
    page_files = files[start:end]

    buttons = []
    for f in page_files:
        size_mb = f.get("file_size", 0) / (1024 * 1024)
        name = f.get("file_name", "file")[:30]
        buttons.append([
            InlineKeyboardButton(
                f"📄 {name} ({size_mb:.1f} MB)",
                callback_data=f"file_view_{f['id']}"
            )
        ])

    nav = []
    if page > 0:
        nav.append(InlineKeyboardButton("◀️ السابق", callback_data=f"files_page_{page-1}"))
    if page < total_pages - 1:
        nav.append(InlineKeyboardButton("التالي ▶️", callback_data=f"files_page_{page+1}"))
    if nav:
        buttons.append(nav)

    buttons.append([
        InlineKeyboardButton("⬆️ رفع ملف جديد", callback_data="upload_file"),
        InlineKeyboardButton("🔙 رجوع", callback_data="main_menu"),
    ])
    return InlineKeyboardMarkup(buttons)


def file_actions_keyboard(file_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("▶️ تشغيل", callback_data=f"file_play_{file_id}"),
            InlineKeyboardButton("🔗 نسخ الرابط", callback_data=f"file_link_{file_id}"),
        ],
        [
            InlineKeyboardButton("🗑 حذف", callback_data=f"file_delete_{file_id}"),
        ],
        [
            InlineKeyboardButton("🔙 رجوع", callback_data="my_files"),
        ],
    ])


def upload_prompt_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🔙 إلغاء", callback_data="my_files")]
    ])
