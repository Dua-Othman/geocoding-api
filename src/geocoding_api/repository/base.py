from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from ..domain.types import GeoRecord, MatchType


@dataclass(frozen=True, slots=True)
class NameSearchHit:
    record: GeoRecord
    confidence: float
    match_type: MatchType


@dataclass(frozen=True, slots=True)
class NearestHit:
    record: GeoRecord
    distance_km: float


@dataclass(frozen=True, slots=True)
class RepositoryStats:
    records: int
    built_at: str
    source: str


class GeocodingRepository(Protocol):
    """Storage port — swap the in-memory adapter for PostGIS or Elasticsearch
    later without touching the service layer."""

    def search_by_name(self, normalized_query: str, limit: int) -> list[NameSearchHit]: ...

    def nearest(
        self, lat: float, lon: float, limit: int, max_radius_km: float
    ) -> list[NearestHit]: ...

    def stats(self) -> RepositoryStats: ...
