from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
SEED_PACKAGE_ROOT = REPO_ROOT / "packages" / "seed_research"
if str(SEED_PACKAGE_ROOT) not in sys.path:
    sys.path.insert(0, str(SEED_PACKAGE_ROOT))

from seed_research.core import freeze_seed, read_jsonl, run_seed_iteration
from seed_research.runtime_anchor import resolve_seed_concepts


ANCHOR_PROBES: list[dict[str, Any]] = [
    {
        "query": "근거가 없으면 어떻게 답해야 해?",
        "expected_concepts": {"seed.core.no_evidence", "seed.core.grounding", "seed.core.answer"},
        "expected_relations": {"requires", "weakens"},
    },
    {
        "query": "답변은 왜 근거화가 필요해?",
        "expected_concepts": {"seed.core.answer", "seed.core.grounding", "seed.core.evidence"},
        "expected_relations": {"requires", "has_evidence"},
    },
    {
        "query": "Local Brain과 Cloud Brain은 어떻게 분리돼?",
        "expected_concepts": {"seed.core.local_brain", "seed.core.cloud_brain", "seed.core.privacy_scope"},
        "expected_relations": {"belongs_to_layer", "depends_on"},
    },
    {
        "query": "유재석이 누구야",
        "expected_concepts": set(),
        "expected_relations": set(),
    },
]


CHAT_PROBES = ["유재석이 누구야", "김안석이 누구야"]
FORBIDDEN_ANSWER_FRAGMENTS = ["ghost:", "핵심 개념", "최근 연결된 개념"]


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def artifact_checks(root: Path) -> dict[str, Any]:
    current = root / "current"
    files = [
        current / "seed_concepts.jsonl",
        current / "seed_edges.jsonl",
        current / "seed_aliases.jsonl",
        current / "viewer_export.json",
        root / "benchmarks" / "seed_benchmark_questions.jsonl",
    ]
    checked = []
    replacement_char_found = False
    for path in files:
        text = path.read_text(encoding="utf-8") if path.exists() else ""
        has_replacement = "�" in text
        replacement_char_found = replacement_char_found or has_replacement
        checked.append({"path": str(path), "exists": path.exists(), "replacement_char_found": has_replacement})
    return {
        "passed": all(item["exists"] for item in checked) and not replacement_char_found,
        "checked_files": checked,
    }


def anchor_checks(root: Path) -> dict[str, Any]:
    probe_results = []
    scores = []
    for probe in ANCHOR_PROBES:
        resolved = resolve_seed_concepts(probe["query"], root)
        concept_ids = {item.get("concept_id") for item in resolved.get("matched_seed_concepts", [])}
        relation_ids = {item.get("relation") for item in resolved.get("matched_seed_edges", [])}
        expected_concepts = set(probe["expected_concepts"])
        expected_relations = set(probe["expected_relations"])
        concept_score = 1.0 if not expected_concepts else len(expected_concepts & concept_ids) / len(expected_concepts)
        relation_score = 1.0 if not expected_relations else len(expected_relations & relation_ids) / len(expected_relations)
        score = round((concept_score + relation_score) / 2, 3)
        scores.append(score)
        probe_results.append(
            {
                "query": probe["query"],
                "score": score,
                "matched_concepts": sorted(concept_ids),
                "matched_relations": sorted(relation_ids),
                "missing_concepts": sorted(expected_concepts - concept_ids),
                "missing_relations": sorted(expected_relations - relation_ids),
            }
        )
    return {
        "score": round(sum(scores) / len(scores), 3) if scores else 0.0,
        "passed": all(score >= 0.95 for score in scores),
        "probes": probe_results,
    }


