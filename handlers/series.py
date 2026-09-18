"""Telegram UI for series search / seasons / episodes."""
import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from services import series as svc
from utils.helpers import safe_edit_message
logger=logging.getLogger(__name__)

def _rows(items,n=5):
    return [items[i:i+n] for i in range(0,len(items),n)]

async def series_menu_callback(update, context):
    q=update.callback_query
    try:
        await q.answer()
    except Exception:
        pass
    context.user_data.pop("series_search",None)
    await safe_edit_message(
        q,
        "📺 <b>المسلسلات</b>\n\nأرسل اسم المسلسل بالعربي أو الإنجليزي للبحث.",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 الرئيسية",callback_data="main_menu")]])
    )
    context.user_data["await_series_search"]=True

async def run_series_search(update, context, text):
    msg=await update.message.reply_text(f"🔍 جاري البحث عن «{text}» (جودة عالية)...")
    results=[]
    try:
        from services.oscar_movies import oscar_api
        results = await oscar_api.search_series(text, limit=12)
    except Exception as e:
        logger.warning("oscar series: %s", e)
    if not results:
        try: results=await svc.search_series(text)
        except Exception as e:
            logger.exception(e); results=[]
    if not results:
        await msg.edit_text("❌ لم يتم العثور على مسلسل. جرّب اسماً أقصر.")
        return
    context.user_data["series_results"]=results
    kb=[]
    for i,s in enumerate(results):
        title=s.get("title_ar") or s.get("title_en") or s.get("title") or "مسلسل"
        rating=s.get("rating")
        label=f"{title[:28]}" + (f" ⭐{rating}" if rating else "")
        kb.append([InlineKeyboardButton(label,callback_data=f"series_pick:{i}")])
    kb.append([InlineKeyboardButton("🔙 الرئيسية",callback_data="main_menu")])
    await msg.edit_text(f"📺 <b>النتائج: {len(results)}</b>\nاختر مسلسلًا:",parse_mode="HTML",reply_markup=InlineKeyboardMarkup(kb))

async def series_pick_callback(update,context):
    q=update.callback_query
    try:
        await q.answer()
    except Exception:
        pass
    try:
        i=int(q.data.split(":")[1])
    except Exception:
        return
    results=context.user_data.get("series_results") or []
    if i<0 or i>=len(results):
        return
    s=results[i]; context.user_data["selected_series"]=s
    seasons=[]
    if s.get("source")=="oscar" or s.get("kind")=="series":
        try:
            from services.oscar_movies import oscar_api
            full = await oscar_api.get_series_details(int(s["id"]))
            if full:
                s={**s,**full}
                context.user_data["selected_series"]=s
                seasons=full.get("seasons") or []
        except Exception as e:
            logger.warning("oscar series detail: %s", e)
    if not seasons:
        try:
            seasons=await svc.get_seasons(s.get("id"))
        except Exception:
            seasons=[]
    context.user_data["series_seasons"]=seasons
    kb=[]
    for j,season in enumerate(seasons):
        n=season.get("season_number",j+1)
        cnt=season.get("episodes_count") or ""
        label=f"📺 الموسم {n}" + (f" ({cnt})" if cnt else "")
        kb.append([InlineKeyboardButton(label,callback_data=f"series_season:{j}")])
    if not kb:
        kb.append([InlineKeyboardButton("لا مواسم متاحة",callback_data="noop")])
    kb.append([InlineKeyboardButton("🔙 الرئيسية",callback_data="main_menu")])
    title=s.get("title") or s.get("title_ar") or s.get("title_en") or "مسلسل"
    await safe_edit_message(q, f"🎬 <b>{title}</b>\n\nاختر الموسم:", parse_mode="HTML", reply_markup=InlineKeyboardMarkup(kb))

async def series_season_callback(update,context):
    q=update.callback_query
    try:
        await q.answer()
    except Exception:
        pass
    try:
        i=int(q.data.split(":")[1])
    except Exception:
        return
    seasons=context.user_data.get("series_seasons") or []
    if i<0 or i>=len(seasons):
        return
    season=seasons[i]; context.user_data["selected_season"]=season
    try:
        episodes=await svc.get_episodes(season.get("id"))
    except Exception:
        episodes=[]
    context.user_data["series_episodes"]=episodes
    if not episodes:
        await safe_edit_message(q, "❌ لا توجد حلقات لهذا الموسم.")
        return
    buttons=[InlineKeyboardButton(str(e.get("episode_number",j+1)),callback_data=f"series_episode:{j}") for j,e in enumerate(episodes)]
    kb=_rows(buttons,5)
    kb.append([InlineKeyboardButton("🔙 الرئيسية",callback_data="main_menu")])
    title=(context.user_data.get("selected_series") or {}).get("title_ar") or "مسلسل"
    await safe_edit_message(q, f"🎬 <b>{title}</b>\n📺 اختر الحلقة ({len(episodes)}):", parse_mode="HTML", reply_markup=InlineKeyboardMarkup(kb))

