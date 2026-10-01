"""Hekaya TV adapter.

المصدر الحقيقي لـ "حكاية TV" هو واجهة GoLive في §1 من المواصفة. الموديول ده
بيبقى مجرد مُغلّف رقيق حوالين services.app_sources.golive، وبيحافظ على نفس
أسماء ودوال الواجهة القديمة (get_movies/get_series/search/get_details) عشان
هاندلرز السينما/الأفلام/المسلسلات تشتغل فوراً ببيانات حقيقية.

مفيش طلب شبكة وقت الاستيراد، وكل الدوال فشل ناعم (ترجّع [] / None).
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from services.app_sources import golive

logger = logging.getLogger(__name__)

# نفس مضيف §1 (اتساقاً للتوافق مع cinema.py اللي بيستورد الاسم ده)
HEKAYA_BASE = golive.BASE_URL
# أسماء مسارات قديمة محفوظة للتوافق فقط (مش بنستخدمها في الطلبات دلوقتي)
HEKAYA_SEARCH_PATH = "/search"
HEKAYA_MOVIES_PATH = "/content/movies"
HEKAYA_SERIES_PATH = "/content/series"

# sort → mode mapping للأوضاع القديمة
_SORT_TO_MODE = {
    "most": "popular",
    "popular": "popular",
    "top": "top_rated",
    "top_rated": "top_rated",
    "latest": None,
    "new": None,
}


def _mode_for(sort: Optional[str], kw: Dict[str, Any]) -> Optional[str]:
    if kw.get("mode") is not None:
        return kw.get("mode")
    return _SORT_TO_MODE.get(str(sort or "").lower())


async def get_movies(page: int = 1, limit: int = 10, sort: str = "most", **kw) -> List[Dict]:
    """قائمة أفلام من GoLive — نفس التوقيع القديم."""
    mode = _mode_for(sort, kw)
    return await golive.movies(mode=mode, page=page, search=kw.get("search"), limit=limit)


async def get_series(page: int = 1, limit: int = 10, **kw) -> List[Dict]:
    """قائمة مسلسلات من GoLive — نفس التوقيع القديم."""
    mode = _mode_for(kw.get("sort"), kw)
    return await golive.series(mode=mode, page=page, search=kw.get("search"), limit=limit)


async def search(query: str, page: int = 1, limit: int = 10) -> List[Dict]:
    """بحث موحّد (أفلام + مسلسلات) — نفس التوقيع القديم."""
    if len((query or "").strip()) < 2:
        return []
    return await golive.search(query.strip(), page=page, limit=limit)


async def get_details(item_id: int, kind: str = "movie") -> Optional[Dict]:
    """تفاصيل فيلم/مسلسل — نفس التوقيع القديم."""
    if kind in ("series", "anime"):
        return await golive.series_detail(item_id)
    return await golive.movie_detail(item_id)
