"""SSRF protection for user-supplied URLs.

Blocks loopback, RFC1918, link-local, cloud metadata endpoints and other
non-public targets — while never blocking legitimate public CDNs
(Cloudflare, R2, CloudFront, ...). Validation must be applied BEFORE every
network touch: HTTP request, ffprobe, FFmpeg input, redirect and HLS variant.
"""
from __future__ import annotations

import ipaddress
import socket
from urllib.parse import urlparse

# Hostnames that must never be probed (cloud metadata / internal aliases).
_BLOCKED_HOSTS = {
    "localhost",
    "metadata",
    "metadata.google.internal",
    "metadata.goog",
    "instance-data",
    "169.254.169.254",
    "100.100.100.200",  # Alibaba metadata
}

_BLOCKED_SUFFIXES = (
    ".local",
    ".internal",
    ".localhost",
    ".lan",
    ".home.arpa",
)

# Literal IPs / networks that are always denied.
_BLOCKED_NETWORKS = [
    ipaddress.ip_network("127.0.0.0/8"),        # loopback
    ipaddress.ip_network("0.0.0.0/8"),          # this-network / unspecified
    ipaddress.ip_network("10.0.0.0/8"),         # RFC1918
    ipaddress.ip_network("172.16.0.0/12"),      # RFC1918 (172.16-31)
    ipaddress.ip_network("192.168.0.0/16"),     # RFC1918
    ipaddress.ip_network("169.254.0.0/16"),     # link-local (+ metadata 169.254.169.254)
    ipaddress.ip_network("100.64.0.0/10"),      # carrier NAT
    ipaddress.ip_network("192.0.0.0/24"),       # IETF protocol assignments
    ipaddress.ip_network("198.18.0.0/15"),      # benchmarking
    ipaddress.ip_network("224.0.0.0/3"),        # multicast + reserved
    ipaddress.ip_network("::1/128"),            # IPv6 loopback
    ipaddress.ip_network("::/128"),             # IPv6 unspecified
    ipaddress.ip_network("fc00::/7"),           # IPv6 unique-local
    ipaddress.ip_network("fe80::/10"),          # IPv6 link-local
    ipaddress.ip_network("ff00::/8"),           # IPv6 multicast
]


def _ip_is_blocked(ip: str) -> bool:
    try:
        addr = ipaddress.ip_address(ip)
    except Exception:
        return True  # unparsable address → deny
    if isinstance(addr, ipaddress.IPv6Address) and addr.ipv4_mapped:
        addr = addr.ipv4_mapped  # ::ffff:10.0.0.5 trick
    for net in _BLOCKED_NETWORKS:
        if addr in net:
            return True
    return addr.is_reserved or addr.is_multicast or addr.is_loopback or addr.is_link_local or addr.is_private


def _host_is_blocked(host: str) -> bool:
    host = (host or "").lower().strip("[]")
    if not host:
        return True
    if host in _BLOCKED_HOSTS:
        return True
    if host.endswith(_BLOCKED_SUFFIXES):
        return True
    try:
        ipaddress.ip_address(host)
    except Exception:
        return False  # hostname, not a literal IP
    return _ip_is_blocked(host)


def _resolve_blocked(host: str) -> bool:
    """Resolve DNS and deny if ANY resolved address is non-public."""
    try:
        infos = socket.getaddrinfo(host, None)
    except Exception:
        return False  # DNS failure → let HTTP layer fail later with a clear error
    for info in infos:
        ip = info[4][0]
        if _ip_is_blocked(ip):
            return True
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
    if _host_is_blocked(host):
        return False
    if _resolve_blocked(host):
        return False
    return True


def assert_safe_url(url: str) -> str:
    if not is_safe_url(url):
        raise ValueError("URL blocked by SSRF protection")
    return url


def assert_safe_redirect_url(url: str) -> str:
    """Every redirect hop must be re-validated, not just the first URL."""
    return assert_safe_url(url)
