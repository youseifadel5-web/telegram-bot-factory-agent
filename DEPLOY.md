# تشغيل البوت + API على الاستضافة

## الوضع الموصى به
شغّل `python bot.py` فقط. الـlauncher الحالي يشغّل Telegram polling والـREST API معًا في نفس العملية، لذلك يظلان متصلين بنفس مصدر المحتوى وقاعدة البيانات.

## Localhost
```env
API_HOST=127.0.0.1
API_PORT=8000
API_BASE_URL=http://127.0.0.1:8000
```

## استضافة / VPS / Docker
```env
API_HOST=0.0.0.0
# اترك API_PORT فارغًا إذا كانت الاستضافة توفر PORT، أو استخدم PORT=xxxx
API_PUBLIC_BASE_URL=https://api.example.com
```

`API_PUBLIC_BASE_URL` هو العنوان الذي يستطيع الهاتف الوصول إليه. إذا كان غير موجود، تحاول الـAPI استخدام `X-Forwarded-Host`/`X-Forwarded-Proto` أو عنوان الطلب تلقائيًا.

## المشغل على الهاتف
- إذا كان الـPlayer مستضافًا على نفس الدومين: يستخدم نفس الـorigin تلقائيًا.
- إذا كان APK أو ملفًا محليًا: يستخدم localhost للتطوير.
- إذا كانت الـAPI على دومين مختلف: Settings → API Server URL → ضع عنوان HTTPS العام.

لا تضع `BOT_TOKEN` أو `API_SECRET` داخل المشغل.
