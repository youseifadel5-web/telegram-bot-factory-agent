"""Tests for the stream state machine (core/stream_states.py)."""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from core.stream_states import (
    can_transition, next_restart_delay, map_legacy_status,
    CREATED, PROBING, READY, STARTING, RUNNING, ON_AIR, CONNECTING,
    RECONNECTING, RESTARTING, STOPPING, STOPPED, FAILED, STALLED, ERROR,
)


def test_happy_path_transitions():
    assert can_transition(CREATED, PROBING)
    assert can_transition(PROBING, READY)
    assert can_transition(READY, STARTING)
    assert can_transition(STARTING, CONNECTING)
    assert can_transition(CONNECTING, RUNNING)
    assert can_transition(RUNNING, ON_AIR)


def test_recovery_and_stop_paths():
    assert can_transition(RUNNING, RECONNECTING)
    assert can_transition(RECONNECTING, CONNECTING)
    assert can_transition(RECONNECTING, FAILED)
    assert can_transition(RUNNING, STOPPING)
    assert can_transition(STOPPING, STOPPED)


def test_illegal_shortcuts_blocked():
    assert not can_transition(STOPPED, RUNNING)      # must go through STARTING
    assert not can_transition(FAILED, RUNNING)       # needs full re-init
    assert not can_transition(STOPPED, ON_AIR)
    assert not can_transition(CREATED, ON_AIR)


def test_stopped_can_only_start():
    assert can_transition(STOPPED, STARTING)
    assert not can_transition(STOPPED, STOPPING)


def test_restart_backoff_and_exhaustion():
    assert next_restart_delay(0) == 5.0
    assert next_restart_delay(1) == 30.0
    assert next_restart_delay(2) == 300.0
    assert next_restart_delay(3) is None  # exhausted → FAILED


def test_legacy_status_mapping():
    # on_air / connecting / reconnecting are canonical states now — identity mapping
    assert map_legacy_status("on_air") == ON_AIR
    assert map_legacy_status("connecting") == CONNECTING
    assert map_legacy_status("reconnecting") == RECONNECTING
    assert map_legacy_status("error") == ERROR  # canonical alias kept as-is
    assert map_legacy_status("stopped") == STOPPED
    assert map_legacy_status("garbage") == STOPPED


def test_stalled_is_valid_state():
    assert can_transition(RUNNING, STALLED)
    assert can_transition(STALLED, RECONNECTING)
    assert can_transition(STALLED, RUNNING)


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            print("OK", name)
    print("all stream_state tests passed")
