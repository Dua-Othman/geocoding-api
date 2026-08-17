#!/usr/bin/env python3
"""Build the geocoding index artifact from a CSV file, streaming end to end.

Usage: python scripts/ingest.py [input.csv] [output.json]
Defaults: data/geodata.csv → data/geocoding-index.json
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from geocoding_api.ingest.pipeline import (  # noqa: E402
    MAX_DROPPED_EXAMPLES,
    JsonArtifactSink,
    stream_ingest,
)

input_arg = sys.argv[1] if len(sys.argv) > 1 else "data/geodata.csv"
output_arg = sys.argv[2] if len(sys.argv) > 2 else "data/geocoding-index.json"
input_path = Path(input_arg).resolve()
output_path = Path(output_arg).resolve()

output_path.parent.mkdir(parents=True, exist_ok=True)
sink = JsonArtifactSink(output_path, source=input_arg)
try:
    # newline="" is what the csv module expects for correct quoting behavior
    with input_path.open(newline="", encoding="utf-8") as lines:
        report = stream_ingest(lines, sink)
except BaseException:
    sink.abort()
    raise

for row in report.dropped:
    print(f"  dropped line {row.line}: {row.reason}", file=sys.stderr)
if report.dropped_total > len(report.dropped):
    hidden = report.dropped_total - len(report.dropped)
    print(f"  … and {hidden} more (first {MAX_DROPPED_EXAMPLES} shown)", file=sys.stderr)
print(
    f"Ingest complete: {report.kept} records kept, {report.merged} duplicates merged, "
    f"{report.dropped_total} rows dropped ({report.rows_read} data rows read)."
)

if report.kept == 0:
    sink.abort()
    print("No valid records — refusing to write an empty index.", file=sys.stderr)
    sys.exit(1)

sink.finalize()
print(f"Index written to {output_arg}")
