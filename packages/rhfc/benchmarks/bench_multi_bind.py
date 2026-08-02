"""Stage 2 RHFC benchmarks: unitary keys, multi-bind noise, cleanup capacity."""

from __future__ import annotations

import json
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
from rhfc.fft_binding import bind, make_unitary_key, unbind
from rhfc.hypervector import HyperVector, cosine_similarity, random_bipolar
from rhfc.pipeline import bind_value_with_keys, query_and_cleanup, unbind_value_with_keys
from rhfc.resonator import compose_role_filler_pairs, factorize_role_filler_pairs

BENCH_DIR = Path(__file__).resolve().parent


def _restore_with_key(value: HyperVector, key: HyperVector) -> float:
    return cosine_similarity(value, unbind(bind(value, key), key))


def benchmark_unitary_vs_random(dim: int = 4096, trials: int = 24) -> dict[str, Any]:
    """Compare one-step random bipolar keys against unitary Fourier keys."""

    random_scores: list[float] = []
    unitary_scores: list[float] = []
    for trial in range(trials):
        value = random_bipolar(dim, seed=10_000 + trial)
        random_key = random_bipolar(dim, seed=20_000 + trial)
        unitary_key = make_unitary_key(dim, seed=30_000 + trial)
        random_scores.append(_restore_with_key(value, random_key))
        unitary_scores.append(_restore_with_key(value, unitary_key))
    return {
        "dim": dim,
        "trials": trials,
        "random_mean": round(float(statistics.mean(random_scores)), 6),
        "random_min": round(float(min(random_scores)), 6),
        "unitary_mean": round(float(statistics.mean(unitary_scores)), 6),
        "unitary_min": round(float(min(unitary_scores)), 6),
        "mean_delta": round(float(statistics.mean(unitary_scores) - statistics.mean(random_scores)), 6),
    }


def benchmark_multi_bind_noise(dim: int = 4096, trials: int = 16, max_depth: int = 5) -> list[dict[str, Any]]:
    """Measure recovery cosine as bind depth increases."""

    rows: list[dict[str, Any]] = []
    for depth in range(1, max_depth + 1):
        random_scores: list[float] = []
        unitary_scores: list[float] = []
        for trial in range(trials):
            value = random_bipolar(dim, seed=40_000 + depth * 100 + trial)
            random_keys = [random_bipolar(dim, seed=50_000 + depth * 1000 + trial * 10 + i) for i in range(depth)]
            unitary_keys = [make_unitary_key(dim, seed=60_000 + depth * 1000 + trial * 10 + i) for i in range(depth)]
            random_scores.append(cosine_similarity(value, unbind_value_with_keys(bind_value_with_keys(value, random_keys), random_keys)))
            unitary_scores.append(cosine_similarity(value, unbind_value_with_keys(bind_value_with_keys(value, unitary_keys), unitary_keys)))
        rows.append(
            {
                "depth": depth,
                "random_mean": round(float(statistics.mean(random_scores)), 6),
                "random_min": round(float(min(random_scores)), 6),
                "unitary_mean": round(float(statistics.mean(unitary_scores)), 6),
                "unitary_min": round(float(min(unitary_scores)), 6),
            }
        )
    return rows


