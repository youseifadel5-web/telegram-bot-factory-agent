"""Canonical SQLite schema used by Database._create_tables."""

SCHEMA_SQL = """
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
        """
