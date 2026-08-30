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
                    if is_youseif_callback(data):
                        if uid:
                            USER_MODE[uid] = "youseif"
                        await process_youseif(upd)
                    else:
                        if uid:
                            USER_MODE[uid] = "cinema"
                        cinema.bot.process_new_updates([upd])
                    continue

                text = message_text(upd)
                if text.startswith("/"):
                    # /start and /search remain owned by the existing Cinema UI.
                    # PTB commands are available after entering its interface.
                    if uid and USER_MODE.get(uid) == "youseif" and text.split()[0].split("@")[0].lower() in {
                        "/help", "/stats", "/broadcast"
                    }:
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
    try:
        await poll_loop()
    finally:
        await PTB_APP.stop()
        await PTB_APP.shutdown()


if __name__ == "__main__":
    asyncio.run(main())
