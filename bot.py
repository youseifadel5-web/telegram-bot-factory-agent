# -*- coding: utf-8 -*-
"""
🎬 𝑌𝑜𝑢𝑠𝑒𝑖𝑓 𝐹𝑖𝑙𝑚𝑠 — بوت تيليجرام سينمائي احترافي
═══════════════════════════════════════════════════════════
• Xtream Codes API: قنوات مباشرة + أفلام + مسلسلات (مواسم/حلقات)
• تشغيل مباشر من روابط المصدر الأصلية — أزرار مشاهدة + بث
• TMDB محسّن: بوسترات + بيانات عربية/إنجليزية + تقييمات
• بحث ذكي ثنائي اللغة مع مطابقة جزئية ومرنة
• حماية المحتوى المقيد بكلمة مرور يديرها مالك البوت فقط
• أزرار مرتبة ومتناسقة + لوحة أدمن (باسورد/إحصائيات/بث)
═══════════════════════════════════════════════════════════
الأسرار (3 فقط) من البيئة / GitHub Secrets: BOT_TOKEN, API_ID, API_HASH
باقي الإعدادات من config.py — TMDB_API_KEY من GitHub Secrets فقط
"""
import os
import re
import sys
import json
import time
import html
import random
import sqlite3
import asyncio
import difflib
import logging
from typing import Dict, List, Optional, Tuple

# ══════════════ أسرار من GitHub Secrets فقط ══════════════
# BOT_TOKEN / API_ID / API_HASH / TMDB_API_KEY
BOT_TOKEN     = os.getenv("BOT_TOKEN", "").strip()
API_ID        = os.getenv("API_ID", "").strip()
API_HASH      = os.getenv("API_HASH", "").strip()
# TMDB من البيئة أولاً (GitHub Secret) — لا تحتاج تضعه في config.py
TMDB_API_KEY  = os.getenv("TMDB_API_KEY", "").strip()
TMDB_READ_TOKEN = os.getenv("API_Read_Access_Token", "").strip()

if not BOT_TOKEN:
    print("❌ BOT_TOKEN مفقود! ضعه في GitHub Secrets أو متغيرات البيئة.")
    sys.exit(1)

# ══════════════ الإعدادات من config.py ══════════════
try:
    import config as _cfg
except ImportError:
    print("⚠️ config.py غير موجود — سيتم استخدام قيم افتراضية.")
    _cfg = None


def _c(name, default):
    return getattr(_cfg, name, default) if _cfg else default


_ADMIN_ID_RAW = os.getenv("ADMIN_ID", "").strip() or str(_c("ADMIN_ID", "")).strip()
try:
    ADMIN_ID = int(_ADMIN_ID_RAW) if _ADMIN_ID_RAW else 0
except ValueError:
    ADMIN_ID = 0
try:
    _legacy_admins = [int(x) for x in _c("ADMIN_IDS", []) if str(x).isdigit() and int(x) > 0]
except Exception:
    _legacy_admins = []
ADMIN_IDS = ([ADMIN_ID] if ADMIN_ID > 0 else _legacy_admins)
IPTV_USERNAME    = str(_c("IPTV_USERNAME", "")).strip()
IPTV_PASSWORD    = str(_c("IPTV_PASSWORD", "")).strip()
IPTV_BASE_URL    = str(_c("IPTV_BASE_URL", "")).strip().rstrip("/")
IPTV_BACKUP_URLS = [u.strip().rstrip("/") for u in _c("IPTV_BACKUP_URLS", []) if str(u).strip()]

# احتياطي: لو TMDB مش في Secrets يقرأ من config (اختياري)
if not TMDB_API_KEY:
    TMDB_API_KEY = str(_c("TMDB_API_KEY", "")).strip()

ITEMS_PER_PAGE   = int(_c("ITEMS_PER_PAGE", 10))
CACHE_DURATION   = int(_c("CACHE_DURATION", 600))
REQUEST_TIMEOUT  = int(_c("REQUEST_TIMEOUT", 30))
MAX_RETRIES      = int(_c("MAX_RETRIES", 3))
BOT_NAME         = str(_c("BOT_NAME", "𝑌𝑜𝑢𝑠𝑒𝑖𝑓 𝐹𝑖𝑙𝑚𝑠 🎬"))
DB_PATH          = str(_c("DB_PATH", "cinema_bot.db"))

BASES = [b for b in [IPTV_BASE_URL] + IPTV_BACKUP_URLS if b]
if not IPTV_USERNAME or not IPTV_PASSWORD or not BASES:
    print("❌ بيانات IPTV ناقصة في config.py (IPTV_USERNAME / IPTV_PASSWORD / IPTV_BASE_URL)")
    sys.exit(1)

logging.basicConfig(format="%(asctime)s [%(levelname)s] %(message)s", level=logging.INFO)
log = logging.getLogger("youseif-films")

try:
    import httpx
    from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup, BotCommand
    from telegram.constants import ParseMode
    from telegram.ext import (
        Application, CommandHandler, CallbackQueryHandler,
        MessageHandler, ContextTypes, filters,
    )
    from telegram.error import RetryAfter, TimedOut, NetworkError, BadRequest
except ImportError:
    print("❌ ثبّت المتطلبات: pip install -r requirements.txt")
    sys.exit(1)


# ══════════════ أدوات مساعدة ══════════════
def esc(t) -> str:
    return html.escape(str(t or ""))


def is_admin(user_id: int) -> bool:
    return bool(ADMIN_IDS) and user_id in ADMIN_IDS


# ── حماية محتوى الكبار: كلمات مفتاحية ──
ADULT_KEYWORDS = re.compile(
    r"(?i)\b(ADULTE?|ADULT|XXX|PORN|SEX|18\+|للكبار|كبار فقط|للبالغين)\b"
)


def is_adult_name(name: str) -> bool:
    """يتحقق هل الاسم/القسم ينتمي لمحتوى كبار."""
    return bool(ADULT_KEYWORDS.search(str(name or "")))

NON_ISLAMIC_RELIGION_KEYWORDS = re.compile(
    r"(?i)(christian|christianity|church|coptic|bible|gospel|jesus|‫مسيحي|‫مسيحية|‫كنيسة|‫قبطي|‫انجيل|‫إنجيل|‫يهودي|‫يهودية|jewish|judaism|torah|synagogue|‫يهود|‫شيعي|‫شيعة|shia|shiite|‫اثني عشر|‫بوذي|‫هندوسي|‫هندوسية|buddhist|buddhism|hindu|hinduism|sikh|sikhism|‫سيخي|‫سيخية)"
)


def is_non_islamic_religious(name: str) -> bool:
    return bool(NON_ISLAMIC_RELIGION_KEYWORDS.search(str(name or "")))


# كلمات تقنية تُحذف من الأسماء (جودة، سنوات، أكواد)
_NOISE_WORDS = re.compile(
    r"(?i)\b(VOD|SERIE|S[ÉE]RIE|4K|8K|FHD|UHD|H265|HEVC|HD|SD|HQ|MULTI|TRUEFRENCH|"
    r"RAMADAN\s*\d{4}|RAMADAN|X264|X265|WEB[- ]?DL|WEBRIP|BLURAY|BDRIP|HDRIP|DVDRIP|"
    r"CAM|TS|HDCAM|SUBFRENCH|VOSTFR|FRENCH|EXTENDED|UNRATED|REMUX|PROPER|REPACK|"
    r"AAC|AC3|DTS|NF|AMZN|DSNP|HMAX|PCOK|ATVP|iT|WEB)\b"
)
_NOISE_BRACKETS = re.compile(r"\[[A-Za-z0-9]{1,6}\]")


def clean_name(raw) -> str:
    """🧹 تنظيف آلي: يشيل [AR]_ وكلمات الجودة والسنوات والرموز الفنية."""
    s = str(raw or "").strip()
    s = _NOISE_BRACKETS.sub("", s)                 # [AR] [FR] [IT]
    s = _NOISE_WORDS.sub("", s)                    # VOD 4K FHD WEB-DL...
    s = re.sub(r"\(([^)]*)\)",
               lambda m: m.group(0) if re.fullmatch(r"\s*\d{4}\s*", m.group(1)) else " ", s)  # احتفظ بقوس سنة صافية
    s = re.sub(r"\(\s*\)", "", s)               # أقواس فاضية
    s = s.replace("(", " ").replace(")", " ")      # أي قوس متبقٍ مكسور → مسافة
    s = re.sub(r"[_\-]{2,}", " ", s)              # رموز مكررة
    s = re.sub(r"\s{2,}", " ", s)                 # مسافات مكررة
    s = s.strip(" _-()")
    return s or str(raw or "بدون عنوان").strip()


# 🌍 خريطة ترجمة الأقسام: كود الدولة → (علم، اسم عربي)
COUNTRY_MAP = {
    "AR": ("🇪🇬", "عربي"), "FR": ("🇫🇷", "فرنسي"), "DE": ("🇩🇪", "ألماني"),
    "EN": ("🇬🇧", "إنجليزي"), "US": ("🇺🇸", "أمريكي"), "TR": ("🇹🇷", "تركي"),
    "ES": ("🇪🇸", "إسباني"), "IT": ("🇮🇹", "إيطالي"), "IN": ("🇮🇳", "هندي"),
    "KR": ("🇰🇷", "كوري"), "EG": ("🇪🇬", "مصري"), "MA": ("🇲🇦", "مغربي"),
    "TN": ("🇹🇳", "تونسي"), "DZ": ("🇩🇿", "جزائري"), "SA": ("🇸🇦", "سعودي"),
}
# 🎭 خريطة نوع المحتوى → (إيموجي، اسم عربي)
GENRE_MAP = {
    "ANIMATION": ("🧸", "أنيميشن"), "ANIME": ("⛩️", "أنمي"),
    "ACTION": ("💥", "أكشن"), "COMEDY": ("😂", "كوميدي"),
    "DRAMA": ("🎭", "دراما"), "HORROR": ("👻", "رعب"),
    "ROMANCE": ("💕", "رومانسي"), "THRILLER": ("🔪", "إثارة"),
    "CRIME": ("🕵️", "جريمة"), "FAMILY": ("👨‍👩‍👧", "عائلي"),
    "FANTASTIC": ("🪄", "فانتازيا"), "FANTASY": ("🪄", "فانتازيا"),
    "SCIFI": ("🚀", "خيال علمي"), "SCI-FI": ("🚀", "خيال علمي"),
    "DOCUMENTARY": ("📚", "وثائقي"), "DOC": ("📚", "وثائقي"),
    "KIDS": ("🧒", "أطفال"), "SPORT": ("⚽", "رياضة"), "SPORTS": ("⚽", "رياضة"),
    "NEWS": ("📰", "إخبارية"), "MUSIC": ("🎵", "موسيقى"),
    "SERIE": ("📺", "مسلسلات"), "SERIES": ("📺", "مسلسلات"),
    "MOVIE": ("🎬", "أفلام"), "VOD": ("🎬", "أفلام"),
    "ADVENTURE": ("🗺️", "مغامرات"), "MYSTERY": ("🔮", "غموض"),
    "WAR": ("⚔️", "حربي"), "WESTERN": ("🤠", "غربي"),
    "HISTORY": ("📜", "تاريخي"), "BIOGRAPHY": ("👤", "سيرة ذاتية"),
    "CLASSIC": ("🎞️", "كلاسيكيات"), "ISLAMIC": ("🕌", "إسلامي"),
    "RELIGIOUS": ("🕌", "ديني"), "COOKING": ("🍳", "طبخ"),
    "ENTERTAINMENT": ("🎉", "منوعات"), "CINEMA": ("🎬", "سينما"),
}


def pretty_category(raw: str) -> str:
    """
    يحوّل اسم القسم الجاف لصيغة أنيقة بالعربي.
    مثال: 'VOD DE ANIMATION' → '🇩🇪 أنيميشن ألماني'
    """
    s = str(raw or "").strip()
    if not s:
        return "📁 عام"
    # لو الاسم عربي أصلاً، رجّعه زي ما هو
    if re.search(r"[\u0600-\u06FF]", s):
        return s
    upper = re.sub(r"[^\w\s&/-]", " ", s.upper())
    tokens = re.split(r"[\s&/|_-]+", upper)
    flag, country, icon, genre = "", "", "🎬", ""
    generic = {"VOD", "MOVIE", "SERIE", "SERIES"}   # أنواع عامة — أولوية أقل
    for t in tokens:
        if t and t in COUNTRY_MAP and not country:
            flag, country = COUNTRY_MAP[t]
    # مرور أول: نوع محدد (أنيميشن، أكشن، رعب...)
    for t in tokens:
        if t and t in GENRE_MAP and t not in generic and not genre:
            icon, genre = GENRE_MAP[t]
    # مرور ثاني: نوع عام لو مفيش محدد
    if not genre:
        for t in tokens:
            if t and t in GENRE_MAP and not genre:
                icon, genre = GENRE_MAP[t]
    if genre and country:
        return f"{flag} {genre} {country}"
    if genre:
        return f"{icon} {genre}"
    if country:
        return f"{flag} محتوى {country}"
    # fallback: اسم نظيف بالإنجليزي
    return f"{icon} {clean_name(s).title()[:28]}"



# ══════════════════════════════════════════════════════════════════
# 🧠 محرك التصنيف النوعي الذكي (Genre-Based Categorization Engine)
# ══════════════════════════════════════════════════════════════════
# بدل عرض أقسام السيرفر الخام (المكررة والمختلطة)، كل قسم خام بيتم
# تصنيفه ذكائياً تحت فئة رئيسية ثابتة حسب نوعه: نوع المحتوى + اللغة.
# ══════════════════════════════════════════════════════════════════

