"""Local HLS relay — يجعل FFmpeg قادراً على تشغيل المصادر المحظورة.

بعض شبكات CDN (nrpstream، Cloudflare وأمثالها) تقبل اتصال Python/المتصفح
وترفض اتصال FFmpeg مباشرة (بصمة TLS) بخطأ 403. الحل: تشغيل خادم HTTP محلي
صغير يمرر كل طلبات القوائم والقطع (segments) عبر Python بهيدرات متصفح،
ثم يقرأ FFmpeg من 127.0.0.1 بدلاً من المصدر الأصلي.

لا يُستخدم إلا عند فشل الاتصال المباشر بخطأ 403/401 — التشغيل المباشر
يظل هو المسار الافتراضي الأسرع.
"""
from __future__ import annotations

import base64
import json
import logging
import re
import threading
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Dict, Optional
from urllib.parse import urljoin, urlparse

logger = logging.getLogger(__name__)

DEFAULT_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
)
FETCH_TIMEOUT = 25

_URI_ATTR_RE = re.compile(r'(URI)="([^"]+)"')

_lock = threading.Lock()
_server: Optional[ThreadingHTTPServer] = None


def _encode_target(url: str, headers: Optional[Dict[str, str]]) -> str:
    h = dict(headers or {})
    # علّم النطاق الأصلي حتى لا تُرسل الهيدرات الخاصة إلا لخادمه نفسه
    h["_origin_host"] = url
    payload = {"u": url, "h": h}
    raw = json.dumps(payload, ensure_ascii=True).encode("utf-8")
    return base64.urlsafe_b64encode(raw).decode("ascii")


def _decode_target(b64: str):
    raw = base64.urlsafe_b64decode(b64 + "=" * (-len(b64) % 4))
    data = json.loads(raw.decode("utf-8"))
    return data.get("u") or "", data.get("h") or {}


def _make_headers(orig_url: str, extra: Dict[str, str]) -> Dict[str, str]:
    """Browser-grade headers — نفس الحزمة التي تنجح مع sniff/urllib."""
    h = {
        "User-Agent": DEFAULT_UA,
        "Accept": "*/*",
        "Accept-Language": "ar,en;q=0.8",
        "Accept-Encoding": "identity",
    }
    host = urlparse(orig_url).netloc
    if host:
        h["Referer"] = f"https://{host}/"
    # هيدرات خاصة مررها مصدر البث (أوسكار وغيره) — لكن لنفس النطاق فقط،
    # حتى لا تتسرب بيانات اعتماد مصدرٍ ما إلى خادم آخر داخل القائمة.
    extra_host = urlparse(str(extra.get("_origin_host") or "")).netloc if isinstance(extra, dict) else ""
    same_host = bool(host) and bool(extra_host) and host == extra_host
    for k, v in (extra or {}).items():
        if not v or str(k) == "_origin_host":
            continue
        if str(k).lower() in ("accept-encoding", "host", "content-length", "connection"):
            continue
        if same_host:
            h[str(k)] = str(v)
    return h


def _fetch(url: str, headers: Dict[str, str], range_header: Optional[str]):
    # فحص SSRF على كل رابط يمر عبر الريلاي — القائمة نفسها قد تحوي
    # روابط داخلية (metadata/RFC1918) لا يجوز جلبها أو بثها.
    from services.security.ssrf import assert_safe_url
    assert_safe_url(url)
    req_headers = _make_headers(url, headers)
    if range_header:
        req_headers["Range"] = range_header
    req = urllib.request.Request(url, headers=req_headers, method="GET")
    return urllib.request.urlopen(req, timeout=FETCH_TIMEOUT)


