from __future__ import annotations

import csv
import io
import json
import math
import os
import re
from collections.abc import Iterable, Iterator
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Protocol

from ..domain.geo import haversine_km
from ..domain.normalize import collapse_whitespace, normalize_name
from ..domain.types import GeoIndexArtifact, GeoRecord

_REQUIRED_COLUMNS = ("id", "place_name", "latitude", "longitude")
_OPTIONAL_COLUMNS = ("country", "population")
_SEPARATORS = re.compile(r"[,\s]")
# same ASCII decimal rule as the query classifier, so both sides agree
_DECIMAL = re.compile(r"[+-]?(\d+(\.\d+)?|\.\d+)", re.ASCII)

# keep this many dropped-row examples; the totals still count everything
MAX_DROPPED_EXAMPLES = 50

# two rows with the same normalized name this close are one place
DEDUP_RADIUS_KM = 0.011  # ~11 m


@dataclass(frozen=True, slots=True)
class DroppedRow:
    line: int
    reason: str


@dataclass(slots=True)
class IngestReport:
    rows_read: int = 0
    kept: int = 0
    merged: int = 0
    dropped_total: int = 0
    #: first MAX_DROPPED_EXAMPLES only — an unbounded list would defeat streaming
    dropped: list[DroppedRow] = field(default_factory=list)


@dataclass(frozen=True, slots=True)
class IngestResult:
    artifact: GeoIndexArtifact
    report: IngestReport


class RecordSink(Protocol):
    """where kept records go — a list, a JSON file, a database later"""

    def write(self, record: GeoRecord) -> None: ...


def stream_ingest(lines: Iterable[str], sink: RecordSink) -> IngestReport:
    """Streaming core: validate → normalize → dedupe, one row in memory at a
    time. Kept records go straight to the sink, never into a list."""
    report = IngestReport()
    header: list[str] | None = None
    col: dict[str, int] = {}
    seen_ids: set[str] = set()
    # kept coordinates bucketed by (name, grid cell) for real-distance dedup.
    # This and seen_ids are the only state that grows; past ~10M rows dedup
    # belongs in the DB sink.
    dedup_index: dict[tuple[str, int, int], list[tuple[float, float]]] = {}
    row_number = 0

    def drop(line: int, reason: str) -> None:
        report.dropped_total += 1
        if len(report.dropped) < MAX_DROPPED_EXAMPLES:
            report.dropped.append(DroppedRow(line=line, reason=reason))

    for row in csv.reader(_strip_bom(lines)):
        if not any(f.strip() for f in row):
            continue
        row_number += 1

        if header is None:
            header = [h.strip().lower() for h in row]
            for column in _REQUIRED_COLUMNS:
                if column not in header:
                    raise ValueError(f'Missing required column "{column}"')
            col = {
                name: header.index(name)
                for name in (*_REQUIRED_COLUMNS, *_OPTIONAL_COLUMNS)
                if name in header
            }
            continue

        report.rows_read += 1
        line = row_number  # header was row 1

        if len(row) != len(header):
            drop(line, f"expected {len(header)} columns, got {len(row)}")
            continue

        record_id = row[col["id"]].strip()
        if not record_id:
            drop(line, "missing id")
            continue
        if record_id in seen_ids:
            drop(line, f'duplicate id "{record_id}"')
            continue

        place_name = collapse_whitespace(row[col["place_name"]])
        if not place_name:
            drop(line, "missing place_name")
            continue

        latitude = _parse_coordinate(row[col["latitude"]])
        if latitude is None or latitude < -90 or latitude > 90:
            drop(line, f'invalid latitude "{row[col["latitude"]].strip()}"')
            continue
        longitude = _parse_coordinate(row[col["longitude"]])
        if longitude is None or longitude < -180 or longitude > 180:
            drop(line, f'invalid longitude "{row[col["longitude"]].strip()}"')
            continue

        normalized = normalize_name(place_name)
        if not normalized:
            drop(line, f'place_name "{place_name}" normalizes to empty')
            continue
        # merge policy is first-row-wins: earlier rows have already been
        # streamed to the sink, so a later duplicate cannot replace them
        if _is_duplicate(dedup_index, normalized, latitude, longitude):
            report.merged += 1
            continue

        seen_ids.add(record_id)
        country_i = col.get("country")
        pop_i = col.get("population")
        sink.write(
            GeoRecord(
                id=record_id,
                place_name=place_name,
                country=(collapse_whitespace(row[country_i]) or None) if country_i is not None else None,
                latitude=latitude,
                longitude=longitude,
                population=_parse_population(row[pop_i]) if pop_i is not None else None,
                normalized=normalized,
            )
        )
        report.kept += 1

    if header is None:
        raise ValueError("CSV input is empty")
    return report


