"""Youseif assistant — on-demand AI help only (no auto-hijack of normal chat).

Activation paths:
1) Explicit trigger: message starts with «يوسف» / youseif
2) Chat session: user pressed «تحدث مع يوسف» → youseif_chat_active=True
3) Help after failure: callback youseif_help with stored error context

While chat is active, free text goes to AI until user ends the session.
"""
from __future__ import annotations

import logging
import re
from typing import Dict, List, Optional

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes

logger = logging.getLogger(__name__)

_TRIGGERS = re.compile(
    r"^\s*(يوسف|youseif|youssef|yusuf)\b",
    re.I,
)

CHAT_FLAG = "youseif_chat_active"
HELP_CTX_KEY = "youseif_help_context"


def is_youseif_message(text: str) -> bool:
    return bool(text and _TRIGGERS.search(text.strip()))


def _strip_trigger(text: str) -> str:
    return _TRIGGERS.sub("", text.strip(), count=1).strip(" :、-—")


def youseif_chat_keyboard(active: bool = True) -> InlineKeyboardMarkup:
    rows = []
    if active:
        rows.append([InlineKeyboardButton("🔚 إنهاء محادثة يوسف", callback_data="youseif_chat_end")])
    else:
        rows.append([InlineKeyboardButton("💬 تحدث مع يوسف", callback_data="youseif_chat_start")])
    rows.append([
        InlineKeyboardButton("🎬 السينما", callback_data="cinema_menu"),
        InlineKeyboardButton("📡 البث", callback_data="section_stream"),
    ])
    rows.append([InlineKeyboardButton("🔙 القائمة", callback_data="main_menu")])
    return InlineKeyboardMarkup(rows)


def youseif_help_button(label: str = "🆘 استعن بيوسف") -> List[List[InlineKeyboardButton]]:
    """Rows to append on failure messages."""
    return [[InlineKeyboardButton(label, callback_data="youseif_help")]]


def _history_from_ctx(context: ContextTypes.DEFAULT_TYPE) -> List[Dict[str, str]]:
    raw = context.user_data.get("youseif_history") or []
    out: List[Dict[str, str]] = []
    for item in raw[-12:]:
        if isinstance(item, dict) and item.get("role") and item.get("content"):
            out.append({"role": str(item["role"]), "content": str(item["content"])[:1200]})
    return out


def _push_history(context: ContextTypes.DEFAULT_TYPE, role: str, content: str) -> None:
    hist = context.user_data.setdefault("youseif_history", [])
    hist.append({"role": role, "content": (content or "")[:1200]})
    context.user_data["youseif_history"] = hist[-14:]


async def _show_typing(context: ContextTypes.DEFAULT_TYPE, chat_id: int) -> None:
    try:
        try:
            from telegram.constants import ChatAction
            action = ChatAction.TYPING
        except Exception:
            action = "typing"
        await context.bot.send_chat_action(chat_id=chat_id, action=action)
    except Exception:
        pass


async def _ai_reply(
    user_text: str,
    context: ContextTypes.DEFAULT_TYPE,
    *,
    extra_system: str = "",
) -> Optional[str]:
    try:
        from services import ai as ai_svc
        return await ai_svc.chat(
            user_text,
            history=_history_from_ctx(context),
            extra_system=extra_system,
        )
    except Exception as e:
        logger.warning("AI chat failed: %s", e)
        return None


async def _thinking_then_reply(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    user_text: str,
    *,
    extra_system: str = "",
    header: str = "🤖 <b>يوسف</b>",
) -> None:
    message = update.effective_message
    chat = update.effective_chat
    if not message or not chat:
        return

    await _show_typing(context, chat.id)
    status = await message.reply_text("✍️ <b>يوسف يفكر ويكتب...</b>", parse_mode="HTML")

    # refresh typing while waiting
    await _show_typing(context, chat.id)
    _push_history(context, "user", user_text)
    ai = await _ai_reply(user_text, context, extra_system=extra_system)
    await _show_typing(context, chat.id)

    if ai:
        _push_history(context, "assistant", ai)
        body = f"{header}\n\n{ai}"
    else:
        body = (
            f"{header}\n\n"
            "تعذّر الوصول لمحرك الذكاء حالياً.\n"
            "تأكد من AI_ENABLED ومفتاح OpenRouter، ثم حاول مرة أخرى."
        )

    kb = youseif_chat_keyboard(active=bool(context.user_data.get(CHAT_FLAG)))
    try:
        await status.edit_text(body, parse_mode="HTML", reply_markup=kb)
    except Exception:
        await message.reply_text(body, parse_mode="HTML", reply_markup=kb)


# ─── Callbacks ─────────────────────────────────────────────────────────────

