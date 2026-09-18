import logging
import asyncio
from telegram import Update
from telegram.ext import ContextTypes
from database import db
from config import ADMIN_ID
from keyboards.menus import (
    admin_panel_keyboard, sys_monitor_keyboard, settings_menu,
    storage_menu, main_menu,
)
from utils.decorators import rate_limit
from utils.helpers import is_admin, register_admin, safe_edit_message
from services.system_monitor import build_dashboard
from telegram import InlineKeyboardButton, InlineKeyboardMarkup

logger = logging.getLogger(__name__)

_MONITOR_TASKS = {}
PERMISSIONS = [
    ("stream.create", "إنشاء البث"), ("stream.stop", "إيقاف البث"),
    ("stream.restart", "إعادة تشغيل البث"), ("stream.view", "مشاهدة البثوث"),
    ("files.upload", "رفع الملفات"), ("files.delete", "حذف الملفات"),
    ("files.view", "عرض الملفات"), ("users.manage", "إدارة المستخدمين"),
    ("users.ban", "حظر المستخدمين"), ("users.view", "عرض المستخدمين"),
    ("system.monitor", "مراقبة السيرفر"), ("system.maintenance", "الصيانة"),
    ("system.backup", "النسخ الاحتياطي"), ("admin.panel", "لوحة المدير"),
    ("api.access", "الوصول للـ API"), ("iptv.manage", "إدارة IPTV"),
    ("plugins.manage", "إدارة الإضافات"),
]



def _admin_only(user_id):
    return is_admin(user_id, ADMIN_ID)

async def _admin_allowed(user_id: int, permission: str = "admin.panel") -> bool:
    if not _admin_only(user_id):
        return False
    if int(user_id) == int(ADMIN_ID):
        return True
    try:
        from core.permissions import check_user_permission
        return await check_user_permission(user_id, permission, ADMIN_ID)
    except Exception:
        return False


async def admin_panel_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    uid = query.from_user.id if query else update.effective_user.id
    if not await _admin_allowed(uid, "admin.panel"):
        if query:
            try:
                await query.answer("للأدمن فقط", show_alert=True)
            except Exception:
                pass
        return
    if query:
        try:
            await query.answer()
        except Exception:
            pass
    text = "📊 <b>لوحة التحكم</b>\n\nاختر قسماً:"
    if query:
        await safe_edit_message(query, text, parse_mode="HTML", reply_markup=admin_panel_keyboard())
    else:
        await update.message.reply_text(text, parse_mode="HTML", reply_markup=admin_panel_keyboard())


async def sys_monitor_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if not await _admin_allowed(query.from_user.id, "system.monitor"):
        await query.answer("للأدمن فقط", show_alert=True)
        return
    tick = context.user_data.get("mon_tick", 0)
    context.user_data["mon_tick"] = tick + 1
    text = build_dashboard(tick)
    await query.edit_message_text(text, parse_mode="HTML", reply_markup=sys_monitor_keyboard())

    # auto-refresh ~2s
    key = (query.message.chat_id, query.message.message_id)
    old = _MONITOR_TASKS.get(key)
    if old and not old.done():
        return

    async def _loop():
        try:
            for i in range(90):
                await asyncio.sleep(2)
                t = build_dashboard(tick + i + 1)
                try:
                    await context.bot.edit_message_text(
                        chat_id=query.message.chat_id,
                        message_id=query.message.message_id,
                        text=t,
                        parse_mode="HTML",
                        reply_markup=sys_monitor_keyboard(),
                    )
                except Exception as e:
                    if "not found" in str(e).lower():
                        break
            _MONITOR_TASKS.pop(key, None)
        except asyncio.CancelledError:
            pass
        except Exception:
            _MONITOR_TASKS.pop(key, None)

    _MONITOR_TASKS[key] = asyncio.create_task(_loop())


async def settings_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if query:
        await query.answer()
        await query.edit_message_text(
            "⚙️ *الإعدادات*", parse_mode="Markdown", reply_markup=settings_menu()
        )
    else:
        await update.message.reply_text(
            "⚙️ *الإعدادات*", parse_mode="Markdown", reply_markup=settings_menu()
        )


async def storage_menu_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """تخزين: اختيار المزود + ملفاتي + رفع."""
    query = update.callback_query
    from telegram import InlineKeyboardButton, InlineKeyboardMarkup
    text = (
        "☁️ <b>التخزين السحابي</b>\n\n"
        "اختر المزود الافتراضي أو إدارة الملفات:\n"
        "• 🟠 Cloudflare R2 (الافتراضي من إعدادات السيرفر)\n"
        "• 🔵 Google Cloud / 🟣 Backblaze / ⚫ Archive.org (اختيار محفوظ)\n\n"
        "للملفات الكبيرة: <code>/upload https://رابط</code>"
    )
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("📂 ملفاتي", callback_data="my_files")],
        [InlineKeyboardButton("☁️ اختيار المزود", callback_data="my_storage")],
        [InlineKeyboardButton("📤 مساعدة الرفع", callback_data="upload_help")],
        [InlineKeyboardButton("🔙 رجوع", callback_data="main_menu")],
    ])
    if query:
        await query.answer()
        await query.edit_message_text(text, parse_mode="HTML", reply_markup=kb)
    else:
        await update.message.reply_text(text, parse_mode="HTML", reply_markup=kb)