# 🎭 خريطة النوع (Genre) — الكلمة المفتاحية → (إيموجي، اسم عربي)
GENRE_RULES = [
    # (كلمات مفتاحية بالإنجليزي/الفرنسي, الإيموجي, الاسم العربي)
    (["HORROR", "HORREUR"],                          "👻", "رعب"),
    (["COMEDY", "COMEDIE", "COMÉDIE", "COMIC"],      "😂", "كوميدي"),
    (["ACTION", "POLICIER"],                         "💥", "أكشن"),
    (["DRAMA", "DRAME"],                             "🎭", "دراما"),
    (["ANIMATION", "ANIME", "CARTOON", "MANGAS"],    "🧸", "أنيميشن"),
    (["KIDS", "CHILD", "ENFANT"],                    "🧒", "أطفال"),
    (["DOCUMENTAIRE", "DOCU", "DOCUMENTARY", "NATURE"], "📚", "وثائقيات"),
    (["ROMANCE", "ROMANTIC"],                        "💕", "رومانسي"),
    (["SCIENCE-FICTION", "SCI-FI", "SCIFI", "SCIENCE"],"🚀", "خيال علمي"),
    (["FANTASTIC", "FANTASY", "FANTASTIQUE"],        "🪄", "فانتازيا"),
    (["FAMILY", "FAMILLE", "FAMILIAL"],              "👨‍👩‍👧", "عائلي"),
    (["MARVEL", "COMICS", "SUPERHERO"],              "🦸", "مارفل وكوميكس"),
    (["WESTERN"],                                    "🤠", "وسترن"),
    (["THRILLER", "CRIME", "SUSPENSE"],              "🔪", "إثارة وجريمة"),
    (["SPORT", "WWE", "UFC", "BOXE", "FIGHT", "LIGUE", "DAZN", "FOOT"],
                                                     "💪", "رياضة ومصارعة"),
    (["SPECTACLE", "CONCERT", "MUSIC", "THEATRE", "THEATER"],
                                                     "🎤", "حفلات ومسرحيات"),
    (["CULTE", "CLASSIC", "ZAMAN", "OLD"],           "🎞️", "كلاسيكيات"),
    (["BOLLYWOOD", "INDIA", "HINDI"],                "🇮🇳", "هندي"),
    (["MEDICAL"],                                    "🏥", "طبي"),
    (["ADVENTURE", "AVENTURE"],                      "🗺️", "مغامرات"),
    (["WAR", "GUERRE"],                              "⚔️", "حربي"),
    (["HISTORY", "HISTOIRE", "HISTORICAL"],          "📜", "تاريخي"),
    (["MYSTERY", "MYSTERE"],                         "🔮", "غموض"),
    (["BIOGRAPHY", "BIOPIC"],                        "👤", "سيرة ذاتية"),
    (["MUSICAL"],                                    "🎵", "موسيقي"),
    (["EMISSION", "SHOW", "TV"],                     "📺", "برامج تلفزيونية"),
    (["RELIGION", "ISLAMIC", "RELIGIEUX", "QURAN"],  "🕌", "إسلامي"),
    (["NEWS", "INFO"],                               "📰", "إخبارية"),
    (["COOKING", "CUISINE"],                         "🍳", "طبخ"),
    (["RELAX", "LOUNGE"],                            "🌿", "استرخاء"),
    (["ADULTE", "ADULT", "XXX"],                     "🔞", "للكبار فقط"),
]

# 🌍 خريطة اللغة/الدولة — الكلمة المفتاحية → (علم، اسم عربي)
LOCALE_RULES = [
    (["RAMADAN", "رمضان"],                           "🌙", "رمضانيات"),
    (["SUB AR", "SUBAR", "VOSTFR", "SUB ARABE", "مترجم"],
                                                     "🇬🇧", "مترجمة عربي"),
    (["مدبلج", "DUBBED", "DUB"],                     "🎙️", "مدبلجة"),
    (["TUNIS", "TUNISIE", "TUNISIA"],                "🇹🇳", "تونسية"),
    (["MAROC", "MOROCCO", "ALGERI", "ALGERIA", "ALGÉRIE", "MAGHREB"],
                                                     "🌙", "مغاربية"),
    (["EGYPT", "EGYPTE", "MASr", "مصر"],             "🇪🇬", "مصرية"),
    (["ARABE", "ARABIC", "AR ", "ARAB", "عربي"],     "🇸🇦", "عربية"),
    (["TURC", "TURK", "TURKISH", "تركي"],            "🇹🇷", "تركية"),
    (["FR ", "FRANCE", "FRANÇAIS", "FRANCAIS", "VF", " FRENCH", "VOD FR", "SÉRIE", "SERIE FR"],
                                                     "🇫🇷", "فرنسية"),
    (["KURD"],                                       "☀️", "كردية"),
    (["PERSIAN", "IRAN", "FARSI"],                   "🇮🇷", "إيرانية"),
    (["KOREA", "KDRAMA", "ASIAN", "ASIE"],           "🇰🇷", "كورية وآسيوية"),
    (["NETFLIX", "FULLBOX"],                         "🍿", "منصات عالمية"),
]

# 🇬🇧 دول البث المباشر — الكلمة → (علم، اسم الدولة بالعربي)
LIVE_COUNTRY_RULES = [
    (["TUNISIA"],            "🇹🇳", "تونس"),
    (["ALGERI"],             "🇩🇿", "الجزائر"),
    (["MAROC"],              "🇲🇦", "المغرب"),
    (["LEBANON"],            "🇱🇧", "لبنان"),
    (["EGYPT"],              "🇪🇬", "مصر"),
    (["ARABIC", "ARAB"],     "🇸🇦", "العربية"),
    (["FRANCE", "FR "],      "🇫🇷", "فرنسا"),
    (["BELGIQUE"],           "🇧🇪", "بلجيكا"),
    (["SUISSE"],             "🇨🇭", "سويسرا"),
    (["ITALIA", "ITALY"],    "🇮🇹", "إيطاليا"),
    (["GERMANY", "DEUTSCH"], "🇩🇪", "ألمانيا"),
    (["SPAIN"],              "🇪🇸", "إسبانيا"),
    (["PORTUGAL"],           "🇵🇹", "البرتغال"),
    (["POLAND"],             "🇵🇱", "بولندا"),
    (["SWEDEN"],             "🇸🇪", "السويد"),
    (["DENMARK"],            "🇩🇰", "الدنمارك"),
    (["NETHERLANDS"],        "🇳🇱", "هولندا"),
    (["UK "],                "🇬🇧", "بريطانيا"),
    (["USA", "CANADA"],      "🇺🇸", "أمريكا وكندا"),
    (["TURKISH"],            "🇹🇷", "تركيا"),
    (["MEXICO"],             "🇲🇽", "المكسيك"),
    (["LATINO"],             "🌎", "أمريكا اللاتينية"),
    (["ALBANIE"],            "🇦🇱", "ألبانيا"),
    (["EX-YU", "SERBIA"],    "🇷🇸", "صربيا ويوغوسلافيا"),
    (["CROATIE"],            "🇭🇷", "كرواتيا"),
    (["ROMANIA"],            "🇷🇴", "رومانيا"),
    (["GRÉCE", "GREECE"],    "🇬🇷", "اليونان"),
    (["RUSSIA"],             "🇷🇺", "روسيا"),
    (["ISRAËL", "ISRAEL"],   "🇮🇱", "إسرائيل"),
    (["KURD"],               "☀️", "كردستان"),
    (["AFRICAIN", "DSTV"],   "🌍", "أفريقيا"),
    (["IRAN"],               "🇮🇷", "إيران"),
    (["WORLD"],              "🌐", "عالمية"),
]


# 📡 فئات القنوات النوعية (لها أولوية على اسم الدولة)
LIVE_GENRE_RULES = [
    (["SPORT", "BEIN SPORT", "SSC", "DAZN", "LIGUE", "FOOT", "CANAL+ LIVE & SPORT"],
                                          "⚽", "رياضية"),
    (["KIDS", "CARTOON", "CHILD"],        "🧒", "أطفال"),
    (["NEWS", "INFO"],                    "📰", "إخبارية"),
    (["DOCUMENTAIRE", "DOCU", "NATURE", "DOC"], "📚", "وثائقية"),
    (["ISLAMIC", "ISLAM", "QURAN", "MUSLIM", "MOSQUE"], "🕌", "إسلامية"),
    (["ADULTE", "ADULT", "XXX"],          "🔞", "للكبار فقط"),
    (["MOVIE", "CINEMA", "VOD", "ENTERTAINMENT", "SERIE"], "🎬", "أفلام ومسلسلات"),
    (["MUSIC"],                           "🎵", "موسيقى"),
    (["ENTERTAINMENT", "VARIETY", "DIVERTISSEMENT", "منوعات"], "📺", "منوعات"),
    (["RELAX"],                           "🌿", "استرخاء"),
]


def _match(text_upper: str, rules) -> Tuple[str, str]:
    """يبحث عن أول قاعدة مطابقة ويرجع (إيموجي، اسم)."""
    for keywords, icon, label in rules:
        for kw in keywords:
            if kw in text_upper:
                return icon, label
    return "", ""


def pretty_category(raw: str, type_: str = "movie") -> str:
    """
    🎯 التصنيف النوعي الذكي:
    يحوّل اسم القسم الخام لفئة ثابتة أنيقة: نوع + لغة.
    'VOD FR HORROR'          → '👻 رعب فرنسية'
    'SUB AR ACTION'          → '💥 أكشن مترجمة عربي'
    'RAMADAN 2026 رمضان'      → '🌙 رمضانيات'
    'TUNISIA TV'             → '🇹🇳 تونس'
    """
    s = str(raw or "").strip()
    if not s:
        return "📁 عام"
    # عربي صِرف → نرجعه زي ما هو
    if re.search(r"[\u0600-\u06FF]", s) and not re.search(r"[A-Za-z]", s):
        return s
    upper = " " + re.sub(r"[^\w\s&/-]", " ", s.upper()) + " "

    if type_ == "live":
        # ⚡ الأولوية للنوع النوعي (رياضة/أطفال/أخبار/وثائقي/إسلامي/سينما) ثم الدولة
        icon, label = _match(upper, LIVE_GENRE_RULES)
        if label:
            return f"{icon} {label}"
        icon, label = _match(upper, LIVE_COUNTRY_RULES)
        if label:
            return f"{icon} {label}"
        gicon, glabel = _match(upper, GENRE_RULES)
        if glabel:
            return f"{gicon} {glabel}"
        return f"📡 {clean_name(s).title()[:26]}"

    # أفلام ومسلسلات: نوع + لغة
    gicon, glabel = _match(upper, GENRE_RULES)
    licon, llabel = _match(upper, LOCALE_RULES)
    # استثناء خاص: رمضانيات تتفوق على كل شيء
    if "RAMADAN" in upper or "رمضان" in s:
        return "🌙 رمضانيات"
    if glabel and llabel:
        return f"{gicon} {glabel} {llabel}"
    if glabel:
        return f"{gicon} {glabel}"
    if llabel:
        return f"{licon} {llabel}"
    return f"🎬 {clean_name(s).title()[:26]}"


def cat_group_key(cat_name: str, type_: str = "movie") -> str:
    """المفتاح الموحد للدمج — نفس النوع+اللغة = نفس الفئة (بيدمج المكرر تلقائياً)."""
    return pretty_category(cat_name, type_)


def group_categories(cats: List[Dict], type_: str = "movie") -> Dict[str, Dict]:
    """
    يدمج الأقسام المتشابهة تحت فئات ثابتة ويحسب الإجمالي:
    يرجع: {اسم_الفئة: {"ids": [ids...], "count": إجمالي, "icon": إيموجي}}
    """
    groups: Dict[str, Dict] = {}
    for c in cats:
        key = pretty_category(c.get("category_name"), type_)
        cnt = c.get("stream_count") or 0
        if key in groups:
            groups[key]["ids"].append(str(c.get("category_id")))
            groups[key]["count"] += cnt
        else:
            groups[key] = {"ids": [str(c.get("category_id"))], "count": cnt}
    # ترتيب تنازلي حسب العدد — الأكبر الأول
    return dict(sorted(groups.items(), key=lambda kv: -kv[1]["count"]))


def normalize_ar(text: str) -> str:
    """توحيد الحروف العربية للبحث الذكي (أ/إ/آ→ا، ة→ه، ى→ي)."""
    t = str(text or "").lower().strip()
    t = re.sub(r"[أإآ]", "ا", t)
    t = t.replace("ة", "ه").replace("ى", "ي")
    t = re.sub(r"[\u064B-\u0652]", "", t)  # تشكيل
    return t


# ══════════════ 🔗 روابط التشغيل المباشرة ══════════════
def direct_url(video_url: str) -> str:
    """رابط المصدر الأصلي كما هو؛ لا Worker ولا quote ولا توقيع."""
    return str(video_url or "").strip()


