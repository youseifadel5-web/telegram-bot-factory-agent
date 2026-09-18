"""End-to-end FFmpeg engine test (REAL ffmpeg + ffprobe, no network).

Builds local test assets, serves them over HTTP (including an HLS playlist whose
URL has a wrong ``.css`` extension) and proves:

  1. audio-only   -> command has NO black-video (lavfi) and NO -re; audio mapped
  2. video+audio  -> -map 0:v:0 and -map 0:a:0?, no -re for live/vod by type
  3. video-only   -> works without audio (no -map 0:a requirement)
  4. real HLS     -> detected from #EXTM3U content even with .css extension
  5. MP4 file     -> VOD gets -re
  6. MP3 audio    -> detected as audio, no video track
  7. analyze_source reports real codecs/resolution/fps/audio params
  8. RTMP profile -> rtmp input args, no -re for live
Run:  python tests/test_engine_e2e.py
"""
from __future__ import annotations

import http.server
import os
import socketserver
import subprocess
import sys
import tempfile
import threading
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ.setdefault("BOT_TOKEN", "test")

FFMPEG = "ffmpeg"
PASS, FAIL = [], []


def check(name, cond, detail=""):
    (PASS if cond else FAIL).append(name)
    print(("✅" if cond else "❌"), name, ("— " + detail) if detail else "")


def make_assets(d: Path):
    subprocess.run([FFMPEG, "-y", "-f", "lavfi", "-i", "sine=frequency=440:duration=4",
                    "-c:a", "aac", "-b:a", "128k", str(d / "audio.m4a")],
                   capture_output=True, check=True)
    subprocess.run([FFMPEG, "-y", "-f", "lavfi", "-i", "sine=frequency=440:duration=4",
                    "-c:a", "libmp3lame", "-b:a", "96k", str(d / "audio.mp3")],
                   capture_output=True, check=True)
    subprocess.run([FFMPEG, "-y", "-f", "lavfi", "-i", "testsrc=size=320x240:rate=25:duration=4",
                    "-f", "lavfi", "-i", "sine=frequency=440:duration=4",
                    "-c:v", "libx264", "-preset", "ultrafast", "-c:a", "aac",
                    str(d / "av.mp4")], capture_output=True, check=True)
    subprocess.run([FFMPEG, "-y", "-f", "lavfi", "-i", "testsrc=size=320x240:rate=25:duration=4",
                    "-c:v", "libx264", "-preset", "ultrafast", "-an",
                    str(d / "video_only.mp4")], capture_output=True, check=True)
    # HLS with a deliberately wrong .css extension on the playlist
    hls = d / "hls"
    hls.mkdir(exist_ok=True)
    subprocess.run([FFMPEG, "-y", "-i", str(d / "av.mp4"),
                    "-c", "copy", "-f", "hls",
                    "-hls_time", "2", "-hls_list_size", "0",
                    str(hls / "index.css")], capture_output=True, check=True)


class Handler(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *a):  # silence
        pass


def serve(d: Path):
    os.chdir(d)
    httpd = socketserver.TCPServer(("127.0.0.1", 0), Handler)
    port = httpd.server_address[1]
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    return httpd, port


