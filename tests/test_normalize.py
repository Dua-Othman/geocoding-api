from geocoding_api.domain.normalize import collapse_whitespace, normalize_name


def test_lowercases_and_trims():
    assert normalize_name("  PARIS  ") == "paris"


def test_strips_combining_diacritics():
    assert normalize_name("São Paulo") == "sao paulo"
    assert normalize_name("Zürich") == "zurich"
    assert normalize_name("Bogotá") == "bogota"
    assert normalize_name("Reykjavík") == "reykjavik"
    assert normalize_name("Kraków") == "krakow"


def test_maps_letters_that_nfkd_does_not_decompose():
    assert normalize_name("Łódź") == "lodz"
    assert normalize_name("Ærø") == "aero"
    assert normalize_name("Straße") == "strasse"


def test_removes_apostrophe_like_characters():
    assert normalize_name("Nukuʻalofa") == "nukualofa"
    assert normalize_name("N'Djamena") == "ndjamena"


def test_collapses_internal_whitespace():
    assert normalize_name("New   York") == "new york"


def test_treats_punctuation_as_separators():
    assert normalize_name("Paris, France") == "paris france"
    assert normalize_name("los-angeles") == "los angeles"
    assert normalize_name("St. Petersburg") == "st petersburg"
    assert normalize_name("Rio de Janeiro/RJ") == "rio de janeiro rj"


def test_collapse_whitespace_collapses_and_trims():
    assert collapse_whitespace("  Padded  Name ") == "Padded Name"
