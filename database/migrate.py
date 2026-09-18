"""Simple SQL migration runner."""
from __future__ import annotations
import logging
from pathlib import Path

logger = logging.getLogger(__name__)
MIGRATIONS_DIR = Path(__file__).resolve().parent / "migrations"


async def run_migrations(conn):
    await conn.execute(
        "CREATE TABLE IF NOT EXISTS schema_migrations (id TEXT PRIMARY KEY, applied_at TEXT)"
    )
    await conn.commit()
    cur = await conn.execute("SELECT id FROM schema_migrations")
    applied = {r[0] for r in await cur.fetchall()}

    files = sorted(MIGRATIONS_DIR.glob("*.sql"))
    for f in files:
        mid = f.stem  # e.g. 001_users
        if mid in applied:
            continue
        sql = f.read_text(encoding="utf-8")
        try:
            await conn.executescript(sql)
            from datetime import datetime
            await conn.execute(
                "INSERT INTO schema_migrations (id, applied_at) VALUES (?, ?)",
                (mid, datetime.utcnow().isoformat()),
            )
            await conn.commit()
            logger.info("Migration applied: %s", mid)
        except Exception as e:
            logger.error("Migration %s failed: %s", mid, e)
            raise
