"""Streaming Engine states and smart restart policy."""
from __future__ import annotations
import logging
import time
from typing import Dict, Any, Optional

logger = logging.getLogger("stream")

# Canonical states
CREATED = "created"
STARTING = "starting"
RUNNING = "running"
DEGRADED = "degraded"
RESTARTING = "restarting"
STOPPING = "stopping"
FAILED = "failed"
STOPPED = "stopped"

VALID = {CREATED, STARTING, RUNNING, DEGRADED, RESTARTING, STOPPING, FAILED, STOPPED}

# Smart restart delays (seconds) by attempt index (0-based)
RESTART_DELAYS = [5, 30, 300]  # 5s, 30s, 5min
MAX_RESTARTS = 3


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
