import logging
import math
from datetime import datetime
from typing import Optional

logger = logging.getLogger(__name__)


def format_size(size_bytes: int) -> str:
    """Convert bytes to human readable size."""
    if size_bytes is None or size_bytes < 0:
        return "0 B"
    units = ["B", "KB", "MB", "GB", "TB"]
    if size_bytes == 0:
        return "0 B"
    i = int(math.floor(math.log(size_bytes, 1024)))
    i = min(i, len(units) - 1)
    p = math.pow(1024, i)
    s = round(size_bytes / p, 2)
    return f"{s} {units[i]}"


def format_duration(seconds: float) -> str:
    """Format seconds to HH:MM:SS."""
    if seconds is None or seconds < 0:
        return "00:00:00"
    seconds = int(seconds)
    h = seconds // 3600
    m = (seconds % 3600) // 60
    s = seconds % 60
    return f"{h:02d}:{m:02d}:{s:02d}"


def parse_iso(iso_str: Optional[str]) -> Optional[datetime]:
    if not iso_str:
        return None
    try:
        return datetime.fromisoformat(iso_str)
    except Exception:
        return None


def stream_uptime(started_at: Optional[str]) -> str:
    """Calculate uptime from started_at ISO string."""
    start = parse_iso(started_at)
    if not start:
        return "00:00:00"
    delta = datetime.utcnow() - start
    return format_duration(delta.total_seconds())


_EXTRA_ADMIN_IDS = set()

def register_admin(user_id: int, enabled: bool = True):
    try:
        uid = int(user_id)
        if enabled:
            _EXTRA_ADMIN_IDS.add(uid)
        else:
            _EXTRA_ADMIN_IDS.discard(uid)
    except Exception:
        pass

def is_admin(user_id: int, admin_id: int) -> bool:
    try:
        return int(user_id) == int(admin_id) or int(user_id) in _EXTRA_ADMIN_IDS
    except Exception:
        return False


def safe_filename(name: str) -> str:
    """Sanitize filename for storage."""
    import re
    name = re.sub(r'[^\w\s\-_.\u0600-\u06FF]', '_', name)
    return name.strip()[:200] or "file"


def paginate(items: list, page: int, per_page: int = 8):
    """Return (page_items, total_pages, current_page)."""
    total = len(items)
    total_pages = max(1, math.ceil(total / per_page))
    page = max(1, min(page, total_pages))
    start = (page - 1) * per_page
    end = start + per_page
    return items[start:end], total_pages, page


# Temporary interaction state only. Persistent preferences, pagination caches,
# and the assistant conversation must survive menu navigation and /start.
WORKFLOW_STATE_KEYS = {
    "await_help_q", "await_archive_search", "await_archive_url", "await_iptv_url",
    "await_iptv_search", "await_extract_url", "await_test_url", "await_broadcast",
    "await_stream_rtmp", "await_stream_key", "await_movie_search", "await_series_search",
    "await_cinema_search", "await_station_rtmp", "await_station_key", "await_probe_continue",
    "stream_title", "stream_source", "start_offset", "rtmp_base", "stream_key",
    "pending_stream_url", "pending_stream_title", "pending_stream_headers", "probe_result",
    "media_kind", "_probe_has_video", "_probe_has_audio", "drive_file_id", "drive_info",
    "extracted_streams", "station_manual_rtmp", "station_rtmp_base", "admin_manage_action",
}


def clear_workflow_state(user_data, *, keep: set[str] | None = None):
    """Remove only transient workflow fields; never wipe user preferences/results."""
    if not user_data:
        return
    protected = keep or set()
    for key in list(user_data.keys()):
        if key in WORKFLOW_STATE_KEYS or str(key).startswith("await_"):
            if key not in protected:
                user_data.pop(key, None)


def has_active_workflow(user_data) -> bool:
    """Return whether free text belongs to an in-progress bot workflow."""
    if not user_data:
        return False
    return any(str(key).startswith("await_") for key in user_data.keys())


async def safe_edit_message(query_or_msg, text, *, parse_mode="HTML", reply_markup=None, disable_web_page_preview=True):
    """Edit text or caption safely. Falls back to send_message on media/no-text errors.

    Accepts either a CallbackQuery or a Message.
    """
    msg = getattr(query_or_msg, "message", None) or query_or_msg
    if msg is None:
        return None
    chat = getattr(msg, "chat", None)
    try:
        if getattr(msg, "photo", None) or getattr(msg, "video", None) or getattr(msg, "document", None):
            caption = str(text or "")
            if len(caption) <= 1024:
                try:
                    if hasattr(query_or_msg, "edit_message_caption"):
                        return await query_or_msg.edit_message_caption(
                            caption=caption, parse_mode=parse_mode, reply_markup=reply_markup
                        )
                    return await msg.edit_caption(
                        caption=caption, parse_mode=parse_mode, reply_markup=reply_markup
                    )
                except Exception:
                    pass
            try:
                await msg.delete()
            except Exception:
                pass
            if chat:
                return await chat.send_message(
                    caption, parse_mode=parse_mode, reply_markup=reply_markup,
                    disable_web_page_preview=disable_web_page_preview,
                )
            return None
        if hasattr(query_or_msg, "edit_message_text"):
            return await query_or_msg.edit_message_text(
                text, parse_mode=parse_mode, reply_markup=reply_markup,
                disable_web_page_preview=disable_web_page_preview,
            )
        return await msg.edit_text(
            text, parse_mode=parse_mode, reply_markup=reply_markup,
            disable_web_page_preview=disable_web_page_preview,
        )
    except Exception as exc:
        logger.warning("safe_edit_message failed: %s", exc)
        try:
            if chat:
                return await chat.send_message(
                    text, parse_mode=parse_mode, reply_markup=reply_markup,
                    disable_web_page_preview=disable_web_page_preview,
                )
        except Exception:
            logger.exception("safe_edit fallback send failed")
        return None
