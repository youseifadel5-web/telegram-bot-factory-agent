"""فك رابط الـ embed إلى جودات قابلة للتشغيل — منقول من §2.6 في المواصفة.

الخوارزمية 13 خطوة بالظبط زي التطبيق: السكرابرز الرسميين (BaseVed + الكلاسيك)،
العامل الاحتياطي، سلسلة hosts/config، سلسلة multiquality، ثم fallback أخير.

مفيش WebView في بايثون، فمسار §2.7 (WebViewResolver) اتعمل هنا بجلب الصفحة
عبر curl_cffi بـ impersonate="chrome" + حصاد MEDIA/PAIR/SRC_FIELD بالريجيكس،
وبعدين فك ماستر m3u8 لو الناتج HLS.
"""
from __future__ import annotations

import asyncio
import json
import logging
import re
import time
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import quote, urljoin, urlparse

from . import keys
from . import http

logger = logging.getLogger(__name__)

DEFAULT_UA = keys.UA_CHROME141
SCRAPER_UA = keys.UA_CHROME137
WORKER_UA = keys.UA_WORKER
# الميزانية العامة لسلسلة السكرابرز (ملي ثانية)
CHAIN_BUDGET_MS = 10_000
MAX_SCRAPERS = 6

# 2.6 — الريفيرر الافتراضي حسب السيرفر
REFERER_BY_SERVER = {
    "shahed": "https://shaaheid4u.net/",
    "egy": "https://flech.tn/",
    "updown": "https://topcinema.media/",
    "wish": "https://topcinema.media/",
}
DEFAULT_REFERER = "https://faselhd.center/"

# 2.6.1 — مسارات POST الخاصة بـ BaseVed
BASEVED_ENDPOINTS = {
    "updown": [
        "https://mawdhou3.com/scrapefinal/updown.php",
        "https://mawdhou3.com/recuperepost.php",
        "https://mawdhou3.com/test.php",
    ],
    "wish": [
        "https://mawdhou3.com/scrapefinal/earnvids.php",
        "https://mawdhou3.com/recuperepost.php",
        "https://mawdhou3.com/test.php",
    ],
    "egy": [
        "https://mawdhou3.com/scrapeamine/scriptEgybest.php",
        "https://mawdhou3.com/test.php",
        "https://abcdef.flech.tn/cimaclub/cimaclub.php",
    ],
    "else": [
        "https://mawdhou3.com/test.php",
        "https://mawdhou3.com/recuperepost.php",
        "https://mawdhou3.com/scrapefinal/earnvids.php",
        "https://mawdhou3.com/scrapefinal/updown.php",
    ],
}

# 2.6.2 — مضيفات multiquality /api/source/{id}
SOURCE_HOSTS: List[str] = [
    "multiquality.host", "suzihaza.com", "gavid.xyz", "zapurl.xyz", "mrdhan.com",
    "diampokusy.com", "diasfem.com", "gdstream.net", "easyplex.xyz", "ff-dns.xyz",
    "ll-dns.xyz", "pp-dns.xyz", "psadns.xyz", "iplhd.cyou", "kotakajair.xyz",
    "manasx.xyz", "mifilm.xyz", "mycineplay.co", "oracleclouds.live", "otcplay.fun",
    "playto1.com", "pocketnow.xyz", "sbplay.xyz", "kawaiifansub.com",
]

# 2.6.3 — دلائل مضيفات الـ embed اللي بتفرض مسار المتصفح
EMBED_HOST_HINTS: List[str] = [
    "streamwish", "swishsrv", "wishfast", "streamhg", "hlsplayer", "updown", "upstream",
    "upsb", "upload", "vidoza", "vidoba", "uqload", "dood", "doodstream", "filemoon",
    "moonplayer", "mixdrop", "mixdroop", "mp4upload", "mp4u", "voe.sx", "voe-network",
    "streamtape", "strtape", "wolfstream", "luluvdo", "luluvid", "vidmoly", "vidhide",
    "vidguard", "vgembed", "vembed", "anafast", "anavids", "serveregy", "egybest",
    "egy.best", "ok.ru", "okru", "vk.com", "vkvideo", "youtube.com/embed", "myvi",
    "rutube", "mail.ru", "cloudvideo", "supervideo", "streamsb", "sbplay", "sbfull",
    "sbanh", "sblona", "embed.", "/e/", "/embed/", "/v/", "/f/",
]

