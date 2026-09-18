import aiosqlite
import logging
import os
import base64
import hashlib
from datetime import datetime
from typing import Optional, List, Dict
from pathlib import Path
from config import DATABASE_PATH

try:
    from cryptography.fernet import Fernet, InvalidToken
except Exception:  # optional at import time; plaintext legacy rows still read
    Fernet = None
    InvalidToken = Exception

logger = logging.getLogger(__name__)


def _rtmp_fernet():
    """Build a stable Fernet key from RTMP_ENCRYPTION_KEY without logging it."""
    if Fernet is None:
        return None
    raw = os.getenv("RTMP_ENCRYPTION_KEY", "").strip()
    if not raw:
        return None
    try:
        return Fernet(raw.encode())
    except Exception:
        derived = base64.urlsafe_b64encode(hashlib.sha256(raw.encode()).digest())
        return Fernet(derived)


def _encrypt_rtmp_key(value: str) -> str:
    if not value:
        return value
    fernet = _rtmp_fernet()
    if not fernet:
        return value
    try:
        return "enc:v1:" + fernet.encrypt(str(value).encode()).decode()
    except Exception:
        logger.warning("Unable to encrypt RTMP key; refusing to log or transform the value")
        return value


def _decrypt_rtmp_key(value: str) -> str:
    if not value or not str(value).startswith("enc:v1:"):
        return value
    fernet = _rtmp_fernet()
    if not fernet:
        logger.error("Encrypted RTMP key cannot be used: RTMP_ENCRYPTION_KEY is missing")
        return ""
    try:
        return fernet.decrypt(str(value)[7:].encode()).decode()
    except InvalidToken:
        logger.error("Encrypted RTMP key could not be decrypted with the configured key")
        return ""
    except Exception as exc:
        logger.error("Encrypted RTMP key read failed: %s", type(exc).__name__)
        return ""


def _public_rtmp_profile(row: Dict) -> Dict:
    data = dict(row)
    data["stream_key"] = _decrypt_rtmp_key(data.get("stream_key"))
    return data


