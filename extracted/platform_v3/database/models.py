# -*- coding: utf-8 -*-
"""SQLite schema with indexes for media, blocks, favorites, audit."""
from __future__ import annotations

import sqlite3
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

DB_PATH = Path(__file__).resolve().parent.parent / "platform.db"


class Database:
    def __init__(self, path: Optional[str] = None):
        self.path = str(path or DB_PATH)
        self._init()

    def _conn(self) -> sqlite3.Connection:
        c = sqlite3.connect(self.path, check_same_thread=False)
        c.row_factory = sqlite3.Row
        return c

    def _init(self):
        try:
            self._create_schema()
        except Exception:
            # sandbox / read-only fallback
            import tempfile, os
            self.path = os.path.join(tempfile.gettempdir(), "platform_fallback.db")
            self._create_schema()

    def _create_schema(self):
        with self._conn() as c:
            c.executescript(
                """
                CREATE TABLE IF NOT EXISTS media (
                    id TEXT PRIMARY KEY,
                    universal_id TEXT,
                    title TEXT,
                    normalized_title TEXT,
                    original_title TEXT,
                    type TEXT,
                    year INTEGER,
                    countries TEXT,
                    genres TEXT,
                    overview TEXT,
                    poster TEXT,
                    rating REAL,
                    visibility TEXT DEFAULT 'public',
                    blocked INTEGER DEFAULT 0,
                    updated_at REAL
                );
                CREATE INDEX IF NOT EXISTS idx_media_norm ON media(normalized_title);
                CREATE INDEX IF NOT EXISTS idx_media_type ON media(type);
                CREATE INDEX IF NOT EXISTS idx_media_year ON media(year);
                CREATE INDEX IF NOT EXISTS idx_media_blocked ON media(blocked);
                CREATE INDEX IF NOT EXISTS idx_media_vis ON media(visibility);

                CREATE TABLE IF NOT EXISTS media_source (
                    media_id TEXT,
                    source_id TEXT,
                    external_id TEXT,
                    url TEXT,
                    PRIMARY KEY (media_id, source_id, external_id)
                );
                CREATE INDEX IF NOT EXISTS idx_ms_media ON media_source(media_id);
                CREATE INDEX IF NOT EXISTS idx_ms_source ON media_source(source_id);

                CREATE TABLE IF NOT EXISTS blocks (
                    content_type TEXT,
                    content_id TEXT,
                    source_id TEXT DEFAULT '*',
                    content_name TEXT,
                    blocked_by INTEGER,
                    blocked_at REAL,
                    reason TEXT,
                    PRIMARY KEY (content_type, content_id, source_id)
                );

                CREATE TABLE IF NOT EXISTS favorites (
                    user_id INTEGER,
                    media_id TEXT,
                    title TEXT,
                    type TEXT,
                    added_at REAL,
                    PRIMARY KEY (user_id, media_id)
                );
                CREATE INDEX IF NOT EXISTS idx_fav_user ON favorites(user_id);

                CREATE TABLE IF NOT EXISTS watch_history (
                    user_id INTEGER,
                    media_id TEXT,
                    title TEXT,
                    type TEXT,
                    watched_at REAL
                );
                CREATE INDEX IF NOT EXISTS idx_hist_user ON watch_history(user_id);

                CREATE TABLE IF NOT EXISTS audit_log (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    admin_id INTEGER,
                    action TEXT,
                    content_type TEXT,
                    content_id TEXT,
                    content_name TEXT,
                    source_id TEXT,
                    timestamp REAL,
                    reason TEXT
                );

                CREATE TABLE IF NOT EXISTS users (
                    user_id INTEGER PRIMARY KEY,
                    username TEXT,
                    first_name TEXT,
                    last_seen REAL
                );
                """
            )

    def touch_user(self, user_id: int, username: str = "", first_name: str = ""):
        with self._conn() as c:
            c.execute(
                "INSERT INTO users(user_id,username,first_name,last_seen) VALUES(?,?,?,?) "
                "ON CONFLICT(user_id) DO UPDATE SET username=excluded.username, first_name=excluded.first_name, last_seen=excluded.last_seen",
                (user_id, username or "", first_name or "", time.time()),
            )

    def users_count(self) -> int:
        with self._conn() as c:
            return c.execute("SELECT COUNT(*) FROM users").fetchone()[0]

    def save_block(self, block: Dict[str, Any]):
        with self._conn() as c:
            c.execute(
                "INSERT OR REPLACE INTO blocks(content_type,content_id,source_id,content_name,blocked_by,blocked_at,reason) VALUES(?,?,?,?,?,?,?)",
                (
                    block["content_type"], block["content_id"], block.get("source_id", "*"),
                    block.get("content_name", ""), block.get("blocked_by", 0),
                    block.get("blocked_at", time.time()), block.get("reason", ""),
                ),
            )
            c.execute(
                "INSERT INTO audit_log(admin_id,action,content_type,content_id,content_name,source_id,timestamp,reason) VALUES(?,?,?,?,?,?,?,?)",
                (
                    block.get("blocked_by", 0), "BLOCK", block["content_type"], block["content_id"],
                    block.get("content_name", ""), block.get("source_id", "*"),
                    block.get("blocked_at", time.time()), block.get("reason", ""),
                ),
            )

    def load_blocks(self) -> List[Dict[str, Any]]:
        with self._conn() as c:
            rows = c.execute("SELECT * FROM blocks").fetchall()
            return [dict(r) for r in rows]

    def add_favorite(self, user_id: int, media_id: str, title: str, type_: str):
        with self._conn() as c:
            c.execute(
                "INSERT OR REPLACE INTO favorites(user_id,media_id,title,type,added_at) VALUES(?,?,?,?,?)",
                (user_id, media_id, title, type_, time.time()),
            )

    def get_favorites(self, user_id: int) -> List[Dict]:
        with self._conn() as c:
            return [dict(r) for r in c.execute(
                "SELECT * FROM favorites WHERE user_id=? ORDER BY added_at DESC LIMIT 50", (user_id,)
            )]

    def add_history(self, user_id: int, media_id: str, title: str, type_: str):
        """Upsert history: same media_id updates watched_at instead of duplicating."""
        with self._conn() as c:
            # remove older consecutive / duplicate rows for this media
            c.execute(
                "DELETE FROM watch_history WHERE user_id=? AND media_id=?",
                (user_id, media_id),
            )
            c.execute(
                "INSERT INTO watch_history(user_id,media_id,title,type,watched_at) VALUES(?,?,?,?,?)",
                (user_id, media_id, title, type_, time.time()),
            )

    def get_history(self, user_id: int, limit: int = 20) -> List[Dict]:
        with self._conn() as c:
            return [dict(r) for r in c.execute(
                "SELECT * FROM watch_history WHERE user_id=? ORDER BY watched_at DESC LIMIT ?",
                (user_id, limit),
            )]