async def series_episode_callback(update,context):
    q=update.callback_query
    try:
        await q.answer()
    except Exception:
        pass
    try:
        i=int(q.data.split(":")[1])
    except Exception:
        return
    eps=context.user_data.get("series_episodes") or []
    if i<0 or i>=len(eps):
        return
    ep=eps[i]
    try:
        links=await svc.get_watch_links(ep.get("id"))
    except Exception:
        links=[]
    # Also try download links if service exposes them
    try:
        dl_links = await svc.get_download_links(ep.get("id")) if hasattr(svc, "get_download_links") else []
    except Exception:
        dl_links = []
    if not links and not dl_links:
        await safe_edit_message(q, "❌ لا توجد روابط متاحة لهذه الحلقة.")
        return
    context.user_data["series_ep_links"] = links or []
    context.user_data["series_ep_dl_links"] = dl_links or []
    context.user_data["series_ep_idx"] = i
    kb=[]
    # Watch links as direct URL buttons
    for j,l in enumerate((links or [])[:6]):
        quality=l.get("quality") or l.get("label") or "مشاهدة"
        url=l.get("url") or l.get("link") or l.get("stream_url") or l.get("streamUrl")
        if url:
            kb.append([InlineKeyboardButton(f"▶️ {quality}", url=url)])
    # Download links as direct URL buttons (no Telegram upload)
    for j,l in enumerate((dl_links or [])[:4]):
        quality=l.get("quality") or l.get("label") or "تحميل"
        url=l.get("url") or l.get("link") or l.get("download_url")
        if url:
            kb.append([InlineKeyboardButton(f"📥 {quality}", url=url)])
    # If only watch links exist and look like mp4, also offer them as download
    if not dl_links:
        for j,l in enumerate((links or [])[:3]):
            url=l.get("url") or ""
            fmt=str(l.get("format") or "").lower()
            if url and (fmt=="mp4" or ".mp4" in url.lower()):
                quality=l.get("quality") or "تحميل"
                kb.append([InlineKeyboardButton(f"📥 {quality}", url=url)])
    first=(links[0].get("url") if links else None)
    if first and str(first).startswith(("http://","https://")):
        kb.append([InlineKeyboardButton("📡 بث على RTMP", callback_data=f"series_play:{i}")])
    kb.append([InlineKeyboardButton("🔙 الحلقات", callback_data="series_back_eps")])
    title = (context.user_data.get("selected_series") or {}).get("title_ar") or "مسلسل"
    n = ep.get("episode_number", i+1)
    await safe_edit_message(
        q,
        f"🎥 <b>{title}</b> — الحلقة {n}\n\nاختر الجودة أو التحميل (رابط مباشر فقط):",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(kb),
    )

async def series_play_callback(update,context):
    q=update.callback_query
    try:
        await q.answer()
    except Exception:
        pass
    try:
        i=int(q.data.split(":")[1])
    except Exception:
        return
    eps=context.user_data.get("series_episodes") or []
    if i<0 or i>=len(eps):
        return
    try:
        links=await svc.get_watch_links(eps[i].get("id"))
    except Exception:
        links=[]
    if not links:
        return
    src=links[0]
    context.user_data["pending_stream_url"]=src.get("url")
    title=(context.user_data.get("selected_series") or {}).get("title_ar") or "مسلسل"
    n=eps[i].get("episode_number","?")
    context.user_data["pending_stream_title"]=f"{title} - الحلقة {n}"
    if isinstance(src.get("headers"),dict):
        context.user_data["pending_stream_headers"]=src["headers"]
    from handlers.streams import start_rtmp_setup_flags
    await start_rtmp_setup_flags(update,context)

async def series_back_eps_callback(update,context):
    q=update.callback_query
    try:
        await q.answer()
    except Exception:
        pass
    eps=context.user_data.get("series_episodes") or []
    buttons=[InlineKeyboardButton(str(e.get("episode_number",i+1)),callback_data=f"series_episode:{i}") for i,e in enumerate(eps)]
    kb=_rows(buttons,5); kb.append([InlineKeyboardButton("🔙 الرئيسية",callback_data="main_menu")])
    await safe_edit_message(q, "📺 اختر الحلقة:", reply_markup=InlineKeyboardMarkup(kb))
