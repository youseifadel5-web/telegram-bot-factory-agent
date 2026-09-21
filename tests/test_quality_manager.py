"""Tests for quality_manager: central profiles, smart auto, no blind upscale."""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from services.quality_manager import (
    PROFILES, get_quality, choose_quality, choose_quality_capped,
    resolve_for_source, label_for, USER_QUALITY_CHOICES,
)


def test_profiles_exist():
    for name in ("360p_stable", "480p_balanced", "720p_hd", "auto"):
        assert name in PROFILES
    # legacy names still resolvable (backward compat)
    for name in ("144p", "240p", "360p", "480p", "720p", "1080p"):
        assert name in PROFILES


def test_auto_does_not_upscale_360p_source():
    prof = resolve_for_source("auto", 360, "video")
    assert prof.height <= 360


def test_auto_uses_720p_for_720p_source():
    prof = resolve_for_source("auto", 720, "video")
    assert prof.height == 720


def test_auto_caps_1080p_source_to_720p():
    prof = resolve_for_source("auto", 1080, "video")
    assert prof.height <= 720


def test_explicit_quality_honored_when_supported():
    prof = resolve_for_source("720p_hd", 1080, "video")
    assert prof.height == 720


def test_explicit_quality_above_source_falls_back():
    prof = resolve_for_source("1080p", 480, "video")
    assert prof.height <= 480


def test_audio_source_never_gets_video_profile():
    prof = resolve_for_source("720p", None, "audio")
    assert prof.name == "audio_only"
    assert prof.audio_bitrate == "128k"


def test_unknown_quality_falls_back_safely():
    prof = resolve_for_source("nonexistent_thing", 720, "video")
    assert prof.name in PROFILES


def test_labels():
    assert label_for("auto") == "⚙️ تلقائي"
    assert label_for(None) == "⚙️ تلقائي"
    assert label_for("audio_only") == "🎵 صوت فقط"


def test_user_choices_are_resolvable():
    for name in USER_QUALITY_CHOICES:
        assert name in PROFILES


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            print("OK", name)
    print("all quality_manager tests passed")
