"""Tests for the HLS detector: master playlists, variants, selection."""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from services.media.hls_detector import parse_m3u8_text, pick_variant, variant_dicts

MASTER = """#EXTM3U
#EXT-X-STREAM-INF:BANDWIDTH=800000,RESOLUTION=640x360,CODECS="avc1.64001e,mp4a.40.2"
360/playlist.m3u8
#EXT-X-STREAM-INF:BANDWIDTH=2500000,RESOLUTION=1280x720,FRAME-RATE=30
720/playlist.m3u8
#EXT-X-STREAM-INF:BANDWIDTH=1200000,RESOLUTION=854x480
480/playlist.m3u8
"""

MEDIA = """#EXTM3U
#EXT-X-TARGETDURATION:10
#EXT-X-MEDIA-SEQUENCE:0
#EXTINF:9.0,
seg0.ts
#EXTINF:9.0,
seg1.ts
#EXT-X-ENDLIST
"""


def test_master_playlist_variants_sorted_low_to_high():
    info = parse_m3u8_text(MASTER, base_url="https://cdn.com/h/master.m3u8")
    assert info.is_hls and info.is_master and not info.is_media
    bws = [v.bandwidth for v in info.variants]
    assert bws == sorted(bws) == [800000, 1200000, 2500000]
    assert info.variants[0].height == 360
    assert info.variants[-1].height == 720
    assert info.variants[-1].frame_rate == 30.0
    assert info.variants[0].uri.endswith("360/playlist.m3u8")


def test_variant_dicts_schema():
    info = parse_m3u8_text(MASTER)
    vs = variant_dicts(info)
    assert vs[0] == {
        "quality": "360p", "width": 640, "height": 360, "bandwidth": 800000,
        "fps": None, "codecs": "avc1.64001e,mp4a.40.2",
        "url": "360/playlist.m3u8",
    }


def test_media_playlist_not_master():
    info = parse_m3u8_text(MEDIA)
    assert info.is_hls and info.is_media and not info.is_master
    assert info.segment_count == 2
    assert info.has_endlist and info.is_live is False


def test_live_playlist_detection():
    live = MEDIA.replace("#EXT-X-ENDLIST\n", "")
    info = parse_m3u8_text(live)
    assert info.is_live is True


def test_pick_variant_quality_selection():
    info = parse_m3u8_text(MASTER)
    assert pick_variant(info, "360p").height == 360
    assert pick_variant(info, "720p").height == 720
    assert pick_variant(info, "best").height == 720
    assert pick_variant(info, "worst").height == 360


def test_non_hls_text_rejected():
    info = parse_m3u8_text("<html>hello</html>")
    assert not info.is_hls


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            print("OK", name)
    print("all hls_detector tests passed")