# 5.5 — قوائم السكرابرز (تُختار حسب السيرفر/الرابط)
SCRAPER_VIP = [
    "https://mawdhou3.com/scripttestfasel.php?api=",
    "https://autumn-dust-1a31.flechlivraison.workers.dev/?url=",
    "https://mawdhou3.com/test.php?api=",
    "https://mawdhou3.com/scrapefinal/faselpost.php?api=",
    "https://abcdef.flech.tn/test.php?api=",
]
SCRAPER_SHAHED = [
    "https://mawdhou3.com/scrapefinal/faselpost.php?api=",
    "https://mawdhou3.com/scrapefinal/vidtubepost.php?api=",
    "https://mawdhou3.com/test.php?api=",
    "https://shahed4uapp.com/akwam/test.php?api=",
    "https://flech.tn/recuperepost.php?api=",
]
SCRAPER_UPDOWN = [
    "https://mawdhou3.com/scrapefinal/updown.php?api=",
    "https://mawdhou3.com/test.php?api=",
]
SCRAPER_WISH = [
    "https://mawdhou3.com/scrapefinal/earnvids.php?api=",
    "https://mawdhou3.com/test.php?api=",
]
SCRAPER_EGY = [
    "https://abcdef.flech.tn/cimaclub/cimaclub.php?api=",
    "https://mawdhou3.com/scrapeamine/scriptEgybest.php?api=",
    "https://mawdhou3.com/test.php?api=",
    "https://abcdef.flech.tn/test.php?api=",
]
SCRAPER_GENERIC = [
    "https://mawdhou3.com/scripttestfasel.php?api=",
    "https://mawdhou3.com/test.php?api=",
    "https://mawdhou3.com/scrapefinal/earnvids.php?api=",
    "https://mawdhou3.com/scrapefinal/updown.php?api=",
    "https://mawdhou3.com/scrapefinal/uqload.php?api=",
    "https://mawdhou3.com/scrapefinal/faselpost.php?api=",
    "https://mawdhou3.com/scrapefinal/vidtubepost.php?api=",
    "https://abcdef.flech.tn/cimaclub/cimaclub.php?api=",
]

# ============================================================
# 2.6.4 — الريجيكس الحرفية
# ============================================================
PAIR = re.compile(r'\{\s*"?file"?\s*:\s*"(.*?)"\s*,\s*"?label"?\s*:\s*"(.*?)"\s*\}')
OLD_PAIR = re.compile(r'"?file"?\s*:\s*"(.*?)"\s*,\s*"?label"?\s*:\s*"(.*?)"')
NEWLINE_PAIR = re.compile(r'file\s*:\s*"(.*?)"\s*,\s*label\s*:\s*"(.*?)"')
RESOLUTION = re.compile(r'RESOLUTION=(\d+x\d+)', re.I)
BANDWIDTH = re.compile(r'BANDWIDTH=(\d+)', re.I)
# مسار المتصفح (2.7): حصاد الروابط
MEDIA = re.compile(r'https?://[^"\'\\\s<>]+\.(?:m3u8|mpd|mp4|mkv|m4v|webm|ts)(?:\?[^"\'\\\s<>]*)?', re.I)
SRC_FIELD = re.compile(
    r'"(?:file|src|source|url|link|stream|hls|dash)"\s*:\s*"(https?://[^"]+)"'
    r'|src="([^"]+\.(?:m3u8|mp4|mpd)[^"]*)"',
    re.I,
)


# ============================================================
# أدوات صغيرة
# ============================================================
def clean_text(value: Any) -> str:
    if value is None:
        return ""
    text = str(value).strip()
    if text.lower() in ("", "null", "none", "undefined"):
        return ""
    return text


def add_pair(qualities: List[dict], seen: set, url: Any, label: Any) -> None:
    """يضيف جودة بعد فلترة: لازم تبدأ http وطولها ≤2000 حرف."""
    url = clean_text(url)
    if not url.startswith("http") or len(url) > 2000:
        return
    label = clean_text(label).strip('"').strip("'").replace("،", "/") or "جودة"
    if url in seen:
        return
    seen.add(url)
    qualities.append({"label": label, "url": url})


