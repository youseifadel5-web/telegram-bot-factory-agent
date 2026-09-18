"""Iron headers generator for OscarTV (ostvapp.cam).

Port of the PHP IronHeadersGenerator so the bot can sign API requests
locally without depending on an external proxy.
"""
from __future__ import annotations

import hashlib
import hmac
import os
import time
from typing import Dict
from urllib.parse import urlparse


class IronHeadersGenerator:
    GUARD_1 = "OscarTVIronGuard"
    GUARD_2 = "IronGuard"

    def __init__(
        self,
        cert_sha256: str = "6e2fcda8631eb49ebcba4ca8ef4c597abe84654c7d3e8096db32bdd21ecf763f",
        pkg_name: str = "com.drama.mp4",
        host: str = "ostvapp.cam",
    ):
        self.cert = cert_sha256
        self.pkg = pkg_name
        self.host = host
        self.fingerprint = cert_sha256[:8]

    def _derive_key(self) -> bytes:
        raw = f"{self.cert}|{self.pkg}"
        data = raw.encode("utf-8")
        length = len(data)
        g1 = self.GUARD_1.encode("utf-8")
        g2 = self.GUARD_2.encode("utf-8")

        # Stage 1: XOR modulo 7
        result1 = bytes(data[i] ^ g1[i % 7] for i in range(length))
        # Stage 2: Reverse
        result2 = result1[::-1]
        # Stage 3: XOR modulo 9
        result3 = bytes(result2[i] ^ g2[i % 9] for i in range(length))
        # Stage 4: 3x SHA-256
        pass1 = hashlib.sha256(result3).digest()
        pass2 = hashlib.sha256(pass1).digest()
        return hashlib.sha256(pass2).digest()

    def generate(self, url: str) -> Dict[str, str]:
        parsed = urlparse(url)
        path = parsed.path or "/"
        timestamp = str(int(time.time()))
        nonce = os.urandom(4).hex()
        key = self._derive_key()
        payload = f"{path}|{timestamp}|{nonce}".encode("utf-8")
        sig = hmac.new(key, payload, hashlib.sha256).hexdigest()
        return {
            "Host": self.host,
            "x-iron-sig": sig,
            "x-iron-ts": timestamp,
            "x-iron-nonce": nonce,
            "x-iron-diag": f"f={self.fingerprint} p={self.fingerprint} h=0",
            "accept-encoding": "gzip",
            "user-agent": "okhttp/4.12.0",
            "connection": "keep-alive",
        }


# Shared singleton with the app certificate from the provided PHP script
iron_gen = IronHeadersGenerator()


def iron_headers_for(url: str) -> Dict[str, str]:
    """Generate signed Iron headers for a full OscarTV URL."""
    return iron_gen.generate(url)
