# -*- coding: utf-8 -*-
"""Unsigned bAbI development measurement with a fresh candidate subprocess.

The test split is refused.  Train/validation bytes are bound before parsing;
only context and question text are sent to the candidate worker; grading stays
in the parent process.  The resulting checksum receipt is reproducibility
evidence, not an external signature, hidden-set result, or E5 claim.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
import time
import uuid
from pathlib import Path
from typing import Any, Iterator, Mapping


REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

from packages.eval_evidence.receipt import (  # noqa: E402
    BENCHMARK_EVIDENCE_KIND,
    BENCHMARK_EVIDENCE_SCHEMA,
    BenchmarkEvidenceError,
    aggregate_items,
    bind_files,
    canonical_json_bytes,
    ensure_safe_report_output,
    environment_record,
    finalize_manifest,
    item_id,
    selection_record,
    strict_json_bytes,
    utc_now,
    verify_manifest,
    write_manifest_exclusive,
)
from scripts.babi_candidate_worker import (  # noqa: E402
    RESULT_SCHEMA as WORKER_RESULT_SCHEMA,
    SCHEMA as WORKER_REQUEST_SCHEMA,
)


DATA = REPO / "data" / "external_benchmarks" / "tasks_1-20_v1-2" / "en-valid-10k"
REPORTS = REPO / "reports" / "benchmarks"
WORKER = REPO / "scripts" / "babi_candidate_worker.py"
TASKS = {
    1: "single-fact",
    2: "two-facts",
    3: "three-facts",
    4: "two-arg rel",
    5: "three-arg rel",
    6: "yes/no",
    7: "counting",
    8: "lists/sets",
    9: "simple negation",
    10: "indefinite",
    11: "basic coref",
    12: "conjunction",
    13: "compound coref",
    14: "time reasoning",
    15: "basic deduction",
    16: "basic induction",
    17: "positional",
    18: "size reasoning",
    19: "path finding",
    20: "agent motivation",
}
GRADING_RULE = (
    "lowercase; punctuation/articles removed; whitespace collapsed; yes/no "
    "uses first normalized token; comma answers use normalized set equality"
)

_EVALUATOR_PATHS = (
    "packages/__init__.py",
    "packages/eval_evidence/__init__.py",
    "packages/eval_evidence/receipt.py",
    "scripts/babi_external_harness.py",
)
_CANDIDATE_PATHS = tuple(
    sorted(
        {
            "data/lexicon/english_vocab.json",
            "packages/__init__.py",
            "packages/eval_evidence/__init__.py",
            "packages/eval_evidence/receipt.py",
            "scripts/babi_candidate_worker.py",
            *{
                path.relative_to(REPO).as_posix()
                for path in (REPO / "packages" / "situation_model").glob("*.py")
            },
        }
    )
)


def _norm(value: str) -> str:
    import re

    text = re.sub(r"[^\w,\s]", " ", (value or "").lower())
    text = re.sub(r"\b(the|a|an)\b", " ", text)
    return " ".join(text.split())


def grade(prediction: str | None, gold: str) -> str:
    """Apply the frozen normalized generative scoring rule."""
    if prediction is None:
        return "abstain"
    normalized_gold = _norm(gold)
    normalized_prediction = _norm(prediction)
    if gold.lower() in {"yes", "no"}:
        first = (
            normalized_prediction.split()[0]
            if normalized_prediction.split()
            else ""
        )
        return "correct" if first == gold.lower() else "wrong"
    if "," in gold:
        gold_set = {part.strip() for part in normalized_gold.split(",")}
        prediction_set = {
            part.strip() for part in normalized_prediction.split(",")
        }
        return "correct" if prediction_set == gold_set else "wrong"
    return "correct" if normalized_prediction == normalized_gold else "wrong"


def parse_task_text(text: str) -> Iterator[tuple[str, str, str]]:
    """Yield context, question, and gold from one already-bound text snapshot."""
    facts: list[str] = []
    for line_number, line in enumerate(text.splitlines(), start=1):
        if not line.strip():
            continue
        story_id, separator, rest = line.partition(" ")
        if not separator or not story_id.isdigit():
            raise BenchmarkEvidenceError(f"invalid bAbI line {line_number}")
        if int(story_id) == 1:
            facts = []
        if "\t" in rest:
            fields = rest.split("\t")
            if len(fields) < 2 or not fields[0].strip() or not fields[1].strip():
                raise BenchmarkEvidenceError(
                    f"invalid bAbI question line {line_number}"
                )
            yield " ".join(facts), fields[0].strip(), fields[1].strip()
        else:
            facts.append(rest.strip())


def parse_task(path: Path) -> Iterator[tuple[str, str, str]]:
    """Compatibility helper; run() uses bound bytes instead."""
    yield from parse_task_text(path.read_text(encoding="utf-8"))


def _dataset_paths(split: str) -> tuple[str, ...]:
    return tuple(
        f"data/external_benchmarks/tasks_1-20_v1-2/en-valid-10k/qa{task}_{split}.txt"
        for task in range(1, 21)
    )


def _new_run_id() -> str:
    stamp = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())
    return f"{stamp}.babi.{uuid.uuid4().hex[:12]}"


def _output_digest(prediction: str) -> str:
    return hashlib.sha256(prediction.encode("utf-8")).hexdigest()


def _read_bound_dataset(
    *,
    split: str,
    cap: int | None,
    scope: Mapping[str, Any],
) -> list[dict[str, Any]]:
    records = {
        record["path"]: record
        for record in scope["files"]
        if isinstance(record, Mapping)
    }
    selected: list[dict[str, Any]] = []
    for task, relative in enumerate(_dataset_paths(split), start=1):
        record = records.get(relative)
        if not isinstance(record, Mapping):
            raise BenchmarkEvidenceError(f"dataset scope missing {relative}")
        try:
            payload = (REPO / relative).read_bytes()
        except OSError as exc:
            raise BenchmarkEvidenceError(
                f"bAbI dataset unreadable: {Path(relative).name}"
            ) from exc
        if hashlib.sha256(payload).hexdigest() != record.get("sha256"):
            raise BenchmarkEvidenceError(
                f"bAbI bytes differ from bound snapshot: {Path(relative).name}"
            )
        try:
            text = payload.decode("utf-8")
        except UnicodeError as exc:
            raise BenchmarkEvidenceError(
                f"bAbI dataset is not UTF-8: {Path(relative).name}"
            ) from exc
        for ordinal, (context, question, gold) in enumerate(parse_task_text(text)):
            if cap is not None and ordinal >= cap:
                break
            selected.append(
                {
                    "task": task,
                    "ordinal": ordinal,
                    "context": context,
                    "question": question,
                    "gold": gold,
                    "item_id": item_id(
                        {
                            "benchmark": "babi-1.2",
                            "split": split,
                            "task": task,
                            "ordinal": ordinal,
                            "context": context,
                            "question": question,
                            "gold": gold,
                        }
                    ),
                }
            )
    if not selected:
        raise BenchmarkEvidenceError("bAbI selection is empty")
    return selected


def _validate_worker_result(value: dict[str, Any], expected: int) -> list[dict[str, Any]]:
    if frozenset(value) != {"schema_version", "items"}:
        raise BenchmarkEvidenceError("candidate worker result fields mismatch")
    if value.get("schema_version") != WORKER_RESULT_SCHEMA:
        raise BenchmarkEvidenceError("candidate worker result schema mismatch")
    rows = value.get("items")
    if not isinstance(rows, list) or len(rows) != expected:
        raise BenchmarkEvidenceError("candidate worker result count mismatch")
    for index, row in enumerate(rows):
        if (
            not isinstance(row, dict)
            or frozenset(row)
            != {"index", "emitted", "answer", "error_type", "latency_ms"}
            or row.get("index") != index
            or type(row.get("emitted")) is not bool
            or (
                row["emitted"]
                and (
                    not isinstance(row.get("answer"), str)
                    or row.get("error_type") is not None
                )
            )
            or (
                not row["emitted"]
                and row.get("answer") is not None
            )
            or type(row.get("latency_ms")) not in (int, float)
            or not 0 <= float(row["latency_ms"]) <= 86_400_000
        ):
            raise BenchmarkEvidenceError(f"candidate worker row {index} invalid")
    return rows


def _run_candidate(selected: list[dict[str, Any]]) -> list[dict[str, Any]]:
    request = {
        "schema_version": WORKER_REQUEST_SCHEMA,
        "items": [
            {
                "index": index,
                "context": row["context"],
                "question": row["question"],
            }
            for index, row in enumerate(selected)
        ],
    }
    environment = os.environ.copy()
    environment["PYTHONDONTWRITEBYTECODE"] = "1"
    try:
        completed = subprocess.run(
            [sys.executable, "-B", str(WORKER)],
            cwd=REPO,
            env=environment,
            input=canonical_json_bytes(request),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=900,
            check=False,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise BenchmarkEvidenceError(
            f"candidate worker failed to launch: {type(exc).__name__}"
        ) from exc
    if completed.returncode != 0:
        detail = completed.stderr.decode("utf-8", errors="replace")[-2000:]
        raise BenchmarkEvidenceError(
            f"candidate worker exited {completed.returncode}: {detail}"
        )
    result = strict_json_bytes(completed.stdout, label="bAbI candidate result")
    return _validate_worker_result(result, len(selected))


def _task_metrics(items: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], float]:
    per_task = []
    for task in range(1, 21):
        rows = [row for row in items if row["metadata"]["task"] == task]
        metrics = aggregate_items(rows)
        per_task.append(
            {
                "task": task,
                "name": TASKS[task],
                "n": metrics["n"],
                "strict_accuracy": metrics["strict_accuracy"],
                "coverage": metrics["coverage"],
                "fired_accuracy": metrics["fired_accuracy"],
            }
        )
    macro = round(
        sum(float(row["strict_accuracy"] or 0.0) for row in per_task)
        / len(per_task),
        12,
    )
    return per_task, macro


def validate_babi_semantics(
    manifest: Mapping[str, Any],
    *,
    require_current_dataset: bool = True,
) -> list[str]:
    """Recompute the declared bAbI item census from bound dataset bytes."""
    findings: list[str] = []
    benchmark = manifest.get("benchmark")
    config = manifest.get("config")
    if not isinstance(benchmark, Mapping) or benchmark.get("id") != (
        "facebook-babi-1.2-en-valid-10k"
    ):
        findings.append("bAbI benchmark identity mismatch")
        return findings
    if not isinstance(config, Mapping):
        return [*findings, "bAbI config missing"]
    split = benchmark.get("split")
    cap = config.get("cap_per_task")
    if split not in {"train", "valid"}:
        findings.append("bAbI split invalid")
        return findings
    if cap is not None and (type(cap) is not int or not 1 <= cap <= 1000):
        findings.append("bAbI cap invalid")
        return findings
    if config.get("all_items") is not (cap is None):
        findings.append("bAbI all_items mismatch")
    if config.get("candidate_payload") != "context_and_question_only":
        findings.append("bAbI candidate payload boundary mismatch")
    if config.get("grading_rule") != GRADING_RULE:
        findings.append("bAbI grading rule mismatch")
    source_paths = [
        row.get("path")
        for row in manifest.get("source", {}).get("files", [])
        if isinstance(row, Mapping)
    ]
    candidate_paths = [
        row.get("path")
        for row in manifest.get("candidate", {}).get("files", [])
        if isinstance(row, Mapping)
    ]
    dataset_paths = [
        row.get("path")
        for row in manifest.get("dataset", {}).get("files", [])
        if isinstance(row, Mapping)
    ]
    if tuple(source_paths) != tuple(sorted(_EVALUATOR_PATHS)):
        findings.append("bAbI evaluator source closure mismatch")
    if tuple(candidate_paths) != _CANDIDATE_PATHS:
        findings.append("bAbI candidate source closure mismatch")
    if tuple(dataset_paths) != tuple(sorted(_dataset_paths(str(split)))):
        findings.append("bAbI dataset inventory mismatch")
        return findings
    if require_current_dataset:
        try:
            expected = _read_bound_dataset(
                split=str(split),
                cap=cap,
                scope=manifest["dataset"],
            )
        except (BenchmarkEvidenceError, KeyError, TypeError) as exc:
            findings.append(f"bAbI dataset census failed: {type(exc).__name__}")
            return findings
        identifiers = [row["item_id"] for row in expected]
        actual = [
            row.get("item_id")
            for row in manifest.get("items", [])
            if isinstance(row, Mapping)
        ]
        if actual != identifiers:
            findings.append("bAbI items do not match the bound dataset census")
        selection = manifest.get("selection", {})
        if selection.get("item_ids") != identifiers:
            findings.append("bAbI selection does not match the bound dataset census")
        for expected_row, measured in zip(expected, manifest.get("items", [])):
            metadata = measured.get("metadata") if isinstance(measured, Mapping) else None
            if (
                not isinstance(metadata, Mapping)
                or metadata.get("task") != expected_row["task"]
                or metadata.get("ordinal") != expected_row["ordinal"]
            ):
                findings.append("bAbI item metadata census mismatch")
                break
    return findings


def run(
    *,
    cap: int | None,
    split: str,
    output: Path | None,
) -> tuple[dict[str, Any], Path]:
    if split == "test":
        raise ValueError("SEALED: bAbI test split is not authorized by this harness")
    if split not in {"train", "valid"}:
        raise ValueError("split must be train or valid")
    if cap is not None and (cap < 1 or cap > 1000):
        raise ValueError("cap must be in [1, 1000]")

    run_id = _new_run_id()
    destination = ensure_safe_report_output(
        REPO,
        output or REPORTS / f"babi_external_{run_id}.json",
    )
    source_before = bind_files(REPO, _EVALUATOR_PATHS)
    candidate_before = bind_files(REPO, _CANDIDATE_PATHS)
    dataset_paths = _dataset_paths(split)
    dataset_before = bind_files(REPO, dataset_paths)
    selected = _read_bound_dataset(
        split=split,
        cap=cap,
        scope=dataset_before,
    )
    started_at = utc_now()
    predictions = _run_candidate(selected)

    items: list[dict[str, Any]] = []
    for selected_row, prediction in zip(selected, predictions):
        if prediction["error_type"] is not None:
            status = "error"
            fired = False
            correct = False
            output_digest = None
        elif prediction["emitted"]:
            status = grade(prediction["answer"], selected_row["gold"])
            fired = True
            correct = status == "correct"
            output_digest = _output_digest(prediction["answer"])
        else:
            status = "abstain"
            fired = False
            correct = False
            output_digest = None
        items.append(
            {
                "item_id": selected_row["item_id"],
                "status": status,
                "fired": fired,
                "correct": correct,
                "output_sha256": output_digest,
                "latency_ms": prediction["latency_ms"],
                "metadata": {
                    "task": selected_row["task"],
                    "ordinal": selected_row["ordinal"],
                    "candidate_error_type": prediction["error_type"],
                },
            }
        )

    source_after = bind_files(REPO, _EVALUATOR_PATHS)
    candidate_after = bind_files(REPO, _CANDIDATE_PATHS)
    dataset_after = bind_files(REPO, dataset_paths)
    payload = {
        "schema_version": BENCHMARK_EVIDENCE_SCHEMA,
        "evidence_kind": BENCHMARK_EVIDENCE_KIND,
        "run_id": run_id,
        "started_at": started_at,
        "completed_at": utc_now(),
        "benchmark": {
            "id": "facebook-babi-1.2-en-valid-10k",
            "version": "1.2",
            "split": split,
            "license": "CC BY 3.0",
            "protocol": "normalized generative scoring; abstention counts as miss",
        },
        "config": {
            "cap_per_task": cap,
            "all_items": cap is None,
            "task_ids": list(range(1, 21)),
            "candidate_payload": "context_and_question_only",
            "gold_in_candidate_payload": False,
            "grading_rule": GRADING_RULE,
            "candidate_process": "fresh_subprocess",
        },
        "environment": environment_record(),
        "source": source_before,
        "candidate": candidate_before,
        "dataset": dataset_before,
        "selection": selection_record(items),
        "evaluator": {
            "identity": "babi_external_harness.normalized_score.v2",
            "source_digest_sha256": source_before["content_sha256"],
            "independent": False,
            "externally_signed": False,
            "limitations": [
                "The evaluator and candidate remain in the same local repository.",
                "The fresh subprocess has ambient filesystem and network access.",
                "No external signature, nonce, or hidden test set is present.",
            ],
        },
        "metrics": aggregate_items(items),
        "items": items,
        "integrity": {
            "source_same_before_after": source_before == source_after,
            "candidate_same_before_after": candidate_before == candidate_after,
            "dataset_same_before_after": dataset_before == dataset_after,
            "network_isolation_enforced": False,
            "shipped_state_isolation_enforced": False,
            "production_authority": False,
            "e5_claimed": False,
            "limitations": [
                "The checksum is recomputable and does not authenticate the run.",
                "Filesystem/network isolation and executed-code attestation are absent.",
                "Public development data may have influenced candidate implementation.",
            ],
        },
    }
    manifest = finalize_manifest(payload)
    semantic_findings = validate_babi_semantics(manifest)
    if semantic_findings:
        raise BenchmarkEvidenceError("; ".join(semantic_findings))
    write_manifest_exclusive(destination, manifest)
    return manifest, destination


def main(argv: list[str] | None = None) -> int:
    arguments = list(argv if argv is not None else sys.argv[1:])
    if arguments and arguments[0] == "verify":
        parser = argparse.ArgumentParser(description="Verify bAbI evidence")
        parser.add_argument("command")
        parser.add_argument("manifest", type=Path)
        parser.add_argument("--historical", action="store_true")
        parsed = parser.parse_args(arguments)
        result = verify_manifest(
            parsed.manifest,
            repo_root=REPO,
            require_current=not parsed.historical,
        )
        if result["structure_valid"]:
            try:
                value = strict_json_bytes(
                    parsed.manifest.read_bytes(),
                    label="bAbI receipt",
                )
                semantic = validate_babi_semantics(
                    value,
                    require_current_dataset=not parsed.historical,
                )
            except (BenchmarkEvidenceError, OSError) as exc:
                semantic = [str(exc)]
            result["semantic_findings"] = semantic
            result["semantic_valid"] = not semantic
            result["valid"] = result["valid"] and not semantic
        print(json.dumps(result, ensure_ascii=False, sort_keys=True))
        return 0 if result["valid"] else 2

    parser = argparse.ArgumentParser(description=__doc__)
    size = parser.add_mutually_exclusive_group()
    size.add_argument("--cap", type=int, default=1000)
    size.add_argument("--all", action="store_true")
    parser.add_argument("--split", default="train")
    parser.add_argument("--output", type=Path)
    parsed = parser.parse_args(arguments)
    try:
        manifest, destination = run(
            cap=None if parsed.all else parsed.cap,
            split=parsed.split,
            output=parsed.output,
        )
    except (OSError, RuntimeError, ValueError) as exc:
        print(
            json.dumps(
                {"error": str(exc), "type": type(exc).__name__},
                ensure_ascii=False,
                sort_keys=True,
            ),
            file=sys.stderr,
        )
        return 2
    per_task, macro = _task_metrics(manifest["items"])
    for row in per_task:
        print(
            f"qa{row['task']:02d} {row['name']:<16} "
            f"strict={row['strict_accuracy']:.3f} "
            f"coverage={row['coverage']:.3f} "
            f"fired_acc={row['fired_accuracy']}",
            flush=True,
        )
    print(
        json.dumps(
            {
                "manifest": str(destination.resolve()),
                "manifest_checksum_sha256": manifest[
                    "manifest_checksum_sha256"
                ],
                "n": manifest["metrics"]["n"],
                "micro_strict_accuracy": manifest["metrics"]["strict_accuracy"],
                "macro_task_strict_accuracy": macro,
                "coverage": manifest["metrics"]["coverage"],
                "fired_accuracy": manifest["metrics"]["fired_accuracy"],
                "authenticity_established": False,
                "e5_claimed": False,
            },
            ensure_ascii=False,
            sort_keys=True,
        )
    )
    return 0 if manifest["metrics"]["error"] == 0 else 2


if __name__ == "__main__":
    raise SystemExit(main())