def _label_from_url(url: str, fallback: str = "جودة") -> str:
    low = url.lower()
    for tag in ("1080", "720", "480", "360"):
        if tag in low:
            return f"{tag}p"
    return fallback


# ============================================================
# 2.6.4 — parsers
# ============================================================
def parse_json_qualities(body: Any) -> List[dict]:
    """يحلّل جودة من JSON: مصفوفة جذرية أو مفاتيح qualities/availableQualities/..."""
    if isinstance(body, str):
        try:
            body = json.loads(body)
        except Exception:
            return []
    qualities: List[dict] = []
    seen: set = set()
    items: List[Any] = []
    if isinstance(body, list):
        items = body
    elif isinstance(body, dict):
        for key in ("qualities", "availableQualities", "sources", "links", "data"):
            value = body.get(key)
            if isinstance(value, list):
                items = value
                break
            if isinstance(value, dict):
                items = [value]
                break
    for item in items:
        if not isinstance(item, dict):
            continue
        url = item.get("url") or item.get("file") or item.get("link") or item.get("src")
        label = item.get("quality") or item.get("label") or item.get("name") or item.get("resolution")
        add_pair(qualities, seen, url, label)
    return qualities


def parse_base_ved_response(body: Any) -> List[dict]:
    """يحلّل رد BaseVed: status (فاضي أو success) + مصفوفات متوازية للجودات والروابط."""
    if isinstance(body, str):
        try:
            body = json.loads(body)
        except Exception:
            return []
    if isinstance(body, list):
        return parse_json_qualities(body)
    if not isinstance(body, dict):
        return []
    status = clean_text(body.get("status")).lower()
    if status and status != "success":
        return []
    labels = body.get("Quality") or body.get("qualities") or body.get("QUALITY") or []
    urls = body.get("filtered_content") or body.get("urls") or body.get("files") or []
    if isinstance(labels, str):
        labels = [labels]
    if isinstance(urls, str):
        urls = [urls]
    if not isinstance(labels, list):
        labels = []
    if not isinstance(urls, list):
        urls = []
    qualities: List[dict] = []
    seen: set = set()
    for index, raw_url in enumerate(urls):
        if isinstance(raw_url, dict):
            raw_url = raw_url.get("url") or raw_url.get("file") or raw_url.get("link")
        label = labels[index] if index < len(labels) else None
        if isinstance(label, dict):
            label = label.get("quality") or label.get("label")
        if not clean_text(label):
            label = _label_from_url(clean_text(raw_url), "جودة")
        add_pair(qualities, seen, raw_url, label)
    return qualities


def parse_pairs(body: Any) -> List[dict]:
    """يحلّل أزواج file/label بأشكاله الثلاثة، وإلا يرجع لـ JSON."""
    if not body:
        return []
    text = body if isinstance(body, str) else str(body)
    qualities: List[dict] = []
    seen: set = set()
    for pattern in (PAIR, NEWLINE_PAIR, OLD_PAIR):
        for match in pattern.finditer(text):
            add_pair(qualities, seen, match.group(1), match.group(2))
        if qualities:
            break
    if qualities:
        return qualities
    return parse_json_qualities(text) or parse_base_ved_response(text)


def parse_master(body: Any, base: str = "") -> List[dict]:
    """يفكّ ماستر m3u8: كل #EXT-X-STREAM-INF ← سطر الرابط اللي بعده."""
    if not body:
        return []
    text = body if isinstance(body, str) else str(body)
    lines = text.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    qualities: List[dict] = []
    seen: set = set()
    pending_label: Optional[str] = None
    for line in lines:
        stripped = line.strip()
        if stripped.upper().startswith("#EXT-X-STREAM-INF"):
            resolution = RESOLUTION.search(stripped)
            bandwidth = BANDWIDTH.search(stripped)
            if resolution:
                pending_label = resolution.group(1)
            elif bandwidth:
                try:
                    pending_label = f"{int(bandwidth.group(1)) // 1000}k"
                except Exception:
                    pending_label = "تلقائي"
            else:
                pending_label = "تلقائي"
            continue
        if stripped.startswith("#") or not stripped:
            continue
        if pending_label is not None:
            url = urljoin(base, stripped) if base else stripped
            add_pair(qualities, seen, url, pending_label)
            pending_label = None
    return qualities


