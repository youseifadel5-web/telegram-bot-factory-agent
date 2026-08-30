# -*- coding: utf-8 -*-
"""
Unified launcher with one primary bot and one-file Add bot plugins.

One BOT_TOKEN / API_ID / API_HASH / ADMIN_ID / TMDB_API_KEY.
Only one getUpdates poller is used. Updates are routed to exactly one
system at a time so handlers and callback namespaces do not interfere.
"""
import asyncio
import json
import logging
import os
from pathlib import Path

from telebot.types import Update as TeleUpdate
import requests

import cinema_core as cinema
import youseif_core as youseif
from plugin_loader import discover_plugins

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
log = logging.getLogger("merged-bot")

BOT_TOKEN = os.getenv("BOT_TOKEN", "").strip()
if not BOT_TOKEN:
    raise RuntimeError("BOT_TOKEN is missing")

# Keep both systems on the same shared secrets.
# youseif_core already reads these from os.environ; cinema_core uses BOT_TOKEN.
# ADMIN_ID is consumed by youseif_core and is also exposed for the cinema module.
try:
    admin_raw = os.getenv("ADMIN_ID", "").strip()
    if admin_raw:
        cinema.ADMIN_ID = int(admin_raw)
        cinema.ADMIN_IDS = [cinema.ADMIN_ID]
except Exception:
    pass

# Session mode: a user stays inside the interface they entered.
# "cinema" = existing Cinema Bot.py system, "youseif" = imported PTB system.
USER_MODE = {}
CINEMA_WAITING = set()
# البحث الموحد: يشمل مصدري Cinema + نظام Youseif الثالث.
GLOBAL_SEARCH_WAITING = set()
GLOBAL_SEARCH_STATE = {}
PLUGIN_SEARCH_STATE = {}

# PTB application is used only as an update processor; it does NOT poll.
PTB_APP = None
PTB_BOT = None
YOUSEIF = None
PLUGINS = {}
PLUGIN_STATE_FILE = Path(__file__).resolve().parent / "plugins_state.json"
PLUGIN_ENABLED = {}

YOUSEIF_CALLBACK_PREFIXES = (
    "main", "t:", "qk:", "hg:", "hc:", "hi:", "lt:", "lp:", "li:",
    "g:", "gp:", "c:", "i:", "f:", "w:", "s:", "e:", "p:",
    "act:", "adm:", "sr:",
)


def is_youseif_callback(data: str) -> bool:
    data = data or ""
    return data == "noop" or data.startswith(YOUSEIF_CALLBACK_PREFIXES)


