"""Template for a future bot module.

Keep this module independent. Do not start polling here.
"""

BOT_PREFIX = "newbot:"


def handle_callback(data: str) -> bool:
    """Return True only when this module owns the callback."""
    return bool(data and data.startswith(BOT_PREFIX))


def handle_text(text: str) -> bool:
    """Optional text entry point. Return True when consumed."""
    return False
