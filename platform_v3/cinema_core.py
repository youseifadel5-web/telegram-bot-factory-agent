import json
import os
import random
import json
import hashlib
import hmac
import secrets
import time
from urllib.parse import unquote, urlparse
import requests
import telebot
from telebot import types


# ---------------------------------------------------------
# إعداد تجريبي سريع لـ Pydroid 3. استبدل التوكن قبل نشر الملف أو مشاركته.
BOT_TOKEN = os.getenv("BOT_TOKEN", "").strip()
# Allow import as library (plugin binding) without token; only the standalone telebot needs it.
DATA_FILE = "users_data.json"

DEFAULT_POSTER = "https://images.unsplash.com/photo-1489599849927-2ee91cede3ba?w=800"

bot = telebot.TeleBot(BOT_TOKEN or "0:dummy", parse_mode="HTML") if BOT_TOKEN else None


def safe_edit_or_send(chat_id, message_id, text, reply_markup=None):
    reply_markup = add_history_back_button(reply_markup)
    try:
        bot.edit_message_text(text, chat_id, message_id, reply_markup=reply_markup, parse_mode="HTML")
    except Exception:
        try:
            bot.delete_message(chat_id, message_id)
        except Exception:
            pass
        bot.send_message(chat_id, text, reply_markup=reply_markup, parse_mode="HTML")


def send_media_with_fallback(chat_id, message_id_to_delete, photo_url, caption, reply_markup):
    """دالة مخصصة لإرسال الصور دائماً مع إمكانية حذف الرسالة السابقة وتوفير صورة بديلة"""
    reply_markup = add_history_back_button(reply_markup)
    try:
        if message_id_to_delete:
            try:
                bot.delete_message(chat_id, message_id_to_delete)
            except Exception:
                pass

        target_photo = photo_url if (photo_url and str(photo_url).startswith("http")) else DEFAULT_POSTER

        try:
            bot.send_photo(chat_id, photo=target_photo, caption=caption, reply_markup=reply_markup, parse_mode="HTML")
        except Exception as e:
            print(f"Failed to send primary photo ({target_photo}): {e}")
            bot.send_photo(chat_id, photo=DEFAULT_POSTER, caption=caption, reply_markup=reply_markup, parse_mode="HTML")
    except Exception as e:
        print(f"Media send error: {e}")
        bot.send_message(chat_id, caption, reply_markup=reply_markup, parse_mode="HTML")


# --- دالات التعامل مع ملف JSON للتخزين الحقيقي ---
def load_data() -> dict:
    if not os.path.exists(DATA_FILE):
        return {}
    try:
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        print(f"Error loading JSON file: {e}")
        return {}


def save_data(data: dict):
    try:
        with open(DATA_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"Error saving JSON file: {e}")


def register_user(user_id: int, username: str = "", first_name: str = "") -> dict:
    data = load_data()
    uid = str(user_id)
    if uid not in data:
        data[uid] = {
            "username": username,
            "first_name": first_name or "مستخدم",
            "favorites": {"movies": {}, "series": {}}
        }
    else:
        data[uid]["first_name"] = first_name or data[uid].get("first_name", "مستخدم")
        if username:
            data[uid]["username"] = username

    save_data(data)
    return data


def get_user_favs(user_id: int) -> dict:
    data = register_user(user_id)
    uid = str(user_id)
    return data[uid].get("favorites", {"movies": {}, "series": {}})


def save_user_favs(user_id: int, favs: dict):
    data = load_data()
    uid = str(user_id)
    if uid not in data:
        data[uid] = {"favorites": {"movies": {}, "series": {}}}
    data[uid]["favorites"] = favs
    save_data(data)



def parse_genres(genres_data) -> str:
    if not genres_data:
        return ""
    if isinstance(genres_data, list):
        items = []
        for g in genres_data:
            if isinstance(g, dict):
                name = g.get("name") or g.get("title") or g.get("name_ar")
                if name:
                    items.append(str(name))
            elif isinstance(g, str):
                items.append(g)
            else:
                items.append(str(g))
        return ", ".join(items)
    elif isinstance(genres_data, str):
        return genres_data
    return ""


# ---------------------------------------------------------
# 2. كلاس التعامل مع API المصدر (OscarAPI)
# ---------------------------------------------------------
class IronHeadersGenerator:
    """يطابق خوارزمية مولّد ترويسات Iron الموجودة في نسخة PHP."""

    GUARD_1 = "OscarTVIronGuard"
    GUARD_2 = "IronGuard"

    def __init__(self, cert_sha256: str, pkg_name: str = "com.drama.mp4"):
        self.cert = cert_sha256
        self.pkg = pkg_name
        self.fingerprint = cert_sha256[:8]

    def derive_key(self) -> bytes:
        raw = (self.cert + "|" + self.pkg).encode("utf-8")

        stage_1 = bytes(
            byte ^ ord(self.GUARD_1[index % 7])
            for index, byte in enumerate(raw)
        )
        stage_2 = stage_1[::-1]
        stage_3 = bytes(
            byte ^ ord(self.GUARD_2[index % 9])
            for index, byte in enumerate(stage_2)
        )

        pass_1 = hashlib.sha256(stage_3).digest()
        pass_2 = hashlib.sha256(pass_1).digest()
        return hashlib.sha256(pass_2).digest()

    def generate(self, url: str) -> dict:
        path = urlparse(url).path or "/"
        timestamp = str(int(time.time()))
        nonce = secrets.token_hex(4)
        payload = f"{path}|{timestamp}|{nonce}".encode("utf-8")
        signature = hmac.new(self.derive_key(), payload, hashlib.sha256).hexdigest()

        return {
            "Host": "ostvapp.cam",
            "x-iron-sig": signature,
            "x-iron-ts": timestamp,
            "x-iron-nonce": nonce,
            "x-iron-diag": f"f={self.fingerprint} p={self.fingerprint} h=0",
            "accept-encoding": "gzip",
            "user-agent": "okhttp/4.12.0",
            "connection": "keep-alive",
        }


class OscarAPI:
    BASE_URL = "https://ostvapp.cam"
    MOVIES_URL = f"{BASE_URL}/api/movies/"
    MOVIE_DETAILS_URL = f"{BASE_URL}/api/movies/show.php"
    SERIES_URL = f"{BASE_URL}/api/series/"
    SERIES_DETAILS_URL = f"{BASE_URL}/api/series/show.php"
    ANIME_URL = f"{BASE_URL}/api/anime/"
    ANIME_DETAILS_URL = f"{BASE_URL}/api/anime/show.php"
    EPISODES_URL = f"{BASE_URL}/api/episodes/"
    EPISODE_DETAILS_URL = f"{BASE_URL}/api/episodes/show.php"
    ANIME_EPISODES_URL = f"{BASE_URL}/api/anime/episodes/"
    ANIME_EPISODE_DETAILS_URL = f"{BASE_URL}/api/anime/episodes/show.php"
    LATEST_EPISODES_URL = f"{BASE_URL}/api/episodes/latest.php"
    LATEST_ANIME_EPISODES_URL = f"{BASE_URL}/api/anime/episodes/latest.php"
    MATCHES_URL = f"{BASE_URL}/api/matches/"
    MATCH_DETAILS_URL = f"{BASE_URL}/api/matches/show.php"
    WATCH_LINKS_URL = f"{BASE_URL}/api/watch_links/"
    DOWNLOAD_LINKS_URL = f"{BASE_URL}/api/download_links/"
    WRESTLING_URL = f"{BASE_URL}/api/wrestling/"
    WRESTLING_DETAILS_URL = f"{BASE_URL}/api/wrestling/show.php"
    BASE_MEDIA_URL = BASE_URL

    def __init__(self, timeout: int = 25):
        self.timeout = timeout
        self.session = requests.Session()
        cert = os.getenv(
            "IRON_CERT_SHA256",
            "6e2fcda8631eb49ebcba4ca8ef4c597abe84654c7d3e8096db32bdd21ecf763f",
        )
        package = os.getenv("IRON_PACKAGE_NAME", "com.drama.mp4")
        self.iron = IronHeadersGenerator(cert, package)

    @staticmethod
    def _json_response(response):
        if not response.ok:
            print(f"API returned HTTP {response.status_code}: {response.url}")
            return None
        try:
            return response.json()
        except ValueError as exc:
            print(f"Invalid JSON from {response.url}: {exc}")
            return None

    def _get(self, endpoint: str, params: dict | None = None):
        params = {key: value for key, value in (params or {}).items() if value is not None}
        target_url = requests.Request("GET", endpoint, params=params).prepare().url
        headers = self.iron.generate(target_url)
        try:
            response = self.session.get(
                endpoint,
                headers=headers,
                params=params,
                timeout=self.timeout,
            )
            return self._json_response(response)
        except requests.RequestException as exc:
            print(f"API request failed for {target_url}: {exc}")
            return None

    def get_movies(self, page=1, limit=20, sort_by="most_viewed"):
        return self._get(self.MOVIES_URL, {"page": page, "limit": limit, "sort_by": sort_by, "app_version": 15})

    def search_movies(self, query, page=1, limit=20):
        return self._get(self.MOVIES_URL, {"page": page, "limit": limit, "search": query, "app_version": 15})

    def get_movie_details(self, movie_id):
        return self._get(self.MOVIE_DETAILS_URL, {"id": movie_id})

    def get_series(self, page=1, limit=20, sort_by="most_viewed"):
        return self._get(self.SERIES_URL, {"page": page, "limit": limit, "sort_by": sort_by, "app_version": 15})

    def search_series(self, query, page=1, limit=20):
        return self._get(self.SERIES_URL, {"page": page, "limit": limit, "search": query, "app_version": 15})

    def get_series_details(self, series_id):
        return self._get(self.SERIES_DETAILS_URL, {"id": series_id})

    def get_anime_movies(self, page=1, limit=20):
        return self._get(self.ANIME_URL, {"page": page, "limit": limit, "anime_type": "movie"})

    def get_anime_series(self, page=1, limit=20):
        return self._get(self.ANIME_URL, {"page": page, "limit": limit, "anime_type": "tv,ova,ona,special", "sort_by": "latest_episode"})

    def get_anime_details(self, anime_id):
        return self._get(self.ANIME_DETAILS_URL, {"id": anime_id})

    def get_anime_episodes(self, anime_id, page=1, per_page=20, season_id=None):
        return self._get(self.ANIME_EPISODES_URL, {"anime_id": anime_id, "page": page, "per_page": per_page, "season_id": season_id})

    def get_season_episodes(self, season_id, page=1, per_page=20, sort="asc"):
        return self._get(self.EPISODES_URL, {"season_id": season_id, "page": page, "per_page": per_page, "sort": sort})

    def get_episode_details(self, episode_id):
        return self._get(self.EPISODE_DETAILS_URL, {"id": episode_id})

    def get_anime_episode_details(self, episode_id):
        return self._get(self.ANIME_EPISODE_DETAILS_URL, {"id": episode_id})

    def get_latest_episodes(self, page=1, limit=20, **filters):
        params = {"page": page, "limit": limit, **filters}
        return self._get(self.LATEST_EPISODES_URL, params)

    def get_latest_anime_episodes(self, page=1, limit=20, **filters):
        params = {"page": page, "limit": limit, **filters}
        return self._get(self.LATEST_ANIME_EPISODES_URL, params)

    def get_matches(self, page=1, limit=20, **filters):
        params = {"page": page, "limit": limit, **filters}
        return self._get(self.MATCHES_URL, params)

    def get_match_details(self, match_id):
        return self._get(self.MATCH_DETAILS_URL, {"id": match_id})

    def get_watch_links(self, item_id=None, **params):
        if item_id is not None:
            params.setdefault("id", item_id)
        return self._get(self.WATCH_LINKS_URL, params)

    def get_download_links(self, item_id=None, **params):
        if item_id is not None:
            params.setdefault("id", item_id)
        return self._get(self.DOWNLOAD_LINKS_URL, params)

    def get_wrestling(self, page=1, limit=20):
        return self._get(self.WRESTLING_URL, {"page": page, "limit": limit})

    def get_wrestling_details(self, wrestling_id):
        return self._get(self.WRESTLING_DETAILS_URL, {"id": wrestling_id})


api = OscarAPI()


