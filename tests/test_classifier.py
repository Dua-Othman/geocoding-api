import pytest

from geocoding_api.domain.classifier import classify_query
from geocoding_api.domain.errors import QueryError
from geocoding_api.domain.types import ForwardQuery, ReverseQuery


def expect_query_error(value: str, code: str) -> None:
    with pytest.raises(QueryError) as exc_info:
        classify_query(value)
    assert exc_info.value.code == code
    assert exc_info.value.status_code == 400


def test_routes_plain_text_to_forward_with_normalization():
    assert classify_query("  PARIS ") == ForwardQuery(text="PARIS", normalized="paris")


def test_routes_text_containing_digits_to_forward():
    assert classify_query("10 Downing Street").type == "forward"


def test_routes_two_comma_separated_numbers_to_reverse_as_lat_lon():
    assert classify_query("48.8566,2.3522") == ReverseQuery(lat=48.8566, lon=2.3522)


def test_tolerates_whitespace_around_coordinate_tokens():
    assert classify_query(" 48.8566 , 2.3522 ") == ReverseQuery(lat=48.8566, lon=2.3522)


def test_accepts_integer_coordinates():
    assert classify_query("48,2") == ReverseQuery(lat=48.0, lon=2.0)


def test_accepts_boundary_coordinates():
    assert classify_query("-90,180") == ReverseQuery(lat=-90.0, lon=180.0)


def test_treats_a_single_number_as_forward():
    assert classify_query("-33.9").type == "forward"


def test_treats_three_comma_separated_numbers_as_forward():
    assert classify_query("1,2,3").type == "forward"


def test_treats_unsupported_coordinate_notations_as_forward():
    assert classify_query("48.8566;2.3522").type == "forward"
    assert classify_query("N48.85,E2.35").type == "forward"


def test_space_separated_numbers_stay_forward():
    # Deliberate: "10 20" is more likely a textual fragment (house number,
    # postal code) than a coordinate pair; comma is the unambiguous signal.
    assert classify_query("48.8566 2.3522").type == "forward"


def test_accepts_a_parenthesized_coordinate_pair():
    assert classify_query("(48.8566, 2.3522)") == ReverseQuery(lat=48.8566, lon=2.3522)
    assert classify_query("( 48 , 2 )") == ReverseQuery(lat=48.0, lon=2.0)
    expect_query_error("(91,0)", "INVALID_COORDINATES")


def test_parenthesized_text_stays_forward():
    assert classify_query("(paris)").type == "forward"


def test_folds_fullwidth_comma_and_digits():
    assert classify_query("48.8566，2.3522") == ReverseQuery(lat=48.8566, lon=2.3522)
    assert classify_query("４８，２") == ReverseQuery(lat=48.0, lon=2.0)


def test_folds_unicode_minus():
    assert classify_query("−48.8,2.3") == ReverseQuery(lat=-48.8, lon=2.3)


def test_non_ascii_digits_stay_forward():
    # Arabic-Indic digits would pass float() but are not documented behaviour
    assert classify_query("٤٨,٢").type == "forward"


def test_rejects_numeric_pairs_with_out_of_range_latitude():
    expect_query_error("91,0", "INVALID_COORDINATES")
    expect_query_error("-90.1,0", "INVALID_COORDINATES")


def test_rejects_numeric_pairs_with_out_of_range_longitude():
    expect_query_error("0,181", "INVALID_COORDINATES")
    expect_query_error("0,-180.5", "INVALID_COORDINATES")


def test_rejects_empty_and_whitespace_only_queries():
    expect_query_error("", "EMPTY_QUERY")
    expect_query_error("   ", "EMPTY_QUERY")
