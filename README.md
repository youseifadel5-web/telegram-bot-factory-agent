# Telegram Merged Bot

هذا المشروع يشغّل نظامي البوت الموجودين في المشروع معًا باستخدام Bot Token واحد وPolling واحد، مع إبقاء كل نظام بواجهته وHandlers وCallbacks الخاصة به.

## GitHub Secrets المطلوبة فقط

```text
ADMIN_ID
API_HASH
API_ID
BOT_TOKEN
TMDB_API_KEY
```

## التشغيل من GitHub Actions

1. ادخل إلى تبويب **Actions**.
2. اختر **تشغيل البوت المدمج**.
3. اضغط **Run workflow**.
4. تأكد أن الـSecrets الخمسة موجودة في:
   Settings → Secrets and variables → Actions.

## ملاحظة

لا تشغّل ملفًا من النظامين منفردًا مع `main.py` في نفس الوقت، لأن نفس Bot Token لا يجب أن يكون له أكثر من Poller يستقبل `getUpdates`.
