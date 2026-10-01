"""اختبارات: إعادة المحاولة بالوضع الآمن عند فشل أول تشغيل + كشف تعارض مفتاح RTMP.

السياق: بثّان بنفس مفتاح تليجرام = الثاني يُرفض ويظهر «متوقفاً» بلا سبب.
وكذلك الأمر المتقدم لو فشل فوراً (قبل وجود watchdog) كان يضيّع فرصة الوضع الآمن.
"""
import sys
import threading
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import services.stream as sm


def _bare_manager():
    mgr = object.__new__(sm.StreamManager)
    mgr.processes = {}
    mgr._meta = {}
    mgr._watchdogs = {}
    mgr._readers = {}
    mgr.ffmpeg = "/tmp/ffmpeg"
    mgr._lock = threading.Lock()
    mgr.ensure_ffmpeg = lambda: True
    mgr._apply_relay_default = lambda meta: None
    mgr._watchdog_loop = lambda sid: None
    return mgr


def test_first_spawn_failure_retries_with_safe_mode():
    mgr = _bare_manager()
    calls = []

    def fake_spawn(sid):
        calls.append(bool(mgr._meta[sid].get("safe_mode")))
        if len(calls) == 1:
            mgr._meta[sid]["last_error"] = "Error opening output files: Invalid argument"
            return None
        return 4242

    mgr._spawn = fake_spawn
    pid = mgr.start_stream(1, "https://cdn.example.com/live/index.m3u8",
                           "rtmps://dc4-1.rtmp.t.me/s/KEY",
                           with_video=True, source_type="M3U8 / HLS")
    assert pid == 4242
    assert calls == [False, True]           # المحاولة الأولى عادية ثم الوضع الآمن
    assert mgr._meta[1]["safe_mode"] is True


def test_first_spawn_failure_safe_also_fails_returns_none():
    mgr = _bare_manager()
    mgr._spawn = lambda sid: None
    pid = mgr.start_stream(2, "https://x/y.m3u8", "rtmps://e/live/K")
    assert pid is None
    assert 2 not in mgr._meta               # نُظّفت الحالة عند الفشل الكامل


def test_rtmp_in_use_detects_conflict():
    mgr = _bare_manager()
    mgr.processes = {1: object()}
    mgr._meta[1] = {"rtmp": "rtmps://dc4-1.rtmp.t.me/s/KEY"}
    assert mgr.rtmp_in_use("rtmps://dc4-1.rtmp.t.me/s/KEY") == 1
    assert mgr.rtmp_in_use("rtmps://dc4-1.rtmp.t.me/s/OTHER") is None
    # بث غير شغّال لا يُعتبر تعارضاً
    mgr.processes = {}
    assert mgr.rtmp_in_use("rtmps://dc4-1.rtmp.t.me/s/KEY") is None


def test_rtmp_in_use_ignores_self():
    mgr = _bare_manager()
    mgr.processes = {5: object()}
    mgr._meta[5] = {"rtmp": "rtmps://e/live/SAME"}
    assert mgr.rtmp_in_use("rtmps://e/live/SAME", exclude_stream_id=5) is None


def test_rtmp_in_use_empty_url_is_none():
    mgr = _bare_manager()
    assert mgr.rtmp_in_use("") is None
    assert mgr.rtmp_in_use(None) is None


def test_start_stream_stops_same_key_stream():
    """تغيير القناة بنفس مفتاح البث = إيقاف البث القديم تلقائياً ثم تشغيل الجديد."""
    mgr = _bare_manager()
    stopped = []
    mgr.processes = {1: object()}
    mgr._meta[1] = {"rtmp": "rtmps://dc4-1.rtmp.t.me/s/KEY", "watchdog": True}
    mgr._stop_stream_locked = lambda sid: stopped.append(sid) or True
    mgr._spawn = lambda sid: 999
    pid = mgr.start_stream(2, "https://cdn.example.com/live/b.m3u8",
                           "rtmps://dc4-1.rtmp.t.me/s/KEY",
                           with_video=True, source_type="M3U8 / HLS")
    assert pid == 999
    assert 1 in stopped                       # البث القديم أُوقف
    assert mgr._meta[2]["rtmp"].endswith("/KEY")


def test_start_stream_keeps_different_key_stream():
    """مفتاح مختلف = بثّان معاً مسموحان (لا إيقاف)."""
    mgr = _bare_manager()
    stopped = []
    mgr.processes = {1: object()}
    mgr._meta[1] = {"rtmp": "rtmps://dc4-1.rtmp.t.me/s/KEY_A", "watchdog": True}
    mgr._stop_stream_locked = lambda sid: stopped.append(sid) or True
    mgr._spawn = lambda sid: 777
    pid = mgr.start_stream(2, "https://cdn.example.com/live/b.m3u8",
                           "rtmps://dc4-1.rtmp.t.me/s/KEY_B",
                           with_video=True, source_type="M3U8 / HLS")
    assert pid == 777
    assert stopped == []
