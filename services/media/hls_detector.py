"""HLS detection without relying only on .m3u8 in the URL."""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional
from urllib.parse import urljoin, urlparse

logger = logging.getLogger(__name__)

HLS_CONTENT_TYPES = (
    "application/vnd.apple.mpegurl",
    "application/x-mpegurl",
    "audio/mpegurl",
    "audio/x-mpegurl",
    "application/mpegurl",
)


@dataclass
class HLSVariant:
    uri: str
    bandwidth: int = 0
    resolution: str = ""
    frame_rate: float = 0.0
    codecs: str = ""
    name: str = ""
    width: int = 0
    height: int = 0

    @property
    def quality_label(self) -> str:
        if self.height:
            return f"{self.height}p"
        if self.resolution:
            return self.resolution
        return ""


@dataclass
class HLSInfo:
    is_hls: bool = False
    is_master: bool = False
    is_media: bool = False
    variants: List[HLSVariant] = field(default_factory=list)
    target_duration: float = 0.0
    media_sequence: int = 0
    has_endlist: bool = False
    playlist_type: str = ""
    is_live: Optional[bool] = None
    segment_count: int = 0
    first_segment: str = ""
    raw_type: str = ""
    content_type: str = ""
    final_url: str = ""
    error: str = ""


def _parse_stream_inf(line: str) -> Dict[str, str]:
    attrs = {}
    # bandwidth=123,RESOLUTION=1280x720,CODECS="avc1,mp4a"
    for part in re.findall(r'([A-Z0-9-]+)=(".*?"|[^,]*)', line, flags=re.I):
        k, v = part[0], part[1].strip().strip('"')
        attrs[k.upper()] = v
    return attrs


def parse_m3u8_text(text: str, base_url: str = "") -> HLSInfo:
    info = HLSInfo(is_hls=False)
    if not text or not str(text).lstrip().startswith("#EXTM3U"):
        return info
    info.is_hls = True
    lines = [ln.strip() for ln in str(text).replace("\r", "").split("\n")]
    pending_inf: Optional[Dict[str, str]] = None
    segments = []
    for i, line in enumerate(lines):
        if not line:
            continue
        if line.startswith("#EXT-X-STREAM-INF:"):
            info.is_master = True
            pending_inf = _parse_stream_inf(line[len("#EXT-X-STREAM-INF:"):])
            continue
        if line.startswith("#EXT-X-TARGETDURATION:"):
            try:
                info.target_duration = float(line.split(":", 1)[1])
            except Exception:
                pass
            info.is_media = True
            continue
        if line.startswith("#EXT-X-MEDIA-SEQUENCE:"):
            try:
                info.media_sequence = int(line.split(":", 1)[1])
            except Exception:
                pass
            info.is_media = True
            continue
        if line.startswith("#EXT-X-ENDLIST"):
            info.has_endlist = True
            info.is_media = True
            continue
        if line.startswith("#EXT-X-PLAYLIST-TYPE:"):
            info.playlist_type = line.split(":", 1)[1].strip().upper()
            info.is_media = True
            continue
        if line.startswith("#EXTINF:"):
            info.is_media = True
            continue
        if line.startswith("#"):
            continue
        # URI line
        uri = urljoin(base_url, line) if base_url else line
        if pending_inf is not None:
            bw = 0
            try:
                bw = int(pending_inf.get("BANDWIDTH") or pending_inf.get("AVERAGE-BANDWIDTH") or 0)
            except Exception:
                pass
            fr = 0.0
            try:
                fr = float(pending_inf.get("FRAME-RATE") or 0)
            except Exception:
                pass
            w, h = 0, 0
            res = pending_inf.get("RESOLUTION") or ""
            if "x" in res:
                try:
                    w, h = (int(x) for x in res.lower().split("x", 1))
                except Exception:
                    w = h = 0
            info.variants.append(
                HLSVariant(
                    uri=uri,
                    bandwidth=bw,
                    resolution=res,
                    frame_rate=fr,
                    codecs=pending_inf.get("CODECS") or "",
                    name=pending_inf.get("NAME") or "",
                    width=w,
                    height=h,
                )
            )
            pending_inf = None
        else:
            segments.append(uri)
    info.segment_count = len(segments)
    if segments:
        info.first_segment = segments[0]
        info.is_media = True
    if info.is_media:
        # EVENT/VOD and ENDLIST are finite playlists; an open playlist is live.
        info.is_live = not info.has_endlist and info.playlist_type not in ("VOD",)
        if info.playlist_type == "EVENT":
            info.is_live = True
    elif info.is_master:
        info.is_live = None
    if info.is_master and not info.is_media:
        info.raw_type = "master"
    elif info.is_media:
        info.raw_type = "media"
    else:
        info.raw_type = "hls"
    # Canonical order: lowest → highest bandwidth
    info.variants.sort(key=lambda v: v.bandwidth)
    return info


