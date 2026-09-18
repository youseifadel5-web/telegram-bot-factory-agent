#!/usr/bin/env python3
"""KataBump launcher.

- Checks installed packages before any pip install
- Skips packages already present (import OR metadata version)
- Never reinstalls unnecessarily
- Binary wheels only on low-memory hosts
"""
from __future__ import annotations

import importlib
import importlib.metadata
import os
import re
import site
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
os.chdir(ROOT)

CRITICAL = (
    ("telegram", "python-telegram-bot==21.6"),
    ("dotenv", "python-dotenv==1.0.1"),
    ("aiohttp", "aiohttp==3.14.3"),
    ("aiosqlite", "aiosqlite==0.20.0"),
    ("psutil", "psutil==6.1.0"),
    ("boto3", "boto3==1.35.36"),
    ("cryptography", "cryptography>=42.0.0"),
)

SOFT = (
    ("pyrogram", "pyrogram==2.0.106"),
)

OPTIONAL_DEPS = (
    ("tgcrypto", "tgcrypto==1.2.5"),
)

DEPENDENCIES = CRITICAL + SOFT

DIST_NAME = {
    "telegram": "python-telegram-bot",
    "dotenv": "python-dotenv",
    "aiohttp": "aiohttp",
    "aiosqlite": "aiosqlite",
    "psutil": "psutil",
    "boto3": "boto3",
    "cryptography": "cryptography",
    "pyrogram": "pyrogram",
    "tgcrypto": "tgcrypto",
}


def _refresh_import_paths() -> None:
    try:
        user_site = site.getusersitepackages()
        if user_site and user_site not in sys.path:
            sys.path.insert(0, user_site)
            site.addsitedir(user_site)
    except Exception:
        pass
    try:
        importlib.invalidate_caches()
    except Exception:
        pass


def _parse_req(requirement: str):
    m = re.match(r"^([A-Za-z0-9_.-]+)\s*==\s*([^\s]+)$", requirement.strip())
    if m:
        return m.group(1), m.group(2)
    return requirement.strip(), None


def _dist_version(dist_name: str):
    try:
        return importlib.metadata.version(dist_name)
    except Exception:
        pass
    try:
        return importlib.metadata.version(dist_name.replace("_", "-"))
    except Exception:
        return None


def _can_import(module: str) -> bool:
    _refresh_import_paths()
    try:
        importlib.import_module(module)
        return True
    except Exception:
        return False


def is_installed(module: str, requirement: str) -> bool:
    """Skip pip if package already present (metadata or import)."""
    dist = DIST_NAME.get(module, _parse_req(requirement)[0])
    want_ver = _parse_req(requirement)[1]
    have_ver = _dist_version(dist)

    if have_ver:
        # Already installed on disk — do NOT reinstall
        if want_ver is None or have_ver == want_ver or have_ver.split(".")[0] == (want_ver or "").split(".")[0]:
            if _can_import(module):
                return True
            print(
                f"  skip {dist}: already installed ({have_ver}) — no reinstall",
                flush=True,
            )
            return True

    if _can_import(module):
        return True
    return False


def missing_packages(deps=DEPENDENCIES):
    missing = []
    for module, requirement in deps:
        if is_installed(module, requirement):
            print(f"  OK {module} (already present)", flush=True)
        else:
            missing.append((module, requirement))
    return missing


def _pip_install(requirements) -> int:
    if not requirements:
        return 0
    base = [
        sys.executable, "-m", "pip", "install",
        "--disable-pip-version-check",
        "--no-cache-dir",
        "--only-binary=:all:",
        "--prefer-binary",
    ]
    attempts = [
        base + requirements,
        base + ["--user"] + requirements,
        base + ["--break-system-packages"] + requirements,
        base + ["--user", "--break-system-packages"] + requirements,
    ]
    last_code = 1
    for cmd in attempts:
        try:
            result = subprocess.run(cmd, cwd=ROOT, check=False)
            last_code = result.returncode
            _refresh_import_paths()
            if last_code == 0:
                return 0
        except Exception as exc:
            print(f"pip attempt error: {exc}", flush=True)
            last_code = 1
    return last_code


def install_missing() -> None:
    print("Checking installed packages...", flush=True)
    missing = missing_packages()
    if not missing:
        print("Dependencies OK — nothing to install.", flush=True)
        return

    reqs = [r for _, r in missing]
    print("Installing only missing:", ", ".join(reqs), flush=True)
    code = _pip_install(reqs)
    _refresh_import_paths()

    still_critical = [
        req for mod, req in CRITICAL if not is_installed(mod, req)
    ]
    still_soft = [
        req for mod, req in SOFT if not is_installed(mod, req)
    ]

    if still_critical:
        raise SystemExit(
            "Critical dependency missing after install: "
            + ", ".join(still_critical)
            + f" (pip exit={code})."
        )

    if still_soft:
        print(
            "WARNING: soft deps still unavailable:",
            ", ".join(still_soft),
            "— bot starts; large-file Pyrogram may be limited.",
            flush=True,
        )
    else:
        print("Dependencies ready.", flush=True)


def install_optional() -> None:
    for module, requirement in OPTIONAL_DEPS:
        if is_installed(module, requirement):
            print(f"  OK optional {module}", flush=True)
            continue
        print(f"Optional install: {requirement}", flush=True)
        try:
            _pip_install([requirement])
        except Exception as e:
            print(f"Optional skip {requirement}: {e}", flush=True)


def ensure_dirs() -> None:
    for rel in (
        "data/tmp",
        "data/iptv",
        "data/upload_state",
        "logs",
        "backup",
        "bin",
    ):
        (ROOT / rel).mkdir(parents=True, exist_ok=True)


def main() -> None:
    ensure_dirs()
    install_missing()
    try:
        install_optional()
    except Exception:
        pass
    os.execv(sys.executable, [sys.executable, str(ROOT / "main.py")])


if __name__ == "__main__":
    main()
