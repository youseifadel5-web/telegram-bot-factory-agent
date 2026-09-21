"""Streaming Engine states — the SINGLE source of truth for stream state.

State machine (allowed transitions):

    CREATED → PROBING → READY → STARTING → RUNNING
    RUNNING → RECONNECTING → RUNNING (recovered)
    RUNNING → STOPPING → STOPPED
    RECONNECTING → FAILED (retries exhausted)
    STARTING → FAILED
    any live state → STOPPING → STOPPED
    STOPPED → STARTING (only via the full Start flow)

Nothing else may mutate a stream's state.
"""
from __future__ import annotations
import logging
import os
import time
from typing import Dict, Any, Optional

logger = logging.getLogger("stream")

# Canonical states (lowercase strings — stored in DB `status` too)
CREATED = "created"
PROBING = "probing"
READY = "ready"
STARTING = "starting"
CONNECTING = "connecting"      # FFmpeg spawning, no confirmed flow yet
ON_AIR = "on_air"              # real confirmed data flow (display alias of RUNNING)
RUNNING = "running"
DEGRADED = "degraded"
STALLED = "stalled"
RECONNECTING = "reconnecting"
RESTARTING = "restarting"
STOPPING = "stopping"
FAILED = "failed"
ERROR = "error"                # legacy alias of FAILED
STOPPED = "stopped"

VALID = {
    CREATED, PROBING, READY, STARTING, CONNECTING, ON_AIR, RUNNING, DEGRADED,
    STALLED, RECONNECTING, RESTARTING, STOPPING, FAILED, ERROR, STOPPED,
}

# Smart restart delays (seconds) by attempt index (0-based) — .env configurable
RESTART_DELAYS = [5, 30, 300]  # 5s, 30s, 5min
try:
    MAX_RESTARTS = max(1, int(os.getenv("MAX_RESTARTS", "") or 3))
except Exception:
    MAX_RESTARTS = 3

_ALLOWED_TRANSITIONS: Dict[str, set] = {
    CREATED: {PROBING, READY, STARTING, STOPPING, STOPPED, FAILED},
    PROBING: {READY, FAILED, STOPPING, STOPPED},
    READY: {STARTING, STOPPING, STOPPED},
    STARTING: {CONNECTING, RUNNING, ON_AIR, FAILED, STOPPING, STOPPED, RECONNECTING},
    CONNECTING: {RUNNING, ON_AIR, RECONNECTING, STALLED, FAILED, STOPPING, STOPPED},
    RUNNING: {ON_AIR, RECONNECTING, RESTARTING, STALLED, STOPPING, STOPPED, FAILED},
    ON_AIR: {RUNNING, RECONNECTING, RESTARTING, STALLED, STOPPING, STOPPED, FAILED},
    DEGRADED: {RUNNING, ON_AIR, RECONNECTING, STOPPING, STOPPED, FAILED},
    STALLED: {RUNNING, ON_AIR, RECONNECTING, RESTARTING, STOPPING, STOPPED, FAILED},
    RECONNECTING: {CONNECTING, RUNNING, ON_AIR, RESTARTING, FAILED, STOPPING, STOPPED},
    RESTARTING: {CONNECTING, RUNNING, ON_AIR, FAILED, STOPPING, STOPPED},
    STOPPING: {STOPPED, FAILED},
    FAILED: {STOPPED, STARTING},   # FAILED → RUNNING requires the full start flow
    ERROR: {STOPPED, STARTING},
    STOPPED: {STARTING},           # STOPPED → RUNNING only via full Start flow
}


def can_transition(old: str, new: str) -> bool:
    old = (old or "").lower()
    new = (new or "").lower()
    if old == new:
        return True
    if new not in VALID or old not in VALID:
        return False
    return new in _ALLOWED_TRANSITIONS.get(old, set())


def transition(stream_id: int, old: str, new: str) -> str:
    """Guarded transition — returns the new state if allowed, else old."""
    if can_transition(old, new):
        return new
    logger.warning("stream %s: illegal transition %s → %s (keeping %s)", stream_id, old, new, old)
    return old


def next_restart_delay(attempt: int) -> Optional[float]:
    """Return delay seconds before next restart, or None if exhausted."""
    if attempt >= MAX_RESTARTS:
        return None
    if attempt < len(RESTART_DELAYS):
        return float(RESTART_DELAYS[attempt])
    return float(RESTART_DELAYS[-1])


def map_legacy_status(status: str) -> str:
    s = (status or "").lower()
    if s in VALID:
        return s
    if s in ("on_air", "healthy"):
        return RUNNING
    if s in ("connecting",):
        return STARTING
    if s in ("reconnecting",):
        return RESTARTING
    if s in ("error",):
        return FAILED
    if s in ("stopped", "stop"):
        return STOPPED
    return STOPPED


class RestartTracker:
    """Per-stream restart bookkeeping."""

    def __init__(self):
        self._data: Dict[int, Dict[str, Any]] = {}

    def record_fail(self, stream_id: int, reason: str = ""):
        d = self._data.setdefault(stream_id, {"attempts": 0, "reasons": [], "last": 0})
        d["attempts"] = d.get("attempts", 0) + 1
        d["reasons"].append(reason)
        d["last"] = time.time()
        logger.warning("stream %s fail #%s: %s", stream_id, d["attempts"], reason)

    def can_restart(self, stream_id: int) -> bool:
        d = self._data.get(stream_id) or {}
        return d.get("attempts", 0) < MAX_RESTARTS

    def delay_for(self, stream_id: int) -> Optional[float]:
        d = self._data.get(stream_id) or {}
        return next_restart_delay(d.get("attempts", 0))

    def reset(self, stream_id: int):
        self._data.pop(stream_id, None)

    def info(self, stream_id: int) -> Dict[str, Any]:
        return dict(self._data.get(stream_id) or {"attempts": 0, "reasons": []})


restart_tracker = RestartTracker()
