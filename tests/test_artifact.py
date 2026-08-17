import pytest

from geocoding_api.domain.types import GeoIndexArtifact


def artifact_dict(**overrides) -> dict:
    record = {
        "id": "1",
        "place_name": "X",
        "country": None,
        "latitude": 1.0,
        "longitude": 2.0,
        "population": None,
        "normalized": "x",
    }
    record.update(overrides)
    return {
        "version": 1,
        "built_at": "2026-08-17T00:00:00+00:00",
        "source": "test",
        "record_count": 1,
        "records": [record],
    }


def test_accepts_a_valid_artifact():
    artifact = GeoIndexArtifact.from_dict(artifact_dict())
    assert artifact.record_count == 1
    assert artifact.records[0].id == "1"


def test_rejects_unknown_version():
    data = artifact_dict()
    data["version"] = 2
    with pytest.raises(ValueError, match="version"):
        GeoIndexArtifact.from_dict(data)


def test_rejects_record_count_mismatch():
    data = artifact_dict()
    data["record_count"] = 5
    with pytest.raises(ValueError, match="record_count"):
        GeoIndexArtifact.from_dict(data)


def test_rejects_string_population():
    # a producer that JSON-encodes numbers as strings must fail at load,
    # not crash ranking later with a TypeError
    with pytest.raises(ValueError, match="population"):
        GeoIndexArtifact.from_dict(artifact_dict(population="123"))


def test_rejects_string_coordinates():
    with pytest.raises(ValueError, match="latitude"):
        GeoIndexArtifact.from_dict(artifact_dict(latitude="48.85"))


def test_rejects_out_of_range_coordinates():
    with pytest.raises(ValueError, match="latitude"):
        GeoIndexArtifact.from_dict(artifact_dict(latitude=95.0))
    with pytest.raises(ValueError, match="longitude"):
        GeoIndexArtifact.from_dict(artifact_dict(longitude=-181.0))


def test_rejects_nan_coordinates():
    with pytest.raises(ValueError, match="latitude"):
        GeoIndexArtifact.from_dict(artifact_dict(latitude=float("nan")))


def test_rejects_boolean_population():
    with pytest.raises(ValueError, match="population"):
        GeoIndexArtifact.from_dict(artifact_dict(population=True))


def test_rejects_empty_id_and_name():
    with pytest.raises(ValueError, match="id"):
        GeoIndexArtifact.from_dict(artifact_dict(id=""))
    with pytest.raises(ValueError, match="place_name"):
        GeoIndexArtifact.from_dict(artifact_dict(place_name=""))
