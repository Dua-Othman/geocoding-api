from __future__ import annotations

import json
from pathlib import Path

from ..domain.kdtree import SpatialPoint, SphericalKdTree
from ..domain.matching import NameMatcher
from ..domain.types import GeoIndexArtifact, GeoRecord
from .base import NameSearchHit, NearestHit, RepositoryStats


class InMemoryGeocodingRepository:
    def __init__(self, artifact: GeoIndexArtifact) -> None:
        self._matcher = NameMatcher(artifact.records)
        self._tree: SphericalKdTree[GeoRecord] = SphericalKdTree(
            [SpatialPoint(lat=r.latitude, lon=r.longitude, item=r) for r in artifact.records]
        )
        self._meta = RepositoryStats(
            records=len(artifact.records),
            built_at=artifact.built_at,
            source=artifact.source,
        )

    @classmethod
    def from_file(cls, path: str | Path) -> "InMemoryGeocodingRepository":
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        return cls(GeoIndexArtifact.from_dict(data))

    def search_by_name(self, normalized_query: str, limit: int) -> list[NameSearchHit]:
        return [
            NameSearchHit(record=m.record, confidence=m.confidence, match_type=m.match_type)
            for m in self._matcher.search(normalized_query, limit)
        ]

    def nearest(self, lat: float, lon: float, limit: int, max_radius_km: float) -> list[NearestHit]:
        return [
            NearestHit(record=hit.item, distance_km=hit.distance_km)
            for hit in self._tree.nearest(lat, lon, limit, max_radius_km)
        ]

    def stats(self) -> RepositoryStats:
        return self._meta
