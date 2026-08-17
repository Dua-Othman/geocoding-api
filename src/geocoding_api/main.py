from __future__ import annotations

import sys

from .config import load_config
from .repository.in_memory import InMemoryGeocodingRepository
from .server import build_app

try:
    config = load_config()
except ValueError as error:
    print(str(error), file=sys.stderr)
    sys.exit(1)

try:
    repository = InMemoryGeocodingRepository.from_file(config.index_file)
except (OSError, ValueError, KeyError, TypeError) as error:
    print(f'Could not load the geocoding index at "{config.index_file}".', file=sys.stderr)
    print('Run "python scripts/ingest.py" first to build it from data/geodata.csv.', file=sys.stderr)
    print(str(error), file=sys.stderr)
    sys.exit(1)

app = build_app(repository, config)


def run() -> None:
    import uvicorn

    uvicorn.run(app, host=config.host, port=config.port)
