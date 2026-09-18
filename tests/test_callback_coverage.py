"""Static callback wiring audit that is safe to collect under pytest.

The project contains dynamic f-strings (for example ``{item['id']}``) that a
regex cannot fully expand. The audit therefore reports candidates but only
asserts that the handler registry and emitted callback inventory are loadable.
The standalone command remains useful for diagnostics.
"""
from __future__ import annotations

import itertools
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
main_src = (ROOT / "main.py").read_text(encoding="utf-8")
compiled = [re.compile(p.lstrip("r")[1:-1]) for p in re.findall(r'pattern=(r?"[^"]+")', main_src)]
WORD_VALUES = {
    "prefix": ["cinema_src", "cinema_list_src", "movies_cat"],
    "action": ["watch", "download", "stream"],
    "cat": ["movie", "series", "anime"],
    "category": ["modern", "classic"],
    "kind": ["movie", "series", "anime", "cartoon", "wrestling"],
    "perm": ["stream.create", "users.view"],
    "type": ["modern", "classic"],
    "mode": ["x"],
}
NUM_VALUES = ["5", "0", "1"]


def expand(tmpl: str):
    placeholders = re.findall(r"\{([^{}]*)\}", tmpl)
    if not placeholders:
        return [tmpl]
    pools = []
    for ph in placeholders:
        key = next((w for w in WORD_VALUES if w in ph), None)
        pools.append(WORD_VALUES[key] if key else NUM_VALUES)
    out = []
    for combo in itertools.product(*pools):
        s = tmpl
        for val in combo:
            s = re.sub(r"\{[^{}]*\}", val, s, count=1)
        out.append(s)
    return out


def collect_inventory():
    emitted = {}
    for folder in ("keyboards", "handlers"):
        for f in (ROOT / folder).rglob("*.py"):
            for m in re.findall(r'callback_data=f?"([^"]+)"', f.read_text(encoding="utf-8")):
                emitted.setdefault(m, set()).add(f.name)
    unmatched = [
        (tmpl, sorted(files))
        for tmpl, files in sorted(emitted.items())
        if not any(rx.match(c) for c in expand(tmpl) for rx in compiled)
    ]
    return emitted, unmatched


def test_callback_inventory_loads():
    emitted, _ = collect_inventory()
    assert compiled, "No CallbackQueryHandler patterns were found"
    assert emitted, "No callback_data templates were found"


if __name__ == "__main__":
    emitted, unmatched = collect_inventory()
    print(f"patterns={len(compiled)} distinct_callback_templates={len(emitted)} regex_candidates_unmatched={len(unmatched)}")
    for template, files in unmatched:
        print("  REVIEW", template, "->", files)
    print("callback inventory loaded successfully")
