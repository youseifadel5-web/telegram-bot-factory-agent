# -*- coding: utf-8 -*-
"""
Unified launcher for two existing Telegram bot systems.

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

import cinema_core as cinema
import youseif_core as youseif

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

# PTB application is used only as an update processor; it does NOT poll.
PTB_APP = None
PTB_BOT = None
YOUSEIF = None

YOUSEIF_CALLBACK_PREFIXES = (
    "main", "t:", "qk:", "hg:", "hc:", "hi:", "lt:", "lp:", "li:",
    "g:", "gp:", "c:", "i:", "f:", "w:", "s:", "e:", "p:",
    "act:", "adm:", "sr:",
)


def is_youseif_callback(data: str) -> bool:
    data = data or ""
    return data == "noop" or data.startswith(YOUSEIF_CALLBACK_PREFIXES)


def raw_update(update):
    if hasattr(update, "to_dict"):
        return update.to_dict()
    if hasattr(update, "to_json"):
        return json.loads(update.to_json())
    return json.loads(str(update))


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
    markup.add(types.InlineKeyboardButton("🏠 البوابة الرئيسية", callback_data="hub_home"))
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
    markup.add(types.InlineKeyboardButton("🏠 البوابة الرئيسية", callback_data="hub_home"))
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


async def process_global_search(chat_id, user_id, query, message_id=None):
    """بحث واحد في الأنظمة الثلاثة؛ فتح النتائج يظل بــcallback الخاص بصاحبها."""
    query = (query or "").strip()[:80]
    if len(query) < 2:
        await PTB_BOT.send_message(chat_id, "❌ اكتب اسمًا من حرفين على الأقل للبحث.")
        return
    try:
        cinema_results = cinema.unified_search_results(query)
    except Exception:
        cinema_results = {"nova_movies": [], "nova_series": [], "orion_movies": [], "orion_series": []}
    try:
        youseif_results = await YOUSEIF.store.search(query)
    except Exception:
        youseif_results = []
    grouped = _youseif_search_groups(youseif_results)
    state = _merged_search_results(query, cinema_results, grouped)
    GLOBAL_SEARCH_STATE[user_id] = state
    total = sum(v.get("total", 0) for k, v in state.items() if k in ("nova", "orion")) + sum(len(v) for v in grouped.values())
    text = (
        f"🔍✨ <b>نتائج البحث عن «{youseif.esc(query)}»</b> ✨\n"
        "━━━━━━━━━━━━━━━\n"
        f"📦 <b>إجمالي النتائج: {total}</b>\n\n"
        "اختر المصدر لعرض نتائجه:"
    )
    kb = _merged_search_keyboard(state)
    if message_id:
        try:
            await PTB_BOT.edit_message_text(chat_id=chat_id, message_id=message_id, text=text, parse_mode=youseif.ParseMode.HTML, reply_markup=None)
            # Telegram bot API cannot reuse telebot markup; send a clean PTB keyboard below.
            await PTB_BOT.edit_message_reply_markup(chat_id=chat_id, message_id=message_id, reply_markup=_ptb_merged_search_keyboard(state))
            return
        except Exception:
            pass
    await PTB_BOT.send_message(chat_id, text, parse_mode=youseif.ParseMode.HTML, reply_markup=_ptb_merged_search_keyboard(state))


def _ptb_merged_search_keyboard(state):
    from telegram import InlineKeyboardButton, InlineKeyboardMarkup
    rows=[]
    for source,title in (("nova","🌟 سينما نوفا"),("orion","🎞️ أوريون بلس"),("youseif","🎬 Youseif Films")):
        d=state[source]
        total=(d.get("total",0) if source != "youseif" else sum(len(d.get(t,[])) for t in ("movie","series","live")))
        rows.append([InlineKeyboardButton(f"{title} ({total})", callback_data=f"merged3:source:{source}")])
    rows.append([InlineKeyboardButton("🏠 البوابة الرئيسية", callback_data="hub_home")])
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
    rows += [[InlineKeyboardButton("🔙 نتائج البحث", callback_data="merged3:back")],[InlineKeyboardButton("🏠 البوابة الرئيسية", callback_data="hub_home")]]
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
    rows += [[InlineKeyboardButton("🔙 نتائج البحث", callback_data="merged3:back")],[InlineKeyboardButton("🏠 البوابة الرئيسية", callback_data="hub_home")]]
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


async def poll_loop():
    offset = None
    retry = 2
    loop = asyncio.get_running_loop()

    while True:
        try:
            def fetch():
                return cinema.bot.get_updates(offset=offset, timeout=30, long_polling_timeout=30)

            updates = await loop.run_in_executor(None, fetch)
            retry = 2
            for upd in updates:
                # Advance the single shared getUpdates cursor immediately so every
                # routed branch (including special commands/callbacks) is consumed once.
                offset = tele_update_id(upd) + 1
                uid = update_user_id(upd)

                # Special entry command handled before either framework sees it.
                if handle_special_command(upd):
                    continue

                if is_callback(upd):
                    data = getattr(upd.callback_query, "data", "") or ""
                    # البحث الموحد الجديد: يضم المصدرين الأصليين + Youseif.
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
                    if data.startswith("merged3:"):
                        if uid:
                            USER_MODE[uid] = "cinema"
                        qmsg = getattr(upd.callback_query, "message", None)
                        state = GLOBAL_SEARCH_STATE.get(uid) if uid else None
                        try:
                            await upd.callback_query.answer()
                        except Exception:
                            pass
                        if not qmsg or not state:
                            continue
                        action = data.split(":")
                        if action[1] == "source" and len(action) >= 3:
                            src=action[2]
                            await PTB_BOT.edit_message_text(chat_id=qmsg.chat.id, message_id=qmsg.message_id, text=f"🔍 <b>{youseif.esc(state['query'])}</b>\n\nاختر القسم:", parse_mode=youseif.ParseMode.HTML, reply_markup=_ptb_source_keyboard(src, state[src]))
                        elif action[1] == "list" and len(action) >= 3:
                            typ=action[2]; items=state["youseif"].get(typ, [])
                            await PTB_BOT.edit_message_text(chat_id=qmsg.chat.id, message_id=qmsg.message_id, text=f"🔍 <b>{youseif.esc(state['query'])}</b> — {youseif.TYPE_LABEL[typ]}", parse_mode=youseif.ParseMode.HTML, reply_markup=_ptb_youseif_list_keyboard(items, typ))
                        elif action[1] == "page" and len(action) >= 4:
                            typ=action[2]; page=int(action[3]); items=state["youseif"].get(typ, [])
                            await PTB_BOT.edit_message_reply_markup(chat_id=qmsg.chat.id, message_id=qmsg.message_id, reply_markup=_ptb_youseif_list_keyboard(items, typ, page))
                        elif action[1] == "back":
                            await PTB_BOT.edit_message_text(chat_id=qmsg.chat.id, message_id=qmsg.message_id, text=f"🔍✨ <b>نتائج البحث عن «{youseif.esc(state['query'])}»</b> ✨\n\nاختر المصدر:", parse_mode=youseif.ParseMode.HTML, reply_markup=_ptb_merged_search_keyboard(state))
                        continue
                    # The shared Cinema hub exposes the third system explicitly.
                    # Intercept only this bridge callback; every original callback
                    # remains owned by its original bot/module.
                    if data == "hub_youseif":
                        if uid:
                            USER_MODE[uid] = "youseif"
                        try:
                            await upd.callback_query.answer()
                        except Exception:
                            pass
                        if uid and getattr(upd.callback_query, "message", None):
                            await send_youseif_start(
                                uid,
                                upd.callback_query.message.chat.id,
                                getattr(upd.callback_query.from_user, "first_name", "") or "",
                            )
                        continue
                    # Once the user is inside Youseif, route EVERY callback to
                    # its original PTB router. Do not depend on a hard-coded list
                    # of prefixes: the original bot may contain additional
                    # callback namespaces and they must keep working after merge.
                    # Only the two bridge callbacks above are intercepted here.
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
                    await process_global_search(getattr(upd.message, "chat", None).id, uid, text)
                    continue
                if text.startswith("/"):
                    command = text.split()[0].split("@")[0].lower()
                    # Entry aliases always open the original Youseif interface.
                    if command in {"/youseif", "/app", "/films"}:
                        if uid:
                            USER_MODE[uid] = "youseif"
                        await process_youseif(upd)
                    elif uid and USER_MODE.get(uid) == "youseif":
                        # Keep ALL commands belonging to Youseif in its own
                        # dispatcher; this preserves future commands too.
                        await process_youseif(upd)
                    else:
                        cinema.bot.process_new_updates([upd])
                    continue

                mode = USER_MODE.get(uid, "cinema") if uid else "cinema"
                if mode == "youseif" and uid not in CINEMA_WAITING:
                    await process_youseif(upd)
                else:
                    cinema.bot.process_new_updates([upd])
                    # A one-shot next-step callback is normally consumed here.
                    CINEMA_WAITING.discard(uid)

        except KeyboardInterrupt:
            raise
        except Exception as exc:
            log.exception("Polling/dispatch error: %s", exc)
            await asyncio.sleep(retry)
            retry = min(retry * 2, 30)


async def main():
    global PTB_APP, PTB_BOT, YOUSEIF

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
