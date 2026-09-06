# -*- coding: utf-8 -*-
"""
بوت أنمي لــ Pydroid 3 — ملف واحد.
التثبيت داخل Pydroid 3: pip install requests
ثم شغّل هذا الملف.
"""
import os, time, json, html, traceback
from urllib.parse import quote
import requests

# إعدادات الاختبار التي زوّدني بها المستخدم — لا تحذفها أثناء التطوير
BOT_TOKEN = os.getenv("BOT_TOKEN", "8988500207:AAHB1QmzRi4J8iuRO8TZtv3aaWySB6ApPPc").strip()
ADMIN_ID = int(os.getenv("ADMIN_ID", "8358047016"))

ALGOLIA_APP_ID = os.getenv("ALGOLIA_APP_ID", "D8LH9I7ZL7")
ALGOLIA_KEY = os.getenv("ALGOLIA_KEY", "b56c01ef52540ef334bcdbaa00ded9e4")
FIREBASE_PROJECT = os.getenv("FIREBASE_PROJECT", "animewitcher-1c66d")
# اختياري: API رسمي تملكه ويعيد {watch, download, subtitle}
EPISODE_API_BASE = os.getenv("EPISODE_API_BASE", "").rstrip("/")

TG = "https://api.telegram.org/bot" + BOT_TOKEN
ALGOLIA = "https://d8lh9i7zl7-dsn.algolia.net/1/indexes"
S = requests.Session()
S.headers.update({"User-Agent": "AnimeBot-Pydroid3/1.0"})
USER_DATA = {}
FAV_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "anime_favorites.json")

def load_favs():
    try:
        with open(FAV_FILE, "r", encoding="utf-8") as f: return json.load(f)
    except Exception: return {}

FAVS = load_favs()

def save_favs():
    try:
        with open(FAV_FILE, "w", encoding="utf-8") as f: json.dump(FAVS, f, ensure_ascii=False, indent=2)
    except Exception: pass



def tg(method, data=None, timeout=35):
    r = S.post(TG + "/" + method, data=data or {}, timeout=timeout)
    r.raise_for_status()
    obj = r.json()
    if not obj.get("ok"):
        raise RuntimeError(obj.get("description", "Telegram API error"))
    return obj.get("result")


def send(chat_id, text, keyboard=None, parse_mode=None):
    data = {"chat_id": chat_id, "text": text, "disable_web_page_preview": True}
    if keyboard: data["reply_markup"] = json.dumps({"inline_keyboard": keyboard}, ensure_ascii=False)
    if parse_mode: data["parse_mode"] = parse_mode
    return tg("sendMessage", data)


def edit(chat_id, message_id, text, keyboard=None, parse_mode=None):
    data = {"chat_id": chat_id, "message_id": message_id, "text": text}
    if keyboard: data["reply_markup"] = json.dumps({"inline_keyboard": keyboard}, ensure_ascii=False)
    if parse_mode: data["parse_mode"] = parse_mode
    return tg("editMessageText", data)


def algolia(index, query="", hits=8, filters=""):
    attrs = ["objectID", "name", "tags", "poster_uri", "poster", "cover_uri", "path", "type", "details", "dubbed", "doc_ref", "anime_id", "episode_id", "episode_name", "thumb_uri"]
    params = {"attributesToRetrieve": json.dumps(attrs, ensure_ascii=False, separators=(",", ":")), "hitsPerPage": hits, "page": 0, "query": query}
    if filters: params["filters"] = filters
    r = S.get(ALGOLIA + "/" + index, headers={"X-Algolia-Application-Id": ALGOLIA_APP_ID, "X-Algolia-API-Key": ALGOLIA_KEY}, params=params, timeout=25)
    r.raise_for_status()
    return r.json().get("hits", [])


def browse(index, filters="", hits=10):
    attrs = ["objectID", "name", "title", "news_link", "thumb_link", "tags", "poster_uri", "poster", "cover_uri", "path", "type", "details", "anime_id"]
    params = {"attributesToRetrieve": json.dumps(attrs, ensure_ascii=False, separators=(",", ":")), "page": 0, "hitsPerPage": hits}
    if filters: params["filters"] = filters
    r = S.get(ALGOLIA + "/" + index + "/browse", headers={"X-Algolia-Application-Id": ALGOLIA_APP_ID, "X-Algolia-API-Key": ALGOLIA_KEY}, params=params, timeout=25)
    r.raise_for_status(); return r.json().get("hits", [])


