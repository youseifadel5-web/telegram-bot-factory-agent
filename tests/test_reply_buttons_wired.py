"""حماية من الأزرار الميتة: كل زر في كيبورد الرد له مدخل في REPLY_MAP.

زر بلا مدخل = ضغطته لا تفعل شيئاً (كان يحدث مع «🎞 المسلسلات»).
الاختبار يقرأ المصادر نصياً بلا استيراد telegram (يعمل في بيئة الاختبار).
"""
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _reply_map_keys():
    src = (ROOT / "handlers" / "start.py").read_text(encoding="utf-8")
    block = src.split("REPLY_MAP = {", 1)[1].split("\n}", 1)[0]
    return set(re.findall(r'"([^"]+)"\s*:', block))


def _reply_button_labels():
    """كل أزرار كيبورد الرد (KeyboardButton وليس InlineKeyboardButton)."""
    out = {}
    for p in ROOT.rglob("*.py"):
        txt = p.read_text(encoding="utf-8", errors="ignore")
        for m in re.finditer(r'(?<!Inline)KeyboardButton\(\s*"([^"]+)"([^)]*)\)', txt):
            label, rest = m.group(1), m.group(2)
            if "request_contact" in rest or "request_location" in rest:
                continue  # أزرار مشاركة الجهة/الموقع تُعالج بمعالج خاص
            out[label] = f"{p.relative_to(ROOT)}"
    return out


def _resolves(label, keys):
    t = label.strip()
    if t in keys:
        return True
    if len(t) > 2 and t[1] == " ":
        return t[2:].strip() in keys
    return False


def test_every_reply_button_is_wired():
    keys = _reply_map_keys()
    labels = _reply_button_labels()
    assert labels, "لم يتم العثور على أزرار كيبورد رد"
    dead = {lab: loc for lab, loc in labels.items() if not _resolves(lab, keys)}
    assert not dead, f"أزرار بلا مدخل في REPLY_MAP: {dead}"


def test_series_label_is_wired():
    keys = _reply_map_keys()
    assert _resolves("🎞 المسلسلات", keys)
    assert _resolves("🎬 الأفلام", keys)
    assert _resolves("📺 IPTV", keys)