# ============================================================
# 2.6 — اختيار السكرابرز و BaseVed
# ============================================================
def _has_vip(server: str, link: str) -> bool:
    s, l = server.lower(), link.lower()
    return "vip" in s or "plusfas" in l or "fasel-hd" in l or re.search(r"[?&]p=\d+", l) is not None


def scrapers_for(server: str, link: str) -> List[str]:
    """يختار قائمة السكرابرز حسب السيرفر/الرابط (5.5)."""
    s, l = server.lower(), link.lower()
    if _has_vip(server, link):
        return SCRAPER_VIP
    if any(k in s or k in l for k in ("shahed", "شاهد", "vidtube", "fdewsdc", "flech")):
        return SCRAPER_SHAHED
    if "updown" in s or "updown" in l:
        return SCRAPER_UPDOWN
    if any(k in s or k in l for k in ("wish", "streamwish", "stmruby", "earnvids")):
        return SCRAPER_WISH
    if "egy" in s or "cima" in s or "egy" in l or "cima" in l:
        return SCRAPER_EGY
    return SCRAPER_GENERIC


def _baseved_kind(server: str, link: str) -> Optional[str]:
    s, l = server.lower(), link.lower()
    if "updown" in s or "updown" in l:
        return "updown"
    if any(k in s or k in l for k in ("wish", "streamwish", "stmruby", "earnvids")):
        return "wish"
    if any(k in s or k in l for k in ("egy", "cima", "egybest", "cimaclub")):
        return "egy"
    return None


def _is_baseved_server(server: str, link: str) -> bool:
    """Path A: updown / wish / server egy / cima / egy — بس مش vip."""
    if _has_vip(server, link):
        return False
    return _baseved_kind(server, link) is not None


def _default_referer(server: str) -> str:
    s = (server or "").lower()
    for key, ref in REFERER_BY_SERVER.items():
        if key in s:
            return ref
    return DEFAULT_REFERER


def _looks_like_fasel_page(link: str) -> bool:
    l = link.lower()
    return bool(
        re.search(r"[?&]p=\d+", l)
        or any(k in l for k in ("plusfas", "fasel-hd", "fashd.com", "faselhd", "faselhds", "egybest", "cimaclub"))
    )


def _is_embed_host(link: str) -> bool:
    l = link.lower()
    return any(hint in l for hint in EMBED_HOST_HINTS)


def _is_direct_file(link: str) -> bool:
    l = link.lower()
    return bool(re.search(r"\.(mp4|mkv|webm|m4v|mov|ts)(\?|$)", l)) and "embed" not in l and "/e/" not in l


def _is_hls(link: str) -> bool:
    l = link.lower()
    return ".m3u8" in l or "/hls/" in l or "playlist" in l


def fasel_referer(link: str) -> Optional[str]:
    """5.4 — ريفيرر فاصل لو الرابط منه، وإلا None."""
    l = link.lower()
    if "fasel-hd" in l or "plusfas" in l or "/?p=" in l:
        return "https://www.fasel-hd.com/"
    return None


def host_referer(link: str) -> Optional[str]:
    """5.4 — {scheme}://{host}/ من الرابط."""
    parsed = urlparse(link)
    if parsed.scheme and parsed.netloc:
        return f"{parsed.scheme}://{parsed.netloc}/"
    return None


# ============================================================
# شبكة — أدوات الفكّ
# ============================================================
async def _first_success(coros, timeout: float) -> List[dict]:
    """يشغّل الكوروتينات بالتوازي ويرجّع أول نتيجة ناجحة قبل انتهاء المدة."""
    if not coros:
        return []
    tasks = [asyncio.ensure_future(c) for c in coros]
    deadline = time.monotonic() + timeout
    try:
        pending = set(tasks)
        while pending:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                break
            done, pending = await asyncio.wait(pending, timeout=remaining, return_when=asyncio.FIRST_COMPLETED)
            for task in done:
                try:
                    result = task.result()
                except Exception:
                    result = None
                if result:
                    return result
        return []
    finally:
        for task in tasks:
            if not task.done():
                task.cancel()


