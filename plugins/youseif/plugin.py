# -*- coding: utf-8 -*-
"""Youseif Films as a MediaSourcePlugin (data only — no Telegram)."""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from core.models import (
    Episode,
    MediaItem,
    MediaSource,
    MediaType,
    SearchQuery,
    Season,
    SeriesDetails,
)
from core.plugin_base import MediaSourcePlugin

log = logging.getLogger("plugin.youseif")


def _num(v, default=None):
    try:
        if v is None or v == "":
            return default
        return int(v)
    except Exception:
        return default


def _float(v, default=0.0):
    try:
        return float(v or 0) or default
    except Exception:
        return default


class Plugin(MediaSourcePlugin):
    id = "youseif"
    name = "Youseif Films"
    version = "4.0.0"

    def __init__(self):
        self._store = None
        self._ready = False

    def bind_store(self, store) -> None:
        """Optional: bind existing youseif_core Store at runtime."""
        self._store = store
        self._ready = store is not None

    def _xt(self):
        return getattr(self._store, "xt", None) if self._store else None

    def _to_item(self, typ: str, it: dict) -> Optional[MediaItem]:
        id_key = "series_id" if typ == "series" else "stream_id"
        iid = str(it.get(id_key) or it.get("id") or "")
        if not iid:
            return None
        title = str(it.get("name") or it.get("title") or "")
        # بوستر: أيقونة القناة / غلاف الفيلم / غلاف المسلسل
        poster = str(
            it.get("stream_icon")
            or it.get("cover")
            or it.get("cover_big")
            or it.get("movie_image")
            or it.get("icon")
            or ""
        ).strip()
        # روابط نسبية → مطلقة عبر قاعدة Xtream
        xt = self._xt()
        if poster and not poster.startswith("http") and xt and getattr(xt, "base", None):
            base = xt.base.rstrip("/")
            poster = base + ("/" if not poster.startswith("/") else "") + poster
        if poster.startswith("//"):
            poster = "https:" + poster
        mt = MediaType.SERIES if typ == "series" else (MediaType.LIVE if typ == "live" else MediaType.MOVIE)
        return MediaItem(
            id=f"youseif:{iid}",
            universal_id=f"youseif:{typ}:{iid}",
            title=title,
            type=mt,
            year=_num(it.get("year") or (str(it.get("releaseDate") or "")[:4] if it.get("releaseDate") else None)),
            poster=poster,
            overview=str(it.get("plot") or it.get("description") or ""),
            rating=_float(it.get("rating") or it.get("rating_5based")),
            source_ids=["youseif"],
            sources=[MediaSource(
                source_id="youseif",
                external_id=iid,
                extra={
                    "raw_type": typ,
                    "container_extension": it.get("container_extension") or "mp4",
                    "direct_source": it.get("direct_source") or "",
                    "category_id": str(it.get("category_id") or ""),
                },
            )],
            extra={"raw_type": typ, "raw": it},
        )

    async def search(self, query: SearchQuery) -> List[MediaItem]:
        if not self._store:
            return []
        out: List[MediaItem] = []
        q = (query.text or "").strip()
        typ_filter = query.media_type if query.media_type not in (None, "any") else None
        try:
            # بحث نصي
            if q:
                raw = await self._store.search(q)
                for typ, it in raw or []:
                    if typ_filter and typ != typ_filter:
                        continue
                    item = self._to_item(typ, it)
                    if item:
                        out.append(item)
            # تصفح حسب النوع (أفلام/مسلسلات/قنوات) بدون نص
            elif typ_filter in ("movie", "series", "live") and hasattr(self._store, "streams"):
                streams = await self._store.streams(typ_filter, None)
                for it in (streams or [])[:40]:
                    item = self._to_item(typ_filter, it)
                    if item:
                        out.append(item)
        except Exception:
            log.exception("youseif search failed")
        return out

    async def get_details(self, item_id: str) -> Optional[MediaItem]:
        # Prefer search/cache enrichment; Xtream often has no single-item detail for VOD
        if not self._store:
            return None
        eid = item_id.split(":")[-1]
        # try series_info
        try:
            if hasattr(self._store, "series_info"):
                info = await self._store.series_info(eid)
                if info and isinstance(info, dict):
                    info_block = info.get("info") or info
                    title = str(info_block.get("name") or info_block.get("title") or "")
                    if title:
                        return MediaItem(
                            id=f"youseif:{eid}",
                            universal_id=f"youseif:series:{eid}",
                            title=title,
                            type=MediaType.SERIES,
                            poster=str(info_block.get("cover") or info_block.get("movie_image") or ""),
                            overview=str(info_block.get("plot") or ""),
                            rating=_float(info_block.get("rating")),
                            year=_num(str(info_block.get("releaseDate") or "")[:4] or None),
                            source_ids=["youseif"],
                            sources=[MediaSource(source_id="youseif", external_id=eid)],
                            extra={"raw": info, "raw_type": "series"},
                        )
        except Exception:
            log.exception("youseif get_details series_info")
        return None

    async def get_series_details(self, item_id: str) -> Optional[SeriesDetails]:
        if not self._store or not hasattr(self._store, "series_info"):
            return None
        eid = item_id.split(":")[-1]
        try:
            info = await self._store.series_info(eid)
            if not info or not isinstance(info, dict):
                return None
            info_block = info.get("info") or {}
            item = MediaItem(
                id=f"youseif:{eid}",
                universal_id=f"youseif:series:{eid}",
                title=str(info_block.get("name") or info_block.get("title") or ""),
                type=MediaType.SERIES,
                poster=str(info_block.get("cover") or ""),
                overview=str(info_block.get("plot") or ""),
                rating=_float(info_block.get("rating")),
                source_ids=["youseif"],
                sources=[MediaSource(source_id="youseif", external_id=eid)],
            )
            seasons: List[Season] = []
            episodes_map = info.get("episodes") or {}
            # Xtream: episodes is dict keyed by season number -> list
            if isinstance(episodes_map, dict):
                for sn_str, eps_raw in sorted(episodes_map.items(), key=lambda x: _num(x[0], 0) or 0):
                    sn = _num(sn_str, 1) or 1
                    eps = []
                    for e in eps_raw or []:
                        en = _num(e.get("episode_num") or e.get("episode") or e.get("number"), 0) or 0
                        eid_ep = str(e.get("id") or e.get("episode_id") or f"{eid}-s{sn}e{en}")
                        ext = e.get("container_extension") or "mp4"
                        eps.append(Episode(
                            id=f"youseif:{eid_ep}",
                            series_id=f"youseif:{eid}",
                            season=sn,
                            number=en,
                            title=str(e.get("title") or f"الحلقة {en}"),
                            sources=[MediaSource(
                                source_id="youseif",
                                external_id=eid_ep,
                                extra={"container_extension": ext, "raw_type": "episode"},
                            )],
                        ))
                    seasons.append(Season(number=sn, episode_count=len(eps), episodes=eps))
            return SeriesDetails(item=item, seasons=seasons)
        except Exception:
            log.exception("youseif get_series_details failed")
        return None

    async def get_sources(self, item_id: str, media_type: str = "movie") -> List[Dict[str, Any]]:
        xt = self._xt()
        if not xt:
            return []
        eid = item_id.split(":")[-1]
        out: List[Dict[str, Any]] = []
        try:
            # episode ids often appear as youseif:{episode_id}
            if media_type in ("episode", "series"):
                # try both mp4 and m3u8
                if hasattr(xt, "episode_url"):
                    out.append({"url": xt.episode_url(eid, "mp4"), "source_id": "youseif", "quality": "mp4"})
                if hasattr(xt, "episode_m3u8"):
                    out.append({"url": xt.episode_m3u8(eid), "source_id": "youseif", "quality": "hls"})
            if media_type in ("movie", "any", None) or not out:
                if hasattr(xt, "movie_url"):
                    out.append({"url": xt.movie_url(eid, "mp4"), "source_id": "youseif", "quality": "mp4"})
                if hasattr(xt, "movie_m3u8"):
                    out.append({"url": xt.movie_m3u8(eid), "source_id": "youseif", "quality": "hls"})
            if media_type == "live" and hasattr(xt, "live_url"):
                out.append({"url": xt.live_url(eid), "source_id": "youseif", "quality": "live"})
        except Exception:
            log.exception("youseif get_sources failed")
        return out

    async def get_categories(self) -> List[Dict[str, Any]]:
        if not self._store or not hasattr(self._store, "categories"):
            return []
        out = []
        try:
            for typ in ("movie", "series", "live"):
                cats = await self._store.categories(typ)
                for c in cats or []:
                    out.append({
                        "id": str(c.get("category_id") or c.get("id") or ""),
                        "name": str(c.get("category_name") or c.get("name") or ""),
                        "type": typ,
                    })
        except Exception:
            log.exception("youseif categories")
        return out

    async def health_check(self) -> Dict[str, Any]:
        return {"id": self.id, "ok": self._ready, "bound": self._ready}