# ---------------------------------------------------------
# 2B. القسم الثاني من المكتبة الموحدة (أفلام ومسلسلات ومواسم)
# ---------------------------------------------------------
class AuroraLibraryAPI:
    BASE_URL = "https://admin.golive-pro.online/api"
    MOVIE_CATEGORIES = {
        "arabic": "2185cd2d-f379-4584-8caa-5884bced7150",
        "foreign": "9ec354e5-4707-4161-9dab-b51f899b29d8",
        "asian": "3443bc74-5492-4abb-a8f1-26b15f6bb814",
        "indian": "baa2d0f9-19ef-4317-adb6-5ef89ff1448e",
        "sports": "69e9a8d2-2e75-415c-b5f2-cb87b2171f1c",
    }
    SERIES_CATEGORIES = {
        "arabic": "dd185bc6-1dfd-45c2-9189-13c47f672e5a",
        "foreign": "1bf63825-0b85-4ed8-8964-4cf2efb854d6",
        "asian": "0669005a-e8dd-4a00-8986-a905826eaca3",
        "turkish": "32d17563-00ee-4433-8b59-ddf969a51230",
        "dubbed": "2660c480-65f2-4a30-a0c9-eda017ea660b",
        "netshort": "1bbdd6d8-02f2-462b-b508-fcbc91694392",
        "moborels": "1ac44de7-1162-40a5-b59d-cd3282a9d891",
        "stardust": "ecc2b43c-ee30-406e-b22c-71fd8be40834",
        "idrama": "734637d2-aec7-4dfe-91ae-2ff78355ca2d",
        "dramabox": "de497227-8620-4074-96c1-2b648174295a",
        "flextv": "86f37c69-e7c1-46b1-a4db-b68e2c8008e8",
        "pinedrama": "c3a3bb27-0255-42e5-b9d1-136c0a6272d1",
        "rapidtv": "6f95184e-9a70-4875-9aeb-02cbc398ae1b",
        "reelshort": "ee7014f1-e0bd-45a8-a1c4-f6b359fd27cf",
        "shortmax": "0e08b255-4df3-44ae-b8e1-00670b8ff9f1",
        "goodshort": "69034f45-6b9c-49fe-9634-d7f17ce2e64a",
        "happyshort": "eae20054-13b8-4a10-af90-6562692782ec",
        "freereels": "96cba0ee-e245-434e-944c-0d3328242655",
        "dramawave": "f84b0194-1662-454a-9672-4fb269f90ac5",
        "dramanova": "a1e27c54-7031-4dc0-aa82-edc832cce97c",
        "cubetv": "5487e086-cb30-4458-a129-3b5661022638",
        "flareflow": "702eb868-92ad-4ed2-afaf-9263488b8ae4",
        "kalostv": "f07a8296-d86d-4fff-9da4-4d289bb76611",
        "dotdrama": "51de00fb-95d9-4a47-bfd1-ca41ac973cc0",
        "flickreels": "0549eece-f0d6-44db-8767-9c06ef9ef3bd",
        "dramabite": "9bd68362-5ede-429b-b969-f5ccce288739",
        "starshort": "68c15996-1297-46bd-be84-92e32af072e2",
        "reelife": "e42eef62-8a1d-4467-b036-120162481de2",
    }
    SERIES_LABELS = {
        "arabic": "🇸🇦 عربية", "foreign": "🌍 أجنبية", "asian": "🌏 آسيوية",
        "turkish": "🇹🇷 تركية", "dubbed": "🎙️ مدبلجة",
    }

    def __init__(self, timeout=25):
        self.timeout = timeout
        self.session = requests.Session()
        self.session.headers.update({"User-Agent": "CinemaFusion/1.0", "Accept": "application/json"})
        self.cache = {}
        self.episodes = {}

    def _get(self, endpoint, params=None, cache=True):
        params = {k: v for k, v in (params or {}).items() if v is not None and v != ""}
        key = f"{endpoint}|{tuple(sorted(params.items()))}"
        cached = self.cache.get(key)
        if cache and cached and time.monotonic() - cached[0] < 60:
            return cached[1]
        try:
            response = self.session.get(f"{self.BASE_URL}{endpoint}", params=params, timeout=self.timeout)
            response.raise_for_status()
            payload = response.json()
        except (requests.RequestException, ValueError) as exc:
            print(f"Aurora API error {endpoint}: {exc}")
            return None
        if cache:
            self.cache[key] = (time.monotonic(), payload)
        return payload

    @staticmethod
    def _sources(raw_sources):
        items = []
        for source in raw_sources or []:
            if not isinstance(source, dict):
                continue
            url = str(source.get("streamUrl") or source.get("url") or "").strip()
            if url:
                items.append({
                    "url": url,
                    "label": str(source.get("label") or "سيرفر مشاهدة"),
                    "quality": source.get("quality"),
                    "format": source.get("format"),
                    "order": int(source.get("sortOrder") or 0),
                })
        return sorted(items, key=lambda item: item["order"])

    def list_content(self, kind, page=1, limit=12, **filters):
        payload = self._get(f"/content/{kind}", {"page": page, "limit": limit, **filters})
        if not payload:
            return [], {"page": page, "totalPages": 1}
        if isinstance(payload, dict):
            return payload.get("data") or [], payload.get("meta") or {"page": page, "totalPages": 1}
        return payload if isinstance(payload, list) else [], {"page": 1, "totalPages": 1}

    def detail(self, kind, item_id):
        return self._get(f"/content/{kind}/{item_id}", cache=False)

    def resolve_sources(self, sources):
        output = []
        for source in sources:
            payload = self._get("/stream/resolve", {"url": source["url"]})
            resolved = payload.get("resolved") if isinstance(payload, dict) and payload.get("ok") else source["url"]
            output.append({**source, "url": resolved})
        return output


vault_api = AuroraLibraryAPI()


def get_hub_keyboard(user_id: int = 0):
    """البوابة: 3 منصات + موحّدة اختيارية."""
    import os
    markup = types.InlineKeyboardMarkup(row_width=1)
    markup.add(
        types.InlineKeyboardButton("🎬 يوسف فيلمز", callback_data="hub_youseif"),
        types.InlineKeyboardButton("🎞️ سينما نوفا", callback_data="hub_nova"),
        types.InlineKeyboardButton("🌟 أوريون بلس", callback_data="hub_orion"),
    )
    if os.getenv("UNIFIED_PLATFORM_ENABLED", "0").strip().lower() in ("1", "true", "yes", "on"):
        markup.add(types.InlineKeyboardButton("✨ المنصة الموحّدة (تجريبي)", callback_data="unified_search"))
    markup.add(types.InlineKeyboardButton("🔍 بحث", callback_data="unified_search"))
    try:
        if int(user_id or 0) in set(ADMIN_IDS or []):
            markup.add(types.InlineKeyboardButton("👑 لوحة التحكم", callback_data="admin:menu"))
    except Exception:
        pass
    return mark_navigation_root(markup)


def vault_movies_menu():
    markup = types.InlineKeyboardMarkup(row_width=2)
    markup.add(
        types.InlineKeyboardButton("🆕 أحدث الأفلام", callback_data="vault_list:m:latest:1"),
        types.InlineKeyboardButton("🔥 الأكثر مشاهدة", callback_data="vault_list:m:popular:1"),
        types.InlineKeyboardButton("🇸🇦 عربية", callback_data="vault_list:m:arabic:1"),
        types.InlineKeyboardButton("🌍 أجنبية", callback_data="vault_list:m:foreign:1"),
        types.InlineKeyboardButton("🌏 آسيوية", callback_data="vault_list:m:asian:1"),
        types.InlineKeyboardButton("🇮🇳 هندية", callback_data="vault_list:m:indian:1"),
        types.InlineKeyboardButton("⚽ رياضة ومباريات", callback_data="vault_list:m:sports:1"),
        types.InlineKeyboardButton("🎬 كل الأفلام", callback_data="vault_list:m:all:1"),
        types.InlineKeyboardButton("🔎 بحث في الأفلام", callback_data="vault_search:m"),
        types.InlineKeyboardButton("📅 حسب السنة", callback_data="vault_year"),
        types.InlineKeyboardButton("🔙 رجوع للبوابة", callback_data="vault_home"),
    )
    return markup


def vault_short_menu():
    providers = [
        ("NetShort", "netshort"), ("MoboRels", "moborels"), ("Stardust", "stardust"), ("iDrama", "idrama"),
        ("DramaBox", "dramabox"), ("FlexTV", "flextv"), ("PineDrama", "pinedrama"), ("RapidTV", "rapidtv"),
        ("ReelShort", "reelshort"), ("ShortMax", "shortmax"), ("GoodShort", "goodshort"), ("HappyShort", "happyshort"),
        ("FreeReels", "freereels"), ("DramaWave", "dramawave"), ("DramaNova", "dramanova"), ("CubeTV", "cubetv"),
        ("FlareFlow", "flareflow"), ("KalosTV", "kalostv"), ("DotDrama", "dotdrama"), ("FlickReels", "flickreels"),
        ("DramaBite", "dramabite"), ("StarShort", "starshort"), ("Reelife", "reelife"),
    ]
    markup = types.InlineKeyboardMarkup(row_width=2)
    for label, mode in providers:
        markup.add(types.InlineKeyboardButton(label, callback_data=f"vault_list:s:{mode}:1"))
    markup.add(
        types.InlineKeyboardButton("🔙 رجوع للمسلسلات", callback_data="vault_menu:s"),
        types.InlineKeyboardButton("🏠 البوابة الرئيسية", callback_data="vault_home"),
    )
    return markup


def vault_series_menu():
    markup = types.InlineKeyboardMarkup(row_width=2)
    markup.add(
        types.InlineKeyboardButton("🇸🇦 عربية", callback_data="vault_list:s:arabic:1"),
        types.InlineKeyboardButton("🌍 أجنبية", callback_data="vault_list:s:foreign:1"),
        types.InlineKeyboardButton("🌏 آسيوية", callback_data="vault_list:s:asian:1"),
        types.InlineKeyboardButton("🇹🇷 تركية", callback_data="vault_list:s:turkish:1"),
        types.InlineKeyboardButton("🎙️ مدبلجة", callback_data="vault_list:s:dubbed:1"),
        types.InlineKeyboardButton("📱 مسلسلات قصيرة", callback_data="vault_menu:short"),
        types.InlineKeyboardButton("📺 كل المسلسلات", callback_data="vault_list:s:all:1"),
        types.InlineKeyboardButton("🔎 بحث في المسلسلات", callback_data="vault_search:s"),
        types.InlineKeyboardButton("🔙 رجوع للبوابة", callback_data="vault_home"),
    )
    return markup


def vault_home_keyboard():
    markup = types.InlineKeyboardMarkup(row_width=2)
    markup.add(
        types.InlineKeyboardButton("🎬 مكتبة الأفلام", callback_data="vault_menu:m"),
        types.InlineKeyboardButton("📺 عالم المسلسلات", callback_data="vault_menu:s"),
        types.InlineKeyboardButton("🔙 البوابة الرئيسية", callback_data="hub_home"),
    )
    return markup


def vault_title(item):
    return str(item.get("titleAr") or item.get("titleEn") or item.get("title") or "محتوى")


def vault_list_keyboard(items, kind, mode, page, total_pages):
    markup = types.InlineKeyboardMarkup(row_width=1)
    icon = "🎬" if kind == "m" else "📺"
    api_kind = "movies" if kind == "m" else "series"
    for item in items:
        title = vault_title(item)
        if len(title) > 32:
            title = title[:31] + "…"
        markup.add(types.InlineKeyboardButton(f"{icon} {title}", callback_data=f"vault_item:{kind}:{item.get('id')}"))
    nav = []
    if page > 1:
        nav.append(types.InlineKeyboardButton("➡️ السابق", callback_data=f"vault_list:{kind}:{mode}:{page - 1}"))
    if page < total_pages:
        nav.append(types.InlineKeyboardButton("التالي ⬅️", callback_data=f"vault_list:{kind}:{mode}:{page + 1}"))
    if nav:
        markup.row(*nav)
    markup.add(types.InlineKeyboardButton("🔙 رجوع للقسم", callback_data=f"vault_menu:{kind}"))
    markup.add(types.InlineKeyboardButton("📂 القائمة", callback_data=f"vault_menu:{kind}"))
    markup.add(types.InlineKeyboardButton("🔍 بحث", callback_data=f"vault_search:{kind}"))
    markup.add(types.InlineKeyboardButton("🏠 البوابة الرئيسية", callback_data="vault_home"))
    return markup


