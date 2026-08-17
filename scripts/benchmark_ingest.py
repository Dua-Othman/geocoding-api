#!/usr/bin/env python3
"""Reproduce the ingest benchmark quoted in the README.

Usage: python scripts/benchmark_ingest.py [rows]      (default 1,000,000)

Generates a synthetic CSV with unique names, streams it through the real
pipeline into a JSON artifact, and reports elapsed time and peak memory.
"""
from __future__ import annotations

import random
import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from geocoding_api.ingest.pipeline import JsonArtifactSink, stream_ingest  # noqa: E402

rows = int(sys.argv[1]) if len(sys.argv) > 1 else 1_000_000
rng = random.Random(7)

with tempfile.TemporaryDirectory() as tmp:
    csv_path = Path(tmp) / "benchmark.csv"
    out_path = Path(tmp) / "benchmark-index.json"

    with csv_path.open("w", encoding="utf-8") as f:
        f.write("id,place_name,latitude,longitude,country,population\n")
        for i in range(rows):
            f.write(
                f"{i},Place Number {i},{rng.uniform(-90, 90):.4f},"
                f"{rng.uniform(-180, 180):.4f},Testland,{rng.randint(100, 9_999_999)}\n"
            )
    csv_bytes = csv_path.stat().st_size

    sink = JsonArtifactSink(out_path, source="benchmark")
    started = time.perf_counter()
    with csv_path.open(newline="", encoding="utf-8") as lines:
        report = stream_ingest(lines, sink)
    sink.finalize()
    elapsed = time.perf_counter() - started

    print(f"rows: {report.rows_read:,} ({csv_bytes / 1e6:.0f} MB CSV)")
    print(f"kept: {report.kept:,}, merged: {report.merged:,}, dropped: {report.dropped_total:,}")
    print(f"elapsed: {elapsed:.1f} s")
    try:
        import resource

        max_rss = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
        rss_mb = (max_rss if sys.platform == "darwin" else max_rss * 1024) / 1e6
        print(f"peak RSS: {rss_mb:.0f} MB")
    except ImportError:
        print("peak RSS: unavailable on this platform")
