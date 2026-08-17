from __future__ import annotations

import math
from dataclasses import asdict, dataclass, field
from typing import Any, Literal

MatchType = Literal["exact", "prefix", "substring", "fuzzy", "nearest"]

OSM_ATTRIBUTION = "Data © OpenStreetMap contributors, ODbL 1.0 (sample extract)"


@dataclass(frozen=True, slots=True)
class GeoRecord:
    id: str
    place_name: str
    country: str | None
    latitude: float
    longitude: float
    population: int | None
    #: calculated at ingest time — lowercase, whitespace stripped
    normalized: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @staticmethod
    def from_dict(data: dict[str, Any]) -> "GeoRecord":
        # the index file may come from another pipeline (Java, the TS twin),
        # so check every field instead of trusting it and crashing later
        record_id = data.get("id")
        if not isinstance(record_id, str) or not record_id:
            raise ValueError("id must be a non-empty string")
        place_name = data.get("place_name")
        if not isinstance(place_name, str) or not place_name:
            raise ValueError(f'record "{record_id}": place_name must be a non-empty string')
        normalized = data.get("normalized")
        if not isinstance(normalized, str) or not normalized:
            raise ValueError(f'record "{record_id}": normalized must be a non-empty string')
        country = data.get("country")
        if country is not None and not isinstance(country, str):
            raise ValueError(f'record "{record_id}": country must be a string or null')
        latitude = _checked_coordinate(record_id, "latitude", data.get("latitude"), 90)
        longitude = _checked_coordinate(record_id, "longitude", data.get("longitude"), 180)
        population = data.get("population")
        if population is not None and (
            not isinstance(population, int) or isinstance(population, bool) or population < 0
        ):
            raise ValueError(f'record "{record_id}": population must be a non-negative integer or null')
        return GeoRecord(
            id=record_id,
            place_name=place_name,
            country=country,
            latitude=latitude,
            longitude=longitude,
            population=population,
            normalized=normalized,
        )


@dataclass(frozen=True, slots=True)
class GeoIndexArtifact:
    version: int
    built_at: str
    source: str
    record_count: int
    records: list[GeoRecord] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "version": self.version,
            "built_at": self.built_at,
            "source": self.source,
            "record_count": self.record_count,
            "records": [r.to_dict() for r in self.records],
        }

    @staticmethod
    def from_dict(data: dict[str, Any]) -> "GeoIndexArtifact":
        if data.get("version") != 1:
            raise ValueError(f"unsupported index version {data.get('version')!r} (expected 1)")
        raw_records = data.get("records")
        if not isinstance(raw_records, list):
            raise ValueError("records must be a list")
        count = data.get("record_count")
        if count != len(raw_records):
            raise ValueError(f"record_count says {count} but there are {len(raw_records)} records")
        records: list[GeoRecord] = []
        for i, raw in enumerate(raw_records):
            if not isinstance(raw, dict):
                raise ValueError(f"record {i} is not an object")
            try:
                records.append(GeoRecord.from_dict(raw))
            except ValueError as error:
                raise ValueError(f"record {i}: {error}") from None
        return GeoIndexArtifact(
            version=1,
            built_at=str(data.get("built_at", "")),
            source=str(data.get("source", "")),
            record_count=len(records),
            records=records,
        )


def _checked_coordinate(record_id: str, name: str, value: Any, bound: float) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f'record "{record_id}": {name} must be a number')
    number = float(value)
    if not math.isfinite(number) or number < -bound or number > bound:
        raise ValueError(f'record "{record_id}": {name} {value!r} is out of range [±{bound:g}]')
    return number


@dataclass(frozen=True, slots=True)
class ForwardQuery:
    text: str
    normalized: str
    type: Literal["forward"] = "forward"


@dataclass(frozen=True, slots=True)
class ReverseQuery:
    lat: float
    lon: float
    type: Literal["reverse"] = "reverse"


ClassifiedQuery = ForwardQuery | ReverseQuery
