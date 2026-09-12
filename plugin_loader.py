# -*- coding: utf-8 -*-
"""Generic one-file bot/plugin loader.

Every .py file placed directly in ``Add bot/`` is treated as one bot plugin.
The filename does not matter. A plugin may expose:
  PLUGIN_ID, PLUGIN_NAME, PLUGIN_BUTTON
  open_plugin(call, context)
  handle_callback(call, context)
  handle_message(update, context)
  search(query, context)  # optional, used by the global Search button

No subfolders are required and the loader never starts a second Telegram poller.
"""
from __future__ import annotations
import importlib.util
import logging
import re
from pathlib import Path

log = logging.getLogger("add-bot")
ROOT = Path(__file__).resolve().parent / "Add bot"


def _safe_module_name(path: Path) -> str:
    stem = re.sub(r"[^a-zA-Z0-9_]+", "_", path.stem).strip("_") or "plugin"
    return f"addbot_{stem.lower()}"


def discover_plugins(root: Path | None = None):
    root = root or ROOT
    plugins = {}
    if not root.exists():
        return plugins

    for bot_file in sorted(root.glob("*.py")):
        if bot_file.name.startswith("_") or bot_file.name == "__init__.py":
            continue
        try:
            spec = importlib.util.spec_from_file_location(_safe_module_name(bot_file), bot_file)
            if not spec or not spec.loader:
                continue
            mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)
            plugin_id = str(getattr(mod, "PLUGIN_ID", bot_file.stem)).strip()
            if not plugin_id:
                plugin_id = bot_file.stem
            # Filename is enough. Metadata is optional.
            # If a plugin omitted open_plugin, allow the common single-file hooks.
            if not hasattr(mod, "open_plugin"):
                starter = getattr(mod, "start_plugin", None) or getattr(mod, "menu", None)
                if callable(starter):
                    mod.open_plugin = starter
            if not hasattr(mod, "handle_callback"):
                cb = getattr(mod, "callback", None)
                if callable(cb):
                    mod.handle_callback = cb
            if not hasattr(mod, "handle_message"):
                hm = getattr(mod, "message_handler", None)
                if callable(hm):
                    mod.handle_message = hm
            if plugin_id in plugins:
                plugin_id = f"{plugin_id}_{bot_file.stem}"
            mod.PLUGIN_ID = plugin_id
            mod.PLUGIN_NAME = str(getattr(mod, "PLUGIN_NAME", bot_file.stem))
            mod.PLUGIN_BUTTON = str(getattr(mod, "PLUGIN_BUTTON", f"🤖 {mod.PLUGIN_NAME}"))
            plugins[plugin_id] = mod
            log.info("Loaded bot plugin: %s (%s)", mod.PLUGIN_NAME, bot_file.name)
        except Exception:
            log.exception("Failed loading bot plugin: %s", bot_file)
    return plugins
