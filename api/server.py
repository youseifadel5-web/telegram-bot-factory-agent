# -*- coding: utf-8 -*-
"""Modular REST API bridge for the existing Youseif Telegram bot/content source."""
import asyncio
import os
import re
import time
from collections import defaultdict, deque
from typing import Optional
from urllib.parse import urljoin

import httpx
from fastapi import FastAPI, Header, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, PlainTextResponse, StreamingResponse

from .auth import AuthStore

app = FastAPI(title="Youseif API", version="1.0.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[x.strip() for x in os.getenv("API_CORS_ORIGINS", "*").split(",") if x.strip()] or ["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

AUTH = AuthStore()
_RUNTIME = {"youseif": None, "bot_username": os.getenv("BOT_USERNAME", "").strip()}
_RATE = defaultdict(deque)
_CLIENT: Optional[httpx.AsyncClient] = None
_API_BASE = os.getenv("API_BASE_URL", "http://127.0.0.1:8000").strip().rstrip("/")
PUBLIC_BASE = os.getenv("API_PUBLIC_BASE_URL", "").strip().rstrip("/") or _API_BASE


def configure(youseif=None, bot_username: str = ""):
    if youseif is not None:
        _RUNTIME["youseif"] = youseif
    if bot_username:
        _RUNTIME["bot_username"] = bot_username


def _client():
    global _CLIENT
    if _CLIENT is None or _CLIENT.is_closed:
        _CLIENT = httpx.AsyncClient(timeout=httpx.Timeout(30, read=120), follow_redirects=True,
                                    headers={"User-Agent": "Youseif-API/1.0"})
    return _CLIENT


@app.on_event("shutdown")
async def _shutdown():
    global _CLIENT
    if _CLIENT and not _CLIENT.is_closed:
        await _CLIENT.aclose()


def _rate(request: Request, key: str, limit=12, window=60):
    host = request.client.host if request.client else "unknown"
    now = time.time()
    q = _RATE[f"{key}:{host}"]
    while q and q[0] <= now - window:
        q.popleft()
    if len(q) >= limit:
        raise HTTPException(429, "Too many requests")
    q.append(now)


def _bearer(authorization: Optional[str]) -> str:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(401, "Missing Bearer session token")
    return authorization[7:].strip()


def current_user(authorization: Optional[str]):
    token = _bearer(authorization)
    user = AUTH.user_for_session(token)
    if not user:
        raise HTTPException(401, "Invalid or expired session")
    return user


def _require(user, permission):
    if permission not in AUTH.permissions(user):
        raise HTTPException(403, "Permission denied")


def _core():
    core = _RUNTIME.get("youseif")
    if core is None:
        raise HTTPException(503, "Bot content service is not ready")
    return core


def _label(item, type_):
    name = item.get("name") or item.get("title") or "Untitled"
    poster = item.get("stream_icon") or item.get("cover") or item.get("cover_big") or ""
    category = item.get("category_name") or item.get("category") or item.get("group") or ""
    return {
        "id": f"{type_}_{item.get('stream_id') or item.get('series_id')}",
        "title": str(name),
        "type": type_,
        "poster": str(poster or ""),
        "description": str(item.get("plot") or item.get("description") or ""),
        "year": item.get("year") or (str(item.get("releaseDate") or "")[:4] or None),
        "category": str(category or ""),
    }


async def _items(type_: str):
    core = _core()
    return await core.store.all_items(type_)


async def _content_list(type_filter: Optional[str] = None):
    out = []
    if type_filter in (None, "movie", "movies", "anime"):
        movies = await _items("movie")
        for x in movies:
            it = _label(x, "movie")
            hay = (it["title"] + " " + it["category"]).lower()
            if type_filter == "anime" and "anime" not in hay and "انمي" not in hay:
                continue
            out.append(it)
    if type_filter in (None, "series", "anime"):
        series = await _items("series")
        for x in series:
            it = _label(x, "series")
            hay = (it["title"] + " " + it["category"]).lower()
            if type_filter == "anime" and "anime" not in hay and "انمي" not in hay:
                continue
            out.append(it)
    return out


@app.get("/api/health")
async def health():
    return {"success": True, "service": "youseif-api", "ready": _RUNTIME.get("youseif") is not None}


@app.post("/api/auth/request")
async def auth_request(request: Request):
    _rate(request, "auth_request", 8, 60)
    req = AUTH.create_login_request()
    username = _RUNTIME.get("bot_username")
    if not username:
        raise HTTPException(503, "Telegram bot username is not configured")
    req["login_url"] = f"https://t.me/{username}?start={req['request_id']}"
    return {"success": True, **req}


@app.get("/api/auth/status/{request_id}")
async def auth_status(request_id: str, request: Request):
    _rate(request, "auth_status", 30, 60)
    row = AUTH.login_status(request_id)
    if not row:
        raise HTTPException(404, "Login request not found")
    if row["expires_at"] < int(time.time()):
        return {"success": True, "status": "expired", "expires_at": _iso(row["expires_at"])}
    if not row["completed_at"] or not row["telegram_id"]:
        return {"success": True, "status": "pending", "expires_at": _iso(row["expires_at"])}
    session = AUTH.session_for_request(request_id, row["telegram_id"])
    user = AUTH.user_for_session(session["token"])
    return {"success": True, "status": "completed",
            "user": _public_user(user), "session": session}


def _public_user(user):
    if not user:
        return None
    return {
        "id": int(user["telegram_id"]),
        "telegram_id": int(user["telegram_id"]),
        "username": user.get("username") or "",
        "first_name": user.get("first_name") or "",
        "last_name": user.get("last_name") or "",
        "role": user.get("role") or "user",
        "permissions": AUTH.permissions(user),
    }


@app.get("/api/me")
async def me(authorization: Optional[str] = Header(default=None)):
    user = current_user(authorization)
    return {"success": True, "user": _public_user(user)}


@app.post("/api/auth/logout")
async def logout(authorization: Optional[str] = Header(default=None)):
    token = _bearer(authorization)
    return {"success": True, "revoked": AUTH.revoke(token)}


@app.get("/api/content")
async def content(authorization: Optional[str] = Header(default=None)):
    user = current_user(authorization); _require(user, "content.read")
    return {"success": True, "items": await _content_list()}


@app.get("/api/content/movies")
async def movies(authorization: Optional[str] = Header(default=None)):
    user = current_user(authorization); _require(user, "content.read")
    return {"success": True, "items": await _content_list("movies")}


@app.get("/api/content/series")
async def series(authorization: Optional[str] = Header(default=None)):
    user = current_user(authorization); _require(user, "content.read")
    return {"success": True, "items": await _content_list("series")}


@app.get("/api/content/anime")
async def anime(authorization: Optional[str] = Header(default=None)):
    user = current_user(authorization); _require(user, "content.read")
    return {"success": True, "items": await _content_list("anime")}


@app.get("/api/content/categories")
async def categories(authorization: Optional[str] = Header(default=None)):
    user = current_user(authorization); _require(user, "content.read")
    core = _core()
    cats = {}
    for typ in ("movie", "series"):
        raw = await core.store.categories(typ)
        cats[typ] = [{"id": str(x.get("category_id", "")), "name": str(x.get("category_name", ""))}
                     for x in raw]
    return {"success": True, "categories": cats}


async def _find_content(content_id: str):
    m = re.match(r"^(movie|series|live)_(.+)$", content_id)
    if not m:
        return None, None
    typ, raw_id = m.group(1), m.group(2)
    items = await _items(typ)
    key = "series_id" if typ == "series" else "stream_id"
    for item in items:
        if str(item.get(key)) == raw_id:
            return typ, item
    return None, None


@app.get("/api/content/{content_id}")
async def content_detail(content_id: str, authorization: Optional[str] = Header(default=None)):
    user = current_user(authorization); _require(user, "content.read")
    typ, item = await _find_content(content_id)
    if not item:
        raise HTTPException(404, "Content not found")
    result = _label(item, typ)
    if typ == "movie":
        result["extension"] = item.get("container_extension") or "mp4"
        result["rating"] = item.get("rating")
        result["duration"] = item.get("duration")
    elif typ == "series":
        info = await _core().store.series_info(item.get("series_id"))
        inf = info.get("info") or {}
        result.update({
            "description": inf.get("plot") or result["description"],
            "poster": inf.get("cover") or inf.get("cover_big") or result["poster"],
            "rating": inf.get("rating"),
            "seasons": info.get("seasons") or [],
            "episodes": info.get("episodes") or {},
        })
    return {"success": True, "item": result}


async def _source_for(content_id: str, episode_id: Optional[str] = None):
    typ, item = await _find_content(content_id)
    if not item:
        raise HTTPException(404, "Content not found")
    core = _core()
    if typ == "movie":
        ext = item.get("container_extension") or "mp4"
        return core.xt.movie_url(item.get("stream_id"), ext), "video/" + ("mp4" if ext == "mp4" else ext)
    if typ == "live":
        return core.xt.live_url(item.get("stream_id")), "application/vnd.apple.mpegurl"
    if typ == "series" and episode_id:
        info = await core.store.series_info(item.get("series_id"))
        for eps in (info.get("episodes") or {}).values():
            for ep in (eps or []):
                if str(ep.get("id")) == str(episode_id):
                    return core.xt.episode_url(ep.get("id"), ep.get("container_extension") or "mp4"), "video/mp4"
        raise HTTPException(404, "Episode not found")
    raise HTTPException(400, "Series playback requires episode_id")


@app.get("/api/stream/{content_id}")
async def stream(content_id: str, request: Request, episode_id: Optional[str] = None, authorization: Optional[str] = Header(default=None)):
    user = current_user(authorization); _require(user, "stream.play")
    source, mime = await _source_for(content_id, episode_id)
    token, exp = AUTH.issue_stream_token(user["telegram_id"], content_id, source, mime)
    return {"success": True, "stream": {
        "url": f"{PUBLIC_BASE}/api/stream/media/{token}",
        "type": "hls" if mime == "application/vnd.apple.mpegurl" else "http",
        "mime": mime, "expires_at": exp
    }}


async def _resolve_proxy(raw: str):
    row = AUTH.stream_token(raw)
    if row:
        return row
    return AUTH.proxy_token(raw)


def _same_origin(a, b):
    try:
        from urllib.parse import urlparse
        return urlparse(a).netloc == urlparse(b).netloc
    except Exception:
        return False


async def _proxy_response(row, request: Request):
    url = row["source_url"]
    headers = {}
    if request.headers.get("range"):
        headers["Range"] = request.headers["range"]
    client = _client()
    req = client.build_request("GET", url, headers=headers)
    r = await client.send(req, stream=True)
    ct = (r.headers.get("content-type") or row.get("mime") or "").lower()
    if "mpegurl" in ct or url.lower().split("?")[0].endswith((".m3u8", ".m3u")):
        try:
            text = await r.aread()
        finally:
            await r.aclose()
        text = text.decode(r.encoding or "utf-8", errors="replace")
        base = url
        parent_hash = row["token_hash"]
        def issue(u):
            absolute = urljoin(base, u)
            if not _same_origin(absolute, base):
                return absolute
            tok = AUTH.issue_proxy_token(row["telegram_id"], parent_hash, absolute,
                                         row["expires_at"])
            return f"{PUBLIC_BASE}/api/stream/proxy/{tok}"
        out = []
        for line in text.splitlines():
            s = line.strip()
            if not s or s.startswith("#"):
                if 'URI="' in line:
                    line = re.sub(r'URI="([^"]+)"', lambda m: 'URI="' + issue(m.group(1)) + '"', line)
                out.append(line)
            else:
                out.append(issue(s))
        return PlainTextResponse("\n".join(out) + "\n", media_type="application/vnd.apple.mpegurl",
                                  headers={"Cache-Control": "no-store"})
    async def body():
        try:
            async for chunk in r.aiter_bytes(1024 * 256):
                yield chunk
        finally:
            await r.aclose()
    response_headers = {}
    for k in ("content-length", "content-range", "accept-ranges", "content-disposition"):
        if k in r.headers:
            response_headers[k] = r.headers[k]
    return StreamingResponse(body(), status_code=r.status_code,
                             media_type=ct, headers=response_headers)


@app.get("/api/stream/media/{token}")
async def stream_media(token: str, request: Request):
    row = AUTH.stream_token(token)
    if not row:
        raise HTTPException(401, "Stream token expired or invalid")
    return await _proxy_response(row, request)


@app.get("/api/stream/proxy/{token}")
async def stream_proxy(token: str, request: Request):
    row = AUTH.proxy_token(token)
    if not row:
        raise HTTPException(401, "Proxy token expired or invalid")
    return await _proxy_response(row, request)
