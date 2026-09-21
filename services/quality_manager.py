"""Quality profiles for Telegram RTMPS output — the SINGLE quality authority.

All quality/FFmpeg encoding parameters come from here. Handlers never repeat
FFmpeg arguments. Legacy profile names (144p..1080p) remain valid so old
saved streams keep working (backward compatible).
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
    maxrate: str = ""
    bufsize: str = ""

    @property
    def maxrate_v(self) -> str:
        return self.maxrate or _bump(self.video_bitrate, 1.2)

    @property
    def bufsize_v(self) -> str:
        return self.bufsize or _bump(self.video_bitrate, 2.0)


def _bump(bitrate: str, factor: float) -> str:
    try:
        return f"{int(int(bitrate.replace('k', '')) * factor)}k"
    except Exception:
        return bitrate


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
    "auto": QualityProfile("auto", 1280, 720, "1000k", "128k"),
}

QUALITY_LABELS = {
    "360p_stable": "🟢 360p Stable",
    "480p_balanced": "🟡 480p Balanced",
    "720p_hd": "🔵 720p HD",
    "360p": "🟢 360p",
    "480p": "🟡 480p",
    "720p": "🔵 720p",
    "1080p": "🟣 1080p",
    "auto": "⚙️ تلقائي",
}

# Names exposed in the quality picker (new UI) — legacy names stay resolvable
USER_QUALITY_CHOICES = ("auto", "360p_stable", "480p_balanced", "720p_hd", "1080p")


def get_quality(name: str, default: str = "360p_stable") -> QualityProfile:
    key = str(name or "").lower().strip()
    if key in ("auto", ""):
        return PROFILES[default]
    return PROFILES.get(key, PROFILES[default])


def choose_quality(height: Optional[int], default: str = "360p_stable") -> QualityProfile:
    """Smart selection: never upscale beyond the source height.

    - source 360p → 360p (no blind upscale)
    - source 720p → 720p
    - source 1080p → 720p is returned only when the caller passes
      ``cap_720p=True`` via :func:`choose_quality_capped`; by default the best
      fitting profile not exceeding the source is chosen.
    """
    if not height or int(height) <= 0:
        return get_quality(default)
    candidates = [p for p in PROFILES.values() if p.name not in ("auto",) and p.height <= int(height)]
    if not candidates:
        return PROFILES["144p"]
    preferred_order = ("360p_stable", "480p_balanced", "720p_hd", "360p", "480p", "720p", "1080p")
    by_height = {p.height: p for p in candidates}
    for h in sorted(by_height, reverse=True):
        return by_height[h]
    return max(candidates, key=lambda p: p.height)


def choose_quality_capped(height: Optional[int], cap: int = 720) -> QualityProfile:
    """Auto with CPU cap — e.g. a 1080p source gets 720p to save CPU."""
    prof = choose_quality(height)
    if prof.height > cap:
        return PROFILES.get(f"{cap}p", PROFILES["720p_hd"])
    return prof


def resolve_for_source(
    requested: Optional[str],
    source_height: Optional[int],
    media_kind: str = "video",
    default: str = "360p_stable",
) -> QualityProfile:
    """Deterministic final profile for a stream.

    - Audio sources get an audio-only profile (video bitrate ignored later).
    - 'auto' adapts to source height without upscaling.
    - Explicit names are honored when the source can support them.
    """
    req = str(requested or "auto").lower().strip()
    if media_kind == "audio":
        return QualityProfile("audio_only", 0, 0, "0k", get_quality(req, default).audio_bitrate)
    if req in ("", "auto"):
        return choose_quality_capped(source_height)
    prof = PROFILES.get(req)
    if prof is None:
        return choose_quality_capped(source_height)
    if source_height and prof.height > int(source_height):
        # requested higher than source → pick best fitting instead of upscaling
        return choose_quality(int(source_height))
    return prof


def all_qualities() -> tuple:
    return tuple(PROFILES.values())


def label_for(name: Optional[str]) -> str:
    if not name:
        return QUALITY_LABELS["auto"]
    key = str(name).lower().strip()
    if key in QUALITY_LABELS:
        return QUALITY_LABELS[key]
    if key.startswith("audio"):
        return "🎵 صوت فقط"
    return str(name)