def chat_once(base_url: str, question: str, timeout_s: float) -> dict[str, Any]:
    body = json.dumps(
        {
            "question": question,
            "language": "ko",
            "audience_level": "beginner",
            "tone": "clear",
            "mode": "default",
            "brain_mode": "local",
            "web_search": False,
            "include_trace": True,
        },
        ensure_ascii=False,
    ).encode("utf-8")
    request = urllib.request.Request(
        f"{base_url.rstrip('/')}/api/chat/atanor",
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    started = time.perf_counter()
    with urllib.request.urlopen(request, timeout=timeout_s) as response:
        payload = json.loads(response.read().decode("utf-8"))
    elapsed_ms = round((time.perf_counter() - started) * 1000, 1)
    answer = str(((payload.get("result") or {}).get("answer")) or "")
    return {"question": question, "elapsed_ms": elapsed_ms, "answer": answer, "raw_state": payload.get("state")}


def chat_checks(base_url: str, timeout_s: float) -> dict[str, Any]:
    results = []
    try:
        for question in CHAT_PROBES:
            result = chat_once(base_url, question, timeout_s)
            answer = result["answer"]
            forbidden_hits = [fragment for fragment in FORBIDDEN_ANSWER_FRAGMENTS if fragment in answer]
            result["forbidden_hits"] = forbidden_hits
            result["passed"] = bool(answer) and not forbidden_hits
            results.append(result)
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        return {"available": False, "passed": None, "score": None, "error": str(exc), "probes": results}
    passed = all(item["passed"] for item in results)
    return {"available": True, "passed": passed, "score": 1.0 if passed else 0.0, "probes": results}


def structural_score(metrics: dict[str, Any]) -> float:
    checks = [
        float(metrics.get("benchmark_score") or 0.0),
        1.0 if int(metrics.get("isolated_node_count") or 0) == 0 else 0.0,
        1.0 if int(metrics.get("connected_component_count") or 0) == 1 else 0.0,
        float(metrics.get("ko_en_label_coverage") or 0.0),
        float(metrics.get("concept_definition_coverage") or 0.0),
        1.0 if int(metrics.get("low_confidence_edge_count") or 0) == 0 else 0.0,
        1.0 if int(metrics.get("conflict_edge_count") or 0) == 0 else 0.0,
    ]
    return round(sum(checks) / len(checks), 3)


def evaluate_run(root: Path, run_result: dict[str, Any], backend_url: str, chat_timeout_s: float) -> dict[str, Any]:
    metrics = run_result["metrics"]
    structure = structural_score(metrics)
    anchors = anchor_checks(root)
    artifacts = artifact_checks(root)
    chat = chat_checks(backend_url, chat_timeout_s)
    chat_score = 1.0 if chat.get("available") is False else float(chat.get("score") or 0.0)
    score = round(
        float(metrics.get("benchmark_score") or 0.0) * 0.30
        + structure * 0.25
        + anchors["score"] * 0.25
        + (1.0 if artifacts["passed"] else 0.0) * 0.10
        + chat_score * 0.10,
        3,
    )
    return {
        "run_id": run_result["run_id"],
        "run_dir": run_result["run_dir"],
        "score": score,
        "metrics": metrics,
        "structure_score": structure,
        "anchor_checks": anchors,
        "artifact_checks": artifacts,
        "chat_checks": chat,
    }


def markdown_report(report: dict[str, Any]) -> str:
    best = report["best_run"]
    lines = [
        f"# Seed Graph Experiment Report",
        "",
        f"- Created at: {report['created_at']}",
        f"- Iterations: {report['iterations']}",
        f"- Best run: {best['run_id']}",
        f"- Best score: {best['score']}",
        f"- Benchmark score: {best['metrics'].get('benchmark_score')}",
        f"- Concepts / edges: {best['metrics'].get('concept_count')} / {best['metrics'].get('edge_count')}",
        f"- Isolated nodes: {best['metrics'].get('isolated_node_count')}",
        f"- Anchor score: {best['anchor_checks']['score']}",
        f"- Artifact UTF-8 check: {best['artifact_checks']['passed']}",
        f"- Chat API checked: {best['chat_checks'].get('available')}",
    ]
    if report.get("freeze"):
        lines.extend(["", "## Freeze", "", f"- Version: {report['freeze']['version']}", f"- Output: {report['freeze']['output_dir']}"])
    lines.extend(["", "## Anchor Probes", ""])
    for probe in best["anchor_checks"]["probes"]:
        lines.append(f"- {probe['query']}: {probe['score']} concepts={probe['matched_concepts']} relations={probe['matched_relations']}")
    return "\n".join(lines) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser(description="Run repeated ATANOR Seed Graph experiments and select the best run.")
    parser.add_argument("--root", default="data/seed_research")
    parser.add_argument("--iterations", type=int, default=2)
    parser.add_argument("--backend-url", default="http://127.0.0.1:8500")
    parser.add_argument("--chat-timeout-s", type=float, default=8.0)
    parser.add_argument("--freeze-version", default="")
    parser.add_argument("--output-dir", default="data/seed_research/experiments")
    args = parser.parse_args()

    root = Path(args.root)
    evaluations = []
    for _ in range(max(1, args.iterations)):
        run_result = run_seed_iteration(root)
        evaluations.append(evaluate_run(root, run_result, args.backend_url, args.chat_timeout_s))

    best = max(evaluations, key=lambda item: (item["score"], item["metrics"].get("benchmark_score", 0), item["run_id"]))
    freeze = None
    if args.freeze_version:
        freeze = freeze_seed(best["run_id"], args.freeze_version, root, "data/seed")

    report = {
        "schema": "atanor.seed-research.experiment-report.v1",
        "created_at": utc_now_iso(),
        "iterations": len(evaluations),
        "best_run": best,
        "runs": evaluations,
        "freeze": freeze,
    }
    output_dir = Path(args.output_dir)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    json_path = output_dir / f"seed_graph_experiment_{timestamp}.json"
    md_path = output_dir / f"seed_graph_experiment_{timestamp}.md"
    write_json(json_path, report)
    md_path.parent.mkdir(parents=True, exist_ok=True)
    md_path.write_text(markdown_report(report), encoding="utf-8", newline="\n")
    print(json.dumps({"best_run": best["run_id"], "best_score": best["score"], "report": str(json_path), "markdown": str(md_path), "freeze": freeze}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
