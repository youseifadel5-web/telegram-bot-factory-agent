# -*- coding: utf-8 -*-
"""
Unified Arabic Media Platform V3
Single framework: python-telegram-bot
Plugins provide data · Core manages content · AI understands intent · Playback validates
"""
from __future__ import annotations

import asyncio
import logging
import os
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.constants import ParseMode
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

from ai.intent_parser import IntentParser
from ai.openrouter import OpenRouterClient
from ai.recommender import RecommendationEngine
from bot.keyboards import main_kb as kb
from core.cache import ai_cache, meta_cache, nav_cache, search_cache
from core.models import MediaItem, SearchQuery
from core.moderation import ModerationService
from core.plugin_manager import PluginManager
from core.search_engine import SearchEngine
from bot.middleware.rate_limit import callback_limiter, message_limiter
from database.models import Database
from playback.validator import validate_source
from services.media_service import MediaService

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
log = logging.getLogger("main")

BOT_TOKEN = (os.getenv("BOT_TOKEN") or "").strip()
ADMIN_IDS = set()
for part in (os.getenv("ADMIN_IDS") or os.getenv("ADMIN_ID") or "").replace(";", ",").split(","):
    part = part.strip()
    if part.isdigit():
        ADMIN_IDS.add(int(part))

# App state
db = Database()
moderation = ModerationService(db)
plugins = PluginManager()
search_engine = SearchEngine(plugins, moderation)
media_service = MediaService(search_engine, moderation)
openrouter = OpenRouterClient()
intent_parser = IntentParser(openrouter)
recommender = RecommendationEngine()

# per-user session
USER_STATE: Dict[int, Dict[str, Any]] = {}
ACTION_LOCKS: Dict[str, float] = {}
PER_PAGE = 8


def is_admin(uid: int) -> bool:
    return bool(ADMIN_IDS) and uid in ADMIN_IDS


def lock_ok(key: str, cooldown: float = 1.5) -> bool:
    now = time.time()
    if now - ACTION_LOCKS.get(key, 0) < cooldown:
        return False
    ACTION_LOCKS[key] = now
    return True


def ustate(uid: int) -> Dict[str, Any]:
    return USER_STATE.setdefault(uid, {})


