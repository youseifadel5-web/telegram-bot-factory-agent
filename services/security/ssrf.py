"""SSRF protection for user-supplied URLs."""
from __future__ import annotations

import ipaddress
import socket
from urllib.parse import urlparse

_BLOCKED_HOSTS = {
    "localhost",
    "127.0.0.1",
    "0.0.0.0",
    "::1",
    "metadata.google.internal",
    "metadata",
}


def _is_private_ip(ip: str) -> bool:
    try:
        addr = ipaddress.ip_address(ip)
        return bool(
            addr.is_private
            or addr.is_loopback
            or addr.is_link_local
            or addr.is_reserved
            or addr.is_multicast
        )
    except Exception:
        return False


def is_safe_url(url: str) -> bool:
    if not url or not isinstance(url, str):
        return False
    try:
        p = urlparse(url.strip())
    except Exception:
        return False
    if p.scheme not in ("http", "https", "rtmp", "rtmps"):
        return False
    host = (p.hostname or "").lower()
    if not host:
        return False
    if host in _BLOCKED_HOSTS:
        return False
    if host.endswith(".local") or host.endswith(".internal"):
        return False
    # literal IP
    try:
        if _is_private_ip(host):
            return False
    except Exception:
        pass
    # resolve DNS carefully (best-effort; skip if fails)
    try:
        infos = socket.getaddrinfo(host, None)
        for info in infos:
            ip = info[4][0]
            if _is_private_ip(ip):
                return False
    except Exception:
        # If DNS fails we still allow http(s) — FFmpeg/HTTP will fail later
        pass
    return True


def assert_safe_url(url: str) -> str:
    if not is_safe_url(url):
        raise ValueError("URL blocked by SSRF protection")
    return url
