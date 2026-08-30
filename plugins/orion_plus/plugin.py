# -*- coding: utf-8 -*-
"""Orion Plus plugin adapter — search / details / sources via Aurora vault."""
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

log = logging.getLogger("plugin.orion")


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


def _title(it: dict) -> str:
    return str(it.get("titleAr") or it.get("titleEn") or it.get("title") or it.get("name") or "")


class Plugin(MediaSourcePlugin):
    id = "orion"
    name = "Orion Plus"
    version = "4.0.0"

    def __init__(self):
        self._vault = None

    def bind_vault(self, vault_api) -> None:
        self._vault = vault_api

    async def search(self, query: SearchQuery) -> List[MediaItem]:
        if not self._vault:
            return []
        out: List[MediaItem] = []
        q = (query.text or "").strip()
        try:
            if query.media_type in (None, "movie", "any"):
                items, _ = self._vault.list_content("movies", page=1, limit=20, search=q)
                for it in items or []:
                    iid = str(it.get("id") or "")
                    if not iid:
                        continue
                    out.append(MediaItem(
                        id=f"orion:{iid}",
                        universal_id=f"orion:movie:{iid}",
                        title=_title(it),
                        original_title=str(it.get("titleEn") or ""),
                        type=MediaType.MOVIE,
                        year=_num(it.get("year")),
                        poster=str(it.get("poster") or it.get("image") or it.get("cover") or ""),
                        overview=str(it.get("overview") or it.get("description") or ""),
                        rating=_float(it.get("rating")),
                        source_ids=["orion"],
                        sources=[MediaSource(source_id="orion", external_id=iid)],
                    ))
            if query.media_type in (None, "series", "any"):
                items, _ = self._vault.list_content("series", page=1, limit=20, search=q)
                for it in items or []:
                    iid = str(it.get("id") or "")
                    if not iid:
                        continue
                    out.append(MediaItem(
                        id=f"orion:{iid}",
                        universal_id=f"orion:series:{iid}",
                        title=_title(it),
                        original_title=str(it.get("titleEn") or ""),
                        type=MediaType.SERIES,
                        year=_num(it.get("year")),
                        poster=str(it.get("poster") or it.get("image") or it.get("cover") or ""),
                        overview=str(it.get("overview") or it.get("description") or ""),
                        rating=_float(it.get("rating")),
                        source_ids=["orion"],
                        sources=[MediaSource(source_id="orion", external_id=iid)],
                    ))
        except Exception:
            log.exception("orion search failed")
        return out

    async def get_details(self, item_id: str) -> Optional[MediaItem]:
        if not self._vault:
            return None
        eid = item_id.split(":")[-1]
        try:
            for kind, mt in (("movies", MediaType.MOVIE), ("series", MediaType.SERIES)):
                it = self._vault.detail(kind, eid)
                if not it or not isinstance(it, dict):
                    continue
                if not (it.get("id") or it.get("title") or it.get("titleAr") or it.get("titleEn")):
                    continue
                return MediaItem(
                    id=f"orion:{eid}",
                    universal_id=f"orion:{mt.value}:{eid}",
                    title=_title(it),
                    original_title=str(it.get("titleEn") or ""),
                    type=mt,
                    year=_num(it.get("year")),
                    poster=str(it.get("poster") or it.get("image") or ""),
                    overview=str(it.get("overview") or it.get("description") or ""),
                    rating=_float(it.get("rating")),
                    source_ids=["orion"],
                    sources=[MediaSource(source_id="orion", external_id=eid)],
                    extra={"raw": it, "kind": kind},
                )
        except Exception:
            log.exception("orion get_details failed")
        return None

    async def get_series_details(self, item_id: str) -> Optional[SeriesDetails]:
        if not self._vault:
            return None
        eid = item_id.split(":")[-1]
        try:
            it = self._vault.detail("series", eid)
            if not it or not isinstance(it, dict):
                return None
            item = MediaItem(
                id=f"orion:{eid}",
                universal_id=f"orion:series:{eid}",
                title=_title(it),
                original_title=str(it.get("titleEn") or ""),
                type=MediaType.SERIES,
                year=_num(it.get("year")),
                poster=str(it.get("poster") or it.get("image") or ""),
                overview=str(it.get("overview") or it.get("description") or ""),
                rating=_float(it.get("rating")),
                source_ids=["orion"],
                sources=[MediaSource(source_id="orion", external_id=eid)],
                extra={"raw": it},
            )
            seasons: List[Season] = []
            raw_seasons = it.get("seasons") or []
            if isinstance(raw_seasons, list) and raw_seasons:
                for s in raw_seasons:
                    sn = _num(s.get("season_number") or s.get("number") or s.get("season"), 1) or 1
                    eps_raw = s.get("episodes") or []
                    eps = []
                    for e in eps_raw:
                        en = _num(e.get("episode_number") or e.get("number") or e.get("episode"), 0) or 0
                        eid_ep = str(e.get("id") or f"{eid}-s{sn}e{en}")
                        eps.append(Episode(
                            id=f"orion:{eid_ep}",
                            series_id=f"orion:{eid}",
                            season=sn,
                            number=en,
                            title=str(e.get("title") or e.get("name") or f"الحلقة {en}"),
                            sources=[
                                MediaSource(source_id="orion", external_id=str(e.get("id") or ""), url=u)
                                for u in [
                                    e.get("url") or e.get("stream_url") or e.get("play_url") or ""
                                ]
                                if u
                            ],
                        ))
                    seasons.append(Season(number=sn, episode_count=len(eps) or _num(s.get("episodes_count"), 0) or 0, episodes=eps))
            else:
                # flat episodes
                ep_list = it.get("episodes") or []
                by_season: Dict[int, List[Episode]] = {}
                for e in ep_list:
                    sn = _num(e.get("season_number") or e.get("season"), 1) or 1
                    en = _num(e.get("episode_number") or e.get("number") or e.get("episode"), 0) or 0
                    eid_ep = str(e.get("id") or f"{eid}-s{sn}e{en}")
                    by_season.setdefault(sn, []).append(Episode(
                        id=f"orion:{eid_ep}",
                        series_id=f"orion:{eid}",
                        season=sn,
                        number=en,
                        title=str(e.get("title") or e.get("name") or f"الحلقة {en}"),
                    ))
                for sn in sorted(by_season.keys()):
                    seasons.append(Season(number=sn, episode_count=len(by_season[sn]), episodes=by_season[sn]))
            return SeriesDetails(item=item, seasons=seasons)
        except Exception:
            log.exception("orion get_series_details failed")
        return None

    async def get_sources(self, item_id: str, media_type: str = "movie") -> List[Dict[str, Any]]:
        if not self._vault:
            return []
        eid = item_id.split(":")[-1]
        out: List[Dict[str, Any]] = []
        try:
            kind = "series" if media_type in ("series", "episode") else "movies"
            it = self._vault.detail(kind, eid)
            if not it and kind == "movies":
                it = self._vault.detail("series", eid)
            if not it or not isinstance(it, dict):
                return []
            raw_sources = []
            if hasattr(self._vault, "_sources"):
                raw_sources = self._vault._sources(it.get("sources"))
            else:
                raw_sources = it.get("sources") or it.get("watch_links") or it.get("links") or []
            # resolve if possible
            resolved = raw_sources
            if hasattr(self._vault, "resolve_sources") and raw_sources:
                try:
                    resolved = self._vault.resolve_sources(raw_sources)
                except Exception:
                    resolved = raw_sources
            for s in resolved or []:
                if isinstance(s, str) and s.startswith("http"):
                    out.append({"url": s, "source_id": "orion"})
                elif isinstance(s, dict):
                    url = (
                        s.get("url") or s.get("link") or s.get("stream_url")
                        or s.get("play_url") or s.get("video_url") or s.get("m3u8_url")
                    )
                    if url:
                        out.append({
                            "url": str(url),
                            "quality": s.get("quality") or s.get("label"),
                            "source_id": "orion",
                        })
        except Exception:
            log.exception("orion get_sources failed")
        return out

    async def get_categories(self) -> List[Dict[str, Any]]:
        return []

    async def health_check(self) -> Dict[str, Any]:
        return {"id": self.id, "ok": self._vault is not None, "bound": self._vault is not None}
