import json

import pytest

from geocoding_api.domain.types import GeoIndexArtifact
from geocoding_api.ingest.pipeline import (
    MAX_DROPPED_EXAMPLES,
    JsonArtifactSink,
    ListSink,
    run_ingest,
    stream_ingest,
)

DIRTY_CSV = "\n".join(
    [
        "id,place_name,latitude,longitude,country,population",
        "1,Good City,10.0,20.0,Testland,1000",
        "2,,11.0,21.0,Testland,",
        "3,Bad Lat,95.0,10.0,Testland,5",
        "4,Bad Lon,10.0,-190.0,Testland,5",
        "5,Not Numbers,abc,def,Testland,5",
        '6,  Padded  Name ,12.5,22.5,Testland,"1,234"',
        "1,Dup Id,13.0,23.0,Testland,10",
        "7,Good City,10.00001,20.00001,Testland,999",
        '8,"Quoted, Name",14.0,24.0,Testland,42',
    ]
)

result = run_ingest(DIRTY_CSV, "fixture")
artifact = result.artifact
report = result.report


def test_keeps_only_valid_unique_records():
    assert report.rows_read == 9
    assert report.kept == 3
    assert artifact.record_count == 3
    assert [r.id for r in artifact.records] == ["1", "6", "8"]


def test_drops_invalid_rows_with_line_numbers_and_reasons():
    assert len(report.dropped) == 5
    reasons = [f"{d.line}:{d.reason}" for d in report.dropped]
    assert "place_name" in reasons[0]
    assert "latitude" in reasons[1]
    assert "longitude" in reasons[2]
    assert "latitude" in reasons[3]
    assert "duplicate id" in reasons[4]


def test_merges_near_duplicate_records_same_name_within_11m():
    assert report.merged == 1


def test_cleans_whitespace_and_parses_thousand_separated_population():
    padded = next(r for r in artifact.records if r.id == "6")
    assert padded.place_name == "Padded Name"
    assert padded.normalized == "padded name"
    assert padded.population == 1234


def test_preserves_commas_inside_quoted_names():
    quoted = next(r for r in artifact.records if r.id == "8")
    assert quoted.place_name == "Quoted, Name"


def test_stamps_artifact_metadata():
    assert artifact.version == 1
    assert artifact.source == "fixture"
    assert artifact.built_at[:4].isdigit() and "T" in artifact.built_at


def test_dedup_uses_real_distance_not_grid_rounding():
    header = "id,place_name,latitude,longitude"
    # 2.2 m apart but on either side of a 4-decimal rounding boundary: merged
    straddling = run_ingest(
        f"{header}\n1,Spot,10.00004,20.0\n2,Spot,10.00006,20.0", "dedup"
    )
    assert straddling.report.kept == 1
    assert straddling.report.merged == 1
    # ~12.5 m apart inside the same rounding cell: kept as two places
    far_same_cell = run_ingest(
        f"{header}\n1,Corner,9.99996,19.99996\n2,Corner,10.00004,20.00004", "dedup"
    )
    assert far_same_cell.report.kept == 2
    assert far_same_cell.report.merged == 0


def test_rejects_scientific_notation_coordinates():
    # the query classifier only accepts plain decimals; ingest matches it
    result = run_ingest(
        "id,place_name,latitude,longitude\n1,X,1e2,20.0", "sci"
    )
    assert result.report.kept == 0
    assert "latitude" in result.report.dropped[0].reason


def test_drops_names_that_normalize_to_empty():
    result = run_ingest(
        "id,place_name,latitude,longitude\n1,'',10.0,20.0", "empty-name"
    )
    assert result.report.kept == 0
    assert "normalizes to empty" in result.report.dropped[0].reason


def test_strips_utf8_bom_from_the_header():
    bom_csv = "\ufeffid,place_name,latitude,longitude\n9,Bom City,1.0,2.0"
    bom_result = run_ingest(bom_csv, "bom")
    assert bom_result.report.kept == 1
    assert bom_result.artifact.records[0].place_name == "Bom City"


def test_rejects_csvs_missing_required_columns():
    with pytest.raises(ValueError, match="place_name"):
        run_ingest("id,name\n1,x", "bad")
    with pytest.raises(ValueError, match="empty"):
        run_ingest("", "empty")


def test_artifact_round_trips_through_dict():
    assert GeoIndexArtifact.from_dict(artifact.to_dict()) == artifact


def test_streaming_from_a_file_produces_identical_records(tmp_path):
    csv_file = tmp_path / "in.csv"
    csv_file.write_text(DIRTY_CSV, encoding="utf-8")
    out = tmp_path / "index.json"

    sink = JsonArtifactSink(out, source="fixture")
    with csv_file.open(newline="", encoding="utf-8") as lines:
        streamed_report = stream_ingest(lines, sink)
    assert sink.finalize() == 3

    streamed = GeoIndexArtifact.from_dict(json.loads(out.read_text(encoding="utf-8")))
    assert streamed.records == artifact.records
    assert streamed.record_count == 3
    assert streamed_report.kept == report.kept
    assert streamed_report.merged == report.merged
    assert streamed_report.dropped == report.dropped
    assert not out.with_suffix(".json.tmp").exists()


def test_caps_dropped_examples_but_counts_everything():
    rows = ["id,place_name,latitude,longitude"]
    rows.extend(f"{i},,10.0,20.0" for i in range(60))
    capped = run_ingest("\n".join(rows), "cap")
    assert capped.report.dropped_total == 60
    assert len(capped.report.dropped) == MAX_DROPPED_EXAMPLES
    assert capped.report.kept == 0


def test_sink_abort_leaves_no_files(tmp_path):
    out = tmp_path / "index.json"
    sink = JsonArtifactSink(out, source="abort")
    stream_ingest(iter(["id,place_name,latitude,longitude", "1,X,1.0,2.0"]), sink)
    sink.abort()
    assert not out.exists()
    assert not out.with_suffix(".json.tmp").exists()


def test_list_sink_matches_wrapper_output():
    sink = ListSink()
    import io

    stream_ingest(io.StringIO(DIRTY_CSV), sink)
    assert sink.records == artifact.records
