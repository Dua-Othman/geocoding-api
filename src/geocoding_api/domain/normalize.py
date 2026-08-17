from __future__ import annotations

import re
import unicodedata

# letters NFKD won't decompose, so they need a manual mapping
CHAR_MAP = {
    "ł": "l",
    "ø": "o",
    "æ": "ae",
    "œ": "oe",
    "ß": "ss",
    "đ": "d",
    "ð": "d",
    "þ": "th",
    "ı": "i",
}

_MAPPED_CHARS = re.compile("[łøæœßđðþı]")
_APOSTROPHES = re.compile("[’‘'`´ʻʼʹ]")
# commas, hyphens etc. act as separators so "Paris, France" and "los-angeles"
# tokenize the same way people type them
_PUNCT_TO_SPACE = re.compile(r"[,;./\-–—]")
_WHITESPACE = re.compile(r"\s+")


def normalize_name(value: str) -> str:
    """Lowercase, strip accents, collapse spaces ("São Paulo" → "sao paulo").
    Ingest and queries both use this — they must agree or lookups miss."""
    decomposed = unicodedata.normalize("NFKD", value)
    stripped = "".join(ch for ch in decomposed if not unicodedata.combining(ch))
    lowered = stripped.lower()
    mapped = _MAPPED_CHARS.sub(lambda m: CHAR_MAP[m.group(0)], lowered)
    no_apostrophes = _APOSTROPHES.sub("", mapped)
    spaced = _PUNCT_TO_SPACE.sub(" ", no_apostrophes)
    return _WHITESPACE.sub(" ", spaced).strip()


def collapse_whitespace(value: str) -> str:
    return _WHITESPACE.sub(" ", value).strip()