def benchmark_cleanup_after_multibind(dim: int = 2048, trials: int = 20, max_depth: int = 5, candidates_count: int = 512) -> list[dict[str, Any]]:
    """Measure exact recovery after unbinding and Hopfield cleanup."""

    rows: list[dict[str, Any]] = []
    candidates = [random_bipolar(dim, seed=70_000 + i) for i in range(candidates_count)]
    memory = ModernHopfieldMemory.store(candidates)
    for depth in range(1, max_depth + 1):
        random_correct = 0
        unitary_correct = 0
        random_cosines: list[float] = []
        unitary_cosines: list[float] = []
        for trial in range(trials):
            target_index = (trial * 37 + depth) % candidates_count
            target = candidates[target_index]
            random_keys = [random_bipolar(dim, seed=80_000 + depth * 1000 + trial * 10 + i) for i in range(depth)]
            unitary_keys = [make_unitary_key(dim, seed=90_000 + depth * 1000 + trial * 10 + i) for i in range(depth)]
            random_result = query_and_cleanup(bind_value_with_keys(target, random_keys), random_keys, memory, target=target, beta=36.0)
            unitary_result = query_and_cleanup(bind_value_with_keys(target, unitary_keys), unitary_keys, memory, target=target, beta=36.0)
            random_correct += int(random_result.nearest_index == target_index)
            unitary_correct += int(unitary_result.nearest_index == target_index)
            random_cosines.append(float(random_result.target_cosine or 0.0))
            unitary_cosines.append(float(unitary_result.target_cosine or 0.0))
        rows.append(
            {
                "depth": depth,
                "candidate_patterns": candidates_count,
                "random_accuracy": round(random_correct / trials, 4),
                "random_mean_cosine": round(float(statistics.mean(random_cosines)), 6),
                "unitary_accuracy": round(unitary_correct / trials, 4),
                "unitary_mean_cosine": round(float(statistics.mean(unitary_cosines)), 6),
            }
        )
    return rows


