"""حماية من عودة «الأزرار الواقفة».

الحارس القديم في reply_menu_router كان يمنع كل أزرار الكيبورد السفلي عندما
يبقى أي await_* معلّقاً (شاشة بحث مفتوحة ثم يضغط المستخدم زراً) — فتبدو
الأزرار متوقفة. الاختبار يمنع إعادة الحارس ويؤكد وضوح رسائل الرفض.
"""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = (ROOT / "main.py").read_text(encoding="utf-8")


def _fn_body(name: str) -> str:
    start = SRC.index(f"async def {name}(")
    rest = SRC[start:]
    # حتى التعريف التالي على مستوى الوحدة
    nxt = rest.find("\nasync def ", 5)
    return rest[: nxt if nxt > 0 else len(rest)]


def test_menu_router_has_no_await_guard():
    body = _fn_body("reply_menu_router")
    assert 'startswith("await_")' not in body, "الحارس القديم عاد — سيجعل الأزرار تتوقف"
    assert "_dispatch_menu" in body
    assert "clear_workflow_state" in body


def test_dispatch_menu_clears_await_flags():
    body = _fn_body("_dispatch_menu")
    assert 'startswith("await_")' in body  # يُلغى الإدخال المعلّق عند ضغط زر


def test_fake_query_answer_is_visible():
    body = _fn_body("_dispatch_menu")
    assert "reply_text(str(text))" in body, "رسائل الرفض يجب أن تظهر للمستخدم"
