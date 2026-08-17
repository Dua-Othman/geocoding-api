from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from geocoding_api.config import load_config
from geocoding_api.ingest.pipeline import run_ingest
from geocoding_api.repository.in_memory import InMemoryGeocodingRepository
from geocoding_api.server import build_app

DATA_FILE = Path(__file__).resolve().parent.parent / "data" / "geodata.csv"


@pytest.fixture(scope="module")
def context() -> dict:
    result = run_ingest(DATA_FILE.read_text(encoding="utf-8"), "data/geodata.csv")
    assert result.report.dropped == []
    app = build_app(
        InMemoryGeocodingRepository(result.artifact),
        load_config({}),
    )
    return {"client": TestClient(app), "records": result.artifact.record_count}


@pytest.fixture()
def client(context: dict) -> TestClient:
    return context["client"]


class TestForward:
    def test_returns_ranked_exact_matches_for_an_ambiguous_name(self, client: TestClient):
        res = client.get("/geocode", params={"q": "paris"})
        assert res.status_code == 200
        body = res.json()
        assert body["query"]["type"] == "forward"
        assert body["query"]["normalized"] == "paris"
        assert len(body["results"]) == 2
        first = body["results"][0]
        assert (first["place_name"], first["country"], first["match_type"], first["confidence"]) == (
            "Paris", "France", "exact", 1,
        )
        assert body["results"][1]["country"] == "United States"
        assert "OpenStreetMap" in body["metadata"]["attribution"]

    def test_is_case_and_diacritic_insensitive(self, client: TestClient):
        res = client.get("/geocode", params={"q": "  ZÜRICH "})
        assert res.json()["results"][0]["place_name"] == "Zürich"
        res = client.get("/geocode", params={"q": "sao paulo"})
        assert res.json()["results"][0]["place_name"] == "São Paulo"

    def test_falls_back_to_prefix_matching(self, client: TestClient):
        body = client.get("/geocode", params={"q": "lond"}).json()
        assert [r["place_name"] for r in body["results"]] == ["London", "London"]
        assert body["results"][0]["match_type"] == "prefix"

    def test_falls_back_to_substring_matching(self, client: TestClient):
        body = client.get("/geocode", params={"q": "angeles"}).json()
        assert body["results"][0]["place_name"] == "Los Angeles"
        assert body["results"][0]["match_type"] == "substring"

    def test_falls_back_to_fuzzy_matching_on_typos(self, client: TestClient):
        body = client.get("/geocode", params={"q": "pariss"}).json()
        assert body["results"][0]["place_name"] == "Paris"
        assert body["results"][0]["match_type"] == "fuzzy"
        assert body["results"][0]["confidence"] < 1

    def test_city_country_queries_filter_by_country(self, client: TestClient):
        body = client.get("/geocode", params={"q": "Paris, France"}).json()
        assert [r["country"] for r in body["results"]] == ["France"]
        body = client.get("/geocode", params={"q": "London, Canada"}).json()
        assert [r["country"] for r in body["results"]] == ["Canada"]

    def test_unmatched_country_qualifier_falls_back_to_all_matches(self, client: TestClient):
        body = client.get("/geocode", params={"q": "Paris, TX"}).json()
        assert len(body["results"]) == 2

    def test_hyphenated_names_match_exactly(self, client: TestClient):
        body = client.get("/geocode", params={"q": "los-angeles"}).json()
        assert body["results"][0]["place_name"] == "Los Angeles"
        assert body["results"][0]["match_type"] == "exact"

    def test_two_letter_fragments_do_not_match_mid_word(self, client: TestClient):
        assert client.get("/geocode", params={"q": "or"}).status_code == 404

    def test_honors_the_limit_parameter(self, client: TestClient):
        body = client.get("/geocode", params={"q": "san", "limit": 1}).json()
        assert len(body["results"]) == 1
        assert body["metadata"]["limit"] == 1

    def test_returns_404_with_a_structured_body_when_nothing_matches(self, client: TestClient):
        res = client.get("/geocode", params={"q": "zzzzzz"})
        assert res.status_code == 404
        body = res.json()
        assert body["error"]["code"] == "NO_MATCH"
        assert body["query"]["type"] == "forward"
        assert body["metadata"]["count"] == 0
        assert "OpenStreetMap" in body["metadata"]["attribution"]

    def test_accepts_a_parenthesized_coordinate_pair(self, client: TestClient):
        res = client.get("/geocode", params={"q": "(48.8566, 2.3522)"})
        assert res.status_code == 200
        assert res.json()["query"]["type"] == "reverse"

    def test_accepts_fullwidth_comma_coordinates(self, client: TestClient):
        res = client.get("/geocode", params={"q": "48.8566，2.3522"})
        assert res.status_code == 200
        assert res.json()["query"]["type"] == "reverse"


