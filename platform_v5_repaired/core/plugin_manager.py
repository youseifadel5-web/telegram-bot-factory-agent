# -*- coding: utf-8 -*-
"""Auto-discover plugins from plugins/ — failure isolation per plugin."""
from __future__ import annotations

import importlib
import logging
import os
import time
from pathlib import Path
from typing import Dict, List, Optional

from core.plugin_base import MediaSourcePlugin

log = logging.getLogger("plugins")

PLUGIN_ROOT = Path(__file__).resolve().parent.parent / "plugins"


class PluginManager:
    def __init__(self, root: Optional[Path] = None):
        self.root = root or PLUGIN_ROOT
        self.plugins: Dict[str, MediaSourcePlugin] = {}
        self.health: Dict[str, Dict] = {}

    def discover(self) -> Dict[str, MediaSourcePlugin]:
        self.plugins.clear()
        if not self.root.exists():
            log.warning("Plugin root missing: %s", self.root)
            return self.plugins
        # Production: never load mock/test content unless explicitly enabled
        enable_test = os.getenv("ENABLE_TEST_SOURCE", "").strip().lower() in ("1", "true", "yes")
        for entry in sorted(self.root.iterdir()):
            if not entry.is_dir() or entry.name.startswith("_"):
                continue
            if entry.name == "test_source" and not enable_test:
                log.info("[PLUGIN] skip test_source (ENABLE_TEST_SOURCE not set)")
                continue
            init_py = entry / "__init__.py"
            plugin_py = entry / "plugin.py"
            module_path = None
            if plugin_py.exists():
                module_path = f"plugins.{entry.name}.plugin"
            elif init_py.exists():
                module_path = f"plugins.{entry.name}"
            else:
                continue
            try:
                mod = importlib.import_module(module_path)
                # reload if already imported
                importlib.reload(mod)
                plugin_cls = getattr(mod, "Plugin", None) or getattr(mod, "plugin_class", None)
                instance = None
                if plugin_cls and callable(plugin_cls):
                    instance = plugin_cls()
                elif hasattr(mod, "create_plugin") and callable(mod.create_plugin):
                    instance = mod.create_plugin()
                if instance is None or not isinstance(instance, MediaSourcePlugin):
                    log.warning("Skip %s: no MediaSourcePlugin", entry.name)
                    continue
                pid = getattr(instance, "id", entry.name) or entry.name
                self.plugins[pid] = instance
                log.info("[PLUGIN] %s loaded (%s)", getattr(instance, "name", pid), pid)
            except Exception:
                log.exception("[PLUGIN] Failed loading %s — isolated", entry.name)
        return self.plugins

    def get(self, plugin_id: str) -> Optional[MediaSourcePlugin]:
        return self.plugins.get(plugin_id)

    def all(self) -> List[MediaSourcePlugin]:
        return list(self.plugins.values())

    async def health_all(self) -> Dict[str, Dict]:
        out = {}
        for pid, p in self.plugins.items():
            t0 = time.time()
            try:
                h = await p.health_check()
                h = h or {}
                h.setdefault("ok", True)
                h["latency_ms"] = int((time.time() - t0) * 1000)
            except Exception as e:
                h = {"ok": False, "error": str(e)[:120], "latency_ms": int((time.time() - t0) * 1000)}
            out[pid] = h
            self.health[pid] = h
        return out