# ══════════════ عميل Xtream Codes API ══════════════
class Xtream:
    """عميل async لسيرفر Xtream مع تبديل تلقائي بين السيرفرات عند الفشل."""

    def __init__(self, bases: List[str], user: str, password: str):
        self.bases = bases
        self.user = user
        self.pw = password
        self.base_idx = 0
        self._client: Optional[httpx.AsyncClient] = None

    @property
    def base(self) -> str:
        return self.bases[self.base_idx]

    async def client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                timeout=httpx.Timeout(REQUEST_TIMEOUT, read=60),
                follow_redirects=True,
                headers={"User-Agent": "Mozilla/5.0 (YouseifFilms)"},
            )
        return self._client

    def _switch(self):
        if len(self.bases) > 1:
            old = self.base
            self.base_idx = (self.base_idx + 1) % len(self.bases)
            log.warning("🔁 تبديل السيرفر: %s → %s", old, self.base)

    async def api(self, action: str = "", **params):
        q = {"username": self.user, "password": self.pw}
        if action:
            q["action"] = action
        q.update({k: v for k, v in params.items() if v is not None})
        last_err = None
        for attempt in range(1, MAX_RETRIES + 1):
            try:
                c = await self.client()
                r = await c.get(f"{self.base}/player_api.php", params=q)
                if r.status_code == 200:
                    try:
                        return r.json()
                    except Exception:
                        return None
                last_err = f"HTTP {r.status_code}"
            except Exception as e:
                last_err = f"{type(e).__name__}: {e}"
                log.warning("⚠️ محاولة %d/%d فشلت (%s) — %s", attempt, MAX_RETRIES, self.base, last_err)
                self._switch()
                await asyncio.sleep(1.5 * attempt)
        log.error("❌ فشل نداء API (%s): %s", action or "login", last_err)
        return None

    # ── روابط المشاهدة الخام المباشرة ──
    def live_url(self, stream_id) -> str:
        return f"{self.base}/live/{self.user}/{self.pw}/{stream_id}.m3u8"

    def movie_url(self, stream_id, ext: str = "mp4") -> str:
        return f"{self.base}/movie/{self.user}/{self.pw}/{stream_id}.{ext or 'mp4'}"

    def movie_m3u8(self, stream_id) -> str:
        return f"{self.base}/movie/{self.user}/{self.pw}/{stream_id}.m3u8"

    def episode_url(self, episode_id, ext: str = "mp4") -> str:
        return f"{self.base}/series/{self.user}/{self.pw}/{episode_id}.{ext or 'mp4'}"

    def episode_m3u8(self, episode_id) -> str:
        return f"{self.base}/series/{self.user}/{self.pw}/{episode_id}.m3u8"

    async def close(self):
        if self._client and not self._client.is_closed:
            await self._client.aclose()


# ══════════════ 🎞️ TMDB API (بوسترات + قصة بالعربية) ══════════════
class TMDB:
    """يجلب بوستر وقصة وتقييم من TMDB. بدون مفتاح → يرجع بيانات السيرفر.
    محسّن: تنظيف أقوى + بحث ثنائي اللغة (ar ثم en) + fallback بدون سنة.
    """

    BASE = "https://api.themoviedb.org/3"
    IMG = "https://image.tmdb.org/t/p/w500"

    def __init__(self, api_key: str, read_access_token: str = ""):
        self.key = api_key
        self.read_access_token = read_access_token
        self._client: Optional[httpx.AsyncClient] = None
        self._cache: Dict[str, Dict] = {}

    @property
    def enabled(self) -> bool:
        return bool(self.key or self.read_access_token)

    async def client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            headers = {"Accept": "application/json"}
            if self.read_access_token:
                headers["Authorization"] = f"Bearer {self.read_access_token}"
            self._client = httpx.AsyncClient(timeout=httpx.Timeout(15), headers=headers)
        return self._client

    def _clean_title(self, raw: str) -> Tuple[str, Optional[int]]:
        """ينظف اسم العمل ويستخرج السنة لو موجودة — أقوى تنظيف للكرتون والمسلسلات."""
        s = clean_name(raw)
        year = None
        m = re.search(r"\((\d{4})\)", s)
        if m:
            year = int(m.group(1))
            s = re.sub(r"\(\d{4}\)", "", s).strip()
        # إزالة سنوات حرة وأرقام الحلقات/المواسم
        if not year:
            m2 = re.search(r"\b((19|20)\d{2})\b", s)
            if m2:
                year = int(m2.group(1))
                s = re.sub(r"\b(19|20)\d{2}\b", "", s).strip()
        s = re.sub(r"(?i)\b(S\d{1,2}|E\d{1,3}|SEASON\s*\d+|EPISODE\s*\d+|موسم\s*\d+|حلقة\s*\d+)\b", "", s)
        s = re.sub(r"\s{2,}", " ", s).strip(" -_.")
        return s, year

    async def _search_once(self, c, endpoint: str, title: str, year: Optional[int],
                           lang: str, adult: bool = False) -> Dict:
        params = {
            "query": title,
            "language": lang,
            "include_adult": "true" if adult else "false",
        }
        if self.key:
            params["api_key"] = self.key
        if year:
            params["year" if endpoint == "movie" else "first_air_date_year"] = year
        try:
            r = await c.get(f"{self.BASE}/search/{endpoint}", params=params)
            if r.status_code != 200:
                return {}
            results = (r.json() or {}).get("results") or []
            if not results:
                return {}
            # اختيار أفضل نتيجة: تطابق أقرب للاسم
            title_n = normalize_ar(title)
            best = results[0]
            best_score = 0
            for res in results[:8]:
                rname = normalize_ar(res.get("title") or res.get("name") or "")
                score = 0
                if rname == title_n:
                    score = 100
                elif title_n in rname or rname in title_n:
                    score = 70
                else:
                    # عدد الكلمات المشتركة
                    tw = set(title_n.split())
                    rw = set(rname.split())
                    if tw and rw:
                        score = int(40 * len(tw & rw) / max(len(tw), 1))
                if score > best_score:
                    best_score = score
                    best = res
            poster = best.get("poster_path")
            overview = (best.get("overview") or "").strip()
            return {
                "id": best.get("id"),
                "poster": f"{self.IMG}{poster}" if poster else "",
                "overview": overview[:450] if overview else "",
                "year": (best.get("release_date") or best.get("first_air_date") or "")[:4],
                "rating": round(float(best.get("vote_average") or 0), 1),
                "title": best.get("title") or best.get("name") or title,
                "original_title": best.get("original_title") or best.get("original_name") or title,
            }
        except Exception as e:
            log.warning("TMDB search_once failed (%s/%s): %s", endpoint, lang, e)
            return {}

    async def lookup(self, raw_title: str, kind: str) -> Dict:
        """
        kind: 'movie' أو 'series'
        يرجع: {poster, overview, year, rating, title} — قد تكون فارغة عند الفشل.
        يجرّب: عربي + سنة → إنجليزي + سنة → عربي بدون سنة → إنجليزي بدون سنة.
        """
        if not self.enabled:
            return {}
        title, year = self._clean_title(raw_title)
        if not title or len(title) < 2:
            return {}
        cache_key = f"{kind}:{normalize_ar(title)}:{year or ''}"
        if cache_key in self._cache:
            return self._cache[cache_key]
        out: Dict = {}
        endpoint = "movie" if kind == "movie" else "tv"
        adult = is_adult_name(raw_title)
        try:
            c = await self.client()
            # سلسلة محاولات مرتبة حسب الأولوية
            attempts = [
                (title, year, "ar"),
                (title, year, "en"),
            ]
            if year:
                attempts += [(title, None, "ar"), (title, None, "en")]
            # لو العنوان قصير جداً أو فشل، جرّب بدون كلمات شائعة
            short = re.sub(r"(?i)\b(the|a|an|le|la|les|el|al)\b", "", title).strip()
            if short and short != title:
                attempts.append((short, year, "en"))
            for q, y, lang in attempts:
                if not q:
                    continue
                out = await self._search_once(c, endpoint, q, y, lang, adult)
                if out.get("poster") or out.get("overview"):
                    break
            if out.get("id"):
                try:
                    r = await c.get(f"{self.BASE}/{endpoint}/{out['id']}", params={"language":"ar"})
                    if r.status_code == 200:
                        d = r.json() or {}
                        runtime = d.get("runtime") or ((d.get("episode_run_time") or [None])[0] if isinstance(d.get("episode_run_time"), list) else None)
                        if runtime:
                            out["runtime"] = runtime
                        if d.get("overview"):
                            out["overview"] = str(d["overview"])[:450]
                        out["original_title"] = d.get("original_title") or d.get("original_name") or out.get("original_title", "")
                except Exception as e:
                    log.debug("TMDB detail lookup failed: %s", e)
        except Exception as e:
            log.warning("TMDB lookup failed: %s", e)
        self._cache[cache_key] = out
        return out

    async def close(self):
        if self._client and not self._client.is_closed:
            await self._client.aclose()


# ══════════════ قاعدة البيانات (كاش + مفضلة + إحصائيات) ══════════════
class DB:
    def __init__(self, path: str = DB_PATH):
        self.path = path
        self._init()

    def _con(self):
        c = sqlite3.connect(self.path)
        c.row_factory = sqlite3.Row
        return c

    def _init(self):
        with self._con() as c:
            c.executescript("""
                CREATE TABLE IF NOT EXISTS users (
                    telegram_id INTEGER PRIMARY KEY,
                    username TEXT, first_name TEXT,
                    joined_at TEXT DEFAULT CURRENT_TIMESTAMP
                );
                CREATE TABLE IF NOT EXISTS favorites (
                    user_id INTEGER NOT NULL,
                    item_type TEXT NOT NULL,
                    item_id TEXT NOT NULL,
                    title TEXT NOT NULL,
                    poster TEXT DEFAULT '',
                    added_at TEXT DEFAULT CURRENT_TIMESTAMP,
                    PRIMARY KEY (user_id, item_type, item_id)
                );
                CREATE TABLE IF NOT EXISTS cache (
                    key TEXT PRIMARY KEY,
                    data TEXT NOT NULL,
                    ts INTEGER NOT NULL
                );
                CREATE TABLE IF NOT EXISTS aliases (
                    item_type TEXT NOT NULL,
                    item_id TEXT NOT NULL,
                    alias TEXT NOT NULL,
                    lang TEXT DEFAULT 'ar',
                    PRIMARY KEY (item_type, item_id, alias)
                );
                CREATE TABLE IF NOT EXISTS views (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER,
                    item_type TEXT,
                    item_id TEXT,
                    day TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS settings (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS adult_unlock (
                    user_id INTEGER PRIMARY KEY,
                    unlocked_at TEXT DEFAULT CURRENT_TIMESTAMP
                );
            """)

    # ── كاش ──
    def cache_get(self, key: str):
        with self._con() as c:
            row = c.execute("SELECT data, ts FROM cache WHERE key=?", (key,)).fetchone()
            if row and (time.time() - row["ts"]) < CACHE_DURATION:
                try:
                    return json.loads(row["data"])
                except Exception:
                    return None
            return None

    def cache_set(self, key: str, data):
        with self._con() as c:
            c.execute("INSERT OR REPLACE INTO cache (key, data, ts) VALUES (?,?,?)",
                      (key, json.dumps(data, ensure_ascii=False), int(time.time())))

    def cache_flush(self):
        with self._con() as c:
            c.execute("DELETE FROM cache")

    # ── مستخدمون ──
    def add_user(self, uid: int, username: str, first_name: str):
        with self._con() as c:
            c.execute("INSERT OR IGNORE INTO users (telegram_id, username, first_name) VALUES (?,?,?)",
                      (uid, username or "", first_name or ""))

    def users_count(self) -> int:
        with self._con() as c:
            return c.execute("SELECT COUNT(*) FROM users").fetchone()[0]

    def all_user_ids(self) -> List[int]:
        with self._con() as c:
            return [r[0] for r in c.execute("SELECT telegram_id FROM users").fetchall()]

    # ── إحصائيات المشاهدة ──
    def log_view(self, uid: int, item_type: str, item_id: str):
        day = time.strftime("%Y-%m-%d")
        with self._con() as c:
            c.execute("INSERT INTO views (user_id, item_type, item_id, day) VALUES (?,?,?,?)",
                      (uid, item_type, str(item_id), day))

    def views_today(self) -> int:
        day = time.strftime("%Y-%m-%d")
        with self._con() as c:
            return c.execute("SELECT COUNT(*) FROM views WHERE day=?", (day,)).fetchone()[0]

    def views_total(self) -> int:
        with self._con() as c:
            return c.execute("SELECT COUNT(*) FROM views").fetchone()[0]

    # ── مفضلة ──
    def toggle_fav(self, uid: int, item_type: str, item_id: str, title: str, poster: str = "") -> bool:
        """يرجع True لو اتضاف، False لو اتشال."""
        with self._con() as c:
            row = c.execute(
                "SELECT 1 FROM favorites WHERE user_id=? AND item_type=? AND item_id=?",
                (uid, item_type, str(item_id))).fetchone()
            if row:
                c.execute("DELETE FROM favorites WHERE user_id=? AND item_type=? AND item_id=?",
                          (uid, item_type, str(item_id)))
                return False
            c.execute("INSERT INTO favorites (user_id, item_type, item_id, title, poster) VALUES (?,?,?,?,?)",
                      (uid, item_type, str(item_id), title, poster or ""))
            return True

    def is_fav(self, uid: int, item_type: str, item_id: str) -> bool:
        with self._con() as c:
            return c.execute(
                "SELECT 1 FROM favorites WHERE user_id=? AND item_type=? AND item_id=?",
                (uid, item_type, str(item_id))).fetchone() is not None

    def get_favs(self, uid: int) -> List[Dict]:
        with self._con() as c:
            return [dict(r) for r in c.execute(
                "SELECT item_type, item_id, title, poster FROM favorites WHERE user_id=? ORDER BY added_at DESC",
                (uid,)).fetchall()]

    # ── أسماء مزدوجة (بحث عربي/إنجليزي) ──
    def set_alias(self, item_type: str, item_id: str, alias: str, lang: str = "ar"):
        """يحفظ اسماً بديلاً لعمل (مثلاً: ترولز ↔ Trolls) لرفع دقة البحث."""
        a = normalize_ar(alias)
        if not a:
            return
        with self._con() as c:
            c.execute(
                "INSERT OR IGNORE INTO aliases (item_type, item_id, alias, lang) VALUES (?,?,?,?)",
                (item_type, str(item_id), a, lang))

    def find_by_alias(self, query: str) -> List[Tuple[str, str]]:
        """يبحث في الأسماء البديلة — يرجع [(item_type, item_id), ...]."""
        q = normalize_ar(query)
        if not q:
            return []
        with self._con() as c:
            return [(r["item_type"], r["item_id"]) for r in c.execute(
                "SELECT item_type, item_id FROM aliases WHERE alias LIKE ? LIMIT 40",
                (f"%{q}%",)).fetchall()]

    # ── إعدادات عامة (باسورد الكبار وغيرها) ──
    def get_setting(self, key: str, default: str = "") -> str:
        with self._con() as c:
            row = c.execute("SELECT value FROM settings WHERE key=?", (key,)).fetchone()
            return row["value"] if row else default

    def set_setting(self, key: str, value: str):
        with self._con() as c:
            c.execute("INSERT OR REPLACE INTO settings (key, value) VALUES (?,?)", (key, value))

    def get_or_create_adult_password(self) -> str:
        """يُنشئ باسورد عشوائي للكبار تلقائياً إن لم يكن موجوداً — للأدمن فقط."""
        pw = self.get_setting("adult_password")
        if pw:
            return pw
        # توليد تلقائي: 6 أرقام
        pw = f"{random.randint(100000, 999999)}"
        self.set_setting("adult_password", pw)
        log.info("🔐 تم توليد باسورد محتوى الكبار تلقائياً")
        return pw

    def regenerate_adult_password(self) -> str:
        pw = f"{random.randint(100000, 999999)}"
        self.set_setting("adult_password", pw)
        # إلغاء فتح الجميع عند التجديد
        with self._con() as c:
            c.execute("DELETE FROM adult_unlock")
        return pw

    def is_adult_unlocked(self, uid: int) -> bool:
        with self._con() as c:
            return bool(c.execute("SELECT 1 FROM adult_unlock WHERE user_id=?", (uid,)).fetchone())

    def unlock_adult(self, uid: int):
        with self._con() as c:
            c.execute("INSERT OR REPLACE INTO adult_unlock (user_id, unlocked_at) VALUES (?, datetime('now'))",
                      (uid,))


