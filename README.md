# Minimal Geocoding API Service (Python)

One endpoint, both directions. `GET /geocode?q=…` takes a place name and returns coordinates, or takes coordinates and returns the nearest place.

Built with Python, FastAPI and Uvicorn. The data is a small OpenStreetMap-derived CSV that a separate script turns into a lookup index.

## Quick start

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"

python scripts/ingest.py     # build the index (needed once, before first run)
python -m geocoding_api      # start on port 3200

# or with auto-reload while developing
uvicorn geocoding_api.main:app --port 3200 --reload
```

Try it:

```bash
curl "http://localhost:3200/geocode?q=paris"
curl "http://localhost:3200/geocode?q=48.8566,2.3522"
curl "http://localhost:3200/geocode?q=zurihc"            # typo still finds Zürich
curl "http://localhost:3200/geocode?q=0,-30&radius=5000" # wider search radius
```

Interactive docs are at `http://localhost:3200/docs`. Run the tests with `pytest` (add `--cov` for coverage).

Config is all environment variables, all optional: `PORT` (3200), `HOST` (127.0.0.1), `INDEX_FILE`, `DEFAULT_LIMIT` (5), `MAX_LIMIT` (20), `DEFAULT_RADIUS_KM` (300), `MAX_RADIUS_KM` (5000), `CORS_ORIGINS` (empty = same-origin only), `RATE_LIMIT` (120/minute per client, 0 disables), `DOCS` (`off` hides docs and `/stats`). Bad config stops startup with a clear message instead of silently falling back.

## API

### `GET /geocode`

| Parameter | Type | Required | Description |
|---|---|---|---|
| `q` | string, max 256 chars | yes | A place name, or a `lat,lon` pair |
| `limit` | integer 1–20 | no | How many results (default 5) |
| `radius` | number up to 5000 | no | Search radius in km for coordinates (default 300) |

How `q` is read — the rule is fixed, so the same input always takes the same path:

1. Two comma-separated numbers = coordinates, read as `lat,lon` (the Google order, not GeoJSON's). `(48.8566, 2.3522)` works too, and pasted variants like a fullwidth comma or a Unicode minus are converted first.
2. Two numbers out of range, like `91,0`, get a 400 — that's a typo, not a place name.
3. Everything else is a text search. `10 Downing Street` has digits but is not two bare numbers. Space-separated numbers also go to text: `10 20` is more likely a house number than a coordinate. The comma is the signal.

`Paris, France` works through the text search: if the full string finds nothing, the part before the comma is searched and the part after filters by country. `London, Canada` gives only the Canadian one; `Paris, TX` matches no country, so both Parises come back.

The response echoes back how the query was understood, so a misread is visible immediately.

### Response

```json
{
  "query": { "raw": "paris", "type": "forward", "normalized": "paris" },
  "results": [
    {
      "id": "1", "place_name": "Paris", "country": "France",
      "latitude": 48.8566, "longitude": 2.3522, "population": 2148000,
      "confidence": 1, "match_type": "exact", "distance_km": null
    },
    {
      "id": "2", "place_name": "Paris", "country": "United States",
      "latitude": 33.6609, "longitude": -95.5555, "population": 24839,
      "confidence": 1, "match_type": "exact", "distance_km": null
    }
  ],
  "metadata": {
    "count": 2, "limit": 5, "radius_km": null, "took_ms": 0.2,
    "attribution": "Data © OpenStreetMap contributors, ODbL 1.0 (sample extract)"
  }
}
```

Ambiguous names return every match, ranked by confidence then population — picking one would just be guessing. Coordinate lookups include `distance_km`.

### Errors

| Status | Code | When |
|---|---|---|
| 400 | `BAD_REQUEST` | `q` missing or repeated, or `limit`/`radius` out of bounds |
| 400 | `EMPTY_QUERY` | `q` is only whitespace |
| 400 | `INVALID_COORDINATES` | Two numbers outside the valid lat/lon range |
| 404 | `NO_MATCH` | Nothing matched, or nothing inside the radius |
| 429 | `RATE_LIMITED` | Too many `/geocode` requests from one client |
| 500 | `INTERNAL_ERROR` | Unexpected failure (no traceback leaked) |

Every error body has an `error` object with `code` and `message`. A 404 also includes the `query` echo and `metadata`, since by then the query was understood — there just was no answer. A lookup in the middle of the Atlantic gets a 404 suggesting a bigger radius, not a city 2000 km away.

`/health` returns status, uptime and record count. `/stats` adds index build info and memory use.

## Architecture

```
                 ┌─────────────────────────────────────────────┐
   client ──────▶│  transport   FastAPI route, validation      │
                 │      │                                       │
                 │  domain      classifier ─▶ forward strategy  │
                 │                          ─▶ reverse strategy │
                 │      │                                       │
                 │  port        GeocodingRepository (Protocol)  │
                 └──────┼───────────────────────────────────────┘
                        ▼
                 in-memory adapter:  name tiers  +  spherical k-d tree
                        ▲
   build time:   geodata.csv ─▶ ingest (clean, normalize, dedupe) ─▶ index file
```

A small layered app. The FastAPI layer only does HTTP, the domain layer only does geocoding, and storage sits behind a `GeocodingRepository` protocol. Microservices would be overkill for one endpoint; one big request handler would be the opposite mistake. This split keeps storage swappable and lets the geocoding logic be tested without a server.

| Pattern | Where |
|---|---|
| Strategy | `ForwardStrategy` / `ReverseStrategy` — a third mode is a new class, not a rewrite |
| Repository | `GeocodingRepository` — swap in a database without touching the rest |
| Chain of responsibility | Match tiers, each running only if the one before found nothing |
| Facade | `GeocodingService.geocode()` — one entry point |
| Composition root | `build_app()` — tests inject fixtures, production injects the real repository |

Cleaning happens at build time: the ingest script validates and writes the index once, and the server loads it, re-validates every field (the file may come from another pipeline), and builds its in-memory indexes at startup — under a second at this size. Exact and reverse lookups are indexed; prefix, substring and fuzzy still scan linearly, which is what the database stages below would replace.

## Why this stack

| Part | Choice | Reason |
|---|---|---|
| Framework | FastAPI + Uvicorn | Validation and OpenAPI docs for free |
| Spatial index | Own k-d tree | No dependencies, and the sphere needed care anyway |
| Fuzzy matching | Own bounded Levenshtein | Small enough to read and test |
| CSV parsing | Stdlib `csv` | Quoting and escapes already handled |
| Tests | pytest + `TestClient` | Integration tests in-process, no ports |

### Why the k-d tree projects onto a sphere

Latitude and longitude are not flat. A k-d tree built on them directly thinks Fiji and Tonga are a world apart (178 vs −175), and distorts distances near the poles. Instead, every point is projected onto a unit sphere in 3D, where straight-line distance always ranks the same as true surface distance — so plain 3D maths is correct everywhere, and results convert back to kilometres at the end.

At 75 records a brute-force scan would honestly be fine. The tree is here because it is the right shape for growth, and the sphere handling is the part that is easy to get wrong.

## Data and accuracy

`data/geodata.csv` is 75 cities, hand-assembled from OpenStreetMap data (August 2026, coordinates to 4 decimals). It is deliberately full of awkward cases: two Parises, two Londons, accents (São Paulo, Łódź), date-line neighbours (Suva, Apia), and high latitudes (Longyearbyen).

The ingest streams — it never holds the file in memory. Rows are read one at a time, checked, and written straight to the index file, via a temp file and rename so a crash can't leave a half-written index. A million rows takes ~11 s and ~250 MB (`python scripts/benchmark_ingest.py` to reproduce). Dropped rows are reported with line numbers, first 50 examples plus totals.

Cleaning: coordinates must be plain in-range decimals (same rule as the query classifier); ids unique; whitespace collapsed; populations like `1,234` parsed; names normalized (lowercase, accents stripped, punctuation folded to spaces) with the same function used for queries, so the two sides always agree. Duplicates — the same normalized name within 11 metres, measured by real distance, not grid rounding — are merged, keeping the first row seen (earlier rows are already streamed out; a database-backed ingest would keep the higher-population row instead).

At query time:

- Tiers with separate confidence ranges: exact (1.0), prefix (0.80–0.95), substring (0.60–0.80), fuzzy (0.40–0.75)
- Substring needs 3+ characters and a word boundary — `angeles` finds Los Angeles, `or` does not return Toronto
- Typo budget grows with length: none up to 2 chars, one up to 5, two above
- Ties break by population, then name, then id, so ordering is stable across restarts
- Reverse lookups have a max radius, so "nothing near here" is a possible answer

One note: reverse `confidence` is a proximity score inside the requested radius, so the same place scores differently if only the radius changes, and it is not comparable with forward confidence. `distance_km` is the objective number.

## Testing

105 tests: the classifier's edge cases, normalization, edit distance, matching tiers, config and index-file validation, and the ingest run over a deliberately messy CSV. The k-d tree is checked against brute-force haversine over 400 random points plus date-line and pole cases. The HTTP layer is tested end to end with `TestClient` against the real dataset — every success shape and every error shape.

## Scaling

| Stage | Size | What changes |
|---|---|---|
| Now | up to ~1M records | In-memory index from the ingest script |
| Next | ~1–10M | SQLite (FTS5 + R*Tree) behind the same repository |
| Then | 10M+ | PostgreSQL with PostGIS and pg_trgm; ingest writes to the database |
| Planet | everything | Elasticsearch for text, PostGIS for geometry, caching in front |

Only the repository adapter and the ingest target change at each stage; the service, classifier and API stay the same. That is the point of the interface.

One thing to be upfront about: swapping the backend changes the numbers, not just the storage. Postgres and Elasticsearch score matches their own way, so confidence values and ordering would come out different even though the JSON fields stay the same. A scoring version in the metadata would let clients see that change coming.

### Production hardening

Defaults are closed: localhost bind, same-origin CORS, per-client rate limit, fail-fast config, full index validation, JSON error envelope, 256-char query cap, docs and `/stats` removable with one switch. A public deployment would still add: auth at the gateway, request IDs, timeouts, a `/ready` check, metrics, zero-downtime index reloads, cache headers, and a lockfile. None of that changes the architecture.

The sample data is derived from OpenStreetMap — © OpenStreetMap contributors — which is why every response carries `metadata.attribution`. CI (`.github/workflows/ci.yml`) runs the suite and a real ingest on every push.
