"""اختبارات: كاش الفحص السريع + حفظ cleaned_url في مسار HLS.

السياق: خطوة «جاري فحص المصدر قبل التشغيل» كانت بطيئة لأن الفحص يُستدعى مرتين
(عند إرسال المصدر ثم قبل التشغيل) ولا يتعرّف على أنه تم مسبقاً.
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import services.source_probe as sp


def test_probe_source_is_cached(monkeypatch):
    calls = []

    def fake_impl(url, timeout=35, headers=None):
        calls.append(url)
        return {"ok": True, "url": url, "cleaned_url": url}

    monkeypatch.setattr(sp, "_probe_source_impl", fake_impl)
    sp._PROBE_CACHE.clear()
    r1 = sp.probe_source("https://cdn.example.com/live/a.m3u8")
    r2 = sp.probe_source("https://cdn.example.com/live/a.m3u8")
    assert r1 == r2
    assert calls == ["https://cdn.example.com/live/a.m3u8"]  # الشبكة مرة واحدة


def test_probe_failures_not_cached(monkeypatch):
    calls = []

    def fake_impl(url, timeout=35, headers=None):
        calls.append(url)
        return {"ok": False}

    monkeypatch.setattr(sp, "_probe_source_impl", fake_impl)
    sp._PROBE_CACHE.clear()
    sp.probe_source("https://cdn.example.com/bad.m3u8")
    sp.probe_source("https://cdn.example.com/bad.m3u8")
    assert calls.count("https://cdn.example.com/bad.m3u8") == 2


def test_hls_fast_path_sets_cleaned_url(monkeypatch):
    monkeypatch.setattr(sp, "sniff_remote_content",
                        lambda url, headers=None, timeout=8: {"is_hls": True,
                                                             "content_type": "application/vnd.apple.mpegurl"})
    monkeypatch.setattr(sp, "_fetch_master_variants",
                        lambda url, headers=None, timeout=8: {"is_master": True, "variants": [
                            {"bandwidth": 900000, "codecs": "avc1.4d401f,mp4a.40.2",
                             "width": 1280, "height": 720}]})
    r = sp._probe_source_impl("https://cdn.example.com/live/index.m3u8")
    assert r["ok"] is True
    assert r["cleaned_url"] == "https://cdn.example.com/live/index.m3u8"
    assert r["is_hls"] is True
    assert r["video_codec"] == "h264" and r["audio_codec"] == "aac"
