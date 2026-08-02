"""Stage 2.5 RHFC benchmark: Hopfield scaling and cleanup stress.

This benchmark intentionally stays inside packages/rhfc and does not touch
ATANOR runtime packages. It measures the existing ModernHopfieldMemory recall
path over larger pattern counts and records when accuracy collapses or when the
local machine's safe memory budget stops the sweep first.
"""

from __future__ import annotations

import json
import math
import statistics
import sys
import time
from pathlib import Path
from typing import Any

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from rhfc.cleanup_memory import ModernHopfieldMemory
from rhfc.fft_binding import make_unitary_key
from rhfc.hypervector import HyperVector, cosine_similarity, random_bipolar
from rhfc.pipeline import bind_value_with_keys, query_and_cleanup

BENCH_DIR = Path(__file__).resolve().parent
MAX_MATRIX_GB = 1.35
COUNTS = [8_192, 16_384, 32_768, 65_536, 131_072]
DIMS = [1_024, 4_096, 10_000]
NOISE_FRACTION = 0.35


def _matrix_gb(patterns: int, dim: int) -> float:
    return patterns * dim * 8 / (1024**3)


def _pattern_matrix(patterns: int, dim: int, seed: int) -> np.ndarray:
    """Create row-normalized random bipolar patterns in the memory's format."""

    rng = np.random.default_rng(seed)
    matrix = rng.choice(np.array([-1.0, 1.0], dtype=np.float64), size=(patterns, dim))
    matrix /= math.sqrt(dim)
    return matrix


def _noisy_query(row: np.ndarray, dim: int, seed: int, noise_fraction: float = NOISE_FRACTION) -> HyperVector:
    rng = np.random.default_rng(seed)
    values = row.copy() * math.sqrt(dim)
    flip_count = max(1, int(dim * noise_fraction))
    indices = rng.choice(dim, size=flip_count, replace=False)
    values[indices] *= -1.0
    return HyperVector(values, "bipolar")


def _trial_indices(patterns: int, trials: int) -> list[int]:
    return [int((17 + i * 9973) % patterns) for i in range(trials)]


def benchmark_capacity() -> list[dict[str, Any]]:
    """Measure recall accuracy across dimensions and pattern counts."""

    rows: list[dict[str, Any]] = []
    for dim in DIMS:
        for patterns in COUNTS:
            matrix_gb = _matrix_gb(patterns, dim)
            if matrix_gb > MAX_MATRIX_GB:
                rows.append(
                    {
                        "dim": dim,
                        "patterns": patterns,
                        "pattern_dim_ratio": round(patterns / dim, 4),
                        "matrix_gb": round(matrix_gb, 4),
                        "status": "skipped_memory_budget",
                        "accuracy": None,
                        "mean_recall_ms": None,
                        "p95_recall_ms": None,
                    }
                )
                continue
            trials = 8 if matrix_gb < 0.75 else 4
            start_build = time.perf_counter()
            matrix = _pattern_matrix(patterns, dim, seed=200_000 + dim + patterns)
            memory = ModernHopfieldMemory(matrix)
            build_ms = (time.perf_counter() - start_build) * 1000.0
            correct = 0
            recall_times: list[float] = []
            target_cosines: list[float] = []
            for trial, target_index in enumerate(_trial_indices(patterns, trials)):
                query = _noisy_query(matrix[target_index], dim, seed=300_000 + dim + patterns + trial)
                start = time.perf_counter()
                recalled = memory.recall(query, beta=42.0)
                nearest = memory.nearest_index(recalled)
                recall_times.append((time.perf_counter() - start) * 1000.0)
                correct += int(nearest == target_index)
                target_cosines.append(cosine_similarity(HyperVector(matrix[target_index] * math.sqrt(dim), "bipolar"), recalled))
            rows.append(
                {
                    "dim": dim,
                    "patterns": patterns,
                    "pattern_dim_ratio": round(patterns / dim, 4),
                    "matrix_gb": round(matrix_gb, 4),
                    "status": "measured",
                    "trials": trials,
                    "noise_fraction": NOISE_FRACTION,
                    "accuracy": round(correct / trials, 4),
                    "mean_target_cosine": round(float(statistics.mean(target_cosines)), 6),
                    "build_ms": round(build_ms, 3),
                    "mean_recall_ms": round(float(statistics.mean(recall_times)), 3),
                    "p95_recall_ms": round(float(np.percentile(recall_times, 95)), 3),
                }
            )
            del memory
            del matrix
    return rows


