"""IPTV M3U/M3U8 playlist parser and channel list."""
import logging
import re
from pathlib import Path
from typing import List, Dict, Optional, Any
from urllib.parse import urlparse

logger = logging.getLogger(__name__)

ROOT = Path(__file__).resolve().parent.parent
IPTV_DIR = ROOT / "data" / "iptv"
IPTV_DIR.mkdir(parents=True, exist_ok=True)



# Channels that the user requested not to display. Filtering is applied at
# presentation/load time so existing playlists are not destroyed.
BLOCKED_CHANNEL_TERMS = (
    "انجيل", "إنجيل", "انجيلية", "إنجيلية", "gospel", "bible",
    "jesus", "christian", "christianity", "coptic", "church",
    "كنيسة", "مسيحي", "مسيحية", "christ",
)

def is_blocked_channel(channel: Dict[str, Any]) -> bool:
    blob = " ".join(str(channel.get(k) or "") for k in ("name", "group", "tvg_id")).casefold()
    return any(term.casefold() in blob for term in BLOCKED_CHANNEL_TERMS)

def filter_visible_channels(channels: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    return [c for c in (channels or []) if isinstance(c, dict) and not is_blocked_channel(c)]

def parse_m3u(content: str) -> List[Dict[str, Any]]:
    """Parse M3U/M3U8 playlist text into channel list."""
    channels = []
    lines = content.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    name, logo, group, tvg_id = "قناة", "", "عام", ""
    for line in lines:
        line = line.strip()
        if not line:
            continue
        if line.startswith("#EXTINF:"):
            # #EXTINF:-1 tvg-id=".." tvg-logo=".." group-title="..",Name
            name = line.split(",")[-1].strip() if "," in line else "قناة"
            m_logo = re.search(r'tvg-logo="([^"]*)"', line, re.I)
            m_group = re.search(r'group-title="([^"]*)"', line, re.I)
            m_id = re.search(r'tvg-id="([^"]*)"', line, re.I)
            logo = m_logo.group(1) if m_logo else ""
            group = m_group.group(1) if m_group else "عام"
            tvg_id = m_id.group(1) if m_id else ""
        elif line.startswith("#"):
            continue
        elif line.startswith(("http://", "https://", "rtmp://", "rtmps://")):
            channels.append({
                "name": name or "قناة",
                "url": line,
                "logo": logo,
                "group": group or "عام",
                "tvg_id": tvg_id,
            })
            name, logo, group, tvg_id = "قناة", "", "عام", ""
    return channels


async def fetch_m3u(url: str, timeout: int = 20) -> List[Dict[str, Any]]:
    import aiohttp
    headers = {"User-Agent": "Mozilla/5.0 (compatible; StreamBot-IPTV/1.0)"}
    async with aiohttp.ClientSession() as session:
        async with session.get(url, headers=headers, timeout=aiohttp.ClientTimeout(total=timeout)) as resp:
            if resp.status >= 400:
                raise RuntimeError(f"HTTP {resp.status}")
            text = await resp.text(errors="ignore")
    return parse_m3u(text)


def _user_playlists_path(user_id: int) -> Path:
    return IPTV_DIR / f"user_{user_id}_playlists.json"


def _legacy_path(user_id: int) -> Path:
    return IPTV_DIR / f"user_{user_id}.json"


def list_user_playlists(user_id: int) -> List[Dict]:
    """Return list of {id, name, channel_count} without full channels."""
    import json
    path = _user_playlists_path(user_id)
    playlists = []
    if path.exists():
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            for p in data.get("playlists") or []:
                playlists.append({
                    "id": p.get("id"),
                    "name": p.get("name") or "قائمة",
                    "channel_count": len(filter_visible_channels(p.get("channels") or [])),
                })
        except Exception as e:
            logger.warning("list playlists: %s", e)
    # migrate legacy single playlist
    legacy = _legacy_path(user_id)
    if legacy.exists() and not playlists:
        try:
            old = json.loads(legacy.read_text(encoding="utf-8"))
            playlists.append({
                "id": "legacy",
                "name": old.get("name") or "قائمتي",
                "channel_count": len(filter_visible_channels(old.get("channels") or [])),
            })
        except Exception:
            pass
    return playlists


def save_user_playlist(user_id: int, name: str, channels: List[Dict], playlist_id: str = None) -> str:
    """Save a playlist. If playlist_id given, update it; else add new. Never deletes others."""
    import json
    import time
    path = _user_playlists_path(user_id)
    data = {"playlists": []}
    if path.exists():
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            if not isinstance(data.get("playlists"), list):
                data = {"playlists": []}
        except Exception:
            data = {"playlists": []}

    # migrate legacy once
    legacy = _legacy_path(user_id)
    if legacy.exists() and not data["playlists"]:
        try:
            old = json.loads(legacy.read_text(encoding="utf-8"))
            data["playlists"].append({
                "id": "legacy",
                "name": old.get("name") or "قائمتي",
                "channels": old.get("channels") or [],
            })
        except Exception:
            pass

    if playlist_id:
        found = False
        for p in data["playlists"]:
            if str(p.get("id")) == str(playlist_id):
                p["name"] = name
                p["channels"] = channels
                found = True
                break
        if not found:
            data["playlists"].append({"id": playlist_id, "name": name, "channels": channels})
    else:
        new_id = f"pl_{int(time.time())}_{user_id}"
        data["playlists"].append({"id": new_id, "name": name, "channels": channels})

    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    return str(path)


def load_user_playlist(user_id: int, playlist_id: str = None) -> Optional[Dict]:
    """Load one playlist. If playlist_id is None, return first / legacy for compatibility."""
    import json
    path = _user_playlists_path(user_id)
    if path.exists():
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            pls = data.get("playlists") or []
            if playlist_id:
                for p in pls:
                    if str(p.get("id")) == str(playlist_id):
                        return {"name": p.get("name"), "channels": filter_visible_channels(p.get("channels") or []), "id": p.get("id")}
            if pls:
                p = pls[0]
                return {"name": p.get("name"), "channels": filter_visible_channels(p.get("channels") or []), "id": p.get("id")}
        except Exception as e:
            logger.warning("load playlist: %s", e)

    # legacy single file
    legacy = _legacy_path(user_id)
    if legacy.exists():
        try:
            old = json.loads(legacy.read_text(encoding="utf-8"))
            return {"name": old.get("name") or "قائمتي", "channels": old.get("channels") or [], "id": "legacy"}
        except Exception:
            return None
    return None


def delete_user_playlist(user_id: int, playlist_id: str) -> bool:
    import json
    path = _user_playlists_path(user_id)
    if not path.exists():
        if playlist_id == "legacy":
            legacy = _legacy_path(user_id)
            if legacy.exists():
                legacy.unlink()
                return True
        return False
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        before = len(data.get("playlists") or [])
        data["playlists"] = [p for p in (data.get("playlists") or []) if str(p.get("id")) != str(playlist_id)]
        path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        return len(data["playlists"]) < before
    except Exception as e:
        logger.warning("delete playlist: %s", e)
        return False


def groups_from_channels(channels: List[Dict]) -> List[str]:
    seen = []
    for c in channels:
        g = c.get("group") or "عام"
        if g not in seen:
            seen.append(g)
    return seen


def search_channels(channels: List[Dict], query: str, limit: int = 25) -> List[Dict]:
    """بحث في اسم القناة / التصنيف / tvg_id."""
    q = (query or "").strip().lower()
    if not q or not channels:
        return []
    tokens = [t for t in q.replace("_", " ").split() if t]
    results = []
    for i, c in enumerate(filter_visible_channels(channels)):
        name = (c.get("name") or "").lower()
        group = (c.get("group") or "").lower()
        tvg = (c.get("tvg_id") or "").lower()
        blob = f"{name} {group} {tvg}"
        if all(t in blob for t in tokens):
            item = dict(c)
            item["_index"] = i
            results.append(item)
            if len(results) >= limit:
                break
    return results


# ==================== OscarTV (ostvapp.cam) ====================
OSCAR_PROXY = "https://mode.giize.com/OscarTV.php"
OSCAR_API = "https://ostvapp.cam/api/channels/show.php"
OSCAR_CACHE = IPTV_DIR / "oscar_cache.json"
OSCAR_START_ID = 1
OSCAR_END_ID = 2000
OSCAR_CONCURRENCY = 24
OSCAR_TIMEOUT = 9
OSCAR_RETRIES = 2


async def _oscar_headers(session):
    """Iron headers for OscarTV channels — local first, proxy fallback."""
    try:
        from services.iron_headers import iron_headers_for
        local = iron_headers_for(OSCAR_API)
        if local.get("x-iron-sig"):
            return local
    except Exception as e:
        logger.warning("local iron for channels: %s", e)
    import aiohttp
    async with session.post(
        OSCAR_PROXY,
        data={"link": OSCAR_API},
        timeout=aiohttp.ClientTimeout(total=20),
    ) as resp:
        resp.raise_for_status()
        data = await resp.json(content_type=None)
        if isinstance(data, dict) and "headers" in data:
            return data["headers"]
        return data


async def _oscar_fetch_one(session, channel_id, headers, semaphore):
    import asyncio
    import aiohttp
    for attempt in range(OSCAR_RETRIES + 1):
        try:
            async with semaphore:
                async with session.get(
                    OSCAR_API,
                    headers=headers,
                    params={"id": channel_id},
                    timeout=aiohttp.ClientTimeout(total=OSCAR_TIMEOUT),
                ) as resp:
                    if resp.status == 404:
                        return None
                    if resp.status in (429, 500, 502, 503, 504):
                        if attempt < OSCAR_RETRIES:
                            await asyncio.sleep(0.25 * (attempt + 1))
                            continue
                        return None
                    if resp.status >= 400:
                        return None
                    data = await resp.json(content_type=None)
                    if isinstance(data, dict) and data.get("status") == "success":
                        return data.get("data")
                    return None
        except (aiohttp.ClientError, asyncio.TimeoutError, ValueError):
            if attempt < OSCAR_RETRIES:
                await asyncio.sleep(0.25 * (attempt + 1))
                continue
            return None
        except Exception as e:
            logger.debug("Oscar channel %s fail: %s", channel_id, e)
            return None
    return None


def _oscar_to_iptv(ch):
    out = []
    name = ch.get("name") or "قناة"
    group = ch.get("category_label") or ch.get("category") or "OscarTV"
    logo = ch.get("logo") or ""
    if logo and logo.startswith("/"):
        logo = "https://ostvapp.cam" + logo
    tvg_id = str(ch.get("id") or "")
    for s in ch.get("streams") or []:
        url = (s.get("stream_url") or "").strip()
        if not url.startswith(("http://", "https://")):
            continue
        quality = s.get("quality") or ""
        server = s.get("server_name") or ""
        title = name
        if quality:
            title = f"{name} [{quality}]"
        if server:
            title = f"{title} - {server}"
        out.append({
            "name": title,
            "url": url,
            "logo": logo,
            "group": group,
            "tvg_id": tvg_id,
            "oscar_id": ch.get("id"),
            "oscar_name": name,
        })
    return out


async def fetch_oscar_channels(start_id=OSCAR_START_ID, end_id=OSCAR_END_ID, progress_cb=None):
    """Fast, resilient OscarTV importer with bounded concurrency."""
    import asyncio
    import json
    import aiohttp

    start_id = max(1, int(start_id))
    end_id = max(start_id, int(end_id))
    total = end_id - start_id + 1

    connector = aiohttp.TCPConnector(
        limit=OSCAR_CONCURRENCY,
        limit_per_host=OSCAR_CONCURRENCY,
        ttl_dns_cache=300,
        enable_cleanup_closed=True,
    )
    timeout = aiohttp.ClientTimeout(total=OSCAR_TIMEOUT + 2, connect=5, sock_read=OSCAR_TIMEOUT)
    http_headers = {
        "User-Agent": "Mozilla/5.0 (Linux; Android 12) AppleWebKit/537.36 "
                      "(KHTML, like Gecko) Chrome/120.0 Mobile Safari/537.36",
        "Accept": "application/json,text/plain,*/*",
        "Connection": "keep-alive",
    }

    channels = []
    checked = 0
    found = 0
    last_progress = 0.0

    async with aiohttp.ClientSession(
        connector=connector, timeout=timeout, headers=http_headers
    ) as session:
        headers = await _oscar_headers(session)
        semaphore = asyncio.Semaphore(OSCAR_CONCURRENCY)

        async def one(cid):
            return cid, await _oscar_fetch_one(session, cid, headers, semaphore)

        tasks = [asyncio.create_task(one(cid)) for cid in range(start_id, end_id + 1)]
        try:
            for fut in asyncio.as_completed(tasks):
                cid, raw = await fut
                checked += 1
                if raw:
                    items = _oscar_to_iptv(raw)
                    if items:
                        channels.extend(items)
                        found += len(items)

                now = asyncio.get_running_loop().time()
                if progress_cb and (now - last_progress >= 2.0 or checked == total):
                    last_progress = now
                    try:
                        await progress_cb(checked, total, found)
                    except Exception:
                        pass
        finally:
            for task in tasks:
                if not task.done():
                    task.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)

    # De-duplicate by stream URL while preserving order.
    unique, seen = [], set()
    for item in channels:
        url = item.get("url")
        if url and url not in seen:
            seen.add(url)
            unique.append(item)
    channels = unique

    try:
        OSCAR_CACHE.write_text(
            json.dumps(
                {"channels": channels, "count": len(channels),
                 "start_id": start_id, "end_id": end_id},
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
    except Exception as e:
        logger.warning("Oscar cache save failed: %s", e)
    return channels


def load_oscar_cache():
    import json
    if not OSCAR_CACHE.exists():
        return []
    try:
        data = json.loads(OSCAR_CACHE.read_text(encoding="utf-8"))
        return data.get("channels") or []
    except Exception:
        return []
