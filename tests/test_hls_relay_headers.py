"""اختبارات توحيد هيدرات الريلاي مع هيدرات الفحص السريع.

المرجع: قناة MBC Masr — الفحص السريع كان ينجح بينما FFmpeg عبر الريلاي يفشل
بخطأ 5XX، لأن الريلاي كان يرسل UA مكتوباً + Referer + Accept-Language بينما
الفحص يرسل UA موبايل بدون Referer. الحزمة موحدة الآن في services/http_headers.py.
"""
import sys
import threading
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from services.http_headers import SNIFF_HEADERS, alt_headers
import services.hls_relay as hls_relay
import services.security.ssrf as ssrf_mod


M3U8 = "#EXTM3U\n#EXT-X-TARGETDURATION:6\n#EXTINF:6,\nseg0.ts\n"


def test_relay_headers_match_sniff():
    """حزمة الريلاي الافتراضية = حزمة الفحص بالضبط (لا Referer/Accept-Language)."""
    h = hls_relay._make_headers("https://cdn.example.com/live/index.m3u8", {})
    assert h == dict(SNIFF_HEADERS)
    assert "Referer" not in h
    assert "Accept-Language" not in h


def test_sniff_headers_stable():
    """حزمة الفحص لم تتغير: UA موبايل + Accept + Accept-Encoding فقط."""
    assert set(SNIFF_HEADERS) == {"User-Agent", "Accept", "Accept-Encoding"}
    assert "Mobile Safari" in SNIFF_HEADERS["User-Agent"]


def _make_origin_server(mode: str):
    """خادم أصل يحاكي CDN: mode يحدد أي حزمة هيدرات يقبلها.

    reject_sniff: يرد 500 على UA الموبايل، 200 للمكتبي+Referer (يختبر الـ fallback)
    reject_desktop: يرد 500 على المكتبي/Referer، 200 للموبايل (حالة MBC Masr الحقيقية)
    """
    hits = {"n": 0}

    class H(BaseHTTPRequestHandler):
        def do_GET(self):  # noqa: N802
            hits["n"] += 1
            ua = self.headers.get("User-Agent", "")
            has_referer = bool(self.headers.get("Referer"))
            if mode == "reject_all":
                bad = True
            elif mode == "reject_desktop":
                bad = "Windows NT" in ua or has_referer
            else:  # reject_sniff
                bad = "Mobile Safari" in ua or not has_referer
            if bad:
                self.send_response(500)
                self.send_header("Content-Length", "0")
                self.end_headers()
                return
            body = M3U8.encode() if ".m3u8" in self.path else b"SEGDATA"
            self.send_response(200)
            self.send_header("Content-Type", "application/vnd.apple.mpegurl")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *a):
            return

    srv = ThreadingHTTPServer(("127.0.0.1", 0), H)
    t = threading.Thread(target=srv.serve_forever, daemon=True)
    t.start()
    return srv, hits


def _relay_get(url, headers=None):
    relay_url = hls_relay.get_relay_url(url, headers=headers)
    with urllib.request.urlopen(relay_url, timeout=15) as r:
        return r.status, r.read()


def test_relay_succeeds_where_sniff_succeeds(monkeypatch):
    """حالة MBC Masr: الأصل يرفض حزمة المكتبي+Referer ويقبل حزمة الموبايل —
    الريلاي الموحد يجب أن يمر من أول محاولة (سلوك الفحص نفسه)."""
    monkeypatch.setattr(ssrf_mod, "assert_safe_url", lambda u: None)
    srv, hits = _make_origin_server("reject_desktop")
    try:
        status, body = _relay_get(
            f"http://127.0.0.1:{srv.server_address[1]}/live/index.m3u8")
        assert status == 200
        assert body.startswith(b"#EXTM3U")
        assert hits["n"] == 1  # نجح من أول محاولة — لا حاجة للـ fallback
    finally:
        srv.shutdown()


def test_relay_fallback_to_desktop_headers(monkeypatch):
    """العكس: الأصل يرفض حزمة الموبايل ويقبل المكتبي+Referer —
    الريلاي يعيد المحاولة تلقائياً بالحزمة البديلة لروابط القوائم."""
    monkeypatch.setattr(ssrf_mod, "assert_safe_url", lambda u: None)
    srv, hits = _make_origin_server("reject_sniff")
    try:
        status, body = _relay_get(
            f"http://127.0.0.1:{srv.server_address[1]}/live/index.m3u8")
        assert status == 200
        assert body.startswith(b"#EXTM3U")
        assert hits["n"] == 2  # فشل ثم نجح بالحزمة البديلة
    finally:
        srv.shutdown()


def test_relay_retries_segments_with_variants(monkeypatch):
    """القطع أيضاً تجرّب الحزم الثلاث قبل الاستسلام (مقاومة Cloudflare)."""
    monkeypatch.setattr(ssrf_mod, "assert_safe_url", lambda u: None)
    srv, hits = _make_origin_server("reject_all")
    try:
        url = f"http://127.0.0.1:{srv.server_address[1]}/live/seg0.ts"
        relay_url = hls_relay.get_relay_url(url)
        try:
            urllib.request.urlopen(relay_url, timeout=15)
            assert False, "كان يجب أن يفشل"
        except urllib.error.HTTPError:
            pass
        assert hits["n"] == 3
    finally:
        srv.shutdown()


def test_alt_headers_shape():
    h = alt_headers("https://cdn.example.com/a/b.m3u8")
    assert "Referer" in h and "cdn.example.com" in h["Referer"]
    assert "Windows NT" in h["User-Agent"]


def test_cf_headers_are_cloudflare_grade():
    from services.http_headers import cf_headers
    h = cf_headers("https://x.workers.dev/a/b.m3u8")
    assert "Referer" in h and "Origin" in h
    assert h.get("Sec-Fetch-Dest") and h.get("Sec-Fetch-Mode") and h.get("Sec-Fetch-Site")
    assert "Windows NT" in h["User-Agent"]


def test_relay_tries_third_variant_for_cloudflare(monkeypatch):
    """Cloudflare-style: يرفض الحزمتين الأوليين ويقبل حزمة المتصفح الكاملة."""
    monkeypatch.setattr(ssrf_mod, "assert_safe_url", lambda u: None)
    hits = {"n": 0}

    class H(BaseHTTPRequestHandler):
        def do_GET(self):  # noqa: N802
            hits["n"] += 1
            ok = bool(self.headers.get("Sec-Fetch-Dest")) and bool(self.headers.get("Referer"))
            if ok:
                body = M3U8.encode()
                self.send_response(200)
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
            else:
                self.send_response(403)
                self.send_header("Content-Length", "0")
                self.end_headers()

        def log_message(self, *a):
            return

    srv = ThreadingHTTPServer(("127.0.0.1", 0), H)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    try:
        status, body = _relay_get(f"http://127.0.0.1:{srv.server_address[1]}/live/index.m3u8")
        assert status == 200 and body.startswith(b"#EXTM3U")
        assert hits["n"] == 3          # رُفضت الحزمتان الأوليان ثم نجحت الثالثة
    finally:
        srv.shutdown()


def test_relay_server_reuses_port(monkeypatch):
    """إعادة إنشاء الريلاي تحافظ على نفس المنفذ (وإلا ماتت روابط مبنية مسبقاً)."""
    import services.hls_relay as hr
    srv1 = hr._ensure_server()
    port1 = srv1.server_address[1]
    try:
        srv1.shutdown()
        srv1.server_close()
    except Exception:
        pass
    hr._server = None
    srv2 = hr._ensure_server()
    assert srv2.server_address[1] == port1
