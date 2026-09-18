"""Quality profiles for Telegram RTMPS output.

Dependency-free — safe to import from handlers and stream engines.
Profiles match the classic bot + stable presets for 24/7 RTMP.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Optional


@dataclass(frozen=True)
class QualityProfile:
    name: str
    width: int
    height: int
    video_bitrate: str
    audio_bitrate: str


PROFILES: Dict[str, QualityProfile] = {
    # Legacy names (saved streams / old callbacks)
    "144p": QualityProfile("144p", 256, 144, "250k", "64k"),
    "240p": QualityProfile("240p", 426, 240, "400k", "64k"),
    "360p": QualityProfile("360p", 640, 360, "700k", "96k"),
    "480p": QualityProfile("480p", 854, 480, "1200k", "128k"),
    "720p": QualityProfile("720p", 1280, 720, "2500k", "128k"),
    "1080p": QualityProfile("1080p", 1920, 1080, "4500k", "192k"),
    # User-facing presets
    "360p_stable": QualityProfile("360p_stable", 640, 360, "700k", "96k"),
    "480p_balanced": QualityProfile("480p_balanced", 854, 480, "1200k", "128k"),
    "720p_hd": QualityProfile("720p_hd", 1280, 720, "2500k", "128k"),
}

QUALITY_LABELS = {
    "360p_stable": "🟢 360p Stable",
    "480p_balanced": "🟡 480p Balanced",
    "720p_hd": "🔵 720p HD",
    "360p": "🟢 360p",
    "480p": "🟡 480p",
    "720p": "🔵 720p",
    "auto": "⚙️ تلقائي",
}


def get_quality(name: str, default: str = "360p_stable") -> QualityProfile:
    key = str(name or "").lower().strip()
    if key in ("auto", ""):
        return PROFILES[default]
    return PROFILES.get(key, PROFILES[default])


def choose_quality(height: Optional[int], default: str = "360p_stable") -> QualityProfile:
    """Highest profile not exceeding source height."""
    if not height or height <= 0:
        return get_quality(default)
    candidates = [p for p in PROFILES.values() if p.height <= int(height)]
    # Prefer the user-facing trio when heights match
    preferred = ("360p_stable", "480p_balanced", "720p_hd", "360p", "480p", "720p")
    by_name = {p.name: p for p in candidates}
    for name in preferred:
        if name in by_name and by_name[name].height <= int(height):
            # pick the best among preferred that fits
            pass
    return max(candidates, key=lambda p: p.height) if candidates else PROFILES["144p"]


def all_qualities() -> tuple:
    return tuple(PROFILES.values())


def label_for(name: Optional[str]) -> str:
    if not name:
        return QUALITY_LABELS["auto"]
    return QUALITY_LABELS.get(str(name).lower(), str(name))
