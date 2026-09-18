"""Optional large-file download via Pyrogram when Local Bot API is unavailable.

Requires API_ID + API_HASH + BOT_TOKEN in .env.
Streams to disk in chunks (not full RAM).
"""
from __future__ import annotations
import asyncio
import logging
from pathlib import Path
from typing import Optional, Callable, Tuple

logger = logging.getLogger(__name__)
ROOT = Path(__file__).resolve().parent.parent
TEMP = ROOT / "data" / "tmp"
TEMP.mkdir(parents=True, exist_ok=True)


def is_configured() -> bool:
    try:
        from config import API_ID, API_HASH, BOT_TOKEN
        return bool(API_ID and API_HASH and BOT_TOKEN)
    except Exception:
        return False


async def download_telegram_file(
    file_id: str,
    dest_name: str,
    progress_cb: Optional[Callable[[int, int], None]] = None,
) -> Tuple[Optional[str], str]:
    """
    Download by file_id using Pyrogram bot client.
    Returns (local_path, error).
    """
    if not is_configured():
        return None, "Pyrogram غير مضبوط (API_ID / API_HASH)"
    try:
        from config import API_ID, API_HASH, BOT_TOKEN
        from pyrogram import Client
    except ImportError:
        return None, "ثبّت pyrogram و tgcrypto: pip install pyrogram tgcrypto"

    out = TEMP / dest_name
    try:
        async with Client(
            "stream_bot_dl",
            api_id=API_ID,
            api_hash=API_HASH,
            bot_token=BOT_TOKEN,
            in_memory=True,
            workdir=str(TEMP),
        ) as app:
            # Pyrogram needs a message reference ideally; for file_id-only
            # we use download_media on a reconstructed path if possible.
            # Bot API file_id works with get_file in Local API; Pyrogram
            # prefers message. Fallback: not always possible with PTB file_id.
            path = await app.download_media(
                file_id,
                file_name=str(out),
                progress=lambda c, t: progress_cb(c, t or 0) if progress_cb else None,
            )
            if path and Path(path).exists():
                return str(path), ""
            return None, "فشل تنزيل Pyrogram"
    except Exception as e:
        logger.exception("pyrogram download")
        return None, str(e)[:200]
