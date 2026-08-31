# أوضاع المنصة

المشروع يحتوي الآن على **أربع منصات من خلال بوابة واحدة**: بوابة جديدة اختيارية، وCinema Nova، وOrion Plus، وYouseif Films. المنصات الثلاث الأصلية تُفتح بواجهاتها الكاملة من المشغّل القديم، بينما المنصة الجديدة الموحدة تبقى متاحة كمسار متقدم مستقل.

## الوضع الموصى به

يعمل `run_bot.sh` افتراضيًا على الوضع `legacy`، لأنه يحافظ على واجهة البوت القديم كاملة ولا يحذف أي وظيفة. لتشغيله:

```bash
export BOT_TOKEN='ضع_توكن_البوت_هنا'
export PLATFORM_MODE=legacy
./run_bot.sh
```

## تشغيل المنصة الجديدة الاختيارية

للتجربة المتقدمة شغّل:

```bash
export BOT_TOKEN='ضع_توكن_البوت_هنا'
export PLATFORM_MODE=advanced
./run_bot.sh
```

الوضع `advanced` يستخدم `main.py` والبنية الموحدة الجديدة. لا يتم تشغيل الوضعين في الوقت نفسه باستخدام نفس `BOT_TOKEN` حتى لا يحدث تعارض في Telegram polling.

## المنصات والمصادر

| المنصة | المسار | الحالة |
|---|---|---|
| بوابة المنصة الجديدة | `main.py` مع `PLATFORM_MODE=advanced` | اختيارية ومتقدمة |
| Cinema Nova | `legacy_launcher.py` و`Add bot/Cinema_Nova.py` | واجهة قديمة كاملة |
| Orion Plus | `legacy_launcher.py` و`Add bot/Orion_Plus.py` | واجهة قديمة كاملة |
| Youseif Films | `legacy_launcher.py` و`Add bot/Youseif_Films.py` | واجهة قديمة كاملة |

جميع الأوضاع تستخدم نفس ملفات المصدر الأساسية `cinema_core.py` و`youseif_core.py`، ولا توجد عملية polling ثانية داخل الإضافات.
