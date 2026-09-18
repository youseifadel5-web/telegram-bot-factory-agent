"""Plugin loader — drop modules in plugins/ with register(app) function."""
import importlib
import logging
import pkgutil
from pathlib import Path

logger = logging.getLogger(__name__)
PLUGINS_DIR = Path(__file__).resolve().parent


def load_plugins(application=None):
    """Discover and load plugins. Each plugin may define register(app)."""
    loaded = []
    for mod in pkgutil.iter_modules([str(PLUGINS_DIR)]):
        if mod.name.startswith("_"):
            continue
        try:
            module = importlib.import_module(f"plugins.{mod.name}")
            if hasattr(module, "register") and application is not None:
                module.register(application)
            loaded.append(mod.name)
            logger.info("Plugin loaded: %s", mod.name)
        except Exception as e:
            logger.warning("Plugin %s failed: %s", mod.name, e)
    return loaded