def run_ingest(csv_text: str, source: str) -> IngestResult:
    """In-memory convenience for small inputs and tests — same pipeline."""
    sink = ListSink()
    report = stream_ingest(io.StringIO(csv_text), sink)
    artifact = GeoIndexArtifact(
        version=1,
        built_at=_now_iso(),
        source=source,
        record_count=len(sink.records),
        records=sink.records,
    )
    return IngestResult(artifact=artifact, report=report)


class ListSink:
    """collects records in memory — fine for tests and small files"""

    def __init__(self) -> None:
        self.records: list[GeoRecord] = []

    def write(self, record: GeoRecord) -> None:
        self.records.append(record)


class JsonArtifactSink:
    """Streams the artifact to disk: header first, one record per line,
    record_count last (JSON keys are unordered, so the schema is unchanged).
    Writes to a temp file and renames on finalize — a crash never leaves a
    half-written index behind."""

    def __init__(self, path: str | Path, source: str) -> None:
        self._path = Path(path)
        self._tmp = self._path.with_suffix(self._path.suffix + ".tmp")
        self._count = 0
        self._file = self._tmp.open("w", encoding="utf-8")
        self._file.write(
            "{\n"
            '  "version": 1,\n'
            f'  "built_at": {json.dumps(_now_iso())},\n'
            f'  "source": {json.dumps(source)},\n'
            '  "records": ['
        )

    def write(self, record: GeoRecord) -> None:
        prefix = ",\n    " if self._count else "\n    "
        self._file.write(prefix + json.dumps(record.to_dict(), ensure_ascii=False))
        self._count += 1

    def finalize(self) -> int:
        closing = "\n  ],\n" if self._count else "],\n"
        self._file.write(closing + f'  "record_count": {self._count}\n}}\n')
        self._file.close()
        os.replace(self._tmp, self._path)
        return self._count

    def abort(self) -> None:
        if not self._file.closed:
            self._file.close()
        self._tmp.unlink(missing_ok=True)


def _strip_bom(lines: Iterable[str]) -> Iterator[str]:
    # Excel exports often start with a BOM; strip it or "id" never matches
    iterator = iter(lines)
    try:
        first = next(iterator)
    except StopIteration:
        return
    yield first.lstrip("\ufeff")
    yield from iterator


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _is_duplicate(
    index: dict[tuple[str, int, int], list[tuple[float, float]]],
    normalized: str,
    lat: float,
    lon: float,
) -> bool:
    """True distance check (not grid rounding): a duplicate is the same name
    within DEDUP_RADIUS_KM. The grid only narrows which kept points to compare
    against; if not a duplicate, the point is added to the index."""
    cell_lat = round(lat * 1e4)
    cell_lon = round(lon * 1e4) % 3_600_000
    # longitude cells shrink towards the poles, so widen the scan there
    meters_per_lon_cell = max(111_320 * abs(math.cos(math.radians(lat))) / 1e4, 1e-9)
    span = min(int(DEDUP_RADIUS_KM * 1000 / meters_per_lon_cell) + 1, 100)
    for d_lat in (-1, 0, 1):
        for d_lon in range(-span, span + 1):
            bucket = index.get((normalized, cell_lat + d_lat, (cell_lon + d_lon) % 3_600_000))
            if not bucket:
                continue
            for kept_lat, kept_lon in bucket:
                if haversine_km(lat, lon, kept_lat, kept_lon) <= DEDUP_RADIUS_KM:
                    return True
    index.setdefault((normalized, cell_lat, cell_lon), []).append((lat, lon))
    return False


def _parse_coordinate(raw: str) -> float | None:
    trimmed = raw.strip()
    if not trimmed or not _DECIMAL.fullmatch(trimmed):
        return None
    return float(trimmed)


def _parse_population(raw: str) -> int | None:
    cleaned = _SEPARATORS.sub("", raw)
    if not cleaned:
        return None
    try:
        value = float(cleaned)
    except ValueError:
        return None
    return round(value) if math.isfinite(value) and value >= 0 else None
