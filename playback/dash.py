# -*- coding: utf-8 -*-
"""DASH/MPD detection helpers."""
from __future__ import annotations


def is_dash_manifest(text: str) -> bool:
    t = text or ""
    return "<MPD" in t or "urn:mpeg:dash" in t.lower()


def list_representations_ids(text: str) -> list:
    import re
    return re.findall(r'id="([^"]+)"', text or "")[:20]
