"""Stations system: named channels defined in data/stations.json, each with a
primary source and an optional list of backup (failover) sources.

data/stations.json schema:
{
  "stations": [
    {
      "id": "quran_1",
      "name": "قناة القرآن الكريم 1",
      "rtmp_url": "rtmp://.../live",       # optional default RTMP target
      "with_video": false,
      "sources": [
        "https://primary-stream-url/stream.mp3",
        "https://backup-1-url/stream.mp3",
        "https://backup-2-url/stream.mp3"
      ]
    }
  ]
}

The first entry in "sources" is the primary; every entry after it is a backup
that StreamManager will automatically fail over to if the primary keeps
dying (see MAX_FAILS_BEFORE_FAILOVER in services/stream.py).
"""
import json
import logging
import threading
from pathlib import Path
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)

ROOT = Path(__file__).resolve().parent.parent
STATIONS_FILE = ROOT / "data" / "stations.json"

_lock = threading.Lock()

_DEFAULT = {"stations": []}


def _ensure_file():
    STATIONS_FILE.parent.mkdir(parents=True, exist_ok=True)
    if not STATIONS_FILE.exists():
        STATIONS_FILE.write_text(
            json.dumps(_DEFAULT, ensure_ascii=False, indent=2), encoding="utf-8"
        )


def load_stations() -> List[Dict]:
    _ensure_file()
    try:
        with _lock:
            data = json.loads(STATIONS_FILE.read_text(encoding="utf-8"))
        stations = data.get("stations", [])
        # normalize
        out = []
        for s in stations:
            sources = s.get("sources") or ([s["source"]] if s.get("source") else [])
            sources = [u for u in sources if u]
            if not sources:
                continue
            out.append({
                "id": str(s.get("id") or s.get("name") or f"station_{len(out)+1}"),
                "name": s.get("name") or s.get("id") or "محطة",
                "rtmp_url": s.get("rtmp_url") or "",
                "with_video": bool(s.get("with_video", False)),
                "sources": sources,
            })
        return out
    except Exception as e:
        logger.error("Failed to load stations.json: %s", e)
        return []


def get_station(station_id: str) -> Optional[Dict]:
    for s in load_stations():
        if s["id"] == station_id:
            return s
    return None


def save_stations(stations: List[Dict]):
    _ensure_file()
    with _lock:
        STATIONS_FILE.write_text(
            json.dumps({"stations": stations}, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )


def add_station(station_id: str, name: str, sources: List[str],
                 rtmp_url: str = "", with_video: bool = False) -> bool:
    stations = load_stations()
    if any(s["id"] == station_id for s in stations):
        return False
    stations.append({
        "id": station_id, "name": name, "sources": sources,
        "rtmp_url": rtmp_url, "with_video": with_video,
    })
    save_stations(stations)
    return True


def remove_station(station_id: str) -> bool:
    stations = load_stations()
    new_stations = [s for s in stations if s["id"] != station_id]
    if len(new_stations) == len(stations):
        return False
    save_stations(new_stations)
    return True