def firestore_value(v):
    if "stringValue" in v: return v["stringValue"]
    if "integerValue" in v: return int(v["integerValue"])
    if "doubleValue" in v: return v["doubleValue"]
    if "booleanValue" in v: return v["booleanValue"]
    if "timestampValue" in v: return v["timestampValue"]
    if "nullValue" in v: return None
    if "mapValue" in v: return {k: firestore_value(x) for k, x in v.get("mapValue", {}).get("fields", {}).items()}
    if "arrayValue" in v: return [firestore_value(x) for x in v.get("arrayValue", {}).get("values", [])]
    return v


def details(name):
    url = "https://firestore.googleapis.com/v1/projects/%s/databases/(default)/documents/anime_list/%s" % (FIREBASE_PROJECT, quote(name, safe=""))
    r = S.get(url, timeout=20)
    if r.status_code != 200: return {}
    return firestore_value({"mapValue": {"fields": r.json().get("fields", {})}})


def episode_summary(anime):
    url = "https://firestore.googleapis.com/v1/projects/%s/databases/(default)/documents/anime_list/%s/episodes_summery?pageSize=100" % (FIREBASE_PROJECT, quote(anime, safe=""))
    r = S.get(url, timeout=25)
    if r.status_code != 200: return []
    out = []
    for d in r.json().get("documents", []):
        fields = firestore_value({"mapValue": {"fields": d.get("fields", {})}})
        out.extend(fields.get("episodes", []))
    return out


def episode_servers(anime, episode_id):
    url = "https://firestore.googleapis.com/v1/projects/%s/databases/(default)/documents/anime_list/%s/episodes/%s/servers?pageSize=100" % (FIREBASE_PROJECT, quote(anime, safe=""), quote(str(episode_id), safe=""))
    r = S.get(url, timeout=25)
    if r.status_code != 200: return []
    out = []
    for d in r.json().get("documents", []):
        x = firestore_value({"mapValue": {"fields": d.get("fields", {})}})
        if x.get("visible") and x.get("link") and x.get("name"):
            out.append(x)
    return out


def name_of(x): return str(x.get("name") or x.get("objectID") or "بدون اسم")
def ep_of(x): return str(x.get("episode_name") or x.get("episode_id") or "حلقة")


def main_menu():
    return [[{"text": "بحث عن أنمي", "callback_data": "help"}, {"text": "عرض كل الأنمي", "callback_data": "all"}], [{"text": "الأكثر مشاهدة", "callback_data": "popular"}, {"text": "الأعلى تفضيلًا", "callback_data": "rank"}], [{"text": "المضاف حديثًا", "callback_data": "new"}, {"text": "آخر الحلقات", "callback_data": "recent"}], [{"text": "المواسم", "callback_data": "seasons"}], [{"text": "حسب الحروف", "callback_data": "alpha"}, {"text": "التصنيفات", "callback_data": "genres"}], [{"text": "أخبار الأنمي", "callback_data": "news"}, {"text": "المانجا", "callback_data": "manga"}], [{"text": "المفضلة", "callback_data": "favs"}]]


def show_results(chat_id, items, title="نتائج البحث"):
    if not items: return send(chat_id, "لم أجد نتائج مطابقة.")
    rows = [[{"text": name_of(x)[:55], "callback_data": "a:%d" % i}] for i, x in enumerate(items)]
    send(chat_id, title, rows)


