from __future__ import annotations

import math
import time
from dataclasses import dataclass
from typing import Any

from ..domain.classifier import classify_query
from ..domain.types import OSM_ATTRIBUTION, ClassifiedQuery, ForwardQuery
from ..repository.base import GeocodingRepository
from .strategies import ForwardStrategy, GeocodeOptions, ReverseStrategy


@dataclass(frozen=True, slots=True)
class GeocodingServiceConfig:
    default_limit: int
    max_limit: int
    default_radius_km: float
    max_radius_km: float


class GeocodingService:
    """Facade: classify, clamp options, run the right strategy, shape the
    response. No HTTP in here."""

    def __init__(self, repository: GeocodingRepository, config: GeocodingServiceConfig) -> None:
        self._config = config
        self._forward = ForwardStrategy(repository)
        self._reverse = ReverseStrategy(repository)

    def geocode(
        self,
        raw: str,
        limit: int | None = None,
        radius_km: float | None = None,
    ) -> dict[str, Any]:
        """raises QueryError for empty input or out-of-range coordinates"""
        started = time.perf_counter()
        query = classify_query(raw)
        effective_limit = _clamp(
            math.trunc(limit if limit is not None else self._config.default_limit),
            1,
            self._config.max_limit,
        )
        effective_radius = _clamp(
            radius_km if radius_km is not None else self._config.default_radius_km,
            math.ulp(0.0),
            self._config.max_radius_km,
        )
        options = GeocodeOptions(limit=int(effective_limit), radius_km=effective_radius)

        if isinstance(query, ForwardQuery):
            results = self._forward.execute(query, options)
        else:
            results = self._reverse.execute(query, options)

        return {
            "query": _echo(raw, query),
            "results": results,
            "metadata": {
                "count": len(results),
                "limit": options.limit,
                "radius_km": options.radius_km if query.type == "reverse" else None,
                "took_ms": round((time.perf_counter() - started) * 1000, 2),
                "attribution": OSM_ATTRIBUTION,
            },
        }


def _echo(raw: str, query: ClassifiedQuery) -> dict[str, Any]:
    if isinstance(query, ForwardQuery):
        return {"raw": raw, "type": "forward", "normalized": query.normalized}
    return {"raw": raw, "type": "reverse", "lat": query.lat, "lon": query.lon, "convention": "lat,lon"}


def _clamp(value: float, minimum: float, maximum: float) -> float:
    return min(max(value, minimum), maximum)