def _jsonable_update(value):
    """Convert a pyTelegramBotAPI Update (and nested objects) to a plain dict.

    pyTelegramBotAPI versions differ: some Update objects expose to_dict()/to_json(),
    while others only expose normal Python attributes. Never parse str(update) as JSON;
    its repr uses single quotes and is not valid JSON.
    """
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, dict):
        return {str(k): _jsonable_update(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_jsonable_update(v) for v in value]
    if hasattr(value, "to_dict"):
        try:
            return _jsonable_update(value.to_dict())
        except Exception:
            pass
    if hasattr(value, "to_json"):
        try:
            return json.loads(value.to_json())
        except Exception:
            pass
    try:
        attrs = vars(value)
    except TypeError:
        attrs = {}
    if attrs:
        return {k: _jsonable_update(v) for k, v in attrs.items() if not k.startswith("_")}

    # Last-resort field extraction for objects implemented with __slots__.
    fields = (
        "update_id", "message", "edited_message", "channel_post",
        "edited_channel_post", "inline_query", "chosen_inline_result",
        "callback_query", "shipping_query", "pre_checkout_query",
        "poll", "poll_answer", "my_chat_member", "chat_member",
        "chat_join_request", "message_reaction", "message_reaction_count",
        "business_connection", "business_message", "edited_business_message",
        "deleted_business_messages", "purchased_paid_media",
    )
    out = {}
    for name in fields:
        if hasattr(value, name):
            item = getattr(value, name)
            if item is not None:
                out[name] = _jsonable_update(item)
    return out


def raw_update(update):
    raw = _jsonable_update(update)
    if not isinstance(raw, dict):
        raise TypeError(f"Unsupported Telegram update type: {type(update).__name__}")
    return raw


def tele_update_id(update):
    return int(getattr(update, "update_id", 0))


def update_user_id(update):
    try:
        if getattr(update, "message", None):
            return update.message.from_user.id
        if getattr(update, "callback_query", None):
            return update.callback_query.from_user.id
    except Exception:
        pass
    return None


def is_callback(update):
    return bool(getattr(update, "callback_query", None))


def message_text(update):
    msg = getattr(update, "message", None)
    return (getattr(msg, "text", None) or "").strip() if msg else ""


def mark_cinema_waiting():
    """Wrap TeleBot next-step registration so routed text does not leak to PTB."""
    original = cinema.bot.register_next_step_handler

    def tracked(message, callback, *args, **kwargs):
        try:
            uid = message.chat.id
            CINEMA_WAITING.add(uid)
        except Exception:
            pass
        return original(message, callback, *args, **kwargs)

    cinema.bot.register_next_step_handler = tracked


async def send_youseif_start(user_id: int, chat_id: int, first_name: str = ""):
    # Use the exact existing PTB menu/text, but send it directly so /start remains
    # the original Cinema entry point and no duplicate command handler is created.
    try:
        YOUSEIF.db.add_user(user_id, None, first_name)
        if youseif.is_admin(user_id):
            YOUSEIF.db.get_or_create_adult_password()
        await PTB_BOT.send_message(
            chat_id=chat_id,
            text=(
                "✨🎬 <b>𝑌𝑜𝑢𝑠𝑒𝑖𝑓 𝐹𝑖𝑙𝑚𝑠</b> 🎬✨\n"
                "━━━━━━━━━━━━━━━\n"
                f"👋 أهلاً <b>{youseif.esc(first_name or 'بك')}</b>\n"
                "🍿 <i>أفلام • مسلسلات • قنوات مباشرة — بجودة عالمية</i>\n"
                "━━━━━━━━━━━━━━━\n"
                "👇 <b>اختر من القائمة:</b>"
            ),
            parse_mode=youseif.ParseMode.HTML,
            reply_markup=youseif.main_menu_kb(user_id),
        )
    except Exception:
        log.exception("Failed to open Youseif interface")



def _youseif_search_groups(results):
    grouped = {"movie": [], "series": [], "live": []}
    for item_type, item in results or []:
        if item_type in grouped:
            grouped[item_type].append(item)
    return grouped


def _merged_search_keyboard(results):
    """يعرض مصادر البحث الثلاثة بدون تغيير واجهة أي نظام داخلي."""
    from telebot import types
    markup = types.InlineKeyboardMarkup(row_width=2)
    labels = (
        ("nova", "🌟 سينما نوفا"),
        ("orion", "🎞️ أوريون بلس"),
        ("youseif", "🎬 Youseif Films"),
    )
    for source, title in labels:
        data = results.get(source, {})
        if source == "youseif":
            counts = (len(data.get("movie", [])), len(data.get("series", [])), len(data.get("live", [])))
            markup.add(types.InlineKeyboardButton(f"{title} ({sum(counts)})", callback_data="merged3:source:youseif"))
        else:
            markup.add(types.InlineKeyboardButton(f"{title} ({data.get('total', 0)})", callback_data=f"merged3:source:{source}"))
    markup.add(types.InlineKeyboardButton("🏠 بوت سينماء", callback_data="hub_home"))
    return markup


def _merged_source_keyboard(source, data):
    from telebot import types
    markup = types.InlineKeyboardMarkup(row_width=2)
    if source == "nova":
        if data.get("movies"): markup.add(types.InlineKeyboardButton(f"🎬 أفلام ({len(data['movies'])})", callback_data="unified_list:nova:m"))
        if data.get("series"): markup.add(types.InlineKeyboardButton(f"📺 مسلسلات ({len(data['series'])})", callback_data="unified_list:nova:s"))
    elif source == "orion":
        if data.get("movies"): markup.add(types.InlineKeyboardButton(f"🎬 أفلام ({len(data['movies'])})", callback_data="unified_list:orion:m"))
        if data.get("series"): markup.add(types.InlineKeyboardButton(f"📺 مسلسلات ({len(data['series'])})", callback_data="unified_list:orion:s"))
    else:
        if data.get("movie"): markup.add(types.InlineKeyboardButton(f"🎬 أفلام ({len(data['movie'])})", callback_data="merged3:list:movie"))
        if data.get("series"): markup.add(types.InlineKeyboardButton(f"📺 مسلسلات ({len(data['series'])})", callback_data="merged3:list:series"))
        if data.get("live"): markup.add(types.InlineKeyboardButton(f"📡 قنوات ({len(data['live'])})", callback_data="merged3:list:live"))
    markup.add(types.InlineKeyboardButton("🔙 رجوع لنتائج البحث", callback_data="merged3:back"))
    markup.add(types.InlineKeyboardButton("🏠 بوت سينماء", callback_data="hub_home"))
    return markup


def _merged_search_results(query, cinema_results, youseif_groups):
    return {
        "nova": {"movies": cinema_results.get("nova_movies", []), "series": cinema_results.get("nova_series", []),
                 "total": len(cinema_results.get("nova_movies", [])) + len(cinema_results.get("nova_series", []))},
        "orion": {"movies": cinema_results.get("orion_movies", []), "series": cinema_results.get("orion_series", []),
                  "total": len(cinema_results.get("orion_movies", [])) + len(cinema_results.get("orion_series", []))},
        "youseif": youseif_groups,
        "query": query,
    }



def _plugin_search(query, context):
    """Run every loaded plugin's optional search() hook."""
    out = {}
    for pid, mod in PLUGINS.items():
        if not _plugin_is_enabled(pid):
            continue
        fn = getattr(mod, "search", None)
        if not callable(fn):
            continue
        try:
            result = fn(query, context)
            if hasattr(result, "__await__"):
                # Caller is async; handled in process_global_search.
                out[pid] = result
            else:
                out[pid] = result or {}
        except Exception:
            log.exception("Plugin search failed: %s", pid)
            out[pid] = {}
    return out


async def _plugin_search_async(query, context):
    out = {}
    for pid, mod in PLUGINS.items():
        if not _plugin_is_enabled(pid):
            continue
        fn = getattr(mod, "search", None)
        if not callable(fn):
            continue
        try:
            result = fn(query, context)
            if hasattr(result, "__await__"):
                result = await result
            out[pid] = result or {}
        except Exception:
            log.exception("Plugin search failed: %s", pid)
            out[pid] = {}
    return out


def _generic_search_total(item):
    if isinstance(item, dict):
        total = item.get("total")
        if isinstance(total, int):
            return total
        return sum(len(v) for v in item.values() if isinstance(v, list))
    if isinstance(item, list):
        return len(item)
    return 0


def _ptb_generic_search_keyboard(state):
    from telegram import InlineKeyboardButton, InlineKeyboardMarkup
    rows=[]
    for pid, mod in PLUGINS.items():
        data = state.get("plugins", {}).get(pid, {})
        total = _generic_search_total(data)
        if total:
            label = str(getattr(mod, "PLUGIN_BUTTON", getattr(mod, "PLUGIN_NAME", pid)))
            rows.append([InlineKeyboardButton(f"{label} ({total})", callback_data=f"psearch:source:{pid}")])
    if not rows:
        rows.append([InlineKeyboardButton("❌ لا توجد نتائج", callback_data="noop")])
    rows.append([InlineKeyboardButton("🏠 بوت سينماء", callback_data="hub_home")])
    return InlineKeyboardMarkup(rows)

async def process_global_search(chat_id, user_id, query, message_id=None):
    """بحث واحد في الأنظمة الثلاثة؛ فتح النتائج يظل بــcallback الخاص بصاحبها."""
    query = (query or "").strip()[:80]
    if len(query) < 2:
        await PTB_BOT.send_message(chat_id, "❌ اكتب اسمًا من حرفين على الأقل للبحث.")
        return
    plugin_results = await _plugin_search_async(query, {**addbot_context(user_id), "youseif_store": YOUSEIF.store})
    state = {"query": query, "plugins": plugin_results}
    GLOBAL_SEARCH_STATE[user_id] = state
    total = sum(_generic_search_total(v) for v in plugin_results.values())
    text = (
        f"🔍✨ <b>نتائج البحث عن «{youseif.esc(query)}»</b> ✨\n"
        "━━━━━━━━━━━━━━━\n"
        f"📦 <b>إجمالي النتائج: {total}</b>\n\n"
        "اختر البوت لعرض نتائجه:"
    )
    if message_id:
        try:
            await PTB_BOT.edit_message_text(chat_id=chat_id, message_id=message_id, text=text, parse_mode=youseif.ParseMode.HTML, reply_markup=_ptb_generic_search_keyboard(state))
            return
        except Exception:
            pass
    await PTB_BOT.send_message(chat_id, text, parse_mode=youseif.ParseMode.HTML, reply_markup=_ptb_generic_search_keyboard(state))


def _ptb_merged_search_keyboard(state):
    from telegram import InlineKeyboardButton, InlineKeyboardMarkup
    rows=[]
    for source,title in (("nova","🌟 سينما نوفا"),("orion","🎞️ أوريون بلس"),("youseif","🎬 Youseif Films")):
        d=state[source]
        total=(d.get("total",0) if source != "youseif" else sum(len(d.get(t,[])) for t in ("movie","series","live")))
        rows.append([InlineKeyboardButton(f"{title} ({total})", callback_data=f"merged3:source:{source}")])
    rows.append([InlineKeyboardButton("🏠 بوت سينماء", callback_data="hub_home")])
    return InlineKeyboardMarkup(rows)


def _ptb_source_keyboard(source, data):
    from telegram import InlineKeyboardButton, InlineKeyboardMarkup
    rows=[]
    if source in ("nova","orion"):
        if data.get("movies"): rows.append([InlineKeyboardButton(f"🎬 أفلام ({len(data['movies'])})", callback_data=f"unified_list:{source}:m")])
        if data.get("series"): rows.append([InlineKeyboardButton(f"📺 مسلسلات ({len(data['series'])})", callback_data=f"unified_list:{source}:s")])
    else:
        if data.get("movie"): rows.append([InlineKeyboardButton(f"🎬 أفلام ({len(data['movie'])})", callback_data="merged3:list:movie")])
        if data.get("series"): rows.append([InlineKeyboardButton(f"📺 مسلسلات ({len(data['series'])})", callback_data="merged3:list:series")])
        if data.get("live"): rows.append([InlineKeyboardButton(f"📡 قنوات ({len(data['live'])})", callback_data="merged3:list:live")])
    rows += [[InlineKeyboardButton("🔙 نتائج البحث", callback_data="merged3:back")],[InlineKeyboardButton("🏠 بوت سينماء", callback_data="hub_home")]]
    return InlineKeyboardMarkup(rows)


def _ptb_youseif_list_keyboard(items, item_type, page=0, per_page=10):
    from telegram import InlineKeyboardButton, InlineKeyboardMarkup
    start=page*per_page; chunk=items[start:start+per_page]
    rows=[]
    for it in chunk:
        key = "series_id" if item_type == "series" else "stream_id"
        iid=it.get(key)
        name=youseif.clean_name(it.get("name") or it.get("title") or "بدون اسم")
        rows.append([InlineKeyboardButton(f"{youseif.ITEM_ICON[item_type]} {name[:35]}", callback_data=f"i:{item_type}:{iid}:all:0")])
    pages=max(1,(len(items)+per_page-1)//per_page)
    if pages>1:
        nav=[]
        if page>0: nav.append(InlineKeyboardButton("◀️",callback_data=f"merged3:page:{item_type}:{page-1}"))
        nav.append(InlineKeyboardButton(f"{page+1}/{pages}",callback_data="noop"))
        if page<pages-1: nav.append(InlineKeyboardButton("▶️",callback_data=f"merged3:page:{item_type}:{page+1}"))
        rows.append(nav)
    rows += [[InlineKeyboardButton("🔙 نتائج البحث", callback_data="merged3:back")],[InlineKeyboardButton("🏠 بوت سينماء", callback_data="hub_home")]]
    return InlineKeyboardMarkup(rows)

def handle_special_command(update):
    text = message_text(update)
    if text.lower().split()[0] if text else "":
        cmd = text.split()[0].split("@")[0].lower()
    else:
        cmd = ""
    uid = update_user_id(update)
    msg = getattr(update, "message", None)
    if not uid or not msg:
        return False

    if cmd in ("/youseif", "/app", "/films"):
        USER_MODE[uid] = "youseif"
        asyncio.create_task(send_youseif_start(uid, msg.chat.id, msg.from_user.first_name or ""))
        return True

    return False


async def process_youseif(update):
    global PTB_APP
    raw = raw_update(update)
    ptb_update = youseif.Update.de_json(raw, PTB_BOT)
    if ptb_update is not None:
        await PTB_APP.process_update(ptb_update)



def _load_plugin_state():
    global PLUGIN_ENABLED
    try:
        data = json.loads(PLUGIN_STATE_FILE.read_text(encoding="utf-8"))
        PLUGIN_ENABLED = {str(k): bool(v) for k, v in data.items()} if isinstance(data, dict) else {}
    except Exception:
        PLUGIN_ENABLED = {}


def _save_plugin_state():
    try:
        PLUGIN_STATE_FILE.write_text(json.dumps(PLUGIN_ENABLED, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception:
        log.exception("Could not save plugin state")


def _plugin_is_enabled(pid):
    return PLUGIN_ENABLED.get(pid, True)


def _hub_keyboard_for(uid):
    from telegram import InlineKeyboardButton, InlineKeyboardMarkup
    rows = [
        [InlineKeyboardButton("🎬 بوت سينماء", callback_data="addbot:menu")],
        [InlineKeyboardButton("🔍 بحث", callback_data="unified_search")],
    ]
    if uid and youseif.is_admin(uid):
        rows.append([InlineKeyboardButton("👑 لوحة التحكم", callback_data="admin:menu")])
    return InlineKeyboardMarkup(rows)


async def _show_external_admin(q, uid):
    from telegram import InlineKeyboardButton, InlineKeyboardMarkup
    if not youseif.is_admin(uid):
        await q.answer("غير مصرح", show_alert=True)
        return True
    rows = []
    for pid, mod in PLUGINS.items():
        status = "🟢" if _plugin_is_enabled(pid) else "🔴"
        name = str(getattr(mod, "PLUGIN_NAME", pid))
        rows.append([InlineKeyboardButton(f"{status} {name}", callback_data=f"admin:toggle:{pid}")])
    rows.append([InlineKeyboardButton("🔄 إعادة تحميل البوتات", callback_data="admin:reload")])
    rows.append([InlineKeyboardButton("🔙 بوت سينماء", callback_data="hub_home")])
    await q.edit_message_text("👑 <b>لوحة التحكم</b>\n\nتحكم في البوتات المضافة:", parse_mode=youseif.ParseMode.HTML, reply_markup=InlineKeyboardMarkup(rows))
    return True


def addbot_keyboard():
    """القائمة الديناميكية لكل البوتات الموجودة داخل Add bot."""
    from telebot import types
    markup = types.InlineKeyboardMarkup(row_width=1)
    for pid, mod in PLUGINS.items():
        if not _plugin_is_enabled(pid):
            continue
        label = str(getattr(mod, "PLUGIN_BUTTON", getattr(mod, "PLUGIN_NAME", pid)))
        markup.add(types.InlineKeyboardButton(label, callback_data=f"addbot:open:{pid}"))
    markup.add(types.InlineKeyboardButton("🔙 رجوع", callback_data="addbot:back"))
    return markup


def addbot_context(uid):
    return {
        "user_id": uid,
        "cinema": cinema,
        "youseif": youseif,
        "ptb_bot": PTB_BOT,
        "ptb_app": PTB_APP,
        "user_mode": USER_MODE,
    }


async def handle_addbot_callback(upd, uid, data):
    """يعالج بوابة Add bot فقط، ثم يسلّم البوت المحدد لواجهته الأصلية."""
    q = getattr(upd, "callback_query", None)
    if not q or not getattr(q, "message", None):
        return True
    chat_id = q.message.chat.id
    msg_id = q.message.message_id
    try:
        await q.answer()
    except Exception:
        pass

    if data == "addbot:menu":
        await PTB_BOT.edit_message_text(
            chat_id=chat_id,
            message_id=msg_id,
            text="🎬 <b>بوت سينماء</b>\n\nاختر البوت الذي تريد فتحه:",
            parse_mode=youseif.ParseMode.HTML,
            reply_markup=_ptb_addbot_keyboard(),
        )
        return True

    if data == "addbot:back":
        # نرجع للبوابة الأصلية بنفس زر Add bot + البحث.
        cinema.bot.process_new_updates([upd])
        return True

    parts = data.split(":", 2)
    if len(parts) != 3 or parts[1] != "open":
        return True
    pid = parts[2]
    mod = PLUGINS.get(pid)
    if not mod:
        await PTB_BOT.send_message(chat_id, "❌ الإضافة غير موجودة أو لم يتم تحميلها.")
        return True

    result = None
    try:
        result = mod.open_plugin(q, addbot_context(uid))
        if hasattr(result, "__await__"):
            result = await result
    except Exception:
        log.exception("Add bot plugin failed: %s", pid)
        await PTB_BOT.send_message(chat_id, "❌ تعذر تشغيل البوت. راجع ملف bot.py الخاص به.")
        return True

    if result == "youseif":
        USER_MODE[uid] = "youseif"
        await send_youseif_start(uid, chat_id, getattr(q.from_user, "first_name", "") or "")
    elif isinstance(result, str) and result.startswith("cinema:"):
        USER_MODE[uid] = "cinema"
        q.data = result.split(":", 1)[1]
        cinema.handle_callbacks(q)
    return True


def _ptb_addbot_keyboard():
    from telegram import InlineKeyboardButton, InlineKeyboardMarkup
    rows = []
    for pid, mod in PLUGINS.items():
        if not _plugin_is_enabled(pid):
            continue
        label = str(getattr(mod, "PLUGIN_BUTTON", getattr(mod, "PLUGIN_NAME", pid)))
        rows.append([InlineKeyboardButton(label, callback_data=f"addbot:open:{pid}")])
    rows.append([InlineKeyboardButton("🔙 رجوع", callback_data="addbot:back")])
    return InlineKeyboardMarkup(rows)


async def poll_loop():
    """Single raw Telegram getUpdates loop shared by all bot modules.

    We intentionally fetch raw JSON once, then create one Telegram Update object
    for pyTelegramBotAPI (Cinema) and one for python-telegram-bot (Youseif).
    This avoids converting pyTelegramBotAPI's Python repr back into JSON, which
    was the direct cause of the previous JSONDecodeError and dead callbacks.
    """
    global PLUGINS
    offset = None
    retry = 2
    loop = asyncio.get_running_loop()
    api_url = f"https://api.telegram.org/bot{BOT_TOKEN}/getUpdates"

    def fetch_raw():
        # Do not restrict allowed_updates: the original bot can use any update
        # type in the future, and the shared poller should preserve that ability.
        payload = {"timeout": 30}
        if offset is not None:
            payload["offset"] = offset
        r = requests.post(api_url, json=payload, timeout=45)
        r.raise_for_status()
        body = r.json()
        if not body.get("ok"):
            raise RuntimeError(body.get("description", "Telegram getUpdates failed"))
        return body.get("result", [])

    while True:
        try:
            raw_updates = await loop.run_in_executor(None, fetch_raw)
            retry = 2

            for raw in raw_updates:
                # Advance the cursor before dispatch. A broken update/plugin can
                # therefore never poison the whole bot and block every later update.
                try:
                    offset = int(raw.get("update_id", 0)) + 1
                except Exception:
                    pass

                try:
                    upd = TeleUpdate.de_json(json.dumps(raw, ensure_ascii=False), bot=cinema.bot)
                    if upd is None:
                        continue
                    uid = update_user_id(upd)

                    # Special entry command handled before either framework sees it.
                    if handle_special_command(upd):
                        continue

                    if is_callback(upd):
                        data = getattr(upd.callback_query, "data", "") or ""

                        # External admin panel — visible only to ADMIN_ID.
                        if data.startswith("admin:"):
                            q = upd.callback_query
                            if not uid or not youseif.is_admin(uid):
                                try:
                                    await q.answer("غير مصرح", show_alert=True)
                                except Exception:
                                    pass
                                continue
                            try:
                                await q.answer()
                            except Exception:
                                pass
                            if data == "admin:menu":
                                await _show_external_admin(q, uid)
                            elif data.startswith("admin:toggle:"):
                                pid = data.split(":", 2)[2]
                                if pid in PLUGINS:
                                    PLUGIN_ENABLED[pid] = not _plugin_is_enabled(pid)
                                    _save_plugin_state()
                                await _show_external_admin(q, uid)
                            elif data == "admin:reload":
                                # Refresh the global plugin registry in-place.
                                fresh = discover_plugins()
                                PLUGINS.clear()
                                PLUGINS.update(fresh)
                                for pid in PLUGINS:
                                    PLUGIN_ENABLED.setdefault(pid, True)
                                _save_plugin_state()
                                await _show_external_admin(q, uid)
                            continue

                        # Add-bot gateway only. The selected bot keeps its own UI.
                        if data.startswith("addbot:"):
                            await handle_addbot_callback(upd, uid, data)
                            continue

                        # Unified search.
                        if data == "unified_search":
                            GLOBAL_SEARCH_WAITING.add(uid)
                            try:
                                await upd.callback_query.answer()
                            except Exception:
                                pass
                            if uid and getattr(upd.callback_query, "message", None):
                                await PTB_BOT.send_message(
                                    chat_id=upd.callback_query.message.chat.id,
                                    text="🔍 <b>بحث</b>\n\nاكتب اسم الفيلم أو المسلسل أو القناة للبحث في الأنظمة الثلاثة:",
                                    parse_mode=youseif.ParseMode.HTML,
                                )
                            continue

                        # Keep all Youseif callbacks inside the original PTB router.
                        # No hard-coded callback-prefix whitelist is used here.
                        if uid and USER_MODE.get(uid) == "youseif":
                            await process_youseif(upd)
                        elif is_youseif_callback(data):
                            if uid:
                                USER_MODE[uid] = "youseif"
                            await process_youseif(upd)
                        else:
                            if uid:
                                USER_MODE[uid] = "cinema"
                            cinema.bot.process_new_updates([upd])
                        continue

                    text = message_text(upd)
                    if uid in GLOBAL_SEARCH_WAITING and text and not text.startswith("/"):
                        GLOBAL_SEARCH_WAITING.discard(uid)
                        await process_global_search(upd.message.chat.id, uid, text)
                        continue

                    if text.startswith("/"):
                        command = text.split()[0].split("@")[0].lower()
                        if command in {"/youseif", "/app", "/films"}:
                            if uid:
                                USER_MODE[uid] = "youseif"
                            await process_youseif(upd)
                        elif uid and USER_MODE.get(uid) == "youseif":
                            await process_youseif(upd)
                        else:
                            cinema.bot.process_new_updates([upd])
                        continue

                    mode = USER_MODE.get(uid, "cinema") if uid else "cinema"
                    if mode == "youseif" and uid not in CINEMA_WAITING:
                        await process_youseif(upd)
                    else:
                        cinema.bot.process_new_updates([upd])
                        CINEMA_WAITING.discard(uid)

                except Exception as update_exc:
                    # One bad update must never stop polling or affect later users.
                    log.exception("Update dispatch failed; continuing with next update: %s", update_exc)
                    continue

        except KeyboardInterrupt:
            raise
        except Exception as exc:
            log.exception("Polling/dispatch error: %s", exc)
            await asyncio.sleep(retry)
            retry = min(retry * 2, 30)


async def main():
    global PTB_APP, PTB_BOT, YOUSEIF, PLUGINS

    # Discover bot.py plugins from Add bot/ without starting another polling loop.
    PLUGINS = discover_plugins()
    _load_plugin_state()
    for _pid in PLUGINS:
        PLUGIN_ENABLED.setdefault(_pid, True)
    _save_plugin_state()
    log.info("Loaded Add bot plugins: %s", list(PLUGINS))

    # Instantiate the existing PTB system without calling its .run() method.
    YOUSEIF = youseif.CinemaBot()
    PTB_APP = youseif.Application.builder().token(BOT_TOKEN).build()
    PTB_BOT = PTB_APP.bot
    PTB_APP.add_handler(youseif.CommandHandler("start", YOUSEIF.cmd_start))
    PTB_APP.add_handler(youseif.CommandHandler("help", YOUSEIF.cmd_help))
    PTB_APP.add_handler(youseif.CommandHandler("stats", YOUSEIF.cmd_stats))
    PTB_APP.add_handler(youseif.CommandHandler("broadcast", YOUSEIF.cmd_broadcast))
    PTB_APP.add_handler(youseif.CallbackQueryHandler(YOUSEIF.on_callback))
    PTB_APP.add_handler(youseif.MessageHandler(youseif.filters.TEXT & ~youseif.filters.COMMAND, YOUSEIF.text_router))

    mark_cinema_waiting()

    await PTB_APP.initialize()
    await PTB_APP.start()
    # Warm/validate the original Youseif data layer without blocking startup.
    # The standalone bot used this hook; keeping it here restores its initial
    # source check while Telegram polling remains responsive.
    try:
        asyncio.create_task(YOUSEIF._post_init(PTB_APP))
    except Exception:
        log.exception("Youseif startup check could not be scheduled")
    try:
        await poll_loop()
    finally:
        await PTB_APP.stop()
        await PTB_APP.shutdown()


if __name__ == "__main__":
    asyncio.run(main())
