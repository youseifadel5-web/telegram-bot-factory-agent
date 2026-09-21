"""Stream-related keyboards.

Telegram limits observed:
  - InlineKeyboardButton text: max 64 characters
  - callback_data: max 64 bytes

All control paths must use stream_actions_keyboard (rich V6 panel).
stream_control_keyboard is a thin compatibility wrapper only.
"""
from __future__ import annotations

from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from typing import List, Dict, Optional


def _short_title(title: Optional[str], max_len: int = 18) -> str:
    t = (title or "بث").strip()
    if len(t) <= max_len:
        return t
    return t[: max_len - 1] + "…"


def _state_icon_and_label(status: str, running: bool = False, healthy: bool = False, state: str = "") -> tuple:
    """Return (emoji, short_label) for list buttons. Labels stay short for TG 64-char limit."""
    st = (state or status or "stopped").lower()
    if healthy or (st in ("on_air", "running") and running):
        return "🟢", "ON AIR"
    if st in ("reconnecting", "restarting", "connecting", "starting"):
        return "🟡", "اتصال"
    if st == "stalled":
        return "🟠", "متوقف مؤقتاً"
    if running:
        return "🟡", "يعمل"
    if st in ("failed", "error"):
        return "🔴", "فشل"
    return "🔴", "متوقف"


def stream_list_button_text(
    stream_id: int,
    title: Optional[str],
    *,
    status: str = "stopped",
    running: bool = False,
    healthy: bool = False,
    state: str = "",
    uptime: str = "—",
) -> str:
    """Build a TG-safe button label: 🟢 #12 Title · 01:24:38 (≤64 chars)."""
    icon, label = _state_icon_and_label(status, running=running, healthy=healthy, state=state)
    up = (uptime or "—").strip()
    if up and up not in ("—", "00:00:00"):
        suffix = f" · {up}"
    else:
        suffix = f" · {label}"
    id_part = f"#{int(stream_id)}"
    budget = 60 - len(id_part) - len(suffix) - 2
    title_part = _short_title(title, max(8, budget))
    text = f"{icon} {id_part} {title_part}{suffix}"
    return text[:64]


def stream_create_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🔗 رابط مباشر / HLS", callback_data="stream_source_direct")],
        [InlineKeyboardButton("📁 من ملفاتي", callback_data="stream_source_files")],
        [InlineKeyboardButton("🔙 رجوع", callback_data="main_menu")],
    ])


def current_streams_keyboard(streams: List[Dict], live_meta: Optional[Dict[int, dict]] = None) -> InlineKeyboardMarkup:
    """List of current streams with #id + state + uptime on each button.

    live_meta optional map: stream_id -> {running, healthy, state, uptime}
    so callers can inject StreamManager truth without importing it here.
    """
    live_meta = live_meta or {}
    buttons = []
    for s in streams:
        try:
            sid = int(s.get("id") or 0)
        except (TypeError, ValueError):
            continue
        if not sid:
            continue
        meta = live_meta.get(sid) or {}
        running = bool(meta.get("running"))
        healthy = bool(meta.get("healthy"))
        state = str(meta.get("state") or s.get("status") or "stopped")
        uptime = str(meta.get("uptime") or "—")
        status = str(s.get("status") or state)
        text = stream_list_button_text(
            sid,
            s.get("title"),
            status=status,
            running=running,
            healthy=healthy,
            state=state,
            uptime=uptime,
        )
        buttons.append([
            InlineKeyboardButton(text, callback_data=f"stream_status:{sid}")
        ])
    if not buttons:
        buttons.append([InlineKeyboardButton("لا يوجد بث نشط", callback_data="noop")])
    buttons.append([
        InlineKeyboardButton("🚀 إنشاء بث جديد", callback_data="stream_new"),
        InlineKeyboardButton("🔙 رجوع", callback_data="main_menu"),
    ])
    return InlineKeyboardMarkup(buttons)


def stream_control_keyboard(stream_id: int, is_running: bool, can_control: bool = True) -> InlineKeyboardMarkup:
    """Compatibility wrapper — always use the rich stream_actions_keyboard.

    Do not maintain a second control panel; Telegram UI must stay unified.
    """
    from keyboards.menus import stream_actions_keyboard
    return stream_actions_keyboard(stream_id, is_running, can_control=can_control)


def rtmp_input_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🔙 إلغاء", callback_data="stream_new")]
    ])
