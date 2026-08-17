from __future__ import annotations

import sys
import time
from typing import Any, Awaitable, Callable, Literal

from fastapi import FastAPI, Query, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from .config import AppConfig
from .domain.errors import QueryError
from .repository.base import GeocodingRepository
from .service.geocoding_service import GeocodingService, GeocodingServiceConfig

try:
    import resource
except ImportError:  # not available on Windows
    resource = None  # type: ignore[assignment]


class _ErrorBody(BaseModel):
    code: str
    message: str


class _QueryEcho(BaseModel):
    raw: str
    type: Literal["forward", "reverse"]
    normalized: str | None = None
    lat: float | None = None
    lon: float | None = None
    convention: str | None = None


class _ResultItem(BaseModel):
    id: str
    place_name: str
    country: str | None
    latitude: float
    longitude: float
    population: int | None
    confidence: float
    match_type: Literal["exact", "prefix", "substring", "fuzzy", "nearest"]
    distance_km: float | None


class _Metadata(BaseModel):
    count: int
    limit: int
    radius_km: float | None
    took_ms: float
    attribution: str


class _GeocodeResponse(BaseModel):
    query: _QueryEcho
    results: list[_ResultItem]
    metadata: _Metadata


class _GeocodeError(BaseModel):
    error: _ErrorBody
    query: _QueryEcho | None = None
    metadata: _Metadata | None = None


def build_app(repository: GeocodingRepository, config: AppConfig) -> FastAPI:
    """Wire repository → service → routes. Tests pass a fixture repo here;
    main.py passes the real artifact-backed one."""
    docs = config.docs_enabled
    app = FastAPI(
        title="Minimal Geocoding API",
        version="1.0.0",
        docs_url="/docs" if docs else None,
        redoc_url="/redoc" if docs else None,
        openapi_url="/openapi.json" if docs else None,
    )

    # CORS is off unless origins are configured — browsers get same-origin only
    origins = [o.strip() for o in config.cors_origins.split(",") if o.strip()]
    if origins:
        app.add_middleware(CORSMiddleware, allow_origins=origins, allow_methods=["GET"])

    if config.rate_limit_per_minute > 0:
        _add_rate_limiter(app, config.rate_limit_per_minute)

    service = GeocodingService(
        repository,
        GeocodingServiceConfig(
            default_limit=config.default_limit,
            max_limit=config.max_limit,
            default_radius_km=config.default_radius_km,
            max_radius_km=config.max_radius_km,
        ),
    )
    started_at = time.monotonic()

    @app.exception_handler(QueryError)
    async def handle_query_error(_request: Request, error: QueryError) -> JSONResponse:
        return JSONResponse(
            status_code=error.status_code,
            content={"error": {"code": error.code, "message": error.message}},
        )

    @app.exception_handler(RequestValidationError)
    async def handle_validation_error(
        _request: Request, error: RequestValidationError
    ) -> JSONResponse:
        message = "; ".join(
            f"{'.'.join(str(part) for part in e['loc'])}: {e['msg']}" for e in error.errors()
        )
        return JSONResponse(
            status_code=400,
            content={"error": {"code": "BAD_REQUEST", "message": message}},
        )

    @app.exception_handler(Exception)
    async def handle_unexpected(_request: Request, _error: Exception) -> JSONResponse:
        # same JSON envelope as every other error, never a raw traceback page
        return JSONResponse(
            status_code=500,
            content={"error": {"code": "INTERNAL_ERROR", "message": "Unexpected server error"}},
        )

    @app.get(
        "/geocode",
        responses={
            200: {"model": _GeocodeResponse},
            400: {"model": _GeocodeError},
            404: {"model": _GeocodeError},
            429: {"model": _GeocodeError},
        },
    )
    def geocode(
        request: Request,
        q: str = Query(min_length=1, max_length=256),
        limit: int | None = Query(default=None, ge=1, le=config.max_limit),
        radius: float | None = Query(default=None, gt=0, le=config.max_radius_km),
    ) -> JSONResponse:
        if len(request.query_params.getlist("q")) > 1:
            return JSONResponse(
                status_code=400,
                content={"error": {"code": "BAD_REQUEST", "message": 'pass "q" exactly once'}},
            )

        response = service.geocode(q, limit=limit, radius_km=radius)

        if not response["results"]:
            if response["query"]["type"] == "forward":
                message = f'No place matched "{q}". Check the spelling or try a shorter query.'
            else:
                message = (
                    f'No place within {response["metadata"]["radius_km"]:g} km of '
                    f'{response["query"]["lat"]:g},{response["query"]["lon"]:g}. '
                    f'Pass a larger "radius" (up to {config.max_radius_km:g} km).'
                )
            return JSONResponse(
                status_code=404,
                content={
                    "error": {"code": "NO_MATCH", "message": message},
                    "query": response["query"],
                    "metadata": response["metadata"],
                },
            )
        return JSONResponse(content=response)

    @app.get("/health")
    def health() -> dict[str, Any]:
        return {
            "status": "ok",
            "uptime_s": round(time.monotonic() - started_at),
            "records": repository.stats().records,
        }

    if docs:
        # diagnostics ship with the docs: both off when DOCS=off in production
        @app.get("/stats")
        def stats() -> dict[str, Any]:
            meta = repository.stats()
            if resource is not None:
                max_rss = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
                # ru_maxrss is bytes on macOS, kilobytes on Linux
                rss_bytes = max_rss if sys.platform == "darwin" else max_rss * 1024
            else:
                rss_bytes = None
            return {
                "records": meta.records,
                "built_at": meta.built_at,
                "source": meta.source,
                "uptime_s": round(time.monotonic() - started_at),
                "memory_rss_bytes": rss_bytes,
            }

    return app


def _add_rate_limiter(app: FastAPI, per_minute: int) -> None:
    """Fixed-window in-process limiter for /geocode. Enough for one process;
    a multi-instance deploy moves this to the gateway."""
    windows: dict[str, tuple[int, int]] = {}

    @app.middleware("http")
    async def rate_limit(
        request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        if request.url.path != "/geocode":
            return await call_next(request)
        minute = int(time.time()) // 60
        client = request.client.host if request.client else "unknown"
        start, count = windows.get(client, (minute, 0))
        if start != minute:
            start, count = minute, 0
        count += 1
        windows[client] = (start, count)
        if count > per_minute:
            return JSONResponse(
                status_code=429,
                content={
                    "error": {
                        "code": "RATE_LIMITED",
                        "message": f"Rate limit is {per_minute} requests per minute.",
                    }
                },
            )
        if len(windows) > 10_000:
            for key in [k for k, (s, _) in windows.items() if s != minute]:
                windows.pop(key, None)
        return await call_next(request)
