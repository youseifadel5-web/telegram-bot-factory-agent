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
    assert "-re" not in cmd  # HLS live input must not be throttled


def test_build_audio_only_is_genuine_audio():
    cmd = sm.build_ffmpeg_cmd(
        "ffmpeg",
        "https://radio.example.com/stream.mp3",
        "rtmps://example/live/KEY",
        with_video=False,
    )
    assert "lavfi" not in cmd
    assert "color=c=black" not in " ".join(map(str, cmd))
    assert "-vn" in cmd
    assert "-c:a" in cmd and "aac" in cmd
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


def test_vod_keeps_re():
    cmd = sm.build_ffmpeg_cmd(
        "ffmpeg", "https://cdn.example.com/movie.mp4", "rtmps://example/live/KEY",
        with_video=True, has_video=True, has_audio=True, source_type="MP4",
    )
    assert "-re" in cmd


def test_hls_with_misleading_extension_uses_hls_demuxer():
    cmd = sm.build_ffmpeg_cmd(
        "ffmpeg", "https://cdn.example.com/live.css", "rtmps://example/live/KEY",
        with_video=True, has_video=True, has_audio=True, source_type="M3U8 / HLS",
    )
    assert "-f" in cmd and "hls" in cmd


# ── تماشياً مع كود FFmpeg المجرّب (سكربت المستخدم) ────────────────────────────

def test_cmd_matches_proven_script_values():
    """قيم السكربت المجرّب: thread_queue 4096، analyze/probe 20M، صوت 44100، g=50."""
    cmd = sm.build_ffmpeg_cmd(
        "ffmpeg",
        "https://cdn.example.com/live/index.m3u8",
        "rtmps://dc4-1.rtmp.t.me/s/KEY",
        with_video=True,
        media_kind="video",
        has_audio=True,
        has_video=True,
        audio_bitrate="96k",
        volume=1.0,
    )
    joined = " ".join(map(str, cmd))
    assert "-thread_queue_size 4096" in joined
    assert "-analyzeduration 20M" in joined
    assert "-probesize 20M" in joined
    assert "-ar 44100" in joined
    assert "-g 50" in joined
    assert "-flvflags no_duration_filesize" in joined
    assert "-preset veryfast" in joined and "-tune zerolatency" in joined
    assert "-pix_fmt yuv420p" in joined


def test_audio_only_matches_proven_script():
    cmd = sm.build_ffmpeg_cmd(
        "ffmpeg",
        "https://radio.example.com/stream.mp3",
        "rtmps://example/live/KEY",
        with_video=False,
        media_kind="audio",
        has_audio=True,
        audio_bitrate="128k",
    )
    joined = " ".join(map(str, cmd))
    assert "-ar 44100" in joined and "-ac 2" in joined
    assert "-b:a 128k" in joined


def test_quality_profile_script_parity():
    from services.quality_manager import get_quality, resolve_for_source
    p = get_quality("360p_stable")
    assert p.video_bitrate == "700k"
    assert p.maxrate_v == "700k"      # maxrate = bitrate (بلا هامش)
    assert p.bufsize_v == "1400k"     # 2x
    assert p.audio_bitrate == "96k"
    a = resolve_for_source("auto", 1080, media_kind="audio")
    assert a.audio_bitrate == "128k"  # صوت فقط 128k


# ── الوضع الآمن: أمر السكربت المجرّب حرفياً ──────────────────────────────────

def test_safe_mode_video_matches_proven_script():
    cmd = sm.build_ffmpeg_cmd(
        "ffmpeg", "https://cdn.example.com/live/index.m3u8",
        "rtmps://dc4-1.rtmp.t.me/s/KEY",
        with_video=True, media_kind="video", has_audio=True, has_video=True,
        source_type="M3U8 / HLS", safe_mode=True,
    )
    j = " ".join(map(str, cmd))
    # قيم السكربت المجرّب حرفياً
    assert "-thread_queue_size 4096" in j
    assert "-map 0:v:0?" in j and "-map 0:a:0?" in j
    assert "-c:v libx264 -preset veryfast -tune zerolatency" in j
    assert "-pix_fmt yuv420p" in j
    assert "-r 25 -g 50" in j
    assert "-b:v 700k -maxrate 700k -bufsize 700k" in j
    assert "-c:a aac -b:a 96k -ar 44100 -ac 2" in j
    assert "-flvflags no_duration_filesize" in j
    assert "-user_agent Mozilla/5.0" in j
    # لا خيارات متقدمة قد يرفضها بناء FFmpeg على السيرفر
    for risky in ("-f hls", "-err_detect", "-max_interleave_delta", "-reconnect",
                  "-fps_mode", "-vsync", "-allowed_extensions", "-live_start_index",
                  "-max_muxing_queue_size", "-keyint_min", "-sc_threshold"):
        assert risky not in j, risky


def test_safe_mode_audio_matches_proven_script():
    cmd = sm.build_ffmpeg_cmd(
        "ffmpeg", "https://radio.example.com/stream.mp3",
        "rtmps://example/live/KEY",
        with_video=False, media_kind="audio", has_audio=True, safe_mode=True,
    )
    j = " ".join(map(str, cmd))
    assert "-map 0:a:0?" in j and "-vn" in j
    assert "-c:a aac -b:a 128k -ar 44100 -ac 2" in j
    assert "-flvflags no_duration_filesize" in j
    assert "-f hls" not in j and "-err_detect" not in j


def test_safe_mode_never_forces_hls_demuxer():
    """حتى لو الرابط m3u8، الوضع الآمن يترك FFmpeg يكتشف التنسيق بنفسه."""
    cmd = sm.build_ffmpeg_cmd(
        "ffmpeg", "https://cdn.example.com/a/b.m3u8?x=1",
        "rtmps://e/live/K", with_video=True, media_kind="video",
        has_audio=True, has_video=True, source_type="M3U8 / HLS", safe_mode=True,
    )
    assert "-f" in cmd and "hls" not in cmd[:cmd.index("-i")]


def test_classifier_output_option_not_blamed_on_version():
    import services.stream as s
    mgr = object.__new__(s.StreamManager)
    msg = mgr._classify_ffmpeg_error("Error opening output files: Invalid argument")
    assert "خيار" in msg and "إصدار FFmpeg لا يدعم" not in msg
    msg2 = mgr._classify_ffmpeg_error(
        "Failed to set value '0:a:0' for option 'map': Invalid argument")
    assert "الإخراج" in msg2


def test_allowed_extensions_for_disguised_hls():
    """HLS متنكّر بامتداد .css (أو عبر الريلاي) يجب أن يحصل على allowed_extensions."""
    cmd = sm.build_ffmpeg_cmd(
        "ffmpeg",
        "https://still-dust.workers.dev/assets/res2/java2/19.css?x=%2Fhls%2F",
        "rtmps://dc4-1.rtmp.t.me/s/KEY",
        with_video=True, media_kind="video", has_audio=True, has_video=True,
        source_type="M3U8 / HLS",
    )
    j = " ".join(map(str, cmd))
    assert "-allowed_extensions ALL" in j
    assert "-f hls" in j