class Database:
    def __init__(self, db_path: str = DATABASE_PATH):
        self.db_path = db_path
        self._conn: Optional[aiosqlite.Connection] = None

    @property
    def conn(self):
        return self._conn

    async def connect(self):
        Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
        last = None
        for attempt in range(3):
            try:
                self._conn = await aiosqlite.connect(self.db_path, timeout=30.0)
                self._conn.row_factory = aiosqlite.Row
                try:
                    await self._conn.execute("PRAGMA journal_mode=WAL")
                    await self._conn.execute("PRAGMA busy_timeout=5000")
                except Exception:
                    pass
                await self._create_tables()
                last = None
                break
            except Exception as e:
                last = e
                logger.warning("db connect attempt %s failed: %s", attempt + 1, e)
                import asyncio
                await asyncio.sleep(0.5 * (attempt + 1))
        if last is not None and self._conn is None:
            raise last
        try:
            # The project historically has both database.py and database/migrate.py.
            # Python resolves database.py as the module, so `database.migrate` is not
            # importable as a package submodule. Load the migration runner directly
            # from its file instead of requiring a package rename (which would break
            # existing `from database import db` imports).
            import importlib.util
            migrate_path = Path(__file__).resolve().parent / "database" / "migrate.py"
            if migrate_path.exists():
                spec = importlib.util.spec_from_file_location("_katabump_db_migrate", migrate_path)
                module = importlib.util.module_from_spec(spec)
                assert spec.loader is not None
                spec.loader.exec_module(module)
                await module.run_migrations(self._conn)
            else:
                logger.info("No database migration runner found; using built-in schema setup.")
        except Exception as e:
            logger.warning("migrations: %s", e)
        # ensure user_permissions + user_stats
        try:
            await self._conn.executescript("""
                CREATE TABLE IF NOT EXISTS user_permissions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    permission TEXT NOT NULL,
                    granted INTEGER DEFAULT 1,
                    UNIQUE(user_id, permission)
                );
                
                CREATE TABLE IF NOT EXISTS jobs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER,
                    type TEXT,
                    status TEXT DEFAULT 'queued',
                    total_bytes INTEGER DEFAULT 0,
                    transferred_bytes INTEGER DEFAULT 0,
                    speed REAL DEFAULT 0,
                    started_at TEXT,
                    updated_at TEXT,
                    error TEXT,
                    meta TEXT
                );

                CREATE TABLE IF NOT EXISTS user_stats (
                    user_id INTEGER PRIMARY KEY,
                    total_stream_seconds INTEGER DEFAULT 0,
                    total_streams INTEGER DEFAULT 0,
                    total_uploads INTEGER DEFAULT 0,
                    last_stream_at TEXT,
                    updated_at TEXT
                );
            """)
            await self._conn.commit()
        except Exception as e:
            logger.warning("extra tables: %s", e)
        await self._migrate_rtmp_keys()
        logger.info("Database connected")

    async def _migrate_rtmp_keys(self):
        """Encrypt legacy plaintext keys once a deployment key is configured."""
        if not _rtmp_fernet():
            return
        try:
            cur = await self._conn.execute(
                "SELECT id, stream_key FROM rtmp_profiles WHERE stream_key NOT LIKE 'enc:v1:%'"
            )
            rows = await cur.fetchall()
            for row in rows:
                await self._conn.execute(
                    "UPDATE rtmp_profiles SET stream_key=? WHERE id=?",
                    (_encrypt_rtmp_key(row["stream_key"]), row["id"]),
                )
            if rows:
                await self._conn.commit()
                logger.info("Encrypted %s legacy RTMP profile key(s)", len(rows))
        except Exception as exc:
            logger.warning("RTMP key migration skipped: %s", type(exc).__name__)

    async def close(self):
        if self._conn:
            try:
                await self._conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
            except Exception:
                pass
            try:
                await self._conn.close()
            finally:
                self._conn = None

    async def ensure_connected(self) -> bool:
        """Reconnect if the connection was lost (rare on long-running hosts)."""
        if self._conn is not None:
            try:
                await self._conn.execute("SELECT 1")
                return True
            except Exception as e:
                logger.warning("db connection unhealthy, reconnecting: %s", e)
                try:
                    await self._conn.close()
                except Exception:
                    pass
                self._conn = None
        try:
            await self.connect()
            return self._conn is not None
        except Exception as e:
            logger.error("db reconnect failed: %s", e)
            return False

    async def _create_tables(self):
        await self._conn.executescript("""
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                username TEXT,
                first_name TEXT,
                last_name TEXT,
                role TEXT DEFAULT 'user',
                is_banned INTEGER DEFAULT 0,
                phone TEXT,
                phone_verified INTEGER DEFAULT 0,
                joined_at TEXT,
                last_active TEXT
            );
            CREATE TABLE IF NOT EXISTS files (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                file_name TEXT,
                file_size INTEGER,
                r2_key TEXT,
                r2_url TEXT,
                mime_type TEXT,
                uploaded_at TEXT,
                FOREIGN KEY (user_id) REFERENCES users(user_id)
            );
            CREATE TABLE IF NOT EXISTS streams (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                title TEXT,
                source_url TEXT,
                rtmp_url TEXT,
                status TEXT DEFAULT 'stopped',
                started_at TEXT,
                stopped_at TEXT,
                pid INTEGER,
                last_error TEXT,
                audio_bitrate TEXT DEFAULT '128k',
                volume REAL DEFAULT 1.0,
                start_offset REAL DEFAULT 0,
                codec_info TEXT,
                FOREIGN KEY (user_id) REFERENCES users(user_id)
            );
            CREATE TABLE IF NOT EXISTS settings (
                key TEXT PRIMARY KEY,
                value TEXT
            );
            CREATE TABLE IF NOT EXISTS rtmp_profiles (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                name TEXT DEFAULT 'الافتراضي',
                rtmp_base TEXT NOT NULL,
                stream_key TEXT NOT NULL,
                is_default INTEGER DEFAULT 0,
                created_at TEXT,
                FOREIGN KEY (user_id) REFERENCES users(user_id)
            );
            CREATE TABLE IF NOT EXISTS stream_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                stream_id INTEGER,
                user_id INTEGER,
                event TEXT,
                message TEXT,
                details TEXT,
                created_at TEXT
            );
            CREATE TABLE IF NOT EXISTS playlists (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                name TEXT DEFAULT 'قائمة التشغيل',
                stream_id INTEGER,
                current_index INTEGER DEFAULT 0,
                shuffle INTEGER DEFAULT 0,
                loop_mode TEXT DEFAULT 'none',
                created_at TEXT,
                FOREIGN KEY (user_id) REFERENCES users(user_id)
            );
            CREATE TABLE IF NOT EXISTS playlist_items (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                playlist_id INTEGER NOT NULL,
                title TEXT,
                source_url TEXT NOT NULL,
                position INTEGER DEFAULT 0,
                duration REAL,
                FOREIGN KEY (playlist_id) REFERENCES playlists(id)
            );
            CREATE TABLE IF NOT EXISTS schedules (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                name TEXT,
                source_url TEXT,
                rtmp_url TEXT,
                start_time TEXT,
                end_time TEXT,
                days TEXT DEFAULT 'daily',
                enabled INTEGER DEFAULT 1,
                last_run TEXT,
                stream_id INTEGER,
                created_at TEXT,
                FOREIGN KEY (user_id) REFERENCES users(user_id)
            );
            CREATE TABLE IF NOT EXISTS favorites (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                item_type TEXT,
                title TEXT,
                source_url TEXT,
                meta TEXT,
                created_at TEXT,
                FOREIGN KEY (user_id) REFERENCES users(user_id)
            );
            CREATE TABLE IF NOT EXISTS audit_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                action TEXT,
                target TEXT,
                details TEXT,
                created_at TEXT
            );
            CREATE TABLE IF NOT EXISTS user_storage (
                user_id INTEGER PRIMARY KEY,
                provider TEXT DEFAULT 'r2',
                config_json TEXT,
                updated_at TEXT,
                FOREIGN KEY (user_id) REFERENCES users(user_id)
            );
            CREATE TABLE IF NOT EXISTS archived_videos (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT NOT NULL,
                title_norm TEXT,
                source_url TEXT,
                source_hash TEXT,
                duration_sec REAL,
                quality TEXT,
                file_id TEXT,
                file_unique_id TEXT,
                message_id INTEGER,
                channel_id INTEGER,
                size_bytes INTEGER,
                uploaded_by INTEGER,
                uploaded_at TEXT,
                UNIQUE(source_hash)
            );
            CREATE INDEX IF NOT EXISTS idx_archive_title ON archived_videos(title_norm);
            CREATE INDEX IF NOT EXISTS idx_archive_hash ON archived_videos(source_hash);
        """)
        await self._conn.commit()
        try:
            cur = await self._conn.execute("PRAGMA table_info(users)")
            cols = {r[1] for r in await cur.fetchall()}
            if "phone" not in cols:
                await self._conn.execute("ALTER TABLE users ADD COLUMN phone TEXT")
            if "phone_verified" not in cols:
                await self._conn.execute(
                    "ALTER TABLE users ADD COLUMN phone_verified INTEGER DEFAULT 0"
                )
            if "approval_status" not in cols:
                await self._conn.execute(
                    "ALTER TABLE users ADD COLUMN approval_status TEXT DEFAULT 'pending'"
                )
                # existing users become approved so nothing breaks
                await self._conn.execute(
                    "UPDATE users SET approval_status='approved' WHERE approval_status IS NULL OR approval_status=''"
                )
            cur = await self._conn.execute("PRAGMA table_info(files)")
            fcols = {r[1] for r in await cur.fetchall()}
            if "r2_url" not in fcols:
                await self._conn.execute("ALTER TABLE files ADD COLUMN r2_url TEXT")
            # streams extra columns (safe migration)
            cur = await self._conn.execute("PRAGMA table_info(streams)")
            scols = {r[1] for r in await cur.fetchall()}
            for col, typedef in [
                ("last_error", "TEXT"),
                ("audio_bitrate", "TEXT DEFAULT '128k'"),
                ("volume", "REAL DEFAULT 1.0"),
                ("start_offset", "REAL DEFAULT 0"),
                ("codec_info", "TEXT"),
            ]:
                if col not in scols:
                    await self._conn.execute(f"ALTER TABLE streams ADD COLUMN {col} {typedef}")
            await self._conn.commit()
        except Exception as e:
            logger.warning("migration: %s", e)

    # ── Users ──
    async def upsert_user(self, user_id, username=None, first_name=None, last_name=None, role="user", approval_status=None):
        """Insert or update user. New users start as 'pending' unless role is owner/admin or approval_status given."""
        now = datetime.utcnow().isoformat()
        existing = await self.get_user(user_id)
        if existing:
            await self._conn.execute(
                "UPDATE users SET username=?, first_name=?, last_name=?, last_active=? WHERE user_id=?",
                (username, first_name, last_name, now, user_id),
            )
        else:
            # New user: pending approval by default (admin/owner auto-approved)
            status = approval_status
            if status is None:
                status = "approved" if role in ("owner", "admin") else "pending"
            await self._conn.execute(
                "INSERT INTO users (user_id, username, first_name, last_name, role, approval_status, joined_at, last_active) VALUES (?,?,?,?,?,?,?,?)",
                (user_id, username, first_name, last_name, role, status, now, now),
            )
        await self._conn.commit()
        return existing is None  # True if this was a brand-new user

    async def get_user(self, user_id: int) -> Optional[Dict]:
        cur = await self._conn.execute("SELECT * FROM users WHERE user_id=?", (user_id,))
        row = await cur.fetchone()
        return dict(row) if row else None

    async def set_role(self, user_id: int, role: str):
        await self._conn.execute("UPDATE users SET role=? WHERE user_id=?", (role, user_id))
        await self._conn.commit()

    async def set_approval_status(self, user_id: int, status: str):
        """status: pending | approved | rejected"""
        await self._conn.execute(
            "UPDATE users SET approval_status=? WHERE user_id=?", (status, user_id)
        )
        await self._conn.commit()

    async def is_approved(self, user_id: int) -> bool:
        u = await self.get_user(user_id)
        if not u:
            return False
        if u.get("is_banned"):
            return False
        status = (u.get("approval_status") or "pending").lower()
        if status == "approved":
            return True
        # owner/admin always allowed
        role = (u.get("role") or "user").lower()
        return role in ("owner", "admin")

    async def get_pending_users(self) -> List[Dict]:
        cur = await self._conn.execute(
            "SELECT * FROM users WHERE approval_status='pending' AND (is_banned=0 OR is_banned IS NULL) ORDER BY joined_at DESC"
        )
        return [dict(r) for r in await cur.fetchall()]

    async def ban_user(self, user_id: int, banned: bool = True):
        await self._conn.execute(
            "UPDATE users SET is_banned=? WHERE user_id=?", (1 if banned else 0, user_id)
        )
        await self._conn.commit()

    async def set_phone(self, user_id: int, phone: str):
        await self._conn.execute(
            "UPDATE users SET phone=?, phone_verified=1 WHERE user_id=?",
            (phone, user_id),
        )
        await self._conn.commit()

    async def is_phone_verified(self, user_id: int) -> bool:
        u = await self.get_user(user_id)
        return bool(u and u.get("phone_verified"))

    async def get_all_users(self) -> List[Dict]:
        cur = await self._conn.execute("SELECT * FROM users ORDER BY joined_at DESC")
        return [dict(r) for r in await cur.fetchall()]

    async def get_all_user_ids(self) -> List[int]:
        cur = await self._conn.execute(
            "SELECT user_id FROM users WHERE (is_banned=0 OR is_banned IS NULL) AND (approval_status='approved' OR approval_status IS NULL OR role IN ('owner','admin'))"
        )
        return [r[0] for r in await cur.fetchall()]

    async def get_users_count(self) -> int:
        cur = await self._conn.execute("SELECT COUNT(*) as c FROM users")
        row = await cur.fetchone()
        return row["c"] if row else 0

    # ── Persistent RBAC overrides ──
    async def set_user_permission(self, user_id: int, permission: str, granted: bool):
        await self._conn.execute(
            "INSERT INTO user_permissions (user_id, permission, granted) VALUES (?,?,?) "
            "ON CONFLICT(user_id, permission) DO UPDATE SET granted=excluded.granted",
            (int(user_id), str(permission), 1 if granted else 0),
        )
        await self._conn.commit()

    async def get_user_permissions(self, user_id: int) -> Dict[str, int]:
        cur = await self._conn.execute(
            "SELECT permission, granted FROM user_permissions WHERE user_id=?", (int(user_id),)
        )
        return {str(r[0]): int(r[1]) for r in await cur.fetchall()}

    async def clear_user_permission(self, user_id: int, permission: str):
        await self._conn.execute(
            "DELETE FROM user_permissions WHERE user_id=? AND permission=?",
            (int(user_id), str(permission)),
        )
        await self._conn.commit()

    # ── Mandatory subscription / bot settings ──
    async def get_json_setting(self, key: str, default=None):
        import json
        raw = await self.get_setting(key, None)
        if raw in (None, ""):
            return default
        try:
            return json.loads(raw)
        except Exception:
            return default

    async def set_json_setting(self, key: str, value):
        import json
        await self.set_setting(key, json.dumps(value, ensure_ascii=False))


    # ── Smart video archive ──
    async def find_archive_by_hash(self, source_hash: str) -> Optional[Dict]:
        cur = await self._conn.execute(
            "SELECT * FROM archived_videos WHERE source_hash=?", (source_hash,)
        )
        row = await cur.fetchone()
        return dict(row) if row else None

    async def search_archive(self, query: str, limit: int = 20) -> List[Dict]:
        q = (query or "").strip().lower()
        if not q:
            cur = await self._conn.execute(
                "SELECT * FROM archived_videos ORDER BY uploaded_at DESC LIMIT ?", (limit,)
            )
        else:
            like = f"%{q}%"
            cur = await self._conn.execute(
                "SELECT * FROM archived_videos WHERE title_norm LIKE ? OR title LIKE ? ORDER BY uploaded_at DESC LIMIT ?",
                (like, like, limit),
            )
        return [dict(r) for r in await cur.fetchall()]

    async def get_archive(self, archive_id: int) -> Optional[Dict]:
        cur = await self._conn.execute(
            "SELECT * FROM archived_videos WHERE id=?", (archive_id,)
        )
        row = await cur.fetchone()
        return dict(row) if row else None

    async def add_archive(
        self,
        title: str,
        source_url: str,
        source_hash: str,
        duration_sec: float,
        quality: str,
        file_id: str,
        file_unique_id: str = None,
        message_id: int = None,
        channel_id: int = None,
        size_bytes: int = None,
        uploaded_by: int = None,
    ) -> int:
        now = datetime.utcnow().isoformat()
        title_norm = (title or "").strip().lower()
        cur = await self._conn.execute(
            """INSERT INTO archived_videos
               (title, title_norm, source_url, source_hash, duration_sec, quality,
                file_id, file_unique_id, message_id, channel_id, size_bytes, uploaded_by, uploaded_at)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)
               ON CONFLICT(source_hash) DO UPDATE SET
                 title=excluded.title,
                 title_norm=excluded.title_norm,
                 file_id=excluded.file_id,
                 file_unique_id=excluded.file_unique_id,
                 message_id=excluded.message_id,
                 duration_sec=excluded.duration_sec,
                 quality=excluded.quality,
                 size_bytes=excluded.size_bytes,
                 uploaded_at=excluded.uploaded_at
            """,
            (
                title, title_norm, source_url, source_hash, duration_sec, quality,
                file_id, file_unique_id, message_id, channel_id, size_bytes, uploaded_by, now,
            ),
        )
        await self._conn.commit()
        return cur.lastrowid

    async def count_archives(self) -> int:
        cur = await self._conn.execute("SELECT COUNT(*) as c FROM archived_videos")
        row = await cur.fetchone()
        return row["c"] if row else 0

    async def list_archives(self, limit: int = 30, offset: int = 0) -> List[Dict]:
        cur = await self._conn.execute(
            "SELECT * FROM archived_videos ORDER BY uploaded_at DESC LIMIT ? OFFSET ?",
            (limit, offset),
        )
        return [dict(r) for r in await cur.fetchall()]

    async def delete_archive(self, archive_id: int) -> bool:
        cur = await self._conn.execute("DELETE FROM archived_videos WHERE id=?", (archive_id,))
        await self._conn.commit()
        return cur.rowcount > 0

    # ── Files ──
    async def add_file(self, user_id, file_name, file_size, r2_key, r2_url, mime_type=None) -> int:
        now = datetime.utcnow().isoformat()
        cur = await self._conn.execute(
            "INSERT INTO files (user_id, file_name, file_size, r2_key, r2_url, mime_type, uploaded_at) VALUES (?,?,?,?,?,?,?)",
            (user_id, file_name, file_size, r2_key, r2_url, mime_type, now),
        )
        await self._conn.commit()
        return cur.lastrowid

    async def get_file(self, file_id: int) -> Optional[Dict]:
        cur = await self._conn.execute("SELECT * FROM files WHERE id=?", (file_id,))
        row = await cur.fetchone()
        return dict(row) if row else None

    async def get_user_files(self, user_id: int) -> List[Dict]:
        cur = await self._conn.execute(
            "SELECT * FROM files WHERE user_id=? ORDER BY id DESC", (user_id,)
        )
        return [dict(r) for r in await cur.fetchall()]

    async def get_all_files(self) -> List[Dict]:
        cur = await self._conn.execute("SELECT * FROM files ORDER BY id DESC LIMIT 100")
        return [dict(r) for r in await cur.fetchall()]

    async def delete_file(self, file_id: int, user_id: int = None) -> bool:
        if user_id:
            await self._conn.execute(
                "DELETE FROM files WHERE id=? AND user_id=?", (file_id, user_id)
            )
        else:
            await self._conn.execute("DELETE FROM files WHERE id=?", (file_id,))
        await self._conn.commit()
        return True

    # ── Streams ──
    async def create_stream(self, user_id, title, source_url, rtmp_url=None) -> int:
        cur = await self._conn.execute(
            "INSERT INTO streams (user_id, title, source_url, rtmp_url, status) VALUES (?,?,?,?,?)",
            (user_id, title, source_url, rtmp_url, "stopped"),
        )
        await self._conn.commit()
        return cur.lastrowid

    async def get_stream(self, stream_id: int) -> Optional[Dict]:
        cur = await self._conn.execute("SELECT * FROM streams WHERE id=?", (stream_id,))
        row = await cur.fetchone()
        return dict(row) if row else None

    async def update_stream_status(self, stream_id, status, pid=None):
        now = datetime.utcnow().isoformat()
        if status == "running":
            await self._conn.execute(
                "UPDATE streams SET status=?, pid=?, started_at=? WHERE id=?",
                (status, pid, now, stream_id),
            )
        else:
            await self._conn.execute(
                "UPDATE streams SET status=?, pid=NULL, stopped_at=? WHERE id=?",
                (status, now, stream_id),
            )
        await self._conn.commit()

    async def get_user_streams(self, user_id: int) -> List[Dict]:
        cur = await self._conn.execute(
            "SELECT * FROM streams WHERE user_id=? ORDER BY id DESC", (user_id,)
        )
        return [dict(r) for r in await cur.fetchall()]

    async def get_active_streams(self) -> List[Dict]:
        cur = await self._conn.execute("SELECT * FROM streams WHERE status='running'")
        return [dict(r) for r in await cur.fetchall()]

    async def get_all_streams(self) -> List[Dict]:
        cur = await self._conn.execute("SELECT * FROM streams ORDER BY id DESC LIMIT 50")
        return [dict(r) for r in await cur.fetchall()]

    async def delete_stream(self, stream_id: int, user_id: int = None) -> bool:
        if user_id is not None:
            cur = await self._conn.execute(
                "DELETE FROM streams WHERE id=? AND user_id=?", (stream_id, user_id)
            )
        else:
            cur = await self._conn.execute("DELETE FROM streams WHERE id=?", (stream_id,))
        await self._conn.commit()
        return cur.rowcount > 0

    # ── Settings ──
    async def get_setting(self, key: str, default: str = None) -> Optional[str]:
        cur = await self._conn.execute("SELECT value FROM settings WHERE key=?", (key,))
        row = await cur.fetchone()
        return row["value"] if row else default

    async def set_setting(self, key: str, value: str):
        await self._conn.execute(
            "INSERT INTO settings (key, value) VALUES (?, ?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
            (key, value),
        )
        await self._conn.commit()

    # ── Stream extras ──
    async def update_stream_error(self, stream_id: int, error: str):
        await self._conn.execute(
            "UPDATE streams SET last_error=? WHERE id=?", (error, stream_id)
        )
        await self._conn.commit()

    async def update_stream_meta(self, stream_id: int, **kwargs):
        allowed = {"audio_bitrate", "volume", "start_offset", "codec_info", "last_error", "rtmp_url", "source_url", "title"}
        sets, vals = [], []
        for k, v in kwargs.items():
            if k in allowed:
                sets.append(f"{k}=?")
                vals.append(v)
        if not sets:
            return
        vals.append(stream_id)
        await self._conn.execute(
            f"UPDATE streams SET {', '.join(sets)} WHERE id=?", vals
        )
        await self._conn.commit()

    async def add_stream_log(self, stream_id: int, user_id: int, event: str, message: str, details: str = ""):
        now = datetime.utcnow().isoformat()
        await self._conn.execute(
            "INSERT INTO stream_logs (stream_id, user_id, event, message, details, created_at) VALUES (?,?,?,?,?,?)",
            (stream_id, user_id, event, message, details, now),
        )
        await self._conn.commit()

    async def get_stream_logs(self, stream_id: int = None, limit: int = 50) -> List[Dict]:
        if stream_id:
            cur = await self._conn.execute(
                "SELECT * FROM stream_logs WHERE stream_id=? ORDER BY id DESC LIMIT ?",
                (stream_id, limit),
            )
        else:
            cur = await self._conn.execute(
                "SELECT * FROM stream_logs ORDER BY id DESC LIMIT ?", (limit,)
            )
        return [dict(r) for r in await cur.fetchall()]

    # ── RTMP Profiles (saved settings) ──
    async def save_rtmp_profile(self, user_id: int, rtmp_base: str, stream_key: str, name: str = "الافتراضي", is_default: bool = True) -> int:
        now = datetime.utcnow().isoformat()
        if is_default:
            await self._conn.execute(
                "UPDATE rtmp_profiles SET is_default=0 WHERE user_id=?", (user_id,)
            )
        cur = await self._conn.execute(
            "INSERT INTO rtmp_profiles (user_id, name, rtmp_base, stream_key, is_default, created_at) VALUES (?,?,?,?,?,?)",
            (user_id, name, rtmp_base, _encrypt_rtmp_key(stream_key), 1 if is_default else 0, now),
        )
        await self._conn.commit()
        return cur.lastrowid

    async def get_user_rtmp_profiles(self, user_id: int) -> List[Dict]:
        cur = await self._conn.execute(
            "SELECT * FROM rtmp_profiles WHERE user_id=? ORDER BY is_default DESC, id DESC",
            (user_id,),
        )
        return [_public_rtmp_profile(dict(r)) for r in await cur.fetchall()]

    async def get_default_rtmp_profile(self, user_id: int) -> Optional[Dict]:
        cur = await self._conn.execute(
            "SELECT * FROM rtmp_profiles WHERE user_id=? AND is_default=1 LIMIT 1",
            (user_id,),
        )
        row = await cur.fetchone()
        if row:
            return _public_rtmp_profile(dict(row))
        # fallback to latest
        cur = await self._conn.execute(
            "SELECT * FROM rtmp_profiles WHERE user_id=? ORDER BY id DESC LIMIT 1",
            (user_id,),
        )
        row = await cur.fetchone()
        return _public_rtmp_profile(dict(row)) if row else None

    async def delete_rtmp_profile(self, profile_id: int, user_id: int) -> bool:
        await self._conn.execute(
            "DELETE FROM rtmp_profiles WHERE id=? AND user_id=?", (profile_id, user_id)
        )
        await self._conn.commit()
        return True

    async def set_default_rtmp_profile(self, profile_id: int, user_id: int):
        await self._conn.execute(
            "UPDATE rtmp_profiles SET is_default=0 WHERE user_id=?", (user_id,)
        )
        await self._conn.execute(
            "UPDATE rtmp_profiles SET is_default=1 WHERE id=? AND user_id=?",
            (profile_id, user_id),
        )
        await self._conn.commit()

    # ── Playlists ──
    async def create_playlist(self, user_id: int, name: str = "قائمة التشغيل", stream_id: int = None) -> int:
        now = datetime.utcnow().isoformat()
        cur = await self._conn.execute(
            "INSERT INTO playlists (user_id, name, stream_id, current_index, shuffle, loop_mode, created_at) VALUES (?,?,?,?,?,?,?)",
            (user_id, name, stream_id, 0, 0, "none", now),
        )
        await self._conn.commit()
        return cur.lastrowid

    async def get_playlist(self, playlist_id: int) -> Optional[Dict]:
        cur = await self._conn.execute("SELECT * FROM playlists WHERE id=?", (playlist_id,))
        row = await cur.fetchone()
        return dict(row) if row else None

    async def get_user_playlists(self, user_id: int) -> List[Dict]:
        cur = await self._conn.execute(
            "SELECT * FROM playlists WHERE user_id=? ORDER BY id DESC", (user_id,)
        )
        return [dict(r) for r in await cur.fetchall()]

    async def get_playlist_for_stream(self, stream_id: int) -> Optional[Dict]:
        cur = await self._conn.execute(
            "SELECT * FROM playlists WHERE stream_id=? ORDER BY id DESC LIMIT 1", (stream_id,)
        )
        row = await cur.fetchone()
        return dict(row) if row else None

    async def add_playlist_item(self, playlist_id: int, title: str, source_url: str, position: int = None) -> int:
        if position is None:
            cur = await self._conn.execute(
                "SELECT COALESCE(MAX(position), -1) + 1 AS p FROM playlist_items WHERE playlist_id=?",
                (playlist_id,),
            )
            row = await cur.fetchone()
            position = row["p"] if row else 0
        cur = await self._conn.execute(
            "INSERT INTO playlist_items (playlist_id, title, source_url, position) VALUES (?,?,?,?)",
            (playlist_id, title, source_url, position),
        )
        await self._conn.commit()
        return cur.lastrowid

    async def get_playlist_items(self, playlist_id: int) -> List[Dict]:
        cur = await self._conn.execute(
            "SELECT * FROM playlist_items WHERE playlist_id=? ORDER BY position ASC, id ASC",
            (playlist_id,),
        )
        return [dict(r) for r in await cur.fetchall()]

    async def delete_playlist_item(self, item_id: int, playlist_id: int) -> bool:
        await self._conn.execute(
            "DELETE FROM playlist_items WHERE id=? AND playlist_id=?", (item_id, playlist_id)
        )
        await self._conn.commit()
        return True

    async def update_playlist(self, playlist_id: int, **kwargs):
        allowed = {"name", "stream_id", "current_index", "shuffle", "loop_mode"}
        sets, vals = [], []
        for k, v in kwargs.items():
            if k in allowed:
                sets.append(f"{k}=?")
                vals.append(v)
        if not sets:
            return
        vals.append(playlist_id)
        await self._conn.execute(f"UPDATE playlists SET {', '.join(sets)} WHERE id=?", vals)
        await self._conn.commit()

    async def clear_playlist_items(self, playlist_id: int):
        await self._conn.execute("DELETE FROM playlist_items WHERE playlist_id=?", (playlist_id,))
        await self._conn.commit()

    # ── Schedules ──
    async def create_schedule(self, user_id, name, source_url, rtmp_url, start_time, end_time, days="daily") -> int:
        now = datetime.utcnow().isoformat()
        cur = await self._conn.execute(
            "INSERT INTO schedules (user_id, name, source_url, rtmp_url, start_time, end_time, days, enabled, created_at) VALUES (?,?,?,?,?,?,?,?,?)",
            (user_id, name, source_url, rtmp_url, start_time, end_time, days, 1, now),
        )
        await self._conn.commit()
        return cur.lastrowid

    async def get_user_schedules(self, user_id: int) -> List[Dict]:
        cur = await self._conn.execute(
            "SELECT * FROM schedules WHERE user_id=? ORDER BY id DESC", (user_id,)
        )
        return [dict(r) for r in await cur.fetchall()]

    async def get_enabled_schedules(self) -> List[Dict]:
        cur = await self._conn.execute("SELECT * FROM schedules WHERE enabled=1")
        return [dict(r) for r in await cur.fetchall()]

    async def update_schedule(self, schedule_id: int, **kwargs):
        allowed = {"name", "source_url", "rtmp_url", "start_time", "end_time", "days", "enabled", "last_run", "stream_id"}
        sets, vals = [], []
        for k, v in kwargs.items():
            if k in allowed:
                sets.append(f"{k}=?")
                vals.append(v)
        if not sets:
            return
        vals.append(schedule_id)
        await self._conn.execute(f"UPDATE schedules SET {', '.join(sets)} WHERE id=?", vals)
        await self._conn.commit()

    async def delete_schedule(self, schedule_id: int, user_id: int) -> bool:
        await self._conn.execute(
            "DELETE FROM schedules WHERE id=? AND user_id=?", (schedule_id, user_id)
        )
        await self._conn.commit()
        return True

    # ── Favorites ──
    async def add_favorite(self, user_id: int, item_type: str, title: str, source_url: str = "", meta: str = "") -> int:
        now = datetime.utcnow().isoformat()
        cur = await self._conn.execute(
            "INSERT INTO favorites (user_id, item_type, title, source_url, meta, created_at) VALUES (?,?,?,?,?,?)",
            (user_id, item_type, title, source_url, meta, now),
        )
        await self._conn.commit()
        return cur.lastrowid

    async def get_favorites(self, user_id: int) -> List[Dict]:
        cur = await self._conn.execute(
            "SELECT * FROM favorites WHERE user_id=? ORDER BY id DESC", (user_id,)
        )
        return [dict(r) for r in await cur.fetchall()]

    async def delete_favorite(self, fav_id: int, user_id: int) -> bool:
        await self._conn.execute(
            "DELETE FROM favorites WHERE id=? AND user_id=?", (fav_id, user_id)
        )
        await self._conn.commit()
        return True

    # ── Audit ──
    async def add_audit(self, user_id: int, action: str, target: str = "", details: str = ""):
        now = datetime.utcnow().isoformat()
        await self._conn.execute(
            "INSERT INTO audit_log (user_id, action, target, details, created_at) VALUES (?,?,?,?,?)",
            (user_id, action, target, details, now),
        )
        await self._conn.commit()

    async def get_audit_logs(self, limit: int = 50, user_id: int = None) -> List[Dict]:
        if user_id:
            cur = await self._conn.execute(
                "SELECT * FROM audit_log WHERE user_id=? ORDER BY id DESC LIMIT ?",
                (user_id, limit),
            )
        else:
            cur = await self._conn.execute(
                "SELECT * FROM audit_log ORDER BY id DESC LIMIT ?", (limit,)
            )
        return [dict(r) for r in await cur.fetchall()]

    # ── User storage preference ──
    async def set_user_storage(self, user_id: int, provider: str, config_json: str = ""):
        now = datetime.utcnow().isoformat()
        await self._conn.execute(
            "INSERT INTO user_storage (user_id, provider, config_json, updated_at) VALUES (?,?,?,?) "
            "ON CONFLICT(user_id) DO UPDATE SET provider=excluded.provider, config_json=excluded.config_json, updated_at=excluded.updated_at",
            (user_id, provider, config_json, now),
        )
        await self._conn.commit()

    async def get_user_storage(self, user_id: int):
        cur = await self._conn.execute("SELECT * FROM user_storage WHERE user_id=?", (user_id,))
        row = await cur.fetchone()
        return dict(row) if row else {"user_id": user_id, "provider": "r2", "config_json": ""}

    async def delete_user_files(self, user_id: int) -> int:
        cur = await self._conn.execute("SELECT COUNT(*) as c FROM files WHERE user_id=?", (user_id,))
        row = await cur.fetchone()
        n = row["c"] if row else 0
        await self._conn.execute("DELETE FROM files WHERE user_id=?", (user_id,))
        await self._conn.commit()
        return n

    async def count_user_streams(self, user_id: int) -> int:
        cur = await self._conn.execute("SELECT COUNT(*) as c FROM streams WHERE user_id=?", (user_id,))
        row = await cur.fetchone()
        return row["c"] if row else 0

    async def count_user_files(self, user_id: int) -> int:
        cur = await self._conn.execute("SELECT COUNT(*) as c FROM files WHERE user_id=?", (user_id,))
        row = await cur.fetchone()
        return row["c"] if row else 0

    async def sum_user_storage(self, user_id: int) -> int:
        cur = await self._conn.execute(
            "SELECT COALESCE(SUM(file_size),0) as s FROM files WHERE user_id=?", (user_id,)
        )
        row = await cur.fetchone()
        return int(row["s"] if row else 0)


db = Database()