# ══════════════ طبقة البيانات (API + كاش) ══════════════
class Store:
    def __init__(self, xt: Xtream, db: DB):
        self.xt = xt
        self.db = db

    async def _cached(self, key: str, action: str, **params):
        hit = self.db.cache_get(key)
        if hit is not None:
            return hit
        data = await self.xt.api(action, **params)
        if data is None:
            data = []
        self.db.cache_set(key, data)
        return data

    async def categories(self, type_: str) -> List[Dict]:
        action = {"live": "get_live_categories", "movie": "get_vod_categories",
                  "series": "get_series_categories"}[type_]
        data = await self._cached(f"cats:{type_}", action)
        return data if isinstance(data, list) else []

    async def streams(self, type_: str, cat_id=None) -> List[Dict]:
        action = {"live": "get_live_streams", "movie": "get_vod_streams",
                  "series": "get_series"}[type_]
        key = f"streams:{type_}:{cat_id or 'all'}"
        params = {} if cat_id in (None, "", "all") else {"category_id": cat_id}
        data = await self._cached(key, action, **params)
        return data if isinstance(data, list) else []

    async def series_info(self, series_id) -> Dict:
        data = await self._cached(f"sinfo:{series_id}", "get_series_info", series_id=series_id)
        return data if isinstance(data, dict) else {}

    async def all_items(self, type_: str) -> List[Dict]:
        return await self.streams(type_, None)

    async def search(self, query: str) -> List[Tuple[str, Dict]]:
        """بحث ذكي محسّن: توحيد عربي + كلمات منفصلة + ترتيب حسب قوة المطابقة + aliases.
        يجلب نتائج أكثر (حتى 150) ويفهم الاستعلامات الجزئية والمتعددة الكلمات.
        """
        raw_q = str(query or "").strip()
        q = normalize_ar(raw_q)
        SEARCH_SYNONYMS = {
            "سبورت":"sport", "رياضه":"sport", "رياضة":"sport", "اكشن":"action",
            "رعب":"horror", "كرتون":"cartoon", "انمي":"anime", "افلام":"movie",
            "مسلسلات":"series", "قنوات":"channel", "اطفال":"kids", "اطفال":"kids",
            "منوعات":"entertainment", "وثائقي":"documentary", "اسلامي":"islamic",
        }
        q_alt = normalize_ar(SEARCH_SYNONYMS.get(q, q))
        if not q or len(q) < 1:
            return []
        # كلمات البحث (تجاهل كلمات قصيرة جداً إلا لو الاستعلام كله قصير)
        tokens = [t for t in q.split() if len(t) >= 1] or ([q] if q else [])
        if not tokens:
            return []

        # أولاً: مطابقة بالاسم البديل
        alias_hits = self.db.find_by_alias(raw_q)
        alias_ids = {(t, str(i)) for t, i in alias_hits}

        scored: List[Tuple[int, str, Dict]] = []  # (score, type, item)
        seen: set = set()

        for type_ in ("movie", "series", "live"):
            try:
                items = await self.all_items(type_)
            except Exception:
                items = []
            id_key = "series_id" if type_ == "series" else "stream_id"
            for it in items:
                if is_adult_name(it.get("name") or it.get("title") or ""):
                    continue
                if type_ == "live" and is_non_islamic_religious(it.get("name") or ""):
                    continue
                iid = it.get(id_key)
                if iid is None:
                    continue
                key = (type_, str(iid))
                if key in seen:
                    continue
                name_raw = it.get("name") or it.get("title") or ""
                name = normalize_ar(name_raw)
                name_clean = normalize_ar(clean_name(name_raw))
                haystack = " ".join([name, name_clean, normalize_ar(str(it.get("category_name") or "")), normalize_ar(str(it.get("stream_type") or ""))])

                score = 0
                # مطابقة alias محفوظ
                if key in alias_ids:
                    score = max(score, 90)
                # الكلمات البديلة الثنائية اللغة
                if q_alt != q and q_alt in haystack:
                    score = max(score, 78)
                # تطابق كامل
                if q == name or q == name_clean or q_alt == name or q_alt == name_clean:
                    score = max(score, 100)
                elif name.startswith(q) or name_clean.startswith(q) or q_alt in haystack:
                    score = max(score, 85)
                elif q in haystack or q_alt in haystack:
                    score = max(score, 70)
                else:
                    # مطابقة كل الكلمات (AND) أو معظمها
                    matched = sum(1 for t in tokens if t in haystack)
                    fuzzy = difflib.SequenceMatcher(None, q_alt, name).ratio() if q_alt else 0
                    if fuzzy >= 0.55:
                        score = max(score, int(fuzzy * 65))
                    if matched == len(tokens) and tokens:
                        score = max(score, 60 + min(20, matched * 5))
                    elif matched >= max(1, len(tokens) - 1) and matched > 0:
                        score = max(score, 40 + matched * 8)
                    elif matched > 0:
                        score = max(score, 25 + matched * 5)

                if score > 0:
                    seen.add(key)
                    scored.append((score, type_, it))

        # ترتيب تنازلي حسب القوة ثم الاسم
        scored.sort(key=lambda x: (-x[0], normalize_ar(x[2].get("name") or "")))
        # حد أعلى 150 نتيجة ليعطي نتائج أكثر
        return [(t, it) for _, t, it in scored[:150]]


# ══════════════ 🎛️ لوحات المفاتيح (شبكة 2 و3 أعمدة) ══════════════
TYPE_LABEL = {"live": "📡 القنوات المباشرة", "movie": "🎬 الأفلام", "series": "📺 المسلسلات"}
ITEM_ICON = {"live": "📡", "movie": "🎞️", "series": "📺"}


# أزرار محتوى سريعة — تظهر في /start وتفتح الفئة على طول (كلمة مفتاحية → بحث في الفئات)
QUICK_BUTTONS = [
    ("💪 مصارعة ورياضة", "رياضة ومصارعة"),
    ("🧸 كرتون وأنيميشن", "أنيميشن"),
    ("🌙 رمضانيات", "رمضانيات"),
    ("👻 رعب", "رعب"),
    ("😂 كوميدي", "كوميدي"),
    ("🍿 منصات عالمية", "منصات عالمية"),
]


def main_reply_kb(uid: int = 0) -> ReplyKeyboardMarkup:
    rows = [["❤️ المفضلة", "🔍 بحث"], ["🎲 عشوائي", "❓ مساعدة"]]
    if is_admin(uid):
        rows.append(["👑 لوحة الأدمن"])
    return ReplyKeyboardMarkup(rows, resize_keyboard=True, is_persistent=True, one_time_keyboard=False)


def main_menu_kb(uid: int = 0) -> InlineKeyboardMarkup:
    """قائمة رئيسية مرتبة باحترافية — أعمدة متناسقة + إخفاء الأدمن لغير المصرح."""
    rows = [
        # صف 1: المحتوى الرئيسي
        [InlineKeyboardButton("🎬 الأفلام", callback_data="t:movie"),
         InlineKeyboardButton("📺 المسلسلات", callback_data="t:series")],
        # صف 2: البث
        [InlineKeyboardButton("📡 القنوات المباشرة", callback_data="t:live")],
        # صف 3: اختصارات محتوى
        [InlineKeyboardButton("💪 مصارعة", callback_data="qk:رياضة ومصارعة"),
         InlineKeyboardButton("🧸 كرتون", callback_data="qk:أنيميشن")],
        [InlineKeyboardButton("🌙 رمضانيات", callback_data="qk:رمضانيات"),
         InlineKeyboardButton("👻 رعب", callback_data="qk:رعب")],
        # صف 4: أدوات المستخدم
        [InlineKeyboardButton("🔍 بحث", callback_data="act:search"),
         InlineKeyboardButton("❤️ المفضلة", callback_data="act:fav")],
        [InlineKeyboardButton("🎲 عشوائي", callback_data="act:random"),
         InlineKeyboardButton("❓ مساعدة", callback_data="act:help")],
    ]
    if is_admin(uid):
        rows.append([InlineKeyboardButton("👑 لوحة الأدمن", callback_data="act:admin")])
    return InlineKeyboardMarkup(rows)


def back_main_row() -> List[InlineKeyboardButton]:
    return [InlineKeyboardButton("🏠 القائمة الرئيسية", callback_data="main")]


def grid(btns: List[InlineKeyboardButton], cols: int = 2) -> List[List[InlineKeyboardButton]]:
    """شبكة أزرار: الأقسام والعناصر عمودين (row_width=2)."""
    return [btns[i:i + cols] for i in range(0, len(btns), cols)]


def nav_row(type_: str, cat_id: str, page: int, pages: int) -> List[InlineKeyboardButton]:
    """شريط التنقل: السابق / رقم الصفحة / التالي — 3 أزرار في سطر (row_width=3)."""
    row = []
    if page > 0:
        row.append(InlineKeyboardButton("◀️ السابق", callback_data=f"c:{type_}:{cat_id}:{page - 1}"))
    else:
        row.append(InlineKeyboardButton("·", callback_data="noop"))
    row.append(InlineKeyboardButton(f"📄 {page + 1}/{pages}", callback_data="noop"))
    if page < pages - 1:
        row.append(InlineKeyboardButton("التالي ▶️", callback_data=f"c:{type_}:{cat_id}:{page + 1}"))
    else:
        row.append(InlineKeyboardButton("·", callback_data="noop"))
    return row


def categories_kb(cats: List[Dict], type_: str) -> InlineKeyboardMarkup:
    """الأقسام شبكة عمودين مع أسماء عربية أنيقة."""
    btns = []
    for cat in cats:
        cid = cat.get("category_id")
        name = pretty_category(cat.get("category_name"), type_)
        cnt = cat.get("stream_count")
        label = f"{name} ({cnt})" if cnt else name
        btns.append(InlineKeyboardButton(label[:30], callback_data=f"c:{type_}:{cid}:0"))
    rows = grid(btns, 2)
    rows.append(back_main_row())
    return InlineKeyboardMarkup(rows)


