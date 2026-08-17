from geocoding_api.domain.matching import NameMatcher
from geocoding_api.domain.normalize import normalize_name
from geocoding_api.domain.types import GeoRecord


def record(record_id: str, name: str, population: int | None = None) -> GeoRecord:
    return GeoRecord(
        id=record_id,
        place_name=name,
        country=None,
        latitude=0,
        longitude=0,
        population=population,
        normalized=normalize_name(name),
    )


matcher = NameMatcher(
    [
        record("1", "Paris", 2_148_000),
        record("2", "Paris", 24_839),
        record("3", "Parisville", 500),
        record("4", "Kraków", 779_115),
        record("5", "Los Angeles", 3_990_000),
        record("6", "San Jose", 1_030_000),
    ]
)


def test_returns_all_exact_matches_ranked_by_population():
    results = matcher.search("paris", 10)
    assert [r.record.id for r in results] == ["1", "2"]
    assert all(r.match_type == "exact" and r.confidence == 1 for r in results)


def test_short_circuits_an_exact_hit_suppresses_prefix_matches():
    results = matcher.search("paris", 10)
    assert not any(r.record.id == "3" for r in results)


def test_falls_through_to_prefix_matches():
    results = matcher.search("par", 10)
    assert sorted(r.record.id for r in results) == ["1", "2", "3"]
    assert all(r.match_type == "prefix" for r in results)
    assert all(0.8 <= r.confidence <= 0.95 for r in results)


def test_falls_through_to_substring_matches():
    results = matcher.search("angeles", 10)
    assert len(results) == 1
    assert results[0].record.id == "5"
    assert results[0].match_type == "substring"


def test_falls_through_to_fuzzy_matches_within_the_edit_budget():
    results = matcher.search("krakov", 10)
    assert len(results) == 1
    assert results[0].record.id == "4"
    assert results[0].match_type == "fuzzy"


def test_gives_no_fuzzy_budget_to_very_short_queries():
    assert matcher.search("pq", 10) == []


def test_two_character_queries_cannot_match_mid_word():
    # "ng" appears inside "los angeles" but is far too loose to act on
    assert matcher.search("ng", 10) == []


def test_substring_requires_a_token_boundary():
    assert matcher.search("angeles", 10)[0].record.id == "5"
    assert matcher.search("ngeles", 10) == []


def test_respects_the_limit_after_ranking():
    results = matcher.search("par", 1)
    assert len(results) == 1
    assert results[0].record.id == "1"


def test_returns_empty_for_empty_input_and_misses():
    assert matcher.search("", 10) == []
    assert matcher.search("zzzzzz", 10) == []
