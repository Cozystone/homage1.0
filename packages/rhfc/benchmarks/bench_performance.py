"""Measure FFT binding scaling for RHFC Stage 1."""

from __future__ import annotations

import csv
import json
import statistics
import sys
import time
import tracemalloc
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from rhfc.fft_binding import bind, unbind
from rhfc.hypervector import random_bipolar

BENCH_DIR = Path(__file__).resolve().parent
PERFORMANCE_START = "## FFT Bind+Unbind Scaling"


def measure_fft_scaling() -> list[dict[str, float | int]]:
    """Measure bind+unbind time for dimensions 2^8 through 2^16."""

    rows: list[dict[str, float | int]] = []
    for power in range(8, 17):
        dim = 2**power
        repeats = 12 if dim <= 8192 else 6
        a = random_bipolar(dim, seed=80_000 + dim)
        b = random_bipolar(dim, seed=90_000 + dim)
        timings = []
        tracemalloc.start()
        for _ in range(repeats):
            start = time.perf_counter()
            _ = unbind(bind(a, b), b)
            timings.append((time.perf_counter() - start) * 1000.0)
        _, peak = tracemalloc.get_traced_memory()
        tracemalloc.stop()
        rows.append(
            {
                "dim": dim,
                "repeats": repeats,
                "median_ms": round(float(statistics.median(timings)), 5),
                "mean_ms": round(float(statistics.mean(timings)), 5),
                "peak_kb": round(float(peak / 1024.0), 2),
            }
        )
    return rows


def main() -> None:
    rows = measure_fft_scaling()
    (BENCH_DIR / "performance_results.json").write_text(json.dumps({"fft_scaling": rows}, indent=2), encoding="utf-8")
    with (BENCH_DIR / "fft_binding_scaling.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=["dim", "repeats", "median_ms", "mean_ms", "peak_kb"])
        writer.writeheader()
        writer.writerows(rows)
    _update_readme(rows)
    print(json.dumps({"fft_scaling": rows}, indent=2))


def _update_readme(rows: list[dict[str, float | int]]) -> None:
    """Append or replace the README performance table with measured rows."""

    readme = BENCH_DIR / "README.md"
    text = readme.read_text(encoding="utf-8") if readme.exists() else "# RHFC Stage 1 Benchmarks\n\n"
    before = text.split(PERFORMANCE_START, 1)[0].rstrip()
    notes = ""
    if "\n## Notes" in text:
        notes = "\n## Notes" + text.split("\n## Notes", 1)[1]
    lines = [
        PERFORMANCE_START,
        "",
        "| dim | repeats | median ms | mean ms | peak KB |",
        "|---:|---:|---:|---:|---:|",
    ]
    for row in rows:
        lines.append(f"| {row['dim']} | {row['repeats']} | {row['median_ms']} | {row['mean_ms']} | {row['peak_kb']} |")
    next_text = before + "\n\n" + "\n".join(lines) + "\n"
    if notes:
        next_text += notes
    readme.write_text(next_text.rstrip() + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
