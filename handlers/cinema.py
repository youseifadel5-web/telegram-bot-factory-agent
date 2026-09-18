"""Cinema UI: movies, series, anime, posters, watch/download and pagination."""
from __future__ import annotations
import html
import json
import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from database import db
from services import cinema

logger = logging.getLogger(__name__)
DEFAULT_POSTER = "https://images.unsplash.com/photo-1489599849927-2ee91cede3ba?w=900"
PAGE_SIZE = 10


async def _safe_edit(q, text, *, parse_mode="HTML", reply_markup=None, disable_web_page_preview=True):
    """Edit a cinema UI message whether the callback came from text or a photo.

    Telegram raises BadRequest("There is no text in the message to edit") when
    edit_message_text is used on a photo message. Cinema detail pages are sent
    as photos, so every later navigation action must use this helper.
    """
    msg = getattr(q, "message", None)
    if msg is None:
        return
    try:
        if getattr(msg, "photo", None):
            caption = str(text or "")
            if len(caption) <= 1024:
                try:
                    await q.edit_message_caption(
                        caption=caption, parse_mode=parse_mode,
                        reply_markup=reply_markup,
                    )
                    return
                except Exception:
                    pass
            # Caption is too long or caption editing failed: replace the photo
            # with a normal text message rather than calling edit_message_text.
            try:
                await msg.delete()
            except Exception:
                pass
            await msg.chat.send_message(
                caption, parse_mode=parse_mode,
                reply_markup=reply_markup,
                disable_web_page_preview=disable_web_page_preview,
            )
            return
        await q.edit_message_text(
            text, parse_mode=parse_mode, reply_markup=reply_markup,
            disable_web_page_preview=disable_web_page_preview,
        )
    except Exception as exc:
        # Last-resort fallback: never let a cinema callback crash the update.
        logger.warning("cinema safe edit failed: %s", exc)
        try:
            await msg.chat.send_message(
                text, parse_mode=parse_mode, reply_markup=reply_markup,
                disable_web_page_preview=disable_web_page_preview,
            )
        except Exception:
            logger.exception("cinema fallback send failed")


async def _safe_message_edit(msg, text, *, parse_mode="HTML", reply_markup=None, disable_web_page_preview=True):
    try:
        if getattr(msg, "photo", None):
            caption = str(text or "")
            if len(caption) <= 1024:
                try:
                    await msg.edit_caption(caption=caption, parse_mode=parse_mode, reply_markup=reply_markup)
                    return
                except Exception:
                    pass
            try:
                await msg.delete()
            except Exception:
                pass
            await msg.chat.send_message(caption, parse_mode=parse_mode, reply_markup=reply_markup, disable_web_page_preview=disable_web_page_preview)
            return
        await msg.edit_text(text, parse_mode=parse_mode, reply_markup=reply_markup, disable_web_page_preview=disable_web_page_preview)
    except Exception as exc:
        logger.warning("cinema message edit failed: %s", exc)


def _kind_label(kind):
    return {"movie": "🎬 فيلم", "series": "📺 مسلسل", "anime": "🍿 أنمي"}.get(kind, "🎬 عمل")


def _rows(items, n=2):
    return [items[i:i+n] for i in range(0, len(items), n)]


def _detail_text(item):
    title = html.escape(str(item.get("title") or "بدون عنوان"))
    lines = [f"{_kind_label(item.get('kind'))} <b>{title}</b>"]
    if item.get("year"): lines.append(f"📅 السنة: {html.escape(str(item['year']))}")
    if item.get("rating"): lines.append(f"⭐ التقييم: {html.escape(str(item['rating']))}")
    if item.get("genre"): lines.append(f"🏷️ التصنيف: {html.escape(str(item['genre']))}")
    if item.get("episodes_count"): lines.append(f"📺 الحلقات: {item['episodes_count']}")
    story = str(item.get("story") or "").strip()
    if story: lines.append(f"\n📝 <b>القصة:</b>\n<i>{html.escape(story[:650])}</i>")
    return "\n".join(lines)


def _poster(item):
    url = str(item.get("poster") or "").strip()
    return url if url.startswith(("http://", "https://")) else DEFAULT_POSTER