def vault_sources_keyboard(sources, back_callback, back_label, menu_callback="vault_home", search_callback="vault_search:m"):
    markup = types.InlineKeyboardMarkup(row_width=1)
    if sources:
        for source in sources:
            extra = " · ".join(str(value) for value in (source.get("quality"), source.get("format")) if value)
            label = f"▶️ {source.get('label', 'سيرفر مشاهدة')}" + (f" ({extra})" if extra else "")
            markup.add(types.InlineKeyboardButton(label[:60], url=source["url"]))
    else:
        markup.add(types.InlineKeyboardButton("⚠️ لا توجد روابط مشاهدة", callback_data="noop"))
    markup.add(types.InlineKeyboardButton(back_label, callback_data=back_callback))
    markup.add(types.InlineKeyboardButton("📂 القائمة", callback_data=menu_callback))
    markup.add(types.InlineKeyboardButton("🔍 بحث", callback_data=search_callback))
    markup.add(types.InlineKeyboardButton("🏠 البوابة الرئيسية", callback_data="vault_home"))
    return markup


def vault_caption(item, is_series=False, is_episode=False):
    if is_episode:
        number = item.get("episodeNumber") or "؟"
        title = item.get("titleAr") or item.get("title") or f"الحلقة {number}"
        return f"📺 <b>الحلقة {number}</b>\n🏷️ {html_escape(title)}\n\nاختر رابط المشاهدة المناسب."
    title = vault_title(item)
    icon = "📺" if is_series else "🎬"
    facts = []
    if item.get("year"):
        facts.append(f"📅 {item['year']}")
    if item.get("rating"):
        facts.append(f"⭐ {item['rating']}/10")
    if is_series and item.get("totalEpisodes"):
        facts.append(f"🎞️ {item['totalEpisodes']} حلقة")
    if item.get("genreAr"):
        facts.append(f"🎭 {html_escape(item['genreAr'])}")
    description = item.get("descriptionAr") or item.get("description") or ""
    text = f"{icon} <b>{html_escape(title)}</b>"
    if facts:
        text += "\n" + " | ".join(facts)
    if description:
        text += f"\n\n📝 <i>{html_escape(str(description)[:600])}</i>"
    text += "\n\n" + ("اختر موسماً لعرض الحلقات." if is_series else "اختر رابط المشاهدة المناسب.")
    return text


def html_escape(value):
    return str(value).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def vault_series_keyboard(series, back_callback="vault_menu:s", back_label="📺 رجوع لقائمة المسلسلات"):
    episodes = series.get("episodes") or []
    seasons = sorted({int(ep.get("seasonNumber") or 1) for ep in episodes if isinstance(ep, dict)})
    markup = types.InlineKeyboardMarkup(row_width=1)
    for season in seasons:
        count = sum(1 for ep in episodes if isinstance(ep, dict) and int(ep.get("seasonNumber") or 1) == season)
        markup.add(types.InlineKeyboardButton(f"📁 الموسم {season} ({count} حلقة)", callback_data=f"vault_season:{series.get('id')}:{season}:1"))
    if not seasons:
        markup.add(types.InlineKeyboardButton("⚠️ لا توجد حلقات حالياً", callback_data="noop"))
    markup.add(types.InlineKeyboardButton(back_label, callback_data=back_callback))
    markup.add(types.InlineKeyboardButton("📂 قائمة المسلسلات", callback_data="vault_menu:s"))
    markup.add(types.InlineKeyboardButton("🔍 بحث", callback_data="vault_search:s"))
    markup.add(types.InlineKeyboardButton("🏠 البوابة الرئيسية", callback_data="vault_home"))
    return markup


def vault_episodes_keyboard(series_id, season, episodes, page, total_pages, back_callback=None):
    markup = types.InlineKeyboardMarkup(row_width=5)
    buttons = []
    for episode in episodes:
        buttons.append(types.InlineKeyboardButton(f"ح {episode.get('episodeNumber') or '؟'}", callback_data=f"vault_episode:{episode.get('id')}"))
    if buttons:
        markup.add(*buttons)
    nav = []
    if page > 1:
        nav.append(types.InlineKeyboardButton("➡️", callback_data=f"vault_season:{series_id}:{season}:{page - 1}"))
    nav.append(types.InlineKeyboardButton(f"{page}/{total_pages}", callback_data="noop"))
    if page < total_pages:
        nav.append(types.InlineKeyboardButton("⬅️", callback_data=f"vault_season:{series_id}:{season}:{page + 1}"))
    markup.row(*nav)
    markup.add(types.InlineKeyboardButton("🔙 رجوع للمواسم", callback_data=f"vault_item:s:{series_id}"))
    if back_callback:
        markup.add(types.InlineKeyboardButton("📺 رجوع لقائمة المسلسلات", callback_data=back_callback))
    else:
        markup.add(types.InlineKeyboardButton("📺 رجوع لأقسام المسلسلات", callback_data="vault_menu:s"))
    markup.add(types.InlineKeyboardButton("📂 قائمة المسلسلات", callback_data="vault_menu:s"))
    markup.add(types.InlineKeyboardButton("🔍 بحث", callback_data="vault_search:s"))
    markup.add(types.InlineKeyboardButton("🏠 البوابة الرئيسية", callback_data="vault_home"))
    return markup


def vault_list_data(kind, mode, page, user_id):
    api_kind = "movies" if kind == "m" else "series"
    if mode == "latest" or mode == "all":
        return vault_api.list_content(api_kind, page=page)
    if mode == "popular" and kind == "m":
        payload = vault_api._get("/content/movies/most-viewed", {"limit": 12})
        items = payload if isinstance(payload, list) else (payload or {}).get("data", [])
        return items, {"page": 1, "totalPages": 1}
    if mode == "search":
        term = str(user_id)  # يستبدل بدالة البحث باستخدام السياق المخزن في الذاكرة.
        return vault_api.list_content(api_kind, page=page, search=term)
    if mode == "year" and kind == "m":
        return vault_api.list_content(api_kind, page=page, year=user_id)
    categories = vault_api.MOVIE_CATEGORIES if kind == "m" else vault_api.SERIES_CATEGORIES
    return vault_api.list_content(api_kind, page=page, categoryId=categories.get(mode))


VAULT_USER_STATE = {}


