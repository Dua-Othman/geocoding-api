from __future__ import annotations

import re
import unicodedata

from .errors import QueryError
from .normalize import normalize_name
from .types import ClassifiedQuery, ForwardQuery, ReverseQuery

# ASCII decimal only — no exponents, degree symbols, or hemisphere letters.
# re.ASCII keeps \d from matching e.g. Arabic-Indic digits, which float()
# would otherwise quietly accept.
_NUMERIC = re.compile(r"[+-]?(\d+(\.\d+)?|\.\d+)", re.ASCII)

# unicode minus and dashes that show up when coordinates are copy-pasted
_DASHES = str.maketrans({"−": "-", "‒": "-", "–": "-", "—": "-"})


def classify_query(raw: str) -> ClassifiedQuery:
    """Two comma-separated numbers = "lat,lon" (reverse); a numeric pair out
    of range is a 400; everything else is a text search. Deterministic on
    purpose — same input, same path. Full rule in the README."""
    trimmed = raw.strip()
    if not trimmed:
        raise QueryError("EMPTY_QUERY", 'Query parameter "q" must not be empty.')

    # fold copy-paste variants (fullwidth comma/digits, unicode minus) before
    # deciding; the numeric check itself stays ASCII-only
    folded = unicodedata.normalize("NFKC", trimmed).translate(_DASHES)

    # allow "(48.85, 2.35)" — common copy-paste format from map apps
    wrapped = folded.startswith("(") and folded.endswith(")")
    candidate = folded[1:-1].strip() if wrapped else folded

    parts = [p.strip() for p in candidate.split(",")]
    if len(parts) == 2 and _NUMERIC.fullmatch(parts[0]) and _NUMERIC.fullmatch(parts[1]):
        lat = float(parts[0])
        lon = float(parts[1])
        if lat < -90 or lat > 90:
            raise QueryError(
                "INVALID_COORDINATES",
                f'Latitude {lat:g} is out of range [-90, 90]. Coordinates are interpreted as "lat,lon".',
            )
        if lon < -180 or lon > 180:
            raise QueryError(
                "INVALID_COORDINATES",
                f'Longitude {lon:g} is out of range [-180, 180]. Coordinates are interpreted as "lat,lon".',
            )
        return ReverseQuery(lat=lat, lon=lon)

    return ForwardQuery(text=trimmed, normalized=normalize_name(trimmed))
