"""Playlist manager — next/prev/shuffle/loop for streams."""
import logging
import random
from typing import Optional, Dict, List, Any

from database import db

logger = logging.getLogger(__name__)


async def ensure_playlist_for_stream(user_id: int, stream_id: int, title: str = None, source_url: str = None) -> int:
    """Get or create a playlist linked to a stream. Optionally seed first item."""
    pl = await db.get_playlist_for_stream(stream_id)
    if pl:
        return pl["id"]
    pid = await db.create_playlist(user_id, name=title or "قائمة التشغيل", stream_id=stream_id)
    if source_url:
        await db.add_playlist_item(pid, title or "عنصر 1", source_url, position=0)
    return pid


async def format_playlist_text(playlist_id: int) -> str:
    pl = await db.get_playlist(playlist_id)
    if not pl:
        return "📃 قائمة التشغيل فارغة."
    items = await db.get_playlist_items(playlist_id)
    if not items:
        return f"📃 *{pl.get('name') or 'قائمة التشغيل'}*\n\nلا توجد عناصر."
    idx = pl.get("current_index") or 0
    shuffle = "🔀" if pl.get("shuffle") else ""
    loop = {"none": "", "one": "🔁×1", "all": "🔁"}.get(pl.get("loop_mode") or "none", "")
    lines = [f"📃 *{pl.get('name') or 'قائمة التشغيل'}* {shuffle} {loop}\n"]
    for i, it in enumerate(items):
        mark = "▶️" if i == idx else f"{i + 1}."
        lines.append(f"{mark} {it.get('title') or 'بدون عنوان'}")
    return "\n".join(lines)


async def get_current_item(playlist_id: int) -> Optional[Dict]:
    pl = await db.get_playlist(playlist_id)
    if not pl:
        return None
    items = await db.get_playlist_items(playlist_id)
    if not items:
        return None
    idx = max(0, min(pl.get("current_index") or 0, len(items) - 1))
    return items[idx]


async def next_item(playlist_id: int) -> Optional[Dict]:
    pl = await db.get_playlist(playlist_id)
    if not pl:
        return None
    items = await db.get_playlist_items(playlist_id)
    if not items:
        return None
    n = len(items)
    idx = pl.get("current_index") or 0
    shuffle = bool(pl.get("shuffle"))
    loop = pl.get("loop_mode") or "none"

    if shuffle:
        new_idx = random.randrange(n)
        if n > 1 and new_idx == idx:
            new_idx = (idx + 1) % n
    else:
        new_idx = idx + 1
        if new_idx >= n:
            if loop == "all":
                new_idx = 0
            else:
                return None  # end of list
    await db.update_playlist(playlist_id, current_index=new_idx)
    return items[new_idx]


async def prev_item(playlist_id: int) -> Optional[Dict]:
    pl = await db.get_playlist(playlist_id)
    if not pl:
        return None
    items = await db.get_playlist_items(playlist_id)
    if not items:
        return None
    n = len(items)
    idx = pl.get("current_index") or 0
    new_idx = (idx - 1) % n if n else 0
    await db.update_playlist(playlist_id, current_index=new_idx)
    return items[new_idx]


async def toggle_shuffle(playlist_id: int) -> bool:
    pl = await db.get_playlist(playlist_id)
    if not pl:
        return False
    new_val = 0 if pl.get("shuffle") else 1
    await db.update_playlist(playlist_id, shuffle=new_val)
    return bool(new_val)


async def cycle_loop(playlist_id: int) -> str:
    pl = await db.get_playlist(playlist_id)
    if not pl:
        return "none"
    order = ["none", "all", "one"]
    cur = pl.get("loop_mode") or "none"
    try:
        i = order.index(cur)
    except ValueError:
        i = 0
    new = order[(i + 1) % len(order)]
    await db.update_playlist(playlist_id, loop_mode=new)
    return new


async def add_to_stream_playlist(user_id: int, stream_id: int, title: str, source_url: str) -> int:
    pid = await ensure_playlist_for_stream(user_id, stream_id, title, None)
    return await db.add_playlist_item(pid, title, source_url)
