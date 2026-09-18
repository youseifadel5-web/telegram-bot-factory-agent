"""
Stream handlers package (refactored).

Public API stays the same so main.py imports continue to work.
"""
from .common import (
    WAITING_TITLE,
    WAITING_SOURCE,
    WAITING_OFFSET,
    WAITING_RTMP_URL,
    WAITING_STREAM_KEY,
    cancel_conversation,
    cancel_all_status_tasks,
)

from .create import (
    stream_new_callback,
    receive_title,
    receive_source,
    receive_offset,
    stream_new_from_text,
    stream_from_url_callback,
    handle_stream_rtmp_text,
    handle_stream_key_text,
)

from .finalize import finalize_stream
# Back-compat alias used by drive.py and older call sites
_finalize_stream = finalize_stream

from .rtmp_setup import (
    start_rtmp_setup_flags,
    receive_rtmp_url,
    receive_stream_key,
    rtmp_use_saved_callback,
    rtmp_change_callback,
    rtmp_skip_callback,
)

from .probe_flow import (
    probe_continue_callback,
    probe_retry_callback,
)

from .status import (
    current_stream_callback,
    stream_status_callback,
)

from .control import (
    stream_start_callback,
    stream_stop_callback,
    stream_delete_callback,
    stream_restart_callback,
    stream_vol_up_callback,
    stream_vol_down_callback,
    stream_mute_callback,
    stream_br_callback,
)

from .playlist import (
    pl_view_callback,
    pl_next_callback,
    pl_prev_callback,
    pl_shuffle_callback,
    pl_loop_callback,
)

from .stations import (
    stations_menu_callback,
    stations_command,
    station_start_callback,
    station_rtmp_callback,
    station_rtmp_receive,
    station_rtmp_key_receive,
    stream_history_callback,
    stream_fav_callback,
)

__all__ = [
    "WAITING_TITLE", "WAITING_SOURCE", "WAITING_OFFSET", "WAITING_RTMP_URL", "WAITING_STREAM_KEY",
    "stream_new_callback", "stream_from_url_callback",
    "receive_title", "receive_source", "receive_offset", "receive_rtmp_url", "receive_stream_key",
    "cancel_conversation", "current_stream_callback", "stream_status_callback",
    "stream_start_callback", "stream_stop_callback", "stream_delete_callback",
    "stream_restart_callback", "stream_vol_up_callback", "stream_vol_down_callback",
    "stream_mute_callback", "stream_br_callback",
    "pl_view_callback", "pl_next_callback", "pl_prev_callback", "pl_shuffle_callback", "pl_loop_callback",
    "stations_menu_callback", "stations_command", "station_start_callback", "station_rtmp_callback",
    "station_rtmp_receive", "station_rtmp_key_receive",
    "start_rtmp_setup_flags", "handle_stream_rtmp_text", "handle_stream_key_text",
    "rtmp_use_saved_callback", "rtmp_change_callback", "rtmp_skip_callback",
    "probe_continue_callback", "probe_retry_callback", "cancel_all_status_tasks",
    "stream_history_callback", "stream_fav_callback",
    "stream_new_from_text",
    "finalize_stream", "_finalize_stream",
]