async def upload_help_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    from config import LOCAL_BOT_API_ENABLED, LOCAL_BOT_API_DOWNLOAD_LIMIT, TELEGRAM_CLOUD_DOWNLOAD_LIMIT
    from utils.helpers import format_size

    query = update.callback_query
    await query.answer()
    current_limit = LOCAL_BOT_API_DOWNLOAD_LIMIT if LOCAL_BOT_API_ENABLED else TELEGRAM_CLOUD_DOWNLOAD_LIMIT
    server_status = "✅ مفعّل" if LOCAL_BOT_API_ENABLED else "❌ غير مفعّل"
    await query.edit_message_text(
        "☁️ *رفع ملفات كبيرة*\n\n"
        f"الحد الحالي لملفات تيليجرام: `{format_size(current_limit)}`\n"
        f"Local Bot API Server: {server_status}\n\n"
        "✅ *يعمل دائماً بدون أي حد (يعتمد على تخزينك فقط):*\n"
        "`/upload https://رابط-مباشر-للملف`\n"
        "يدعم 1GB / 2GB / 4GB / 10GB+ لأنه يرفع Streaming مباشرة "
        "للسحابة بدون المرور بحد تيليجرام إطلاقاً.\n\n"
        "✅ روابط Google Drive العامة تُقبل مباشرة أيضاً.\n\n"
        "⚠️ إرسال ملف من تيليجرام مباشرة محدود بحد تيليجرام نفسه "
        "(20MB بدون سيرفر محلي، حتى 2GB مع Local Bot API Server) — "
        "هذا قيد من تيليجرام وليس من البوت.",
        parse_mode="Markdown",
        reply_markup=storage_menu(),
    )


async def about_bot_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await query.edit_message_text(
        "🎬 *Youseif Stream Bot*\n\nبث + رفع R2 + مكتبات قرآن وموسيقى",
        parse_mode="Markdown",
        reply_markup=settings_menu(),
    )


async def verify_phone_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    from keyboards.menus import phone_keyboard
    await query.message.reply_text(
        "📱 اضغط الزر لمشاركة رقمك:",
        reply_markup=phone_keyboard(),
    )


async def admin_stats_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if not await _admin_allowed(query.from_user.id, "system.monitor"):
        return
    users = await db.get_users_count()
    files = len(await db.get_all_files())
    streams = await db.get_all_streams()
    active = sum(1 for s in streams if s.get("status") == "running")
    from services.stream import stream_manager
    ff = "🟢" if await asyncio.to_thread(stream_manager.has_ffmpeg) else "🔴"
    text = (
        f"📊 <b>إحصائيات</b>\n\n"
        f"👥 المستخدمون: <b>{users}</b>\n"
        f"📁 الملفات: <b>{files}</b>\n"
        f"📡 البثوث: <b>{len(streams)}</b> (نشط: {active})\n"
        f"🎞 FFmpeg: {ff}\n"
    )
    await query.edit_message_text(text, parse_mode="HTML", reply_markup=admin_panel_keyboard())


