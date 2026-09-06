# -*- coding: utf-8 -*-
"""API authentication/session persistence shared with the existing bot SQLite DB."""
import hashlib
import os
import secrets
import sqlite3
import time
import uuid
from datetime import datetime, timezone, timedelta
from typing import Optional, Dict, Any

try:
    import config as _cfg
except Exception:
    _cfg = None
DB_PATH = os.getenv("DB_PATH", "").strip() or str(getattr(_cfg, "DB_PATH", "cinema_bot.db"))
SESSION_TTL = int(os.getenv("API_SESSION_TTL", "86400"))
LOGIN_TTL = int(os.getenv("API_LOGIN_TTL", "300"))
STREAM_TTL = int(os.getenv("API_STREAM_TTL", "900"))


def _now() -> int:
    return int(time.time())


def _iso(ts: int) -> str:
    return datetime.fromtimestamp(ts, timezone.utc).isoformat().replace("+00:00", "Z")


class AuthStore:
    def __init__(self, path: str = DB_PATH):
        self.path = path
        self.init()

    def con(self):
        c = sqlite3.connect(self.path, timeout=20)
        c.row_factory = sqlite3.Row
        return c

    def init(self):
        with self.con() as c:
            # Existing installations keep all existing columns/features.
            cols = {r[1] for r in c.execute("PRAGMA table_info(users)").fetchall()}
            if not cols:
                c.execute("""CREATE TABLE IF NOT EXISTS users (
                    telegram_id INTEGER PRIMARY KEY, username TEXT, first_name TEXT,
                    joined_at TEXT DEFAULT CURRENT_TIMESTAMP)""")
                cols = {"telegram_id", "username", "first_name"}
            if "last_name" not in cols:
                c.execute("ALTER TABLE users ADD COLUMN last_name TEXT DEFAULT ''")
            if "role" not in cols:
                c.execute("ALTER TABLE users ADD COLUMN role TEXT DEFAULT 'user'")
            if "banned" not in cols:
                c.execute("ALTER TABLE users ADD COLUMN banned INTEGER DEFAULT 0")
            c.executescript("""
                CREATE TABLE IF NOT EXISTS api_login_requests (
                    request_id TEXT PRIMARY KEY,
                    created_at INTEGER NOT NULL,
                    expires_at INTEGER NOT NULL,
                    telegram_id INTEGER,
                    completed_at INTEGER,
                    session_token TEXT
                );
                CREATE TABLE IF NOT EXISTS api_sessions (
                    token_hash TEXT PRIMARY KEY,
                    telegram_id INTEGER NOT NULL,
                    created_at INTEGER NOT NULL,
                    expires_at INTEGER NOT NULL,
                    revoked_at INTEGER
                );
                CREATE INDEX IF NOT EXISTS idx_api_sessions_user
                    ON api_sessions(telegram_id);
                CREATE TABLE IF NOT EXISTS api_stream_tokens (
                    token_hash TEXT PRIMARY KEY,
                    telegram_id INTEGER NOT NULL,
                    content_id TEXT NOT NULL,
                    source_url TEXT NOT NULL,
                    mime TEXT DEFAULT 'application/octet-stream',
                    created_at INTEGER NOT NULL,
                    expires_at INTEGER NOT NULL
                );
                CREATE TABLE IF NOT EXISTS api_proxy_tokens (
                    token_hash TEXT PRIMARY KEY,
                    telegram_id INTEGER NOT NULL,
                    parent_token_hash TEXT NOT NULL,
                    source_url TEXT NOT NULL,
                    created_at INTEGER NOT NULL,
                    expires_at INTEGER NOT NULL
                );
            """)

    @staticmethod
    def hash_token(token: str) -> str:
        return hashlib.sha256(token.encode("utf-8")).hexdigest()

    def ensure_user(self, telegram_id: int, username: str = "", first_name: str = "",
                    last_name: str = "") -> Dict[str, Any]:
        with self.con() as c:
            c.execute("""
                INSERT INTO users(telegram_id, username, first_name, last_name)
                VALUES(?,?,?,?)
                ON CONFLICT(telegram_id) DO UPDATE SET
                  username=excluded.username,
                  first_name=excluded.first_name,
                  last_name=excluded.last_name
            """, (int(telegram_id), username or "", first_name or "", last_name or ""))
            row = c.execute(
                "SELECT telegram_id, username, first_name, last_name, role, banned FROM users WHERE telegram_id=?",
                (int(telegram_id),)
            ).fetchone()
            return dict(row)

    def create_login_request(self) -> Dict[str, Any]:
        rid = "login_" + uuid.uuid4().hex
        now = _now()
        exp = now + LOGIN_TTL
        with self.con() as c:
            c.execute("INSERT INTO api_login_requests(request_id,created_at,expires_at) VALUES(?,?,?)",
                      (rid, now, exp))
        return {"request_id": rid, "expires_at": _iso(exp), "expires_in": LOGIN_TTL}

    def complete_login(self, request_id: str, telegram_user: Dict[str, Any]) -> bool:
        now = _now()
        with self.con() as c:
            row = c.execute(
                "SELECT request_id, expires_at, telegram_id, completed_at FROM api_login_requests WHERE request_id=?",
                (request_id,)
            ).fetchone()
            if not row or row["completed_at"] or row["telegram_id"] or row["expires_at"] < now:
                return False
            uid = int(telegram_user["id"])
            c.execute("""
                INSERT INTO users(telegram_id,username,first_name,last_name)
                VALUES(?,?,?,?,)
            """.replace("?,?,?,?,)", "?,?,?,?)"),
                      (uid, telegram_user.get("username","") or "",
                       telegram_user.get("first_name","") or "",
                       telegram_user.get("last_name","") or ""))
            c.execute("UPDATE api_login_requests SET telegram_id=?,completed_at=? WHERE request_id=?",
                      (uid, now, request_id))
            return True

    def login_status(self, request_id: str) -> Optional[Dict[str, Any]]:
        with self.con() as c:
            row = c.execute("SELECT * FROM api_login_requests WHERE request_id=?", (request_id,)).fetchone()
        return dict(row) if row else None

    def session_for_request(self, request_id: str, telegram_id: int):
        with self.con() as c:
            row = c.execute("SELECT session_token FROM api_login_requests WHERE request_id=? AND telegram_id=?",
                            (request_id, int(telegram_id))).fetchone()
        if row and row["session_token"]:
            token = row["session_token"]
            user = self.user_for_session(token)
            if user:
                return {"token": token, "expires_at": _iso(user["expires_at"]),
                        "expires_in": max(0, int(user["expires_at"] - _now()))}
        session = self.create_session(telegram_id)
        with self.con() as c:
            c.execute("UPDATE api_login_requests SET session_token=? WHERE request_id=? AND telegram_id=?",
                      (session["token"], request_id, int(telegram_id)))
        return session

    def create_session(self, telegram_id: int) -> Dict[str, Any]:
        token = secrets.token_urlsafe(48)
        now = _now(); exp = now + SESSION_TTL
        with self.con() as c:
            c.execute("INSERT INTO api_sessions(token_hash,telegram_id,created_at,expires_at) VALUES(?,?,?,?)",
                      (self.hash_token(token), int(telegram_id), now, exp))
        return {"token": token, "expires_at": _iso(exp), "expires_in": SESSION_TTL}

    def user_for_session(self, token: str) -> Optional[Dict[str, Any]]:
        if not token:
            return None
        h = self.hash_token(token); now = _now()
        with self.con() as c:
            row = c.execute("""
                SELECT u.telegram_id,u.username,u.first_name,u.last_name,u.role,u.banned,
                       s.expires_at,s.revoked_at
                FROM api_sessions s JOIN users u ON u.telegram_id=s.telegram_id
                WHERE s.token_hash=?
            """, (h,)).fetchone()
        if not row or row["revoked_at"] or row["expires_at"] < now or row["banned"]:
            return None
        return dict(row)

    def revoke(self, token: str) -> bool:
        with self.con() as c:
            cur = c.execute("UPDATE api_sessions SET revoked_at=? WHERE token_hash=? AND revoked_at IS NULL",
                            (_now(), self.hash_token(token)))
            return cur.rowcount > 0

    def permissions(self, user: Dict[str, Any]):
        role = (user.get("role") or "user").lower()
        if role == "admin":
            return ["content.read", "stream.play", "admin.*"]
        if role == "premium":
            return ["content.read", "stream.play", "premium.*"]
        if role == "banned":
            return []
        return ["content.read", "stream.play"]

    def issue_stream_token(self, telegram_id: int, content_id: str, source_url: str, mime: str):
        raw = secrets.token_urlsafe(40); now = _now(); exp = now + STREAM_TTL
        with self.con() as c:
            c.execute("""INSERT INTO api_stream_tokens
                (token_hash,telegram_id,content_id,source_url,mime,created_at,expires_at)
                VALUES(?,?,?,?,?,?,?)""",
                      (self.hash_token(raw), int(telegram_id), content_id, source_url, mime, now, exp))
        return raw, _iso(exp)

    def stream_token(self, raw: str):
        with self.con() as c:
            row = c.execute("SELECT * FROM api_stream_tokens WHERE token_hash=?",
                            (self.hash_token(raw),)).fetchone()
        return dict(row) if row and row["expires_at"] >= _now() else None

    def issue_proxy_token(self, telegram_id: int, parent_hash: str, source_url: str, expires_at: int):
        raw = secrets.token_urlsafe(36); now = _now()
        with self.con() as c:
            c.execute("""INSERT INTO api_proxy_tokens
                (token_hash,telegram_id,parent_token_hash,source_url,created_at,expires_at)
                VALUES(?,?,?,?,?,?)""",
                      (self.hash_token(raw), int(telegram_id), parent_hash, source_url, now, min(expires_at, now + STREAM_TTL)))
        return raw

    def proxy_token(self, raw: str):
        with self.con() as c:
            row = c.execute("SELECT * FROM api_proxy_tokens WHERE token_hash=?",
                            (self.hash_token(raw),)).fetchone()
        return dict(row) if row and row["expires_at"] >= _now() else None