def groups_kb(groups: Dict[str, Dict], type_: str, page: int = 0) -> InlineKeyboardMarkup:
    """لوحة الفئات المدمجة — شبكة عمودين + تقسيم لصفحات (14 فئة/صفحة) مع أرقام صفحات تحت."""
    entries = list(groups.items())
    per = 14
    total = len(entries)
    pages = max(1, (total + per - 1) // per)
    page = max(0, min(page, pages - 1))
    chunk = entries[page * per:(page + 1) * per]
    btns = []
    for i, (gname, gdata) in enumerate(chunk):
        gidx = page * per + i
        btns.append(InlineKeyboardButton(f"{gname} ({gdata['count']:,})"[:34],
                                         callback_data=f"g:{type_}:{gidx}"))
    rows = grid(btns, 2)
    if pages > 1:
        nav = []
        nav.append(InlineKeyboardButton("◀️ السابق", callback_data=f"gp:{type_}:{page - 1}") if page > 0
                   else InlineKeyboardButton("·", callback_data="noop"))
        nav.append(InlineKeyboardButton(f"📄 {page + 1}/{pages}", callback_data="noop"))
        nav.append(InlineKeyboardButton("التالي ▶️", callback_data=f"gp:{type_}:{page + 1}") if page < pages - 1
                   else InlineKeyboardButton("·", callback_data="noop"))
        rows.append(nav)
    rows.append(back_main_row())
    return InlineKeyboardMarkup(rows)


async def get_groups(store, type_: str) -> Dict[str, Dict]:
    """يبني الفئات المدمجة من كاش SQLite الدائم — تشتغل حتى بعد إعادة تشغيل البوت."""
    cats = await store.categories(type_)
    return group_categories(cats, type_)


HIER_CACHE: Dict[str, List[Dict]] = {}

def _genre_label(raw: str, type_: str) -> Tuple[str, str]:
    upper = " " + re.sub(r"[^\w\s&/-]", " ", str(raw or "").upper()) + " "
    icon, label = _match(upper, LIVE_GENRE_RULES if type_ == "live" else GENRE_RULES)
    if label:
        return icon, label
    return "📁", "عام"

def _locale_label(raw: str) -> Tuple[str, str]:
    upper = " " + re.sub(r"[^\w\s&/-]", " ", str(raw or "").upper()) + " "
    icon, label = _match(upper, LOCALE_RULES)
    return (icon, label) if label else ("🌐", "متنوعة")

async def build_content_hierarchy(store, type_: str) -> List[Dict]:
    cats = await store.categories(type_)
    if type_ == "live":
        groups = {}
        for c in cats:
            raw = str(c.get("category_name") or "").strip()
            if is_non_islamic_religious(raw):
                continue
            icon, genre = _genre_label(raw, "live")
            if genre == "للكبار فقط":
                continue
            u = raw.upper()
            if genre == "أطفال":
                if any(k in u for k in ("MUSIC", "SONG", "أغاني", "اغاني")):
                    genre, icon = "أغاني الأطفال", "🎵"
                elif any(k in u for k in ("CARTOON", "ANIME", "ANIMATION")):
                    genre, icon = "كرتون وأنيميشن", "🧸"
            g = groups.setdefault(genre, {"icon": icon, "packages": {}})
            package = clean_name(raw) or "باقة عامة"
            p = g["packages"].setdefault(package, {"ids": [], "count": 0})
            cid = str(c.get("category_id"))
            if cid not in p["ids"]: p["ids"].append(cid)
            p["count"] += int(c.get("stream_count") or 0)
        return [{"key": k, "icon": v["icon"], "packages": dict(sorted(v["packages"].items(), key=lambda x: -x[1]["count"]))} for k,v in sorted(groups.items(), key=lambda x: -sum(y["count"] for y in x[1]["packages"].values()))]
    groups = {}
    for c in cats:
        raw = str(c.get("category_name") or "").strip()
        if is_adult_name(raw): continue
        gi, genre = _genre_label(raw, type_)
        li, locale = _locale_label(raw)
        if genre == "عام":
            genre, gi = (clean_name(raw)[:28] or "عام"), "📁"
        g = groups.setdefault(genre, {"icon": gi, "countries": {}})
        country = f"{li} {locale}"
        d = g["countries"].setdefault(country, {"ids": [], "count": 0})
        cid = str(c.get("category_id"))
        if cid not in d["ids"]: d["ids"].append(cid)
        d["count"] += int(c.get("stream_count") or 0)
    return [{"key": k, "icon": v["icon"], "countries": dict(sorted(v["countries"].items(), key=lambda x: -x[1]["count"]))} for k,v in sorted(groups.items(), key=lambda x: -sum(y["count"] for y in x[1]["countries"].values()))]


def _page_slice(items: List, page: int) -> Tuple[List, int, int]:
    total = len(items)
    pages = max(1, (total + ITEMS_PER_PAGE - 1) // ITEMS_PER_PAGE)
    page = max(0, min(page, pages - 1))
    return items[page * ITEMS_PER_PAGE:(page + 1) * ITEMS_PER_PAGE], page, pages


def items_kb(items: List[Dict], type_: str, cat_id: str, page: int) -> InlineKeyboardMarkup:
    """العناصر شبكة عمودين + شريط تنقل 3 أزرار."""
    slice_, page, pages = _page_slice(items, page)
    id_key = "series_id" if type_ == "series" else "stream_id"
    btns = []
    for it in slice_:
        iid = it.get(id_key)
        name = clean_name(it.get("name") or it.get("title"))
        btns.append(InlineKeyboardButton(f"{ITEM_ICON[type_]} {name[:26]}",
                                         callback_data=f"i:{type_}:{iid}:{cat_id}:{page}"))
    rows = grid(btns, 2)
    if pages > 1:
        if cat_id.startswith("h:"):
            _, gi, ci = cat_id.split(":")
            nav=[]
            if page>0: nav.append(InlineKeyboardButton("◀️ السابق",callback_data=f"hi:{type_}:{gi}:{ci}:{page-1}"))
            nav.append(InlineKeyboardButton(f"📄 {page+1}/{pages}",callback_data="noop"))
            if page<pages-1: nav.append(InlineKeyboardButton("التالي ▶️",callback_data=f"hi:{type_}:{gi}:{ci}:{page+1}"))
            rows.append(nav)
        elif cat_id.startswith("lp:"):
            _,gi,pi=cat_id.split(":")
            nav=[]
            if page>0: nav.append(InlineKeyboardButton("◀️ السابق",callback_data=f"li:{gi}:{pi}:{page-1}"))
            nav.append(InlineKeyboardButton(f"📄 {page+1}/{pages}",callback_data="noop"))
            if page<pages-1: nav.append(InlineKeyboardButton("التالي ▶️",callback_data=f"li:{gi}:{pi}:{page+1}"))
            rows.append(nav)
        else:
            rows.append(nav_row(type_, cat_id, page, pages))
    if cat_id.startswith("h:"):
        _,gi,ci=cat_id.split(":")
        rows.append([InlineKeyboardButton("🔙 الدول",callback_data=f"hg:{type_}:{gi}")])
    elif cat_id.startswith("lp:"):
        _,gi,pi=cat_id.split(":")
        rows.append([InlineKeyboardButton("🔙 الباقات",callback_data=f"lt:{gi}")])
    else:
        rows.append([InlineKeyboardButton(f"🔙 {TYPE_LABEL[type_]}", callback_data=f"t:{type_}")])
    rows.append(back_main_row())
    return InlineKeyboardMarkup(rows)


def item_detail_kb(uid: int, db: DB, type_: str, item: Dict, cat_id: str, page: int, xt: Xtream,
                   title: str = "", poster: str = "") -> InlineKeyboardMarkup:
    """أزرار كارت العمل: مشاهدة وبث عبر المصدر المباشر + مفضلة + رجوع — متناسقة."""
    rows = []
    id_key = "series_id" if type_ == "series" else "stream_id"
    iid = item.get(id_key)
    if type_ == "live":
        # زر مشاهدة (عبر المصدر المباشر) + زر بث (رابط m3u8 مباشر مباشرةً)
        rows.append([
            InlineKeyboardButton("▶️ مشاهدة", url=direct_url(xt.live_url(iid))),
            InlineKeyboardButton("📡 بث مباشر", url=direct_url(xt.live_url(iid))),
        ])
    elif type_ == "movie":
        ext = item.get("container_extension") or "mp4"
        rows.append([
            InlineKeyboardButton("▶️ مشاهدة", url=direct_url(xt.movie_url(iid, item.get("container_extension") or "mp4"))),
            InlineKeyboardButton(f"⬇️ تحميل ({ext})", url=direct_url(xt.movie_url(iid, ext))),
        ])
    elif type_ == "series":
        rows.append([InlineKeyboardButton("📀 المواسم والحلقات", callback_data=f"s:{iid}:0")])
        rows.append([InlineKeyboardButton("⚡ مشاهدة أول حلقة", callback_data=f"w:{iid}")])
    fav = db.is_fav(uid, type_, str(iid))
    rows.append([InlineKeyboardButton(
        "💔 إزالة من المفضلة" if fav else "❤️ إضافة للمفضلة",
        callback_data=f"f:{type_}:{iid}:{cat_id}:{page}",
    )])
    if cat_id == "fav":
        rows.append([InlineKeyboardButton("🔙 رجوع للمفضلة", callback_data="act:fav")])
    elif cat_id.startswith("h:"):
        _,gi,ci=cat_id.split(":")
        rows.append([InlineKeyboardButton("🔙 الدول", callback_data=f"hg:{type_}:{gi}")])
    elif cat_id.startswith("lp:"):
        _,gi,pi=cat_id.split(":")
        rows.append([InlineKeyboardButton("🔙 الباقات", callback_data=f"lt:{gi}")])
    elif cat_id not in ("all", ""):
        rows.append([InlineKeyboardButton("🔙 رجوع للقائمة", callback_data=f"c:{type_}:{cat_id}:{page}")])
    rows.append(back_main_row())
    return InlineKeyboardMarkup(rows)


def seasons_kb(info: Dict, series_id) -> InlineKeyboardMarkup:
    btns = []
    seasons = info.get("seasons") or []
    episodes_map = info.get("episodes") or {}
    for s in seasons:
        snum = s.get("season_number")
        cnt = s.get("episode_count")
        if cnt is None:
            cnt = len(episodes_map.get(str(snum), []))
        btns.append(InlineKeyboardButton(f"📀 موسم {snum} ({cnt} ح)",
                                         callback_data=f"e:{series_id}:{snum}:0"))
    rows = grid(btns, 2)
    rows.append(back_main_row())
    return InlineKeyboardMarkup(rows)


def episodes_kb(info: Dict, series_id, season: int, page: int) -> InlineKeyboardMarkup:
    eps = (info.get("episodes") or {}).get(str(season), [])
    slice_, page, pages = _page_slice(eps, page)
    btns = []
    for ep in slice_:
        num = ep.get("episode_num", "?")
        eid = ep.get("id")
        btns.append(InlineKeyboardButton(f"🎞️ حلقة {num}",
                                         callback_data=f"p:{eid}:{series_id}:{season}:{page}"))
    rows = grid(btns, 3)
    if pages > 1:
        nav = []
        nav.append(InlineKeyboardButton("◀️ السابق", callback_data=f"e:{series_id}:{season}:{page - 1}") if page > 0
                   else InlineKeyboardButton("·", callback_data="noop"))
        nav.append(InlineKeyboardButton(f"📄 {page + 1}/{pages}", callback_data="noop"))
        nav.append(InlineKeyboardButton("التالي ▶️", callback_data=f"e:{series_id}:{season}:{page + 1}") if page < pages - 1
                   else InlineKeyboardButton("·", callback_data="noop"))
        rows.append(nav)
    rows.append([InlineKeyboardButton("🔙 المواسم", callback_data=f"s:{series_id}:0")])
    rows.append(back_main_row())
    return InlineKeyboardMarkup(rows)


def episode_play_kb(ep: Dict, series_id, season: int, page: int, xt: Xtream,
                    series_title: str = "") -> InlineKeyboardMarkup:
    """زر مشاهدة الحلقة عبر رابط المصدر المباشر."""
    eid = ep.get("id")
    num = ep.get("episode_num", "?")
    title = f"{series_title} — حلقة {num}" if series_title else f"حلقة {num}"
    rows = [[InlineKeyboardButton("▶️ مشاهدة الحلقة 🎬",
                                  url=direct_url(xt.episode_url(eid, ep.get("container_extension") or "mp4")))]]
    rows.append([InlineKeyboardButton("🔙 الحلقات", callback_data=f"e:{series_id}:{season}:{page}")])
    rows.append(back_main_row())
    return InlineKeyboardMarkup(rows)


def admin_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📊 الإحصائيات", callback_data="adm:stats"),
         InlineKeyboardButton("🔄 تحديث الكاش", callback_data="adm:flush")],
        [InlineKeyboardButton("🔐 باسورد الكبار", callback_data="adm:adultpass"),
         InlineKeyboardButton("🔄 تجديد الباسورد", callback_data="adm:regenpass")],
        [InlineKeyboardButton("📢 رسالة جماعية", callback_data="adm:cast")],
        back_main_row(),
    ])


