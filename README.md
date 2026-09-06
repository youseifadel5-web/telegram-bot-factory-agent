# Unified Telegram Bot

## الهيكل
- `bot.py` هو البوت الأساسي والـpolling الوحيد (Token واحد).
- `Add bot/` هو المكان الوحيد لإضافة البوتات الفرعية.
- كل ملف `.py` مباشر داخل `Add bot/` يُحمَّل تلقائيًا كبوت فرعي. اسم الملف لا يهم.
- لا تحتاج لإنشاء مجلد أو ملف إعداد إضافي للبوت الفرعي.
- بعد وضع الملف: من لوحة الأدمن → **إدارة البوتات** → **إعادة تحميل البوتات** (أو أعد تشغيل الخدمة).

## البوابة
- `🎬 بوت سينماء`: يعرض كل البوتات **المفعّلة** الموجودة في `Add bot/`.
- `🔍 بحث`: يبحث في كل البوتات المفعّلة التي توفر hook باسم `search`.
- `👑 لوحة التحكم`: تظهر للـ`ADMIN_ID` فقط في البوابة الخارجية، وتشمل:
  - إحصائيات / كاش / باسورد الكبار / رسالة جماعية (نظام يوسف)
  - **إدارة البوتات**: تفعيل/إيقاف أي بوت مكتشف + إعادة تحميل قائمة `Add bot/`

## طريقة إضافة بوت جديد
1. أنشئ ملفًا مثل `Add bot/MyBot.py` (بدون polling).
2. وفّر على الأقل:
   ```python
   PLUGIN_ID = "mybot"
   PLUGIN_NAME = "بوت تجريبي"
   PLUGIN_BUTTON = "🤖 بوت تجريبي"

   def open_plugin(call, context):
       # افتح واجهتك أو أرجع مسارًا معروفًا للمضيف
       # أمثلة جاهزة:
       # return "youseif"              # واجهة يوسف فيلم
       # return "cinema:hub_nova"      # واجهة سينما نوفا
       return "cinema:hub_orion"

   def handle_callback(call, context):
       # اختياري — إن كان البوت يعتمد على cinema_core
       return bool(context["cinema"].handle_callbacks(call))

   def handle_message(update, context):
       return False

   def search(query, context):
       # اختياري — للبحث الموحد
       return {"movie": [], "series": []}
   ```
3. من لوحة الأدمن اضغط **إعادة تحميل البوتات** ثم فعّله إن لزم.

> مهم: ملف البوت الفرعي **لا يجب** أن يبدأ `polling` أو `run_polling()` بنفسه.

## الأنظمة المدمجة
- **سينما نوفا / أوريون بلس**: عبر `cinema_core.py` + ملفات الإضافة في `Add bot/`.
- **Youseif Films**: عبر `youseif_core.py` + `Add bot/Youseif_Films.py` (بدون polling مستقل).

## الأسرار
```env
ADMIN_ID=
API_HASH=
API_ID=
BOT_TOKEN=
TMDB_API_KEY=
```

إعدادات IPTV/العرض تبقى في `config.py`.


## Video Player REST API

The REST API is additive and uses the same existing SQLite/content source; it does not create a second movie database.

### Localhost

Install requirements and set the existing environment variables as before:

```bash
pip install -r requirements.txt
python bot.py
```

The unified launcher starts Telegram polling and the API together. By default:

```text
http://127.0.0.1:8000
```

Set `API_BASE_URL` for the player. For a remote production deployment, set both `API_BASE_URL` and `API_PUBLIC_BASE_URL` to the public HTTPS origin.

### Authentication flow

1. Player: `POST /api/auth/request`
2. Open returned `login_url`.
3. Telegram user presses Start.
4. The bot consumes the one-time `login_<request_id>` start parameter.
5. Player polls `GET /api/auth/status/{request_id}`.
6. The completed response contains a random session token.
7. Send it as `Authorization: Bearer <SESSION_TOKEN>`.

### Endpoints

- `POST /api/auth/request`
- `GET /api/auth/status/{request_id}`
- `POST /api/auth/logout`
- `GET /api/me`
- `GET /api/content`
- `GET /api/content/movies`
- `GET /api/content/series`
- `GET /api/content/anime`
- `GET /api/content/categories`
- `GET /api/content/{id}`
- `GET /api/stream/{id}`
- `GET /api/health`

Series playback accepts `episode_id` on `/api/stream/{series_id}?episode_id=<episode_id>`.

### JSON examples

`POST /api/auth/request`

```json
{
  "success": true,
  "request_id": "login_...",
  "login_url": "https://t.me/BOT_USERNAME?start=login_...",
  "expires_at": "2026-09-06T20:00:00Z",
  "expires_in": 300
}
```

`GET /api/me`

```json
{
  "success": true,
  "user": {
    "id": 123456789,
    "telegram_id": 123456789,
    "username": "example",
    "first_name": "Example",
    "last_name": "",
    "role": "user",
    "permissions": ["content.read", "stream.play"]
  }
}
```

`GET /api/content/movies`

```json
{
  "success": true,
  "items": [
    {
      "id": "movie_001",
      "title": "Example Movie",
      "type": "movie",
      "poster": "https://example.com/poster.jpg",
      "description": "Example description",
      "year": "2026",
      "category": "Action"
    }
  ]
}
```

`GET /api/content/{id}` returns the same normalized item plus movie metadata, or series seasons/episodes.

`GET /api/stream/{id}` returns an opaque, short-lived API media URL. Provider credentials are kept server-side and are not included in the JSON sent to the player.

```json
{
  "success": true,
  "stream": {
    "url": "http://127.0.0.1:8000/api/stream/media/OPAQUE_TOKEN",
    "type": "http",
    "mime": "video/mp4",
    "expires_at": "2026-09-06T20:15:00Z"
  }
}
```

### Permissions

Roles are stored server-side in the existing `users` table and default to `user`. Built-in permissions are:

- `user`: `content.read`, `stream.play`
- `premium`: `content.read`, `stream.play`, `premium.*`
- `admin`: all API content/stream permissions plus `admin.*`

A `banned` user cannot authenticate API requests.

### Video Player

The supplied player keeps its existing local playlist/file/URL features. It adds:

- Settings → Telegram Login / API
- Films → Server Library
- API base URL stored in local storage (default follows `API_BASE_URL` convention)
- Telegram deep-link login
- `/api/me`, content browsing and stream playback

The player never receives `BOT_TOKEN`, IPTV username/password, database credentials, or other server secrets.

### Security notes

Use HTTPS in production. Keep all existing secrets in environment variables/GitHub Secrets. Login requests expire and are single-use. Sessions are random, expiring and revocable. Stream URLs are short-lived opaque tokens and provider credentials remain on the server.
