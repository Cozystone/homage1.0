"""Run RHFC Stage 1 correctness benchmarks and write measured results."""

from __future__ import annotations

import csv
import json
import platform
import statistics
import sys
import time
from pathlib import Path
from typing import Any

import networkx as nx
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from rhfc.cleanup_memory import ModernHopfieldMemory
from rhfc.fft_binding import bind, unbind
from rhfc.graph_spectral import propagate
from rhfc.hypervector import HyperVector, cosine_similarity, random_bipolar
from rhfc.resonator import compose_role_filler_pairs, factorize_role_filler_pairs
from rhfc.sheaf_consistency import consistency_score, flag_contradictions

BENCH_DIR = Path(__file__).resolve().parent


def _cpu_label() -> str:
    return platform.processor() or platform.machine() or "unknown-cpu"


def bench_bind_unbind() -> list[dict[str, Any]]:
    """Measure bind/unbind cosine similarity across dimensions."""

    rows: list[dict[str, Any]] = []
    for dim in [256, 1024, 4096, 10_000]:
        scores = []
        elapsed = []
        for trial in range(8):
            a = random_bipolar(dim, seed=10_000 + dim + trial)
            b = random_bipolar(dim, seed=20_000 + dim + trial)
            start = time.perf_counter()
            recovered = unbind(bind(a, b), b)
            elapsed.append((time.perf_counter() - start) * 1000.0)
            scores.append(cosine_similarity(a, recovered))
        rows.append(
            {
                "dim": dim,
                "mean_cosine": round(float(statistics.mean(scores)), 6),
                "min_cosine": round(float(min(scores)), 6),
                "mean_ms": round(float(statistics.mean(elapsed)), 4),
            }
        )
    return rows


