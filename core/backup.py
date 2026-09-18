"""Automatic database and config backup — keep last 7 daily copies."""
from __future__ import annotations
import logging
import shutil
import zipfile
from datetime import datetime
from pathlib import Path

logger = logging.getLogger(__name__)

ROOT = Path(__file__).resolve().parent.parent
BACKUP_DIR = ROOT / "backup"
BACKUP_DIR.mkdir(parents=True, exist_ok=True)
KEEP = 7


def run_backup(label: str = "") -> Path:
    """Create a zip backup of DB + key data files."""
    ts = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    name = f"backup_{ts}{('_' + label) if label else ''}.zip"
    out = BACKUP_DIR / name

    targets = [
        ROOT / "data" / "bot.db",
        ROOT / "data" / "library.json",
        ROOT / "data" / "stations.json",
        ROOT / ".env.example",
    ]
    # iptv playlists
    iptv = ROOT / "data" / "iptv"
    if iptv.exists():
        targets.extend(iptv.glob("*.json"))

    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as zf:
        for f in targets:
            if f.exists() and f.is_file():
                zf.write(f, arcname=str(f.relative_to(ROOT)))
    logger.info("Backup created: %s", out.name)
    _rotate()
    return out


def _rotate():
    files = sorted(BACKUP_DIR.glob("backup_*.zip"), key=lambda p: p.stat().st_mtime, reverse=True)
    for old in files[KEEP:]:
        try:
            old.unlink()
            logger.info("Backup rotated out: %s", old.name)
        except Exception as e:
            logger.warning("rotate: %s", e)


def list_backups(limit: int = 10):
    files = sorted(BACKUP_DIR.glob("backup_*.zip"), key=lambda p: p.stat().st_mtime, reverse=True)
    return files[:limit]
