"""مفاتيح وثوابت مصادر المحتوى — منقولة من تطبيق المستخدم YouseifPlayer.

كل القيم اللي تحت جاية من ملفات إعداد تطبيق المستخدم نفسه (YouseifPlayer)
والهدف إنها تتجمّع في مكان واحد واضح يسهل تغييره. مفيش أي طلب شبكة هنا،
ولا أي مفاتيح سرية لأي طرف تالت — دي توكنات المصادر اللي التطبيق بيستخدمها.
"""
from __future__ import annotations

# ============================================================
# 5.1 — القيم المفكوكة من خزنة التطبيق (SecretVault)
#     مفتاح الفك: "YouseifKey9" (Base64 ثم XOR)
# ============================================================

# توكن فاصل HD — بيتحط في كل مسار من مسارات الـ API
FASEL_TOKEN = "p2lbgWkFrykA4QyUmpHihzmc5BNzIABq"
# نفس التوكن بس بالاسم اللي التطبيق بيستخدمه جوه مسارات فاصل
APP_TOKEN = FASEL_TOKEN
# اسم الحزمة المطلوب في هيدر packagename
FASEL_PACKAGE = "com.flech.mathquiz"
# كود البوابة
PORTAL_CODE = "2026"
# قاعدة بيانات فايربيس
FIREBASE_URL = "https://bsr-player-9c88b-default-rtdb.firebaseio.com"
# جذر شجرة فايربيس
FIREBASE_ROOT = "bsr_player"
# نطاق السكرابينج (البصري / ألووي)
SCRAPING_DOMAIN = "https://k.alooytv10.com"
# العامل الاحتياطي (worker) اللي بيفك روابط فاصل
FALLBACK_WORKER = "https://autumn-dust-1a31.flechlivraison.workers.dev?url="

# ============================================================
# 5.3 — يوزر-إيجنتس المشغّل والروابط
# ============================================================
UA_VLC = "VLC/3.0.21 LibVLC/3.0.21"
UA_EXOPLAYER = "ExoPlayerLib/2.19.1 (Linux;Android 14) YouseifPlayer/12"
UA_BROWSER = (
    "Mozilla/5.0 (Linux; Android 14; SM-S918B) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Mobile Safari/537.36"
)

# ============================================================
# يوزر-إيجنتس إضافية مستخدمة جوه الـ clients والسكرابرز
# ============================================================
UA_EASYPLEX = "EasyPlex (Android 15; RMX3710; realme REE2ADL1; ar)"
UA_HIKAYE = "Mozilla/5.0 HikayeTV/3.0"
UA_GOLIVE = "Mozilla/5.0 YouseifPlayer/25.2"
UA_ANDROID = "Mozilla/5.0 Android"
UA_DESKTOP = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/141.0.0.0 Safari/537.36"
)
UA_CHROME141 = UA_DESKTOP
UA_CHROME137 = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/137.0.0.0 Safari/537.36"
)
# العامل الاحتياطي لازم يبعت UA قديم ومحدّد، ومفيش Referer خالص
UA_WORKER = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/117.0.0.0 Safari/537.36"
)

# ============================================================
# 5.2 — الهيدرات المطلوبة لكل مضيف/طبقة
# ============================================================

# فاصل HD API — لازم هيدر packagename وإلا الرد يرجّع فاضي/محجوب
FASEL_HEADERS = {
    "Accept": "application/json",
    "packagename": FASEL_PACKAGE,
    "User-Agent": UA_EASYPLEX,
}

# حكاية TV API
HIKAYE_HEADERS = {
    "Accept": "application/json",
    "User-Agent": UA_HIKAYE,
    "Accept-Language": "ar,en;q=0.8",
}

# GoLive API
GOLIVE_HEADERS = {
    "Accept": "application/json",
    "User-Agent": UA_GOLIVE,
}

# فايربيس RTDB
FIREBASE_HEADERS = {
    "Accept": "application/json",
}

# سكرابينج ألووي (البصري)
ALOOY_HEADERS = {
    "User-Agent": UA_ANDROID,
    "Accept": "text/html,*/*",
}

# سكرابينج أفلام فايربيس
FIREBASE_SCRAPE_HEADERS = {
    "User-Agent": UA_ANDROID,
}

# مسارات SOURCE_HOSTS /api/source لازم Referer لموقع فاصل
SOURCE_HOST_HEADERS = {
    "Referer": "https://www.fasel-hd.com/",
}

# العامل (worker): UA ثابت بس، وممنوع Referer/Accept-Language/كوكيز
WORKER_HEADERS = {
    "User-Agent": UA_WORKER,
    "Accept": "*/*",
}

# الطلب العام (httpGet): UA كروم 137 + Accept-Language
GENERAL_HEADERS = {
    "User-Agent": UA_CHROME137,
    "Accept": "*/*",
    "Accept-Language": "ar,en;q=0.9",
}

# جدول الهيدرات حسب المضيف — يستخدمه http.headers_for
HOST_HEADERS = {
    "fasel": FASEL_HEADERS,
    "fashd.com": FASEL_HEADERS,
    "kahitdgku.com": FASEL_HEADERS,
    "hrrejhp.com": FASEL_HEADERS,
    "hikaye": HIKAYE_HEADERS,
    "golive": GOLIVE_HEADERS,
    "admin.golive-pro.online": HIKAYE_HEADERS,
    "firebase": FIREBASE_HEADERS,
    "firebaseio.com": FIREBASE_HEADERS,
    "alooy": ALOOY_HEADERS,
    "k.alooytv10.com": ALOOY_HEADERS,
    "source_host": SOURCE_HOST_HEADERS,
    "worker": WORKER_HEADERS,
}
