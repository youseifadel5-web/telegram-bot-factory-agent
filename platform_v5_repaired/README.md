# Unified Arabic Media Platform V3

منصة تيليجرام عربية موحّدة: مكتبات متعددة + AI + فحص تشغيل + إدارة حظر.

## التشغيل

```bash
pip install -r requirements.txt
cp .env.example .env   # املأ BOT_TOKEN و ADMIN_IDS
python main.py
```

## الأسرار (من البيئة فقط)

| المتغير | مطلوب |
|---------|--------|
| `BOT_TOKEN` | نعم |
| `ADMIN_IDS` / `ADMIN_ID` | للوحة الأدمن |
| `OPENROUTER_API_KEY` | اختياري — AI |
| `OPENROUTER_MODEL` | اختياري |

البوت يعمل **بدون** OpenRouter (بحث عادي + heuristic).

## الهيكل

```
main.py                 # نقطة الدخول — python-telegram-bot فقط
core/                   # نماذج، بحث، دمج، حظر، plugins
ai/                     # OpenRouter + intent + recommender
playback/               # فحص HLS/MP4/DASH + جودات
database/               # SQLite + فهارس
plugins/                # اكتشاف تلقائي
  youseif/
  cinema_nova/
  orion_plus/
  test_source/          # مثال لإضافة مصدر جديد
bot/keyboards/          # واجهة عربية
tests/
```

## إضافة مصدر جديد

1. أنشئ `plugins/my_source/plugin.py`
2. نفّذ `MediaSourcePlugin` (`search`, `get_details`, …)
3. أعد التشغيل — يظهر في اللوج: `[PLUGIN] ... loaded`

لا تعديل على نواة البحث.

## الميزات

- مكتبة عربية: أفلام / مسلسلات / أنواع / دول
- بحث موحّد بدون تكرار (بوستر + تعريف أولاً)
- اطلب من AI — فهم نية + بحث حقيقي + اقتراحات مشابهة
- مشاهدة بعد فحص المصدر والجودات
- أدمن: مصادر، حظر فردي/جماعي، سجل، كاش، AI stats
- عزل أخطاء كل plugin

## اختبار سريع

```bash
PYTHONPATH=. python -c "from core.plugin_manager import PluginManager; p=PluginManager(); p.discover(); print(list(p.plugins))"
```

## GitHub Actions

A dedicated `Telegram Bot` workflow is included at `.github/workflows/telegram-bot.yml` and contains `workflow_dispatch`, so the **Run workflow** button appears in GitHub Actions after the workflow is committed to the default branch.

Add these repository secrets:

- `BOT_TOKEN`
- `ADMIN_IDS` (optional for normal operation, required for admin controls)
- `OPENROUTER_API_KEY` (optional)
- `OPENROUTER_MODEL` (optional)

The workflow can run the bot or execute the V3 verification suite. GitHub-hosted runners are temporary and should not be treated as permanent 24/7 bot hosting.
