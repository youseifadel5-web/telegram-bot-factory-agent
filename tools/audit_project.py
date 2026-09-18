#!/usr/bin/env python3
"""Static KataBump architecture audit. No network, secrets, or shell execution."""
from __future__ import annotations
import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SKIP = {".git", "__pycache__", "bin", ".venv", "venv"}
CORE = {"start_stream", "stop_stream", "restart_stream", "create_stream", "search_movies", "search_series", "get_watch_links", "get_movies", "get_series"}

def pyfiles():
    for p in ROOT.rglob("*.py"):
        if not any(part in SKIP for part in p.parts):
            yield p

def audit():
    funcs = {}
    callbacks = []
    duplicate_dict_keys = []
    errors = []
    for p in pyfiles():
        rel = str(p.relative_to(ROOT))
        try:
            tree = ast.parse(p.read_text(encoding="utf-8"), filename=rel)
        except SyntaxError as e:
            errors.append(f"syntax:{rel}:{e}")
            continue
        for n in ast.walk(tree):
            if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.col_offset == 0:
                funcs.setdefault(n.name, []).append(rel)
            if isinstance(n, ast.Call) and isinstance(n.func, ast.Name) and n.func.id == "InlineKeyboardButton":
                for kw in n.keywords:
                    if kw.arg == "callback_data" and isinstance(kw.value, ast.Constant) and isinstance(kw.value.value, str):
                        callbacks.append((kw.value.value, rel))
            if isinstance(n, ast.Dict):
                seen = {}
                for k in n.keys:
                    if isinstance(k, ast.Constant) and isinstance(k.value, str):
                        seen[k.value] = seen.get(k.value, 0) + 1
                duplicate_dict_keys.extend((rel, k, c) for k, c in seen.items() if c > 1)
    duplicates = {k: v for k, v in funcs.items() if len(v) > 1 and k in CORE}
    counts = {}
    for c, _ in callbacks:
        counts[c] = counts.get(c, 0) + 1
    duplicate_callbacks = {k: v for k, v in counts.items() if v > 1}
    print("KataBump architecture audit")
    print("python_files=", len(list(pyfiles())))
    print("syntax_errors=", len(errors))
    print("duplicate_core_functions=", duplicates)
    print("duplicate_literal_callbacks=", duplicate_callbacks)
    print("duplicate_dict_keys=", duplicate_dict_keys)
    return 1 if errors else 0

if __name__ == "__main__":
    raise SystemExit(audit())