async def _resolve_via_page_post(link: str, ua: str, ref: str, server: str, timeout: float = 12.0) -> List[dict]:
    """Path A — EasyPlex BaseVed: GET صفحة الـ embed ثم POST للـ endpoints."""
    html = await http.get_text(link, headers={"User-Agent": ua, "Referer": ref, "Accept": "*/*"}, timeout=timeout)
    if not html:
        return []
    kind = _baseved_kind(server, link) or "else"
    endpoints = BASEVED_ENDPOINTS.get(kind, BASEVED_ENDPOINTS["else"])
    data = {"content": html, "url": link}

    async def _try(endpoint: str) -> List[dict]:
        body = await http.post_form(endpoint, data, headers={"User-Agent": ua, "Referer": ref, "Accept": "*/*"}, timeout=timeout)
        if not body:
            return []
        return parse_base_ved_response(body) or parse_pairs(body)

    return await _first_success([_try(e) for e in endpoints], timeout)


async def _resolve_via_classic_scrapers(link: str, ua: str, ref: str, server: str, timeout: float = 9.0) -> List[dict]:
    """Path B — سكرابرز api= الكلاسيكية."""
    bases = scrapers_for(server, link)[:MAX_SCRAPERS]
    encoded = quote(link, safe="")

    async def _try(base: str) -> List[dict]:
        for candidate, headers, kwargs in (
            (base + encoded, {"User-Agent": ua, "Referer": ref, "Accept": "*/*"}, {}),
            (base + link, {"User-Agent": ua, "Referer": ref, "Accept": "*/*"}, {}),
        ):
            body = await http.get_text(candidate, headers=headers, timeout=timeout, **kwargs)
            if body:
                result = parse_pairs(body) or parse_base_ved_response(body)
                if result:
                    return result
        body = await http.post_form(
            base,
            {"api": encoded, "url": encoded, "link": encoded},
            headers={"User-Agent": ua, "Referer": ref, "Accept": "*/*"},
            timeout=timeout,
        )
        if body:
            return parse_pairs(body) or parse_base_ved_response(body)
        return []

    return await _first_success([_try(b) for b in bases], timeout)


async def _try_official_scrapers(link: str, ua: str, ref: str, server: str) -> List[dict]:
    """الخطوة 2: السكرابرز الرسميين — Path A ثم Path B."""
    ua = ua or DEFAULT_UA
    ref = ref or _default_referer(server)
    if _is_baseved_server(server, link):
        result = await _resolve_via_page_post(link, ua, ref, server)
        if result:
            return result
    return await _resolve_via_classic_scrapers(link, ua, ref, server)


async def _resolve_worker(link: str, timeout: float = 12.0) -> List[dict]:
    """العامل الاحتياطي: الرابط الخام الأول ثم المشفّر (5.6.3)."""
    for candidate in (keys.FALLBACK_WORKER + link, keys.FALLBACK_WORKER + quote(link, safe="")):
        body = await http.get_text(candidate, headers=keys.WORKER_HEADERS, timeout=timeout)
        if body:
            result = parse_pairs(body)
            if result:
                return result
    return []


async def _harvest_media(body: str) -> List[dict]:
    """حصاد MEDIA/PAIR/SRC_FIELD من صفحة (بديل WebView)."""
    qualities: List[dict] = []
    seen: set = set()
    for pair in parse_pairs(body):
        add_pair(qualities, seen, pair["url"], pair["label"])
    for match in SRC_FIELD.finditer(body):
        url = match.group(1) or match.group(2)
        add_pair(qualities, seen, url, _label_from_url(clean_text(url), "تلقائي"))
    for match in MEDIA.finditer(body):
        add_pair(qualities, seen, match.group(0), _label_from_url(match.group(0), "تلقائي"))
    return qualities