# ══════════════ 🤖 البوت الرئيسي ══════════════
class CinemaBot:
    def __init__(self):
        self.db = DB()
        self.xt = Xtream(BASES, IPTV_USERNAME, IPTV_PASSWORD)
        self.store = Store(self.xt, self.db)
        self.tmdb = TMDB(TMDB_API_KEY, TMDB_READ_TOKEN)

    # ---------- أدوات إرسال آمنة ----------
    async def _safe_edit(self, q, text: str, kb=None):
        try:
            await q.edit_message_text(text, parse_mode=ParseMode.HTML,
                                      reply_markup=kb, disable_web_page_preview=True)
        except Exception as e:
            if "not modified" not in str(e).lower():
                try:
                    await q.message.reply_text(text, parse_mode=ParseMode.HTML,
                                               reply_markup=kb, disable_web_page_preview=True)
                except Exception:
                    pass

    # ---------- /start ----------
    async def cmd_start(self, update: Update, ctx: ContextTypes.DEFAULT_TYPE):
        u = update.effective_user
        self.db.add_user(u.id, u.username, u.first_name)
        # توليد باسورد الكبار تلقائياً عند أول تشغيل (يظهر للأدمن فقط)
        if is_admin(u.id):
            self.db.get_or_create_adult_password()
        await update.message.reply_text(
            "✨🎬 <b>𝑌𝑜𝑢𝑠𝑒𝑖𝑓 𝐹𝑖𝑙𝑚𝑠</b> 🎬✨\n"
            "━━━━━━━━━━━━━━━\n"
            f"👋 أهلاً <b>{esc(u.first_name or 'بك')}</b>\n"
            "🍿 <i>أفلام • مسلسلات • قنوات مباشرة — بجودة عالمية</i>\n"
            "━━━━━━━━━━━━━━━\n"
            "👇 <b>اختر من القائمة:</b>",
            parse_mode=ParseMode.HTML,
            reply_markup=main_menu_kb(u.id),
        )
        await update.message.reply_text("👇 اللوحة السفلية ثابتة للتنقل السريع", reply_markup=main_reply_kb(u.id))

    async def cmd_help(self, update: Update, ctx: ContextTypes.DEFAULT_TYPE):
        await update.message.reply_text(
            "📖 <b>طريقة الاستخدام:</b>\n"
            "━━━━━━━━━━━━━━━\n"
            "• 🎬 الأفلام / 📺 المسلسلات / 📡 القنوات — تصفح بالأقسام\n"
            "• 🔍 بحث — ابعت اسم العمل (عربي أو إنجليزي)\n"
            "• 🔗 ابعت أي رابط فيديو مباشر → يتحول لزر مشاهدة فوراً\n"
            "• 🎲 عشوائي — اقتراح مفاجئ\n"
            "• ❤️ المفضلة — قائمتك الخاصة\n\n"
            "👑 أوامر الأدمن: /stats /broadcast",
            parse_mode=ParseMode.HTML,
            reply_markup=main_reply_kb(update.effective_user.id),
        )

    async def cmd_stats(self, update: Update, ctx: ContextTypes.DEFAULT_TYPE):
        if not is_admin(update.effective_user.id):
            return
        await self._stats_text(update.message)

    async def _stats_text(self, msg):
        lines = ["📊 <b>إحصائيات البوت</b>", "━━━━━━━━━━━━━━━"]
        lines.append(f"👥 المستخدمون: <b>{self.db.users_count()}</b>")
        lines.append(f"👁 مشاهدات اليوم: <b>{self.db.views_today()}</b>")
        lines.append(f"📈 إجمالي المشاهدات: <b>{self.db.views_total()}</b>")
        for t in ("live", "movie", "series"):
            cats = await self.store.categories(t)
            lines.append(f"{TYPE_LABEL[t]}: {len(cats)} قسم")
        lines.append(f"\n🌐 السيرفر: <code>{esc(self.xt.base)}</code>")
        lines.append(f"🔗 التشغيل: رابط المصدر المباشر بدون وسيط")
        lines.append(f"🎞️ TMDB: {'✅ مفعّل' if self.tmdb.enabled else '⚠️ بدون مفتاح'}")
        await msg.reply_text("\n".join(lines), parse_mode=ParseMode.HTML)

    async def cmd_broadcast(self, update: Update, ctx: ContextTypes.DEFAULT_TYPE):
        if not is_admin(update.effective_user.id):
            return
        text = " ".join(ctx.args) if ctx.args else ""
        if not text:
            await update.message.reply_text("استخدم: /broadcast نص الرسالة")
            return
        ok = fail = 0
        for uid in self.db.all_user_ids():
            try:
                await ctx.bot.send_message(uid, f"📢 {esc(text)}", parse_mode=ParseMode.HTML)
                ok += 1
            except RetryAfter as e:
                await asyncio.sleep(e.retry_after + 1)
            except Exception:
                fail += 1
            await asyncio.sleep(0.05)
        await update.message.reply_text(f"✅ تم الإرسال: {ok} | ❌ فشل: {fail}")

    # ---------- عرض الأقسام والعناصر ----------
    async def _show_categories(self, q, type_: str):
        await self._safe_edit(q, f"⏳ جاري تحميل تصنيفات {TYPE_LABEL[type_]}...")
        hierarchy = await build_content_hierarchy(self.store, type_)
        HIER_CACHE[type_] = hierarchy
        if not hierarchy:
            await self._safe_edit(q, f"❌ لا توجد تصنيفات متاحة في {TYPE_LABEL[type_]} حالياً.", InlineKeyboardMarkup([back_main_row()]))
            return
        if type_ == "live":
            rows = grid([InlineKeyboardButton(f"{g['icon']} {g['key']}", callback_data=f"lt:{i}") for i,g in enumerate(hierarchy)], 2)
            text = "📡✨ <b>القنوات المباشرة</b> ✨\n━━━━━━━━━━━━━━━\n🎯 اختر النوع الرئيسي:"
        else:
            rows = grid([InlineKeyboardButton(f"{g['icon']} {g['key']}", callback_data=f"hg:{type_}:{i}") for i,g in enumerate(hierarchy)], 2)
            text = f"{TYPE_LABEL[type_]}✨ <b>التصنيفات والأنواع</b> ✨\n━━━━━━━━━━━━━━━\n🎯 اختر النوع أولاً، ثم الدولة:"
        rows.append(back_main_row()); await self._safe_edit(q, text, InlineKeyboardMarkup(rows))

    async def _show_genre_countries(self, q, type_: str, idx: int):
        hierarchy=HIER_CACHE.get(type_) or await build_content_hierarchy(self.store,type_); HIER_CACHE[type_]=hierarchy
        if idx<0 or idx>=len(hierarchy): return await self._show_categories(q,type_)
        g=hierarchy[idx]; entries=list(g["countries"].items())
        rows=grid([InlineKeyboardButton(f"{n} ({d['count']:,})",callback_data=f"hc:{type_}:{idx}:{j}") for j,(n,d) in enumerate(entries)],2)
        rows.append([InlineKeyboardButton("🔙 التصنيفات الرئيسية",callback_data=f"t:{type_}")]); rows.append(back_main_row())
        await self._safe_edit(q,f"{g['icon']}✨ <b>{esc(g['key'])}</b> ✨\n━━━━━━━━━━━━━━━\n🌍 الدول المتاحة لهذا التصنيف:",InlineKeyboardMarkup(rows))

    async def _show_genre_items(self,q,type_:str,gidx:int,cidx:int,page:int=0):
        hierarchy=HIER_CACHE.get(type_) or await build_content_hierarchy(self.store,type_); HIER_CACHE[type_]=hierarchy
        if gidx<0 or gidx>=len(hierarchy): return await self._show_categories(q,type_)
        g=hierarchy[gidx]; entries=list(g["countries"].items())
        if cidx<0 or cidx>=len(entries): return await self._show_genre_countries(q,type_,gidx)
        cname,d=entries[cidx]; items=[]; seen=set(); id_key="series_id" if type_=="series" else "stream_id"
        for rid in d["ids"]:
            for it in await self.store.streams(type_,rid):
                iid=it.get(id_key)
                if iid is not None and iid not in seen and not is_adult_name(it.get("name") or ""):
                    seen.add(iid); items.append(it)
        if not items:
            await self._safe_edit(q,"❌ لا توجد عناصر متاحة هنا حالياً.",InlineKeyboardMarkup([[InlineKeyboardButton("🔙 التصنيف",callback_data=f"hg:{type_}:{gidx}")],back_main_row()])); return
        await self._safe_edit(q,f"{g['icon']} <b>{esc(g['key'])}</b> • {esc(cname)}\n━━━━━━━━━━━━━━━\n📦 <b>{len(items):,} عنصر</b>",items_kb(items,type_,f"h:{gidx}:{cidx}",page))

    async def _show_live_packages(self,q,idx:int):
        hierarchy=HIER_CACHE.get("live") or await build_content_hierarchy(self.store,"live"); HIER_CACHE["live"]=hierarchy
        if idx<0 or idx>=len(hierarchy): return await self._show_categories(q,"live")
        g=hierarchy[idx]; entries=list(g["packages"].items())
        rows=grid([InlineKeyboardButton(f"📦 {n} ({d['count']:,})",callback_data=f"lp:{idx}:{j}") for j,(n,d) in enumerate(entries)],2)
        rows.append([InlineKeyboardButton("🔙 الأنواع الرئيسية",callback_data="t:live")]); rows.append(back_main_row())
        await self._safe_edit(q,f"{g['icon']}✨ <b>{esc(g['key'])}</b> ✨\n━━━━━━━━━━━━━━━\n📦 اختر الباقة:",InlineKeyboardMarkup(rows))

    async def _show_live_items(self,q,gidx:int,pidx:int,page:int=0):
        hierarchy=HIER_CACHE.get("live") or await build_content_hierarchy(self.store,"live"); HIER_CACHE["live"]=hierarchy
        if gidx<0 or gidx>=len(hierarchy): return await self._show_categories(q,"live")
        g=hierarchy[gidx]; entries=list(g["packages"].items())
        if pidx<0 or pidx>=len(entries): return await self._show_live_packages(q,gidx)
        pname,d=entries[pidx]; items=[]; seen=set()
        for rid in d["ids"]:
            for it in await self.store.streams("live",rid):
                iid=it.get("stream_id")
                if iid is not None and iid not in seen and not is_adult_name(it.get("name") or ""):
                    seen.add(iid); items.append(it)
        if not items:
            await self._safe_edit(q,"❌ لا توجد قنوات في هذه الباقة حالياً.",InlineKeyboardMarkup([[InlineKeyboardButton("🔙 الباقات",callback_data=f"lt:{gidx}")],back_main_row()])); return
        await self._safe_edit(q,f"📡 <b>{esc(pname)}</b>\n━━━━━━━━━━━━━━━\n📺 <b>{len(items):,} قناة</b>",items_kb(items,"live",f"lp:{gidx}:{pidx}",page))

    async def _require_adult(self, q, uid: int) -> bool:
        """يرجع True لو مسموح، False لو طُلب الباسورد."""
        if is_admin(uid) or self.db.is_adult_unlocked(uid):
            return True
        await self._safe_edit(
            q,
            "🔐 <b>هذا القسم محمي</b>\n━━━━━━━━━━━━━━━\n"
            "أرسل كلمة المرور إذا كانت لديك صلاحية.\n"
            "لن يتم عرض أسماء أو تفاصيل المحتوى قبل التحقق.",
            InlineKeyboardMarkup([back_main_row()]))
        return False

    async def _show_items(self, q, type_: str, cat_id: str, page: int):
        await self._safe_edit(q, "⏳ جاري تحميل العناصر...")
        group_label = None
        if cat_id.startswith("g") and cat_id[1:].isdigit():
            # 🔗 فئة مدمجة: نجمع عناصر كل الأقسام الخام تحتها (مكرر يُحذف بالـ id)
            idx = int(cat_id[1:])
            groups = await get_groups(self.store, type_)
            entries = list(groups.items())
            GROUPS_CACHE[type_] = entries
            if idx >= len(entries):
                await self._show_categories(q, type_)
                return
            group_label, gdata = entries[idx]
            # حماية محتوى الكبار
            if group_label and is_adult_name(group_label):
                if not await self._require_adult(q, q.from_user.id):
                    ADULT_PENDING[q.from_user.id] = {
                        "type": type_, "cat_id": cat_id, "page": page, "kind": "items",
                    }
                    return
            items, seen = [], set()
            id_key = "series_id" if type_ == "series" else "stream_id"
            for raw_id in gdata["ids"]:
                for it in await self.store.streams(type_, raw_id):
                    iid = it.get(id_key)
                    if iid is not None and iid not in seen:
                        seen.add(iid)
                        items.append(it)
        else:
            items = await self.store.streams(type_, cat_id)
        if type_ == "live":
            items = [it for it in items if not is_non_islamic_religious(it.get("name") or "") and not is_adult_name(it.get("name") or "")]
        if not items:
            await self._safe_edit(q, "❌ لا توجد عناصر في هذا القسم.",
                                  InlineKeyboardMarkup([[InlineKeyboardButton("🔙 رجوع", callback_data=f"t:{type_}")], back_main_row()]))
            return
        # فحص أسماء العناصر إن كان القسم للكبار
        header = group_label or TYPE_LABEL[type_]
        if is_adult_name(header) or any(is_adult_name(it.get("name") or "") for it in items[:5]):
            if not await self._require_adult(q, q.from_user.id):
                ADULT_PENDING[q.from_user.id] = {
                    "type": type_, "cat_id": cat_id, "page": page, "kind": "items",
                }
                return
        _, page, pages = _page_slice(items, page)
        await self._safe_edit(
            q,
            f"✨ <b>{esc(header)}</b> ✨\n━━━━━━━━━━━━━━━\n"
            f"📦 <b>{len(items):,} عنصر</b> — صفحة {page + 1}/{pages}:",
            items_kb(items, type_, cat_id, page))

    async def _find_item(self, type_: str, iid: str) -> Optional[Dict]:
        id_key = "series_id" if type_ == "series" else "stream_id"
        items = await self.store.streams(type_, None)
        for it in items:
            if str(it.get(id_key)) == str(iid):
                return it
        return None

    # ---------- كارت العمل (بوستر + TMDB + أزرار) ----------
    async def _show_item(self, q, uid: int, type_: str, iid: str, cat_id: str, page: int):
        item = await self._find_item(type_, iid)
        if not item:
            await self._safe_edit(q, "❌ العنصر غير موجود.", InlineKeyboardMarkup([back_main_row()]))
            return
        if type_ == "live" and is_non_islamic_religious(item.get("name") or ""):
            await self._safe_edit(q, "❌ هذا المحتوى غير متاح.", InlineKeyboardMarkup([back_main_row()]))
            return

        name = clean_name(item.get("name") or item.get("title"))
        # حماية عنصر كبار
        if is_adult_name(name) or is_adult_name(item.get("name") or ""):
            if not await self._require_adult(q, uid):
                ADULT_PENDING[uid] = {
                    "type": type_, "cat_id": cat_id, "page": page, "kind": "item",
                    "iid": iid,
                }
                return
        self.db.log_view(uid, type_, str(iid))

        # جلب بيانات TMDB (بوستر رسمي + قصة عربية + تقييم)
        kind = "movie" if type_ == "movie" else ("series" if type_ == "series" else "")
        meta = await self.tmdb.lookup(name, kind) if kind else {}
        # 💾 حفظ الاسم الرسمي من TMDB كاسم بديل للبحث المزدوج (ترولز ↔ Trolls)
        if kind and meta.get("title"):
            try:
                self.db.set_alias(type_, str(iid), meta["title"])
                self.db.set_alias(type_, str(iid), name)
            except Exception:
                pass
        poster = meta.get("poster") or item.get("stream_icon") or item.get("cover") or ""
        rating = meta.get("rating") or item.get("rating") or item.get("rating_5based") or ""
        year = meta.get("year") or ""
        overview = meta.get("overview") or ""

        ar_title = meta.get("title") or name
        lines = [f"{ITEM_ICON[type_]}✨ <b>{esc(ar_title)}</b> ✨", "━━━━━━━━━━━━━━━"]
        if year:
            lines.append(f"📅 السنة: <b>{year}</b>")
        original_title = meta.get("original_title") or ""
        display_title = meta.get("title") or name
        if original_title and normalize_ar(original_title) != normalize_ar(display_title):
            lines.append(f"🌐 الاسم الأصلي: <b>{esc(original_title)}</b>")
        if rating:
            lines.append(f"⭐ التقييم: <b>{rating}</b>/10")
        if meta.get("runtime"):
            lines.append(f"⏱️ المدة: <b>{esc(meta['runtime'])} دقيقة</b>")
        if type_ == "series":
            info = await self.store.series_info(iid)
            # بعض سيرفرات Xtream تضع الغلاف داخل معلومات المسلسل وليس العنصر نفسه
            series_info = info.get("info") or {}
            poster = poster or series_info.get("cover") or series_info.get("cover_big") or series_info.get("movie_image") or ""
            seasons = info.get("seasons") or []
            eps_map = info.get("episodes") or {}
            total_eps = sum(len(v) for v in eps_map.values()) if eps_map else \
                sum(s.get("episode_count", 0) for s in seasons)
            if seasons:
                lines.append(f"📀 المواسم: <b>{len(seasons)}</b>")
            if total_eps:
                lines.append(f"🎞️ الحلقات: <b>{total_eps}</b>")
            if not overview:
                overview = (info.get("info") or {}).get("plot") or item.get("plot") or ""
        if type_ == "movie":
            ext = item.get("container_extension")
            if ext:
                lines.append(f"🎥 الصيغة: <b>{ext}</b>")
        if overview:
            lines.append(f"\n📝 <i>{esc(str(overview)[:280])}</i>")
        text = "\n".join(lines)

        kb = item_detail_kb(uid, self.db, type_, item, cat_id, page, self.xt, name, poster)

        # إرسال كارت المعاينة: صورة البوستر + التفاصيل + زر المشاهدة
        if poster:
            try:
                await q.message.delete()
            except Exception:
                pass
            try:
                await q.get_bot().send_photo(
                    q.message.chat_id, poster,
                    caption=text[:1000], parse_mode=ParseMode.HTML, reply_markup=kb)
                return
            except Exception as e:
                log.warning("فشل إرسال البوستر: %s", e)
        await self._safe_edit(q, text, kb)

    async def _show_seasons(self, q, series_id: str):
        await self._safe_edit(q, "⏳ جاري تحميل المواسم...")
        info = await self.store.series_info(series_id)
        seasons = info.get("seasons") or []
        if not seasons:
            await self._safe_edit(q, "❌ لا توجد مواسم لهذا المسلسل.",
                                  InlineKeyboardMarkup([back_main_row()]))
            return
        name = clean_name((info.get("info") or {}).get("name") or "المسلسل")
        await self._safe_edit(
            q,
            f"📺✨ <b>{esc(name)}</b> ✨\n━━━━━━━━━━━━━━━\n"
            f"📀 <b>{len(seasons)} موسم</b> — اختر الموسم:",
            seasons_kb(info, series_id))

    async def _show_episodes(self, q, series_id: str, season: int, page: int):
        await self._safe_edit(q, "⏳ جاري تحميل الحلقات...")
        info = await self.store.series_info(series_id)
        eps = (info.get("episodes") or {}).get(str(season), [])
        if not eps:
            await self._safe_edit(q, "❌ لا توجد حلقات في هذا الموسم.",
                                  InlineKeyboardMarkup([[InlineKeyboardButton("🔙 المواسم", callback_data=f"s:{series_id}:0")], back_main_row()]))
            return
        _, page, pages = _page_slice(eps, page)
        await self._safe_edit(
            q,
            f"📀✨ <b>الموسم {season}</b> ✨\n━━━━━━━━━━━━━━━\n"
            f"🎞️ <b>{len(eps)} حلقة</b> — صفحة {page + 1}/{pages}:",
            episodes_kb(info, series_id, season, page))

    async def _play_episode(self, q, episode_id: str, series_id: str, season: int, page: int):
        info = await self.store.series_info(series_id)
        eps = (info.get("episodes") or {}).get(str(season), [])
        ep = next((e for e in eps if str(e.get("id")) == str(episode_id)), None)
        if not ep:
            await self._safe_edit(q, "❌ الحلقة غير موجودة.",
                                  InlineKeyboardMarkup([[InlineKeyboardButton("🔙 الحلقات", callback_data=f"e:{series_id}:{season}:{page}")]]))
            return
        series_name = clean_name((info.get("info") or {}).get("name") or "")
        title = clean_name(str(ep.get("title") or f"الحلقة {ep.get('episode_num', '?')}"))
        dur = ep.get("info", {}).get("duration") if isinstance(ep.get("info"), dict) else None
        lines = [f"🎞️✨ <b>{esc(series_name)}</b> ✨" if series_name else "🎞️✨ <b>الحلقة</b> ✨",
                 "━━━━━━━━━━━━━━━", f"▶️ {esc(title)}"]
        if dur:
            lines.append(f"⏱️ المدة: {esc(dur)}")
        lines.append("\n🔗 <i>رابط المصدر المباشر</i>")
        await self._safe_edit(q, "\n".join(lines),
                              episode_play_kb(ep, series_id, season, page, self.xt, series_name))

    async def _show_favs_message(self, update, uid: int):
        favs=self.db.get_favs(uid)
        if not favs:
            await update.message.reply_text("❤️✨ <b>مفضلتك فارغة</b> ✨",parse_mode=ParseMode.HTML,reply_markup=main_reply_kb(uid)); return
        rows=[[InlineKeyboardButton(f"{ITEM_ICON.get(f.get('item_type'),'🎞️')} {clean_name(f.get('title'))[:28]}",callback_data=f"i:{f.get('item_type')}:{f.get('item_id')}:fav:0")] for f in favs[:30]]
        rows.append(back_main_row()); await update.message.reply_text("❤️✨ <b>المفضلة</b> ✨\n━━━━━━━━━━━━━━━\nاختر عنصراً:",parse_mode=ParseMode.HTML,reply_markup=InlineKeyboardMarkup(rows))

    async def _show_random_message(self, update, uid: int):
        type_=random.choice(["movie","series","live"]); items=[x for x in await self.store.streams(type_,None) if not is_adult_name(x.get("name") or "")]
        if not items: return await update.message.reply_text("❌ لا يوجد محتوى متاح حالياً.",reply_markup=main_reply_kb(uid))
        key="series_id" if type_=="series" else "stream_id"; it=random.choice(items); iid=str(it.get(key)); name=clean_name(it.get("name") or it.get("title"))
        await update.message.reply_text(f"🎲✨ <b>اختيار عشوائي</b> ✨\n━━━━━━━━━━━━━━━\n{ITEM_ICON[type_]} {esc(name)}",parse_mode=ParseMode.HTML,reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("👀 التفاصيل والمشاهدة",callback_data=f"i:{type_}:{iid}:all:0")],back_main_row()]))

    async def _show_favs(self, q, uid: int):
        favs = self.db.get_favs(uid)
        if not favs:
            await self._safe_edit(
                q,
                "❤️✨ <b>مفضلتك</b> ✨\n━━━━━━━━━━━━━━━\n"
                "فارغة حالياً — أضف أعمالك من زر ❤️ في كارت أي عمل.",
                InlineKeyboardMarkup([back_main_row()]))
            return
        btns = []
        for f in favs[:30]:
            t, iid, title = f["item_type"], f["item_id"], f["title"]
            btns.append(InlineKeyboardButton(f"{ITEM_ICON.get(t, '🎞️')} {clean_name(title)[:24]}",
                                             callback_data=f"i:{t}:{iid}:fav:0"))
        rows = grid(btns, 2)
        rows.append(back_main_row())
        await self._safe_edit(
            q,
            f"❤️✨ <b>مفضلتك</b> ✨\n━━━━━━━━━━━━━━━\n💎 <b>{len(favs)} عمل</b> محفوظ عندك:",
            InlineKeyboardMarkup(rows))

    async def _random_pick(self, q):
        await self._safe_edit(q, "🎲 جاري اختيار عشوائي...")
        type_ = random.choice(["movie", "series", "live"])
        cats = await self.store.categories(type_)
        if not cats:
            await self._safe_edit(q, "❌ لا يوجد محتوى حالياً.", InlineKeyboardMarkup([back_main_row()]))
            return
        cat = random.choice(cats)
        items = await self.store.streams(type_, cat.get("category_id"))
        if not items:
            await self._safe_edit(q, "❌ لا يوجد محتوى حالياً.", InlineKeyboardMarkup([back_main_row()]))
            return
        it = random.choice(items)
        id_key = "series_id" if type_ == "series" else "stream_id"
        await self._show_item(q, q.from_user.id, type_, str(it.get(id_key)), "all", 0)

    async def _show_admin(self, q):
        if not is_admin(q.from_user.id):
            await self._safe_edit(q, "🚫 هذه اللوحة للأدمن فقط.", InlineKeyboardMarkup([back_main_row()]))
            return
        await self._safe_edit(
            q,
            "👑✨ <b>لوحة تحكم الأدمن</b> ✨\n━━━━━━━━━━━━━━━\n⚙️ <i>اختر الإجراء:</i>",
            admin_kb())

    # ---------- راوتر الأزرار ----------
    async def on_callback(self, update: Update, ctx: ContextTypes.DEFAULT_TYPE):
        q = update.callback_query
        data = q.data or ""
        uid = q.from_user.id
        try:
            await q.answer()
        except Exception:
            pass

        try:
            if data in ("", "noop"):
                return
            if data == "main":
                await self._safe_edit(
                    q,
                    "✨🎬 <b>𝑌𝑜𝑢𝑠𝑒𝑖𝑓 𝐹𝑖𝑙𝑚𝑠</b> 🎬✨\n━━━━━━━━━━━━━━━\n"
                    "🏠 <b>القائمة الرئيسية</b>\n👇 <i>اختر اللي نفسك فيه:</i>",
                    main_menu_kb(uid))
            elif data.startswith("t:"):
                await self._show_categories(q, data.split(":", 1)[1])
            elif data.startswith("qk:"):
                key = data.split(":", 1)[1]
                found = False
                for t in ("movie", "series", "live"):
                    hierarchy = HIER_CACHE.get(t) or await build_content_hierarchy(self.store, t)
                    HIER_CACHE[t] = hierarchy
                    for idx, g in enumerate(hierarchy):
                        if normalize_ar(key) in normalize_ar(g.get("key", "")):
                            if t == "live":
                                await self._show_live_packages(q, idx)
                            else:
                                await self._show_genre_countries(q, t, idx)
                            found = True; break
                    if found: break
                if not found:
                    await self._safe_edit(q, f"❌ لا توجد فئة «{esc(key)}» حالياً.", main_menu_kb(uid))
            elif data.startswith("g:"):
                # 🌳 فئة مدمجة — نبنيها من كاش SQLite الدائم (تشتغل حتى بعد إعادة التشغيل)
                _, t, idx = data.split(":", 2)
                groups = await get_groups(self.store, t)
                entries = list(groups.items())
                GROUPS_CACHE[t] = entries
                if not idx.isdigit() or int(idx) >= len(entries):
                    await self._show_categories(q, t)
                else:
                    await self._show_items(q, t, f"g{idx}", 0)
            elif data.startswith("gp:"):
                # 📄 تنقل صفحات الفئات
                _, t, page = data.split(":", 2)
                groups = await get_groups(self.store, t)
                GROUPS_CACHE[t] = list(groups.items())
                await self._safe_edit(
                    q,
                    f"✨ <b>{TYPE_LABEL[t]}</b> ✨\n━━━━━━━━━━━━━━━\n"
                    f"🌳 <b>{len(groups)} فئة</b> — اختر الفئة:",
                    groups_kb(groups, t, int(page)))
            elif data.startswith("c:"):
                _, t, cid, page = data.split(":")
                await self._show_items(q, t, cid, int(page))
            elif data.startswith("i:"):
                _, t, iid, cid, page = data.split(":")
                await self._show_item(q, uid, t, iid, cid, int(page))
            elif data.startswith("f:"):
                _, t, iid, cid, page = data.split(":")
                item = await self._find_item(t, iid)
                title = clean_name((item or {}).get("name") or (item or {}).get("title") or iid)
                poster = (item or {}).get("stream_icon") or (item or {}).get("cover") or ""
                added = self.db.toggle_fav(uid, t, iid, title, poster)
                try:
                    await q.answer("❤️ أُضيف للمفضلة" if added else "💔 أُزيل من المفضلة")
                except Exception:
                    pass
                if item:
                    await self._show_item(q, uid, t, iid, cid, int(page))
            elif data.startswith("w:"):
                # ⚡ مشاهدة سريعة: أول حلقة من أول موسم مباشرة
                sid = data.split(":", 1)[1]
                await self._safe_edit(q, "⏳ جاري تحضير أول حلقة...")
                info = await self.store.series_info(sid)
                eps_map = info.get("episodes") or {}
                first_ep = None
                first_season = None
                for s in sorted((info.get("seasons") or []), key=lambda x: x.get("season_number", 0)):
                    s_eps = eps_map.get(str(s.get("season_number")), [])
                    if s_eps:
                        first_season = s.get("season_number")
                        first_ep = s_eps[0]
                        break
                if first_ep:
                    await self._play_episode(q, str(first_ep.get("id")), sid, int(first_season), 0)
                else:
                    await self._safe_edit(q, "❌ لا توجد حلقات متاحة لهذا المسلسل حالياً.",
                                          InlineKeyboardMarkup([back_main_row()]))
            elif data.startswith("s:"):
                await self._show_seasons(q, data.split(":")[1])
            elif data.startswith("e:"):
                _, sid, season, page = data.split(":")
                await self._show_episodes(q, sid, int(season), int(page))
            elif data.startswith("p:"):
                _, eid, sid, season, page = data.split(":")
                await self._play_episode(q, eid, sid, int(season), int(page))
            elif data.startswith("sr:"):
                _, t, page = data.split(":")
                if t == "back":
                    d = SEARCH_CACHE.get(q.from_user.id)
                    if d:
                        grouped = {"movie": d["movie"], "series": d["series"], "live": d["live"]}
                        await self._safe_edit(q, self._search_summary_text(d["q"], grouped),
                                              self._search_summary_kb(grouped))
                    else:
                        await self._safe_edit(q, "⌛ ابعت كلمة البحث من جديد.", main_menu_kb(uid))
                else:
                    await self._show_search_results(q, t, int(page))
            elif data == "act:search":
                ctx.user_data["awaiting_search"] = True
                await self._safe_edit(
                    q,
                    "🔍✨ <b>البحث الذكي</b> ✨\n━━━━━━━━━━━━━━━\n"
                    "ابعت اسم الفيلم أو المسلسل أو القناة\n<i>(عربي أو إنجليزي)</i>",
                    InlineKeyboardMarkup([back_main_row()]))
            elif data == "act:random":
                await self._random_pick(q)
            elif data == "act:fav":
                await self._show_favs(q, uid)
            elif data == "act:help":
                await self._safe_edit(
                    q,
                    "❓✨ <b>مساعدة 𝑌𝑜𝑢𝑠𝑒𝑖𝑓 𝐹𝑖𝑙𝑚𝑠</b> ✨\n━━━━━━━━━━━━━━━\n"
                    "🎬 <b>الأفلام:</b> تصفح واختَر الفيلم ثم اضغط مشاهدة.\n"
                    "📺 <b>المسلسلات:</b> اختر المسلسل ← الموسم ← الحلقة.\n"
                    "📡 <b>القنوات:</b> اختر القناة واضغط مشاهدة مباشرة.\n"
                    "🔍 <b>البحث:</b> اكتب الاسم بالعربي أو الإنجليزي.\n"
                    "🔗 <b>رابط مباشر:</b> أرسل أي رابط HTTP/HTTPS وسيتم إرساله كرابط مباشر كما هو.\n"
                    "❤️ <b>المفضلة:</b> احفظ أعمالك للوصول السريع إليها.\n\n"
                    "🖼️ <b>البوسترات والبيانات:</b> TMDB مفعّل لجلب البوستر والبيانات العربية والإنجليزية والتقييم، مع بوستر السيرفر كبديل.",
                    InlineKeyboardMarkup([back_main_row()]))
            elif data == "act:admin":
                await self._show_admin(q)
            elif data == "adm:stats":
                if is_admin(uid):
                    lines = ["📊 <b>إحصائيات البوت</b>", "━━━━━━━━━━━━━━━",
                             f"👥 المستخدمون: <b>{self.db.users_count()}</b>",
                             f"👁 مشاهدات اليوم: <b>{self.db.views_today()}</b>",
                             f"📈 إجمالي المشاهدات: <b>{self.db.views_total()}</b>"]
                    for t in ("live", "movie", "series"):
                        cats = await self.store.categories(t)
                        lines.append(f"{TYPE_LABEL[t]}: {len(cats)} قسم")
                    lines.append(f"\n🌐 السيرفر: <code>{esc(self.xt.base)}</code>")
                    lines.append(f"🔗 التشغيل: رابط المصدر المباشر بدون وسيط")
                    lines.append(f"🎞️ TMDB: {'✅ مفعّل' if self.tmdb.enabled else '⚠️ بدون مفتاح'}")
                    await self._safe_edit(q, "\n".join(lines), admin_kb())
            elif data == "adm:flush":
                if is_admin(uid):
                    self.db.cache_flush()
                    await self._safe_edit(q, "🔄 تم مسح الكاش — البيانات ستُحمّل من جديد.", admin_kb())
            elif data == "adm:cast":
                if is_admin(uid):
                    await self._safe_edit(q, "📢 أرسل الرسالة بالأمر:\n/broadcast نص الرسالة", admin_kb())
            elif data == "adm:adultpass":
                if is_admin(uid):
                    pw = self.db.get_or_create_adult_password()
                    await self._safe_edit(
                        q,
                        "🔐✨ <b>باسورد محتوى الكبار</b> ✨\n━━━━━━━━━━━━━━━\n"
                        f"🔑 الباسورد الحالي:\n<code>{esc(pw)}</code>\n\n"
                        "⚠️ <i>هذا الباسورد يظهر لك فقط (الأدمن).\n"
                        "المستخدمون يدخلونه مرة واحدة لفتح قسم «للكبار فقط».</i>",
                        admin_kb())
            elif data == "adm:regenpass":
                if is_admin(uid):
                    pw = self.db.regenerate_adult_password()
                    await self._safe_edit(
                        q,
                        "🔄✨ <b>تم تجديد الباسورد</b> ✨\n━━━━━━━━━━━━━━━\n"
                        f"🔑 الباسورد الجديد:\n<code>{esc(pw)}</code>\n\n"
                        "✅ تم إلغاء فتح جميع المستخدمين السابقين.",
                        admin_kb())
            else:
                await self._safe_edit(q, "❓ أمر غير معروف.", main_menu_kb(uid))
        except RetryAfter as e:
            await asyncio.sleep(e.retry_after + 1)
        except (TimedOut, NetworkError) as e:
            log.warning("مشكلة شبكة: %s", e)
        except Exception as e:
            log.exception("خطأ في معالجة الزر %s: %s", data, e)
            try:
                await self._safe_edit(q, "❌ حدث خطأ مؤقت — حاول مرة أخرى.", main_menu_kb(uid))
            except Exception:
                pass

    # ---------- نتائج البحث المقسّمة ----------
    def _search_summary_text(self, query: str, grouped: Dict) -> str:
        return (
            f"🔍✨ <b>نتائج البحث عن «{esc(query)}»</b> ✨\n"
            "━━━━━━━━━━━━━━━\n"
            f"🎬 <b>الأفلام:</b> {len(grouped['movie'])} نتيجة\n"
            f"📺 <b>المسلسلات:</b> {len(grouped['series'])} نتيجة\n"
            f"📡 <b>القنوات:</b> {len(grouped['live'])} نتيجة\n"
            "━━━━━━━━━━━━━━━\n"
            "👇 <i>اختر القسم اللي عايز تعرضه</i>"
        )

    def _search_summary_kb(self, grouped: Dict) -> InlineKeyboardMarkup:
        rows = []
        if grouped["movie"]:
            rows.append([InlineKeyboardButton(f"🎬 عرض الأفلام ({len(grouped['movie'])})",
                                              callback_data="sr:movie:0")])
        if grouped["series"]:
            rows.append([InlineKeyboardButton(f"📺 عرض المسلسلات ({len(grouped['series'])})",
                                              callback_data="sr:series:0")])
        if grouped["live"]:
            rows.append([InlineKeyboardButton(f"📡 عرض القنوات ({len(grouped['live'])})",
                                              callback_data="sr:live:0")])
        rows.append(back_main_row())
        return InlineKeyboardMarkup(rows)

    async def _show_search_results(self, q, type_: str, page: int):
        uid = q.from_user.id
        data = SEARCH_CACHE.get(uid)
        if not data or (time.time() - data["ts"]) > 1800:
            await self._safe_edit(q, "⌛ انتهت صلاحية نتائج البحث — ابعت الكلمة من جديد.",
                                  InlineKeyboardMarkup([back_main_row()]))
            return
        items = data.get(type_, [])
        slice_, page, pages = _page_slice(items, page)
        id_key = "series_id" if type_ == "series" else "stream_id"
        btns = []
        for it in slice_:
            iid = it.get(id_key)
            name = clean_name(it.get("name") or it.get("title"))
            btns.append(InlineKeyboardButton(f"{ITEM_ICON[type_]} {name[:26]}",
                                             callback_data=f"i:{type_}:{iid}:all:0"))
        rows = grid(btns, 2)
        if pages > 1:
            nav = []
            nav.append(InlineKeyboardButton("◀️ السابق", callback_data=f"sr:{type_}:{page - 1}") if page > 0
                       else InlineKeyboardButton("·", callback_data="noop"))
            nav.append(InlineKeyboardButton(f"📄 {page + 1}/{pages}", callback_data="noop"))
            nav.append(InlineKeyboardButton("التالي ▶️", callback_data=f"sr:{type_}:{page + 1}") if page < pages - 1
                       else InlineKeyboardButton("·", callback_data="noop"))
            rows.append(nav)
        rows.append([InlineKeyboardButton("🔙 نتائج البحث", callback_data="sr:back:0")])
        rows.append(back_main_row())
        await self._safe_edit(
            q,
            f"🔍✨ <b>«{esc(data['q'])}»</b> — {TYPE_LABEL[type_]}\n"
            f"━━━━━━━━━━━━━━━\n📦 <b>{len(items)} نتيجة</b> (صفحة {page + 1}/{pages}):",
            InlineKeyboardMarkup(rows))

    # ---------- الرسائل النصية: بحث ذكي + روابط مباشرة ----------
    async def text_router(self, update: Update, ctx: ContextTypes.DEFAULT_TYPE):
        if not update.message or not update.message.text:
            return
        text = update.message.text.strip()
        if text.startswith("/"):
            return
        uid = update.effective_user.id
        if text == "🔍 بحث":
            ctx.user_data["awaiting_search"] = True
            await update.message.reply_text("🔍 أرسل اسم الفيلم أو المسلسل أو القناة — عربي أو English:",reply_markup=main_reply_kb(uid)); return
        if text == "❤️ المفضلة":
            await self._show_favs_message(update,uid); return
        if text == "🎲 عشوائي":
            await self._show_random_message(update,uid); return
        if text == "❓ مساعدة":
            await self.cmd_help(update,ctx); return
        if text == "👑 لوحة الأدمن":
            if is_admin(uid): await update.message.reply_text("👑✨ <b>لوحة الأدمن</b>",parse_mode=ParseMode.HTML,reply_markup=admin_kb())
            else: await update.message.reply_text("⛔ غير مصرح لك باستخدام لوحة الأدمن.")
            return
        # 🔐 التحقق من باسورد محتوى الكبار
        if uid in ADULT_PENDING:
            correct = self.db.get_or_create_adult_password()
            if text.strip() == correct:
                self.db.unlock_adult(uid)
                pending = ADULT_PENDING.pop(uid, {})
                await update.message.reply_text(
                    "✅ <b>تم فتح محتوى الكبار</b>\n"
                    "يمكنك الآن تصفح القسم بحرية.",
                    parse_mode=ParseMode.HTML)
                # إعادة فتح القسم المطلوب إن أمكن
                kind = pending.get("kind")
                if kind == "items":
                    # نعيد عبر رسالة جديدة لأننا لا نملك callback query هنا
                    await update.message.reply_text(
                        "🔄 اضغط مرة أخرى على القسم لفتحه.",
                        reply_markup=main_menu_kb(uid))
                return
            else:
                await update.message.reply_text(
                    "✨ هذا القسم مخصص لمالك البوت فقط ✨\n━━━━━━━━━━━━━━━\n🔒 لا يمكن للمستخدمين الوصول إلى محتوى الكبار.\n📩 إذا كنت تعتقد أن لديك صلاحية، تواصل مع مطور البوت.",
                    reply_markup=main_reply_kb(uid))
                return

        # 🔗 معالجة رابط فيديو مباشر → زر مشاهدة فوري
        url_match = re.search(r"https?://[^\s<>]+", text)
        if url_match:
            raw_url = url_match.group(0).rstrip(".,؛،)\"'")
            if raw_url.startswith(("http://", "https://")):
                link = direct_url(raw_url)
                await update.message.reply_text(
                    "🎬✨ <b>الرابط المباشر جاهز</b> ✨\n━━━━━━━━━━━━━━━\n🌐 رابط المصدر الأصلي بدون وسيط خارجي.\n\n👇 اضغط مشاهدة لبدء التشغيل:",
                    parse_mode=ParseMode.HTML,
                    reply_markup=InlineKeyboardMarkup([
                        [InlineKeyboardButton("▶️ مشاهدة الآن 🎬", url=link)],
                        [InlineKeyboardButton("🏠 القائمة الرئيسية", callback_data="main")],
                    ]))
                return

        # 🔍 بحث ذكي
        msg = await update.message.reply_text(f"🔍 جاري البحث عن: <b>{esc(text)}</b>...",
                                              parse_mode=ParseMode.HTML)
        results = await self.store.search(text)
        if not results:
            await msg.edit_text(
                f"🔍✨ <b>بحث عن «{esc(text)}»</b> ✨\n"
                "━━━━━━━━━━━━━━━\n"
                "😔 <b>لا توجد نتائج</b>\n"
                "💡 جرّب كلمة تانية أو جزء من الاسم",
                parse_mode=ParseMode.HTML,
                reply_markup=InlineKeyboardMarkup([back_main_row()]))
            return
        grouped = {"movie": [], "series": [], "live": []}
        for t, it in results:
            grouped[t].append(it)
        uid = update.effective_user.id
        SEARCH_CACHE[uid] = {"q": text, **grouped, "ts": time.time()}
        await msg.edit_text(self._search_summary_text(text, grouped),
                            parse_mode=ParseMode.HTML,
                            reply_markup=self._search_summary_kb(grouped))

    # ---------- تشغيل ----------
    async def _post_init(self, app):
        try:
            await app.bot.set_my_commands([BotCommand("start", "بدء البوت والعودة للقائمة الرئيسية"), BotCommand("help", "المساعدة")])
        except Exception as e:
            log.warning("تعذر تثبيت أوامر القائمة: %s", e)

    def run(self):
        app = Application.builder().token(BOT_TOKEN).post_init(self._post_init).build()
        app.add_handler(CommandHandler("start", self.cmd_start))
        app.add_handler(CommandHandler("help", self.cmd_help))
        app.add_handler(CommandHandler("stats", self.cmd_stats))
        app.add_handler(CommandHandler("broadcast", self.cmd_broadcast))
        app.add_handler(CallbackQueryHandler(self.on_callback))
        app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, self.text_router))
        log.info("🚀 %s يعمل الآن — السيرفر: %s | التشغيل: %s", BOT_NAME, self.xt.base, "روابط المصدر المباشرة" )
        app.run_polling(drop_pending_updates=True)


# كاش نتائج البحث في الذاكرة لكل مستخدم
SEARCH_CACHE: Dict[int, Dict] = {}

# كاش المجموعات المدمجة لكل نوع (movie/series/live) — يُملأ عند عرض الأقسام
# البنية: {"movie": [("👻 رعب فرنسية", {"ids": [...], "count": N}), ...]}
GROUPS_CACHE: Dict[str, List[Tuple[str, Dict]]] = {}

# انتظار إدخال باسورد الكبار: {user_id: {"type", "cat_id", "page", "kind"}}
ADULT_PENDING: Dict[int, Dict] = {}


if __name__ == "__main__":
    CinemaBot().run()
