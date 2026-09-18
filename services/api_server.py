"""Lightweight HTTP API for stream control (Phase 3).

Endpoints:
  GET  /api/health
  GET  /api/streams
  POST /api/streams/{id}/start
  POST /api/streams/{id}/stop
  GET  /api/status

Auth: header X-API-Key matching API_KEY env (optional if empty).
"""
import asyncio
import logging
import os
from typing import Optional

logger = logging.getLogger(__name__)

_runner = None
_site = None


def _check_key(request) -> bool:
    expected = os.getenv("API_KEY", "").strip()
    if not expected:
        return True  # open if not configured
    return request.headers.get("X-API-Key", "") == expected


async def _handle(request):
    from aiohttp import web
    if not _check_key(request):
        return web.json_response({"error": "unauthorized"}, status=401)

    path = request.path
    method = request.method

    try:
        from database import db
        from services.stream import stream_manager
    except Exception as e:
        return web.json_response({"error": str(e)}, status=500)

    if path == "/api/health" and method == "GET":
        return web.json_response({
            "ok": True,
            "ffmpeg": stream_manager.has_ffmpeg(),
            "active": len(stream_manager.processes),
        })

    if path == "/api/streams" and method == "GET":
        streams = await db.get_all_streams()
        return web.json_response({
            "streams": [
                {
                    "id": s["id"],
                    "title": s.get("title"),
                    "status": s.get("status"),
                    "user_id": s.get("user_id"),
                }
                for s in streams[:50]
            ]
        })

    if path == "/api/status" and method == "GET":
        from services.system_monitor import cpu_percent, ram_info
        ru, rt = ram_info()
        return web.json_response({
            "cpu": cpu_percent(),
            "ram_used": ru,
            "ram_total": rt,
            "ffmpeg": stream_manager.has_ffmpeg(),
            "streams_running": sum(1 for sid in stream_manager.processes if stream_manager.is_running(sid)),
        })

    # /api/streams/{id}/start|stop
    parts = path.strip("/").split("/")
    if len(parts) == 4 and parts[0] == "api" and parts[1] == "streams":
        try:
            sid = int(parts[2])
        except ValueError:
            return web.json_response({"error": "invalid id"}, status=400)
        action = parts[3]
        s = await db.get_stream(sid)
        if not s:
            return web.json_response({"error": "not found"}, status=404)
        if action == "stop" and method == "POST":
            stream_manager.stop_stream(sid)
            await db.update_stream_status(sid, "stopped")
            return web.json_response({"ok": True, "status": "stopped"})
        if action == "start" and method == "POST":
            if not s.get("rtmp_url") or not s.get("source_url"):
                return web.json_response({"error": "missing rtmp/source"}, status=400)
            pid = stream_manager.start_stream(sid, s["source_url"], s["rtmp_url"])
            if pid:
                await db.update_stream_status(sid, "running", pid)
                return web.json_response({"ok": True, "status": "running", "pid": pid})
            return web.json_response({"error": "start failed"}, status=500)

    return web.json_response({"error": "not found"}, status=404)


async def start_api_server(host: str = "0.0.0.0", port: int = None):
    global _runner, _site
    port = port or int(os.getenv("API_PORT", "8088"))
    try:
        from aiohttp import web
    except ImportError:
        logger.warning("aiohttp missing — API server disabled")
        return
    app = web.Application()
    app.router.add_route("*", "/api/{tail:.*}", _handle)
    app.router.add_get("/api/health", _handle)
    app.router.add_get("/api/streams", _handle)
    app.router.add_get("/api/status", _handle)
    # also catch subpaths via middleware-style single handler
    app.router.add_route("*", "/{path:.*}", _handle)

    _runner = web.AppRunner(app)
    await _runner.setup()
    _site = web.TCPSite(_runner, host, port)
    try:
        await _site.start()
        logger.info("API server on %s:%s", host, port)
    except Exception as e:
        logger.warning("API server failed to bind %s:%s — %s", host, port, e)


async def stop_api_server():
    global _runner, _site
    try:
        if _site:
            await _site.stop()
        if _runner:
            await _runner.cleanup()
    except Exception:
        pass
    _runner = _site = None