async def youseif_chat_start_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Start a dedicated AI chat session (from any «تحدث مع يوسف» button)."""
    q = update.callback_query
    try:
        await q.answer("تم فتح محادثة يوسف")
    except Exception:
        pass
    context.user_data[CHAT_FLAG] = True
    # optional clear stale help context when starting fresh chat
    help_note = context.user_data.get(HELP_CTX_KEY)
    body = (
        "🤖 <b>يوسف جاهز للمحادثة</b>\n\n"
        "اكتب سؤالك مباشرة هنا — مش محتاج تكتب اسمي كل مرة.\n"
        "أقدر أشرح البث، السينما، IPTV، الأخطاء، والخطوات العملية.\n\n"
        "للخروج: اضغط «إنهاء محادثة يوسف» أو اكتب /cancel"
    )
    if help_note:
        body += f"\n\n📋 <b>سياق آخر مشكلة:</b>\n<code>{str(help_note)[:400]}</code>"

    from utils.helpers import safe_edit_message
    try:
        await safe_edit_message(q, body, parse_mode="HTML", reply_markup=youseif_chat_keyboard(True))
    except Exception:
        if update.effective_message:
            await update.effective_message.reply_text(
                body, parse_mode="HTML", reply_markup=youseif_chat_keyboard(True)
            )


async def youseif_chat_end_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    try:
        await q.answer("تم إنهاء المحادثة")
    except Exception:
        pass
    context.user_data.pop(CHAT_FLAG, None)
    context.user_data.pop(HELP_CTX_KEY, None)
    from utils.helpers import safe_edit_message
    body = (
        "🔚 <b>انتهت محادثة يوسف</b>\n\n"
        "لو احتجتني تاني:\n"
        "• اكتب: <code>يوسف ...</code>\n"
        "• أو اضغط «تحدث مع يوسف» من القائمة / بعد أي خطأ"
    )
    try:
        await safe_edit_message(q, body, parse_mode="HTML", reply_markup=youseif_chat_keyboard(False))
    except Exception:
        if update.effective_message:
            await update.effective_message.reply_text(
                body, parse_mode="HTML", reply_markup=youseif_chat_keyboard(False)
            )


async def youseif_help_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Help after a failure — opens chat with error context baked into the prompt."""
    q = update.callback_query
    try:
        await q.answer()
    except Exception:
        pass
    context.user_data[CHAT_FLAG] = True
    err = context.user_data.get(HELP_CTX_KEY) or context.user_data.get("last_stream_error") or "مشكلة غير محددة"
    # Seed history so AI sees the problem
    _push_history(context, "user", f"واجهت هذه المشكلة في البوت:\n{err}\nاشرح السبب وخطوات الحل بالعربي بشكل عملي.")

    if update.effective_chat:
        await _show_typing(context, update.effective_chat.id)

    status_msg = None
    try:
        from utils.helpers import safe_edit_message
        status_msg = await safe_edit_message(
            q, "✍️ <b>يوسف يراجع المشكلة ويكتب الحل...</b>", parse_mode="HTML"
        )
    except Exception:
        if update.effective_message:
            status_msg = await update.effective_message.reply_text(
                "✍️ <b>يوسف يراجع المشكلة ويكتب الحل...</b>", parse_mode="HTML"
            )

    extra = (
        "المستخدم طلب المساعدة بعد فشل عملية في البوت. "
        "اشرح السبب المحتمل وخطوات الحل المرقّمة بوضوح. "
        f"تفاصيل الخطأ/السياق:\n{str(err)[:800]}"
    )
    ai = await _ai_reply(
        f"ساعدني في حل هذه المشكلة:\n{err}",
        context,
        extra_system=extra,
    )
    if ai:
        _push_history(context, "assistant", ai)
        body = f"🤖 <b>يوسف — مساعدة</b>\n\n{ai}\n\nيمكنك متابعة السؤال بالكتابة مباشرة."
    else:
        body = (
            "🤖 <b>يوسف</b>\n\n"
            "تعذّر الاتصال بالذكاء الاصطناعي.\n"
            f"ملخص المشكلة المحفوظة:\n<code>{str(err)[:500]}</code>\n\n"
            "جرّب لاحقاً أو راجع إعدادات AI."
        )
    kb = youseif_chat_keyboard(True)
    try:
        if status_msg and hasattr(status_msg, "edit_text"):
            await status_msg.edit_text(body, parse_mode="HTML", reply_markup=kb)
        elif q:
            from utils.helpers import safe_edit_message
            await safe_edit_message(q, body, parse_mode="HTML", reply_markup=kb)
        else:
            await update.effective_message.reply_text(body, parse_mode="HTML", reply_markup=kb)
    except Exception:
        if update.effective_message:
            await update.effective_message.reply_text(body, parse_mode="HTML", reply_markup=kb)


