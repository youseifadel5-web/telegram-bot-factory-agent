"""واجهة الأفلام — تمرير رقيق لطبقة المصادر الجديدة (حكاية/GoLive).

كانت هذه الوحدة تتصل بالـ API مباشرة بـ aiohttp، وكانت محجوبة من عناوين
مراكز البيانات. الآن كل الطلبات تمر عبر `services.app_sources` (curl_cffi
ببصمة Chrome ثم aiohttp)، بنفس أسماء الدوال القديمة حتى لا تتغير الشاشات.
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from services.app_sources import golive

logger = logging.getLogger(__name__)

BASE_URL = golive.BASE_URL

# نفس مفاتيح التصنيفات القديمة (يحافظ على الشاشات المحفوظة)
CATEGORIES: Dict[str, str] = {
    "arabic_all": golive.MOVIE_CATEGORIES["arabic_all"]["categoryId"],
    "foreign_general": golive.MOVIE_CATEGORIES["foreign_general"]["categoryId"],
    "arabic_movies": golive.MOVIE_CATEGORIES["arabic"]["categoryId"],
    "foreign_movies": golive.MOVIE_CATEGORIES["foreign"]["categoryId"],
}

CATEGORY_LABELS: Dict[str, str] = {
    "arabic_all": "🇸🇦 أفلام عربية",
    "foreign_general": "🌍 أفلام أجنبية",
    "arabic_movies": "🎬 أفلام عربية",
    "foreign_movies": "🎥 أفلام أجنبية",
    "most_viewed": "🔥 الأكثر مشاهدة",
    "top_rated": "⭐ أعلى تقييم",
}

# مفاتيح التصنيفات القديمة → أوضاع golive الجديدة
_MODE_BY_KEY = {
    "arabic_all": "arabic",
    "arabic_movies": "arabic",
    "foreign_general": "foreign",
    "foreign_movies": "foreign",
}


def _movie_row(item: Dict[str, Any]) -> Dict[str, Any]:
    """توحيد شكل الصف كما تتوقعه الشاشات الحالية."""
    item = dict(item or {})
    item.setdefault("kind", "movie")
    item["source"] = item.get("source") or "golive"
    return item


async def search_movies(
    query: str,
    category_key: Optional[str] = None,
    limit: int = 15,
    page: int = 1,
) -> List[Dict]:
    """بحث الأفلام — مع دعم تصنيف اختياري مثل الواجهة القديمة."""
    mode = _MODE_BY_KEY.get(str(category_key or ""))
    if category_key and category_key not in _MODE_BY_KEY:
        mode = None
    rows = await golive.movies(mode=mode, page=page, search=query, limit=limit)
    out = [_movie_row(r) for r in (rows or [])]
    if category_key in CATEGORY_LABELS:
        for m in out:
            m["category"] = CATEGORY_LABELS[category_key]
    return out


async def get_most_viewed(limit: int = 12) -> List[Dict]:
    rows = await golive.movies(mode="popular", limit=limit)
    return [_movie_row(r) for r in (rows or [])]


async def get_top_rated(limit: int = 12) -> List[Dict]:
    rows = await golive.movies(mode="top_rated", limit=limit)
    return [_movie_row(r) for r in (rows or [])]


async def get_by_category(category_key: str, page: int = 1, limit: int = 20) -> List[Dict]:
    mode = _MODE_BY_KEY.get(str(category_key or ""))
    if not mode:
        return []
    rows = await golive.movies(mode=mode, page=page, limit=limit)
    out = [_movie_row(r) for r in (rows or [])]
    label = CATEGORY_LABELS.get(category_key)
    if label:
        for m in out:
            m["category"] = label
    return out


async def get_movie(movie_id: Any) -> Optional[Dict]:
    data = await golive.movie_detail(movie_id)
    if not data:
        return None
    out = dict(data)
    out.setdefault("kind", "movie")
    out["source"] = out.get("source") or "golive"
    return out
