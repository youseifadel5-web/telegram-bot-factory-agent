# رفع المشروع إلى GitHub وتشغيل Workflow

هذا المشروع مجهّز بملف GitHub Actions في `.github/workflows/telegram-bot.yml`.

## الرفع من جهازك

افتح الطرفية داخل مجلد المشروع ثم نفّذ الأوامر التالية:

```bash
git init
git add .
git commit -m "Initial commit"
git branch -M main
git remote add origin https://github.com/USERNAME/REPOSITORY.git
git push -u origin main
```

استبدل `USERNAME/REPOSITORY` بعنوان مستودعك في GitHub. لا ترفع ملف `.env` أو أي Token؛ ملف `.gitignore` يمنع الملفات الحساسة المعتادة.

## إضافة أسرار GitHub

من صفحة المستودع افتح **Settings → Secrets and variables → Actions → New repository secret**، ثم أضف الأسرار التالية:

| الاسم | الحالة | القيمة |
|---|---|---|
| `BOT_TOKEN` | مطلوب لتشغيل البوت | Token البوت من BotFather |
| `ADMIN_IDS` | اختياري | أرقام Telegram للمشرفين، حسب تنسيق المشروع |
| `OPENROUTER_API_KEY` | اختياري | مفتاح OpenRouter إذا أردت ميزات الذكاء الاصطناعي |
| `OPENROUTER_MODEL` | اختياري | اسم النموذج المطلوب في OpenRouter |

## طريقة التشغيل

عند رفع أي تعديل على فرع `main` أو `master`، ينفذ الـ Workflow الفحص الآلي تلقائيًا، بما في ذلك تجميع ملفات Python، وتشغيل `scripts/verify_v3.py`، وتشغيل اختبارات مجلد `tests`.

لتشغيل البوت يدويًا، افتح تبويب **Actions**، واختر **Telegram Bot**، ثم اضغط **Run workflow** واختر `start`. ولتشغيل الفحوصات يدويًا اختر `test`.

> تشغيل البوت على GitHub-hosted runner مؤقت، لذلك قد يتوقف عند انتهاء مدة المهمة أو عند إيقاف الـ runner. للاستخدام المستمر على مدار الساعة استخدم استضافة دائمة.

## تشغيل محلي

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
# املأ القيم داخل .env
PYTHONPATH=. python scripts/verify_v3.py
PYTHONPATH=. python main.py
```
