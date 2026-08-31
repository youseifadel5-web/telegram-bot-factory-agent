# -*- coding: utf-8 -*-
"""Blocking & visibility — enforced server-side."""
from __future__ import annotations

import time
from typing import Any, Dict, List, Optional, Set, Tuple

from core.models import MediaItem, Visibility


class ModerationService:
    def __init__(self, db=None):
        self.db = db
        # in-memory fallback; mirrored to SQLite when db available
        self._blocks: Dict[Tuple[str, str, str], Dict[str, Any]] = {}  # (type, id, source|*)
        self._audit: List[Dict[str, Any]] = []

    def is_blocked(self, content_type: str, content_id: str, source_id: Optional[str] = None) -> bool:
        if (content_type, str(content_id), "*") in self._blocks:
            return True
        if source_id and (content_type, str(content_id), source_id) in self._blocks:
            return True
        return False

    def filter_items(self, items: List[MediaItem], is_admin: bool = False) -> List[MediaItem]:
        out = []
        for it in items:
            typ = it.type.value if hasattr(it.type, "value") else str(it.type)
            if self.is_blocked(typ, it.id) and not is_admin:
                continue
            if it.blocked and not is_admin:
                continue
            vis = it.visibility
            if isinstance(vis, Visibility):
                vis = vis.value
            if vis in ("blocked", "hidden") and not is_admin:
                continue
            if vis == "admin_only" and not is_admin:
                continue
            # filter blocked sources
            if it.sources and not is_admin:
                it.sources = [
                    s for s in it.sources
                    if not self.is_blocked(typ, it.id, s.source_id)
                ]
                if not it.sources and it.source_ids:
                    # still allow if universal not blocked
                    pass
            out.append(it)
        return out

    def block(
        self,
        content_type: str,
        content_id: str,
        content_name: str = "",
        source_id: str = "*",
        admin_id: int = 0,
        reason: str = "",
    ) -> None:
        key = (content_type, str(content_id), source_id or "*")
        self._blocks[key] = {
            "content_type": content_type,
            "content_id": str(content_id),
            "content_name": content_name,
            "source_id": source_id or "*",
            "blocked_by": admin_id,
            "blocked_at": time.time(),
            "reason": reason,
        }
        self._audit.append({
            "admin_id": admin_id,
            "action": "BLOCK" if source_id in ("*", "", None) else "SOURCE_BLOCK",
            "content_type": content_type,
            "content_id": str(content_id),
            "content_name": content_name,
            "source_id": source_id or "*",
            "timestamp": time.time(),
            "reason": reason,
        })
        if self.db:
            try:
                self.db.save_block(self._blocks[key])
            except Exception:
                pass

    def unblock(self, content_type: str, content_id: str, source_id: str = "*", admin_id: int = 0) -> bool:
        key = (content_type, str(content_id), source_id or "*")
        existed = key in self._blocks
        self._blocks.pop(key, None)
        if source_id in ("*", ""):
            # also clear source-specific
            for k in list(self._blocks.keys()):
                if k[0] == content_type and k[1] == str(content_id):
                    self._blocks.pop(k, None)
        self._audit.append({
            "admin_id": admin_id,
            "action": "UNBLOCK",
            "content_type": content_type,
            "content_id": str(content_id),
            "content_name": "",
            "source_id": source_id or "*",
            "timestamp": time.time(),
            "reason": "",
        })
        return existed

    def list_blocks(self, page: int = 0, per_page: int = 15) -> Tuple[List[Dict], int]:
        items = list(self._blocks.values())
        items.sort(key=lambda x: -x.get("blocked_at", 0))
        total = len(items)
        return items[page * per_page:(page + 1) * per_page], total

    def audit_log(self, limit: int = 50) -> List[Dict[str, Any]]:
        return list(reversed(self._audit[-limit:]))
