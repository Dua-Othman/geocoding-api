import pytest

from geocoding_api.config import load_config


def test_defaults_are_safe_for_local_use():
    config = load_config({})
    assert config.port == 3200
    assert config.host == "127.0.0.1"
    assert config.cors_origins == ""
    assert config.docs_enabled is True
    assert config.rate_limit_per_minute == 120
    assert config.default_limit == 5
    assert config.max_limit == 20


def test_rejects_zero_max_limit():
    with pytest.raises(ValueError, match="MAX_LIMIT"):
        load_config({"MAX_LIMIT": "0"})


def test_rejects_non_numeric_port():
    with pytest.raises(ValueError, match="PORT"):
        load_config({"PORT": "abc"})


def test_rejects_default_limit_above_max_limit():
    with pytest.raises(ValueError, match="DEFAULT_LIMIT"):
        load_config({"DEFAULT_LIMIT": "10", "MAX_LIMIT": "5"})


def test_rejects_negative_radius():
    with pytest.raises(ValueError, match="RADIUS"):
        load_config({"MAX_RADIUS_KM": "-5"})


def test_rejects_negative_rate_limit_but_allows_zero():
    with pytest.raises(ValueError, match="RATE_LIMIT"):
        load_config({"RATE_LIMIT": "-1"})
    assert load_config({"RATE_LIMIT": "0"}).rate_limit_per_minute == 0


def test_out_of_range_port_fails():
    with pytest.raises(ValueError, match="PORT"):
        load_config({"PORT": "70000"})