class TestReverse:
    def test_returns_the_nearest_place_with_distance_and_echo(self, client: TestClient):
        res = client.get("/geocode", params={"q": "48.8566,2.3522"})
        assert res.status_code == 200
        body = res.json()
        assert body["query"] == {
            "raw": "48.8566,2.3522",
            "type": "reverse",
            "lat": 48.8566,
            "lon": 2.3522,
            "convention": "lat,lon",
        }
        first = body["results"][0]
        assert (first["place_name"], first["country"], first["match_type"]) == (
            "Paris", "France", "nearest",
        )
        assert first["distance_km"] < 1
        assert first["confidence"] > 0.99
        assert body["metadata"]["radius_km"] == 300

    def test_swapped_lon_lat_input_finds_nothing(self, client: TestClient):
        # lon,lat for Paris happens to be valid lat,lon in the Indian Ocean.
        assert client.get("/geocode", params={"q": "2.3522,48.8566"}).status_code == 404

    def test_enforces_the_default_radius_cap(self, client: TestClient):
        res = client.get("/geocode", params={"q": "0,-30"})
        assert res.status_code == 404
        body = res.json()
        assert body["error"]["code"] == "NO_MATCH"
        assert "radius" in body["error"]["message"]

    def test_accepts_a_larger_radius_override(self, client: TestClient):
        res = client.get("/geocode", params={"q": "0,-30", "radius": 5000})
        assert res.status_code == 200
        body = res.json()
        assert len(body["results"]) > 0
        assert body["metadata"]["radius_km"] == 5000


class TestErrors:
    def test_rejects_out_of_range_coordinates_with_400(self, client: TestClient):
        res = client.get("/geocode", params={"q": "91,0"})
        assert res.status_code == 400
        assert res.json()["error"]["code"] == "INVALID_COORDINATES"
        assert client.get("/geocode", params={"q": "0,181"}).status_code == 400

    def test_rejects_whitespace_only_queries_with_400(self, client: TestClient):
        res = client.get("/geocode", params={"q": "   "})
        assert res.status_code == 400
        assert res.json()["error"]["code"] == "EMPTY_QUERY"

    def test_rejects_a_missing_q_parameter_with_400(self, client: TestClient):
        res = client.get("/geocode")
        assert res.status_code == 400
        assert res.json()["error"]["code"] == "BAD_REQUEST"

    def test_rejects_an_out_of_bounds_limit_with_400(self, client: TestClient):
        assert client.get("/geocode", params={"q": "paris", "limit": 999}).status_code == 400

    def test_rejects_overlong_queries_with_400(self, client: TestClient):
        res = client.get("/geocode", params={"q": "a" * 300})
        assert res.status_code == 400
        assert res.json()["error"]["code"] == "BAD_REQUEST"

    def test_rejects_a_duplicate_q_parameter(self, client: TestClient):
        res = client.get("/geocode?q=paris&q=london")
        assert res.status_code == 400
        assert res.json()["error"]["code"] == "BAD_REQUEST"

    def test_unhandled_errors_return_the_json_envelope(self, context: dict):
        from geocoding_api.repository.base import RepositoryStats

        class BrokenRepo:
            def search_by_name(self, normalized_query, limit):
                raise RuntimeError("boom")

            def nearest(self, lat, lon, limit, max_radius_km):
                raise RuntimeError("boom")

            def stats(self):
                return RepositoryStats(records=0, built_at="", source="")

        app = build_app(BrokenRepo(), load_config({}))
        broken = TestClient(app, raise_server_exceptions=False)
        res = broken.get("/geocode", params={"q": "paris"})
        assert res.status_code == 500
        assert res.json()["error"]["code"] == "INTERNAL_ERROR"


class TestHardening:
    def test_rate_limit_returns_429(self, context: dict):
        result = run_ingest(DATA_FILE.read_text(encoding="utf-8"), "data/geodata.csv")
        app = build_app(
            InMemoryGeocodingRepository(result.artifact),
            load_config({"RATE_LIMIT": "2"}),
        )
        limited = TestClient(app)
        assert limited.get("/geocode", params={"q": "paris"}).status_code == 200
        assert limited.get("/geocode", params={"q": "paris"}).status_code == 200
        res = limited.get("/geocode", params={"q": "paris"})
        assert res.status_code == 429
        assert res.json()["error"]["code"] == "RATE_LIMITED"
        # other endpoints are not limited
        assert limited.get("/health").status_code == 200

    def test_docs_off_hides_docs_and_stats(self, context: dict):
        result = run_ingest(DATA_FILE.read_text(encoding="utf-8"), "data/geodata.csv")
        app = build_app(
            InMemoryGeocodingRepository(result.artifact),
            load_config({"DOCS": "off"}),
        )
        quiet = TestClient(app)
        assert quiet.get("/docs").status_code == 404
        assert quiet.get("/openapi.json").status_code == 404
        assert quiet.get("/stats").status_code == 404
        assert quiet.get("/geocode", params={"q": "paris"}).status_code == 200


class TestOperational:
    def test_reports_health(self, client: TestClient, context: dict):
        res = client.get("/health")
        assert res.status_code == 200
        body = res.json()
        assert body["status"] == "ok"
        assert body["records"] == context["records"]

    def test_reports_stats(self, client: TestClient, context: dict):
        res = client.get("/stats")
        assert res.status_code == 200
        body = res.json()
        assert body["records"] == context["records"]
        assert "geodata" in body["source"]
        assert body["memory_rss_bytes"] > 0
