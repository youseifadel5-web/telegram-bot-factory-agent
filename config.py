import os
import logging
from pathlib import Path
from dotenv import load_dotenv

# Load .env from project root (works on KataBump + local)
_env_path = Path(__file__).resolve().parent / ".env"
load_dotenv(_env_path)
load_dotenv()  # also load from cwd if different

logger = logging.getLogger(__name__)

# Telegram — ONE bot only. BOT_TOKEN is the single source of truth.
# TELEGRAM_BOT_TOKEN is accepted ONLY as a fallback alias when BOT_TOKEN is empty.
# If both are set to different values, BOT_TOKEN wins and a warning is logged
# (running two tokens causes 409 Conflict / dual-instance fights).
_bot_primary = (os.getenv("BOT_TOKEN") or "").strip()
_bot_alias = (os.getenv("TELEGRAM_BOT_TOKEN") or "").strip()
if _bot_primary and _bot_alias and _bot_primary != _bot_alias:
    logging.getLogger(__name__).warning(
        "Both BOT_TOKEN and TELEGRAM_BOT_TOKEN are set and differ — "
        "using BOT_TOKEN only. Remove the extra token to avoid conflicts."
    )
BOT_TOKEN = _bot_primary or _bot_alias

def _safe_int(value: str, default: int = 0) -> int:
    try:
        return int(str(value).strip())
    except (TypeError, ValueError):
        return default

ADMIN_ID = _safe_int(os.getenv("ADMIN_ID", "0"), 0)

# AI (optional — never required to start the bot)
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "").strip()
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "").strip()
DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY", "").strip()
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY", "").strip()
XAI_API_KEY = os.getenv("XAI_API_KEY", "").strip() or os.getenv("GROK_API_KEY", "").strip()
GROK_API_KEY = os.getenv("GROK_API_KEY", "").strip() or XAI_API_KEY
# A provider key makes the explicit «يوسف» assistant usable when a hosting
# panel leaves AI_ENABLED unset. Setting AI_ENABLED=false still disables it;
# normal messages are never intercepted unless the assistant is activated.
_ai_enabled_raw = os.getenv("AI_ENABLED")
_ai_has_provider = any((OPENAI_API_KEY, GEMINI_API_KEY, DEEPSEEK_API_KEY, OPENROUTER_API_KEY, XAI_API_KEY))
AI_ENABLED = (
    _ai_enabled_raw.strip().lower() not in ("0", "false", "no", "off")
    if _ai_enabled_raw is not None and _ai_enabled_raw.strip()
    else _ai_has_provider
)
AI_MODE = os.getenv("AI_MODE", "explicit").strip().lower() or "explicit"
AI_TIMEOUT = _safe_int(os.getenv("AI_TIMEOUT", "90"), 90)
AI_MAX_RETRIES = _safe_int(os.getenv("AI_MAX_RETRIES", "3"), 3)
# Preferred provider: openrouter | openai | deepseek | xai
AI_PROVIDER = (os.getenv("AI_PROVIDER", "openrouter") or "openrouter").strip().lower()
# Model id (OpenRouter style e.g. openai/gpt-4o-mini, anthropic/claude-3.5-sonnet, google/gemini-2.0-flash-001)
AI_MODEL = (
    os.getenv("AI_MODEL", "").strip()
    or os.getenv("OPENROUTER_MODEL", "").strip()
    or "openai/gpt-4o-mini"
)

# Oscar / HLS / concurrency (defaults safe if unset)
OSCAR_TIMEOUT = _safe_int(os.getenv("OSCAR_TIMEOUT", "25"), 25)
OSCAR_RETRIES = _safe_int(os.getenv("OSCAR_RETRIES", "3"), 3)
OSCAR_CACHE_TTL = _safe_int(os.getenv("OSCAR_CACHE_TTL", "300"), 300)
HLS_TIMEOUT = _safe_int(os.getenv("HLS_TIMEOUT", "15"), 15)
HLS_RETRIES = _safe_int(os.getenv("HLS_RETRIES", "2"), 2)
MAX_STREAMS = _safe_int(os.getenv("MAX_STREAMS", "4"), 4)
MAX_UPLOADS = _safe_int(os.getenv("MAX_UPLOADS", "3"), 3)
MAX_PROBES = _safe_int(os.getenv("MAX_PROBES", "5"), 5)
FFMPEG_RECONNECT = os.getenv("FFMPEG_RECONNECT", "true").strip().lower() in ("1", "true", "yes")
FFMPEG_TIMEOUT = _safe_int(os.getenv("FFMPEG_TIMEOUT", "15000000"), 15000000)
FFMPEG_RETRY = _safe_int(os.getenv("FFMPEG_RETRY", "3"), 3)

# Cloudflare R2
ACCOUNT_ID = os.getenv("ACCOUNT_ID", "").strip()
R2_ACCESS_KEY_ID = os.getenv("R2_ACCESS_KEY_ID", "").strip()
R2_SECRET_ACCESS_KEY = os.getenv("R2_SECRET_ACCESS_KEY", "").strip()
R2_ENDPOINT = os.getenv("R2_ENDPOINT", "").strip()
R2_BUCKET_NAME = os.getenv("R2_BUCKET_NAME", "").strip()
CF_API_TOKEN = os.getenv("CF_API_TOKEN", "").strip()

