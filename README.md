# Local APK/API Analyzer

محلل محلي وحتمي لتطبيقات Android التي يملك المستخدم حق تحليلها. يقرأ ملفات **APK** و**HAR** دون اتصال بخدمات ذكاء اصطناعي أو APIs خارجية، ويخرج خريطة أدلة قابلة لإعادة الإنتاج تشمل عناوين الخوادم، المسارات، معاملات الطلب، الرؤوس، عينات JSON، مخططات الاستجابة، تعليقات Retrofit، والمكتبات الأصلية وإشارات التوقيع الظاهرة داخلها.

> لا ينفذ هذا المشروع تجاوز SSL Pinning، ولا يفك تشفير اتصالات، ولا يخمن صلاحية endpoint. التحليل العميق يتطلب تأكيداً صريحاً عبر `--owned`، وتبقى القيم المستخرجة من نصوص APK مرشحات حتى تظهر في HAR أو في تعليق ثابت واضح.

## التشغيل

يتطلب Python 3.11 أو أحدث ولا يحتاج إلى تثبيت مكتبات خارجية:

```bash
python apk_api_analyzer.py --owned --apk app.apk --har traffic.har --out report.json
```

يمكن تحليل ملف واحد فقط:

```bash
python apk_api_analyzer.py --owned --apk app.apk --out apk-report.json
python apk_api_analyzer.py --owned --har traffic.har --out har-report.json
```

التقرير JSON منظم إلى مصدر APK ومصدر HAR وقسم `reconciliation`. المسار الموجود في HAR يعد **مؤكداً بالملاحظة**، بينما المسار الموجود كنص أو تعليق داخل APK يعد **مرشحاً** ما لم تثبته حركة الشبكة. عينات JSON لا تُنشأ افتراضياً؛ تُستخرج فقط من response bodies الموجودة في HAR.

## ما الذي يستخرجه؟

| المصدر | النتائج |
|---|---|
| HAR | Base URLs، كل URL ملاحظ، method، path، query parameters، request headers، status codes، عينات response JSON، ومخطط JSON متداخل |
| APK | SHA-256، الملفات الداخلية، مرشحات URLs والمسارات، تعليقات Retrofit، المكتبات `.so`، وسلاسل مرتبطة بـ HMAC/SHA/nonce/signature/Iron/OkHttp/Retrofit |
| المطابقة | فصل الأدلة المؤكدة عن مرشحات APK، مع منع تحويل النصوص إلى endpoints مؤكدة |

## حدود مقصودة

البرنامج أداة تحليل ثابت وسلبي. لا يرسل طلبات إلى الخوادم، ولا يضع توكنات أو أسراراً داخل المستودع، ولا يبني روابط مشاهدة أو ترويسات توقيع من التخمين. إذا كان التطبيق يعتمد على مكتبة أصلية أو توقيعاً ديناميكياً، يعرض البرنامج مؤشرات النصوص والملفات الأصلية لتوجيه المراجعة اليدوية المصرح بها، من دون ادعاء استخراج خوارزمية غير موجودة في الأدلة.

## الاختبار

```bash
python -m unittest discover -s tests -v
```

يعمل GitHub Actions على Python 3.11 و3.12، ويجري الاختبارات وفحص compilation فقط. لا يحتاج workflow إلى Secrets.

## بيئة Windows وOpenCode

يوجد Workflow يدوي باسم **Windows OpenCode Workspace**. من تبويب **Actions** اختر هذا الـ Workflow ثم **Run workflow**. يمكنك ترك الأمر الافتراضي لفحص الملفات، أو تمرير أمر PowerShell غير تفاعلي عبر الحقل `command`، واختيار تشغيل اختبارات المحلل.

يعمل الـ Workflow على `windows-latest`، ويثبت Node.js 22 وOpenCode عبر npm أثناء الـ run فقط. لا يستخدم Docker، ولا يحتاج إلى Codespaces أو خادم دائم. إذا أضفت Secret باسم `OPENCODE_API_KEY`، يمرره Workflow كمتغير بيئة مقنّع؛ لا توجد مفاتيح افتراضية داخل المستودع.

| ما هو متاح | القيد |
|---|---|
| Windows runner، PowerShell، Git، Python، Node.js، OpenCode، وفحص ملفات المشروع | الجهاز مؤقت وينتهي بعد انتهاء الـ Workflow |
| تثبيت أدوات إضافية أثناء الـ run | لا توجد جلسة سطح مكتب رسومية أو Terminal دائم يمكن إبقاؤه مفتوحًا من GitHub Actions |
| تشغيل أوامر بناء واختبار وتحليل ورفع logs كـ Artifacts | الأوامر التفاعلية التي تنتظر إدخالًا يدويًا لا تناسب GitHub Actions |

لذلك فهذا الحل مناسب لتشغيل OpenCode والأوامر الآلية وتحليل ملفات المشروع. أما فتح تطبيق Android بواجهة رسومية أو التحكم المستمر في سطح مكتب Windows فيحتاج جهاز Windows فعليًا أو runner ذاتيًا يديره المستخدم، وليس GitHub-hosted runner مؤقتًا.
