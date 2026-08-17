from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from ..domain.normalize import normalize_name
from ..domain.types import ForwardQuery, ReverseQuery
from ..repository.base import GeocodingRepository, NameSearchHit


@dataclass(frozen=True, slots=True)
class GeocodeOptions:
    limit: int
    radius_km: float


class ForwardStrategy:
    def __init__(self, repository: GeocodingRepository) -> None:
        self._repository = repository

    def execute(self, query: ForwardQuery, options: GeocodeOptions) -> list[dict[str, Any]]:
        hits = self._repository.search_by_name(query.normalized, options.limit)
        if not hits and "," in query.text:
            hits = self._qualified_search(query.text, options.limit)
        return [
            {
                "id": hit.record.id,
                "place_name": hit.record.place_name,
                "country": hit.record.country,
                "latitude": hit.record.latitude,
                "longitude": hit.record.longitude,
                "population": hit.record.population,
                "confidence": hit.confidence,
                "match_type": hit.match_type,
                "distance_km": None,
            }
            for hit in hits
        ]

    def _qualified_search(self, text: str, limit: int) -> list[NameSearchHit]:
        # "Paris, France" — search the part before the comma, then prefer
        # results whose country matches the part after it
        primary_raw, _, qualifier_raw = text.partition(",")
        primary = normalize_name(primary_raw)
        if not primary:
            return []
        candidates = self._repository.search_by_name(primary, limit)
        qualifier = normalize_name(qualifier_raw)
        if qualifier:
            filtered = [
                hit
                for hit in candidates
                if hit.record.country and qualifier in normalize_name(hit.record.country)
            ]
            return filtered or candidates
        return candidates


class ReverseStrategy:
    def __init__(self, repository: GeocodingRepository) -> None:
        self._repository = repository

    def execute(self, query: ReverseQuery, options: GeocodeOptions) -> list[dict[str, Any]]:
        hits = self._repository.nearest(query.lat, query.lon, options.limit, options.radius_km)
        # id breaks distance ties, so equal-distance results are stable
        hits.sort(key=lambda h: (h.distance_km, h.record.id))
        return [
            {
                "id": hit.record.id,
                "place_name": hit.record.place_name,
                "country": hit.record.country,
                "latitude": hit.record.latitude,
                "longitude": hit.record.longitude,
                "population": hit.record.population,
                # linear falloff: 1.0 at the point, ~0 at the radius edge
                # (floored so an included hit is never exactly 0)
                "confidence": _round3(max(0.001, min(1.0, 1 - hit.distance_km / options.radius_km))),
                "match_type": "nearest",
                "distance_km": _round3(hit.distance_km),
            }
            for hit in hits
        ]


def _round3(value: float) -> float:
    return round(value * 1000) / 1000
