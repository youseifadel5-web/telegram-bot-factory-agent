# -*- coding: utf-8 -*-
from __future__ import annotations

import re
from typing import List

from core.models import QualityOption


def sort_qualities(options: List[QualityOption]) -> List[QualityOption]:
    def key(q: QualityOption):
        m = re.search(r"(\d+)", q.label or "")
        return -int(m.group(1)) if m else 0

    return sorted(options, key=key)


def unique_labels(options: List[QualityOption]) -> List[QualityOption]:
    seen = set()
    out = []
    for q in sort_qualities(options):
        if q.label in seen:
            continue
        seen.add(q.label)
        out.append(q)
    return out
