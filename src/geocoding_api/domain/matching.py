from __future__ import annotations

import re
from dataclasses import dataclass, replace

from .levenshtein import levenshtein, max_edits_for_length
from .types import GeoRecord, MatchType

_MIN_PREFIX_QUERY_LENGTH = 2
# 2-char substrings match half the dataset ("or" → Toronto, New York…)
_MIN_SUBSTRING_QUERY_LENGTH = 3
_TOKEN_SPLIT = re.compile(r"[^a-z0-9]+")


@dataclass(frozen=True, slots=True)
class NameMatch:
    record: GeoRecord
    confidence: float
    match_type: MatchType


@dataclass(frozen=True, slots=True)
class _IndexedEntry:
    record: GeoRecord
    normalized: str
    tokens: tuple[str, ...]


class NameMatcher:
    """Tiered matching: exact → prefix → substring → fuzzy.

    A tier only runs when everything before it came up empty, so a typo can
    never outrank an exact match. Confidence bands don't overlap across tiers.
    """

    def __init__(self, records: list[GeoRecord]) -> None:
        self._entries = [
            _IndexedEntry(
                record=record,
                normalized=record.normalized,
                tokens=tuple(t for t in _TOKEN_SPLIT.split(record.normalized) if t),
            )
            for record in records
        ]
        self._by_normalized: dict[str, list[_IndexedEntry]] = {}
        for entry in self._entries:
            self._by_normalized.setdefault(entry.normalized, []).append(entry)

    @property
    def indexed_names(self) -> int:
        return len(self._by_normalized)

    def search(self, query: str, limit: int) -> list[NameMatch]:
        """query must already be normalized via normalize_name()"""
        if not query:
            return []
        for tier in (self._exact_tier, self._prefix_tier, self._substring_tier, self._fuzzy_tier):
            matches = tier(query)
            if matches:
                return _rank(matches, limit)
        return []

    def _exact_tier(self, query: str) -> list[NameMatch]:
        bucket = self._by_normalized.get(query, [])
        return [NameMatch(record=e.record, confidence=1.0, match_type="exact") for e in bucket]

    def _prefix_tier(self, query: str) -> list[NameMatch]:
        if len(query) < _MIN_PREFIX_QUERY_LENGTH:
            return []
        return [
            NameMatch(
                record=e.record,
                confidence=0.8 + 0.15 * (len(query) / len(e.normalized)),
                match_type="prefix",
            )
            for e in self._entries
            if e.normalized.startswith(query)
        ]

    def _substring_tier(self, query: str) -> list[NameMatch]:
        # token boundaries only: "angeles" matches "los angeles",
        # "or" inside "toronto" does not
        if len(query) < _MIN_SUBSTRING_QUERY_LENGTH:
            return []
        return [
            NameMatch(
                record=e.record,
                confidence=0.6 + 0.2 * (len(query) / len(e.normalized)),
                match_type="substring",
            )
            for e in self._entries
            if any(t.startswith(query) for t in e.tokens)
        ]

    def _fuzzy_tier(self, query: str) -> list[NameMatch]:
        max_edits = max_edits_for_length(len(query))
        if max_edits == 0:
            return []
        matches: list[NameMatch] = []
        for entry in self._entries:
            if abs(len(entry.normalized) - len(query)) > max_edits:
                continue
            distance = levenshtein(query, entry.normalized, max_edits)
            if distance > max_edits:
                continue
            similarity = 1 - distance / max(len(query), len(entry.normalized))
            matches.append(
                NameMatch(record=entry.record, confidence=0.4 + 0.35 * similarity, match_type="fuzzy")
            )
        return matches


def _rank(matches: list[NameMatch], limit: int) -> list[NameMatch]:
    # id last, so ties order the same way on every rebuild
    ordered = sorted(
        matches,
        key=lambda m: (
            -m.confidence,
            -(m.record.population if m.record.population is not None else -1),
            m.record.place_name,
            m.record.id,
        ),
    )
    return [replace(m, confidence=round(m.confidence * 1000) / 1000) for m in ordered[:limit]]
