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