def handle_vault_callbacks(call):
    data = call.data or ""
    if not (data.startswith("vault_") or data in {"hub_home", "hub_nova", "hub_orion"}):
        return False
    chat_id = call.message.chat.id
    user_id = call.from_user.id

    if data in {"hub_home", "vault_home"}:
        bot.answer_callback_query(call.id)
        safe_edit_or_send(chat_id, call.message.message_id, "<b>✨ اختر وجهتك السينمائية:</b>", get_hub_keyboard(user_id))
        return True
    if data == "hub_nova":
        bot.answer_callback_query(call.id)
        safe_edit_or_send(chat_id, call.message.message_id, "<b>🌟 سينما نوفا</b>\nاختر ما تريد مشاهدته:", get_main_keyboard())
        return True
    if data == "hub_orion":
        bot.answer_callback_query(call.id)
        safe_edit_or_send(chat_id, call.message.message_id, "<b>🎞️ أوريون بلس</b>\nمكتبة منظمة للأفلام والمسلسلات:", vault_home_keyboard())
        return True
    if data == "vault_menu:m":
        bot.answer_callback_query(call.id)
        safe_edit_or_send(chat_id, call.message.message_id, "<b>🎬 مكتبة الأفلام</b>", vault_movies_menu())
        return True
    if data == "vault_menu:s":
        bot.answer_callback_query(call.id)
        safe_edit_or_send(chat_id, call.message.message_id, "<b>📺 عالم المسلسلات</b>", vault_series_menu())
        return True
    if data == "vault_menu:short":
        bot.answer_callback_query(call.id)
        safe_edit_or_send(chat_id, call.message.message_id, "<b>📱 مسلسلات قصيرة ومنصات</b>", vault_short_menu())
        return True
    if data.startswith("vault_search:"):
        kind = data.split(":", 1)[1]
        VAULT_USER_STATE[user_id] = {"awaiting": "search", "kind": kind}
        bot.answer_callback_query(call.id)
        prompt = "فيلم" if kind == "m" else "مسلسل"
        msg = bot.send_message(chat_id, f"🔎 أرسل اسم {prompt} الذي تبحث عنه:")
        bot.register_next_step_handler(msg, vault_text_input)
        return True
    if data == "vault_year":
        VAULT_USER_STATE[user_id] = {"awaiting": "year", "kind": "m"}
        bot.answer_callback_query(call.id)
        msg = bot.send_message(chat_id, "📅 أرسل سنة صحيحة، مثل: 2026")
        bot.register_next_step_handler(msg, vault_text_input)
        return True
    if data.startswith("vault_list:"):
        _, kind, mode, page_text = data.split(":", 3)
        page = max(1, int(page_text))
        state = VAULT_USER_STATE.setdefault(user_id, {})
        state["last_list"] = data
        if mode == "search":
            term = state.get("term", "")
            items, meta = vault_api.list_content("movies" if kind == "m" else "series", page=page, search=term)
        elif mode == "year":
            items, meta = vault_api.list_content("movies", page=page, year=state.get("year"))
        else:
            items, meta = vault_list_data(kind, mode, page, user_id)
        total_pages = max(1, int(meta.get("totalPages") or 1))
        if not items:
            bot.answer_callback_query(call.id, "لا توجد نتائج في هذا القسم.", show_alert=True)
            return True
        title_map = {"m": "🎬 الأفلام", "s": "📺 المسلسلات"}
        label = (vault_api.SERIES_LABELS.get(mode) if kind == "s" else None) or mode
        text = f"<b>{title_map[kind]} — {html_escape(label)}</b>\nصفحة {page} من {total_pages}\n\nاختر المحتوى المطلوب:"
        bot.answer_callback_query(call.id)
        safe_edit_or_send(chat_id, call.message.message_id, text, vault_list_keyboard(items, kind, mode, page, total_pages))
        return True
    if data.startswith("vault_item:"):
        _, kind, item_id = data.split(":", 2)
        api_kind = "movies" if kind == "m" else "series"
        item = vault_api.detail(api_kind, item_id)
        if not item:
            bot.answer_callback_query(call.id, "تعذر جلب التفاصيل.", show_alert=True)
            return True
        bot.answer_callback_query(call.id)
        if kind == "m":
            sources = vault_api.resolve_sources(vault_api._sources(item.get("sources")))
            back = VAULT_USER_STATE.get(user_id, {}).get("last_list", "vault_menu:m")
            send_media_with_fallback(chat_id, call.message.message_id, item.get("posterUrl"), vault_caption(item), vault_sources_keyboard(sources, back, "🔙 رجوع لقائمة الأفلام", "vault_menu:m", "vault_search:m"))
        else:
            for episode in item.get("episodes") or []:
                if isinstance(episode, dict) and episode.get("id"):
                    vault_api.episodes[str(episode["id"])] = episode
            back = VAULT_USER_STATE.get(user_id, {}).get("last_list", "vault_menu:s")
            send_media_with_fallback(chat_id, call.message.message_id, item.get("posterUrl"), vault_caption(item, is_series=True), vault_series_keyboard(item, back, "🔙 رجوع لقائمة المسلسلات"))
        return True
    if data.startswith("vault_season:"):
        _, series_id, season_text, page_text = data.split(":", 3)
        series = vault_api.detail("series", series_id)
        if not series:
            bot.answer_callback_query(call.id, "تعذر جلب الحلقات.", show_alert=True)
            return True
        season = int(season_text)
        VAULT_USER_STATE.setdefault(user_id, {})["last_season"] = data
        episodes = [ep for ep in series.get("episodes") or [] if isinstance(ep, dict) and int(ep.get("seasonNumber") or 1) == season]
        episodes.sort(key=lambda ep: int(ep.get("episodeNumber") or 0))
        for episode in episodes:
            if episode.get("id"):
                vault_api.episodes[str(episode["id"])] = episode
        page_size = 20
        total_pages = max(1, (len(episodes) + page_size - 1) // page_size)
        page = min(max(1, int(page_text)), total_pages)
        current = episodes[(page - 1) * page_size:page * page_size]
        bot.answer_callback_query(call.id)
        back = VAULT_USER_STATE.get(user_id, {}).get("last_list")
        safe_edit_or_send(chat_id, call.message.message_id, f"<b>{html_escape(vault_title(series))}</b>\n📁 الموسم {season} — اختر الحلقة:", vault_episodes_keyboard(series_id, season, current, page, total_pages, back))
        return True
    if data.startswith("vault_episode:"):
        episode = vault_api.episodes.get(data.split(":", 1)[1])
        if not episode:
            bot.answer_callback_query(call.id, "انتهت صلاحية الحلقات. افتح المسلسل مجدداً.", show_alert=True)
            return True
        sources = vault_api.resolve_sources(vault_api._sources(episode.get("sources")))
        bot.answer_callback_query(call.id)
        back = VAULT_USER_STATE.get(user_id, {}).get("last_season", f"vault_item:s:{episode.get('seriesId')}")
        send_media_with_fallback(chat_id, call.message.message_id, episode.get("thumbnailUrl"), vault_caption(episode, is_episode=True), vault_sources_keyboard(sources, back, "🔙 رجوع للحلقات", "vault_menu:s", "vault_search:s"))
        return True
    return False


def vault_text_input(message):
    user_id = message.from_user.id
    state = VAULT_USER_STATE.get(user_id, {})
    text = (message.text or "").strip()
    if state.get("awaiting") == "search":
        if len(text) < 2:
            bot.send_message(message.chat.id, "❌ اكتب كلمتين على الأقل للبحث.")
            return
        kind = state.get("kind", "m")
        VAULT_USER_STATE[user_id] = {"term": text[:80], "last_list": f"vault_list:{kind}:search:1"}
        items, meta = vault_api.list_content("movies" if kind == "m" else "series", page=1, search=text[:80])
        if not items:
            bot.send_message(message.chat.id, "❌ لا توجد نتائج.", reply_markup=vault_home_keyboard())
            return
        NAV_CURRENT[user_id] = f"vault_search:{kind}"
        bot.send_message(message.chat.id, f"<b>🔎 نتائج البحث: {html_escape(text)}</b>", reply_markup=vault_list_keyboard(items, kind, "search", 1, max(1, int(meta.get('totalPages') or 1))))
        return
    if state.get("awaiting") == "year":
        if not text.isdigit() or not 1888 <= int(text) <= 2100:
            bot.send_message(message.chat.id, "❌ أدخل سنة صحيحة بين 1888 و2100.")
            return
        VAULT_USER_STATE[user_id] = {"year": int(text), "last_list": "vault_list:m:year:1"}
        items, meta = vault_api.list_content("movies", page=1, year=int(text))
        if not items:
            bot.send_message(message.chat.id, "❌ لا توجد نتائج لهذه السنة.", reply_markup=vault_movies_menu())
            return
        NAV_CURRENT[user_id] = "vault_year"
        bot.send_message(message.chat.id, f"<b>📅 أفلام سنة {text}</b>", reply_markup=vault_list_keyboard(items, "m", "year", 1, max(1, int(meta.get('totalPages') or 1))))


# ذاكرة قصيرة العمر للروابط: تحفظ عناوين URL في الخادم فقط كي لا تظهر في callback_data.
LINK_MENU_CACHE: dict[str, dict] = {}
LINK_MENU_CACHE_LIMIT = 400
NAV_CONTEXT: dict[int, dict[str, str]] = {}
NAV_HISTORY: dict[int, list[str]] = {}
NAV_CURRENT: dict[int, str] = {}
NAV_REPLAY: set[int] = set()
NAV_HISTORY_LIMIT = 30


def nav_context(user_id: int) -> dict[str, str]:
    """يحفظ آخر قائمة أو صفحة لكل مستخدم لتعمل أزرار الرجوع بصورة طبيعية."""
    return NAV_CONTEXT.setdefault(user_id, {})


def mark_navigation_root(markup):
    """يعلّم لوحة البداية حتى لا يُضاف لها شريط التنقل."""
    if isinstance(markup, types.InlineKeyboardMarkup):
        setattr(markup, "_navigation_root", True)
    return markup


def add_history_back_button(markup):
    """يوحّد التنقل في كل شاشة إلى: رجوع للخلف ثم الأقسام."""
    if not isinstance(markup, types.InlineKeyboardMarkup):
        return markup
    if getattr(markup, "_navigation_root", False):
        return markup

    # إزالة أزرار التنقل المتكررة القديمة بالنص فقط، مع إبقاء كل أزرار المحتوى والأقسام.
    def is_legacy_navigation_button(button):
        callback = getattr(button, "callback_data", None)
        label = (str(getattr(button, "text", ""))
                 .replace("🏠", "").replace("📂", "").replace("🔙", "").replace("⬅️", "")
                 .replace("🔍", "").replace("🔎", "").replace("📺", "").strip())
        if callback == "nav_back":
            return True
        return label.startswith(("رجوع", "القائمة الرئيسية", "البوابة الرئيسية")) or label in {"القائمة", "بحث"}

    cleaned_rows = []
    for row in getattr(markup, "keyboard", []):
        kept = [button for button in row if not is_legacy_navigation_button(button)]
        if kept:
            cleaned_rows.append(kept)
    markup.keyboard = cleaned_rows

    # القسم الحالي يستدل من أزرار المحتوى المتبقية؛ القائمة الرئيسية تبقى بوابة التطبيق دائماً.
    remaining_callbacks = {
        getattr(button, "callback_data", None)
        for row in markup.keyboard for button in row
    }
    is_orion = any(callback and (callback.startswith("vault_") or callback.startswith("vault:")) for callback in remaining_callbacks)
    sections_callback = getattr(markup, "_sections_callback", "vault_home" if is_orion else "hub_nova")

    markup.row(
        types.InlineKeyboardButton("⬅️ رجوع للخلف", callback_data="nav_back"),
        types.InlineKeyboardButton("📂 الأقسام", callback_data=sections_callback),
    )
    return markup


def track_navigation(user_id: int, destination: str):
    """يحفظ الشاشة الحالية قبل الانتقال إلى شاشة جديدة."""
    if user_id in NAV_REPLAY:
        NAV_REPLAY.discard(user_id)
        NAV_CURRENT[user_id] = destination
        return
    previous = NAV_CURRENT.get(user_id)
    if previous and previous != destination:
        history = NAV_HISTORY.setdefault(user_id, [])
        if not history or history[-1] != previous:
            history.append(previous)
            if len(history) > NAV_HISTORY_LIMIT:
                del history[:-NAV_HISTORY_LIMIT]
    NAV_CURRENT[user_id] = destination


def reset_navigation(user_id: int):
    NAV_HISTORY[user_id] = []
    NAV_CURRENT[user_id] = "hub_home"


# يجعل رسائل النص المباشرة تحمل زر الرجوع أيضاً، من دون تغيير محتواها.
_ORIGINAL_SEND_MESSAGE = bot.send_message

def _send_message_with_history(*args, **kwargs):
    if "reply_markup" in kwargs:
        kwargs["reply_markup"] = add_history_back_button(kwargs.get("reply_markup"))
    return _ORIGINAL_SEND_MESSAGE(*args, **kwargs)

bot.send_message = _send_message_with_history


def _store_link_menu(watch_links: list, download_links: list, back_callback: str = "hub_nova", back_label: str = "🔙 رجوع") -> str:
    if len(LINK_MENU_CACHE) >= LINK_MENU_CACHE_LIMIT:
        LINK_MENU_CACHE.pop(next(iter(LINK_MENU_CACHE)), None)
    token = secrets.token_urlsafe(9).replace("-", "x").replace("_", "y")
    LINK_MENU_CACHE[token] = {
        "watch": watch_links,
        "download": download_links,
        "back_callback": back_callback,
        "back_label": back_label,
    }
    return token


# ---------------------------------------------------------
# 3. لوحات التحكم (Keyboards)
# ---------------------------------------------------------
def get_main_keyboard():
    """قائمة سينما نوفا المبسطة."""
    markup = types.InlineKeyboardMarkup(row_width=2)
    markup.add(
        types.InlineKeyboardButton("🎬 الأفلام", callback_data="mpage_1_most_viewed"),
        types.InlineKeyboardButton("📺 المسلسلات", callback_data="spage_1_most_viewed"),
        types.InlineKeyboardButton("⛩️ أفلام أنمي", callback_data="ampage_1"),
        types.InlineKeyboardButton("🌸 مسلسلات أنمي", callback_data="aspage_1"),
        types.InlineKeyboardButton("🤼‍♂️ المصارعة الحرة", callback_data="wpage_1"),
        types.InlineKeyboardButton("🔍 بحث شامل", callback_data="src_prompt"),
        types.InlineKeyboardButton("❤️ المفضلة", callback_data="show_favs"),
        types.InlineKeyboardButton("🎲 اقتراح عشوائي", callback_data="random_recommend"),
        types.InlineKeyboardButton("🔙 البوابة الرئيسية", callback_data="hub_home")
    )
    return markup


def build_movies_keyboard(movies: list, page: int, sort_by: str = "most_viewed", is_anime: bool = False):
    markup = types.InlineKeyboardMarkup(row_width=1)
    if not is_anime:
        other_sort = "latest" if sort_by == "most_viewed" else "most_viewed"
        other_label = "🔄 التبديل إلى الأحدث" if sort_by == "most_viewed" else "🔄 التبديل للأكثر مشاهدة"
        markup.add(types.InlineKeyboardButton(other_label, callback_data=f"mpage_1_{other_sort}"))

    for m in movies:
        title = m.get("title_ar") or m.get("title_en", "فيلم")
        year = m.get("release_year", "")
        cb = f"adet_{m['id']}" if is_anime else f"mdet_{m['id']}"
        markup.add(types.InlineKeyboardButton(f"📽️ {title} ({year})", callback_data=cb))

    nav = []
    prefix = "ampage_" if is_anime else "mpage_"
    jump_tag = "jump_am" if is_anime else f"jump_m_{sort_by}"

    if page > 1:
        cb_prev = f"{prefix}{page - 1}" if is_anime else f"{prefix}{page - 1}_{sort_by}"
        nav.append(types.InlineKeyboardButton("⬅️ السابق", callback_data=cb_prev))

    nav.append(types.InlineKeyboardButton(f"🔢 صفحة {page}", callback_data=jump_tag))

    if len(movies) > 0:
        cb_next = f"{prefix}{page + 1}" if is_anime else f"{prefix}{page + 1}_{sort_by}"
        nav.append(types.InlineKeyboardButton("التالي ➡️", callback_data=cb_next))

    markup.row(*nav)
    markup.add(types.InlineKeyboardButton("🔙 رجوع لسينما نوفا", callback_data="hub_nova"))
    markup.add(types.InlineKeyboardButton("📂 القائمة", callback_data="hub_nova"))
    markup.add(types.InlineKeyboardButton("🔍 بحث", callback_data="src_prompt"))
    return markup


def build_series_keyboard(series_list: list, page: int, sort_by: str = "most_viewed", is_anime: bool = False):
    markup = types.InlineKeyboardMarkup(row_width=1)
    if not is_anime:
        other_sort = "latest" if sort_by == "most_viewed" else "most_viewed"
        other_label = "🔄 التبديل إلى الأحدث" if sort_by == "most_viewed" else "🔄 التبديل للأكثر مشاهدة"
        markup.add(types.InlineKeyboardButton(other_label, callback_data=f"spage_1_{other_sort}"))

    for s in series_list:
        title = s.get("title_ar") or s.get("title_en", "مسلسل")
        year = s.get("release_year", "")
        cb = f"adet_{s['id']}" if is_anime else f"sdet_{s['id']}"
        markup.add(types.InlineKeyboardButton(f"📺 {title} ({year})", callback_data=cb))

    nav = []
    prefix = "aspage_" if is_anime else "spage_"
    jump_tag = "jump_as" if is_anime else f"jump_s_{sort_by}"

    if page > 1:
        cb_prev = f"{prefix}{page - 1}" if is_anime else f"{prefix}{page - 1}_{sort_by}"
        nav.append(types.InlineKeyboardButton("⬅️ السابق", callback_data=cb_prev))

    nav.append(types.InlineKeyboardButton(f"🔢 صفحة {page}", callback_data=jump_tag))

    if len(series_list) > 0:
        cb_next = f"{prefix}{page + 1}" if is_anime else f"{prefix}{page + 1}_{sort_by}"
        nav.append(types.InlineKeyboardButton("التالي ➡️", callback_data=cb_next))

    markup.row(*nav)
    markup.add(types.InlineKeyboardButton("🔙 رجوع لسينما نوفا", callback_data="hub_nova"))
    markup.add(types.InlineKeyboardButton("📂 القائمة", callback_data="hub_nova"))
    markup.add(types.InlineKeyboardButton("🔍 بحث", callback_data="src_prompt"))
    return markup


def build_wrestling_keyboard(wrestling_list: list, page: int):
    markup = types.InlineKeyboardMarkup(row_width=1)
    for w in wrestling_list:
        title = w.get("title_ar") or w.get("title_en", "عرض مصارعة")
        date_str = w.get("air_date", "")
        markup.add(types.InlineKeyboardButton(f"🤼‍♂️ {title} ({date_str})", callback_data=f"wdet_{w['id']}"))

    nav = []
    if page > 1:
        nav.append(types.InlineKeyboardButton("⬅️ السابق", callback_data=f"wpage_{page - 1}"))

    nav.append(types.InlineKeyboardButton(f"🔢 صفحة {page}", callback_data="jump_w"))

    if len(wrestling_list) > 0:
        nav.append(types.InlineKeyboardButton("التالي ➡️", callback_data=f"wpage_{page + 1}"))

    markup.row(*nav)
    markup.add(types.InlineKeyboardButton("🔙 رجوع لسينما نوفا", callback_data="hub_nova"))
    markup.add(types.InlineKeyboardButton("📂 القائمة", callback_data="hub_nova"))
    markup.add(types.InlineKeyboardButton("🔍 بحث", callback_data="src_prompt"))
    return markup


def build_series_details_keyboard(series_data: dict, user_id: int, is_anime: bool = False, back_callback: str = "hub_nova", back_label: str = "🔙 رجوع للقائمة"):

    markup = types.InlineKeyboardMarkup(row_width=2)
    seasons = series_data.get("seasons", [])
    s_id = series_data.get("id")

    # إصلاح مواسم الأنمي وتجاوبها بشكل دقيق
    if is_anime:
        valid_seasons = [s for s in seasons if isinstance(s, dict) and s.get("id")] if isinstance(seasons, list) else []
        if valid_seasons:
            for s in valid_seasons:
                s_num = s.get("season_number", 1)
                count = s.get("episodes_count", 0)
                season_id = s.get("id")
                markup.add(types.InlineKeyboardButton(f"📁 الموسم {s_num} ({count} حلقة)", callback_data=f"asn_{s_id}_{season_id}_1"))
        else:
            ep_count = series_data.get("episode_count") or series_data.get("episodes_count") or 0
            count_str = f" ({ep_count} حلقة)" if ep_count else ""
            markup.add(types.InlineKeyboardButton(f"📺 عرض جميع الحلقات{count_str}", callback_data=f"asn_{s_id}_0_1"))
    elif seasons:
        for s in seasons:
            s_num = s.get("season_number", 1)
            count = s.get("episodes_count", 0)
            markup.add(types.InlineKeyboardButton(f"📁 الموسم {s_num} ({count} حلقة)", callback_data=f"sn_{s['id']}_1"))

    favs = get_user_favs(user_id)["series"]
    if str(s_id) in favs or s_id in favs:
        markup.add(types.InlineKeyboardButton("💔 إزالة من المفضلة", callback_data=f"tfav_s_{s_id}"))
    else:
        markup.add(types.InlineKeyboardButton("❤️ إضافة للمفضلة", callback_data=f"tfav_s_{s_id}"))

    markup.add(types.InlineKeyboardButton(back_label, callback_data=back_callback))
    markup.add(types.InlineKeyboardButton("📂 قائمة سينما نوفا", callback_data="hub_nova"))
    markup.add(types.InlineKeyboardButton("🔍 بحث", callback_data="src_prompt"))
    markup.add(types.InlineKeyboardButton("🏠 البوابة الرئيسية", callback_data="hub_home"))
    return markup


def build_episodes_keyboard(episodes: list, parent_id: int, page: int, is_anime: bool = False, season_id: int = 0, back_callback: str = "hub_nova"):
    markup = types.InlineKeyboardMarkup(row_width=4)
    prefix_ep = "aep_" if is_anime else "ep_"

    ep_buttons = [types.InlineKeyboardButton(f"حـ {ep.get('episode_number', '?')}", callback_data=f"{prefix_ep}{ep['id']}") for ep in episodes]
    markup.add(*ep_buttons)

    nav = []
    if is_anime:
        cb_base = f"asn_{parent_id}_{season_id}_"
    else:
        cb_base = f"sn_{parent_id}_"

    if page > 1:
        nav.append(types.InlineKeyboardButton("⬅️", callback_data=f"{cb_base}{page - 1}"))
    nav.append(types.InlineKeyboardButton(f"صفحة {page}", callback_data="noop"))
    if len(episodes) > 0:
        nav.append(types.InlineKeyboardButton("➡️", callback_data=f"{cb_base}{page + 1}"))

    markup.row(*nav)
    markup.add(types.InlineKeyboardButton("🔙 رجوع للمسلسل", callback_data=back_callback))
    markup.add(types.InlineKeyboardButton("📂 قائمة سينما نوفا", callback_data="hub_nova"))
    markup.add(types.InlineKeyboardButton("🔍 بحث", callback_data="src_prompt"))
    markup.add(types.InlineKeyboardButton("🏠 البوابة الرئيسية", callback_data="hub_home"))
    return markup


def _link_url(link: dict) -> str:
    """يستخرج رابط البث من أكثر الحقول شيوعاً، مع تفضيل حقول HLS الصريحة."""
    fields = ("m3u8_url", "m3u_url", "hls_url", "stream_url", "play_url", "url", "link")
    for field in fields:
        value = link.get(field)
        if value:
            return str(value).strip()
    return ""


def _is_m3u_stream(link: dict) -> bool:
    """يتعرف على HLS حتى لو كانت M3U داخل query string أو وسم من الـ API."""
    url = unquote(_link_url(link)).lower()
    metadata_fields = (
        "type", "link_type", "format", "stream_type", "mime_type", "content_type",
        "server_name", "server", "provider", "source", "kind",
    )
    metadata = " ".join(str(link.get(field) or "") for field in metadata_fields).lower()
    stream_markers = (
        ".m3u8", ".m3u", "m3u8", "m3u", "application/vnd.apple.mpegurl",
        "application/x-mpegurl", "application/x-mpegurl", "hls",
    )
    return any(marker in url or marker in metadata for marker in stream_markers)


def _unique_valid_links(links) -> list:
    """يبقي روابط كل نوع مستقلة، مع حذف التكرار داخل النوع نفسه فقط."""
    result, seen_urls = [], set()
    for link in links if isinstance(links, list) else []:
        if not isinstance(link, dict):
            continue
        url = _link_url(link)
        if not url or url in seen_urls:
            continue
        seen_urls.add(url)
        result.append(link)
    return result


def _prepare_link_groups(watch_links: list, download_links: list) -> tuple[list, list]:
    """يطابق API التطبيق: watch_links للمشاهدة المباشرة وdownload_links للتحميل."""
    # سجل الشبكة يبين أن التطبيق قد يشغّل رابط MP4 مباشر من watch_links؛
    # لذلك لا يجوز اشتراط امتداد M3U هنا.
    watch_only = _unique_valid_links(watch_links)
    download_only = _unique_valid_links(download_links)
    return watch_only, download_only


def _quality_label(link: dict, mode: str) -> str:
    quality = str(link.get("quality") or link.get("resolution") or "جودة متاحة").strip()
    server = str(link.get("server_name") or link.get("server") or "").strip()
    size = str(link.get("file_size") or link.get("size") or "").strip()

    details = " — ".join(part for part in ([quality, server] if mode == "watch" else [quality, size]) if part)
    prefix = "▶️ مشاهدة" if mode == "watch" else "📥 تحميل"
    return f"{prefix}: {details}" if details else prefix


def _build_link_menu_keyboard(token: str, stream_links: list, download_links: list, item_id=None, is_movie=True, user_id=None, back_callback: str = "hub_nova", back_label: str = "🔙 رجوع"):
    markup = types.InlineKeyboardMarkup(row_width=2)
    if stream_links:
        markup.add(types.InlineKeyboardButton("▶️ مشاهدة مباشرة", callback_data=f"links_watch_{token}"))
    else:
        markup.add(types.InlineKeyboardButton("▶️ لا توجد روابط مشاهدة", callback_data="noop"))

    if download_links:
        markup.add(types.InlineKeyboardButton("📥 تحميل", callback_data=f"links_download_{token}"))
    else:
        markup.add(types.InlineKeyboardButton("📥 لا توجد روابط تحميل", callback_data="noop"))

    if is_movie and item_id and user_id:
        favs = get_user_favs(user_id)["movies"]
        if str(item_id) in favs or item_id in favs:
            markup.add(types.InlineKeyboardButton("💔 إزالة من المفضلة", callback_data=f"tfav_m_{item_id}"))
        else:
            markup.add(types.InlineKeyboardButton("❤️ إضافة للمفضلة", callback_data=f"tfav_m_{item_id}"))

    markup.add(types.InlineKeyboardButton(back_label, callback_data=back_callback))
    markup.add(types.InlineKeyboardButton("📂 قائمة سينما نوفا", callback_data="hub_nova"))
    markup.add(types.InlineKeyboardButton("🔍 بحث", callback_data="src_prompt"))
    markup.add(types.InlineKeyboardButton("🏠 البوابة الرئيسية", callback_data="hub_home"))
    return markup


def build_links_keyboard(watch_links: list, download_links: list, item_id: int = None, is_movie: bool = True, user_id: int = None, back_callback: str = "hub_nova", back_label: str = "🔙 رجوع"):
    """ينشئ زري مشاهدة/تحميل ثم يعرض الجودة بعد اختيار المستخدم للنوع."""
    stream_links, download_only = _prepare_link_groups(watch_links, download_links)
    token = _store_link_menu(stream_links, download_only, back_callback, back_label)
    return _build_link_menu_keyboard(token, stream_links, download_only, item_id, is_movie, user_id, back_callback, back_label)


def build_link_quality_keyboard(token: str, mode: str):
    links = LINK_MENU_CACHE.get(token, {}).get(mode, [])
    markup = types.InlineKeyboardMarkup(row_width=1)
    for link in links:
        url = _link_url(link)
        if url:
            markup.add(types.InlineKeyboardButton(_quality_label(link, mode), url=url))
    markup.add(types.InlineKeyboardButton("🔙 رجوع لخيارات الروابط", callback_data=f"links_menu_{token}"))
    menu = LINK_MENU_CACHE.get(token, {})
    markup.add(types.InlineKeyboardButton(menu.get("back_label", "🔙 رجوع"), callback_data=menu.get("back_callback", "hub_nova")))
    markup.add(types.InlineKeyboardButton("📂 قائمة سينما نوفا", callback_data="hub_nova"))
    markup.add(types.InlineKeyboardButton("🔍 بحث", callback_data="src_prompt"))
    markup.add(types.InlineKeyboardButton("🏠 البوابة الرئيسية", callback_data="hub_home"))
    return markup


# ---------------------------------------------------------
# 4. معالجة الانتقال المباشر برقم الصفحة
# ---------------------------------------------------------
def process_jump_m(message, sort_by):
    chat_id = message.chat.id
    if not message.text or not message.text.isdigit():
        bot.send_message(chat_id, "❌ <b>رجاءً أدخل رقم صفحة صحيح (أرقام فقط).</b>", reply_markup=get_main_keyboard())
        return

    page = max(1, int(message.text))
    bot.send_message(chat_id, f"⏳ <b>جاري جلب الصفحة {page} للأفلام...</b>")
    res = api.get_movies(page=page, limit=20, sort_by=sort_by)

    if res and res.get("status") == "success":
        movies = res.get("data", [])
        if not movies:
            bot.send_message(chat_id, f"⚠️ <b>لا توجد أفلام في الصفحة {page}.</b>", reply_markup=get_main_keyboard())
            return

        keyboard = build_movies_keyboard(movies, page, sort_by)
        sort_title = "الأكثر مشاهدة 🔥" if sort_by == "most_viewed" else "الأحدث 🆕"
        bot.send_message(chat_id, f"🎬 <b>قائمة الأفلام ({sort_title}) - صفحة {page}:</b>", reply_markup=keyboard)
    else:
        bot.send_message(chat_id, "❌ <b>حدث خطأ أثناء جلب البيانات.</b>", reply_markup=get_main_keyboard())


def process_jump_s(message, sort_by):
    chat_id = message.chat.id
    if not message.text or not message.text.isdigit():
        bot.send_message(chat_id, "❌ <b>رجاءً أدخل رقم صفحة صحيح (أرقام فقط).</b>", reply_markup=get_main_keyboard())
        return

    page = max(1, int(message.text))
    bot.send_message(chat_id, f"⏳ <b>جاري جلب الصفحة {page} للمسلسلات...</b>")
    res = api.get_series(page=page, limit=20, sort_by=sort_by)

    if res and res.get("status") == "success":
        series_list = res.get("data", [])
        if not series_list:
            bot.send_message(chat_id, f"⚠️ <b>لا توجد مسلسلات في الصفحة {page}.</b>", reply_markup=get_main_keyboard())
            return

        keyboard = build_series_keyboard(series_list, page, sort_by)
        sort_title = "الأكثر مشاهدة 🔥" if sort_by == "most_viewed" else "الأحدث 🆕"
        bot.send_message(chat_id, f"📺 <b>قائمة المسلسلات ({sort_title}) - صفحة {page}:</b>", reply_markup=keyboard)
    else:
        bot.send_message(chat_id, "❌ <b>حدث خطأ أثناء جلب البيانات.</b>", reply_markup=get_main_keyboard())


def process_jump_am(message):
    chat_id = message.chat.id
    if not message.text or not message.text.isdigit():
        bot.send_message(chat_id, "❌ <b>رجاءً أدخل رقم صفحة صحيح.</b>", reply_markup=get_main_keyboard())
        return
    page = max(1, int(message.text))
    bot.send_message(chat_id, f"⏳ <b>جاري جلب الصفحة {page} لأفلام الأنمي...</b>")
    res = api.get_anime_movies(page=page, limit=20)
    if res and res.get("status") == "success":
        movies = res.get("data", [])
        if not movies:
            bot.send_message(chat_id, f"⚠️ <b>لا توجد أفلام أنمي في الصفحة {page}.</b>", reply_markup=get_main_keyboard())
            return
        keyboard = build_movies_keyboard(movies, page, is_anime=True)
        bot.send_message(chat_id, f"⛩️ <b>قائمة أفلام الأنمي - صفحة {page}:</b>", reply_markup=keyboard)


def process_jump_as(message):
    chat_id = message.chat.id
    if not message.text or not message.text.isdigit():
        bot.send_message(chat_id, "❌ <b>رجاءً أدخل رقم صفحة صحيح.</b>", reply_markup=get_main_keyboard())
        return
    page = max(1, int(message.text))
    bot.send_message(chat_id, f"⏳ <b>جاري جلب الصفحة {page} لمسلسلات الأنمي...</b>")
    res = api.get_anime_series(page=page, limit=20)
    if res and res.get("status") == "success":
        series_list = res.get("data", [])
        if not series_list:
            bot.send_message(chat_id, f"⚠️ <b>لا توجد مسلسلات أنمي في الصفحة {page}.</b>", reply_markup=get_main_keyboard())
            return
        keyboard = build_series_keyboard(series_list, page, is_anime=True)
        bot.send_message(chat_id, f"🌸 <b>قائمة مسلسلات الأنمي - صفحة {page}:</b>", reply_markup=keyboard)


def process_jump_w(message):
    chat_id = message.chat.id
    if not message.text or not message.text.isdigit():
        bot.send_message(chat_id, "❌ <b>رجاءً أدخل رقم صفحة صحيح.</b>", reply_markup=get_main_keyboard())
        return
    page = max(1, int(message.text))
    bot.send_message(chat_id, f"⏳ <b>جاري جلب الصفحة {page} لعروض المصارعة...</b>")
    res = api.get_wrestling(page=page, limit=20)
    if res and res.get("status") == "success":
        wrestling_list = res.get("data", [])
        if not wrestling_list:
            bot.send_message(chat_id, f"⚠️ <b>لا توجد عروض مصارعة في الصفحة {page}.</b>", reply_markup=get_main_keyboard())
            return
        keyboard = build_wrestling_keyboard(wrestling_list, page)
        bot.send_message(chat_id, f"🤼‍♂️ <b>قائمة عروض المصارعة - صفحة {page}:</b>", reply_markup=keyboard)


# ---------------------------------------------------------
# 6. معالجة الأوامر والبحث
# ---------------------------------------------------------
@bot.message_handler(commands=["start"])
def send_welcome(message):
    """استقبال آمن لأمر البداية، مناسب لتشغيل Pydroid 3."""
    try:
        user = message.from_user
        reset_navigation(user.id)
        register_user(user.id, user.username or "", user.first_name or "")
        safe_name = html_escape(user.first_name or "صديقي")
        bot.send_message(
            message.chat.id,
            f"<b>✨ أهلاً بك يا {safe_name} في عالم المشاهدة!</b>\n\nاختر وجهتك من البوابتين بالأسفل:",
            reply_markup=get_hub_keyboard(user.id),
        )
    except Exception as exc:
        print(f"START handler error: {exc!r}")
        bot.send_message(message.chat.id, "✨ أهلاً بك في عالم المشاهدة!", reply_markup=get_hub_keyboard(message.from_user.id))

@bot.message_handler(commands=["search"])
def search_command(message):
    user = message.from_user
    register_user(user.id, user.username or "", user.first_name or "")

    msg = bot.send_message(message.chat.id, "🔍 <b>أدخل اسم الفيلم أو المسلسل للبحث:</b>")
    bot.register_next_step_handler(msg, process_search)


def process_search(message):
    query = message.text.strip() if message.text else ""
    if not query:
        bot.send_message(message.chat.id, "❌ إدخال غير صالح.", reply_markup=get_main_keyboard())
        return

    bot.send_message(message.chat.id, "⏳ <b>جاري البحث في قاعدة البيانات...</b>")

    s_res = api.search_series(query=query, page=1, limit=10)
    m_res = api.search_movies(query=query, page=1, limit=10)

    series_list = s_res.get("data", []) if s_res and s_res.get("status") == "success" else []
    movies_list = m_res.get("data", []) if m_res and m_res.get("status") == "success" else []

    if not series_list and not movies_list:
        bot.send_message(
            message.chat.id,
            f"❌ لم يتم العثور على أي نتائج لـ: <b>{query}</b>",
            reply_markup=get_main_keyboard(),
        )
        return

    markup = types.InlineKeyboardMarkup(row_width=1)

    if series_list:
        markup.add(types.InlineKeyboardButton("─── 📺 نتائج المسلسلات ───", callback_data="noop"))
        for s in series_list:
            title = s.get("title_ar") or s.get("title_en", "مسلسل")
            year = s.get("release_year", "")
            ep_count = s.get("episode_count")
            ep_str = f" | {ep_count} حلقة" if ep_count else ""
            markup.add(types.InlineKeyboardButton(f"📺 {title} ({year}){ep_str}", callback_data=f"sdet_{s['id']}"))

    if movies_list:
        markup.add(types.InlineKeyboardButton("─── 🎬 نتائج الأفلام ───", callback_data="noop"))
        for m in movies_list:
            title = m.get("title_ar") or m.get("title_en", "فيلم")
            year = m.get("release_year", "")
            markup.add(types.InlineKeyboardButton(f"📽️ {title} ({year})", callback_data=f"mdet_{m['id']}"))

    markup.add(types.InlineKeyboardButton("🔙 رجوع لسينما نوفا", callback_data="hub_nova"))
    markup.add(types.InlineKeyboardButton("🔍 بحث جديد", callback_data="src_prompt"))
    nav_context(message.from_user.id)["legacy_list"] = "legacy_search"
    NAV_CURRENT[message.from_user.id] = "legacy_search"
    bot.send_message(message.chat.id, f"🔍 <b>نتائج البحث عن ({query}):</b>", reply_markup=markup)



UNIFIED_SEARCH_STATE = {}


def unified_search_results(query: str):
    """يجلب النتائج ويحفظها في أربع مجموعات منفصلة: مكتبة × نوع."""
    query = query.strip()[:80]
    nova_movies_response = api.search_movies(query=query, page=1, limit=12)
    nova_series_response = api.search_series(query=query, page=1, limit=12)
    nova_movies = nova_movies_response.get("data", []) if nova_movies_response and nova_movies_response.get("status") == "success" else []
    nova_series = nova_series_response.get("data", []) if nova_series_response and nova_series_response.get("status") == "success" else []
    orion_movies, _ = vault_api.list_content("movies", page=1, limit=12, search=query)
    orion_series, _ = vault_api.list_content("series", page=1, limit=12, search=query)
    return {
        "nova_movies": nova_movies or [],
        "nova_series": nova_series or [],
        "orion_movies": orion_movies or [],
        "orion_series": orion_series or [],
    }


def unified_overview_keyboard(results):
    """اختيار المكتبة ثم النوع قبل إظهار العناصر، لمنع اختلاط الأفلام بالمسلسلات."""
    markup = types.InlineKeyboardMarkup(row_width=2)
    markup.add(types.InlineKeyboardButton("── 🌟 سينما نوفا ──", callback_data="noop"))
    markup.add(
        types.InlineKeyboardButton(f"🎬 أفلام ({len(results['nova_movies'])})", callback_data="unified_list:nova:m"),
        types.InlineKeyboardButton(f"📺 مسلسلات ({len(results['nova_series'])})", callback_data="unified_list:nova:s"),
    )
    markup.add(types.InlineKeyboardButton("── 🎞️ أوريون بلس ──", callback_data="noop"))
    markup.add(
        types.InlineKeyboardButton(f"🎬 أفلام ({len(results['orion_movies'])})", callback_data="unified_list:orion:m"),
        types.InlineKeyboardButton(f"📺 مسلسلات ({len(results['orion_series'])})", callback_data="unified_list:orion:s"),
    )
    setattr(markup, "_sections_callback", "hub_home")
    return markup


def unified_type_results_keyboard(results, library: str, kind: str):
    key = f"{library}_{'movies' if kind == 'm' else 'series'}"
    items = results.get(key, [])
    markup = types.InlineKeyboardMarkup(row_width=1)
    icon = "🎬" if kind == "m" else "📺"
    if not items:
        markup.add(types.InlineKeyboardButton("لا توجد نتائج مطابقة في هذا القسم", callback_data="noop"))
    for item in items:
        if library == "nova":
            title = item.get("title_ar") or item.get("title_en") or ("فيلم" if kind == "m" else "مسلسل")
            callback = f"mdet_{item['id']}" if kind == "m" else f"sdet_{item['id']}"
        else:
            title = vault_title(item)
            callback = f"vault_item:{kind}:{item['id']}"
        markup.add(types.InlineKeyboardButton(f"{icon} {title}"[:60], callback_data=callback))
    markup.add(types.InlineKeyboardButton("🔙 رجوع لنتائج البحث", callback_data="unified_results"))
    setattr(markup, "_sections_callback", "hub_home")
    return markup


def show_unified_results(chat_id: int, user_id: int, query: str, message_id=None):
    results = unified_search_results(query)
    UNIFIED_SEARCH_STATE[user_id] = {"query": query, "results": results}
    NAV_CURRENT[user_id] = "unified_results"
    title = f"<b>🔍 نتائج البحث عن: {html_escape(query)}</b>\n\n"
    title += "اختر أولاً المكتبة، ثم اختر أفلام أو مسلسلات."
    if not any(results.values()):
        title += "\n\n⚠️ لم تظهر نتائج مطابقة في أي مكتبة."
    markup = unified_overview_keyboard(results)
    if message_id:
        safe_edit_or_send(chat_id, message_id, title, markup)
    else:
        bot.send_message(chat_id, title, reply_markup=markup)


def show_unified_type_results(chat_id: int, user_id: int, library: str, kind: str, message_id):
    state = UNIFIED_SEARCH_STATE.get(user_id, {})
    results = state.get("results")
    if not results:
        return False
    library_title = "سينما نوفا" if library == "nova" else "أوريون بلس"
    kind_title = "أفلام" if kind == "m" else "مسلسلات"
    title = f"<b>{'🌟' if library == 'nova' else '🎞️'} {library_title} — {kind_title}</b>\nاختر النتيجة المطلوبة:"
    safe_edit_or_send(chat_id, message_id, title, unified_type_results_keyboard(results, library, kind))
    return True


def process_unified_search(message):
    query = (message.text or "").strip()
    if len(query) < 2:
        bot.send_message(message.chat.id, "❌ اكتب كلمتين على الأقل للبحث.", reply_markup=get_hub_keyboard(message.from_user.id))
        return
    bot.send_message(message.chat.id, "⏳ <b>جاري البحث في المكتبتين...</b>")
    show_unified_results(message.chat.id, message.from_user.id, query)


# ---------------------------------------------------------
# 7. معالجة الأحداث والأزرار (Callbacks)
# ---------------------------------------------------------
@bot.callback_query_handler(func=lambda call: True)
def handle_callbacks(call):
    # دمج آمن: callbacks الخاصة بالنظام الآخر لا يعالجها هذا النظام.
    data = getattr(call, "data", "") or ""
    _youseif_prefixes = (
        "main", "t:", "qk:", "hg:", "hc:", "hi:", "lt:", "lp:", "li:",
        "g:", "gp:", "c:", "i:", "f:", "w:", "s:", "e:", "p:",
        "act:", "adm:", "sr:"
    )
    if data == "noop" or data.startswith(_youseif_prefixes):
        return

    chat_id = call.message.chat.id
    user = call.from_user
    user_id = user.id
    data = call.data

    register_user(user_id, user.username or "", user.first_name or "")

    if data == "nav_back":
        history = NAV_HISTORY.get(user_id, [])
        if not history:
            bot.answer_callback_query(call.id, "لا توجد شاشة سابقة.", show_alert=True)
            return
        target = history.pop()
        NAV_CURRENT[user_id] = target
        NAV_REPLAY.add(user_id)
        call.data = target
        handle_callbacks(call)
        return

    track_navigation(user_id, data)

    if data == "unified_search":
        bot.answer_callback_query(call.id)
        prompt = bot.send_message(chat_id, "🔍 <b>اكتب اسم الفيلم أو المسلسل للبحث في المكتبتين:</b>")
        bot.register_next_step_handler(prompt, process_unified_search)
        return

    if data.startswith("unified_list:"):
        _, library, kind = data.split(":", 2)
        if library not in {"nova", "orion"} or kind not in {"m", "s"}:
            bot.answer_callback_query(call.id, "خيار غير صالح.", show_alert=True)
            return
        bot.answer_callback_query(call.id)
        if not show_unified_type_results(chat_id, user_id, library, kind, call.message.message_id):
            bot.answer_callback_query(call.id, "انتهت جلسة البحث، ابحث من جديد.", show_alert=True)
        return

    if data == "unified_results":
        query = UNIFIED_SEARCH_STATE.get(user_id, {}).get("query")
        if not query:
            bot.answer_callback_query(call.id, "ابدأ بحثاً جديداً أولاً.", show_alert=True)
            return
        bot.answer_callback_query(call.id)
        show_unified_results(chat_id, user_id, query, call.message.message_id)
        return

    if handle_vault_callbacks(call):
        return

    if data == "noop":
        bot.answer_callback_query(call.id)
        return

    if data == "legacy_search":
        bot.answer_callback_query(call.id)
        msg = bot.send_message(chat_id, "🔍 <b>أدخل اسم الفيلم أو المسلسل للبحث:</b>")
        bot.register_next_step_handler(msg, process_search)
        return

    # --- قوائم روابط المشاهدة والتحميل ---
    if data.startswith("links_menu_"):
        token = data.removeprefix("links_menu_")
        menu = LINK_MENU_CACHE.get(token)
        if not menu:
            bot.answer_callback_query(call.id, "انتهت صلاحية قائمة الروابط. افتح تفاصيل المحتوى مجدداً.", show_alert=True)
            return
        bot.answer_callback_query(call.id)
        markup = _build_link_menu_keyboard(token, menu["watch"], menu["download"], is_movie=False, back_callback=menu.get("back_callback", "hub_nova"), back_label=menu.get("back_label", "🔙 رجوع"))
        bot.send_message(chat_id, "<b>اختر نوع الرابط:</b>", reply_markup=markup)
        return

    if data.startswith("links_watch_") or data.startswith("links_download_"):
        mode = "watch" if data.startswith("links_watch_") else "download"
        prefix = f"links_{mode}_"
        token = data.removeprefix(prefix)
        menu = LINK_MENU_CACHE.get(token)
        if not menu:
            bot.answer_callback_query(call.id, "انتهت صلاحية قائمة الروابط. افتح تفاصيل المحتوى مجدداً.", show_alert=True)
            return
        links = menu[mode]
        if not links:
            bot.answer_callback_query(call.id, "لا توجد روابط متاحة لهذا الخيار.", show_alert=True)
            return
        title = "<b>اختر جودة المشاهدة:</b>" if mode == "watch" else "<b>اختر جودة التحميل:</b>"
        bot.answer_callback_query(call.id)
        bot.send_message(chat_id, title, reply_markup=build_link_quality_keyboard(token, mode))
        return

    # --- عروض المصارعة الحرة ---
    elif data.startswith("wpage_"):
        nav_context(user_id)["legacy_list"] = data
        page = int(data.split("_")[1])
        bot.answer_callback_query(call.id, "جاري تحميل عروض المصارعة...")
        res = api.get_wrestling(page=page, limit=20)
        if res and res.get("status") == "success":
            wrestling_list = res.get("data", [])
            if not wrestling_list and page > 1:
                bot.answer_callback_query(call.id, "⚠️ وصلت لنهاية القائمة.", show_alert=True)
                return
            keyboard = build_wrestling_keyboard(wrestling_list, page)
            safe_edit_or_send(chat_id, call.message.message_id, f"🤼‍♂️ <b>قائمة عروض المصارعة - صفحة {page}:</b>", keyboard)

    elif data.startswith("wdet_"):
        w_id = int(data.split("_")[1])
        bot.answer_callback_query(call.id, "جاري تحميل تفاصيل عرض المصارعة...")
        res = api.get_wrestling_details(w_id)

        if res and res.get("status") == "success":
            w = res["data"]
            title = w.get("title_ar") or w.get("title_en", "")
            air_date = w.get("air_date", "N/A")
            cat_name = w.get("category", {}).get("name", "غير محدد") if w.get("category") else "غير محدد"
            desc = w.get("description") or "لا يوجد وصف إضافي."

            caption = f"🤼‍♂️ <b>{title}</b>\n📅 تاريخ العرض: <b>{air_date}</b>\n🏷️ الفئة: <b>{cat_name}</b>\n\n📝 <b>الوصف:</b>\n<i>{desc[:400]}</i>"

            poster = w.get("poster")
            poster_url = f"{api.BASE_MEDIA_URL}{poster}" if poster else None
            keyboard = build_links_keyboard(w.get("watch_links", []), w.get("download_links", []), is_movie=False, user_id=user_id, back_callback=nav_context(user_id).get("legacy_list", "hub_nova"), back_label="🔙 رجوع لقائمة المصارعة")

            send_media_with_fallback(chat_id, call.message.message_id, poster_url, caption, keyboard)

    elif data == "jump_w":
        bot.answer_callback_query(call.id)
        msg = bot.send_message(chat_id, "🔢 <b>أدخل رقم صفحة المصارعة التي تريد الانتقال إليها:</b>")
        bot.register_next_step_handler(msg, process_jump_w)

    # --- أفلام أنمي ---
    elif data.startswith("ampage_"):
        nav_context(user_id)["legacy_list"] = data
        page = int(data.split("_")[1])
        bot.answer_callback_query(call.id, "جاري تحميل أفلام الأنمي...")
        res = api.get_anime_movies(page=page, limit=20)
        if res and res.get("status") == "success":
            movies = res.get("data", [])
            if not movies and page > 1:
                bot.answer_callback_query(call.id, "⚠️ وصلت لنهاية الأفلام.", show_alert=True)
                return
            keyboard = build_movies_keyboard(movies, page, is_anime=True)
            safe_edit_or_send(chat_id, call.message.message_id, f"⛩️ <b>قائمة أفلام الأنمي - صفحة {page}:</b>", keyboard)

    # --- مسلسلات أنمي ---
    elif data.startswith("aspage_"):
        nav_context(user_id)["legacy_list"] = data
        page = int(data.split("_")[1])
        bot.answer_callback_query(call.id, "جاري تحميل مسلسلات الأنمي...")
        res = api.get_anime_series(page=page, limit=20)
        if res and res.get("status") == "success":
            series_list = res.get("data", [])
            if not series_list and page > 1:
                bot.answer_callback_query(call.id, "⚠️ وصلت لنهاية المسلسلات.", show_alert=True)
                return
            keyboard = build_series_keyboard(series_list, page, is_anime=True)
            safe_edit_or_send(chat_id, call.message.message_id, f"🌸 <b>قائمة مسلسلات الأنمي - صفحة {page}:</b>", keyboard)

    # --- تفاصيل الأنمي (فيلم / مسلسل) ---
    elif data.startswith("adet_"):
        a_id = int(data.split("_")[1])
        bot.answer_callback_query(call.id, "جاري تحميل تفاصيل الأنمي...")
        res = api.get_anime_details(a_id)

        if res and res.get("status") == "success":
            a = res["data"]
            title = a.get("title_ar") or a.get("title_en", "")
            year = a.get("release_year", "N/A")
            rating = a.get("rating", "N/A")
            story = a.get("story") or "لا توجد قصة متاحة."
            anime_type = a.get("anime_type", "tv")
            genres = parse_genres(a.get("genres") or a.get("genre_list"))
            genres_str = f"\n🏷️ التصنيف: {genres}" if genres else ""

            caption = f"🌸 <b>{title}</b> ({year})\n⭐ التقييم: {rating}{genres_str}\n\n📝 <b>القصة:</b>\n<i>{story[:500]}</i>"
            poster = a.get("poster")
            poster_url = f"{api.BASE_MEDIA_URL}{poster}" if poster else None

            if anime_type == "movie" or (a.get("watch_links") and not a.get("episodes_count")):
                keyboard = build_links_keyboard(a.get("watch_links", []), a.get("download_links", []), item_id=a_id, is_movie=True, user_id=user_id, back_callback=nav_context(user_id).get("legacy_list", "hub_nova"), back_label="🔙 رجوع للقائمة")
            else:
                keyboard = build_series_details_keyboard(a, user_id, is_anime=True, back_callback=nav_context(user_id).get("legacy_list", "hub_nova"), back_label="🔙 رجوع لقائمة الأنمي")

            nav_context(user_id)["legacy_series_detail"] = data
            send_media_with_fallback(chat_id, call.message.message_id, poster_url, caption, keyboard)

    # --- جلب حلقات الأنمي (معالجة إصلاح زر الموسم والمواسم المتعددة) ---
    elif data.startswith("asn_"):
        parts = data.split("_")
        anime_id = int(parts[1])
        
        # التنسيق الجديد: asn_{anime_id}_{season_id}_{page}
        if len(parts) >= 4:
            season_id = int(parts[2])
            page = int(parts[3])
        elif len(parts) == 3:
            season_id = 0
            page = int(parts[2])
        else:
            season_id = 0
            page = 1

        nav_context(user_id)["legacy_episodes"] = data
        bot.answer_callback_query(call.id, "جاري تحميل حلقات الأنمي...")
        
        # طلب الحلقات مع إرسال season_id إن وجد
        res = api.get_anime_episodes(anime_id=anime_id, page=page, per_page=20, season_id=season_id if season_id > 0 else None)

        if res and res.get("status") == "success":
            episodes = res.get("data", [])
            if not episodes and page > 1:
                bot.answer_callback_query(call.id, "⚠️ لا توجد حلقات أخرى.", show_alert=True)
                return
            elif not episodes:
                bot.answer_callback_query(call.id, "⚠️ لم يتم العثور على حلقات لهذا الموسم.", show_alert=True)
                return

            keyboard = build_episodes_keyboard(episodes, parent_id=anime_id, page=page, is_anime=True, season_id=season_id, back_callback=nav_context(user_id).get("legacy_series_detail", "hub_nova"))
            safe_edit_or_send(chat_id, call.message.message_id, f"🌸 <b>حلقات الأنمي - صفحة {page}:</b>", keyboard)

    # --- تفاصيل حلقة الأنمي ---
    elif data.startswith("aep_"):
        ep_id = int(data.split("_")[1])
        bot.answer_callback_query(call.id, "جاري تحميل روابط الحلقة...")
        res = api.get_anime_episode_details(ep_id)

        if res and res.get("status") == "success":
            ep = res["data"]
            anime_title = ep.get("anime_title") or ep.get("anime_title_en", "أنمي")
            ep_num = ep.get("episode_number", "?")
            caption = f"📺 <b>{anime_title}</b> - الحلقة <b>{ep_num}</b>"

            thumb = ep.get("thumbnail") or ep.get("anime_poster")
            thumb_url = f"{api.BASE_MEDIA_URL}{thumb}" if thumb and str(thumb).startswith("/") else thumb

            keyboard = build_links_keyboard(ep.get("watch_links", []), ep.get("download_links", []), is_movie=False, user_id=user_id, back_callback=nav_context(user_id).get("legacy_episodes", "hub_nova"), back_label="🔙 رجوع للحلقات")
            send_media_with_fallback(chat_id, call.message.message_id, thumb_url, caption, keyboard)

    # --- الانتقال لرقم صفحة أنمي ---
    elif data == "jump_am":
        bot.answer_callback_query(call.id)
        msg = bot.send_message(chat_id, "🔢 <b>أدخل رقم صفحة أفلام الأنمي التي تريد الانتقال إليها:</b>")
        bot.register_next_step_handler(msg, process_jump_am)

    elif data == "jump_as":
        bot.answer_callback_query(call.id)
        msg = bot.send_message(chat_id, "🔢 <b>أدخل رقم صفحة مسلسلات الأنمي التي تريد الانتقال إليها:</b>")
        bot.register_next_step_handler(msg, process_jump_as)

    # --- اقتراح عشوائي ---
    elif data == "random_recommend":
        bot.answer_callback_query(call.id, "🎲 جاري جلب اقتراح رائع لك...")
        res = api.get_movies(page=random.randint(1, 5), limit=20)
        if res and res.get("status") == "success":
            movies = res.get("data", [])
            if movies:
                m = random.choice(movies)
                m_id = m['id']
                res_det = api.get_movie_details(m_id)
                if res_det and res_det.get("status") == "success":
                    m_data = res_det["data"]
                    title = m_data.get("title_ar") or m_data.get("title_en", "")
                    year = m_data.get("release_year", "N/A")
                    rating = m_data.get("rating", "N/A")
                    story = m_data.get("story") or "لا توجد قصة متاحة."
                    caption = f"🎲 <b>اقتراح اليوم العشوائي:</b>\n\n🎬 <b>{title}</b> ({year})\n⭐ التقييم: {rating}\n\n📝 <b>القصة:</b>\n<i>{story[:400]}</i>"

                    poster = m_data.get("poster")
                    poster_url = f"{api.BASE_MEDIA_URL}{poster}" if poster else None
                    keyboard = build_links_keyboard(m_data.get("watch_links", []), m_data.get("download_links", []), item_id=m_id, is_movie=True, user_id=user_id)

                    send_media_with_fallback(chat_id, call.message.message_id, poster_url, caption, keyboard)
                    return

        bot.send_message(chat_id, "❌ تعذر جلب اقتراح الآن، حاول لاحقاً.", reply_markup=get_main_keyboard())

    elif data == "main_menu":
        bot.answer_callback_query(call.id)
        safe_edit_or_send(chat_id, call.message.message_id, "<b>✨ اختر وجهتك السينمائية:</b>", reply_markup=get_hub_keyboard(user_id))

    elif data == "src_prompt":
        bot.answer_callback_query(call.id)
        msg = bot.send_message(chat_id, "🔍 <b>أدخل اسم الفيلم أو المسلسل للبحث:</b>")
        bot.register_next_step_handler(msg, process_search)

    elif data.startswith("jump_m_"):
        sort_by = data.split("_")[2]
        bot.answer_callback_query(call.id)
        msg = bot.send_message(chat_id, "🔢 <b>أدخل رقم صفحة الأفلام التي تريد الانتقال إليها:</b>")
        bot.register_next_step_handler(msg, process_jump_m, sort_by)

    elif data.startswith("jump_s_"):
        sort_by = data.split("_")[2]
        bot.answer_callback_query(call.id)
        msg = bot.send_message(chat_id, "🔢 <b>أدخل رقم صفحة المسلسلات التي تريد الانتقال إليها:</b>")
        bot.register_next_step_handler(msg, process_jump_s, sort_by)

    elif data == "show_favs":
        nav_context(user_id)["legacy_list"] = "show_favs"
        bot.answer_callback_query(call.id)
        favs = get_user_favs(user_id)
        m_favs, s_favs = favs.get("movies", {}), favs.get("series", {})

        if not m_favs and not s_favs:
            bot.send_message(chat_id, "❤️ <b>قائمة المفضلة لديك فارغة حالياً.</b>", reply_markup=get_main_keyboard())
            return

        markup = types.InlineKeyboardMarkup(row_width=1)

        if m_favs:
            markup.add(types.InlineKeyboardButton("─── 🎬 الأفلام المفضلة ───", callback_data="noop"))
            for m_id, title in m_favs.items():
                markup.add(types.InlineKeyboardButton(f"📽️ {title}", callback_data=f"mdet_{m_id}"))

        if s_favs:
            markup.add(types.InlineKeyboardButton("─── 📺 المسلسلات المفضلة ───", callback_data="noop"))
            for s_id, title in s_favs.items():
                markup.add(types.InlineKeyboardButton(f"📺 {title}", callback_data=f"sdet_{s_id}"))

        markup.add(types.InlineKeyboardButton("🔙 رجوع لسينما نوفا", callback_data="hub_nova"))
        markup.add(types.InlineKeyboardButton("🔍 بحث", callback_data="src_prompt"))
        bot.send_message(chat_id, "❤️ <b>قائمة المفضلة الخاصة بك:</b>", reply_markup=markup)

    elif data.startswith("tfav_"):
        parts = data.split("_")
        item_type, item_id = parts[1], str(parts[2])
        favs = get_user_favs(user_id)
        target_dict = favs["movies"] if item_type == "m" else favs["series"]

        if item_id in target_dict:
            target_dict.pop(item_id, None)
            bot.answer_callback_query(call.id, "💔 تم الإزالة من المفضلة!")
        else:
            title = "عنصر مفضل"
            if item_type == "m":
                details = api.get_movie_details(int(item_id))
                if details and details.get("status") == "success":
                    title = details["data"].get("title_ar") or details["data"].get("title_en", "فيلم")
            else:
                details = api.get_series_details(int(item_id))
                if details and details.get("status") == "success":
                    title = details["data"].get("title_ar") or details["data"].get("title_en", "مسلسل")

            target_dict[item_id] = title
            bot.answer_callback_query(call.id, "❤️ تم الإضافة إلى المفضلة!")

        save_user_favs(user_id, favs)

    elif data.startswith("mpage_"):
        nav_context(user_id)["legacy_list"] = data
        parts = data.split("_")
        page = int(parts[1])
        sort_by = parts[2] if len(parts) > 2 else "most_viewed"

        bot.answer_callback_query(call.id, "جاري تحميل قائمة الأفلام...")
        res = api.get_movies(page=page, limit=20, sort_by=sort_by)

        if res and res.get("status") == "success":
            movies = res.get("data", [])
            if not movies and page > 1:
                bot.answer_callback_query(call.id, "⚠️ لا توجد أفلام أخرى، وصلت إلى نهاية القائمة.", show_alert=True)
                return

            keyboard = build_movies_keyboard(movies, page, sort_by)
            sort_title = "الأكثر مشاهدة 🔥" if sort_by == "most_viewed" else "الأحدث 🆕"
            safe_edit_or_send(chat_id, call.message.message_id, f"🎬 <b>قائمة الأفلام ({sort_title}) - صفحة {page}:</b>", keyboard)

    elif data.startswith("mdet_"):
        m_id = int(data.split("_")[1])
        bot.answer_callback_query(call.id, "جاري تحميل التفاصيل...")
        res = api.get_movie_details(m_id)

        if res and res.get("status") == "success":
            m = res["data"]
            title = m.get("title_ar") or m.get("title_en", "")
            year, rating = m.get("release_year", "N/A"), m.get("rating", "N/A")
            story = m.get("story") or "لا توجد قصة متاحة."
            genres = parse_genres(m.get("genres"))
            genres_str = f"\n🏷️ التصنيف: {genres}" if genres else ""

            caption = f"🎬 <b>{title}</b> ({year})\n⭐ التقييم: {rating}{genres_str}\n\n📝 <b>القصة:</b>\n<i>{story[:500]}</i>"
            poster = m.get("poster")
            poster_url = f"{api.BASE_MEDIA_URL}{poster}" if poster else None
            keyboard = build_links_keyboard(m.get("watch_links", []), m.get("download_links", []), item_id=m_id, is_movie=True, user_id=user_id, back_callback=nav_context(user_id).get("legacy_list", "hub_nova"), back_label="🔙 رجوع لقائمة الأفلام")

            send_media_with_fallback(chat_id, call.message.message_id, poster_url, caption, keyboard)

    elif data.startswith("spage_"):
        nav_context(user_id)["legacy_list"] = data
        parts = data.split("_")
        page = int(parts[1])
        sort_by = parts[2] if len(parts) > 2 else "most_viewed"

        bot.answer_callback_query(call.id, "جاري تحميل المسلسلات...")
        res = api.get_series(page=page, limit=20, sort_by=sort_by)

        if res and res.get("status") == "success":
            series_list = res.get("data", [])
            if not series_list and page > 1:
                bot.answer_callback_query(call.id, "⚠️ لا توجد مسلسلات أخرى، وصلت إلى نهاية القائمة.", show_alert=True)
                return

            keyboard = build_series_keyboard(series_list, page, sort_by)
            sort_title = "الأكثر مشاهدة 🔥" if sort_by == "most_viewed" else "الأحدث 🆕"
            safe_edit_or_send(chat_id, call.message.message_id, f"📺 <b>قائمة المسلسلات ({sort_title}) - صفحة {page}:</b>", keyboard)

    elif data.startswith("sdet_"):
        s_id = int(data.split("_")[1])
        bot.answer_callback_query(call.id, "جاري تحميل المسلسل والمواسم...")
        res = api.get_series_details(s_id)

        if res and res.get("status") == "success":
            s = res["data"]
            title = s.get("title_ar") or s.get("title_en", "")
            year, rating = s.get("release_year", "N/A"), s.get("rating", "N/A")
            story = s.get("story") or "لا توجد قصة متاحة."
            genres = parse_genres(s.get("genres"))
            genres_str = f"\n🏷️ التصنيف: {genres}" if genres else ""

            caption = f"📺 <b>{title}</b> ({year})\n⭐ التقييم: {rating}{genres_str}\n\n📝 <b>القصة:</b>\n<i>{story[:500]}</i>"
            poster = s.get("poster")
            poster_url = f"{api.BASE_MEDIA_URL}{poster}" if poster else None
            keyboard = build_series_details_keyboard(s, user_id, back_callback=nav_context(user_id).get("legacy_list", "hub_nova"), back_label="🔙 رجوع لقائمة المسلسلات")

            nav_context(user_id)["legacy_series_detail"] = data
            send_media_with_fallback(chat_id, call.message.message_id, poster_url, caption, keyboard)

    elif data.startswith("sn_"):
        parts = data.split("_")
        season_id = int(parts[1])
        page = int(parts[2]) if len(parts) > 2 else 1

        nav_context(user_id)["legacy_episodes"] = data
        bot.answer_callback_query(call.id, "جاري تحميل الحلقات...")
        res = api.get_season_episodes(season_id=season_id, page=page, per_page=20)

        if res and res.get("status") == "success":
            episodes = res.get("data", [])
            if not episodes and page > 1:
                bot.answer_callback_query(call.id, "⚠️ لا توجد حلقات أخرى في هذا الموسم.", show_alert=True)
                return

            keyboard = build_episodes_keyboard(episodes, season_id, page, is_anime=False, back_callback=nav_context(user_id).get("legacy_series_detail", "hub_nova"))
            safe_edit_or_send(chat_id, call.message.message_id, f"📁 <b>حلقات الموسم - صفحة {page}:</b>", keyboard)

    elif data.startswith("ep_"):
        ep_id = int(data.split("_")[1])
        bot.answer_callback_query(call.id, "جاري تحميل روابط الحلقة...")
        res = api.get_episode_details(ep_id)

        if res and res.get("status") == "success":
            ep = res["data"]
            series_title = ep.get("series_title") or ep.get("series_title_en", "المسلسل")
            ep_num = ep.get("episode_number", "?")
            caption = f"📺 <b>{series_title}</b> - الحلقة <b>{ep_num}</b>"

            thumb = ep.get("thumbnail") or ep.get("series_poster")
            thumb_url = f"{api.BASE_MEDIA_URL}{thumb}" if thumb and str(thumb).startswith("/") else thumb

            keyboard = build_links_keyboard(ep.get("watch_links", []), ep.get("download_links", []), is_movie=False, user_id=user_id, back_callback=nav_context(user_id).get("legacy_episodes", "hub_nova"), back_label="🔙 رجوع للحلقات")
            send_media_with_fallback(chat_id, call.message.message_id, thumb_url, caption, keyboard)


# ---------------------------------------------------------
# 8. تشغيل البوت — مناسب للشبكات المتقطعة على Pydroid
# ---------------------------------------------------------
def run_bot_forever():
    retry_delay = 5
    print("🤖 Bot is starting...")
    while True:
        try:
            # skip_pending=False يتجنب طلب تخطي التحديثات الذي قد يفشل فورياً على بعض الشبكات.
            bot.infinity_polling(
                skip_pending=False,
                timeout=20,
                long_polling_timeout=20,
                logger_level=40,
            )
        except KeyboardInterrupt:
            print("\n🛑 تم إيقاف البوت.")
            break
        except (requests.exceptions.RequestException, ConnectionError, OSError) as exc:
            print(f"⚠️ تعذر الاتصال بـ Telegram: {exc.__class__.__name__}. إعادة المحاولة بعد {retry_delay} ثوانٍ...")
            time.sleep(retry_delay)
        except Exception as exc:
            # لا يطبع Traceback طويلاً في Pydroid؛ يعيد المحاولة ويُبقي البوت متاحاً.
            print(f"⚠️ توقف الاستقبال مؤقتاً: {exc.__class__.__name__}. إعادة المحاولة بعد {retry_delay} ثوانٍ...")
            time.sleep(retry_delay)