def callback(q):
    qid, msg = q["id"], q.get("message", {})
    chat_id = msg.get("chat", {}).get("id"); mid = msg.get("message_id"); data = q.get("data", "")
    try:
        tg("answerCallbackQuery", {"callback_query_id": qid})
        u = USER_DATA.setdefault(chat_id, {})
        if data == "help": edit(chat_id, mid, "أرسل اسم الأنمي في رسالة جديدة للبحث."); return
        if data == "all":
            u["results"] = browse("all_animation", "", 20); edit_results(chat_id, mid, u["results"], "كل الأنمي"); return
        if data == "alpha":
            u["results"] = browse("series_name_asc", "", 20); edit_results(chat_id, mid, u["results"], "كل الأنمي بالترتيب الأبجدي"); return
        if data == "rank":
            u["results"] = algolia("series_fav_count_desc", "", 20); edit_results(chat_id, mid, u["results"], "الأعلى تفضيلًا"); return
        if data == "new":
            u["results"] = algolia("series_date_created", "", 20); edit_results(chat_id, mid, u["results"], "المضاف حديثًا"); return
        if data == "seasons":
            seasons = []
            for year in range(2026, 2018, -1):
                for s in ("شتاء", "ربيع", "صيف", "خريف"): seasons.append((s + " عام " + str(year)))
            kb = [[{"text": x, "callback_data": "season:" + x}] for x in seasons]
            edit(chat_id, mid, "اختر الموسم — القائمة كاملة:", kb); return
        if data == "genres":
            genres = ["اكشن", "مغامرات", "كوميدي", "دراما", "رومانسي", "خيال", "رعب", "مدرسي", "شريحة من الحياة", "رياضي", "ميكا", "غموض", "نفسي", "خارق للطبيعة"]
            edit(chat_id, mid, "اختر التصنيف:", [[{"text": g, "callback_data": "genre:" + g}] for g in genres]); return
        if data.startswith("genre:"):
            g = data[6:]; u["results"] = browse("series", 'tags:"%s"' % g, 20); edit_results(chat_id, mid, u["results"], "تصنيف: " + g); return
        if data.startswith("season:"):
            season = data[7:]; u["results"] = browse("series", 'details.season:"%s"' % season, 20); edit_results(chat_id, mid, u["results"], season); return
        if data == "news":
            items = algolia("news", "", 10); u["news"] = items
            rows = [[{"text": str(x.get("title", "خبر"))[:55], "url": x.get("news_link", "https://www.crunchyroll.com/news")} ] for x in items if x.get("news_link")]
            edit(chat_id, mid, "آخر أخبار الأنمي:", rows or None); return
        if data == "manga":
            u["results"] = browse("manga", "", 12); edit_results(chat_id, mid, u["results"], "أحدث المانجا"); return
        if data == "favs":
            names = FAVS.get(str(chat_id), []); items = [{"name": n, "objectID": n, "path": "anime_list/" + n} for n in names]; u["results"] = items; edit_results(chat_id, mid, items, "المفضلة"); return
        if data == "popular":
            u["results"] = algolia("most_watched_animations", "", 8); edit_results(chat_id, mid, u["results"], "الأكثر مشاهدة"); return
        if data == "recent":
            u["episodes"] = algolia("recent", "", 12); edit_episodes(chat_id, mid, u["episodes"]); return
        if data.startswith("a:"):
            x = u.get("results", [])[int(data[2:])]
            n = str(x.get("path", "")).replace("anime_list/", "", 1) if x.get("path") else str(x.get("objectID") or x.get("name"))
            d = details(n) or x.get("details") or {}
            text = "<b>%s</b>\n" % html.escape(n)
            for k, label in (("year", "السنة"), ("state", "الحالة"), ("eps_num", "عدد الحلقات")):
                if d.get(k): text += "%s: %s\n" % (label, html.escape(str(d[k])))
            text += "النوع: %s\n\n" % html.escape(str(x.get("type", "")))
            u["anime"] = n
            fav = n in FAVS.get(str(chat_id), [])
            edit(chat_id, mid, text + "اختر من الخيارات:", [[{"text": "عرض الحلقات", "callback_data": "e"}], [{"text": "إزالة من المفضلة" if fav else "إضافة للمفضلة", "callback_data": "fav"}]], "HTML"); return
        if data == "fav":
            n = u.get("anime", ""); key = str(chat_id); arr = FAVS.setdefault(key, [])
            if n in arr: arr.remove(n); label = "تمت الإزالة من المفضلة."
            else: arr.append(n); label = "تمت الإضافة إلى المفضلة."
            save_favs(); edit(chat_id, mid, label, [[{"text": "العودة للتفاصيل", "callback_data": "back"}]]); return
        if data == "back":
            edit(chat_id, mid, "اكتب اسم الأنمي لفتح التفاصيل من جديد."); return
        if data == "e":
            n = u.get("anime", ""); raw = episode_summary(n)
            u["anime"] = n
            u["episodes"] = [{"name": n, "episode_id": x.get("doc_id"), "episode_name": x.get("name"), "thumb_uri": x.get("thumb_uri")} for x in raw]
            edit_episodes(chat_id, mid, u["episodes"]); return
        if data.startswith("p:"):
            x = u.get("episodes", [])[int(data[2:])]; n = name_of(x); ep = ep_of(x); ep_id = x.get("episode_id") or x.get("doc_id")
            servers = episode_servers(n, ep_id)
            text = "<b>%s</b> — %s" % (html.escape(n), html.escape(ep))
            kb = []
            order = {"SF": 0, "ST": 1, "MF2": 2, "PD": 3, "KF": 4}
            for s in sorted(servers, key=lambda z: (order.get(str(z.get("name")), 9), str(z.get("quality", "")))):
                label = "%s %s" % (s.get("name", "مصدر"), s.get("quality", ""))
                kb.append([{"text": "مشاهدة %s" % label, "url": s["link"]}])
            if not kb: text += "\n\nلا توجد روابط ظاهرة لهذه الحلقة حاليًا."
            edit(chat_id, mid, text, kb or None, "HTML"); return
    except Exception:
        edit(chat_id, mid, "تعذر تنفيذ الطلب حاليًا. جرّب مرة أخرى.")