def benchmark_hopfield_capacity(dim: int = 1024) -> list[dict[str, Any]]:
    """Extend cleanup capacity measurement until degradation appears."""

    rows: list[dict[str, Any]] = []
    for count in [512, 1024, 2048, 4096]:
        trials = 16 if count <= 1024 else 8
        patterns = [random_bipolar(dim, seed=100_000 + count * 10 + i) for i in range(count)]
        start = time.perf_counter()
        memory = ModernHopfieldMemory.store(patterns)
        build_ms = (time.perf_counter() - start) * 1000.0
        correct = 0
        for trial in range(trials):
            target_index = (trial * 131 + 17) % count
            target = patterns[target_index]
            noisy = target.values.copy()
            noisy[: min(160, dim // 4)] *= -1.0
            recalled = memory.recall(HyperVector(noisy, "bipolar"), beta=36.0)
            correct += int(memory.nearest_index(recalled) == target_index)
        rows.append(
            {
                "patterns": count,
                "dim": dim,
                "trials": trials,
                "accuracy": round(correct / trials, 4),
                "build_ms": round(build_ms, 3),
                "pattern_dim_ratio": round(count / dim, 4),
            }
        )
    return rows


def benchmark_resonator_dictionary(dim: int = 2048) -> list[dict[str, Any]]:
    """Measure closed-dictionary factorization as dictionary size grows."""

    rows: list[dict[str, Any]] = []
    for dictionary_size in [10, 100, 1000]:
        trials = 10 if dictionary_size < 1000 else 5
        successes = 0
        recovered_counts = []
        fillers = {f"item{i}": random_bipolar(dim, seed=120_000 + dictionary_size * 10 + i) for i in range(dictionary_size)}
        for trial in range(trials):
            roles = {f"role{i}": random_bipolar(dim, seed=130_000 + dictionary_size * 100 + trial * 10 + i) for i in range(3)}
            expected = [(f"role{i}", f"item{(trial * 17 + i * 23) % dictionary_size}") for i in range(3)]
            composite = compose_role_filler_pairs([(roles[r], fillers[f]) for r, f in expected])
            recovered = factorize_role_filler_pairs(composite, roles, fillers, max_iter=6, threshold=0.11)
            pairs = {(item.role, item.filler) for item in recovered}
            successes += int(all(pair in pairs for pair in expected))
            recovered_counts.append(len(recovered))
        rows.append(
            {
                "dictionary_size": dictionary_size,
                "trials": trials,
                "success_rate": round(successes / trials, 4),
                "mean_recovered_pairs": round(float(statistics.mean(recovered_counts)), 3),
            }
        )
    return rows


def _write_stage2_readme(results: dict[str, Any]) -> None:
    readme = BENCH_DIR / "README.md"
    existing = readme.read_text(encoding="utf-8") if readme.exists() else "# RHFC Stage 1 Benchmarks\n"
    base = existing.split("\n# RHFC Stage 2 Benchmarks", 1)[0].rstrip()
    lines = [
        base,
        "",
        "# RHFC Stage 2 Benchmarks",
        "",
        f"- Generated: {results['generated_at']}",
        "- torchhd install: failed (`No matching distribution found for torchhd` on this Python 3.13 environment)",
        "",
        "## Unitary Key vs Random Key",
        "",
        "| dim | trials | random mean | random min | unitary mean | unitary min | mean delta |",
        "|---:|---:|---:|---:|---:|---:|---:|",
    ]
    unit = results["unitary_vs_random"]
    lines.append(f"| {unit['dim']} | {unit['trials']} | {unit['random_mean']} | {unit['random_min']} | {unit['unitary_mean']} | {unit['unitary_min']} | {unit['mean_delta']} |")
    lines += [
        "",
        "## Multi-Bind Noise Accumulation",
        "",
        "| depth | random mean | random min | unitary mean | unitary min |",
        "|---:|---:|---:|---:|---:|",
    ]
    for row in results["multi_bind_noise"]:
        lines.append(f"| {row['depth']} | {row['random_mean']} | {row['random_min']} | {row['unitary_mean']} | {row['unitary_min']} |")
    lines += [
        "",
        "## Cleanup After Multi-Bind",
        "",
        "| depth | patterns | random accuracy | random cosine | unitary accuracy | unitary cosine |",
        "|---:|---:|---:|---:|---:|---:|",
    ]
    for row in results["cleanup_after_multibind"]:
        lines.append(f"| {row['depth']} | {row['candidate_patterns']} | {row['random_accuracy']} | {row['random_mean_cosine']} | {row['unitary_accuracy']} | {row['unitary_mean_cosine']} |")
    lines += [
        "",
        "## Extended Hopfield Capacity",
        "",
        "| patterns | dim | ratio | trials | accuracy | build ms |",
        "|---:|---:|---:|---:|---:|---:|",
    ]
    for row in results["hopfield_capacity_extended"]:
        lines.append(f"| {row['patterns']} | {row['dim']} | {row['pattern_dim_ratio']} | {row['trials']} | {row['accuracy']} | {row['build_ms']} |")
    lines += [
        "",
        "## Resonator Dictionary Scaling",
        "",
        "| dictionary size | trials | success rate | mean recovered pairs |",
        "|---:|---:|---:|---:|",
    ]
    for row in results["resonator_dictionary"]:
        lines.append(f"| {row['dictionary_size']} | {row['trials']} | {row['success_rate']} | {row['mean_recovered_pairs']} |")
    lines += [
        "",
        "## Stage 2 Conclusion",
        "",
        results["conclusion"],
    ]
    readme.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    results: dict[str, Any] = {
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "unitary_vs_random": benchmark_unitary_vs_random(),
        "multi_bind_noise": benchmark_multi_bind_noise(),
        "cleanup_after_multibind": benchmark_cleanup_after_multibind(),
        "hopfield_capacity_extended": benchmark_hopfield_capacity(),
        "resonator_dictionary": benchmark_resonator_dictionary(),
    }
    depth3 = next(row for row in results["cleanup_after_multibind"] if row["depth"] == 3)
    if depth3["unitary_accuracy"] >= 0.95:
        conclusion = (
            "Yes, conditionally: with unitary keys plus Hopfield cleanup, the RHFC pipeline supports "
            f"SQC-like depth-3 binding at practical accuracy in this benchmark "
            f"({depth3['unitary_accuracy']} exact recovery over {depth3['candidate_patterns']} candidates). "
            "Random bipolar keys alone remain unsuitable for deep binding."
        )
    else:
        conclusion = (
            "No: even with unitary keys and cleanup, depth-3 binding did not reach the 95% practical "
            f"accuracy target in this benchmark ({depth3['unitary_accuracy']})."
        )
    results["conclusion"] = conclusion
    (BENCH_DIR / "multi_bind_results.json").write_text(json.dumps(results, indent=2), encoding="utf-8")
    _write_stage2_readme(results)
    print(json.dumps(results, indent=2))


if __name__ == "__main__":
    main()
