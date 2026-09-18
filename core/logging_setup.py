"""Professional logging with rotation — bot / stream / error / security."""
import logging
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
LOG_DIR = ROOT / "logs"
LOG_DIR.mkdir(parents=True, exist_ok=True)

_FMT = logging.Formatter("%(asctime)s | %(levelname)-7s | %(name)s | %(message)s")


def _file_handler(name: str, level=logging.INFO) -> RotatingFileHandler:
    path = LOG_DIR / name
    h = RotatingFileHandler(path, maxBytes=5 * 1024 * 1024, backupCount=5, encoding="utf-8")
    h.setLevel(level)
    h.setFormatter(_FMT)
    return h


def setup_logging(level: str = "INFO"):
    root = logging.getLogger()
    root.setLevel(getattr(logging, level.upper(), logging.INFO))

    # clear existing handlers to avoid duplicates on reload
    root.handlers.clear()

    console = logging.StreamHandler(sys.stdout)
    console.setFormatter(_FMT)
    root.addHandler(console)

    root.addHandler(_file_handler("bot.log", logging.INFO))
    root.addHandler(_file_handler("error.log", logging.ERROR))

    # dedicated loggers
    stream_log = logging.getLogger("stream")
    stream_log.addHandler(_file_handler("stream.log", logging.INFO))
    stream_log.propagate = True

    security_log = logging.getLogger("security")
    security_log.addHandler(_file_handler("security.log", logging.INFO))
    security_log.propagate = True

    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("telegram").setLevel(logging.WARNING)
    return root
