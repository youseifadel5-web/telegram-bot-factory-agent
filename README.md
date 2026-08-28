# 🎬 Telegram Movie/Series Bot

بوت تيليجرام مبني على **Xtream Codes API** لمشاهدة القنوات المباشرة والأفلام والمسلسلات مع دعم بروكسي وموارد متعددة وبحث ومفضلة وسجل ولوحة إدارة.

## 🗂️ هيكل الإعدادات

قيم المشروع منقسمة بوضوح على ملفين:

| الملف | يحتوي على |
|---|---|
| **`config.py`** *(ترفعه مع المشروع)* | بيانات IPTV، سيرفرات احتياطية، البروكسي، الأدمن، إعدادات الواجهة… كل القيم العادية |
| **GitHub Secrets** *(ما يطلعش للعلن)* | ٣ أسرار فقط: `BOT_TOKEN`، `API_ID`، `API_HASH` |

## 🚀 التشغيل محليًا

```bash
# 1) ثبّت المتطلبات
pip install -r requirements.txt

# 2) أنشئ ملف الإعدادات من المثال
cp config.example.py config.py

# 3) عدّل config.py بالقيم العادية لديك
#    (يوزر/باسورد IPTV، روابط السيرفرات، البروكسي…)

# 4) ضع الأسرار الثلاثة في ملف .env
cat > .env <<'EOF'
BOT_TOKEN=123456789:ABC...
API_ID=12345678
API_HASH=abcdef0123456789...
EOF

# 5) شغّل
python bot.py
```

## 📤 النشر على GitHub

```bash
git init
git add .
git commit -m "Cinema Telegram bot"
git branch -M main
git remote add origin https://github.com/<user>/<repo>.git
git push -u origin main --force
```

بعد الرفع، **لا تنسَ** تنشئ `config.py` بالقيم الصحيحة داخل الريبو:
- إما ترفعه مع رفع الكود (الطريقة الأسهل)
- وإما من واجهة GitHub: **Add file → Create new file** باسم `config.py` وتنسخ القيم.

> ⚠️ **ملاحظة أمان**: تأكد إن `config.py` تبع مشروعك **مفيهوش أي قيمة من الأسرار الثلاثة**. الثلاث أسرار (`BOT_TOKEN` / `API_ID` / `API_HASH`) تفضل في Secrets فقط.

## 🔐 إعداد الـ Secrets

من صفحة الريبو: **Settings → Secrets and variables → Actions → New repository secret**.
أضف **ثلاث** أسرار فقط تمامًا:

| Secret | المصدر |
|---|---|
| `BOT_TOKEN` | من @BotFather في تيليجرام |
| `API_ID` | من my.telegram.org |
| `API_HASH` | من my.telegram.org |

باقي القيم كلها في ملف `config.py` المعدّل للريبو.

## ▶️ التشغيل عبر GitHub Actions

1. ارفع الكود كما في خطوة النشر.
2. من تبويب **Actions** اختر workflow البوت واضغط **Run workflow**.
3. جرّب `/start` في تيليجرام.

> GitHub Actions يوقف أي Job بعد ~6 ساعات. لو محتاج تشغيل مستمر، انقل البوت لسيرفر خاص (Railway / Render / VPS).

## 🛠️ تخصيص الإعدادات (`config.py`)

```python
ADMIN_IDS = [123456789]              # الآيدي بتاعك كأدمن
IPTV_USERNAME = "..."
IPTV_PASSWORD = "..."
IPTV_BASE_URL = "http://server:8000"
IPTV_BACKUP_URLS = ["http://b1:8000", "http://b2:8000"]
ATLAN_USERNAME = "..."                # مصدر مسلسلات إضافي (اختياري)
ATLAN_PASSWORD = "..."
ATLAN_BASE_URL = "http://atlan..."
PROXY_URL = "https://worker.dev"      # اتركها "" لو ما تحتاجش بروكسي
ITEMS_PER_PAGE = 10
CACHE_DURATION = 600                  # كباش API في ثواني
BOT_NAME = "سينما بوت"
DB_PATH = "cinema_bot.db"
```

## ⚠️ ملاحظات أمان

- **ثلاث أسرار بس** في Secrets: التوكن ومعرّفات API.
- كل القيم العادية في `config.py` ترفعها مع الريبو وتقدر تعدّلها في أي وقت بدون ما تعيد إصدار توكن.
- لا تشارك توكن البوت مع أحد. لو حصل، استخدم `/revoke` في @BotFather وولّد جديد.