def _human_size(value):
    if value in (None, "", 0):
        return "الحجم غير متوفر"
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return "الحجم غير متوفر"
        return text
    try:
        n = float(value)
        if n < 1024:
            return f"{int(n)} B"
        if n < 1024**2:
            return f"{n/1024:.1f} KB"
        if n < 1024**3:
            return f"{n/1024**2:.1f} MB"
        return f"{n/1024**3:.2f} GB"
    except Exception:
        return str(value)


def _link_buttons(links):
    """Render compact quality choices; actual Watch/Download choice is made first."""
    rows = []
    for l in links or []:
        if not l.get("url"):
            continue
        q = str(l.get("quality") or "جودة متاحة").strip()
        size = _human_size(l.get("size"))
        label = f"{q} • {size}" if size != "الحجم غير متوفر" else q
        rows.append((q, label, l))
    return rows


def _action_keyboard(links, item_kind="movie"):
    """Compact cinema controls: watch/download, then broadcast/favorite/back."""
    all_links=[x for x in (links or []) if x.get("url")]
    watch=[x for x in all_links if x.get("type") != "download"]
    explicit_download=[x for x in all_links if x.get("type") == "download"]
    # If the API exposes a direct MP4 but omits a separate downloads array, it
    # is still a valid download source; do not invent download links for HLS.
    download=explicit_download or [x for x in watch if str(x.get("format") or "").lower()=="mp4" or ".mp4" in str(x.get("url")).lower()]
    rows=[]
    first=[]
    if watch: first.append(InlineKeyboardButton("▶️ مشاهدة", callback_data="cinema_action:watch"))
    if download: first.append(InlineKeyboardButton("📥 تحميل", callback_data="cinema_action:download"))
    if first: rows.append(first)
    second=[]
    if watch: second.append(InlineKeyboardButton("📡 بث", callback_data="cinema_action:stream"))
    second.append(InlineKeyboardButton("⭐ المفضلة", callback_data="cinema_fav"))
    second.append(InlineKeyboardButton("🔙 السينما", callback_data="cinema_menu"))
    rows.append(second)
    return rows


def _quality_keyboard(links, action):
    rows = []
    prefix = "📥" if action == "download" else ("📡" if action == "stream" else "▶️")
    for i, l in enumerate(links):
        if not l.get("url"):
            continue
        q = str(l.get("quality") or "جودة متاحة").strip()
        size = _human_size(l.get("size"))
        label = f"{prefix} {q}"
        if size != "الحجم غير متوفر":
            label += f" • {size}"
        rows.append([InlineKeyboardButton(label, callback_data=f"cinema_quality:{action}:{i}")])
    rows.append([InlineKeyboardButton("🔙 رجوع", callback_data="cinema_back_item")])
    return InlineKeyboardMarkup(rows)


def _nav(page, has_next, prefix, back="cinema_menu"):
    row = []
    if page > 1: row.append(InlineKeyboardButton("⬅️ السابق", callback_data=f"{prefix}:{page-1}"))
    row.append(InlineKeyboardButton(f"📄 {page}", callback_data="noop"))
    if has_next: row.append(InlineKeyboardButton("التالي ➡️", callback_data=f"{prefix}:{page+1}"))
    rows = [row] if row else []
    rows.append([InlineKeyboardButton("🔙 السينما", callback_data=back)])
    return rows


async def cinema_menu_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query; await q.answer()
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("🎬 الأفلام", callback_data="cinema_list:movie:1"), InlineKeyboardButton("📺 المسلسلات", callback_data="cinema_list:series:1"), InlineKeyboardButton("🍿 الأنمي", callback_data="cinema_list:anime:1")],
        [InlineKeyboardButton("🔍 بحث شامل", callback_data="cinema_search"), InlineKeyboardButton("⭐ المفضلة", callback_data="cinema_favs"), InlineKeyboardButton("🔄 تحديث", callback_data="cinema_menu")],
        [InlineKeyboardButton("🔙 القائمة الرئيسية", callback_data="main_menu")],
    ])
    await _safe_edit(q, "🎬 <b>السينما</b>\n\nاختر القسم الذي تريد تصفحه أو استخدم البحث الشامل.", parse_mode="HTML", reply_markup=kb)


