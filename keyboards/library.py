import json
import os
from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from typing import List, Dict

LIBRARY_PATH = os.path.join(os.path.dirname(__file__), "..", "data", "library.json")


def load_library() -> Dict:
    with open(LIBRARY_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def quran_menu_keyboard() -> InlineKeyboardMarkup:
    data = load_library()
    buttons = []
    for cat in data["categories"]:
        if cat["type"] in ("modern", "classic", "radio_quran", "islamic"):
            buttons.append([
                InlineKeyboardButton(cat["name"], callback_data=f"lib_cat_{cat['type']}")
            ])
    buttons.append([InlineKeyboardButton("🔙 رجوع", callback_data="main_menu")])
    return InlineKeyboardMarkup(buttons)


def music_menu_keyboard() -> InlineKeyboardMarkup:
    data = load_library()
    buttons = []
    for cat in data["categories"]:
        if cat["type"] in ("music_artists", "music_radios"):
            buttons.append([
                InlineKeyboardButton(cat["name"], callback_data=f"lib_cat_{cat['type']}")
            ])
    buttons.append([InlineKeyboardButton("🔙 رجوع", callback_data="main_menu")])
    return InlineKeyboardMarkup(buttons)


def category_items_keyboard(cat_type: str, page: int = 0, per_page: int = 8) -> InlineKeyboardMarkup:
    data = load_library()
    category = next((c for c in data["categories"] if c["type"] == cat_type), None)
    if not category:
        return InlineKeyboardMarkup([[InlineKeyboardButton("🔙 رجوع", callback_data="main_menu")]])

    items = category["items"]
    total_pages = max(1, (len(items) + per_page - 1) // per_page)
    page = max(0, min(page, total_pages - 1))
    start = page * per_page
    end = start + per_page
    page_items = items[start:end]

    buttons = []
    for idx, item in enumerate(page_items):
        global_idx = start + idx
        buttons.append([
            InlineKeyboardButton(
                f"▶️ {item['name']}",
                callback_data=f"lib_play_{cat_type}_{global_idx}"
            )
        ])

    # Pagination
    nav = []
    if page > 0:
        nav.append(InlineKeyboardButton("◀️ السابق", callback_data=f"lib_page_{cat_type}_{page-1}"))
    if page < total_pages - 1:
        nav.append(InlineKeyboardButton("التالي ▶️", callback_data=f"lib_page_{cat_type}_{page+1}"))
    if nav:
        buttons.append(nav)

    # Back
    if cat_type in ("modern", "classic", "radio_quran", "islamic"):
        back_cb = "quran_menu"
    else:
        back_cb = "music_menu"
    buttons.append([InlineKeyboardButton("🔙 رجوع", callback_data=back_cb)])

    return InlineKeyboardMarkup(buttons)


def get_item_by_index(cat_type: str, index: int) -> Dict | None:
    data = load_library()
    category = next((c for c in data["categories"] if c["type"] == cat_type), None)
    if not category or index < 0 or index >= len(category["items"]):
        return None
    return category["items"][index]
