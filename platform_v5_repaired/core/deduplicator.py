# -*- coding: utf-8 -*-
from __future__ import annotations

import re
import unicodedata
from typing import Dict, List, Optional, Tuple

from core.models import MediaItem


def normalize_title(text: str) -> str:
    if not text:
        return ""
    s = unicodedata.normalize("NFKC", str(text)).lower().strip()
    s = re.sub(r"[\u064B-\u065F\u0670]", "", s)
    s = s.replace("أ", "ا").replace("إ", "ا").replace("آ", "ا").replace("ة", "ه").replace("ى", "ي")
    s = re.sub(r"\((19|20)\d{2}\)", " ", s)
    s = re.sub(r"\b(19|20)\d{2}\b", " ", s)
    s = re.sub(r"(?i)\b(1080p|720p|480p|4k|bluray|web-?dl|hdrip)\b", " ", s)
    s = re.sub(r"[^\w\s\u0600-\u06FF]", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def _score(item: MediaItem) -> int:
    score = 0
    if item.poster:
        score += 50
    if item.overview and len(item.overview) > 20:
        score += 30
    score += int(min(item.rating or 0, 10) * 2)
    score += len(item.sources) * 5
    return score


def dedupe_items(items: List[MediaItem]) -> List[MediaItem]:
    """Same title+type+year → keep best (poster/overview first), merge sources."""
    best: Dict[Tuple[str, str, Optional[int]], MediaItem] = {}
    for it in items:
        typ = it.type.value if hasattr(it.type, "value") else str(it.type)
        key = (typ, normalize_title(it.title or it.original_title), it.year)
        cur = best.get(key)
        if cur is None:
            best[key] = it
            continue
        existing_ids = {(s.source_id, s.external_id) for s in cur.sources}
        for s in it.sources:
            if (s.source_id, s.external_id) not in existing_ids:
                cur.sources.append(s)
                if s.source_id not in cur.source_ids:
                    cur.source_ids.append(s.source_id)
        if _score(it) > _score(cur):
            it.sources = cur.sources
            it.source_ids = list(cur.source_ids)
            best[key] = it
    out = list(best.values())
    out.sort(key=lambda x: (-_score(x), x.title or ""))
    return out
