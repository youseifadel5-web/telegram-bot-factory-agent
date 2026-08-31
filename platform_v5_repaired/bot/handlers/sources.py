# -*- coding: utf-8 -*-
"""تصفح مكتبة بوت قديم (يوسف فيلم) كاملة داخل المنصة الموحدة — من بيانات Xtream مباشرة."""
from __future__ import annotations

import logging
from typing import List

from core.models import MediaItem, MediaSource, MediaType

log = logging.getLogger("sources")


def _num(v, default=None):
    try:
        if v is None or v == "":
            return default
        return int(v)
    except Exception:
        return default


async def browse(plugin, media_type: str, limit: int = 400) -> List[MediaItem]:
    store = getattr(plugin, "_store", None) if plugin else None
    if not store or not hasattr(store, "streams"):
        log.warning("youseif store not bound — cannot browse")
        return []
    try:
        raw = await store.streams(media_type)
    except Exception:
        log.exception("browse streams %s", media_type)
        return []
    out: List[MediaItem] = []
    for it in (raw or [])[:limit]:
        id_key = "series_id" if media_type == "series" else "stream_id"
        iid = str(it.get(id_key) or it.get("id") or "")
        if not iid:
            continue
        title = str(it.get("name") or it.get("title") or "")
        if not title:
            continue
        poster = str(it.get("stream_icon") or it.get("cover") or it.get("movie_image") or "")
        mt = MediaType.SERIES if media_type == "series" else (MediaType.LIVE if media_type == "live" else MediaType.MOVIE)
        out.append(MediaItem(
            id=f"youseif:{iid}",
            universal_id=f"youseif:{media_type}:{iid}",
            title=title,
            type=mt,
            year=_num(it.get("year")),
            poster=poster,
            overview=str(it.get("plot") or it.get("description") or ""),
            source_ids=["youseif"],
            sources=[MediaSource(source_id="youseif", external_id=iid, extra={"raw_type": media_type, "raw": it})],
            extra={"raw_type": media_type, "raw": it},
        ))
    return out
