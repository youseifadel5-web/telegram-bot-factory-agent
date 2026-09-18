"""Unit tests for FFmpeg command builder (no real ffmpeg required for structure)."""
import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

# Stub option/encoder probes so tests don't need a real binary
import services.stream as sm

sm._ffmpeg_supports_option = lambda ffmpeg, option: True  # type: ignore
sm._pick_video_encoder = lambda ffmpeg: "libx264"  # type: ignore
sm._ffmpeg_help_text = lambda ffmpeg: ""  # type: ignore


def test_build_video_cmd_contains_essentials():
    cmd = sm.build_ffmpeg_cmd(
        "ffmpeg",
        "https://cdn.example.com/live/index.m3u8",
        "rtmps://dc4-1.rtmp.t.me/s/KEY",
        with_video=True,
        audio_bitrate="128k",
        volume=1.0,
    )
    assert cmd[0] == "ffmpeg"
    assert "-i" in cmd
    assert "https://cdn.example.com/live/index.m3u8" in cmd
    assert "-f" in cmd and "flv" in cmd
    assert "rtmps://dc4-1.rtmp.t.me/s/KEY" in cmd
    assert "-c:v" in cmd and "libx264" in cmd
    assert "-c:a" in cmd and "aac" in cmd
    assert "-progress" in cmd
    assert "-re" in cmd


def test_build_audio_only_has_black_video():
    cmd = sm.build_ffmpeg_cmd(
        "ffmpeg",
        "https://radio.example.com/stream.mp3",
        "rtmps://example/live/KEY",
        with_video=False,
    )
    assert "lavfi" in cmd
    assert any("color=c=black" in str(x) for x in cmd)
    # -shortest intentionally omitted: it kills live radio on brief stalls
    assert "-shortest" not in cmd


def test_http_command_omits_incompatible_protocol_options():
    cmd = sm.build_ffmpeg_cmd(
        "ffmpeg",
        "https://qurango.net/radio/ahmad_alajmy",
        "rtmps://example/live/KEY",
        with_video=False,
    )
    assert "-http_seekable" not in cmd
    assert "-http_persistent" not in cmd


def test_validate_rejects_private_url():
    try:
        sm._validate_source_url("http://127.0.0.1/stream.m3u8")
        raise AssertionError("expected SSRF block")
    except ValueError:
        pass


def test_validate_strips_fragment():
    u = sm._validate_source_url("https://cdn.example.com/a.m3u8#t=10")
    assert "#t=" not in u


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            print("OK", name)
    print("all ffmpeg cmd tests passed")
