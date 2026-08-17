from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass

# hard ceilings so a typo in an env var cannot configure something absurd
_MAX_LIMIT_CEILING = 100
_MAX_RADIUS_CEILING_KM = 40_000


@dataclass(frozen=True, slots=True)
class AppConfig:
    port: int
    host: str
    index_file: str
    default_limit: int
    max_limit: int
    default_radius_km: float
    max_radius_km: float
    cors_origins: str
    docs_enabled: bool
    rate_limit_per_minute: int


def load_config(env: Mapping[str, str] | None = None) -> AppConfig:
    """Raises ValueError on invalid values — bad config should stop startup,
    not quietly fall back to something the operator did not ask for."""
    if env is None:
        env = os.environ
    config = AppConfig(
        port=_int_from_env(env, "PORT", 3200),
        host=env.get("HOST", "127.0.0.1"),
        index_file=env.get("INDEX_FILE", "data/geocoding-index.json"),
        default_limit=_int_from_env(env, "DEFAULT_LIMIT", 5),
        max_limit=_int_from_env(env, "MAX_LIMIT", 20),
        default_radius_km=_float_from_env(env, "DEFAULT_RADIUS_KM", 300),
        max_radius_km=_float_from_env(env, "MAX_RADIUS_KM", 5000),
        cors_origins=env.get("CORS_ORIGINS", ""),
        docs_enabled=env.get("DOCS", "on").lower() not in ("0", "false", "off", "no"),
        rate_limit_per_minute=_int_from_env(env, "RATE_LIMIT", 120),
    )

    problems: list[str] = []
    if not 1 <= config.port <= 65535:
        problems.append(f"PORT must be 1–65535, got {config.port}")
    if not 1 <= config.default_limit <= config.max_limit <= _MAX_LIMIT_CEILING:
        problems.append(
            f"limits must satisfy 1 <= DEFAULT_LIMIT ({config.default_limit}) "
            f"<= MAX_LIMIT ({config.max_limit}) <= {_MAX_LIMIT_CEILING}"
        )
    if not 0 < config.default_radius_km <= config.max_radius_km <= _MAX_RADIUS_CEILING_KM:
        problems.append(
            f"radii must satisfy 0 < DEFAULT_RADIUS_KM ({config.default_radius_km:g}) "
            f"<= MAX_RADIUS_KM ({config.max_radius_km:g}) <= {_MAX_RADIUS_CEILING_KM}"
        )
    if config.rate_limit_per_minute < 0:
        problems.append(f"RATE_LIMIT must be >= 0 (0 disables), got {config.rate_limit_per_minute}")
    if problems:
        raise ValueError("invalid configuration: " + "; ".join(problems))
    return config


def _int_from_env(env: Mapping[str, str], key: str, fallback: int) -> int:
    raw = env.get(key)
    if raw is None or raw == "":
        return fallback
    try:
        return int(raw)
    except ValueError:
        raise ValueError(f'{key} must be an integer, got "{raw}"') from None


def _float_from_env(env: Mapping[str, str], key: str, fallback: float) -> float:
    raw = env.get(key)
    if raw is None or raw == "":
        return fallback
    try:
        return float(raw)
    except ValueError:
        raise ValueError(f'{key} must be a number, got "{raw}"') from None
