# -*- coding: utf-8 -*-
"""Universal media models — UI never depends on raw plugin data."""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional


class MediaType(str, Enum):
    MOVIE = "movie"
    SERIES = "series"
    LIVE = "live"
    EPISODE = "episode"


class Visibility(str, Enum):
    PUBLIC = "public"
    ADMIN_ONLY = "admin_only"
    HIDDEN = "hidden"
    BLOCKED = "blocked"


class PlaybackStatus(str, Enum):
    PLAYABLE = "playable"
    PARTIALLY_PLAYABLE = "partially_playable"
    INVALID = "invalid"
    UNAVAILABLE = "unavailable"
    TIMEOUT = "timeout"
    REQUIRES_AUTH = "requires_auth"


@dataclass
class MediaSource:
    source_id: str
    external_id: str
    url: Optional[str] = None
    quality: Optional[str] = None
    media_format: Optional[str] = None  # mp4, hls, dash, ts
    extra: Dict[str, Any] = field(default_factory=dict)


@dataclass
class MediaItem:
    id: str
    universal_id: str
    title: str
    type: MediaType
    original_title: str = ""
    year: Optional[int] = None
    countries: List[str] = field(default_factory=list)
    languages: List[str] = field(default_factory=list)
    genres: List[str] = field(default_factory=list)
    overview: str = ""
    poster: str = ""
    rating: float = 0.0
    source_ids: List[str] = field(default_factory=list)
    sources: List[MediaSource] = field(default_factory=list)
    visibility: Visibility = Visibility.PUBLIC
    blocked: bool = False
    extra: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "universal_id": self.universal_id,
            "title": self.title,
            "original_title": self.original_title,
            "type": self.type.value if isinstance(self.type, MediaType) else self.type,
            "year": self.year,
            "countries": self.countries,
            "languages": self.languages,
            "genres": self.genres,
            "overview": self.overview,
            "poster": self.poster,
            "rating": self.rating,
            "source_ids": self.source_ids,
            "visibility": self.visibility.value if isinstance(self.visibility, Visibility) else self.visibility,
            "blocked": self.blocked,
        }


@dataclass
class Episode:
    id: str
    series_id: str
    season: int
    number: int
    title: str = ""
    duration: str = ""
    sources: List[MediaSource] = field(default_factory=list)


@dataclass
class Season:
    number: int
    episode_count: int = 0
    episodes: List[Episode] = field(default_factory=list)


@dataclass
class SeriesDetails:
    item: MediaItem
    seasons: List[Season] = field(default_factory=list)


@dataclass
class SearchQuery:
    text: str = ""
    media_type: Optional[str] = None
    genres: List[str] = field(default_factory=list)
    countries: List[str] = field(default_factory=list)
    year_min: Optional[int] = None
    year_max: Optional[int] = None
    sort: str = "relevance"  # relevance | newest | rating | popular
    limit: int = 30
    page: int = 0


@dataclass
class QualityOption:
    label: str  # 1080p
    url: str
    bandwidth: Optional[int] = None
    status: PlaybackStatus = PlaybackStatus.PLAYABLE