def bench_hopfield_capacity() -> list[dict[str, Any]]:
    """Measure single-step cleanup accuracy as pattern count increases."""

    rows: list[dict[str, Any]] = []
    dim = 1024
    for count in [8, 16, 32, 64, 128, 256]:
        correct = 0
        trials = 12
        patterns = [random_bipolar(dim, seed=30_000 + count * 100 + i) for i in range(count)]
        memory = ModernHopfieldMemory.store(patterns)
        for trial in range(trials):
            target_idx = (trial * 7) % count
            target = patterns[target_idx]
            noisy = target.values.copy()
            flips = min(dim // 5, 120)
            noisy[:flips] *= -1.0
            recalled = memory.recall(HyperVector(noisy, "bipolar"), beta=28.0)
            if memory.nearest_index(recalled) == target_idx:
                correct += 1
        rows.append({"patterns": count, "dim": dim, "accuracy": round(correct / trials, 4)})
    return rows


def bench_resonator() -> list[dict[str, Any]]:
    """Measure role/filler recovery success by number of bound elements."""

    rows: list[dict[str, Any]] = []
    dim = 4096
    for element_count in [2, 3, 5]:
        successes = 0
        trials = 10
        iterations = []
        for trial in range(trials):
            roles = {f"role{i}": random_bipolar(dim, seed=40_000 + trial * 100 + i) for i in range(element_count)}
            fillers = {f"item{i}": random_bipolar(dim, seed=50_000 + trial * 100 + i) for i in range(element_count + 3)}
            expected = [(f"role{i}", f"item{i}") for i in range(element_count)]
            composite = compose_role_filler_pairs([(roles[r], fillers[f]) for r, f in expected])
            recovered = factorize_role_filler_pairs(composite, roles, fillers, threshold=0.13, max_iter=6)
            recovered_pairs = {(item.role, item.filler) for item in recovered}
            if all(pair in recovered_pairs for pair in expected):
                successes += 1
            if recovered:
                iterations.append(max(item.iterations for item in recovered))
        rows.append(
            {
                "bound_elements": element_count,
                "trials": trials,
                "success_rate": round(successes / trials, 4),
                "mean_iterations": round(float(statistics.mean(iterations)) if iterations else 0.0, 2),
            }
        )
    return rows


def bench_graph_spectral() -> dict[str, Any]:
    """Check that PPR activation follows graph locality on a 100-node graph."""

    graph = nx.path_graph(100)
    scores = propagate(graph, [50], alpha=0.85)
    return {
        "seed": round(scores[50], 8),
        "distance_1": round(scores[49], 8),
        "distance_5": round(scores[45], 8),
        "distance_20": round(scores[30], 8),
        "locality_order_holds": bool(scores[50] > scores[49] > scores[45] > scores[30]),
    }


def bench_sheaf() -> dict[str, Any]:
    """Score one consistent edge and one contradictory edge."""

    graph = nx.Graph()
    graph.add_edge("consistent_a", "consistent_b")
    graph.add_edge("claim_a", "claim_b")
    states = {
        "consistent_a": np.array([1.0, 0.0]),
        "consistent_b": np.array([0.95, 0.05]),
        "claim_a": np.array([1.0, 0.0]),
        "claim_b": np.array([-1.0, 0.0]),
    }
    scores = consistency_score(graph, states)
    contradictions = flag_contradictions(scores, threshold=0.5)
    return {
        "consistent_edge_score": round(scores[("consistent_a", "consistent_b")], 6),
        "contradiction_edge_score": round(scores[("claim_a", "claim_b")], 6),
        "flagged_edges": [list(edge) for edge in contradictions],
        "contradiction_higher": bool(scores[("claim_a", "claim_b")] > scores[("consistent_a", "consistent_b")]),
    }


def bench_end_to_end() -> dict[str, Any]:
    """Measure one hypervector -> bind -> store -> recall pipeline."""

    dim = 4096
    patterns = [random_bipolar(dim, seed=60_000 + i) for i in range(64)]
    role = random_bipolar(dim, seed=70_000)
    key = random_bipolar(dim, seed=70_001)
    start = time.perf_counter()
    composite = bind(patterns[7], role)
    recovered = unbind(composite, role)
    memory = ModernHopfieldMemory.store(patterns + [key])
    recalled = memory.recall(recovered, beta=32.0)
    elapsed_ms = (time.perf_counter() - start) * 1000.0
    return {
        "dim": dim,
        "patterns": 65,
        "elapsed_ms": round(elapsed_ms, 4),
        "target_cosine": round(cosine_similarity(patterns[7], recalled), 6),
        "nearest_index": memory.nearest_index(recalled),
    }


def _write_markdown(results: dict[str, Any]) -> None:
    lines = [
        "# RHFC Stage 1 Benchmarks",
        "",
        f"- Generated: {results['generated_at']}",
        f"- CPU label: `{results['cpu']}`",
        f"- Python: `{platform.python_version()}`",
        "",
        "## Bind / Unbind Accuracy",
        "",
        "| dim | mean cosine | min cosine | mean ms |",
        "|---:|---:|---:|---:|",
    ]
    for row in results["bind_unbind"]:
        lines.append(f"| {row['dim']} | {row['mean_cosine']} | {row['min_cosine']} | {row['mean_ms']} |")
    lines += [
        "",
        "## Hopfield Cleanup Capacity",
        "",
        "| patterns | dim | accuracy |",
        "|---:|---:|---:|",
    ]
    for row in results["hopfield_capacity"]:
        lines.append(f"| {row['patterns']} | {row['dim']} | {row['accuracy']} |")
    lines += [
        "",
        "## Resonator Factorization",
        "",
        "| bound elements | trials | success rate | mean iterations |",
        "|---:|---:|---:|---:|",
    ]
    for row in results["resonator"]:
        lines.append(f"| {row['bound_elements']} | {row['trials']} | {row['success_rate']} | {row['mean_iterations']} |")
    graph = results["graph_spectral"]
    sheaf = results["sheaf_consistency"]
    e2e = results["end_to_end"]
    lines += [
        "",
        "## Graph Spectral Propagation",
        "",
        f"- PPR seed score: `{graph['seed']}`",
        f"- Distance 1 / 5 / 20: `{graph['distance_1']}` / `{graph['distance_5']}` / `{graph['distance_20']}`",
        f"- Locality order holds: `{graph['locality_order_holds']}`",
        "",
        "## Sheaf Consistency",
        "",
        f"- Consistent edge score: `{sheaf['consistent_edge_score']}`",
        f"- Contradiction edge score: `{sheaf['contradiction_edge_score']}`",
        f"- Flagged edges: `{sheaf['flagged_edges']}`",
        "",
        "## End-to-End Pipeline",
        "",
        f"- dim: `{e2e['dim']}`",
        f"- patterns: `{e2e['patterns']}`",
        f"- elapsed_ms: `{e2e['elapsed_ms']}`",
        f"- target_cosine: `{e2e['target_cosine']}`",
        f"- nearest_index: `{e2e['nearest_index']}`",
        "",
        "## Notes",
        "",
        "- These numbers are measured on the local CPU runtime used by Codex.",
        "- No external LLM/sLLM call is used.",
        "- `torchhd` is not required; Stage 1 uses NumPy/SciPy implementations.",
    ]
    (BENCH_DIR / "README.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    results = {
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "cpu": _cpu_label(),
        "bind_unbind": bench_bind_unbind(),
        "hopfield_capacity": bench_hopfield_capacity(),
        "resonator": bench_resonator(),
        "graph_spectral": bench_graph_spectral(),
        "sheaf_consistency": bench_sheaf(),
        "end_to_end": bench_end_to_end(),
    }
    (BENCH_DIR / "correctness_results.json").write_text(json.dumps(results, indent=2), encoding="utf-8")
    with (BENCH_DIR / "bind_unbind_accuracy.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=["dim", "mean_cosine", "min_cosine", "mean_ms"])
        writer.writeheader()
        writer.writerows(results["bind_unbind"])
    _write_markdown(results)
    print(json.dumps(results, indent=2))


if __name__ == "__main__":
    main()