async def _fetch_browser(url: str, referer: str = "", timeout: float = 14.0) -> Optional[str]:
    """يجلب صفحة عبر curl_cffi بـ impersonate="chrome" (بديل WebView)."""
    def _blocking() -> Optional[str]:
        try:
            from curl_cffi import requests as cffi_requests
        except Exception:
            logger.warning("curl_cffi غير متاح — تخطي مسار المتصفح")
            return None
        headers = {"User-Agent": keys.UA_BROWSER, "Accept": "*/*"}
        if referer:
            headers["Referer"] = referer
        try:
            resp = cffi_requests.get(url, headers=headers, impersonate="chrome", timeout=timeout)
            return resp.text if resp.status_code < 400 else None
        except Exception as exc:
            logger.warning("browser fetch %s failed: %s", url, exc)
            return None

    return await asyncio.to_thread(_blocking)


async def _webview_resolve(url: str, referer: str = "", timeout: float = 14.0) -> List[dict]:
    """2.7 — مسار المتصفح: جلب الصفحة + حصاد + فك ماستر m3u8."""
    body = await _fetch_browser(url, referer, timeout)
    if not body:
        return []
    qualities = await _harvest_media(body)
    if not qualities:
        return []
    # لو الناتج HLS واحد، نفك الماستر لجودات
    return await expand_qualities(qualities, referer=referer, ua=keys.UA_BROWSER)


async def _resolve_multiquality(p_id: str, timeout: float = 10.0) -> List[dict]:
    """الخطوة 8: سلسلة multiquality /api/source/{pId}."""
    async def _try(host: str) -> List[dict]:
        body = await http.get_text(f"https://{host}/api/source/{p_id}", headers=keys.SOURCE_HOST_HEADERS, timeout=timeout)
        if not body:
            return []
        return parse_json_qualities(body) or parse_pairs(body)

    return await _first_success([_try(h) for h in SOURCE_HOSTS], timeout)


def _order_hosts(link: str, hosts: List[dict]) -> List[dict]:
    """يرتّب المضيفات: اللي دومينها يطابق الرابط أولاً."""
    host = (urlparse(link).netloc or "").lower()

    def rank(cfg: dict) -> int:
        for domain in (cfg.get("domains") or []):
            if domain and domain.lower() in host:
                return 0
        return 1

    enabled = [h for h in (hosts or []) if isinstance(h, dict) and h.get("enabled", True)]
    return sorted(enabled, key=rank)


def _build_api_url(site: str, link: str) -> str:
    """يبني رابط api= مع عدم تكرار العلامة (5.6.4)."""
    site = clean_text(site)
    encoded = quote(link, safe="")
    if "api=" in site:
        return site + encoded
    if "workers.dev" in site or site.endswith("url="):
        return site + encoded
    sep = "&" if "?" in site else "?"
    return f"{site}{sep}api={encoded}"


async def _resolve_via_hosts(link: str, hosts: List[dict], video_ua: str, video_ref: str, budget: float = 10.0) -> List[dict]:
    """الخطوة 10: سلسلة hosts/config."""
    ordered = _order_hosts(link, hosts)
    deadline = time.monotonic() + budget
    for cfg in ordered:
        if time.monotonic() > deadline:
            break
        site = clean_text(cfg.get("urlSite"))
        if not site.startswith("http") or len(site) > 300:
            continue
        api_url = _build_api_url(site, link)
        headers = {
            "User-Agent": clean_text(cfg.get("userAgent")) or video_ua or DEFAULT_UA,
            "Referer": clean_text(cfg.get("referer")) or video_ref or "https://shaaheid4u.net/",
            "Accept": "*/*",
        }
        remaining = max(1.0, deadline - time.monotonic())
        body = await http.get_text(api_url, headers=headers, timeout=remaining)
        if body:
            result = parse_pairs(body)
            if result:
                return result
    return []


async def expand_qualities(qualities: List[dict], referer: str = "", ua: str = "") -> List[dict]:
    """2.6 — لو أقل من جودتين والرابط الوحيد HLS، نفك الماستر ونقسّم الجودات."""
    if len(qualities) >= 2:
        return qualities
    if not qualities:
        return qualities
    single = qualities[0]
    url = single.get("url") or ""
    if not _is_hls(url):
        return qualities
    headers = {"User-Agent": ua or DEFAULT_UA, "Accept": "*/*"}
    if referer:
        headers["Referer"] = referer
    body = await http.get_text(url, headers=headers)
    if not body:
        return qualities
    variants = parse_master(body, base=url)
    return variants or qualities


