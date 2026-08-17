from geocoding_api.domain.levenshtein import levenshtein, max_edits_for_length


def test_computes_classic_distances():
    assert levenshtein("kitten", "sitting") == 3
    assert levenshtein("paris", "pariss") == 1
    assert levenshtein("paris", "paris") == 0


def test_handles_empty_strings():
    assert levenshtein("", "abc") == 3
    assert levenshtein("abc", "") == 3


def test_short_circuits_past_the_cap():
    assert levenshtein("abcdef", "uvwxyz", 2) == 3
    assert levenshtein("abcdefgh", "ab", 2) == 3


def test_is_symmetric():
    assert levenshtein("krakow", "krakov") == levenshtein("krakov", "krakow")


def test_max_edits_follows_the_auto_fuzziness_bands():
    assert max_edits_for_length(1) == 0
    assert max_edits_for_length(2) == 0
    assert max_edits_for_length(3) == 1
    assert max_edits_for_length(5) == 1
    assert max_edits_for_length(6) == 2
    assert max_edits_for_length(20) == 2
