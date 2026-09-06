# Youseif API ↔ Video Player

This is an additive REST API for the existing Telegram bot. It reuses the bot's existing Youseif content store and SQLite database.

## Quick start

```bash
pip install -r requirements.txt
python bot.py
```

Default API: `http://127.0.0.1:8000`

Production example:

```env
API_HOST=0.0.0.0
API_PORT=8000
API_BASE_URL=https://my-api.example.com
API_PUBLIC_BASE_URL=https://my-api.example.com
API_CORS_ORIGINS=https://my-player.example.com
```

## Login

`POST /api/auth/request`

Response:

```json
{
  "success": true,
  "request_id": "login_...",
  "login_url": "https://t.me/BOT_USERNAME?start=login_...",
  "expires_at": "2026-09-06T20:00:00Z",
  "expires_in": 300
}
```

After Telegram Start:

`GET /api/auth/status/{request_id}`

Completed response contains a random session token. Send it as:

```http
Authorization: Bearer SESSION_TOKEN
```

## User

`GET /api/me`

`POST /api/auth/logout`

## Content

All require a valid session with `content.read`.

- `GET /api/content`
- `GET /api/content/movies`
- `GET /api/content/series`
- `GET /api/content/anime`
- `GET /api/content/categories`
- `GET /api/content/{id}`

Content IDs are normalized as `movie_<stream_id>`, `series_<series_id>`, or `live_<stream_id>`.

## Streaming

`GET /api/stream/{id}` requires `stream.play`.

For series:

```text
GET /api/stream/series_<series_id>?episode_id=<episode_id>
```

The returned media URL is an opaque short-lived API token. Provider credentials stay server-side. HLS playlists are proxied and rewritten to opaque API URLs; direct MP4 playback is streamed through the API with Range support.

## Roles

Default role is `user`.

- `user`: `content.read`, `stream.play`
- `premium`: user permissions + `premium.*`
- `admin`: content/stream + `admin.*`

`banned=1` blocks API authentication.

## Existing bot safety

The API does not start another Telegram polling loop. `bot.py` remains the only Telegram update poller and starts FastAPI on the same asyncio loop.
