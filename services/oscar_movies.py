"""OscarTV (ostvapp.cam) movies & series client — high quality sources.

Uses local Iron header signing (same algorithm as the PHP generator)
with optional fallback to the external proxy.
"""
from __future__ import annotations
import logging
from typing import Any, Dict, List, Optional
from urllib.parse import urlencode
import aiohttp

logger = logging.getLogger(__name__)

OSCAR_PROXY = "https://mode.giize.com/OscarTV.php"
BASE = "https://ostvapp.cam"
BASE_MEDIA = "https://ostvapp.cam"

MOVIES_URL = f"{BASE}/api/movies/"
MOVIE_DETAILS = f"{BASE}/api/movies/show.php"
SERIES_URL = f"{BASE}/api/series/"
SERIES_DETAILS = f"{BASE}/api/series/show.php"
EPISODES_URL = f"{BASE}/api/episodes/"
EPISODE_DETAILS = f"{BASE}/api/episodes/show.php"
ANIME_URL = f"{BASE}/api/anime/"
ANIME_DETAILS = f"{BASE}/api/anime/show.php"
ANIME_EPISODES_URL = f"{BASE}/api/anime/episodes/"
ANIME_EPISODE_DETAILS = f"{BASE}/api/anime/episodes/show.php"


class OscarMovies:
    def __init__(self, timeout: int = 25):
        self.timeout = timeout

    def _local_iron_headers(self, target_url: str) -> dict:
        """Generate Iron headers locally (PHP algorithm port)."""
        try:
            from services.iron_headers import iron_headers_for
            return iron_headers_for(target_url)
        except Exception as e:
            logger.warning("local iron headers: %s", e)
            return {}

    async def _proxy_headers(self, session: aiohttp.ClientSession, target_url: str) -> dict:
        """Fallback: fetch headers from external PHP proxy."""
        try:
            async with session.post(
                OSCAR_PROXY, data={"link": target_url},
                timeout=aiohttp.ClientTimeout(total=self.timeout),
            ) as resp:
                if resp.status != 200:
                    return {}
                data = await resp.json(content_type=None)
                if isinstance(data, dict) and "headers" in data:
                    data = data["headers"]
                if isinstance(data, dict):
                    return {str(k): str(v) for k, v in data.items() if isinstance(v, (str, int, float))}
        except Exception as e:
            logger.warning("oscar proxy headers: %s", e)
        return {}

    async def _headers(self, session: aiohttp.ClientSession, target_url: str) -> dict:
        # Prefer local Iron signing — no external dependency
        headers = self._local_iron_headers(target_url)
        if headers.get("x-iron-sig"):
            return headers
        return await self._proxy_headers(session, target_url)

    async def _get(self, url: str, params: dict = None) -> Optional[dict]:
        # Prefer unified OscarClient (Iron + retry + cache)
        try:
            from services.oscar.client import oscar_client
            path = url
            if url.startswith(BASE):
                path = url[len(BASE):] or "/"
            return await oscar_client.get(path, params)
        except Exception as e:
            logger.debug("oscar_client fallback: %s", e)
        try:
            full = url
            if params:
                full = url + ("?" + urlencode({k: v for k, v in params.items()}))
            async with aiohttp.ClientSession() as session:
                headers = await self._headers(session, full)
                async with session.get(
                    url, headers=headers or None, params=params,
                    timeout=aiohttp.ClientTimeout(total=self.timeout),
                ) as resp:
                    if resp.status != 200:
                        logger.warning("oscar HTTP %s for %s", resp.status, url)
                        return None
                    return await resp.json(content_type=None)
        except Exception as e:
            logger.warning("oscar get %s: %s", url, e)
            return None

    async def search_movies(self, query: str, page: int = 1, limit: int = 20) -> List[Dict]:
        res = await self._get(MOVIES_URL, {"page": page, "limit": limit, "search": query, "app_version": 15})
        if not res or res.get("status") != "success":
            return []
        return self._normalize_list(res.get("data") or [], kind="movie")

    async def get_movies(self, page: int = 1, limit: int = 20, sort_by: str = "most_viewed") -> List[Dict]:
        res = await self._get(MOVIES_URL, {"page": page, "limit": limit, "sort_by": sort_by, "app_version": 15})
        if not res or res.get("status") != "success":
            return []
        return self._normalize_list(res.get("data") or [], kind="movie")

    async def get_movie_details(self, movie_id: int) -> Optional[Dict]:
        res = await self._get(MOVIE_DETAILS, {"id": movie_id})
        if not res or res.get("status") != "success":
            return None
        return self._normalize_detail(res.get("data") or {}, kind="movie")

    async def search_series(self, query: str, page: int = 1, limit: int = 20) -> List[Dict]:
        res = await self._get(SERIES_URL, {"page": page, "limit": limit, "search": query, "app_version": 15})
        if not res or res.get("status") != "success":
            return []
        return self._normalize_list(res.get("data") or [], kind="series")

    async def get_series(self, page: int = 1, limit: int = 20, sort_by: str = "most_viewed") -> List[Dict]:
        res = await self._get(SERIES_URL, {"page": page, "limit": limit, "sort_by": sort_by, "app_version": 15})
        if not res or res.get("status") != "success":
            return []
        return self._normalize_list(res.get("data") or [], kind="series")

    async def get_anime_movies(self, page: int = 1, limit: int = 12) -> List[Dict]:
        res = await self._get(ANIME_URL, {"page": page, "limit": limit, "anime_type": "movie"})
        if not res or res.get("status") != "success": return []
        return self._normalize_list(res.get("data") or [], kind="anime")

    async def get_anime_series(self, page: int = 1, limit: int = 12) -> List[Dict]:
        res = await self._get(ANIME_URL, {"page": page, "limit": limit, "anime_type": "tv,ova,ona,special", "sort_by": "latest_episode"})
        if not res or res.get("status") != "success": return []
        return self._normalize_list(res.get("data") or [], kind="anime")

    async def search_anime(self, query: str, page: int = 1, limit: int = 20) -> List[Dict]:
        res = await self._get(ANIME_URL, {"page": page, "limit": limit, "search": query})
        if not res or res.get("status") != "success":
            return []
        return self._normalize_list(res.get("data") or [], kind="anime")

    async def get_anime_details(self, anime_id: int) -> Optional[Dict]:
        res = await self._get(ANIME_DETAILS, {"id": anime_id})
        if not res or res.get("status") != "success":
            return None
        return self._normalize_detail(res.get("data") or {}, kind="anime")

    async def get_anime_episodes(self, anime_id: int, page: int = 1, per_page: int = 20, season_id: int = None) -> List[Dict]:
        params = {"anime_id": anime_id, "page": page, "per_page": per_page}
        if season_id:
            params["season_id"] = season_id
        res = await self._get(ANIME_EPISODES_URL, params)
        if not res or res.get("status") != "success":
            return []
        return res.get("data") or []

    async def get_anime_episode_details(self, episode_id: int) -> Optional[Dict]:
        res = await self._get(ANIME_EPISODE_DETAILS, {"id": episode_id})
        if not res or res.get("status") != "success":
            return None
        return res.get("data") or {}

    async def get_series_details(self, series_id: int) -> Optional[Dict]:
        res = await self._get(SERIES_DETAILS, {"id": series_id})
        if not res or res.get("status") != "success":
            return None
        return self._normalize_detail(res.get("data") or {}, kind="series")

    async def get_season_episodes(self, season_id: int, page: int = 1) -> List[Dict]:
        res = await self._get(EPISODES_URL, {"season_id": season_id, "page": page, "per_page": 20, "sort": "asc"})
        if not res or res.get("status") != "success":
            return []
        return res.get("data") or []

    async def get_episode_details(self, episode_id: int) -> Optional[Dict]:
        res = await self._get(EPISODE_DETAILS, {"id": episode_id})
        if not res or res.get("status") != "success":
            return None
        return res.get("data")

    def _normalize_list(self, items: list, kind: str) -> List[Dict]:
        out = []
        for m in items:
            if not isinstance(m, dict):
                continue
            title = m.get("title_ar") or m.get("title_en") or m.get("title") or "—"
            poster = m.get("poster") or ""
            if poster and str(poster).startswith("/"):
                poster = BASE_MEDIA + poster
            out.append({
                "id": m.get("id"),
                "title": title,
                "title_en": m.get("title_en") or "",
                "year": m.get("release_year") or m.get("year") or "",
                "rating": m.get("rating") or "",
                "poster": poster,
                "kind": kind,
                "source": "oscar",
            })
        return out

    def _normalize_detail(self, m: dict, kind: str) -> Dict:
        title = m.get("title_ar") or m.get("title_en") or m.get("title") or "—"
        poster = m.get("poster") or ""
        if poster and str(poster).startswith("/"):
            poster = BASE_MEDIA + poster
        watch = []
        download = []
        for link in (m.get("watch_links") or []):
            if isinstance(link, dict) and link.get("url"):
                watch.append({
                    "label": link.get("server_name") or "سيرفر",
                    "quality": link.get("quality") or link.get("resolution") or link.get("label") or "",
                    "size": link.get("file_size") or link.get("size") or "",
                    "url": link["url"],
                    "type": "watch",
                })
        for raw_group in ((m.get("download_links") or []), (m.get("downloads") or [])):
            if isinstance(raw_group, dict):
                raw_group = list(raw_group.values())
            for link in raw_group:
                if isinstance(link, str) and link.strip():
                    download.append({"label": "تحميل", "quality": "", "size": "", "url": link.strip()})
                elif isinstance(link, dict):
                    url = link.get("url") or link.get("link") or link.get("download_url") or link.get("stream_url")
                    if url:
                        download.append({
                            "label": link.get("quality") or link.get("label") or "تحميل",
                            "quality": link.get("quality") or link.get("resolution") or "",
                            "size": link.get("file_size") or link.get("size") or "",
                            "url": url,
                            "type": "download",
                        })
        # also sources field; preserve explicit download sources separately.
        raw_sources = m.get("sources") or []
        if isinstance(raw_sources, dict):
            raw_sources = list(raw_sources.values())
        for s in raw_sources:
            if isinstance(s, dict):
                url = s.get("streamUrl") or s.get("stream_url") or s.get("url") or s.get("link")
                if url:
                    target = download if str(s.get("type") or s.get("kind") or "").lower() in ("download", "downloads") else watch
                    target.append({
                        "label": s.get("label") or s.get("server_name") or "سيرفر",
                        "quality": s.get("quality") or s.get("resolution") or "",
                        "size": s.get("file_size") or s.get("size") or "",
                        "url": url,
                    })

        seasons = m.get("seasons") or []
        return {
            "id": m.get("id"),
            "title": title,
            "title_en": m.get("title_en") or "",
            "year": m.get("release_year") or "",
            "rating": m.get("rating") or "",
            "story": m.get("story") or m.get("description") or "",
            "poster": poster,
            "poster_url": m.get("poster_url") or m.get("posterUrl") or m.get("image") or m.get("image_url") or "",
            "genres": m.get("genres") or [],
            "watch_links": watch,
            "download_links": download,
            "seasons": seasons,
            "kind": kind,
            "source": "oscar",
        }


oscar_api = OscarMovies()
