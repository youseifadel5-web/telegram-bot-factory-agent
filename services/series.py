"""Series API client for the supplied DramaRamadan API."""
from __future__ import annotations
import asyncio, json, logging
import aiohttp
logger=logging.getLogger(__name__)
BASE_URL="https://admin.dramaramadan.net/api"

def _headers():
    return {"User-Agent":"okhttp/4.12.0","Accept-Encoding":"gzip","Accept":"application/json","Connection":"keep-alive"}

async def _get(path, params=None, attempts=4):
    last=None
    for i in range(attempts):
        try:
            async with aiohttp.ClientSession(headers=_headers()) as s:
                async with s.get(f"{BASE_URL}{path}", params=params or {}, timeout=aiohttp.ClientTimeout(total=20)) as r:
                    if r.status != 200: raise RuntimeError(f"HTTP {r.status}")
                    return await r.json(content_type=None)
        except Exception as e:
            last=e
            if i+1<attempts: await asyncio.sleep(min(2**i,5))
    logger.warning("series API failed %s: %s", path, last)
    return None

def _items(d):
    if isinstance(d,list): return d
    if isinstance(d,dict): return d.get("data") or d.get("results") or d.get("items") or []
    return []

async def search_series(q, limit=20):
    q=(q or "").strip()
    if len(q)<2: return []
    d=await _get("/series/", {"page":1,"limit":limit,"search":q,"app_version":9})
    return _items(d)[:limit]

async def get_seasons(series_id):
    d=await _get("/seasons/", {"series_id":series_id})
    seasons=_items(d)
    return seasons or [{"id":series_id,"season_number":1}]

async def get_episodes(season_id):
    d=await _get("/episodes/", {"season_id":season_id})
    return _items(d)

async def get_watch_links(episode_id):
    d=await _get("/episodes/show.php", {"id":episode_id})
    if isinstance(d,dict):
        data=d.get("data") or d
        links = (
            data.get("watch_links")
            or data.get("sources")
            or data.get("streams")
            or data.get("links")
            or []
        )
        out = []
        for x in links:
            if not isinstance(x, dict):
                continue
            url = x.get("url") or x.get("link") or x.get("stream_url") or x.get("streamUrl")
            if url:
                y = dict(x)
                y["url"] = url
                out.append(y)
        return out
    return []


async def get_download_links(episode_id):
    """Return download-oriented links only (direct URL, no Telegram upload)."""
    d = await _get("/episodes/show.php", {"id": episode_id})
    if not isinstance(d, dict):
        return []
    data = d.get("data") or d
    candidates = (
        data.get("download_links")
        or data.get("downloads")
        or data.get("download")
        or []
    )
    out = []
    for x in candidates:
        if not isinstance(x, dict):
            continue
        url = x.get("url") or x.get("link") or x.get("download_url")
        if url:
            y = dict(x)
            y["url"] = url
            y["type"] = "download"
            out.append(y)
    # Also accept top-level download_url
    top = data.get("download_url") or data.get("download_link")
    if top and isinstance(top, str) and top.startswith("http"):
        out.append({"url": top, "quality": "تحميل", "type": "download"})
    return out
