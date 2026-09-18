"""Broadcast scheduler — start/stop streams at set times (daily/weekly)."""
import asyncio
import logging
from datetime import datetime, time as dtime
from typing import Optional

logger = logging.getLogger(__name__)

_task: Optional[asyncio.Task] = None
_running = False


def _parse_hhmm(s: str) -> Optional[dtime]:
    try:
        parts = (s or "").strip().split(":")
        h, m = int(parts[0]), int(parts[1]) if len(parts) > 1 else 0
        return dtime(h % 24, m % 60)
    except Exception:
        return None


def _should_be_on(start: dtime, end: dtime, now: dtime) -> bool:
    """Support overnight ranges (22:00 → 06:00)."""
    if start <= end:
        return start <= now < end
    # overnight
    return now >= start or now < end


def _day_matches(days: str, now: datetime) -> bool:
    d = (days or "daily").lower().strip()
    if d in ("daily", "كل يوم", "*"):
        return True
    # weekly: mon,tue,... or 0-6
    weekday = now.weekday()  # mon=0
    names = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]
    ar = ["اثنين", "ثلاثاء", "اربعاء", "خميس", "جمعة", "سبت", "احد"]
    tokens = [t.strip() for t in d.replace("،", ",").split(",") if t.strip()]
    for t in tokens:
        tl = t.lower()
        if tl.isdigit() and int(tl) == weekday:
            return True
        if tl in names and names.index(tl) == weekday:
            return True
        if t in ar and ar.index(t) == weekday:
            return True
    return False


async def _tick():
    """Check schedules every 30s."""
    from database import db
    from services.stream import stream_manager

    while _running:
        try:
            schedules = await db.get_enabled_schedules()
            now = datetime.utcnow()
            now_t = now.time().replace(second=0, microsecond=0)
            for sch in schedules:
                try:
                    if not _day_matches(sch.get("days") or "daily", now):
                        continue
                    st = _parse_hhmm(sch.get("start_time") or "")
                    et = _parse_hhmm(sch.get("end_time") or "")
                    if not st or not et:
                        continue
                    should_on = _should_be_on(st, et, now_t)
                    sid = sch.get("stream_id")
                    is_on = bool(sid and stream_manager.is_running(sid))

                    if should_on and not is_on:
                        if not sch.get("rtmp_url") or not sch.get("source_url"):
                            continue
                        if not stream_manager.has_ffmpeg():
                            continue
                        # create stream record if needed
                        if not sid:
                            sid = await db.create_stream(
                                sch["user_id"],
                                sch.get("name") or "مجدول",
                                sch["source_url"],
                                sch["rtmp_url"],
                            )
                            await db.update_schedule(sch["id"], stream_id=sid)
                        pid = stream_manager.start_stream(sid, sch["source_url"], sch["rtmp_url"])
                        if pid:
                            await db.update_stream_status(sid, "running", pid)
                            await db.update_schedule(sch["id"], last_run=now.isoformat())
                            await db.add_audit(sch["user_id"], "schedule_start", str(sid), sch.get("name") or "")
                            logger.info("Scheduler started stream %s (%s)", sid, sch.get("name"))

                    elif not should_on and is_on and sid:
                        stream_manager.stop_stream(sid)
                        await db.update_stream_status(sid, "stopped")
                        await db.add_audit(sch["user_id"], "schedule_stop", str(sid), sch.get("name") or "")
                        logger.info("Scheduler stopped stream %s", sid)
                except Exception as e:
                    logger.warning("schedule tick item: %s", e)
        except Exception as e:
            logger.warning("scheduler tick: %s", e)
        await asyncio.sleep(30)


def start_scheduler(loop=None):
    global _task, _running
    if _running:
        return
    _running = True
    try:
        _task = asyncio.get_event_loop().create_task(_tick())
    except RuntimeError:
        if loop:
            _task = loop.create_task(_tick())
    logger.info("Broadcast scheduler started")


def stop_scheduler():
    global _task, _running
    _running = False
    if _task and not _task.done():
        _task.cancel()
    _task = None
    logger.info("Broadcast scheduler stopped")
