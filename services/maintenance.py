"""Smart Maintenance Mode — protect the bot under resource pressure."""
import logging
import time
from typing import Optional, Dict, Any

logger = logging.getLogger(__name__)

_state = {
    "active": False,
    "reason": "",
    "since": 0.0,
    "block_new_streams": False,
}


def is_maintenance() -> bool:
    return bool(_state["active"])


def blocks_new_streams() -> bool:
    return bool(_state["active"] and _state["block_new_streams"])


def get_status() -> Dict[str, Any]:
    return dict(_state)


def activate(reason: str, block_new: bool = True):
    _state["active"] = True
    _state["reason"] = reason
    _state["since"] = time.time()
    _state["block_new_streams"] = block_new
    logger.warning("MAINTENANCE ON: %s", reason)


def deactivate():
    _state["active"] = False
    _state["reason"] = ""
    _state["block_new_streams"] = False
    logger.info("MAINTENANCE OFF")


def check_resources() -> Optional[str]:
    """Return reason string if resources are critical, else None."""
    try:
        from services.system_monitor import cpu_percent, ram_info, disk_info
        cpu = cpu_percent()
        ru, rt = ram_info()
        du, dt = disk_info()
        ram_pct = (ru / rt * 100) if rt else 0
        disk_pct = (du / dt * 100) if dt else 0
        if cpu >= 95:
            return f"CPU مرتفع جداً ({cpu:.0f}%)"
        if ram_pct >= 92:
            return f"الذاكرة ممتلئة ({ram_pct:.0f}%)"
        if disk_pct >= 95:
            return f"التخزين ممتلئ ({disk_pct:.0f}%)"
    except Exception as e:
        logger.debug("resource check: %s", e)
    return None


def auto_evaluate():
    """Call periodically — enter/exit maintenance based on resources."""
    reason = check_resources()
    if reason and not _state["active"]:
        activate(reason, block_new=True)
        return True
    if not reason and _state["active"] and _state["reason"].startswith(("CPU", "الذاكرة", "التخزين")):
        # only auto-clear resource-based maintenance
        deactivate()
        return False
    return _state["active"]