def page_slice(items: List, page: int):
    pages = max(1, (len(items) + PER_PAGE - 1) // PER_PAGE)
    page = max(0, min(page, pages - 1))
    return items[page * PER_PAGE:(page + 1) * PER_PAGE], page, pages


async def safe_edit(q, text: str, markup=None):
    try:
        await q.edit_message_text(text, parse_mode=ParseMode.HTML, reply_markup=markup, disable_web_page_preview=True)
    except Exception:
        try:
            await q.message.reply_text(text, parse_mode=ParseMode.HTML, reply_markup=markup)
        except Exception:
            pass


# ── Commands ──────────────────────────────────────────────
async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """البوابة الرئيسية: 3 منصات + موحّدة اختيارية."""
    u = update.effective_user
    db.touch_user(u.id, u.username or "", u.first_name or "")
    st = ustate(u.id)
    for k in list(st.keys()):
        if k not in ("prefs",):
            st.pop(k, None)
    lines = [
        "✨ <b>اختر وجهتك السينمائية</b> ✨",
        "━━━━━━━━━━━━━━━",
        "🎬 <b>يوسف فيلمز</b> — أفلام · مسلسلات · قنوات",
        "🎞️ <b>سينما نوفا</b> — مكتبة أفلام ومسلسلات",
        "🌟 <b>أوريون بلس</b> — مكتبة إضافية",
    ]
    if kb.unified_enabled():
        lines.append("✨ <b>المنصة الموحّدة</b> — تجريبي (يمكن إيقافها)")
    lines.append("")
    lines.append("اختر منصة من الأزرار:")
    await update.message.reply_text(
        "\n".join(lines),
        parse_mode=ParseMode.HTML,
        reply_markup=kb.hub_home(is_admin(u.id)),
    )


async def cmd_help(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "📚 المكتبة · 🔍 بحث · 🤖 اطلب من AI\n"
        "❤️ مفضلة · 🕘 آخر مشاهدة\n"
        "كل النتائج من مصادر حقيقية بعد إزالة التكرار.",
        reply_markup=kb.back_home(),
    )


# ── Library / search helpers ──────────────────────────────
async def run_search(uid: int, query: SearchQuery) -> List[MediaItem]:
    items = await search_engine.search(query, is_admin=is_admin(uid))
    ustate(uid)["results"] = items
    ustate(uid)["page"] = 0
    return items


def format_results(items: List[MediaItem], title: str, page: int, pages: int) -> str:
    return (
        f"{title}\n━━━━━━━━━━━━━━━\n"
        f"📦 <b>{len(ustate(0).get('results') if False else '')}</b>"
        f"صفحة {page + 1}/{pages} — اختر عملًا:"
    )


async def show_results(q, uid: int, title: str, page: int = 0, back: str = "lib:home"):
    items: List[MediaItem] = ustate(uid).get("results") or []
    ustate(uid)["results_back"] = back
    if not items:
        await safe_edit(
            q,
            f"{title}\n━━━━━━━━━━━━━━━\n"
            f"❌ لا توجد نتائج حاليًا في المصادر المتاحة.\n"
            f"جرّب بحثًا آخر أو قسمًا مختلفًا.",
            kb.empty_results_kb(back=back),
        )
        return
    chunk, page, pages = page_slice(items, page)
    ustate(uid)["page"] = page
    ustate(uid)["page_items"] = chunk
    text = (
        f"{title}\n━━━━━━━━━━━━━━━\n"
        f"✅ <b>{len(items)}</b> نتيجة (بدون تكرار)\n"
        f"📄 صفحة {page + 1}/{pages}"
    )
    await safe_edit(q, text, kb.results_kb(chunk, page, pages, back=back))


async def show_item(q, uid: int, item: MediaItem):
    lines = [
        f"{'🎬' if item.type.value == 'movie' else '📺'} <b>{_esc(item.title)}</b>",
        "━━━━━━━━━━━━━━━",
    ]
    if item.year:
        lines.append(f"📅 {item.year}")
    if item.rating:
        lines.append(f"⭐ {item.rating}")
    if item.countries:
        lines.append("🌍 " + " · ".join(item.countries[:4]))
    if item.genres:
        lines.append("🎭 " + " · ".join(item.genres[:5]))
    if item.overview:
        lines.append(f"\n📝 <i>{_esc(item.overview[:280])}</i>")
    lines.append(f"\n📡 مصادر: {', '.join(item.source_ids) or '—'}")
    ustate(uid)["current_item"] = item
    # series → try load seasons
    if item.type.value == "series":
        seasons = None
        for sid in item.source_ids or []:
            p = plugins.get(sid)
            if p and hasattr(p, "get_series_details"):
                try:
                    sd = await p.get_series_details(item.id)
                    if sd and sd.seasons:
                        seasons = sd.seasons
                        if sd.item:
                            item = sd.item
                            ustate(uid)["current_item"] = item
                        break
                except Exception:
                    log.exception("series details")
        if seasons:
            ustate(uid)["seasons"] = seasons
            rows = []
            for s in seasons[:30]:
                rows.append([InlineKeyboardButton(
                    f"📁 الموسم {s.number} ({s.episode_count or len(s.episodes)} حلقات)",
                    callback_data=f"ser:season:{s.number}",
                )])
            rows.append([
                InlineKeyboardButton("⬅️ رجوع للنتائج", callback_data="lib:results"),
                InlineKeyboardButton("🏠 الرئيسية", callback_data="home"),
            ])
            await safe_edit(q, "\n".join(lines) + "\n\n📚 <b>المواسم</b>", InlineKeyboardMarkup(rows))
            return
    markup = kb.item_kb(item.id, back=ustate(uid).get("results_back") or "hub_home")
    caption = "\n".join(lines)
    poster = (item.poster or "").strip()
    if poster.startswith("http"):
        try:
            await q.message.delete()
        except Exception:
            pass
        try:
            await q.get_bot().send_photo(
                q.message.chat_id,
                poster,
                caption=caption[:1024],
                parse_mode=ParseMode.HTML,
                reply_markup=markup,
            )
            return
        except Exception:
            log.warning("poster send failed for %s", item.id)
    await safe_edit(q, caption, markup)


def _esc(s: str) -> str:
    return (s or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


# ── Callback router ───────────────────────────────────────
async def on_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    data = q.data or ""
    uid = q.from_user.id
    # answer immediately (spec §50)
    try:
        await q.answer()
    except Exception:
        pass
    if not callback_limiter.allow(uid):
        try:
            await q.answer("⏳ استنى لحظة — طلبات كثيرة", show_alert=False)
        except Exception:
            pass
        return

    if data == "noop":
        return
    if data in ("home", "hub_home"):
        await safe_edit(q, "✨ <b>اختر وجهتك السينمائية</b>\nاختر منصة:", kb.hub_home(is_admin(uid)))
        return
    if data in ("lib:home",):
        plat = ustate(uid).get("platform") or "unified"
        await safe_edit(q, "📚 <b>المكتبة</b>", kb.platform_menu(plat, is_admin(uid)))
        return


    # ── اختيار المنصة (3 قديمة + موحّدة اختيارية) ──
    if data.startswith("plat:"):
        plat = data.split(":")[-1]
        if plat == "unified" and not kb.unified_enabled():
            await safe_edit(q, "⚠️ المنصة الموحّدة متوقفة حاليًا.\nفعّلها من لوحة الإدارة أو UNIFIED_PLATFORM_ENABLED=1", kb.hub_home(is_admin(uid)))
            return
        ustate(uid)["platform"] = plat
        titles = {
            "youseif": "🎬 يوسف فيلمز",
            "nova": "🎞️ سينما نوفا",
            "orion": "🌟 أوريون بلس",
            "unified": "✨ المنصة الموحّدة",
        }
        await safe_edit(q, f"{titles.get(plat, plat)}\n━━━━━━━━━━━━━━━\nاختر القسم:", kb.platform_menu(plat, is_admin(uid)))
        return

    # يوسف: تصفح حسب النوع من الـ Store
    if data.startswith("y:type:"):
        typ = data.split(":")[-1]
        ustate(uid)["platform"] = "youseif"
        await safe_edit(q, "⏳ جاري التحميل من يوسف...", kb.back_home())
        items = await run_search(uid, SearchQuery(text="", media_type=typ, limit=40))
        if not items:
            items = await run_search(uid, SearchQuery(text=typ if typ != "live" else "beIN", media_type=typ, limit=40))
        label = {"movie": "🎬 أفلام يوسف", "series": "📺 مسلسلات يوسف", "live": "📡 قنوات يوسف"}.get(typ, typ)
        await show_results(q, uid, label, 0, back="plat:youseif")
        return

    # types
    if data.startswith("lib:type:"):
        typ = data.split(":")[-1]
        items = await run_search(uid, SearchQuery(text="", media_type=typ, limit=40, sort="rating"))
        if not items:
            items = await run_search(uid, SearchQuery(text=typ, media_type=typ, limit=40))
        if not items:
            items = await run_search(uid, SearchQuery(text=typ, limit=40))
        label = {"movie": "🎬 أفلام", "series": "📺 مسلسلات", "live": "📡 قنوات"}.get(typ, typ)
        await show_results(q, uid, label, 0, back="lib:home")
        return

    if data == "lib:countries":
        await safe_edit(q, "🌍 <b>حسب الدولة</b>\nاختر:", kb.countries_kb())
        return

    if data.startswith("lib:country:"):
        country = data.split(":", 2)[2]
        await safe_edit(q, f"🌍 <b>{_esc(country)}</b>\nاختر نوعًا:", kb.country_genres_kb(country))
        return

    if data.startswith("lib:cotype:"):
        _, _, country, typ = data.split(":", 3)
        items = await run_search(uid, SearchQuery(text=country, media_type=typ, countries=[country], limit=40))
        if not items:
            items = await run_search(uid, SearchQuery(text=country, media_type=typ, limit=40))
        await show_results(q, uid, f"🌍 {country} · {typ}", 0, back=f"lib:country:{country}")
        return

    if data.startswith("lib:cogenre:"):
        parts = data.split(":")
        country, genre = parts[2], parts[3]
        items = await run_search(uid, SearchQuery(text=genre, countries=[country], genres=[genre], limit=40))
        if not items:
            items = await run_search(uid, SearchQuery(text=f"{genre} {country}", limit=40))
        await show_results(q, uid, f"🎭 {genre} · 🌍 {country}", 0, back=f"lib:country:{country}")
        return

    if data.startswith("lib:genre:"):
        genre = data.split(":")[-1]
        labels = {"horror": "👻 رعب", "action": "💥 أكشن", "drama": "🎭 دراما", "comedy": "😂 كوميدي",
                  "romance": "❤️ رومانسي", "scifi": "🚀 خيال علمي", "animation": "🧸 أنيميشن"}
        label = labels.get(genre, genre)
        await safe_edit(q, f"{label}\n━━━━━━━━━━━━━━━\nاختر الدولة أو اضغط «عرض الكل»:", kb.genre_countries_kb(genre))
        return

    if data.startswith("lib:gencountry:"):
        _, _, genre, country = data.split(":", 3)
        items = await run_search(uid, SearchQuery(text=genre, genres=[genre], countries=[country], limit=40))
        if not items:
            items = await run_search(uid, SearchQuery(text=f"{genre} {country}", limit=40))
        await show_results(q, uid, f"🎭 {genre} · 🌍 {country}", 0, back=f"lib:genre:{genre}")
        return

    if data.startswith("lib:gensort:"):
        _, _, genre, sort = data.split(":", 3)
        items = await run_search(uid, SearchQuery(text=genre, genres=[genre], sort=sort, limit=40))
        if not items:
            # fallback: text search without strict genre tag (plugins may lack genre metadata)
            items = await run_search(uid, SearchQuery(text=genre, sort=sort, limit=40))
        await show_results(q, uid, f"🎭 {genre} · {sort}", 0, back=f"lib:genre:{genre}")
        return

    if data == "lib:search":
        ustate(uid)["awaiting"] = "search"
        await safe_edit(q, "🔍 <b>بحث</b>\n\nاكتب اسم الفيلم أو المسلسل:", kb.back_home())
        return

    if data == "lib:results":
        items = ustate(uid).get("results") or []
        page = int(ustate(uid).get("page") or 0)
        back = ustate(uid).get("results_back") or "lib:home"
        await show_results(q, uid, "📋 النتائج", page, back=back)
        return

    if data.startswith("lib:page:"):
        page = int(data.split(":")[-1])
        await show_results(q, uid, "📋 النتائج", page)
        return

    if data.startswith("lib:open:"):
        parts = data.split(":")
        page, idx = int(parts[2]), int(parts[3])
        chunk = ustate(uid).get("page_items") or []
        if idx < 0 or idx >= len(chunk):
            await safe_edit(q, "❌ انتهت صلاحية القائمة.", kb.back_home())
            return
        await show_item(q, uid, chunk[idx])
        return

    if data.startswith("lib:item:"):
        item = ustate(uid).get("current_item")
        if item:
            await show_item(q, uid, item)
        return


    # ── Series seasons / episodes (mandatory flow) ──
    if data.startswith("ser:season:"):
        sn = int(data.split(":")[-1])
        seasons = ustate(uid).get("seasons") or []
        season = next((s for s in seasons if getattr(s, "number", None) == sn), None)
        if not season:
            await safe_edit(q, "❌ الموسم غير متاح.", kb.back_home())
            return
        eps = list(getattr(season, "episodes", None) or [])
        if not eps:
            from core.models import Episode
            for i in range(1, int(getattr(season, "episode_count", 0) or 0) + 1):
                eps.append(Episode(
                    id=f"ep-{sn}-{i}",
                    series_id="",
                    season=sn,
                    number=i,
                    title=f"الحلقة {i}",
                ))
        ustate(uid)["current_season"] = sn
        ustate(uid)["episodes"] = eps
        chunk, page, pages = page_slice(eps, 0)
        ustate(uid)["page_items"] = chunk
        rows = []
        for i, e in enumerate(chunk):
            label = f"▶️ الحلقة {e.number}"
            if e.title and e.title != f"الحلقة {e.number}":
                label += f" — {e.title[:24]}"
            rows.append([InlineKeyboardButton(label, callback_data=f"ser:ep:{page}:{i}")])
        if pages > 1:
            nav = []
            if page > 0:
                nav.append(InlineKeyboardButton("⬅️", callback_data=f"ser:eppage:{page-1}"))
            nav.append(InlineKeyboardButton(f"{page+1}/{pages}", callback_data="noop"))
            if page < pages - 1:
                nav.append(InlineKeyboardButton("➡️", callback_data=f"ser:eppage:{page+1}"))
            rows.append(nav)
        rows.append([
            InlineKeyboardButton("⬅️ المواسم", callback_data="lib:item:x"),
            InlineKeyboardButton("🏠 الرئيسية", callback_data="home"),
        ])
        await safe_edit(q, f"📁 <b>الموسم {sn}</b>\nاختر حلقة:", InlineKeyboardMarkup(rows))
        return

    if data.startswith("ser:eppage:"):
        page = int(data.split(":")[-1])
        eps = ustate(uid).get("episodes") or []
        sn = ustate(uid).get("current_season") or 1
        chunk, page, pages = page_slice(eps, page)
        ustate(uid)["page_items"] = chunk
        rows = []
        for i, e in enumerate(chunk):
            rows.append([InlineKeyboardButton(
                f"▶️ الحلقة {e.number}",
                callback_data=f"ser:ep:{page}:{i}",
            )])
        if pages > 1:
            nav = []
            if page > 0:
                nav.append(InlineKeyboardButton("⬅️", callback_data=f"ser:eppage:{page-1}"))
            nav.append(InlineKeyboardButton(f"{page+1}/{pages}", callback_data="noop"))
            if page < pages - 1:
                nav.append(InlineKeyboardButton("➡️", callback_data=f"ser:eppage:{page+1}"))
            rows.append(nav)
        rows.append([
            InlineKeyboardButton("⬅️ المواسم", callback_data="lib:item:x"),
            InlineKeyboardButton("🏠 الرئيسية", callback_data="home"),
        ])
        await safe_edit(q, f"📁 <b>الموسم {sn}</b>\nاختر حلقة:", InlineKeyboardMarkup(rows))
        return

    if data.startswith("ser:ep:"):
        parts = data.split(":")
        page, idx = int(parts[2]), int(parts[3])
        chunk = ustate(uid).get("page_items") or []
        if idx < 0 or idx >= len(chunk):
            await safe_edit(q, "❌ انتهت صلاحية القائمة.", kb.back_home())
            return
        ep = chunk[idx]
        item = ustate(uid).get("current_item")
        from core.models import MediaItem as MI, MediaType as MT
        play_item = MI(
            id=getattr(ep, "id", None) or f"{getattr(item, 'id', 'x')}:s{ep.season}e{ep.number}",
            universal_id=getattr(ep, "id", "") or "",
            title=f"{getattr(item, 'title', '')} — الحلقة {ep.number}".strip(" —"),
            type=MT.EPISODE,
            overview=getattr(ep, "title", "") or "",
            source_ids=list(getattr(item, "source_ids", None) or []),
            sources=list(getattr(ep, "sources", None) or []) or list(getattr(item, "sources", None) or []),
        )
        ustate(uid)["current_item"] = play_item
        lines = [
            f"🎬 <b>الحلقة {ep.number}</b>",
            f"📁 الموسم {ep.season}",
        ]
        if item:
            lines.append(f"📺 {_esc(item.title)}")
        if getattr(ep, "title", None):
            lines.append(f"📝 {_esc(ep.title)}")
        await safe_edit(q, "\n".join(lines), kb.item_kb(play_item.id, back="lib:results"))
        return


    # AI

    # ── بوابة البوتات القديمة ──
    if data.startswith("hub:"):
        which = data.split(":")[-1]
        labels = {
            "youseif": ("🎬 بوت يوسف فيلمز", "Youseif Films — Xtream: أفلام/مسلسلات/قنوات"),
            "nova": ("🎞️ سينما نوفا", "Cinema Nova — مكتبة الأفلام والمسلسلات"),
            "orion": ("🌟 أوريون بلس", "Orion Plus — مكتبة إضافية"),
        }
        title, desc = labels.get(which, (which, ""))
        await safe_edit(
            q,
            f"{title}\n━━━━━━━━━━━━━━━\n"
            f"{desc}\n\n"
            f"المحتوى يظهر داخل المنصة الموحّدة عبر الإضافة "
            f"<code>{which}</code> عند ربط المصدر.\n\n"
            f"استخدم 🔍 بحث أو 📚 المكتبة لاستعراض المحتوى من كل المصادر.",
            kb.main_menu(is_admin(uid)),
        )
        return

    if data == "ai:start":
        ustate(uid)["awaiting"] = "ai"
        ustate(uid)["ai_intent"] = None
        await safe_edit(
            q,
            "🤖 <b>مساعد الأفلام والمسلسلات</b>\n━━━━━━━━━━━━━━━\n"
            "اكتب لي ماذا تريد بالتفصيل.\n\n"
            "مثال:\n"
            "• عاوز فيلم رعب مصري جديد\n"
            "• عاوز مسلسل تركي رومانسي\n"
            "• عاوز فيلم أكشن شبه John Wick\n"
            "• show me something like Breaking Bad\n\n"
            "✍️ اكتب طلبك الآن:",
            kb.back_home(),
        )
        return

    if data.startswith("ai:similar:"):
        item = ustate(uid).get("current_item")
        pool = ustate(uid).get("results") or []
        if not item:
            await safe_edit(q, "❌ لا يوجد عمل محدد.", kb.back_home())
            return
        sims = recommender.similar(item, pool, limit=6)
        if not sims:
            # broaden search
            more = await run_search(uid, SearchQuery(text=item.title[:20], limit=30))
            sims = recommender.similar(item, more, limit=6)
        ustate(uid)["results"] = sims
        await show_results(q, uid, "🤖 اقتراحات مشابهة", 0)
        return

    # Playback
    if data.startswith("play:start:"):
        if not lock_ok(f"play:{uid}"):
            return
        item = ustate(uid).get("current_item")
        if not item:
            await safe_edit(q, "❌ لا يوجد عمل.", kb.back_home())
            return
        await safe_edit(q, "🔍 جاري فحص المصدر...", kb.back_home())
        urls = []
        seen = set()
        def _add_url(u):
            u = (u or "").strip()
            if u and u.startswith("http") and u not in seen:
                seen.add(u)
                urls.append(u)
        for s in item.sources:
            _add_url(getattr(s, "url", None))
            extra = getattr(s, "extra", None) or {}
            for k in ("url", "link", "stream_url", "streamUrl", "play_url", "playUrl",
                      "video_url", "videoUrl", "m3u8_url", "hls_url", "mpd_url", "dash_url"):
                _add_url(extra.get(k) if isinstance(extra, dict) else None)
        # resolve via every plugin that owns this item
        for sid in list(item.source_ids or []):
            p = plugins.get(sid)
            if not p:
                continue
            try:
                extra = await p.get_sources(item.id, item.type.value)
                for e in extra or []:
                    if isinstance(e, str):
                        _add_url(e)
                    elif isinstance(e, dict):
                        for k in ("url", "link", "stream_url", "streamUrl", "play_url", "playUrl",
                                  "video_url", "videoUrl", "m3u8_url", "hls_url", "mpd_url", "dash_url"):
                            _add_url(e.get(k))
            except Exception:
                log.exception("get_sources %s", sid)
        log.info("[SOURCES] item=%s found=%d", item.id, len(urls))
        if not urls:
            await safe_edit(
                q,
                "❌ لا يوجد رابط تشغيل مباشر متاح حاليًا لهذا العنصر من المصادر.\n"
                "تم فحص كل المصادر المتاحة — جرّب لاحقًا أو مصدر آخر.",
                kb.item_kb(item.id),
            )
            return
        best_status = None
        best_qs = []
        best_url = None
        # try all candidates (fallback chain)
        for url in urls[:8]:
            try:
                status, fmt, qualities = await validate_source(url)
                log.info("[VALIDATION] url=%s status=%s fmt=%s qs=%s", url[:80], getattr(status, "value", status), fmt, [getattr(x, "label", x) for x in (qualities or [])])
                if status.value in ("playable", "partially_playable"):
                    best_status, best_qs, best_url = status, qualities, url
                    break
            except Exception:
                log.exception("validate %s", url[:80])
        if not best_url:
            await safe_edit(q, "❌ المصدر غير متاح حاليًا.\n🔄 جرّب لاحقًا أو مصدر بديل.", kb.item_kb(item.id))
            return
        ustate(uid)["play_url"] = best_url
        ustate(uid)["play_qualities"] = best_qs
        db.add_history(uid, item.id, item.title, item.type.value)
        await safe_edit(
            q,
            f"🟢 المصدر صالح للتشغيل\nاختر الجودة:",
            kb.qualities_kb(item.id, best_qs or []),
        )
        return

    if data.startswith("play:q:"):
        if not lock_ok(f"playq:{uid}", 2.0):
            return
        parts = data.split(":")
        label = parts[-1]
        item = ustate(uid).get("current_item")
        qualities = ustate(uid).get("play_qualities") or []
        chosen = next((x for x in qualities if x.label == label), None)
        if not chosen:
            await safe_edit(q, "❌ هذه الجودة غير متاحة حاليًا.", kb.back_home())
            return
        # re-validate
        status, _, _ = await validate_source(chosen.url)
        if status.value not in ("playable", "partially_playable"):
            await safe_edit(q, "❌ هذه الجودة غير متاحة حاليًا.\n🔄 تجربة مصدر بديل...", kb.item_kb(item.id if item else "x"))
            return
        await safe_edit(
            q,
            f"▶️ <b>تشغيل {label}</b>\n\n"
            f"<a href=\"{_esc(chosen.url)}\">اضغط هنا للتشغيل</a>\n\n"
            f"<code>{_esc(chosen.url[:120])}</code>",
            kb.item_kb(item.id) if item else kb.back_home(),
        )
        return

    # user fav/hist
    if data == "user:fav":
        favs = db.get_favorites(uid)
        if not favs:
            await safe_edit(q, "❤️ المفضلة فارغة.", kb.back_home())
            return
        lines = ["❤️ <b>المفضلة</b>", "━━━━━━━━━━━━━━━"]
        for f in favs[:20]:
            lines.append(f"• {_esc(f.get('title') or f.get('media_id'))}")
        await safe_edit(q, "\n".join(lines), kb.back_home())
        return

    if data == "user:hist":
        hist = db.get_history(uid)
        if not hist:
            await safe_edit(q, "🕘 لا يوجد سجل مشاهدة.", kb.back_home())
            return
        lines = ["🕘 <b>آخر مشاهدة</b>", "━━━━━━━━━━━━━━━"]
        for h in hist[:20]:
            lines.append(f"• {_esc(h.get('title') or '')}")
        await safe_edit(q, "\n".join(lines), kb.back_home())
        return

    if data.startswith("user:addfav:"):
        item = ustate(uid).get("current_item")
        if item:
            db.add_favorite(uid, item.id, item.title, item.type.value)
            await safe_edit(q, "❤️ تمت الإضافة للمفضلة.", kb.item_kb(item.id))
        return

    # Admin
    if data.startswith("adm:"):
        if not is_admin(uid):
            hint = (
                "🚫 للأدمن فقط.\n\n"
                "لو أنت المالك: تأكد إن <code>ADMIN_IDS</code> في Secrets "
                f"فيه رقمك: <code>{uid}</code>"
            )
            await safe_edit(q, hint, kb.back_home())
            return
        await handle_admin(q, uid, data)
        return


async def handle_admin(q, uid: int, data: str):
    if data == "adm:toggle_unified":
        # تبديل عبر ملف بسيط (يستمر بعد إعادة التشغيل عبر env أفضل)
        import pathlib
        flag_path = pathlib.Path(__file__).resolve().parent / ".unified_enabled"
        currently = kb.unified_enabled()
        if currently:
            # أوقف: امسح الملف واضبط env للجلسة
            try:
                flag_path.unlink(missing_ok=True)
            except Exception:
                pass
            os.environ["UNIFIED_PLATFORM_ENABLED"] = "0"
            msg = "🔴 تم إيقاف المنصة الموحّدة"
        else:
            flag_path.write_text("1", encoding="utf-8")
            os.environ["UNIFIED_PLATFORM_ENABLED"] = "1"
            msg = "🟢 تم تشغيل المنصة الموحّدة"
        await safe_edit(q, msg + "\n\nأعد /start لرؤية التغيير في البوابة.", kb.admin_home_kb())
        return
    if data == "adm:home":
        await safe_edit(q, "👑 <b>لوحة التحكم</b>", kb.admin_home_kb())
        return
    if data == "adm:stats":
        await safe_edit(
            q,
            f"📊 <b>إحصائيات</b>\n━━━━━━━━━━━━━━━\n"
            f"👥 مستخدمون: <b>{db.users_count()}</b>\n"
            f"🤖 إضافات: <b>{len(plugins.plugins)}</b>\n"
            f"🚫 محظور: <b>{len(moderation._blocks)}</b>",
            kb.admin_home_kb(),
        )
        return
    if data == "adm:plugins":
        health = await plugins.health_all()
        lines = ["📡 <b>حالة المصادر</b>", "━━━━━━━━━━━━━━━"]
        for pid, h in health.items():
            mark = "🟢" if h.get("ok") else "🔴"
            lat = h.get("latency_ms", "?")
            name = plugins.plugins[pid].name if pid in plugins.plugins else pid
            lines.append(f"{mark} {name} — {lat}ms")
        await safe_edit(q, "\n".join(lines), kb.admin_home_kb())
        return
    if data == "adm:ai":
        st = openrouter.stats
        status = "🟢" if openrouter.enabled else "🔴"
        await safe_edit(
            q,
            f"🧠 <b>AI</b>\n━━━━━━━━━━━━━━━\n"
            f"الحالة: {status}\n"
            f"الموديل: <code>{_esc(openrouter.model)}</code>\n"
            f"طلبات: {st['requests']} · نجاح: {st['success']} · فشل: {st['fail']}\n"
            f"Cache hits: {st['cache_hits']}",
            kb.admin_home_kb(),
        )
        return
    if data == "adm:cache":
        search_cache.clear()
        nav_cache.clear()
        ai_cache.clear()
        meta_cache.clear()
        await safe_edit(q, "🗄 تم مسح الكاش.", kb.admin_home_kb())
        return
    if data == "adm:blocks":
        await safe_edit(q, "🚫 <b>المحظور</b>", kb.admin_blocks_kb())
        return
    if data.startswith("adm:blocklist:"):
        page = int(data.split(":")[-1])
        items, total = moderation.list_blocks(page=page)
        lines = [f"🚫 <b>المحظور</b> ({total})", "━━━━━━━━━━━━━━━"]
        rows = []
        for b in items:
            name = b.get("content_name") or b.get("content_id")
            cid = b.get("content_id")
            lines.append(
                f"🎬 {_esc(name)}\n"
                f"الاسم: <code>{_esc(name)}</code>\n"
                f"ID: <code>{_esc(cid)}</code> · {b.get('content_type')} · src={b.get('source_id')}"
            )
            rows.append([
                InlineKeyboardButton(f"📋 نسخ {str(cid)[:12]}", callback_data=f"adm:copy:{cid}"),
                InlineKeyboardButton("🔓 فك", callback_data=f"adm:unblok:{b.get('content_type')}:{cid}"),
            ])
        if not items:
            lines.append("لا يوجد محتوى محظور.")
        rows.append([InlineKeyboardButton("⬅️ رجوع", callback_data="adm:blocks")])
        await safe_edit(q, "\n".join(lines), InlineKeyboardMarkup(rows) if rows else kb.admin_blocks_kb())
        return
    if data.startswith("adm:unblok:"):
        parts = data.split(":")
        if len(parts) >= 4:
            moderation.unblock(parts[2], parts[3], admin_id=uid)
            await safe_edit(q, f"🔓 تم فك الحظر عن <code>{_esc(parts[3])}</code>", kb.admin_blocks_kb())
        return
    if data == "adm:blockadd":
        ustate(uid)["awaiting"] = "block_one"
        await safe_edit(q, "➕ أرسل: <code>type|id|name</code>\nمثال: <code>movie|12345|Film Name</code>", kb.admin_blocks_kb())
        return
    if data == "adm:blockbulk":
        ustate(uid)["awaiting"] = "block_bulk"
        await safe_edit(
            q,
            "📦 <b>حظر جماعي</b>\nأرسل قائمة (سطر لكل عنصر):\n"
            "<code>name | id</code>\nأو\n<code>id</code>\n\nسيتم عرض مراجعة قبل التأكيد.",
            kb.admin_blocks_kb(),
        )
        return
    if data == "adm:blockconfirm":
        pending = ustate(uid).get("bulk_pending") or []
        for p in pending:
            moderation.block(p.get("type", "movie"), p["id"], p.get("name", ""), admin_id=uid, reason="bulk")
        ustate(uid).pop("bulk_pending", None)
        await safe_edit(q, f"🚫 تم حظر <b>{len(pending)}</b> عنصر.", kb.admin_blocks_kb())
        return
    if data == "adm:unblock":
        ustate(uid)["awaiting"] = "unblock"
        await safe_edit(q, "🔓 أرسل ID لفك الحظر:", kb.admin_blocks_kb())
        return
    if data.startswith("adm:copy:"):
        cid = data.split(":", 2)[2]
        try:
            await q.answer(f"ID: {cid}", show_alert=True)
        except Exception:
            pass
        try:
            await q.message.reply_text(f"📋 <code>{_esc(cid)}</code>", parse_mode=ParseMode.HTML)
        except Exception:
            pass
        return
    if data == "adm:audit":
        logs = moderation.audit_log(30)
        lines = ["📝 <b>سجل الإدارة</b>", "━━━━━━━━━━━━━━━"]
        for a in logs[:20]:
            lines.append(f"{a.get('action')} · {a.get('content_id')} · admin={a.get('admin_id')}")
        if not logs:
            lines.append("فارغ.")
        await safe_edit(q, "\n".join(lines), kb.admin_home_kb())
        return


# ── Text messages ────────────────────────────────────────
async def on_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    u = update.effective_user
    uid = u.id
    text = (update.message.text or "").strip()
    if not text:
        return
    if not message_limiter.allow(uid):
        await update.message.reply_text("⏳ طلبات كثيرة — حاول بعد دقيقة.")
        return
    db.touch_user(uid, u.username or "", u.first_name or "")
    awaiting = ustate(uid).get("awaiting")

    if awaiting == "search":
        ustate(uid)["awaiting"] = None
        msg = await update.message.reply_text("🔍 جاري البحث...")
        items = await run_search(uid, SearchQuery(text=text, limit=40))
        chunk, page, pages = page_slice(items, 0)
        ustate(uid)["page_items"] = chunk
        await msg.edit_text(
            f"🔍 نتائج «{_esc(text)}»\n✅ {len(items)} بدون تكرار",
            parse_mode=ParseMode.HTML,
            reply_markup=kb.results_kb(chunk, page, pages),
        )
        return

    if awaiting == "ai":
        msg = await update.message.reply_text("🤖 جاري فهم طلبك...")
        prev = ustate(uid).get("ai_intent")
        try:
            intent = await intent_parser.parse(text, previous=prev)
        except Exception:
            log.exception("intent parse")
            intent = None
        if intent is None:
            await msg.edit_text(
                "❌ مساعد AI غير متاح مؤقتًا.\nاستخدم 🔍 البحث العادي.",
                reply_markup=kb.back_home(),
            )
            ustate(uid)["awaiting"] = None
            return
        ustate(uid)["ai_intent"] = intent
        if intent.needs_clarification and intent.clarification_question:
            await msg.edit_text(f"🤖 {intent.clarification_question}", reply_markup=kb.back_home())
            return
        # keep awaiting for refinement
        sq = SearchQuery(
            text=intent.query_text or text,
            media_type=None if intent.type == "any" else intent.type,
            genres=intent.genres,
            countries=intent.countries,
            year_min=intent.year_min,
            year_max=intent.year_max,
            sort=intent.sort,
            limit=40,
        )
        items = await run_search(uid, sq)
        # AI must not invent — only real items
        items = moderation.filter_items(items, is_admin=is_admin(uid))
        if not items:
            await msg.edit_text(
                "🤖 فهمت طلبك لكن لا توجد نتائج متاحة حاليًا في المصادر.\n"
                "جرّب صياغة أخرى أو البحث العادي.",
                reply_markup=kb.back_home(),
            )
            return
        chunk, page, pages = page_slice(items, 0)
        ustate(uid)["page_items"] = chunk
        reason = intent.explanation or "نتائج حقيقية من مكتبتك حسب طلبك."
        await msg.edit_text(
            f"🤖 فهمت طلبك\n━━━━━━━━━━━━━━━\n"
            f"النوع: {intent.type} · الأنواع: {', '.join(intent.genres) or '—'}\n"
            f"الدول: {', '.join(intent.countries) or '—'}\n\n"
            f"💡 <i>{_esc(reason)}</i>\n\n"
            f"✅ {len(items)} نتيجة حقيقية:",
            parse_mode=ParseMode.HTML,
            reply_markup=kb.results_kb(chunk, page, pages),
        )
        return

    if awaiting == "block_one" and is_admin(uid):
        ustate(uid)["awaiting"] = None
        parts = [p.strip() for p in text.replace(",", "|").split("|")]
        if len(parts) >= 2:
            typ, cid = parts[0], parts[1]
            name = parts[2] if len(parts) > 2 else cid
            moderation.block(typ, cid, name, admin_id=uid, reason="manual")
            await update.message.reply_text(f"🚫 تم حظر {name} ({cid})", reply_markup=kb.admin_blocks_kb())
        else:
            await update.message.reply_text("صيغة غير صحيحة.", reply_markup=kb.admin_blocks_kb())
        return

    if awaiting == "block_bulk" and is_admin(uid):
        lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
        pending = []
        for ln in lines:
            if "|" in ln:
                name, cid = [x.strip() for x in ln.split("|", 1)]
            else:
                name, cid = ln, ln
            pending.append({"type": "movie", "id": cid, "name": name})
        ustate(uid)["bulk_pending"] = pending
        ustate(uid)["awaiting"] = None
        preview = "\n".join(f"{i+1}. {p['name']} — {p['id']}" for i, p in enumerate(pending[:20]))
        await update.message.reply_text(
            f"🚫 مراجعة الحظر الجماعي\nتم العثور على {len(pending)} عناصر:\n\n{preview}",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🚫 تأكيد الحظر", callback_data="adm:blockconfirm")],
                [InlineKeyboardButton("❌ إلغاء", callback_data="adm:blocks")],
            ]),
        )
        return

    if awaiting == "unblock" and is_admin(uid):
        ustate(uid)["awaiting"] = None
        moderation.unblock("movie", text.strip(), admin_id=uid)
        moderation.unblock("series", text.strip(), admin_id=uid)
        moderation.unblock("live", text.strip(), admin_id=uid)
        await update.message.reply_text(f"🔓 تم فك الحظر عن {text.strip()}", reply_markup=kb.admin_blocks_kb())
        return

    # default: treat as search refinement if AI session active
    if ustate(uid).get("ai_intent"):
        ustate(uid)["awaiting"] = "ai"
        return await on_text(update, context)

    await update.message.reply_text("استخدم القائمة أو /start", reply_markup=kb.main_menu(is_admin(uid)))


