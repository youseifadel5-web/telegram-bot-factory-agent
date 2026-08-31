# -*- coding: utf-8 -*-
"""
📡 القنوات المباشرة — تصنيف تفصيلي بأسلوب "يوسف باي": نوع ← باقة ← قناة (بوستر + اسم).
المنطق مبني على بيانات يوسف فيلم (Xtream) مع هرم تصنيف ذكي يدمج الأقسام المتشابهة.
"""
from __future__ import annotations

import logging
import re
import time
from typing import Any, Dict, List

from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from telegram.constants import ParseMode

import youseif_core as yc

log = logging.getLogger("live")

PER_PAGE = 10
TTL = 300.0
CACHE: Dict[str, Any] = {"hier": None, "at": 0.0, "streams": {}}

# مضيف شعارات القنوات المستخدم في بوت يوسف باي (ملاحظ من الـ HAR)
LOGO_HOST = "http://51.158.158.30/world_tv_logos"


def _esc(s: str) -> str:
    return (s or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def guess_logo(name: str) -> str:
    """بوستر احتياطي للقناة إذا لم يوجد stream_icon — نفس نمط شعارات يوسف باي (الموجودة فعليًا على 51.158.158.30)."""
    n = (name or "").lower()
    # beIN SPORTS 8 / bein-8 → bein-8.png (النمط المؤكَّد من الـ HAR)
    m = re.search(r"bein[\s\-]?(\d+)", n)
    if m:
        return f"{LOGO_HOST}/bein-{m.group(1)}.png"
    # Al Jazeera / beIN Sports English → شكل عام
    slug = re.sub(r"[^a-z0-9]+", "-", n).strip("-")
    if not slug:
        return ""
    return f"{LOGO_HOST}/{slug}.png"


async def get_hierarchy(store) -> List[Dict]:
    now = time.time()
    if CACHE["hier"] and now - CACHE["at"] < TTL:
        return CACHE["hier"]
    try:
        hier = await yc.build_content_hierarchy(store, "live")
    except Exception:
        log.exception("live hierarchy failed")
        hier = []
    CACHE["hier"] = hier
    CACHE["at"] = now
    return hier or []


async def package_streams(store, ids: List[str]) -> List[Dict]:
    key = ",".join(ids)
    hit = CACHE["streams"].get(key)
    if hit is not None:
        return hit
    seen: set = set()
    out: List[Dict] = []
    for cid in ids[:12]:
        try:
            rows = await store.streams("live", cid)
        except Exception:
            rows = []
        for r in rows or []:
            sid = str(r.get("stream_id") or "")
            if sid and sid not in seen:
                seen.add(sid)
                out.append(r)
    CACHE["streams"][key] = out
    return out


def _slice(items: List, page: int, per: int = PER_PAGE):
    pages = max(1, (len(items) + per - 1) // per)
    page = max(0, min(page, pages - 1))
    return items[page * per:(page + 1) * per], page, pages


async def safe_edit(q, text: str, markup=None):
    try:
        await q.edit_message_text(text, parse_mode=ParseMode.HTML, reply_markup=markup, disable_web_page_preview=True)
    except Exception:
        try:
            await q.message.reply_text(text, parse_mode=ParseMode.HTML, reply_markup=markup)
        except Exception:
            pass


async def show_chan(q, name: str, logo: str, text: str, markup=None):
    """قناة ببوستر + اسمها بشكل احترافي، مع الرجوع للنص إذا فشلت الصورة."""
    if logo:
        try:
            await q.message.delete()
        except Exception:
            pass
        try:
            await q.message.chat.send_photo(
                photo=logo,
                caption=text,
                parse_mode=ParseMode.HTML,
                reply_markup=markup,
                disable_notification=True,
            )
            return
        except Exception:
            pass
    await safe_edit(q, text, markup)


def foot(back: str):
    return [InlineKeyboardButton("⬅️ رجوع", callback_data=back),
            InlineKeyboardButton("🏠 الرئيسية", callback_data="home")]


async def genre_page(q, store):
    """التصنيف التفصيلي: رياضة / أخبار / أطفال / أفلام ... مثل يوسف باي."""
    hier = await get_hierarchy(store)
    if not hier:
        await safe_edit(
            q,
            "❌ لا توجد قنوات متاحة حاليًا.\n"
            "المصدر متوقف مؤقتًا أو غير مربوط — أعد المحاولة لاحقًا.",
            InlineKeyboardMarkup([foot("lib:home")]),
        )
        return
    rows = []
    for i, g in enumerate(hier):
        total = sum(int(p.get("count") or 0) for p in g.get("packages", {}).values())
        rows.append([InlineKeyboardButton(
            f"{g.get('icon', '📡')} {g.get('key', 'عام')} ({total:,})",
            callback_data=f"live:pkg:{i}",
        )])
    rows.append([InlineKeyboardButton("📺 كل القنوات", callback_data="live:all:0")])
    rows.append(foot("lib:home"))
    await safe_edit(
        q,
        "📡 <b>القنوات المباشرة</b>\n"
        "━━━━━━━━━━━━━━━\n"
        "تصنيف تفصيلي مدمج (نوع ← باقة ← قناة):",
        InlineKeyboardMarkup(rows),
    )


async def pkg_page(q, store, gidx: int):
    hier = await get_hierarchy(store)
    if gidx >= len(hier):
        await safe_edit(q, "❌ تصنيف غير موجود.", InlineKeyboardMarkup([foot("lib:live")]))
        return
    g = hier[gidx]
    rows = []
    for pidx, (pkg, p) in enumerate(g.get("packages", {}).items()):
        rows.append([InlineKeyboardButton(
            f"📦 {pkg} ({p.get('count', 0):,})",
            callback_data=f"live:chans:{gidx}:{pidx}:0",
        )])
    rows.append(foot("lib:live"))
    await safe_edit(
        q,
        f"{g.get('icon', '📡')} <b>{_esc(g.get('key', 'عام'))}</b>\nاختر الباقة:",
        InlineKeyboardMarkup(rows),
    )


async def chans_page(q, store, gidx: int, pidx: int, page: int = 0):
    hier = await get_hierarchy(store)
    if gidx >= len(hier):
        await safe_edit(q, "❌ تصنيف غير موجود.", InlineKeyboardMarkup([foot("lib:live")]))
        return
    g = hier[gidx]
    pkgs = list(g.get("packages", {}).items())
    if pidx >= len(pkgs):
        await safe_edit(q, "❌ باقة غير موجودة.", InlineKeyboardMarkup([foot(f"live:pkg:{gidx}")]))
        return
    pkg_name, pkg = pkgs[pidx]
    streams_ = await package_streams(store, pkg.get("ids") or [])
    chunk, page, pages = _slice(streams_, page)
    rows = []
    for i, ch in enumerate(chunk):
        nm = str(ch.get("name") or ch.get("stream_id") or "قناة")
        rows.append([InlineKeyboardButton(f"📡 {nm[:40]}", callback_data=f"live:ch:{gidx}:{pidx}:{i}:{page}")])
    if pages > 1:
        nav = []
        if page > 0:
            nav.append(InlineKeyboardButton("⬅️", callback_data=f"live:chans:{gidx}:{pidx}:{page-1}"))
        nav.append(InlineKeyboardButton(f"{page+1}/{pages}", callback_data="noop"))
        if page < pages - 1:
            nav.append(InlineKeyboardButton("➡️", callback_data=f"live:chans:{gidx}:{pidx}:{page+1}"))
        rows.append(nav)
    rows.append(foot(f"live:pkg:{gidx}"))
    await safe_edit(
        q,
        f"📦 <b>{_esc(pkg_name)}</b>\n📡 {len(streams_):,} قناة\n──────────\nاختر قناة:",
        InlineKeyboardMarkup(rows),
    )


async def render_channel(q, store, ch: Dict, back: str):
    name = str(ch.get("name") or "قناة")
    logo = str(ch.get("stream_icon") or "").strip() or guess_logo(name)
    try:
        url = yc.resolve_live_url(store.xt, ch)
    except Exception:
        url = ""
    cat = str(ch.get("category_name") or "")
    text = (
        f"📡 <b>{_esc(name)}</b>\n"
        "━━━━━━━━━━━━━━━\n"
        f"🗂 {_esc(cat) or '—'}\n\n"
        "اضغط «▶️ بث مباشر» للتشغيل:"
    )
    rows = []
    if url:
        rows.append([InlineKeyboardButton("▶️ بث مباشر", url=url)])
    rows.append(foot(back))
    await show_chan(q, name, logo, text, InlineKeyboardMarkup(rows))


async def chan_page(q, store, gidx: int, pidx: int, idx: int, page: int = 0):
    hier = await get_hierarchy(store)
    if gidx >= len(hier):
        await safe_edit(q, "❌ تصنيف غير موجود.", InlineKeyboardMarkup([foot("lib:live")]))
        return
    g = hier[gidx]
    pkgs = list(g.get("packages", {}).items())
    if pidx >= len(pkgs):
        await safe_edit(q, "❌ باقة غير موجودة.", InlineKeyboardMarkup([foot(f"live:pkg:{gidx}")]))
        return
    _, pkg = pkgs[pidx]
    streams_ = await package_streams(store, pkg.get("ids") or [])
    chunk, cur_page, _ = _slice(streams_, page)
    if idx >= len(chunk):
        await safe_edit(q, "❌ قناة غير موجودة.", InlineKeyboardMarkup([foot(f"live:chans:{gidx}:{pidx}:0")]))
        return
    await render_channel(q, store, chunk[idx], back=f"live:chans:{gidx}:{pidx}:{cur_page}")


def _all_package_ids(hier: List[Dict]) -> List[str]:
    ids: List[str] = []
    for g in hier:
        for p in g.get("packages", {}).values():
            for cid in p.get("ids") or []:
                if cid not in ids:
                    ids.append(cid)
    return ids


async def all_page(q, store, page: int = 0):
    hier = await get_hierarchy(store)
    streams_ = await package_streams(store, _all_package_ids(hier))
    streams_ = streams_[:(PER_PAGE * 30)]
    chunk, page, pages = _slice(streams_, page)
    rows = []
    for i, ch in enumerate(chunk):
        nm = str(ch.get("name") or "قناة")
        rows.append([InlineKeyboardButton(f"📡 {nm[:40]}", callback_data=f"live:chall:{i}:{page}")])
    if pages > 1:
        nav = []
        if page > 0:
            nav.append(InlineKeyboardButton("⬅️", callback_data=f"live:all:{page-1}"))
        nav.append(InlineKeyboardButton(f"{page+1}/{pages}", callback_data="noop"))
        if page < pages - 1:
            nav.append(InlineKeyboardButton("➡️", callback_data=f"live:all:{page+1}"))
        rows.append(nav)
    rows.append(foot("lib:live"))
    await safe_edit(q, f"📺 <b>كل القنوات</b> ({len(streams_):,})\nاختر قناة:", InlineKeyboardMarkup(rows))


async def chan_all(q, store, idx: int, page: int = 0):
    hier = await get_hierarchy(store)
    streams_ = await package_streams(store, _all_package_ids(hier))
    streams_ = streams_[:PER_PAGE * 30]
    chunk, cur_page, _ = _slice(streams_, page)
    if idx >= len(chunk):
        await safe_edit(q, "❌ قناة غير موجودة.", InlineKeyboardMarkup([foot("live:all:0")]))
        return
    await render_channel(q, store, chunk[idx], back=f"live:all:{cur_page}")


async def route(q, store, data: str):
    parts = data.split(":")
    cmd = parts[1] if len(parts) > 1 else ""
    try:
        if cmd == "pkg":
            await pkg_page(q, store, int(parts[2]))
        elif cmd == "chans":
            await chans_page(q, store, int(parts[2]), int(parts[3]), int(parts[4]) if len(parts) > 4 else 0)
        elif cmd == "ch":
            await chan_page(q, store, int(parts[2]), int(parts[3]), int(parts[4]), int(parts[5]) if len(parts) > 5 else 0)
        elif cmd == "all":
            await all_page(q, store, int(parts[2]) if len(parts) > 2 else 0)
        elif cmd == "chall":
            await chan_all(q, store, int(parts[2]), int(parts[3]) if len(parts) > 3 else 0)
        else:
            await genre_page(q, store)
    except (ValueError, IndexError):
        await genre_page(q, store)