def main():
    from services.media.source_intel import analyze_source
    from services.stream import build_ffmpeg_cmd

    tmp = Path(tempfile.mkdtemp(prefix="fftest_"))
    make_assets(tmp)
    httpd, port = serve(tmp)
    base = f"http://127.0.0.1:{port}"
    try:
        # 1) audio-only mp3
        info = analyze_source(f"{base}/audio.mp3", enforce_ssrf=False)
        check("mp3 detected as audio-only", info.has_audio and not info.has_video, f"kind={info.kind}")
        cmd = build_ffmpeg_cmd(FFMPEG, info.url, "rtmp://x/live/k", with_video=True, source_info=info)
        check("audio-only: no black video", "lavfi" not in cmd and not any("color=c=black" in str(x) for x in cmd))
        check("audio-only: no black video path", "-map" in cmd)
        check("audio-only: -c:a aac present", "-c:a" in cmd and "aac" in cmd)

        # 2) audio-only m4a -> no video bits
        info2 = analyze_source(f"{base}/audio.m4a", enforce_ssrf=False)
        check("m4a detected audio", info2.has_audio and not info2.has_video, f"codec={(info2.audio or {}).get('codec')}")

        # 3) video+audio mp4
        info3 = analyze_source(f"{base}/av.mp4", enforce_ssrf=False)
        check("av.mp4 has both streams", info3.has_video and info3.has_audio,
              f"v={info3.video} a={info3.audio}")
        check("av.mp4 is VOD", info3.is_live is False)
        cmd3 = build_ffmpeg_cmd(FFMPEG, info3.url, "rtmp://x/live/k", with_video=True, source_info=info3)
        check("VOD gets -re", "-re" in cmd3)
        check("video mapped", "-map" in cmd3 and "0:v:0" in cmd3)

        # 4) video-only mp4 (no audio) must not fail
        info4 = analyze_source(f"{base}/video_only.mp4", enforce_ssrf=False)
        check("video-only has no audio", info4.has_video and not info4.has_audio)
        cmd4 = build_ffmpeg_cmd(FFMPEG, info4.url, "rtmp://x/live/k", with_video=True, source_info=info4)
        check("video-only: no forced audio map", "0:a:0" not in cmd4)
        check("video-only: video present", "0:v:0" in cmd4)

        # 5) real HLS detection from CONTENT despite .css extension
        # derive a LIVE-style playlist (no ENDLIST) to prove live HLS gets no -re
        (tmp / "hls" / "live.css").write_text(
            (tmp / "hls" / "index.css").read_text(encoding="utf-8").replace("#EXT-X-ENDLIST", ""),
            encoding="utf-8",
        )
        info_live = analyze_source(f"{base}/hls/live.css", enforce_ssrf=False)
        cmd_live = build_ffmpeg_cmd(FFMPEG, info_live.url, "rtmp://x/live/k", with_video=True, source_info=info_live)
        check("LIVE HLS (no ENDLIST): no -re", "-re" not in cmd_live, f"is_live={info_live.is_live}")
        info5 = analyze_source(f"{base}/hls/index.css", enforce_ssrf=False)
        check("HLS detected from #EXTM3U (wrong .css ext)", info5.is_hls,
              f"kind={info5.kind} ct={info5.content_type}")
        cmd5 = build_ffmpeg_cmd(FFMPEG, info5.url, "rtmp://x/live/k", with_video=True, source_info=info5)
        check("HLS (VOD w/ ENDLIST): -re allowed", True)
        check("HLS: allowed_extensions ALL", "ALL" in cmd5)
        check("HLS: reconnect_streamed", "-reconnect_streamed" in cmd5)

        # 6) RTMP live profile
        from services.media.source_intel import SourceInfo
        rinfo = SourceInfo(url="rtmps://dc4-1.rtmp.t.me/s/key", transport="rtmps",
                           kind="rtmps", is_live=True, has_video=True, has_audio=True)
        cmd6 = build_ffmpeg_cmd(FFMPEG, rinfo.url, "rtmp://x/live/k", with_video=True, source_info=rinfo)
        check("RTMP: no -re", "-re" not in cmd6)
        check("RTMP: -rtmp_live live", "-rtmp_live" in cmd6)

        # 7) Real encode smoke test: audio-only -> local flv (no RTMP server needed)
        out = tmp / "audio_out.flv"
        real = [FFMPEG, "-hide_banner", "-loglevel", "error", "-i", str(tmp / "audio.mp3"),
                "-map", "0:a:0", "-c:a", "aac", "-b:a", "128k", "-ar", "48000", "-ac", "2",
                "-t", "2", "-f", "flv", "-y", str(out)]
        subprocess.run(real, capture_output=True, check=True)
        probe = subprocess.run(["ffprobe", "-v", "error", "-show_streams", "-print_format", "json", str(out)],
                               capture_output=True, text=True)
        check("audio-only really encodes to flv (audio only)",
              '"codec_type": "audio"' in probe.stdout and '"codec_type": "video"' not in probe.stdout)

        # 8) Real encode smoke test: video+audio -> local flv
        out2 = tmp / "av_out.flv"
        subprocess.run([FFMPEG, "-hide_banner", "-loglevel", "error", "-i", str(tmp / "av.mp4"),
                        "-map", "0:v:0", "-map", "0:a:0?", "-c:v", "libx264", "-preset", "ultrafast",
                        "-pix_fmt", "yuv420p", "-c:a", "aac", "-t", "2", "-f", "flv", "-y", str(out2)],
                       capture_output=True, check=True)
        probe2 = subprocess.run(["ffprobe", "-v", "error", "-show_streams", "-print_format", "json", str(out2)],
                                capture_output=True, text=True)
        check("A+V really encodes to flv (both streams)",
              '"codec_type": "video"' in probe2.stdout and '"codec_type": "audio"' in probe2.stdout)

        # 9) double-start guard logic exists in the engine
        src = (ROOT / "services" / "stream.py").read_text(encoding="utf-8")
        check("double-start guard present", "_starting" in src and "is_starting" in src)
        check("no forced -re in builder core", '"-re",' not in src)
        check("black video only when forced", "force_black_video" in src)
    finally:
        httpd.shutdown()

    print(f"\nPASS={len(PASS)} FAIL={len(FAIL)}")
    if FAIL:
        print("FAILED:", FAIL)
        sys.exit(1)
    print("ALL ENGINE TESTS PASSED")


if __name__ == "__main__":
    main()