# ── Bootstrap ─────────────────────────────────────────────
def bind_legacy_plugins():
    """Optionally bind existing cores if available — plugins stay independent."""
    # Cinema Nova + Orion (same cinema_core module)
    try:
        import cinema_core as cc
        p = plugins.get("nova")
        if p and hasattr(p, "bind_api") and getattr(cc, "api", None) is not None:
            p.bind_api(cc.api)
            log.info("Bound nova api")
        p2 = plugins.get("orion")
        if p2 and hasattr(p2, "bind_vault") and getattr(cc, "vault_api", None) is not None:
            p2.bind_vault(cc.vault_api)
            log.info("Bound orion vault")
    except Exception as e:
        log.info("cinema_core not bound (optional): %s", e)

    # Youseif Films — prefer constructing Store without full Telegram bot if possible
    try:
        import youseif_core as yc
        p = plugins.get("youseif")
        if p and hasattr(p, "bind_store"):
            store = None
            # Try lightweight path: Xtream + Store from config credentials
            try:
                from config import IPTV_USERNAME, IPTV_PASSWORD, IPTV_BASE_URL, IPTV_BACKUP_URLS, DB_PATH
                bases = [IPTV_BASE_URL] + list(IPTV_BACKUP_URLS or [])
                xt = yc.Xtream(bases, IPTV_USERNAME, IPTV_PASSWORD)
                db = yc.DB(DB_PATH)
                store = yc.Store(xt, db)
                log.info("Built youseif Store from config")
            except Exception as e:
                log.info("youseif lightweight Store failed: %s", e)
                try:
                    bot = yc.CinemaBot()
                    store = getattr(bot, "store", None)
                except Exception as e2:
                    log.info("youseif CinemaBot failed: %s", e2)
            if store is not None:
                p.bind_store(store)
                log.info("Bound youseif store")
    except Exception as e:
        log.info("youseif_core not bound (optional): %s", e)


def main():
    if not BOT_TOKEN:
        raise SystemExit("BOT_TOKEN missing")
    plugins.discover()
    bind_legacy_plugins()
    # load blocks from db
    for b in db.load_blocks():
        moderation._blocks[(b["content_type"], b["content_id"], b.get("source_id") or "*")] = dict(b)

    app = Application.builder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("help", cmd_help))
    app.add_handler(CallbackQueryHandler(on_callback))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, on_text))
    log.info("🚀 Platform V3 starting · plugins=%s · AI=%s", list(plugins.plugins), openrouter.enabled)
    app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()
