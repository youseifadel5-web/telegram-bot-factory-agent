"""Safe AI action layer.

AI can call only these registered actions. No shell/exec/eval capability is exposed.
"""
from __future__ import annotations
from typing import Any, Dict

from database import db
from services.source_probe import probe_source
from services.stream import stream_manager


def _mask_rtmp(value: str) -> str:
    if not value:
        return ""
    if "://" not in value:
        return "***"
    head, tail = value.split("://", 1)
    if "/" in tail:
        host, rest = tail.split("/", 1)
        if ":" in rest:
            base, key = rest.rsplit(":", 1)
            return f"{head}://{host}/{base}:***"
    return f"{head}://{tail}"


async def search_movies(query: str, limit: int = 8) -> list:
    from services import cinema
    return await cinema.search(query, limit=limit)


async def get_movie(movie_id: int, source: str = "oscar") -> Dict[str, Any] | None:
    from services import cinema
    if source == "hekaya":
        from services import hekaya
        return await hekaya.get_movie_by_id(movie_id)
    return await cinema.details("movie", movie_id)


async def get_watch_links(item: Dict[str, Any]) -> list:
    links = item.get("links") or []
    return [x for x in links if isinstance(x, dict) and x.get("url") and x.get("type") != "download"]


async def probe_source_action(url: str, headers: Dict[str, str] | None = None, quality: str = "best") -> Dict[str, Any]:
    return probe_source(url, headers=headers, quality=quality)


async def select_quality(links: list, quality: str = "best") -> Dict[str, Any] | None:
    valid = [x for x in links if isinstance(x, dict) and x.get("url")]
    if not valid:
        return None
    q = str(quality or "best").lower()
    if q in ("best", "highest", "max"):
        return valid[-1]
    for x in valid:
        label = str(x.get("quality") or x.get("resolution") or "").lower()
        if q in label:
            return x
    return valid[0]


async def get_saved_rtmp(user_id: int) -> Dict[str, Any] | None:
    profile = await db.get_default_rtmp_profile(user_id)
    if not profile:
        return None
    base = str(profile.get("rtmp_base") or "")
    key = str(profile.get("stream_key") or "")
    return {"id": profile.get("id"), "name": profile.get("name") or "الافتراضي", "rtmp_base": base, "has_key": bool(key),
            "rtmp_preview": _mask_rtmp(base.rstrip("/") + "/" + key.lstrip("/")) if base and key else _mask_rtmp(base)}


async def create_stream(user_id: int, title: str, source_url: str, rtmp_url: str | None = None) -> int:
    return await db.create_stream(user_id, title, source_url, rtmp_url)


async def start_stream(user_id: int, stream_id: int, source_url: str, rtmp_url: str, headers: Dict[str, str] | None = None) -> Dict[str, Any]:
    probe = probe_source(source_url, headers=headers)
    if not probe.get("ok"):
        return {"ok": False, "error_code": "SOURCE_INVALID_DATA", "error": probe.get("error") or "فشل فحص المصدر", "probe": probe}
    pid = stream_manager.start_stream(
        stream_id, source_url, rtmp_url,
        with_video=bool(probe.get("has_video")),
        extra_headers=headers,
        media_kind=probe.get("media_kind") or "unknown",
        has_audio=probe.get("has_audio"),
        has_video=probe.get("has_video"),
        force_video_for_audio=not bool(probe.get("has_video")),
        source_type=probe.get("source_type") or "",
        probe_result=probe,
    )
    if not pid:
        return {"ok": False, "error_code": stream_manager.get_meta(stream_id).get("error_code") or "STREAM_START_FAILED",
                "error": stream_manager.get_meta(stream_id).get("last_error") or "تعذر بدء البث"}
    return {"ok": True, "pid": pid, "state": stream_manager.get_state(stream_id), "probe": probe}


async def stop_stream(stream_id: int) -> bool:
    ok = stream_manager.stop_stream(stream_id)
    try:
        await db.update_stream_status(stream_id, "stopped")
    except Exception:
        pass
    return ok


async def restart_stream(stream_id: int) -> Dict[str, Any]:
    pid = stream_manager.restart_stream(stream_id)
    return {"ok": bool(pid), "pid": pid, "state": stream_manager.get_state(stream_id)}


async def stream_status(stream_id: int) -> Dict[str, Any]:
    meta = stream_manager.get_meta(stream_id)
    return {"stream_id": stream_id, "state": stream_manager.get_state(stream_id), "healthy": stream_manager.is_healthy(stream_id),
            "error_code": meta.get("error_code"), "error": meta.get("last_error"), "reconnects": meta.get("restarts", 0)}


async def list_current_streams() -> list:
    return [{"stream_id": sid, **await stream_status(sid)} for sid in list(stream_manager.processes.keys())]


TOOLS = {
    "search_movies": search_movies,
    "get_movie": get_movie,
    "get_watch_links": get_watch_links,
    "probe_source": probe_source_action,
    "select_quality": select_quality,
    "get_saved_rtmp": get_saved_rtmp,
    "create_stream": create_stream,
    "start_stream": start_stream,
    "stop_stream": stop_stream,
    "restart_stream": restart_stream,
    "stream_status": stream_status,
    "list_current_streams": list_current_streams,
}


async def call_tool(name: str, **kwargs):
    fn = TOOLS.get(name)
    if not fn:
        raise ValueError("unsupported AI action")
    return await fn(**kwargs)