class _RelayHandler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def do_GET(self):  # noqa: N802
        try:
            url, hdrs = _decode_target(self.path.split("?", 1)[0].split("/r/", 1)[1])
        except Exception:
            self._fail(400)
            return
        if not url:
            self._fail(400)
            return
        try:
            resp = _fetch(url, hdrs, self.headers.get("Range"))
        except Exception as e:
            logger.debug("relay fetch failed (%s): %s", url[:120], e)
            self._fail(502)
            return

        try:
            ctype = str(resp.headers.get("Content-Type") or "")
            status = int(getattr(resp, "status", 200) or 200)
            head = resp.read(64 * 1024)

            if head.lstrip(b"\xef\xbb\xbf \r\n\t").startswith(b"#EXTM3U"):
                text = head.decode("utf-8", errors="ignore")
                rest = resp.read()
                if rest:
                    text += rest.decode("utf-8", errors="ignore")
                body = _rewrite_playlist(text, url, hdrs).encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "application/vnd.apple.mpegurl")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
                return

            # قطعة media — تمرير مباشر (streaming)
            self.send_response(status)
            self.send_header("Content-Type", ctype or "video/mp2t")
            length = resp.headers.get("Content-Length")
            crange = resp.headers.get("Content-Range")
            if crange:
                self.send_header("Content-Range", crange)
            if length:
                self.send_header("Content-Length", length)
            else:
                self.send_header("Connection", "close")
                self.close_connection = True
            self.end_headers()
            self.wfile.write(head)
            while True:
                chunk = resp.read(64 * 1024)
                if not chunk:
                    break
                self.wfile.write(chunk)
                if hasattr(self.wfile, "flush"):
                    self.wfile.flush()
        except (BrokenPipeError, ConnectionResetError):
            return  # FFmpeg أغلق الاتصال (طبيعي عند الإيقاف/التبديل)
        except Exception as e:
            logger.debug("relay stream failed: %s", e)
            try:
                self._fail(502)
            except Exception:
                pass

    def _fail(self, code: int):
        try:
            self.send_response(code)
            self.send_header("Content-Length", "0")
            self.end_headers()
        except Exception:
            pass

    def log_message(self, *a):  # إسكات سجلات الخادم
        return


def _rewrite_playlist(text: str, base_url: str, hdrs: Dict[str, str]) -> str:
    """أعد كتابة كل الروابط داخل قائمة M3U8 لتمر عبر الريلاي بنفس الهيدرات."""
    def relay_link(u: str) -> str:
        return get_relay_url(urljoin(base_url, u), hdrs)

    out = []
    for line in text.replace("\r\n", "\n").split("\n"):
        s = line.strip()
        if not s:
            out.append(line)
            continue
        if s.startswith("#"):
            out.append(_URI_ATTR_RE.sub(
                lambda m: f'{m.group(1)}="{relay_link(m.group(2))}"', line
            ))
        else:
            out.append(relay_link(s))
    return "\n".join(out)


def _serve():
    global _server
    try:
        _server.serve_forever()
    finally:
        # لو مات خيط الخدمة لأي سبب — اسمح بإنشاء خادم جديد في الطلب القادم
        _server = None


def _ensure_server() -> ThreadingHTTPServer:
    global _server
    with _lock:
        if _server is None:
            _server = ThreadingHTTPServer(("127.0.0.1", 0), _RelayHandler)
            _server.daemon_threads = True
            t = threading.Thread(target=_serve, daemon=True, name="hls-relay")
            t.start()
            logger.info("HLS relay listening on 127.0.0.1:%s", _server.server_address[1])
        return _server


def is_relay_url(url: str) -> bool:
    """True إذا كان الرابط من إنتاج هذا الريلاي (يُسمح به في فحص SSRF)."""
    if _server is None or not url:
        return False
    try:
        return url.startswith(f"http://127.0.0.1:{_server.server_address[1]}/r/")
    except Exception:
        return False


def get_relay_url(url: str, headers: Optional[Dict[str, str]] = None) -> str:
    """رابط محلي يمر عبر الريلاي إلى url (مع هيدرات اختيارية لكل طلب)."""
    srv = _ensure_server()
    port = srv.server_address[1]
    return f"http://127.0.0.1:{port}/r/{_encode_target(url, headers)}"