def edit_results(chat_id, mid, items, title):
    if not items: return edit(chat_id, mid, "لم أجد نتائج.")
    rows = [[{"text": name_of(x)[:55], "callback_data": "a:%d" % i}] for i, x in enumerate(items)]
    edit(chat_id, mid, title, rows)


def edit_episodes(chat_id, mid, items):
    if not items: return edit(chat_id, mid, "لا توجد حلقات ظاهرة في المصدر.")
    rows = [[{"text": "%s — %s" % (name_of(x)[:35], ep_of(x)), "callback_data": "p:%d" % i}] for i, x in enumerate(items[:15])]
    edit(chat_id, mid, "اختر الحلقة:", rows)


def handle_message(m):
    chat = m.get("chat", {}); cid = chat.get("id"); text = (m.get("text") or "").strip()
    if not cid: return
    if text.startswith("/start"):
        send(cid, "أهلًا بك في بوت الأنمي. أرسل اسم الأنمي للبحث، أو اختر من القائمة.", main_menu()); return
    if text.startswith("/help") or text.startswith("/menu"):
        send(cid, "اختر وظيفة:", main_menu()); return
    if text.startswith("/all"):
        try: USER_DATA.setdefault(cid, {})["results"] = browse("all_animation", "", 20); show_results(cid, USER_DATA[cid]["results"], "كل الأنمي")
        except Exception: send(cid, "تعذر تحميل كل الأنمي.")
        return
    if text.startswith("/seasons"):
        send(cid, "اختر الموسم:", [[{"text": s + " عام " + str(y), "callback_data": "season:" + s + " عام " + str(y)}] for y in range(2026, 2018, -1) for s in ("شتاء", "ربيع", "صيف", "خريف")])
        return
    if text.startswith("/rank"):
        try: USER_DATA.setdefault(cid, {})["results"] = algolia("series_fav_count_desc", "", 20); show_results(cid, USER_DATA[cid]["results"], "الأعلى تفضيلًا")
        except Exception: send(cid, "تعذر تحميل الترتيب.")
        return
    if text.startswith("/new"):
        try: USER_DATA.setdefault(cid, {})["results"] = algolia("series_date_created", "", 20); show_results(cid, USER_DATA[cid]["results"], "المضاف حديثًا")
        except Exception: send(cid, "تعذر تحميل الإضافات الجديدة.")
        return
    if text.startswith("/popular"):
        try: USER_DATA.setdefault(cid, {})["results"] = algolia("most_watched_animations", "", 8); show_results(cid, USER_DATA[cid]["results"], "الأكثر مشاهدة")
        except Exception: send(cid, "تعذر تحميل القائمة.")
        return
    if text.startswith("/latest"):
        try: USER_DATA.setdefault(cid, {})["episodes"] = algolia("recent", "", 12); send(cid, "آخر الحلقات:", [[{"text": "%s — %s" % (name_of(x)[:35], ep_of(x)), "callback_data": "p:%d" % i}] for i,x in enumerate(USER_DATA[cid]["episodes"])])
        except Exception: send(cid, "تعذر تحميل الحلقات.")
        return
    if text.startswith("/news"):
        try:
            items=algolia("news", "", 10); rows=[[{"text": str(x.get("title","خبر"))[:55], "url": x.get("news_link")}] for x in items if x.get("news_link")]; send(cid,"آخر الأخبار:",rows)
        except Exception: send(cid,"تعذر تحميل الأخبار.")
        return
    if text.startswith("/manga"):
        try: items=browse("manga", "", 12); USER_DATA.setdefault(cid, {})["results"]=items; show_results(cid,items,"المانجا")
        except Exception: send(cid,"تعذر تحميل المانجا.")
        return
    if len(text) < 2: send(cid, "اكتب اسم أنمي للبحث."); return
    try:
        items = algolia("series", text, 8); USER_DATA.setdefault(cid, {})["results"] = items; show_results(cid, items)
    except Exception:
        send(cid, "تعذر الوصول لمصدر البيانات. حاول لاحقًا.")


def run():
    print("Anime bot started. Stop with Ctrl+C")
    offset = None
    while True:
        try:
            params = {"timeout": 25, "allowed_updates": json.dumps(["message", "callback_query"])}
            if offset is not None: params["offset"] = offset
            updates = tg("getUpdates", params, timeout=40)
            for upd in updates:
                offset = upd["update_id"] + 1
                if upd.get("callback_query"): callback(upd["callback_query"])
                elif upd.get("message"): handle_message(upd["message"])
        except KeyboardInterrupt: print("Stopped"); break
        except Exception as e:
            print("Error:", e); time.sleep(5)

if __name__ == "__main__": run()
