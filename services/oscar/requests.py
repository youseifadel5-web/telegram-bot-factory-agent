"""Oscar POST endpoints — only call when a feature explicitly needs them."""
from __future__ import annotations
from typing import Any, Dict, Optional
from services.oscar.client import oscar_client


async def sync_log(payload: dict) -> Any:
    return await oscar_client.post("/api/app/sync-log.php", payload)


async def cls_log(payload: dict) -> Any:
    return await oscar_client.post("/api/app/cls-log.php", payload)


async def store_comment(payload: dict) -> Any:
    return await oscar_client.post("/api/comments/store.php", payload)


async def match_prediction(payload: dict) -> Any:
    return await oscar_client.post("/api/matches/predictions.php", payload)


async def comment_react(payload: dict) -> Any:
    return await oscar_client.post("/api/comments/react.php", payload)


async def comment_report(payload: dict) -> Any:
    return await oscar_client.post("/api/comments/report.php", payload)


async def series_broadcast_subscribe(payload: dict) -> Any:
    return await oscar_client.post("/api/series/broadcast_subscribe.php", payload)


async def movie_request(payload: dict) -> Any:
    return await oscar_client.post("/api/movie_requests/store.php", payload)


async def series_request(payload: dict) -> Any:
    return await oscar_client.post("/api/series_requests/store.php", payload)


async def anime_request(payload: dict) -> Any:
    return await oscar_client.post("/api/anime_requests/store.php", payload)


async def channel_request(payload: dict) -> Any:
    return await oscar_client.post("/api/channel_requests/store.php", payload)


async def content_report(payload: dict) -> Any:
    return await oscar_client.post("/api/content_reports/store.php", payload)


async def track_view_movie(payload: dict) -> Any:
    return await oscar_client.post("/api/movies/view.php", payload)


async def track_view_series(payload: dict) -> Any:
    return await oscar_client.post("/api/series/view.php", payload)


async def track_view_anime(payload: dict) -> Any:
    return await oscar_client.post("/api/anime/view.php", payload)


async def track_view_channel(payload: dict) -> Any:
    return await oscar_client.post("/api/channels/view.php", payload)
