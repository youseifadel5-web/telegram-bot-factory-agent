"""Stream Extractor — find playable media URLs from a page or direct link."""
import logging
import re
from typing import Dict, Any, List
from urllib.parse import urljoin, unquote

logger = logging.getLogger(__name__)

_M3U8_RE = re.compile(r'https?://[^\s"\'<>]+(?:\.m3u8|/hls/)[^\s"\'<>]*', re.I)
_MP3_RE = re.compile(r'https?://[^\s"\'<>\\]+\.(mp3|aac|ogg|m4a)(?:\?[^\s"\'<>\\]*)?', re.I)
_MP4_RE = re.compile(r'https?://[^\s"\'<>\\]+\.mp4[^\s"\'<>\\]*', re.I)
_SRC_RE = re.compile(
    r'(?:src|file|source|url|stream|file_link|hlsUrl|sourceURL|playbackUrl|stream_url|media_url|hls)\s*[:=]\s*["\']([^"\']+)["\']',
    re.I,
)
_IFRAME_RE = re.compile(r'<iframe[^>]+src=["\']([^"\']+)["\']', re.I)
_JSON_URL_RE = re.compile(r'["\'](https?://[^"\']+\.(?:m3u8|mpd|mp4)[^"\']*)["\']', re.I)
# escaped urls in JS strings
_M3U8_ESCAPED_RE = re.compile(r'https?:\\/\\/[^\s"\'<>]+(?:\\.m3u8|/hls/)[^\s"\'<>]*', re.I)
_ESC_M3U8 = re.compile(r'https?:\\?/\\?/[^\s"\'<>]+\\.m3u8[^\s"\'<>]*', re.I)


def _classify(url: str) -> str:
    u = url.lower()
    if ".m3u8" in u or "mpegurl" in u:
        return "hls"
    if any(x in u for x in (".mp3", ".aac", ".ogg", ".m4a")):
        return "audio"
    if ".mp4" in u:
        return "mp4"
    if u.startswith("rtmp"):
        return "rtmp"
    return "unknown"


def _clean_url(u: str) -> str:
    u = (u or "").strip().strip("'\"")
    u = u.replace("\\/", "/").replace("\\u0026", "&")
    u = unquote(u)
    # strip trailing punctuation
    while u and u[-1] in ",);]}":
        u = u[:-1]
    return u


async def extract_stream_urls(page_url: str, timeout: int = 15) -> Dict[str, Any]:
    result: Dict[str, Any] = {
        "ok": False,
        "input": page_url,
        "direct": False,
        "streams": [],
        "error": None,
    }
    url = (page_url or "").strip().strip("<>")
    if not url.startswith(("http://", "https://", "rtmp://", "rtmps://")):
        result["error"] = "الرابط يجب أن يبدأ بـ http/https/rtmp"
        return result

    kind = _classify(url)
    if kind in ("hls", "audio", "mp4", "rtmp") or url.endswith((".m3u8", ".mp3", ".aac", ".mp4")):
        result["ok"] = True
        result["direct"] = True
        result["streams"] = [{"url": url, "type": kind}]
        return result

    found: List[Dict[str, str]] = []
    seen = set()

    def _add(u: str, base: str = url):
        u = _clean_url(u)
        if not u or u in seen:
            return
        if u.startswith("//"):
            u = "https:" + u
        elif u.startswith("/"):
            u = urljoin(base, u)
        if not u.startswith(("http://", "https://", "rtmp://")):
            return
        # skip obvious non-media
        low = u.lower()
        if any(x in low for x in (".css", ".js", ".png", ".jpg", ".jpeg", ".gif", ".svg", ".woff", "facebook.com", "twitter.com", "google-analytics")):
            return
        seen.add(u)
        found.append({"url": u, "type": _classify(u)})

    def _scan_text(text: str, base: str):
        text = (text or "").replace("\\/", "/").replace("&amp;", "&").replace("\u0026", "&")
        for rx in (_M3U8_RE, _MP3_RE, _MP4_RE, _JSON_URL_RE, _M3U8_ESCAPED_RE):
            for m in rx.findall(text):
                _add(m if isinstance(m, str) else m[0], base)
        for m in _ESC_M3U8.findall(text):
            _add(m.replace("\\/", "/"), base)
        for m in _SRC_RE.finditer(text):
            cand = m.group(1)
            if any(x in cand.lower() for x in (".m3u8", ".mp3", ".aac", ".mp4", "stream", "radio", "live", "hls", "playlist")):
                _add(cand, base)

    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
        ),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "ar,en;q=0.9",
    }

    try:
        import aiohttp
        async with aiohttp.ClientSession() as session:
            async with session.get(
                url, headers=headers,
                timeout=aiohttp.ClientTimeout(total=timeout),
                allow_redirects=True,
            ) as resp:
                if resp.status >= 400:
                    result["error"] = f"HTTP {resp.status}"
                    return result
                ctype = (resp.headers.get("Content-Type") or "").lower()
                final = str(resp.url)
                if _classify(final) in ("hls", "audio", "mp4"):
                    result["ok"] = True
                    result["direct"] = True
                    result["streams"] = [{"url": final, "type": _classify(final)}]
                    return result
                if "mpegurl" in ctype or "audio/" in ctype or "video/" in ctype:
                    result["ok"] = True
                    result["direct"] = True
                    result["streams"] = [{"url": final, "type": _classify(final) or "unknown"}]
                    return result
                text = await resp.text(errors="ignore")

            _scan_text(text, final)

            # follow up to 2 iframes that look like players
            iframes = _IFRAME_RE.findall(text)[:3]
            for ifr in iframes:
                ifr = _clean_url(ifr)
                if ifr.startswith("//"):
                    ifr = "https:" + ifr
                elif ifr.startswith("/"):
                    ifr = urljoin(final, ifr)
                if not ifr.startswith("http"):
                    continue
                try:
                    async with session.get(
                        ifr, headers=headers,
                        timeout=aiohttp.ClientTimeout(total=10),
                        allow_redirects=True,
                    ) as r2:
                        if r2.status < 400:
                            t2 = await r2.text(errors="ignore")
                            _scan_text(t2, str(r2.url))
                except Exception:
                    pass
    except Exception as e:
        result["error"] = f"تعذر فتح الصفحة: {e}"
        return result

    # Prefer hls > audio > mp4
    found.sort(key=lambda x: {"hls": 0, "audio": 1, "mp4": 2}.get(x["type"], 9))
    # de-dup by normalized url
    result["streams"] = found[:10]
    result["ok"] = len(found) > 0
    if not found:
        result["error"] = (
            "لم يتم العثور على رابط بث داخل الصفحة.\n"
            "جرّب رابط m3u8 مباشر أو قائمة IPTV من زر 📡 IPTV."
        )
    return result


def format_extract_result(data: Dict[str, Any]) -> str:
    if not data.get("ok"):
        return f"❌ <b>فشل الاستخراج</b>\n\n{data.get('error') or 'سبب غير معروف'}"
    lines = ["🔎 <b>تم استخراج روابط البث</b>\n"]
    if data.get("direct"):
        lines.append("الرابط نفسه مصدر مباشر.\n")
    for i, s in enumerate(data.get("streams") or [], 1):
        t = s.get("type") or "?"
        u = s.get("url") or ""
        short = u if len(u) < 70 else u[:55] + "…"
        lines.append(f"{i}. <b>{t}</b>\n<code>{short}</code>")
    lines.append("\nاضغط زر التشغيل لاستخدام أول رابط.")
    return "\n".join(lines)
