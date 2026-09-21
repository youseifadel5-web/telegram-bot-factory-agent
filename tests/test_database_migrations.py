"""Tests for database migrations: idempotent, backward compatible, no data loss."""
import asyncio
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from database import Database


def run(coro):
    return asyncio.run(coro)


def test_new_columns_exist_and_idempotent():
    async def run_inner():
        with tempfile.TemporaryDirectory() as td:
            path = os.path.join(td, "t.db")
            d1 = Database(path)
            await d1.connect()
            cur = await d1.conn.execute("PRAGMA table_info(streams)")
            cols = {r[1] for r in await cur.fetchall()}
            for c in ("quality", "media_mode", "source_mode", "restart_count", "reconnect_count"):
                assert c in cols, f"missing column {c}"
            # legacy row: fields read with safe defaults (backward compat)
            sid = await d1.create_stream(1, "قناة قرآن", "https://x/a.m3u8", "rtmp://y/z")
            s = await d1.get_stream(sid)
            assert (s.get("quality") or "auto") == "auto"
            assert (s.get("media_mode") or "auto") == "auto"
            await d1.update_stream_meta(sid, quality="720p", media_mode="video", source_mode="auto")
            s2 = await d1.get_stream(sid)
            assert s2["quality"] == "720p" and s2["media_mode"] == "video"
            # stream logs work
            await d1.add_stream_log(sid, 1, "started", "test")
            logs = await d1.get_stream_logs(sid)
            assert logs and logs[0]["event"] == "started"
            # favorites dedup
            f1 = await d1.add_favorite(1, "stream", "t", "https://x", meta=str(sid))
            f2 = await d1.add_favorite(1, "stream", "t", "https://x", meta=str(sid))
            assert f1 == f2
            await d1.close()
            # SECOND connect on the same file → idempotent, no crash, no data loss
            d2 = Database(path)
            await d2.connect()
            cur = await d2.conn.execute("PRAGMA table_info(streams)")
            cols2 = {r[1] for r in await cur.fetchall()}
            assert cols == cols2
            streams = await d2.get_user_streams(1)
            assert len(streams) == 1  # old data intact
            await d2.close()
    run(run_inner())


def test_update_stream_status_restart_count():
    async def run_inner():
        with tempfile.TemporaryDirectory() as td:
            d = Database(os.path.join(td, "t.db"))
            await d.connect()
            sid = await d.create_stream(1, "s", "https://x/a.mp3")
            await d.update_stream_status(sid, "running", pid=4321, restart_count=2)
            s = await d.get_stream(sid)
            assert s["restart_count"] == 2 and s["pid"] == 4321
            await d.update_stream_status(sid, "stopped", restart_count=2)
            s2 = await d.get_stream(sid)
            assert s2["status"] == "stopped" and s2["restart_count"] == 2
            await d.close()
    run(run_inner())


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            print("OK", name)
    print("all database migration tests passed")