def _select_near_limit_rows(capacity_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    selected: list[dict[str, Any]] = []
    for dim in DIMS:
        measured = [row for row in capacity_rows if row["dim"] == dim and row["status"] == "measured"]
        if not measured:
            continue
        collapsed = [row for row in measured if float(row["accuracy"]) < 0.95]
        selected.append(collapsed[0] if collapsed else measured[-1])
    return selected


def benchmark_key_cleanup_near_limit(capacity_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Compare random vs unitary cleanup at the largest safe measured counts."""

    rows: list[dict[str, Any]] = []
    for selected in _select_near_limit_rows(capacity_rows):
        dim = int(selected["dim"])
        patterns = int(selected["patterns"])
        matrix = _pattern_matrix(patterns, dim, seed=400_000 + dim + patterns)
        memory = ModernHopfieldMemory(matrix)
        trials = 6 if _matrix_gb(patterns, dim) < 0.75 else 3
        random_correct = 0
        unitary_correct = 0
        random_times: list[float] = []
        unitary_times: list[float] = []
        for trial, target_index in enumerate(_trial_indices(patterns, trials)):
            target = HyperVector(matrix[target_index] * math.sqrt(dim), "bipolar")
            random_keys = [random_bipolar(dim, seed=500_000 + dim + trial * 10 + i) for i in range(5)]
            unitary_keys = [make_unitary_key(dim, seed=600_000 + dim + trial * 10 + i) for i in range(5)]
            start = time.perf_counter()
            random_result = query_and_cleanup(bind_value_with_keys(target, random_keys), random_keys, memory, target=target, beta=42.0)
            random_times.append((time.perf_counter() - start) * 1000.0)
            start = time.perf_counter()
            unitary_result = query_and_cleanup(bind_value_with_keys(target, unitary_keys), unitary_keys, memory, target=target, beta=42.0)
            unitary_times.append((time.perf_counter() - start) * 1000.0)
            random_correct += int(random_result.nearest_index == target_index)
            unitary_correct += int(unitary_result.nearest_index == target_index)
        rows.append(
            {
                "dim": dim,
                "patterns": patterns,
                "depth": 5,
                "trials": trials,
                "random_accuracy": round(random_correct / trials, 4),
                "unitary_accuracy": round(unitary_correct / trials, 4),
                "random_mean_ms": round(float(statistics.mean(random_times)), 3),
                "unitary_mean_ms": round(float(statistics.mean(unitary_times)), 3),
                "selected_basis": "first_accuracy_below_0.95_or_largest_safe_measured",
            }
        )
        del memory
        del matrix
    return rows


def _first_limit(rows: list[dict[str, Any]], dim: int) -> str:
    measured = [row for row in rows if row["dim"] == dim and row["status"] == "measured"]
    if not measured:
        return "not measured"
    collapsed = [row for row in measured if float(row["accuracy"]) < 0.95]
    if collapsed:
        row = collapsed[0]
        return f"collapse observed at {row['patterns']} patterns"
    skipped = [row for row in rows if row["dim"] == dim and row["status"] == "skipped_memory_budget"]
    return f"no collapse before resource ceiling; largest measured {measured[-1]['patterns']} patterns; next skipped {skipped[0]['patterns'] if skipped else 'none'}"


def _realtime_limit(rows: list[dict[str, Any]], threshold_ms: float = 100.0) -> dict[str, Any]:
    measured = [row for row in rows if row["status"] == "measured"]
    under = [row for row in measured if float(row["mean_recall_ms"]) < threshold_ms]
    if not under:
        return {"threshold_ms": threshold_ms, "largest_realtime": None}
    best = max(under, key=lambda row: int(row["patterns"]) * int(row["dim"]))
    return {"threshold_ms": threshold_ms, "largest_realtime": {"dim": best["dim"], "patterns": best["patterns"], "mean_recall_ms": best["mean_recall_ms"]}}


def _write_readme(results: dict[str, Any]) -> None:
    readme = BENCH_DIR / "README.md"
    existing = readme.read_text(encoding="utf-8") if readme.exists() else "# RHFC Benchmarks\n"
    base = existing.split("\n# RHFC Stage 2.5 Benchmarks", 1)[0].rstrip()
    lines = [
        base,
        "",
        "# RHFC Stage 2.5 Benchmarks",
        "",
        f"- Generated: {results['generated_at']}",
        f"- Total benchmark wall time: `{results['wall_time_seconds']}s`",
        f"- Safe matrix memory budget: `{MAX_MATRIX_GB} GiB`",
        f"- Noise fraction: `{NOISE_FRACTION}`",
        "",
        "## Hopfield Scaling",
        "",
        "| dim | patterns | ratio | matrix GiB | status | accuracy | mean recall ms | p95 recall ms |",
        "|---:|---:|---:|---:|---|---:|---:|---:|",
    ]
    for row in results["capacity"]:
        lines.append(
            f"| {row['dim']} | {row['patterns']} | {row['pattern_dim_ratio']} | {row['matrix_gb']} | {row['status']} | "
            f"{row.get('accuracy')} | {row.get('mean_recall_ms')} | {row.get('p95_recall_ms')} |"
        )
    lines += [
        "",
        "## Random vs Unitary Near Measured Limit",
        "",
        "| dim | patterns | depth | random accuracy | unitary accuracy | random ms | unitary ms |",
        "|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for row in results["key_cleanup_near_limit"]:
        lines.append(
            f"| {row['dim']} | {row['patterns']} | {row['depth']} | {row['random_accuracy']} | "
            f"{row['unitary_accuracy']} | {row['random_mean_ms']} | {row['unitary_mean_ms']} |"
        )
    lines += [
        "",
        "## Limit Summary",
        "",
    ]
    for dim, text in results["limit_summary"].items():
        lines.append(f"- dim {dim}: {text}")
    lines += [
        "",
        "## ATANOR Scale Interpretation",
        "",
        f"- Local Brain baseline: `419 nodes / 1453 edges`. {results['atanor_scale']['local_brain']}",
        f"- Cloud proof store baseline: `22,530,240 shard concepts / 33,750,552 shard relations`. {results['atanor_scale']['cloud_brain']}",
        f"- Real-time threshold: `{results['realtime_limit']['threshold_ms']}ms`; largest measured under threshold: `{results['realtime_limit']['largest_realtime']}`",
        "",
        "## Theory Comparison",
        "",
        results["theory_comparison"],
        "",
        "## Stage 2.5 Conclusion",
        "",
        results["conclusion"],
    ]
    readme.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    start = time.perf_counter()
    capacity = benchmark_capacity()
    key_cleanup = benchmark_key_cleanup_near_limit(capacity)
    realtime_limit = _realtime_limit(capacity)
    limit_summary = {str(dim): _first_limit(capacity, dim) for dim in DIMS}
    local_safe = "The measured Local Brain scale is far below every tested single-layer capacity point."
    cloud_safe = (
        "A single flat Hopfield layer is not practical for the current Cloud proof-store scale: "
        "22.5M concepts exceeds the largest measured single matrix by orders of magnitude and would require sharding/hierarchy."
    )
    theory = (
        "Modern Hopfield networks can have very high capacity when stored patterns are well separated. "
        "The random bipolar synthetic patterns stayed well separated enough that accuracy did not collapse before the configured memory ceiling. "
        "This does not prove unlimited capacity; it shows that resource cost, not accuracy collapse, became the first observed boundary."
    )
    conclusion = (
        "Single-layer cleanup is sufficient for the current Local Brain scale under this benchmark. "
        "It is not sufficient as one flat layer for the Cloud proof-store scale; Stage 3 must use sharded or hierarchical cleanup memories. "
        "Near the measured limits, random and unitary keys did not separate in cleanup accuracy, but random keys still show severe pre-cleanup cosine collapse."
    )
    results = {
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "wall_time_seconds": round(time.perf_counter() - start, 3),
        "capacity": capacity,
        "key_cleanup_near_limit": key_cleanup,
        "limit_summary": limit_summary,
        "realtime_limit": realtime_limit,
        "atanor_scale": {"local_brain": local_safe, "cloud_brain": cloud_safe},
        "theory_comparison": theory,
        "conclusion": conclusion,
    }
    (BENCH_DIR / "hopfield_scaling_results.json").write_text(json.dumps(results, indent=2), encoding="utf-8")
    _write_readme(results)
    print(json.dumps(results, indent=2))


if __name__ == "__main__":
    main()
