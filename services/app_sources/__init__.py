"""طبقة مصادر المحتوى المَنقولة من تطبيق YouseifPlayer.

ده سجل صغير بيجمّع المصادر وبيكشف تشغيل/إيقاف كل واحد زي FaselGateways في
التطبيق (googlefire / faselhd / hikaye / custom). مفيش أي طلب شبكة وقت الاستيراد.
"""
from __future__ import annotations

from typing import Any, Dict

from . import channels
from . import fasel
from . import firebase_catalog
from . import golive

# السجل: الاسم → الموديول
SOURCES: Dict[str, Any] = {
    "golive": golive,
    "fasel": fasel,
    "firebase": firebase_catalog,
    "channels": channels,
}

# 2.3 — بوابة كل مصدر (نفس أسماء FaselGateways.defaults)
GATEWAYS: Dict[str, bool] = {
    "googlefire": True,   # Google Firebase (جوجل فاير)
    "faselhd": True,      # فاصل HD
    "hikaye": True,       # حكاية TV
    "custom": True,       # محتواي الشخصي
}

# ربط كل مصدر ببوابته
SOURCE_GATEWAY: Dict[str, str] = {
    "golive": "hikaye",
    "fasel": "faselhd",
    "firebase": "googlefire",
    "channels": "custom",
}


def enabled(name: str) -> bool:
    """هل المصدر ده مفعّل؟"""
    gateway = SOURCE_GATEWAY.get(name, name)
    return bool(GATEWAYS.get(gateway, True))


def set_enabled(gateway: str, value: bool) -> None:
    """يفعّل/يوقف بوابة."""
    GATEWAYS[gateway] = bool(value)


def enabled_sources() -> Dict[str, Any]:
    """المصادر المفعّلة بس."""
    return {name: module for name, module in SOURCES.items() if enabled(name)}


__all__ = [
    "SOURCES", "GATEWAYS", "SOURCE_GATEWAY", "enabled", "set_enabled",
    "enabled_sources", "golive", "fasel", "firebase_catalog", "channels",
]
