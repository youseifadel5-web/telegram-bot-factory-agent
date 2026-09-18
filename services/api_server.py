"""Authenticated HTTP control plane for live streams.

GET  /api/health
GET  /api/status
GET  /api/streams
GET  /api/streams/{id}
POST /api/streams/{id}/start|stop|restart
POST /api/streams/{id}/volume  JSON {"value": 0..2}
POST /api/streams/{id}/bitrate JSON {"value": "64k|128k|192k"}

Set API_KEY to protect the API; it is closed by default when unset.
"""
import logging
import os
from typing import Optional

logger = logging.getLogger(__name__)
_runner = None
_site = None


def _check_key(request) -> bool:
    expected = os.getenv("API_KEY", "").strip()
    return bool(expected) and request.headers.get("X-API-Key", "") == expected


def _stream_snapshot(stream_manager, sid: int) -> dict:
    meta = stream_manager.get_meta(sid) or {}
    running = stream_manager.is_running(sid)
    return {
        "stream_id": sid,
        "running": running,
        "healthy": stream_manager.is_healthy(sid),
        "state": stream_manager.get_state(sid),
        "pid": getattr(stream_manager.processes.get(sid), "pid", None),
        "volume": meta.get("volume", 1.0),
        "bitrate": meta.get("audio_bitrate", "128k"),
        "with_video": meta.get("with_video"),
        "restarts": meta.get("restarts", 0),
        "progress": meta.get("progress") or {},
        "last_error": meta.get("last_error", ""),
        "source_ok": bool(meta.get("data_flow") or meta.get("healthy")),
    }


async def _handle(request):
    from aiohttp import web
    if not _check_key(request):
        return web.json_response({"error": "unauthorized"}, status=401)
    path, method = request.path, request.method
    try:
        from database import db
        from services.stream import stream_manager
    except Exception as e:
        return web.json_response({"error": type(e).__name__}, status=500)

    if path == "/api/health" and method == "GET":
        return web.json_response({"ok": True, "ffmpeg": stream_manager.has_ffmpeg(), "active": len(stream_manager.processes)})
    if path == "/api/status" and method == "GET":
        from services.system_monitor import cpu_percent, ram_info
        ru, rt = ram_info()
        return web.json_response({"ok": True, "cpu": cpu_percent(), "ram_used": ru, "ram_total": rt,
                                  "ffmpeg": stream_manager.has_ffmpeg(),
                                  "streams_running": sum(stream_manager.is_running(sid) for sid in stream_manager.processes)})
    if path == "/api/streams" and method == "GET":
        rows = await db.get_all_streams()
        return web.json_response({"streams": [{"id": s["id"], "title": s.get("title"), "status": s.get("status"),
                                                 "live": _stream_snapshot(stream_manager, int(s["id"]))} for s in rows[:50]]})

    parts = path.strip("/").split("/")
    if len(parts) < 3 or parts[0] != "api" or parts[1] != "streams":
        return web.json_response({"error": "not found"}, status=404)
    try:
        sid = int(parts[2])
    except ValueError:
        return web.json_response({"error": "invalid id"}, status=400)
    s = await db.get_stream(sid)
    if not s:
        return web.json_response({"error": "not found"}, status=404)
    if len(parts) == 3 and method == "GET":
        return web.json_response({"ok": True, "stream": s, "live": _stream_snapshot(stream_manager, sid)})
    if len(parts) != 4 or method != "POST":
        return web.json_response({"error": "not found"}, status=404)
    action = parts[3]
    if action == "stop":
        stream_manager.stop_stream(sid); await db.update_stream_status(sid, "stopped")
        return web.json_response({"ok": True, "live": _stream_snapshot(stream_manager, sid)})
    if action in ("start", "restart"):
        if action == "restart": stream_manager.stop_stream(sid)
        if not s.get("rtmp_url") or not s.get("source_url"):
            return web.json_response({"error": "missing rtmp/source"}, status=400)
        pid = stream_manager.start_stream(sid, s["source_url"], s["rtmp_url"])
        if not pid: return web.json_response({"error": "start failed", "live": _stream_snapshot(stream_manager, sid)}, status=500)
        await db.update_stream_status(sid, "running", pid)
        return web.json_response({"ok": True, "pid": pid, "live": _stream_snapshot(stream_manager, sid)})
    if action in ("volume", "bitrate"):
        try: body = await request.json()
        except Exception: body = {}
        if action == "volume":
            try: value = max(0.0, min(2.0, float(body.get("value"))))
            except Exception: return web.json_response({"error": "value must be 0..2"}, status=400)
            ok = stream_manager.set_volume(sid, value)
        else:
            value = str(body.get("value", ""))
            if value not in {"64k", "128k", "192k"}: return web.json_response({"error": "unsupported bitrate"}, status=400)
            ok = stream_manager.set_bitrate(sid, value)
        return web.json_response({"ok": bool(ok), "live": _stream_snapshot(stream_manager, sid)})
    return web.json_response({"error": "unsupported action"}, status=400)


async def start_api_server(host: str = "0.0.0.0", port: int = None):
    global _runner, _site
    port = port or int(os.getenv("API_PORT", "8088"))
    try:
        from aiohttp import web
    except ImportError:
        logger.warning("aiohttp missing — API server disabled"); return
    app = web.Application(); app.router.add_route("*", "/{path:.*}", _handle)
    _runner = web.AppRunner(app); await _runner.setup(); _site = web.TCPSite(_runner, host, port)
    try: await _site.start(); logger.info("API server on %s:%s", host, port)
    except Exception as e: logger.warning("API server failed to bind %s:%s — %s", host, port, e)


async def stop_api_server():
    global _runner, _site
    try:
        if _site: await _site.stop()
        if _runner: await _runner.cleanup()
    except Exception: pass
    _runner = _site = None