# Paths
_BASE = Path(__file__).resolve().parent
DATABASE_PATH = os.getenv("DATABASE_PATH", str(_BASE / "data" / "bot.db"))
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").strip() or "INFO"

# Streaming
FFMPEG_PATH = os.getenv("FFMPEG_PATH", "ffmpeg").strip() or "ffmpeg"
MAX_STREAM_DURATION = 24 * 3600  # 24 hours max

# --- Large file downloads ---------------------------------------------------
# Telegram's regular Bot API (api.telegram.org) hard-caps file DOWNLOADS
# (bot.get_file) at 20MB no matter what — this is a Telegram platform limit,
# not something any bot code can bypass. This is the real cause of the
# "File is too big" error.
#
# The supported fix is to run a self-hosted Local Bot API Server
# (https://github.com/tdlib/telegram-bot-api). Pointed at your own bot token,
# it raises the download limit to 2000 MB (2GB) and uploads become effectively
# limited only by disk space. Set LOCAL_BOT_API_URL below once it's running
# (see README section "Large files / Local Bot API Server").
# Aliases: TELEGRAM_LOCAL_API / TELEGRAM_API_URL (KataBump friendly)
_local_flag = os.getenv("TELEGRAM_LOCAL_API", "").strip().lower() in ("1", "true", "yes")
LOCAL_BOT_API_URL = (
    os.getenv("LOCAL_BOT_API_URL", "").strip().rstrip("/")
    or os.getenv("TELEGRAM_API_URL", "").strip().rstrip("/")
)
if _local_flag and not LOCAL_BOT_API_URL:
    LOCAL_BOT_API_URL = "http://localhost:8081"
LOCAL_BOT_API_ENABLED = bool(LOCAL_BOT_API_URL) or _local_flag

# Optional Pyrogram (userbot) for large files when Local API unavailable
API_ID = _safe_int(os.getenv("API_ID", "0"), 0)
API_HASH = os.getenv("API_HASH", "").strip()

# If the local telegram-bot-api server is run with --local, get_file() returns
# an absolute path on THIS disk instead of an HTTP URL — much faster since the
# bot reads the file directly instead of downloading it a second time.
LOCAL_BOT_API_LOCAL_MODE = os.getenv("LOCAL_BOT_API_LOCAL_MODE", "false").strip().lower() in ("1", "true", "yes")

# Official cloud Bot API download ceiling (bytes) — used when no local server.
TELEGRAM_CLOUD_DOWNLOAD_LIMIT = 20 * 1024 * 1024
# Local Bot API server download ceiling (bytes) — default for the official
# telegram-bot-api binary without --local; with --local file access is
# effectively unlimited by disk space, so treat this as a soft display cap.
LOCAL_BOT_API_DOWNLOAD_LIMIT = 2000 * 1024 * 1024

# Smart video archive (HLS → MP4 → Telegram channel, no permanent local storage)
def _safe_int_opt(value: str, default: int = 0) -> int:
    try:
        return int(str(value).strip())
    except (TypeError, ValueError):
        return default

ARCHIVE_CHANNEL_ID = _safe_int_opt(os.getenv("ARCHIVE_CHANNEL_ID", "0"), 0)
AUTO_ARCHIVE_ON_STOP = os.getenv("AUTO_ARCHIVE_ON_STOP", "false").strip().lower() in ("1", "true", "yes")
# Max duration to archive (seconds). Longer = likely live, skip auto.
ARCHIVE_MAX_DURATION_SEC = _safe_int_opt(os.getenv("ARCHIVE_MAX_DURATION_SEC", "14400"), 14400)  # 4h
# Min duration to consider a "complete video" (skip tiny clips)
ARCHIVE_MIN_DURATION_SEC = _safe_int_opt(os.getenv("ARCHIVE_MIN_DURATION_SEC", "60"), 60)



def validate_config():
    """
    Soft validation:
    - BOT_TOKEN is mandatory (bot cannot start without it)
    - Other vars: warn only so the bot still starts on limited hosts (KataBump etc.)
    """
    if not BOT_TOKEN:
        raise ValueError(
            "BOT_TOKEN is missing. Set it in .env or in the panel Environment Variables."
        )

    if ADMIN_ID == 0:
        logger.warning("ADMIN_ID is not set or invalid — admin panel will be disabled.")

    optional = [
        ("R2_ACCESS_KEY_ID", R2_ACCESS_KEY_ID),
        ("R2_SECRET_ACCESS_KEY", R2_SECRET_ACCESS_KEY),
        ("R2_ENDPOINT", R2_ENDPOINT),
        ("R2_BUCKET_NAME", R2_BUCKET_NAME),
    ]
    missing = [name for name, val in optional if not val]
    if missing:
        logger.warning(
            "Missing R2 variables: %s — file upload to R2 will not work until set.",
            ", ".join(missing),
        )