async def cinema_search_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q=update.callback_query; await q.answer(); context.user_data["await_cinema_search"]=True
    await _safe_edit(q, "🔍 <b>بحث شامل</b>\n\nأرسل اسم الفيلم أو المسلسل أو الأنمي:", parse_mode="HTML", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 إلغاء", callback_data="cinema_menu")]]))


async def run_cinema_search(update: Update, context: ContextTypes.DEFAULT_TYPE, text: str):
    context.user_data.pop("await_cinema_search", None)
    msg=await update.message.reply_text("🔍 جاري البحث في الأفلام والمسلسلات والأنمي...")
    try: results=await cinema.search(text, limit=20)
    except Exception:
        logger.exception("cinema search"); results=[]
    if not results:
        await _safe_message_edit(msg, "❌ لم يتم العثور على نتائج.", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔍 بحث جديد",callback_data="cinema_search")],[InlineKeyboardButton("🔙 السينما",callback_data="cinema_menu")]])); return
    context.user_data["cinema_results"]=results; context.user_data["cinema_search_page"]=1
    await _render_search(msg, context, 1)


async def _render_search(msg, context, page):
    results=context.user_data.get("cinema_results") or []; start=(page-1)*PAGE_SIZE; chunk=results[start:start+PAGE_SIZE]
    buttons=[InlineKeyboardButton(f"{_kind_label(r.get('kind'))} {(r.get('title') or 'بدون عنوان')[:34]}",callback_data=f"cinema_pick:{start+i}") for i,r in enumerate(chunk)]
    rows=_rows(buttons,1); rows += _nav(page, start+PAGE_SIZE<len(results), "cinema_search_page")
    # search page callback is handled by a local dispatcher pattern in main
    await _safe_message_edit(msg, f"🔍 <b>نتائج البحث</b> — صفحة {page}", parse_mode="HTML", reply_markup=InlineKeyboardMarkup(rows))


async def cinema_search_page_callback(update, context):
    q=update.callback_query; await q.answer(); page=int(q.data.split(":")[1]); context.user_data["cinema_search_page"]=page
    await _render_search(q.message, context, page)



async def cinema_src_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Source picker for multi-API categories (Oscar / Hekaya)."""
    q = update.callback_query
    try:
        await q.answer()
    except Exception:
        pass
    data = (q.data or "")
    # cinema_src:most | top | latest | genres | wrestling | cartoon
    kind = data.split(":", 1)[-1] if ":" in data else "most"
    labels = {
        "most": "🔥 الأكثر مشاهدة",
        "top": "⭐ الأعلى تقييماً",
        "latest": "🆕 الأحدث",
        "genres": "🎭 التصنيفات",
        "wrestling": "🥊 المصارعة",
        "cartoon": "🧒 الكرتون",
        "year": "📅 حسب السنة",
    }
    title = labels.get(kind, "🎬 السينما")
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("🎬 Oscar", callback_data=f"cinema_list_src:oscar:{kind}")],
        [InlineKeyboardButton("📺 Hekaya TV", callback_data=f"cinema_list_src:hekaya:{kind}")],
        [InlineKeyboardButton("🔙 رجوع", callback_data="cinema_menu")],
    ])
    await _safe_edit(q, f"{title}\n\nاختر المصدر:", reply_markup=kb)


async def cinema_list_src_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """List results for a chosen source + category."""
    q = update.callback_query
    try:
        await q.answer()
    except Exception:
        pass
    parts = (q.data or "").split(":")
    # cinema_list_src:oscar:most or with page cinema_list_src:oscar:most:2
    source = parts[1] if len(parts) > 1 else "oscar"
    kind = parts[2] if len(parts) > 2 else "most"
    page = int(parts[3]) if len(parts) > 3 and parts[3].isdigit() else 1
    results = []
    try:
        if source == "oscar":
            sort_map = {"most": "most_viewed", "top": "top_rated", "latest": "latest"}
            sort_by = sort_map.get(kind, "most_viewed")
            if kind in ("most", "top", "latest"):
                results = await cinema.oscar_api.get_movies(page=page, limit=PAGE_SIZE, sort_by=sort_by)
            elif kind == "anime":
                results = await cinema.oscar_api.get_anime_movies(page=page, limit=PAGE_SIZE)
            else:
                # wrestling/cartoon/genres — try movies list as best effort without inventing
                results = await cinema.oscar_api.get_movies(page=page, limit=PAGE_SIZE)
        else:
            # Hekaya TV — independent path
            try:
                from services import hekaya
                if kind in ("most", "top", "latest"):
                    results = await hekaya.get_movies(page=page, limit=PAGE_SIZE, sort=kind)
                else:
                    results = await hekaya.get_movies(page=page, limit=PAGE_SIZE)
            except Exception as e:
                logger.warning("hekaya list: %s", e)
                results = []
    except Exception as e:
        logger.exception("cinema_list_src: %s", e)
        results = []

    if not results:
        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("🔙 اختر مصدراً", callback_data=f"cinema_src:{kind}")],
            [InlineKeyboardButton("🏠 السينما", callback_data="cinema_menu")],
        ])
        await _safe_edit(q, f"❌ لا توجد نتائج من <b>{html.escape(source)}</b> حالياً.", reply_markup=kb)
        return

    context.user_data["cinema_results"] = results
    context.user_data["cinema_src"] = source
    context.user_data["cinema_kind"] = kind
    rows = []
    for i, r in enumerate(results):
        title = (r.get("title") or "بدون عنوان")[:34]
        rows.append([InlineKeyboardButton(f"{i+1}. {title}", callback_data=f"cinema_pick:{i}")])
    nav = []
    if page > 1:
        nav.append(InlineKeyboardButton("◀ السابق", callback_data=f"cinema_list_src:{source}:{kind}:{page-1}"))
    nav.append(InlineKeyboardButton(f"· {page} ·", callback_data="noop"))
    if len(results) >= PAGE_SIZE:
        nav.append(InlineKeyboardButton("التالي ▶", callback_data=f"cinema_list_src:{source}:{kind}:{page+1}"))
    if nav:
        rows.append(nav)
    rows.append([InlineKeyboardButton("🔙 رجوع", callback_data=f"cinema_src:{kind}")])
    await _safe_edit(q, f"🎬 <b>{html.escape(source)}</b> — صفحة {page}\nاختر عملاً:", reply_markup=InlineKeyboardMarkup(rows))


async def cinema_list_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q=update.callback_query; await q.answer(); parts=q.data.split(":"); kind=parts[1]; page=int(parts[2]) if len(parts)>2 else 1
    try:
        if kind=="movie": results=await cinema.oscar_api.get_movies(page=page,limit=PAGE_SIZE)
        elif kind=="series": results=await cinema.oscar_api.get_series(page=page,limit=PAGE_SIZE)
        else:
            movies=await cinema.oscar_api.get_anime_movies(page=page,limit=PAGE_SIZE//2)
            series=await cinema.oscar_api.get_anime_series(page=page,limit=PAGE_SIZE//2)
            results=movies+series
    except Exception:
        logger.exception("cinema list"); results=[]
    results=[cinema.normalize(x,kind) for x in results if isinstance(x,dict)]
    if not results and page>1:
        await q.answer("⚠️ وصلت إلى نهاية القائمة.",show_alert=True); return
    context.user_data["cinema_results"]=results
    buttons=[InlineKeyboardButton(f"{_kind_label(kind)} {(r.get('title') or 'بدون عنوان')[:34]}",callback_data=f"cinema_pick:{i}") for i,r in enumerate(results)]
    rows=_rows(buttons,1)
    # API page itself determines next availability. If a full page came back, offer next.
    rows += _nav(page, len(results)>=PAGE_SIZE, f"cinema_list:{kind}")
    await _safe_edit(q, f"{_kind_label(kind)}\n\n📄 صفحة <b>{page}</b> — اختر عملاً:",parse_mode="HTML",reply_markup=InlineKeyboardMarkup(rows))


async def cinema_pick_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q=update.callback_query; await q.answer(); idx=int(q.data.split(":")[1]); results=context.user_data.get("cinema_results") or []
    if idx<0 or idx>=len(results): await q.answer("النتيجة غير متاحة",show_alert=True); return
    item=results[idx]; full=await cinema.details(item.get("kind"),item.get("id")) if item.get("id") else None
    if full: item={**item,**full}
    context.user_data["cinema_item"]=item
    rec=context.user_data.setdefault("cinema_recent", [])
    rec=[x for x in rec if x.get("id")!=item.get("id")]
    rec.insert(0, {k:item.get(k) for k in ("id","title","kind","poster","source")})
    context.user_data["cinema_recent"]=rec[:20]
    kb=_action_keyboard(item.get("links") or [], item.get("kind"))
    if item.get("kind") in ("series","anime"):
        for i,s in enumerate(item.get("seasons") or []):
            if s.get("id"):
                kb.append([InlineKeyboardButton(f"📁 الموسم {s.get('season_number',i+1)} • {s.get('episodes_count',0)} حلقة",callback_data=f"cinema_season:{i}")])
        if not item.get("seasons") and item.get("episodes_count"):
            kb.append([InlineKeyboardButton("📺 الحلقات",callback_data="cinema_season:0")])
    caption=_detail_text(item)
    try: await q.message.delete()
    except Exception: pass
    await q.message.chat.send_photo(photo=_poster(item),caption=caption,parse_mode="HTML",reply_markup=InlineKeyboardMarkup(kb))


async def cinema_action_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query; await q.answer()
    action = q.data.split(":", 1)[1]
    item = context.user_data.get("cinema_item") or {}
    links = item.get("links") or []
    from services.cinema import prefer_stream_links
    if action == "download":
        selected = prefer_stream_links(links, for_download=True)
        title = "📥 اختر جودة التحميل"
    else:
        # بث/مشاهدة: أولوية لروابط HLS/m3u8 وليس mp4 المباشر
        selected = prefer_stream_links(links, for_download=False)
        title = "📡 اختر جودة البث" if action == "stream" else "▶️ اختر جودة المشاهدة"
    if not selected:
        await _safe_edit(q, "❌ لا توجد روابط متاحة لهذا الخيار.\n\n🔙 ارجع واختر خياراً آخر.", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 رجوع", callback_data="cinema_back_item")]])); return
    context.user_data["cinema_action_links"] = selected
    context.user_data["cinema_action_type"] = action
    await _safe_edit(q, f"<b>{html.escape(title)}</b>\n\nالجودة والحجم ظاهرين أمامك، اختر المناسب:", parse_mode="HTML", reply_markup=_quality_keyboard(selected, action))


async def cinema_quality_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query; await q.answer()
    parts = q.data.split(":")
    action = parts[1] if len(parts) > 1 else "watch"
    idx = int(parts[2]) if len(parts) > 2 else -1
    links = context.user_data.get("cinema_action_links") or []
    if idx < 0 or idx >= len(links):
        await _safe_edit(q, "❌ الرابط غير متاح.", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 رجوع", callback_data="cinema_back_item")]])); return
    link = links[idx]
    url = link.get("url")
    if not url:
        await _safe_edit(q, "❌ الرابط فارغ.", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 رجوع", callback_data="cinema_back_item")]])); return
    if action == "stream":
        context.user_data["pending_stream_url"] = url
        context.user_data["pending_stream_title"] = context.user_data.get("cinema_item", {}).get("title") or "Cinema"
        if link.get("headers"):
            context.user_data["pending_stream_headers"] = link["headers"]
        try:
            from handlers.streams import start_rtmp_setup_flags
            await start_rtmp_setup_flags(update, context)
        except Exception as exc:
            logger.exception("cinema stream setup: %s", exc)
            try: await q.answer("تعذر بدء إعداد البث", show_alert=True)
            except Exception: pass
        return
    title = str(context.user_data.get("cinema_item", {}).get("title") or "العمل")
    quality = str(link.get("quality") or "متاحة")
    size = _human_size(link.get("size"))
    # Download is always a direct URL button. Never ask Telegram to fetch,
    # upload, or re-send the media through the bot. The API/source remains
    # the only provider of the download URL.
    await q.message.reply_text(
        f"{'▶️ مشاهدة' if action == 'watch' else '📥 تحميل'}\n\n"
        f"🎞️ {html.escape(title)}\n"
        f"🎥 الجودة: <b>{html.escape(quality)}</b>\n"
        f"📦 الحجم: <b>{html.escape(size)}</b>",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("▶️ فتح المصدر" if action == "watch" else "📥 فتح رابط التحميل", url=url)],
            [InlineKeyboardButton("🔙 رجوع", callback_data="cinema_back_item")]
        ])
    )


async def cinema_stream_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q=update.callback_query; await q.answer(); item=context.user_data.get("cinema_item") or {}
    from services.cinema import prefer_stream_links
    ranked = prefer_stream_links(item.get("links") or [], for_download=False)
    link = ranked[0] if ranked else None
    if not link:
        await _safe_edit(q, "❌ لا يوجد رابط تشغيل لهذا العمل.", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 رجوع",callback_data="cinema_back_item")]])); return
    context.user_data["pending_stream_url"]=link.get("url"); context.user_data["pending_stream_title"]=item.get("title") or "Cinema"
    if link.get("headers"): context.user_data["pending_stream_headers"]=link["headers"]
    try:
        from handlers.streams import start_rtmp_setup_flags
        await start_rtmp_setup_flags(update,context)
    except Exception: await q.answer("تعذر تشغيل Stream من إعدادات البث الحالية",show_alert=True)


async def cinema_season_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q=update.callback_query; await q.answer(); item=context.user_data.get("cinema_item") or {}; seasons=item.get("seasons") or []; idx=int(q.data.split(":")[1]); season=seasons[idx] if 0<=idx<len(seasons) else {}
    eps=await cinema.episodes(item.get("kind"),item.get("id"),season.get("id"),page=1)
    context.user_data["cinema_episodes"]=eps; context.user_data["cinema_episode_page"]=1; context.user_data["cinema_selected_season"]=season
    if not eps: await _safe_edit(q, "❌ لا توجد حلقات لهذا الموسم.",reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 رجوع",callback_data="cinema_menu")]])); return
    await _render_episodes(q.message,context,1)


async def _render_episodes(msg,context,page):
    item=context.user_data.get("cinema_item") or {}; season_id=0; seasons=item.get("seasons") or []
    # retrieve the selected season id from stored episode state when available
    season=context.user_data.get("cinema_selected_season") or (seasons[0] if seasons else {})
    season_id=season.get("id")
    eps=await cinema.episodes(item.get("kind"),item.get("id"),season_id,page=page)
    if eps: context.user_data["cinema_episodes"]=eps
    else: eps=[]
    buttons=[InlineKeyboardButton(f"حـ {e.get('episode_number',i+1)}",callback_data=f"cinema_episode:{i}") for i,e in enumerate(eps)]
    rows=_rows(buttons,4); row=[]
    if page>1: row.append(InlineKeyboardButton("⬅️",callback_data=f"cinema_episode_page:{page-1}"))
    row.append(InlineKeyboardButton(f"📄 {page}",callback_data="noop"))
    if len(eps)>=20: row.append(InlineKeyboardButton("➡️",callback_data=f"cinema_episode_page:{page+1}"))
    if row: rows.append(row)
    rows.append([InlineKeyboardButton("🔙 العمل",callback_data="cinema_back_item")])
    await _safe_message_edit(msg, "📺 <b>اختر الحلقة</b>",parse_mode="HTML",reply_markup=InlineKeyboardMarkup(rows))


async def cinema_episode_page_callback(update,context):
    q=update.callback_query; await q.answer(); context.user_data["cinema_episode_page"]=int(q.data.split(":")[1]); await _render_episodes(q.message,context,context.user_data["cinema_episode_page"])


async def cinema_back_item_callback(update,context):
    q=update.callback_query
    await q.answer()
    item=context.user_data.get("cinema_item") or {}
    if not item:
        await _safe_edit(q, "❌ انتهت جلسة العمل.", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 السينما",callback_data="cinema_menu")]]))
        return
    kb=_action_keyboard(item.get("links") or [], item.get("kind"))
    # Keep the detail page visual: always restore the poster when returning.
    try:
        await q.message.delete()
    except Exception:
        pass
    try:
        await q.message.chat.send_photo(
            photo=_poster(item), caption=_detail_text(item), parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup(kb),
        )
    except Exception:
        # If Telegram rejects the poster URL, fall back to text without crashing.
        await q.message.chat.send_message(
            _detail_text(item), parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup(kb),
        )


async def cinema_episode_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q=update.callback_query; await q.answer(); idx=int(q.data.split(":")[1]); eps=context.user_data.get("cinema_episodes") or []
    if idx<0 or idx>=len(eps): return
    ep=eps[idx]; item=context.user_data.get("cinema_item") or {}; details=await cinema.episode_details(item.get("kind"),ep.get("id")); links=(details or {}).get("links") or cinema.normalize_links(details or ep)
    context.user_data["cinema_episode_links"]=links
    watch=[x for x in links if x.get("type") != "download" and x.get("url")]
    download=[x for x in links if x.get("type") == "download" and x.get("url")]
    rows=[]
    if watch: rows.append([InlineKeyboardButton("▶️ مشاهدة",callback_data="cinema_episode_action:watch")])
    if download: rows.append([InlineKeyboardButton("📥 تحميل",callback_data="cinema_episode_action:download")])
    if watch: rows.append([InlineKeyboardButton("📡 بث",callback_data="cinema_episode_action:stream")])
    rows.append([InlineKeyboardButton("🔙 الحلقات",callback_data="cinema_back_episodes")])
    await _safe_edit(q, f"🎥 <b>{html.escape(str(item.get('title') or 'العمل'))}</b>\n\nالحلقة <b>{ep.get('episode_number','?')}</b>\n\nاختر ما تريد أولاً:",parse_mode="HTML",reply_markup=InlineKeyboardMarkup(rows))


async def cinema_episode_action_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q=update.callback_query; await q.answer(); action=q.data.split(":",1)[1]
    links=context.user_data.get("cinema_episode_links") or []
    from services.cinema import prefer_stream_links
    if action=="download":
        selected=prefer_stream_links(links, for_download=True)
    else:
        selected=prefer_stream_links(links, for_download=False)
    if not selected:
        await _safe_edit(q, "❌ لا توجد روابط لهذا الخيار.", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 الحلقات",callback_data="cinema_back_episodes")]])); return
    context.user_data["cinema_episode_action_links"]=selected
    if action=="stream":
        context.user_data["cinema_episode_stream_mode"]=True
    rows=[]
    for i,l in enumerate(selected):
        size=_human_size(l.get("size")); qtxt=str(l.get("quality") or "جودة متاحة")
        rows.append([InlineKeyboardButton(f"{qtxt} • {size}",callback_data=f"cinema_episode_quality:{action}:{i}")])
    rows.append([InlineKeyboardButton("🔙 رجوع",callback_data="cinema_back_episodes")])
    title="📥 اختر جودة التحميل" if action=="download" else "📡 اختر جودة البث" if action=="stream" else "▶️ اختر جودة المشاهدة"
    await _safe_edit(q, f"<b>{title}</b>\n\nالجودة والحجم ظاهرين أمامك:",parse_mode="HTML",reply_markup=InlineKeyboardMarkup(rows))


async def cinema_episode_quality_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q=update.callback_query; await q.answer(); parts=q.data.split(":"); action=parts[1]; idx=int(parts[2]); links=context.user_data.get("cinema_episode_action_links") or []
    if idx<0 or idx>=len(links): return
    link=links[idx]; url=link.get("url")
    if not url:
        await _safe_edit(q, "❌ الرابط غير متاح.", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 الحلقات",callback_data="cinema_back_episodes")]])); return
    if action=="stream":
        context.user_data["pending_stream_url"]=url; context.user_data["pending_stream_title"]="Cinema Episode"
        if link.get("headers"): context.user_data["pending_stream_headers"]=link["headers"]
        try:
            from handlers.streams import start_rtmp_setup_flags
            await start_rtmp_setup_flags(update,context)
        except Exception:
            await q.answer("تعذر تشغيل البث",show_alert=True)
        return
    # For episodes too, download/watch are opened directly from the source.
    await q.message.reply_text(
        f"{'▶️ مشاهدة' if action=='watch' else '📥 تحميل'}\n\n"
        f"🎥 الجودة: <b>{html.escape(str(link.get('quality') or 'متاحة'))}</b>\n"
        f"📦 الحجم: <b>{html.escape(_human_size(link.get('size')))}</b>",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("▶️ فتح الرابط" if action == "watch" else "📥 فتح رابط التحميل", url=url)],
            [InlineKeyboardButton("🔙 الحلقات", callback_data="cinema_back_episodes")]
        ])
    )


async def cinema_back_episodes_callback(update,context):
    q=update.callback_query; await q.answer(); await _render_episodes(q.message,context,context.user_data.get("cinema_episode_page",1))


async def cinema_episode_stream_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q=update.callback_query; await q.answer(); links=context.user_data.get("cinema_episode_links") or []
    if not links: return
    l=next((x for x in links if x.get("type")!="download"),links[0]); context.user_data["pending_stream_url"]=l.get("url"); context.user_data["pending_stream_title"]="Cinema Episode"
    if l.get("headers"): context.user_data["pending_stream_headers"]=l["headers"]
    try:
        from handlers.streams import start_rtmp_setup_flags
        await start_rtmp_setup_flags(update,context)
    except Exception: await q.answer("تعذر تشغيل Stream",show_alert=True)


async def cinema_fav_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q=update.callback_query; item=context.user_data.get("cinema_item") or {}
    if not item.get("id"):
        await q.answer("❌ العنصر غير صالح", show_alert=True); return
    try:
        links=item.get("links") or []
        url=next((x.get("url") for x in links if x.get("type")!="download"),"")
        await db.add_favorite(update.effective_user.id, f"cinema_{item.get('kind')}",
                              item.get("title") or "بدون عنوان", url,
                              json.dumps({"id":item.get("id"),"kind":item.get("kind"),"poster":item.get("poster","")}, ensure_ascii=False))
        await q.answer("⭐ تمت الإضافة للمفضلة", show_alert=True)
    except Exception as e:
        logger.exception("favorite")
        try: await q.answer("❌ تعذر حفظ المفضلة", show_alert=True)
        except Exception: pass


async def cinema_favs_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q=update.callback_query; await q.answer()
    try: favs=await db.get_favorites(update.effective_user.id)
    except Exception: favs=[]
    favs=[f for f in favs if str(f.get("item_type","")).startswith("cinema_")]
    rows=[]
    for f in favs[:40]:
        label="🎬" if f.get("item_type")=="cinema_movie" else "📺" if f.get("item_type")=="cinema_series" else "🍿"
        try: meta=json.loads(f.get("meta") or "{}")
        except Exception: meta={}
        if meta.get("id"): rows.append([InlineKeyboardButton(f"{label} {str(f.get('title') or 'بدون عنوان')[:34]}",callback_data=f"cinema_fav_pick:{f['id']}")])
    rows.append([InlineKeyboardButton("🔙 السينما",callback_data="cinema_menu")])
    await _safe_edit(q, "⭐ <b>المفضلة السينمائية</b>\n\nاختر عملاً:",parse_mode="HTML",reply_markup=InlineKeyboardMarkup(rows))


async def cinema_fav_pick_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q=update.callback_query; await q.answer(); fid=int(q.data.split(":")[1]); favs=await db.get_favorites(update.effective_user.id); f=next((x for x in favs if x.get("id")==fid),None)
    if not f:return
    try: meta=json.loads(f.get("meta") or "{}")
    except Exception: meta={}
    item=await cinema.details(meta.get("kind"),meta.get("id"))
    if not item:return
    context.user_data["cinema_item"]=item
    kb=_action_keyboard(item.get("links") or [], item.get("kind"))
    try: await q.message.delete()
    except Exception: pass
    await q.message.chat.send_photo(photo=_poster(item),caption=_detail_text(item),parse_mode="HTML",reply_markup=InlineKeyboardMarkup(kb))


async def cinema_recent_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    try:
        await q.answer()
    except Exception:
        pass
    recent = context.user_data.get("cinema_recent") or []
    if not recent:
        await _safe_edit(
            q,
            "🕒 <b>المشاهدة الأخيرة</b>\n\nلا يوجد سجل بعد.\nافتح عملاً من السينما ليظهر هنا.",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 السينما", callback_data="cinema_menu")]]),
        )
        return
    context.user_data["cinema_results"] = recent
    rows = []
    for i, r in enumerate(recent[:10]):
        title = str(r.get("title") or "—")[:34]
        rows.append([InlineKeyboardButton(f"{i+1}. {title}", callback_data=f"cinema_pick:{i}")])
    rows.append([InlineKeyboardButton("🔙 السينما", callback_data="cinema_menu")])
    await _safe_edit(q, "🕒 <b>المشاهدة الأخيرة</b>", reply_markup=InlineKeyboardMarkup(rows))
