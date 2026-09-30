"""Unified browser-grade HTTP headers — طبقة واحدة لهيدرات طلبات HTTP.

الفحص السريع (source_probe) والريلاي (hls_relay) يجب أن يرسلا نفس حزمة
الهيدرات بالضبط: شبكات CDN تُفرّق بين الطلبات بناءً على UA/Referer وقد
ترجع 5XX لحزمة و200 لأخرى. أي تعديل هنا ينعكس تلقائياً على الطرفين.
"""
from __future__ import annotations

from urllib.parse import urlparse

# الحزمة الأساسية — نفس ما يرسله الفحص السريع (نجحت مع كل المصادر المفحوصة):
# UA موبايل، بدون Referer، بدون Accept-Language.
SNIFF_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Linux; Android 15) AppleWebKit/537.36 "
        "Chrome/131.0 Mobile Safari/537.36"
    ),
    "Accept": "*/*",
    "Accept-Encoding": "identity",
}

# الحزمة البديلة — متصفح مكتبي مع Referer لنفس النطاق؛ تستخدم كإعادة محاولة
# واحدة عندما ترد الشبكة بخطأ 4XX/5XX على الحزمة الأساسية.
DESKTOP_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
)


def alt_headers(orig_url: str, extra: dict | None = None) -> dict:
    """حزمة بديلة: UA مكتبي + Referer لنفس نطاق المصدر (بدون بيانات خارجية)."""
    h = {
        "User-Agent": DESKTOP_UA,
        "Accept": "*/*",
        "Accept-Language": "ar,en;q=0.8",
        "Accept-Encoding": "identity",
    }
    host = urlparse(orig_url).netloc
    if host:
        h["Referer"] = f"https://{host}/"
    for k, v in (extra or {}).items():
        if v and str(k).lower() not in (
            "accept-encoding", "host", "content-length", "connection", "user-agent",
            "_origin_host", "referer", "accept", "accept-language",
        ):
            h[str(k)] = str(v)
    return h