async def youseif_assistant_entry(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Menu card: explain how to talk to Youseif + start button."""
    q = update.callback_query
    if q:
        try:
            await q.answer()
        except Exception:
            pass
    body = (
        "🤖 <b>يوسف — المساعد الذكي</b>\n\n"
        "يوسف <b>لا يتدخل</b> في رسائلك العادية.\n"
        "يتكلم معك فقط عندما تطلبه:\n\n"
        "• اضغط «💬 تحدث مع يوسف» بالأسفل\n"
        "• أو اكتب: <code>يوسف كيف أسوي بث؟</code>\n"
        "• أو بعد أي فشل اضغط «🆘 استعن بيوسف»\n\n"
        "يعرف أقسام البوت: البث، السينما، IPTV، الملفات، المكتبة، والأخطاء الشائعة."
    )
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("💬 تحدث مع يوسف", callback_data="youseif_chat_start")],
        [InlineKeyboardButton("ℹ️ شرح البوت", callback_data="help_assistant")],
        [InlineKeyboardButton("🔙 القائمة", callback_data="main_menu")],
    ])
    if q:
        from utils.helpers import safe_edit_message
        await safe_edit_message(q, body, parse_mode="HTML", reply_markup=kb)
    elif update.effective_message:
        await update.effective_message.reply_text(body, parse_mode="HTML", reply_markup=kb)


# ─── Message handler ───────────────────────────────────────────────────────

async def youseif_message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = update.effective_message
    if not message or not message.text:
        return

    text = message.text.strip()

    # End session commands
    if text.lower() in ("/cancel", "إنهاء", "انهي", "وقف يوسف", "انهاء"):
        if context.user_data.get(CHAT_FLAG):
            context.user_data.pop(CHAT_FLAG, None)
            await message.reply_text(
                "🔚 تم إنهاء محادثة يوسف.",
                reply_markup=youseif_chat_keyboard(False),
            )
            return

    explicit = is_youseif_message(text)
    chat_active = bool(context.user_data.get(CHAT_FLAG))

    # Never steal workflow inputs
    from utils.helpers import has_active_workflow
    ud = context.user_data or {}
    if has_active_workflow(ud) or ud.get("admin_manage_action"):
        return
    if not explicit and not chat_active:
        return
    if not explicit and chat_active:
        if ud.get("stream_source") and ud.get("stream_title") and not chat_active:
            return

    q = _strip_trigger(text) if explicit else text
    if explicit and not q:
        await message.reply_text(
            "🤖 <b>يوسف</b>\n\nاكتب سؤالك بعد اسمي، أو اضغط الزر لبدء محادثة.\n"
            "مثال: <code>يوسف ليه البث واقف؟</code>",
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("💬 تحدث مع يوسف", callback_data="youseif_chat_start")],
            ]),
        )
        return

    # Enter chat mode on explicit call so follow-ups don't need the name
    if explicit:
        context.user_data[CHAT_FLAG] = True

    extra = ""
    if context.user_data.get(HELP_CTX_KEY):
        extra = f"سياق مشكلة سابقة للمستخدم:\n{context.user_data.get(HELP_CTX_KEY)}"

    # Search intent still supported inside chat
    low = (q or "").lower()
    want_search = any(x in low for x in ("بحث", "ابحث", "دور", "search", "لقي", "رشح", "فيلم", "مسلسل", "انمي", "أنمي"))

    if want_search and not any(x in low for x in ("ازاي", "كيف", "ليه", "خطأ", "فشل", "مشكلة", "حل")):
        # keep cinema search path light
        thinking = await message.reply_text("✍️ <b>يوسف يبحث...</b>", parse_mode="HTML")
        await _show_typing(context, update.effective_chat.id)
        query = q
        for w in ("رشح", "اقترح", "عايز", "أريد", "فيلم", "مسلسل", "انمي", "أنمي", "بحث", "ابحث", "عن", "لي", "يوسف"):
            query = query.replace(w, " ")
        query = " ".join(query.split()).strip() or q
        results = []
        try:
            from services import cinema
            results = await cinema.search(query, limit=8)
        except Exception as e:
            logger.warning("youseif search: %s", e)
        if results:
            context.user_data["cinema_results"] = results
            lines = ["🤖 <b>يوسف — نتائج من مصادر البوت</b>\n"]
            buttons = []
            for i, r in enumerate(results[:8]):
                title = str(r.get("title") or "—")[:40]
                lines.append(f"{i+1}. {title}")
                buttons.append([InlineKeyboardButton(f"{i+1}. {title[:28]}", callback_data=f"cinema_pick:{i}")])
            buttons.append([InlineKeyboardButton("🔚 إنهاء المحادثة", callback_data="youseif_chat_end")])
            try:
                await thinking.edit_text("\n".join(lines), parse_mode="HTML", reply_markup=InlineKeyboardMarkup(buttons))
            except Exception:
                await message.reply_text("\n".join(lines), parse_mode="HTML", reply_markup=InlineKeyboardMarkup(buttons))
            return
        # fall through to AI if no results

    await _thinking_then_reply(update, context, q or text, extra_system=extra)


def store_help_context(context: ContextTypes.DEFAULT_TYPE, error_text: str) -> None:
    """Call from stream/cinema failure paths before showing the help button."""
    if not context or not error_text:
        return
    context.user_data[HELP_CTX_KEY] = str(error_text)[:900]
    context.user_data["last_stream_error"] = str(error_text)[:900]
