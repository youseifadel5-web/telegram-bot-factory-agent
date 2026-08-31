# -*- coding: utf-8 -*-
"""Cinema Nova plugin adapter — full search / details / sources."""
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

log = logging.getLogger("plugin.nova")


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
    id = "nova"
    name = "Cinema Nova"
    version = "4.0.0"

    def __init__(self):
        self._api = None

    def bind_api(self, api) -> None:
        self._api = api

    async def search(self, query: SearchQuery) -> List[MediaItem]:
        if not self._api:
            return []
        out: List[MediaItem] = []
        q = (query.text or "").strip()
        try:
            if query.media_type in (None, "movie", "any"):
                resp = self._api.search_movies(query=q, page=1, limit=20)
                items = (resp or {}).get("data") or [] if (resp or {}).get("status") == "success" else []
                if not items and hasattr(self._api, "get_movies") and not q:
                    resp = self._api.get_movies(page=1, limit=20)
                    items = (resp or {}).get("data") or [] if (resp or {}).get("status") == "success" else []
                for it in items:
                    iid = str(it.get("id") or "")
                    if not iid:
                        continue
                    out.append(MediaItem(
                        id=f"nova:{iid}",
                        universal_id=f"nova:movie:{iid}",
                        title=str(it.get("title_ar") or it.get("title_en") or it.get("title") or ""),
                        original_title=str(it.get("title_en") or ""),
                        type=MediaType.MOVIE,
                        year=_num(it.get("year")),
                        poster=str(it.get("poster") or it.get("image") or it.get("cover") or ""),
                        overview=str(it.get("overview") or it.get("story") or it.get("description") or ""),
                        rating=_float(it.get("rating")),
                        countries=[str(c) for c in (it.get("countries") or it.get("country") or [])] if isinstance(it.get("countries") or it.get("country"), list) else ([str(it.get("country"))] if it.get("country") else []),
                        genres=[str(g) for g in (it.get("genres") or [])] if isinstance(it.get("genres"), list) else [],
                        source_ids=["nova"],
                        sources=[MediaSource(source_id="nova", external_id=iid)],
                    ))
            if query.media_type in (None, "series", "any"):
                resp = self._api.search_series(query=q, page=1, limit=20)
                items = (resp or {}).get("data") or [] if (resp or {}).get("status") == "success" else []
                if not items and hasattr(self._api, "get_series") and not q:
                    resp = self._api.get_series(page=1, limit=20)
                    items = (resp or {}).get("data") or [] if (resp or {}).get("status") == "success" else []
                for it in items:
                    iid = str(it.get("id") or "")
                    if not iid:
                        continue
                    out.append(MediaItem(
                        id=f"nova:{iid}",
                        universal_id=f"nova:series:{iid}",
                        title=str(it.get("title_ar") or it.get("title_en") or it.get("title") or ""),
                        original_title=str(it.get("title_en") or ""),
                        type=MediaType.SERIES,
                        year=_num(it.get("year")),
                        poster=str(it.get("poster") or it.get("image") or it.get("cover") or ""),
                        overview=str(it.get("overview") or it.get("story") or it.get("description") or ""),
                        rating=_float(it.get("rating")),
                        countries=[str(c) for c in (it.get("countries") or it.get("country") or [])] if isinstance(it.get("countries") or it.get("country"), list) else ([str(it.get("country"))] if it.get("country") else []),
                        genres=[str(g) for g in (it.get("genres") or [])] if isinstance(it.get("genres"), list) else [],
                        source_ids=["nova"],
                        sources=[MediaSource(source_id="nova", external_id=iid)],
                    ))
        except Exception:
            log.exception("nova search failed")
        return out

    async def get_details(self, item_id: str) -> Optional[MediaItem]:
        if not self._api:
            return None
        eid = item_id.split(":")[-1]
        try:
            resp = self._api.get_movie_details(eid)
            it = None
            if isinstance(resp, dict):
                it = resp.get("data") if resp.get("status") == "success" else resp
            if it and (it.get("id") or it.get("title") or it.get("title_ar")):
                return MediaItem(
                    id=f"nova:{eid}",
                    universal_id=f"nova:movie:{eid}",
                    title=str(it.get("title_ar") or it.get("title_en") or it.get("title") or ""),
                    original_title=str(it.get("title_en") or ""),
                    type=MediaType.MOVIE,
                    year=_num(it.get("year")),
                    poster=str(it.get("poster") or it.get("image") or ""),
                    overview=str(it.get("overview") or it.get("story") or ""),
                    rating=_float(it.get("rating")),
                    source_ids=["nova"],
                    sources=[MediaSource(source_id="nova", external_id=eid)],
                    extra={"raw": it},
                )
            resp = self._api.get_series_details(eid)
            it = None
            if isinstance(resp, dict):
                it = resp.get("data") if resp.get("status") == "success" else resp
            if it and (it.get("id") or it.get("title") or it.get("title_ar")):
                return MediaItem(
                    id=f"nova:{eid}",
                    universal_id=f"nova:series:{eid}",
                    title=str(it.get("title_ar") or it.get("title_en") or it.get("title") or ""),
                    original_title=str(it.get("title_en") or ""),
                    type=MediaType.SERIES,
                    year=_num(it.get("year")),
                    poster=str(it.get("poster") or it.get("image") or ""),
                    overview=str(it.get("overview") or it.get("story") or ""),
                    rating=_float(it.get("rating")),
                    source_ids=["nova"],
                    sources=[MediaSource(source_id="nova", external_id=eid)],
                    extra={"raw": it},
                )
        except Exception:
            log.exception("nova get_details failed")
        return None

    async def get_series_details(self, item_id: str) -> Optional[SeriesDetails]:
        if not self._api:
            return None
        eid = item_id.split(":")[-1]
        try:
            resp = self._api.get_series_details(eid)
            it = None
            if isinstance(resp, dict):
                it = resp.get("data") if resp.get("status") == "success" else resp
            if not it:
                return None
            item = MediaItem(
                id=f"nova:{eid}",
                universal_id=f"nova:series:{eid}",
                title=str(it.get("title_ar") or it.get("title_en") or it.get("title") or ""),
                original_title=str(it.get("title_en") or ""),
                type=MediaType.SERIES,
                year=_num(it.get("year")),
                poster=str(it.get("poster") or it.get("image") or ""),
                overview=str(it.get("overview") or it.get("story") or ""),
                rating=_float(it.get("rating")),
                source_ids=["nova"],
                sources=[MediaSource(source_id="nova", external_id=eid)],
            )
            seasons: List[Season] = []
            raw_seasons = it.get("seasons") or it.get("season") or []
            if isinstance(raw_seasons, list) and raw_seasons:
                for s in raw_seasons:
                    sn = _num(s.get("season_number") or s.get("number") or s.get("season"), 1) or 1
                    eps_raw = s.get("episodes") or []
                    eps = []
                    for e in eps_raw:
                        en = _num(e.get("episode_number") or e.get("number") or e.get("episode"), 0) or 0
                        eid_ep = str(e.get("id") or f"{eid}-s{sn}e{en}")
                        eps.append(Episode(
                            id=f"nova:{eid_ep}",
                            series_id=f"nova:{eid}",
                            season=sn,
                            number=en,
                            title=str(e.get("title") or e.get("name") or f"الحلقة {en}"),
                        ))
                    seasons.append(Season(number=sn, episode_count=len(eps) or _num(s.get("episodes_count"), 0) or 0, episodes=eps))
            else:
                if hasattr(self._api, "get_episodes"):
                    try:
                        ep_resp = self._api.get_episodes(eid)
                        ep_list = (ep_resp or {}).get("data") or [] if isinstance(ep_resp, dict) else (ep_resp or [])
                        by_season: Dict[int, List[Episode]] = {}
                        for e in ep_list:
                            sn = _num(e.get("season_number") or e.get("season"), 1) or 1
                            en = _num(e.get("episode_number") or e.get("number") or e.get("episode"), 0) or 0
                            eid_ep = str(e.get("id") or f"{eid}-s{sn}e{en}")
                            by_season.setdefault(sn, []).append(Episode(
                                id=f"nova:{eid_ep}",
                                series_id=f"nova:{eid}",
                                season=sn,
                                number=en,
                                title=str(e.get("title") or e.get("name") or f"الحلقة {en}"),
                            ))
                        for sn in sorted(by_season.keys()):
                            seasons.append(Season(number=sn, episode_count=len(by_season[sn]), episodes=by_season[sn]))
                    except Exception:
                        pass
            return SeriesDetails(item=item, seasons=seasons)
        except Exception:
            log.exception("nova get_series_details failed")
        return None

    async def get_sources(self, item_id: str, media_type: str = "movie") -> List[Dict[str, Any]]:
        if not self._api:
            return []
        eid = item_id.split(":")[-1]
        out: List[Dict[str, Any]] = []
        try:
            if hasattr(self._api, "get_watch_links"):
                resp = self._api.get_watch_links(item_id=eid)
                data = resp
                if isinstance(resp, dict):
                    data = resp.get("data") or resp.get("watch_links") or resp
                links = []
                if isinstance(data, list):
                    links = data
                elif isinstance(data, dict):
                    links = data.get("watch_links") or data.get("links") or data.get("sources") or []
                for ln in links or []:
                    if isinstance(ln, str) and ln.startswith("http"):
                        out.append({"url": ln, "source_id": "nova"})
                    elif isinstance(ln, dict):
                        url = (
                            ln.get("url") or ln.get("link") or ln.get("stream_url")
                            or ln.get("play_url") or ln.get("video_url") or ln.get("m3u8_url")
                            or ln.get("hls_url") or ln.get("file")
                        )
                        if url:
                            out.append({
                                "url": str(url),
                                "quality": ln.get("quality") or ln.get("label") or ln.get("resolution"),
                                "source_id": "nova",
                            })
            det = await self.get_details(item_id)
            if det and det.extra.get("raw"):
                raw = det.extra["raw"]
                for key in ("watch_links", "links", "sources", "streams", "play_links"):
                    for ln in (raw.get(key) or []):
                        if isinstance(ln, str) and ln.startswith("http"):
                            out.append({"url": ln, "source_id": "nova"})
                        elif isinstance(ln, dict):
                            url = (
                                ln.get("url") or ln.get("link") or ln.get("stream_url")
                                or ln.get("play_url") or ln.get("video_url")
                            )
                            if url:
                                out.append({"url": str(url), "source_id": "nova", "quality": ln.get("quality")})
        except Exception:
            log.exception("nova get_sources failed")
        return out

    async def get_categories(self) -> List[Dict[str, Any]]:
        return []

    async def health_check(self) -> Dict[str, Any]:
        return {"id": self.id, "ok": self._api is not None, "bound": self._api is not None}