async def admin_manage_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Open admin/RBAC management without letting malformed user rows crash the UI."""
    query = update.callback_query
    uid = query.from_user.id if query else update.effective_user.id
    if not await _admin_allowed(uid, "admin.panel"):
        if query:
            try:
                await query.answer("للأدمن فقط", show_alert=True)
            except Exception:
                pass
        else:
            await update.message.reply_text("⛔ هذه الصفحة للأدمن فقط.")
        return
    if query:
        try:
            await query.answer()
        except Exception:
            pass
    try:
        from html import escape
        users = await db.get_all_users() or []
        admins = [u for u in users if str(u.get("role") or "").lower() in ("admin", "owner")]
        lines = ["🛡 <b>إدارة الأدمن والصلاحيات</b>", "", "الأدمن الحاليون:"]
        buttons = []
        for u in admins[:20]:
            raw_id = u.get("user_id")
            try:
                target_id = int(raw_id)
            except Exception:
                continue
            name = str(u.get("first_name") or u.get("username") or target_id)[:20]
            role = str(u.get("role") or "admin")
            lines.append(f"• {escape(name)} — <code>{target_id}</code> ({escape(role)})")
            if target_id != int(ADMIN_ID):
                buttons.append([InlineKeyboardButton(f"⚙️ صلاحيات {name}", callback_data=f"admin_perms:{target_id}")])
        if not admins:
            lines.append("• لا يوجد أدمن إضافيون حالياً.")
        buttons += [
            [InlineKeyboardButton("➕ إضافة أدمن", callback_data="admin_add")],
            [InlineKeyboardButton("🗑 إزالة أدمن", callback_data="admin_remove")],
            [InlineKeyboardButton("🔙 لوحة المدير", callback_data="admin_panel")],
        ]
        markup = InlineKeyboardMarkup(buttons)
        text = "\n".join(lines)
        if query:
            await safe_edit_message(query, text, parse_mode="HTML", reply_markup=markup)
        else:
            await update.message.reply_text(text, parse_mode="HTML", reply_markup=markup)
    except Exception as exc:
        logger.exception("admin manage render failed: %s", exc)
        fallback = "❌ تعذر فتح إدارة الأدمن حالياً.\nتحقق من قاعدة البيانات ثم أعد المحاولة."
        try:
            if query and query.message:
                await query.message.reply_text(fallback, reply_markup=admin_panel_keyboard())
            elif update.message:
                await update.message.reply_text(fallback, reply_markup=admin_panel_keyboard())
        except Exception:
            pass

async def admin_add_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    try:
        await q.answer()
    except Exception:
        pass
    if not _admin_only(q.from_user.id):
        return
    context.user_data["admin_manage_action"] = "add"
    await safe_edit_message(
        q,
        "➕ أرسل ID الأدمن الجديد (رقم فقط):\nمثال: <code>123456789</code>",
        parse_mode="HTML",
    )

async def admin_remove_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    try:
        await q.answer()
    except Exception:
        pass
    if not _admin_only(q.from_user.id):
        return
    context.user_data["admin_manage_action"] = "remove"
    await safe_edit_message(q, "🗑 أرسل ID الأدمن الذي تريد إزالته:", parse_mode="HTML")

async def admin_permissions_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    internal = context.user_data.pop("_internal_admin_render", False)
    if not _admin_only(q.from_user.id):
        try:
            await q.answer("للأدمن فقط", show_alert=True)
        except Exception:
            pass
        return
    if not internal:
        try:
            await q.answer()
        except Exception:
            pass
    try:
        target = int(q.data.split(":", 1)[1])
    except Exception:
        return
    user = await db.get_user(target)
    if not user:
        await safe_edit_message(q, "❌ المستخدم غير موجود.")
        return
    overrides = await db.get_user_permissions(target) or {}
    rows = []
    for perm, label in PERMISSIONS:
        if perm in overrides:
            enabled = bool(overrides[perm])
            icon = "🟢" if enabled else "🔴"
            state = "مسموح" if enabled else "ممنوع"
        else:
            role = (user.get("role") or "user")
            from core.permissions import permissions_for_role
            enabled = perm in permissions_for_role(role)
            icon = "🟡" if enabled else "⚪"
            state = "افتراضي" if enabled else "غير ممنوح"
        rows.append([InlineKeyboardButton(f"{icon} {label} · {state}", callback_data=f"admin_perm_toggle:{target}:{perm}")])
    rows.append([InlineKeyboardButton("🔙 إدارة الأدمن", callback_data="admin_manage")])
    name = user.get("first_name") or target
    await safe_edit_message(
        q,
        f"🛡 <b>صلاحيات {name}</b>\n\n🟡 افتراضي  🟢 مسموح  🔴 ممنوع",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(rows),
    )

async def admin_permission_toggle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q=update.callback_query; await q.answer()
    if not _admin_only(q.from_user.id): return
    parts=q.data.split(":",2)
    if len(parts)!=3: return
    target=int(parts[1]); perm=parts[2]
    overrides=await db.get_user_permissions(target)
    if perm in overrides:
        await db.set_user_permission(target, perm, not bool(overrides[perm]))
    else:
        await db.set_user_permission(target, perm, True)
    q.data=f"admin_perms:{target}"
    context.user_data["_internal_admin_render"] = True
    await admin_permissions_callback(update, context)

async def required_sub_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q=update.callback_query
    internal = context.user_data.pop("_internal_sub_render", False)
    if not _admin_only(q.from_user.id):
        try: await q.answer("للأدمن فقط", show_alert=True)
        except Exception: pass
        return
    if not internal:
        try: await q.answer()
        except Exception: pass
    channels=await db.get_json_setting("required_channels", []) or []
    lines=["📢 <b>الاشتراك الإجباري</b>", ""]
    buttons=[]
    for i,ch in enumerate(channels):
        lines.append(f"{i+1}. {ch.get('name') or ch.get('username') or ch.get('chat_id')}")
        buttons.append([InlineKeyboardButton(f"🗑 حذف {ch.get('name') or ch.get('username') or i+1}", callback_data=f"required_sub_del:{i}")])
    lines.append("\nأضف قناة بصيغة:\n<code>@channel | اسم القناة</code>\nأو قناة خاصة:\n<code>-100123... | اسم القناة | رابط الدعوة</code>")
    buttons += [[InlineKeyboardButton("➕ إضافة قناة", callback_data="required_sub_add")], [InlineKeyboardButton("🔙 لوحة المدير", callback_data="admin_panel")]]
    await safe_edit_message(q, "\n".join(lines), parse_mode="HTML", reply_markup=InlineKeyboardMarkup(buttons))

async def required_sub_add_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q=update.callback_query; await q.answer()
    if not _admin_only(q.from_user.id): return
    context.user_data["admin_manage_action"]="sub_add"
    await safe_edit_message(q, "➕ أرسل القناة:\n<code>@channel | الاسم</code>\nأو <code>-100... | الاسم | https://t.me/+invite</code>", parse_mode="HTML")

async def required_sub_del_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q=update.callback_query; await q.answer()
    if not _admin_only(q.from_user.id): return
    try: idx=int(q.data.split(":",1)[1])
    except Exception: return
    channels=await db.get_json_setting("required_channels", []) or []
    if 0 <= idx < len(channels): channels.pop(idx)
    await db.set_json_setting("required_channels", channels)
    q.data="required_sub"
    context.user_data["_internal_sub_render"] = True
    await required_sub_callback(update, context)

async def admin_management_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    action=context.user_data.get("admin_manage_action")
    if not action or not await _admin_allowed(update.effective_user.id, "users.manage"): return False
    text=(update.message.text or "").strip()
    try:
        if action in ("add","remove"):
            target=int(text)
            user=await db.get_user(target)
            if action=="add":
                if not user:
                    await db.upsert_user(target, role="admin", approval_status="approved")
                await db.set_role(target,"admin"); await db.set_approval_status(target,"approved")
                register_admin(target, True)
                await update.message.reply_text(f"✅ تمت إضافة <code>{target}</code> كأدمن.", parse_mode="HTML")
            else:
                if target==ADMIN_ID:
                    await update.message.reply_text("❌ لا يمكن إزالة الأدمن الأساسي.")
                else:
                    await db.set_role(target,"user"); register_admin(target, False)
                    await update.message.reply_text(f"✅ تمت إزالة صلاحيات الأدمن عن <code>{target}</code>.", parse_mode="HTML")
        elif action=="sub_add":
            parts=[x.strip() for x in text.split("|")]
            if len(parts)<2: raise ValueError("الصيغة غير صحيحة")
            ident=parts[0]; name=parts[1]; invite=parts[2] if len(parts)>2 else ""
            item={"chat_id": ident if ident.startswith("-") else ident, "username": ident if ident.startswith("@") else "", "name": name, "invite_link": invite}
            channels=await db.get_json_setting("required_channels", []) or []
            if not any(str(x.get("chat_id") or x.get("username"))==ident for x in channels): channels.append(item)
            await db.set_json_setting("required_channels", channels)
            await update.message.reply_text("✅ تمت إضافة القناة للاشتراك الإجباري.")
    except Exception as exc:
        await update.message.reply_text(f"❌ {exc}")
    context.user_data.pop("admin_manage_action",None)
    return True


async def admin_users_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if not await _admin_allowed(query.from_user.id, "users.view"):
        return
    from telegram import InlineKeyboardButton, InlineKeyboardMarkup
    users = await db.get_all_users()
    pending = [u for u in users if (u.get("approval_status") or "") == "pending"]
    lines = [f"👥 <b>المستخدمون</b> ({len(users)}) — قيد الانتظار: {len(pending)}\n"]
    buttons = []
    # Pending first
    for u in pending[:8]:
        name = (u.get("first_name") or "مستخدم")[:18]
        uname = u.get("username") or "—"
        lines.append(f"⏳ <b>{name}</b> @{uname} <code>{u['user_id']}</code>")
        buttons.append([InlineKeyboardButton(
            f"⏳ {name} — عرض", callback_data=f"admin_user_{u['user_id']}"
        )])
    for u in users[:15]:
        if (u.get("approval_status") or "") == "pending":
            continue
        banned = u.get("is_banned")
        st = (u.get("approval_status") or "approved")
        mark = "🚫" if banned else ("✅" if st == "approved" else "❌")
        name = (u.get("first_name") or "مستخدم")[:16]
        uname = u.get("username") or "—"
        lines.append(f"{mark} <b>{name}</b> @{uname}")
        buttons.append([InlineKeyboardButton(
            f"{mark} {name}", callback_data=f"admin_user_{u['user_id']}"
        )])
    buttons.append([InlineKeyboardButton("🔙 رجوع", callback_data="admin_panel")])
    await query.edit_message_text(
        "\n".join(lines), parse_mode="HTML", reply_markup=InlineKeyboardMarkup(buttons)
    )


async def admin_user_detail_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """عرض بيانات مستخدم كاملة + أزرار موافقة/رفض/حظر."""
    query = update.callback_query
    await query.answer()
    if not await _admin_allowed(query.from_user.id, "users.view"):
        return
    from telegram import InlineKeyboardButton, InlineKeyboardMarkup
    try:
        uid = int(query.data.split("_")[-1])
    except Exception:
        await query.answer("خطأ", show_alert=True)
        return
    u = await db.get_user(uid)
    if not u:
        await query.edit_message_text("❌ المستخدم غير موجود.")
        return
    name = u.get("first_name") or "—"
    last = u.get("last_name") or ""
    uname = f"@{u['username']}" if u.get("username") else "—"
    phone = u.get("phone") or "—"
    role = u.get("role") or "user"
    st = u.get("approval_status") or "pending"
    banned = "نعم 🚫" if u.get("is_banned") else "لا"
    joined = (u.get("joined_at") or "—")[:19]
    active = (u.get("last_active") or "—")[:19]
    text = (
        f"📋 <b>بيانات المستخدم</b>\n\n"
        f"📛 الاسم: <b>{name} {last}</b>\n"
        f"🆔 ID: <code>{uid}</code>\n"
        f"👤 يوزر: {uname}\n"
        f"📱 الهاتف: <code>{phone}</code>\n"
        f"🎭 الدور: <b>{role}</b>\n"
        f"📌 الموافقة: <b>{st}</b>\n"
        f"🚫 محظور: {banned}\n"
        f"📅 انضم: {joined}\n"
        f"⏱ آخر نشاط: {active}\n"
    )
    kb = []
    if st != "approved":
        kb.append([InlineKeyboardButton("✅ موافقة", callback_data=f"admin_approve_{uid}")])
    if st != "rejected":
        kb.append([InlineKeyboardButton("❌ رفض", callback_data=f"admin_reject_{uid}")])
    if u.get("is_banned"):
        kb.append([InlineKeyboardButton("✅ رفع الحظر", callback_data=f"admin_unban:{uid}")])
    else:
        if uid != ADMIN_ID:
            kb.append([InlineKeyboardButton("🚫 حظر", callback_data=f"admin_ban:{uid}")])
    kb.append([InlineKeyboardButton("🔙 المستخدمون", callback_data="admin_users")])
    await safe_edit_message(query, text, parse_mode="HTML", reply_markup=InlineKeyboardMarkup(kb))


async def _render_admin_user_detail(query, uid: int):
    """Refresh a user detail card without answering the callback twice."""
    from telegram import InlineKeyboardButton, InlineKeyboardMarkup
    u = await db.get_user(uid)
    if not u:
        await safe_edit_message(query, "❌ المستخدم غير موجود.")
        return
    name = u.get("first_name") or "—"
    last = u.get("last_name") or ""
    uname = f"@{u['username']}" if u.get("username") else "—"
    phone = u.get("phone") or "—"
    role = u.get("role") or "user"
    st = u.get("approval_status") or "pending"
    banned = "نعم 🚫" if u.get("is_banned") else "لا"
    joined = (u.get("joined_at") or "—")[:19]
    active = (u.get("last_active") or "—")[:19]
    text = (
        f"📋 <b>بيانات المستخدم</b>\n\n"
        f"📛 الاسم: <b>{name} {last}</b>\n"
        f"🆔 ID: <code>{uid}</code>\n"
        f"👤 يوزر: {uname}\n"
        f"📱 الهاتف: <code>{phone}</code>\n"
        f"🎭 الدور: <b>{role}</b>\n"
        f"📌 الموافقة: <b>{st}</b>\n"
        f"🚫 محظور: {banned}\n"
        f"📅 انضم: {joined}\n"
        f"⏱ آخر نشاط: {active}\n"
    )
    kb = []
    if st != "approved":
        kb.append([InlineKeyboardButton("✅ موافقة", callback_data=f"admin_approve_{uid}")])
    if st != "rejected":
        kb.append([InlineKeyboardButton("❌ رفض", callback_data=f"admin_reject_{uid}")])
    if u.get("is_banned"):
        kb.append([InlineKeyboardButton("✅ رفع الحظر", callback_data=f"admin_unban:{uid}")])
    elif uid != ADMIN_ID:
        kb.append([InlineKeyboardButton("🚫 حظر", callback_data=f"admin_ban:{uid}")])
    kb.append([InlineKeyboardButton("🔙 المستخدمون", callback_data="admin_users")])
    await safe_edit_message(query, text, parse_mode="HTML", reply_markup=InlineKeyboardMarkup(kb))


async def admin_approve_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if not await _admin_allowed(query.from_user.id, "users.manage"):
        try:
            await query.answer("⛔ للمسؤولين فقط", show_alert=True)
        except Exception:
            pass
        return
    try:
        uid = int(query.data.rsplit("_", 1)[1])
    except Exception:
        try:
            await query.answer("❌ معرف المستخدم غير صالح", show_alert=True)
        except Exception:
            pass
        return
    try:
        await db.set_approval_status(uid, "approved")
        try:
            await query.answer("✅ تمت الموافقة", show_alert=False)
        except Exception:
            pass
        # Notify the user
        try:
            await context.bot.send_message(
                uid,
                "✅ <b>تمت الموافقة على حسابك</b>\n\nيمكنك الآن استخدام البوت. أرسل /start للمتابعة.",
                parse_mode="HTML",
            )
        except Exception:
            pass
        # Confirm to admin
        confirm = f"✅ تمت الموافقة على المستخدم <code>{uid}</code>."
        try:
            if query.message:
                await query.message.reply_text(confirm, parse_mode="HTML")
            else:
                await context.bot.send_message(query.from_user.id, confirm, parse_mode="HTML")
        except Exception:
            pass
        # Refresh user detail if possible
        try:
            await _render_admin_user_detail(query, uid)
        except Exception:
            logger.exception("approval detail refresh failed")
    except Exception as exc:
        logger.exception("approval failed: %s", exc)
        try:
            await query.answer("❌ تعذر إتمام الموافقة", show_alert=True)
        except Exception:
            pass
        try:
            if query.message:
                await query.message.reply_text("❌ حدث خطأ أثناء الموافقة. حاول مرة أخرى.")
        except Exception:
            pass


async def admin_reject_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if not await _admin_allowed(query.from_user.id, "users.manage"):
        await query.answer("⛔ للمسؤولين فقط", show_alert=True)
        return
    try:
        uid = int(query.data.rsplit("_", 1)[1])
    except Exception:
        await query.answer("❌ معرف المستخدم غير صالح", show_alert=True)
        return
    await db.set_approval_status(uid, "rejected")
    await query.answer("❌ تم الرفض", show_alert=True)
    try:
        await context.bot.send_message(
            uid,
            "❌ تم رفض طلبك لاستخدام البوت.\nتواصل مع الأدمن إن لزم.",
        )
    except Exception:
        pass
    await _render_admin_user_detail(query, uid)



async def admin_files_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if not await _admin_allowed(query.from_user.id, "files.view"):
        return
    files = await db.get_all_files()
    lines = [f"📁 *الملفات* ({len(files)})\n"]
    for f in files[:15]:
        lines.append(f"#{f['id']} {f['file_name'][:30]}")
    await query.edit_message_text(
        "\n".join(lines) or "لا ملفات",
        parse_mode="Markdown",
        reply_markup=admin_panel_keyboard(),
    )


async def admin_streams_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if not await _admin_allowed(query.from_user.id, "stream.view"):
        return
    from telegram import InlineKeyboardButton, InlineKeyboardMarkup
    streams = await db.get_all_streams()
    lines = [f"📡 <b>البثوث</b> ({len(streams)})\n"]
    buttons = []
    for s in streams[:12]:
        st = s.get("status") or "?"
        emoji = "🟢" if st == "running" else "🔴"
        lines.append(f"{emoji} #{s['id']} {(s.get('title') or '')[:22]} [{st}]")
        if st == "running":
            buttons.append([InlineKeyboardButton(
                f"⏹ إيقاف #{s['id']}", callback_data=f"admin_stop:{s['id']}"
            )])
    buttons.append([InlineKeyboardButton("🔄 تحديث", callback_data="admin_streams")])
    buttons.append([InlineKeyboardButton("🔙 رجوع", callback_data="admin_panel")])
    await query.edit_message_text(
        "\n".join(lines) or "لا بثوث",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(buttons),
    )


@rate_limit(calls=2, period=120, key_prefix="admin_bc")
async def admin_broadcast_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if not await _admin_allowed(query.from_user.id, "users.manage"):
        return
    context.user_data["await_broadcast"] = True
    await query.edit_message_text("📢 أرسل نص الإشعار الآن (أو /cancel):")


async def link_hidden_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer("🔒 الروابط ظاهرة للأدمن فقط", show_alert=True)


async def rtmp_settings_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """عرض إعدادات RTMP المحفوظة للمستخدم."""
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    profiles = await db.get_user_rtmp_profiles(user_id)
    from telegram import InlineKeyboardButton, InlineKeyboardMarkup
    if not profiles:
        text = (
            "⚙️ <b>إعدادات البث (RTMP)</b>\n\n"
            "لا توجد إعدادات محفوظة بعد.\n"
            "عند إنشاء بث جديد وإدخال RTMP + المفتاح، سيتم حفظها تلقائياً."
        )
        kb = InlineKeyboardMarkup([[InlineKeyboardButton("🔙 رجوع", callback_data="settings")]])
    else:
        lines = ["⚙️ <b>إعدادات البث المحفوظة</b>\n"]
        buttons = []
        for p in profiles[:5]:
            mark = "⭐ " if p.get("is_default") else ""
            base = p["rtmp_base"]
            if len(base) > 35:
                base = base[:30] + "…"
            lines.append(f"{mark}<b>{p.get('name') or 'إعداد'}</b>")
            lines.append(f"  RTMP: <code>{base}</code>")
            lines.append(f"  Key: <code>***{p['stream_key'][-6:]}</code>\n")
            if not p.get("is_default"):
                buttons.append([InlineKeyboardButton(
                    f"⭐ تعيين افتراضي #{p['id']}", callback_data=f"rtmp_default:{p['id']}"
                )])
        buttons.append([InlineKeyboardButton("🔙 رجوع", callback_data="settings")])
        text = "\n".join(lines)
        kb = InlineKeyboardMarkup(buttons)
    await query.edit_message_text(text, parse_mode="HTML", reply_markup=kb)


async def rtmp_default_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    try:
        pid = int(query.data.split(":")[1])
        await db.set_default_rtmp_profile(pid, query.from_user.id)
        await query.answer("✅ تم تعيينه كافتراضي", show_alert=True)
        await rtmp_settings_callback(update, context)
    except Exception as e:
        logger.exception(e)
        await query.answer("خطأ", show_alert=True)


async def schedule_menu_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    from telegram import InlineKeyboardButton, InlineKeyboardMarkup
    schedules = await db.get_user_schedules(query.from_user.id)
    lines = ["📅 <b>جدولة البث</b>\n"]
    if not schedules:
        lines.append(
            "لا توجد جداول.\n\nلإنشاء جدول أرسل:\n"
            "<code>/schedule اسم | 22:00 | 06:00</code>\n"
            "(يستخدم آخر مصدر + إعدادات RTMP المحفوظة)"
        )
    else:
        for s in schedules[:10]:
            en = "🟢" if s.get("enabled") else "🔴"
            lines.append(
                f"{en} <b>{s.get('name') or 'جدول'}</b> #{s['id']}\n"
                f"  ⏱ {s.get('start_time')} → {s.get('end_time')} · {s.get('days') or 'daily'}"
            )
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("🔄 تحديث", callback_data="schedule_menu")],
        [InlineKeyboardButton("🔙 رجوع", callback_data="settings")],
    ])
    await query.edit_message_text("\n".join(lines), parse_mode="HTML", reply_markup=kb)


async def favorites_menu_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    from telegram import InlineKeyboardButton, InlineKeyboardMarkup
    favs = await db.get_favorites(query.from_user.id)
    lines = ["⭐ <b>المفضلة</b>\n"]
    buttons = []
    if not favs:
        lines.append("لا توجد عناصر محفوظة بعد.")
    else:
        for f in favs[:12]:
            item_type = str(f.get("item_type") or "-")
            title = (f.get("title") or "بدون عنوان")[:25]
            lines.append(f"• {f.get('title') or 'بدون عنوان'} ({item_type})")
            if item_type.startswith("cinema_"):
                buttons.append([InlineKeyboardButton(
                    f"🎬 {title}",
                    callback_data=f"cinema_fav_pick:{f['id']}",
                )])
            elif f.get("source_url"):
                buttons.append([InlineKeyboardButton(
                    f"▶️ {title}",
                    callback_data=f"fav_play:{f['id']}",
                )])
    buttons.append([InlineKeyboardButton("🔙 رجوع", callback_data="main_menu")])
    await query.edit_message_text("\n".join(lines), parse_mode="HTML", reply_markup=InlineKeyboardMarkup(buttons))


async def fav_play_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    try:
        fid = int(query.data.split(":")[1])
        favs = await db.get_favorites(query.from_user.id)
        item = next((f for f in favs if f["id"] == fid), None)
        if not item or not item.get("source_url"):
            await query.answer("غير موجود", show_alert=True)
            return
        context.user_data["pending_stream_url"] = item["source_url"]
        context.user_data["pending_stream_title"] = item.get("title") or "مفضلة"
        from handlers.streams import start_rtmp_setup_flags
        await start_rtmp_setup_flags(update, context)
    except Exception as e:
        logger.exception(e)


async def pro_stream_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    from telegram import InlineKeyboardButton, InlineKeyboardMarkup
    user_id = query.from_user.id
    profile = await db.get_default_rtmp_profile(user_id)
    if not profile:
        await query.edit_message_text(
            "🚀 <b>البث الاحترافي</b>\n\n"
            "❌ لا توجد إعدادات RTMP محفوظة.\n"
            "أنشئ بثاً عادياً مرة واحدة أولاً ليتم حفظ المفتاح.",
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 رجوع", callback_data="settings")]]),
        )
        return

    streams = await db.get_user_streams(user_id)
    source = streams[0].get("source_url") if streams else None
    title = (streams[0].get("title") if streams else None) or "بث احترافي"

    if not source:
        await query.edit_message_text(
            "🚀 <b>البث الاحترافي</b>\n\n"
            "لا يوجد مصدر سابق. شغّل عنصراً من المكتبة أو أنشئ بثاً أولاً.",
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 رجوع", callback_data="settings")]]),
        )
        return

    from services.source_probe import probe_source, format_probe_error
    from services.stream import stream_manager

    await query.edit_message_text("🔍 فحص المصدر وضبط الإعدادات الاحترافية...")
    probe = await asyncio.to_thread(probe_source, source)
    source = probe.get("cleaned_url") or source
    if not probe.get("ok"):
        await query.edit_message_text(
            format_probe_error(probe, source_url=source or ""),
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 رجوع", callback_data="settings")]]),
        )
        return

    rtmp = profile["rtmp_base"].rstrip("/") + "/" + profile["stream_key"].lstrip("/")
    stream_id = await db.create_stream(user_id, title, source, rtmp)
    await db.update_stream_meta(stream_id, audio_bitrate="128k", volume=1.0)
    await db.add_audit(user_id, "pro_stream", str(stream_id), title)

    if not await asyncio.to_thread(stream_manager.has_ffmpeg):
        await query.edit_message_text(
            f"✅ تم إنشاء البث #{stream_id}\n⚠️ FFmpeg غير متوفر — محفوظ بدون تشغيل.",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("📡 البث الحالي", callback_data="current_stream")]]),
        )
        return

    pid = await asyncio.to_thread(
        stream_manager.start_stream,
        stream_id, source, rtmp, audio_bitrate="128k", volume=1.0,
    )
    import asyncio as _aio
    await _aio.sleep(6)
    if pid and (stream_manager.is_healthy(stream_id) or stream_manager.is_running(stream_id)):
        await db.update_stream_status(stream_id, "running", pid)
        status = "🟢 ON AIR"
    else:
        status = "🟡 جاري الاتصال — تحقق من البث الحالي"

    await query.edit_message_text(
        f"🚀 <b>بث احترافي</b>\n\n"
        f"📌 {title}\n"
        f"🆔 #{stream_id}\n"
        f"🎵 AAC 128k · Stereo\n"
        f"📡 {status}",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("📡 فتح لوحة البث", callback_data=f"stream_status:{stream_id}")],
            [InlineKeyboardButton("🔙 رجوع", callback_data="settings")],
        ]),
    )


async def schedule_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """ /schedule اسم | 22:00 | 06:00  — optional source as 4th part """
    text = (update.message.text or "").replace("/schedule", "", 1).strip()
    user_id = update.effective_user.id
    if not text:
        await update.message.reply_text(
            "📅 الاستخدام:\n"
            "`/schedule قرآن الليل | 22:00 | 06:00`\n"
            "أو مع مصدر:\n"
            "`/schedule قرآن | 22:00 | 06:00 | https://...`",
            parse_mode="Markdown",
        )
        return
    parts = [p.strip() for p in text.split("|")]
    if len(parts) < 3:
        await update.message.reply_text("❌ الصيغة: اسم | بداية | نهاية [| مصدر]")
        return
    name, start_t, end_t = parts[0], parts[1], parts[2]
    source = parts[3] if len(parts) > 3 else None
    if not source:
        streams = await db.get_user_streams(user_id)
        source = streams[0]["source_url"] if streams else None
    profile = await db.get_default_rtmp_profile(user_id)
    if not profile or not source:
        await update.message.reply_text("❌ تحتاج مصدر + إعدادات RTMP محفوظة أولاً.")
        return
    rtmp = profile["rtmp_base"].rstrip("/") + "/" + profile["stream_key"].lstrip("/")
    sid = await db.create_schedule(user_id, name, source, rtmp, start_t, end_t, days="daily")
    await db.add_audit(user_id, "schedule_create", str(sid), name)
    await update.message.reply_text(
        f"✅ تم جدولة *{name}*\n⏱ {start_t} → {end_t} (يومياً)\n🆔 #{sid}",
        parse_mode="Markdown",
    )


async def extract_menu_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    from telegram import InlineKeyboardButton, InlineKeyboardMarkup
    context.user_data["await_extract_url"] = True
    await query.edit_message_text(
        "🔎 <b>استخراج رابط البث</b>\n\n"
        "أرسل أي رابط صفحة أو بث:\n"
        "• قناة / راديو / صفحة لايف\n"
        "• رابط m3u8 أو mp3 مباشر\n\n"
        "البوت سيحاول استخراج رابط التشغيل الحقيقي.",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 رجوع", callback_data="main_menu")]]),
    )


async def test_source_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    from telegram import InlineKeyboardButton, InlineKeyboardMarkup
    context.user_data["await_test_url"] = True
    await query.edit_message_text(
        "🧪 <b>اختبار المصدر</b>\n\nأرسل رابط المصدر للفحص:",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 رجوع", callback_data="main_menu")]]),
    )


async def reset_stream_settings_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    from telegram import InlineKeyboardButton, InlineKeyboardMarkup
    await query.edit_message_text(
        "♻️ <b>إعادة ضبط إعدادات البث</b>\n\n"
        "سيتم إرجاع:\n• الصوت 128k\n• Volume 100%\n• بدون start offset\n\n"
        "هل أنت متأكد؟",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup([
            [
                InlineKeyboardButton("✅ نعم", callback_data="reset_stream_confirm"),
                InlineKeyboardButton("❌ لا", callback_data="settings"),
            ]
        ]),
    )


async def reset_stream_confirm_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    streams = await db.get_user_streams(user_id)
    n = 0
    for s in streams[:20]:
        await db.update_stream_meta(s["id"], audio_bitrate="128k", volume=1.0, start_offset=0, last_error="")
        n += 1
    await db.add_audit(user_id, "reset_settings", "", f"streams={n}")
    from telegram import InlineKeyboardButton, InlineKeyboardMarkup
    await query.edit_message_text(
        f"✅ تم إعادة ضبط {n} بث إلى الإعدادات الافتراضية.",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 رجوع", callback_data="settings")]]),
    )


async def maintenance_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if not await _admin_allowed(query.from_user.id, "system.maintenance"):
        await query.answer("للأدمن فقط", show_alert=True)
        return
    from services import maintenance as maint
    from telegram import InlineKeyboardButton, InlineKeyboardMarkup
    st = maint.get_status()
    if st["active"]:
        text = f"🛡 <b>وضع الحماية مفعّل</b>\n\nالسبب: {st.get('reason') or '-'}"
        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("🟢 إلغاء الحماية", callback_data="maint_off")],
            [InlineKeyboardButton("🔙 رجوع", callback_data="admin_panel")],
        ])
    else:
        text = "🛡 <b>وضع الحماية</b>\n\nغير مفعّل حالياً.\nيراقب CPU/RAM/Disk تلقائياً."
        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("🔴 تفعيل يدوياً", callback_data="maint_on")],
            [InlineKeyboardButton("🔙 رجوع", callback_data="admin_panel")],
        ])
    await query.edit_message_text(text, parse_mode="HTML", reply_markup=kb)


async def maint_on_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if not await _admin_allowed(query.from_user.id, "system.maintenance"):
        return
    from services import maintenance as maint
    maint.activate("تفعيل يدوي من الأدمن", block_new=True)
    await query.answer("تم التفعيل", show_alert=True)
    await maintenance_callback(update, context)


async def maint_off_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if not await _admin_allowed(query.from_user.id, "system.maintenance"):
        return
    from services import maintenance as maint
    maint.deactivate()
    await query.answer("تم الإلغاء", show_alert=True)
    await maintenance_callback(update, context)


@rate_limit(calls=8, period=60, key_prefix="admin_act")
async def admin_stop_stream_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if not await _admin_allowed(query.from_user.id, "stream.stop"):
        return
    try:
        sid = int(query.data.split(":")[1])
        from services.stream import stream_manager
        stream_manager.stop_stream(sid)
        await db.update_stream_status(sid, "stopped")
        await db.add_audit(query.from_user.id, "admin_stop_stream", str(sid), "")
        await query.answer(f"⏹ أُوقف البث #{sid}", show_alert=True)
        await admin_streams_callback(update, context)
    except Exception as e:
        logger.exception(e)


@rate_limit(calls=8, period=60, key_prefix="admin_act")
async def admin_ban_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if not await _admin_allowed(query.from_user.id, "users.ban"):
        return
    try:
        uid = int(query.data.split(":")[1])
        if uid == ADMIN_ID:
            await query.answer("لا يمكن حظر الأدمن", show_alert=True)
            return
        await db.ban_user(uid, True)
        await db.add_audit(query.from_user.id, "ban_user", str(uid), "")
        await query.answer(f"🚫 تم حظر {uid}", show_alert=True)
        await admin_users_callback(update, context)
    except Exception as e:
        logger.exception(e)


@rate_limit(calls=8, period=60, key_prefix="admin_act")
async def admin_unban_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if not await _admin_allowed(query.from_user.id, "users.ban"):
        return
    try:
        uid = int(query.data.split(":")[1])
        await db.ban_user(uid, False)
        await db.add_audit(query.from_user.id, "unban_user", str(uid), "")
        await query.answer(f"✅ تم رفع الحظر {uid}", show_alert=True)
        await admin_users_callback(update, context)
    except Exception as e:
        logger.exception(e)


async def admin_logs_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if not await _admin_allowed(query.from_user.id, "system.monitor"):
        return
    from telegram import InlineKeyboardButton, InlineKeyboardMarkup
    try:
        logs = await db.get_audit_logs(limit=20)
    except Exception as e:
        logger.warning("audit logs: %s", e)
        logs = []
    lines = ["📜 <b>سجل النظام (Audit)</b>\n"]
    if not logs:
        lines.append("لا سجلات بعد.")
    for L in logs:
        ts = str(L.get("created_at") or "")
        ts_short = ts[11:19] if len(ts) >= 19 else ts
        act = str(L.get("action") or "").replace("<", "").replace(">", "")
        tgt = str(L.get("target") or "").replace("<", "").replace(">", "")
        lines.append(f"• <code>{ts_short}</code> u:{L.get('user_id')} <b>{act}</b> {tgt}")
    try:
        await query.edit_message_text(
            "\n".join(lines),
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🔄 تحديث", callback_data="admin_logs")],
                [InlineKeyboardButton("🔙 رجوع", callback_data="admin_panel")],
            ]),
        )
    except Exception as e:
        logger.warning("admin_logs edit: %s", e)
        await query.edit_message_text("📜 لا سجلات أو فشل العرض.")
    return