def variant_dicts(info: HLSInfo) -> List[Dict[str, Any]]:
    """Serialize variants (sorted low→high) into plain dicts for probe results."""
    return [
        {
            "quality": v.quality_label,
            "width": v.width,
            "height": v.height,
            "bandwidth": v.bandwidth,
            "fps": v.frame_rate or None,
            "codecs": v.codecs,
            "url": v.uri,
        }
        for v in sorted(info.variants, key=lambda x: x.bandwidth)
    ]


def pick_variant(info: HLSInfo, quality: str = "best") -> Optional[HLSVariant]:
    if not info.variants:
        return None
    variants = sorted(info.variants, key=lambda v: v.bandwidth)
    q = (quality or "best").lower().strip()
    if q in ("worst", "lowest", "min"):
        return variants[0]
    if q in ("best", "highest", "max", "source"):
        return variants[-1]
    # resolution match like 720p
    m = re.match(r"(\d{3,4})p?", q)
    if m:
        target = int(m.group(1))
        best = None
        best_diff = 10**9
        for v in variants:
            h = 0
            if "x" in (v.resolution or ""):
                try:
                    h = int(v.resolution.split("x")[1])
                except Exception:
                    h = 0
            if h:
                diff = abs(h - target)
                if diff < best_diff:
                    best_diff = diff
                    best = v
        if best:
            return best
    return variants[-1]


async def detect_hls(
    url: str,
    headers: Optional[Dict[str, str]] = None,
    timeout: float = 15.0,
    max_redirects: int = 5,
) -> HLSInfo:
    """HTTP probe + content detection for HLS (does not require .m3u8 in URL)."""
    import aiohttp
    from services.security.ssrf import is_safe_url

    info = HLSInfo()
    info.final_url = url
    if not is_safe_url(url):
        info.error = "URL blocked by SSRF protection"
        return info

    hdrs = {
        "User-Agent": "Mozilla/5.0 (Linux; Android 15) AppleWebKit/537.36 Chrome/131.0 Mobile Safari/537.36",
        "Accept": "*/*",
    }
    if headers:
        hdrs.update({k: v for k, v in headers.items() if v})

    try:
        timeout_cfg = aiohttp.ClientTimeout(total=timeout)
        async with aiohttp.ClientSession(timeout=timeout_cfg) as session:
            async with session.get(
                url,
                headers=hdrs,
                allow_redirects=True,
                max_redirects=max_redirects,
            ) as resp:
                info.final_url = str(resp.url)
                if not is_safe_url(info.final_url):
                    info.error = "Redirect target blocked by SSRF protection"
                    return info
                ct = (resp.headers.get("Content-Type") or "").split(";")[0].strip().lower()
                info.content_type = ct
                if resp.status >= 400:
                    info.error = f"HTTP {resp.status}"
                    return info
                # Read limited body for playlist detection
                body = await resp.content.read(512 * 1024)
                text = ""
                try:
                    text = body.decode("utf-8", errors="ignore")
                except Exception:
                    text = ""
                looks_playlist = text.lstrip().startswith("#EXTM3U")
                ct_hls = any(x in ct for x in HLS_CONTENT_TYPES) or "mpegurl" in ct
                url_hint = ".m3u8" in (url or "").lower() or ".m3u8" in info.final_url.lower()
                if looks_playlist or ct_hls or (url_hint and text.lstrip().startswith("#")):
                    parsed = parse_m3u8_text(text, base_url=info.final_url)
                    parsed.content_type = ct
                    parsed.final_url = info.final_url
                    if not parsed.is_hls and looks_playlist:
                        parsed.is_hls = True
                    return parsed
                # Not HLS text — maybe MPEG-TS / MP4
                if ct in ("video/mp2t", "video/mp4", "audio/mpeg", "audio/aac"):
                    info.raw_type = ct
                return info
    except Exception as e:
        info.error = f"{type(e).__name__}: {e}"
        logger.debug("detect_hls: %s", e)
        return info