# ============================================================
# 2.6 — الخطوات 1..13
# ============================================================
def _normalize_link(link: Any) -> str:
    text = clean_text(link).lstrip("\ufeff").strip()
    if not text:
        return ""
    if not text.startswith("http"):
        text = "https://" + text
    return text


async def _resolve_inner(link: str, ua: str, ref: str, server: str, video: dict, hosts: List[dict]) -> Tuple[List[dict], Optional[str], str]:
    """يرجّع (الجودات، الرابط المباشر، مصدر الفك)."""
    # 1. تطبيع الرابط
    if not link:
        return [], None, "none"

    hd = bool(video.get("hd"))

    # 2. السكرابرز الرسميين
    result = await _try_official_scrapers(link, ua, ref, server)
    if result:
        return result, None, "official"

    # 3. صفحات فاصل → العامل ثم المتصفح
    if _looks_like_fasel_page(link):
        result = await _resolve_worker(link)
        if result:
            return result, None, "worker"
        result = await _webview_resolve(link, ref or DEFAULT_REFERER)
        if result:
            return result, None, "webview"

    # 4. ملف مباشر
    if _is_direct_file(link):
        return [{"label": "HD" if hd else "مباشر", "url": link}], link, "direct"

    # 5. HLS جاهز
    if _is_hls(link):
        variants = await expand_qualities([{"label": "HD", "url": link}], referer=ref, ua=ua)
        if len(variants) >= 2:
            return variants, link, "hls"
        return [{"label": "HD" if hd else "متوسط", "url": link}], link, "hls"

    # 6. مضيف embed معروف → المتصفح
    if _is_embed_host(link):
        result = await _webview_resolve(link, ref or host_referer(link) or "")
        if result:
            return result, None, "webview"

    # 7. workers.dev مع /video أو get-links
    low = link.lower()
    if "workers.dev" in low and ("/video" in low or "get-links" in low):
        body = await http.get_text(link, headers={"User-Agent": ua, "Referer": ref, "Accept": "*/*"})
        if body:
            if "availableQualities" in body or "qualities" in body:
                parsed = parse_json_qualities(body)
                if parsed:
                    return parsed, None, "worker-direct"
            return [{"label": "مباشر", "url": link}], link, "worker-direct"

    # 8. سلسلة multiquality لو فيه ?p=
    match = re.search(r"[?&]p=(\d+)", link)
    if match:
        result = await _resolve_multiquality(match.group(1))
        if result:
            return result, None, "multiquality"

    # 9. mawdhou3 scripttestfasel
    body = await http.get_text(
        "https://mawdhou3.com/scripttestfasel.php?api=" + quote(link, safe=""),
        headers={"User-Agent": SCRAPER_UA, "Referer": DEFAULT_REFERER, "Accept": "*/*"},
    )
    if body:
        result = parse_pairs(body)
        if result:
            return result, None, "scripttest"

    # 10. سلسلة hosts/config
    result = await _resolve_via_hosts(link, hosts, ua, ref)
    if result:
        return result, None, "hosts"

    # 11. العامل العام
    result = await _resolve_worker(link)
    if result:
        return result, None, "worker"

    # 12. المتصفح — تمريرة عامة
    result = await _webview_resolve(link, ref or host_referer(link) or "")
    if result:
        return result, None, "webview"

    # 13. الاحتياطي
    return [{"label": "Original", "url": link}], link, "fallback"


async def resolve(video: dict, hosts: List[dict]) -> Dict[str, Any]:
    """الواجهة العامة: {qualities:[{label,url}], direct, source}."""
    video = video if isinstance(video, dict) else {}
    link = _normalize_link(video.get("link") or video.get("url") or "")
    if not link:
        return {"qualities": [], "direct": None, "source": "none"}
    ua = clean_text(video.get("userAgent"))
    ref = clean_text(video.get("referer"))
    server = clean_text(video.get("server"))
    qualities, direct, source = await _resolve_inner(link, ua, ref, server, video, hosts or [])
    qualities = await expand_qualities(qualities, referer=ref, ua=ua)
    if not qualities:
        qualities = [{"label": "Original", "url": link}]
        direct = direct or link
        source = source or "fallback"
    return {"qualities": qualities, "direct": direct, "source": source}
