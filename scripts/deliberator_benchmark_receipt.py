"""Unsigned isolated DELIBERATOR compiler/firing receipt.

This measures only the grounded engine path on GPQA or a fixed MMLU-Pro
development slice.  It is intentionally not an OFF/ON full-cascade comparison
and cannot establish accuracy lift or E5 capability.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import math
import os
import secrets
import sys
import time
import uuid
from pathlib import Path
from typing import Any, Callable, Mapping


REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

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


REPORTS = REPO / "reports" / "benchmarks"
GPQA = REPO / "data" / "benchmarks" / "gpqa" / "gpqa_diamond.csv"
MMLU_PRO = REPO / "data" / "benchmarks" / "mmlu_pro"
_MMLU_SLICES = frozenset({5, 8, 15, 20, 25})
_MMLU_CATEGORIES = frozenset(
    {
        "biology",
        "chemistry",
        "physics",
        "history",
        "economics",
        "psychology",
        "health",
        "law",
    }
)
_GPQA_HEADER_SHA256 = (
    "604b6f9d72e1403c3b5f721e35f4819fc6a62741fb5a4d62c25e97b57ddd081d"
)
_EVALUATOR_SOURCE_PATHS = (
    "packages/__init__.py",
    "packages/eval_evidence/__init__.py",
    "packages/eval_evidence/receipt.py",
    "scripts/deliberator_benchmark_receipt.py",
)
_CANDIDATE_SOURCE_PATHS = (
    "packages/__init__.py",
    "packages/evolution/rational_evolver.py",
    "packages/graph_scale/__init__.py",
    "packages/graph_scale/graph_paths.py",
    "packages/graph_scale/multi_shard_store.py",
    "packages/graph_scale/sharded_term_dict.py",
    "packages/graph_scale/triple_store.py",
    "packages/reasoning_vm/__init__.py",
    "packages/reasoning_vm/deduction.py",
    "packages/reasoning_vm/discrimination.py",
    "packages/reasoning_vm/quantity.py",
    "packages/reasoning_vm/deliberator/__init__.py",
    "packages/reasoning_vm/deliberator/back_chain.py",
    "packages/reasoning_vm/deliberator/compiler.py",
    "packages/reasoning_vm/deliberator/kernel_forge.py",
    "packages/reasoning_vm/deliberator/mcq_adapter.py",
    "packages/reasoning_vm/deliberator/reasoner.py",
    "scripts/benchmark_openbook.py",
)


def _new_run_id(benchmark: str) -> str:
    stamp = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())
    return f"{stamp}.{benchmark}.{uuid.uuid4().hex[:12]}"


def _permutation_order(
    question: str,
    *,
    ordinal: int,
    nonce: bytes,
) -> list[int]:
    seed = int.from_bytes(
        hashlib.sha256(
            nonce
            + ordinal.to_bytes(8, "big", signed=False)
            + question.encode("utf-8")
        ).digest(),
        "big",
    )
    order = list(range(4))
    for index in range(3, 0, -1):
        seed, selected = divmod(seed, index + 1)
        order[index], order[selected] = order[selected], order[index]
    return order


def _shuffled(
    question: str,
    correct: str,
    incorrect: list[str],
    *,
    ordinal: int = 0,
    nonce: bytes = b"unit-test-only-fixed-nonce",
) -> tuple[dict[str, str], str]:
    """Permute with an evaluator nonce, never a stem-only deterministic oracle."""
    options = [correct, *incorrect]
    order = _permutation_order(question, ordinal=ordinal, nonce=nonce)
    letters = "ABCD"
    choices = {
        letters[index]: str(options[order[index]]).strip()
        for index in range(4)
    }
    return choices, letters[order.index(0)]


def _load_gpqa_bytes(payload: bytes, *, nonce: bytes) -> list[dict[str, Any]]:
    try:
        text = payload.decode("utf-8")
    except UnicodeError as exc:
        raise BenchmarkEvidenceError("GPQA CSV is not UTF-8") from exc
    reader = csv.DictReader(io.StringIO(text, newline=""))
    header_digest = hashlib.sha256(
        canonical_json_bytes(reader.fieldnames)
    ).hexdigest()
    if header_digest != _GPQA_HEADER_SHA256:
        raise BenchmarkEvidenceError("GPQA header does not match the pinned schema")
    rows = list(reader)
    if len(rows) != 198:
        raise BenchmarkEvidenceError("GPQA Diamond census must be exactly 198 rows")
    items = []
    for ordinal, row in enumerate(rows):
        question = str(row.get("Question") or "").strip()
        correct = str(row.get("Correct Answer") or "").strip()
        incorrect = [
            str(row.get(f"Incorrect Answer {index}") or "").strip()
            for index in (1, 2, 3)
        ]
        options = [correct, *incorrect]
        if (
            not question
            or not all(options)
            or len({option.casefold() for option in options}) != 4
        ):
            raise BenchmarkEvidenceError(f"GPQA row {ordinal} is malformed")
        choices, gold = _shuffled(
            question,
            correct,
            incorrect,
            ordinal=ordinal,
            nonce=nonce,
        )
        items.append(
            {
                "ordinal": ordinal,
                "q": question,
                "choices": choices,
                "gold": gold,
                "category": str(row.get("High-level domain") or "").strip() or None,
            }
        )
    return items


def _load_mmlu_pro_bytes(payload: bytes, *, slice_size: int) -> list[dict[str, Any]]:
    if slice_size not in _MMLU_SLICES:
        raise ValueError(f"MMLU-Pro slice must be one of {sorted(_MMLU_SLICES)}")
    try:
        lines = payload.decode("utf-8").splitlines()
    except UnicodeError as exc:
        raise BenchmarkEvidenceError("MMLU-Pro slice is not UTF-8") from exc
    if len(lines) != 8 * slice_size:
        raise BenchmarkEvidenceError("MMLU-Pro census must be 8 × slice size")
    items = []
    category_counts: dict[str, int] = {}
    for ordinal, line in enumerate(lines):
        row = strict_json_bytes(
            line.encode("utf-8"),
            label=f"MMLU-Pro row {ordinal}",
        )
        if frozenset(row) != {"question", "choices", "gold", "category"}:
            raise BenchmarkEvidenceError(f"MMLU-Pro row {ordinal} fields mismatch")
        question = row.get("question")
        choices = row.get("choices")
        category = row.get("category")
        gold = row.get("gold")
        if (
            not isinstance(question, str)
            or not question.strip()
            or not isinstance(choices, dict)
            or not 2 <= len(choices) <= 10
            or any(
                not isinstance(key, str)
                or not key.strip()
                or not isinstance(value, str)
                or not value.strip()
                for key, value in choices.items()
            )
            or len({str(value).strip() for value in choices.values()})
            != len(choices)
            or gold not in choices
            or category not in _MMLU_CATEGORIES
        ):
            raise BenchmarkEvidenceError(f"MMLU-Pro row {ordinal} invalid")
        category_counts[str(category)] = category_counts.get(str(category), 0) + 1
        items.append(
            {
                "ordinal": ordinal,
                "q": question.strip(),
                "choices": {
                    str(key): str(value).strip()
                    for key, value in choices.items()
                },
                "gold": str(gold),
                "category": str(category),
            }
        )
    if category_counts != {
        category: slice_size for category in sorted(_MMLU_CATEGORIES)
    }:
        raise BenchmarkEvidenceError("MMLU-Pro per-category census mismatch")
    return items


def _is_link(path: Path) -> bool:
    if path.is_symlink():
        return True
    checker = getattr(path, "is_junction", None)
    return bool(callable(checker) and checker())


def _store_paths(store_name: str) -> tuple[str, ...]:
    if not store_name or "/" in store_name or "\\" in store_name or ".." in store_name:
        raise ValueError("store must be one repository-local directory name")
    root = REPO / "data" / "graph_scale" / store_name
    if not root.is_dir() or _is_link(root):
        raise ValueError(f"store directory unavailable or linked: {store_name}")
    paths: list[str] = []
    for path in sorted(root.rglob("*")):
        if _is_link(path):
            raise BenchmarkEvidenceError(
                f"linked store entry is forbidden: {path.relative_to(root)}"
            )
        if path.is_file():
            paths.append(path.relative_to(REPO).as_posix())
    if not paths:
        raise ValueError(f"store has no regular files: {store_name}")
    return tuple(paths)


def _dataset_path(benchmark: str, slice_size: int) -> str:
    if benchmark == "gpqa":
        return "data/benchmarks/gpqa/gpqa_diamond.csv"
    return f"data/benchmarks/mmlu_pro/slice_{slice_size}.jsonl"


def _read_bound_dataset(
    relative: str,
    scope: Mapping[str, Any],
) -> bytes:
    records = {
        record["path"]: record
        for record in scope["files"]
        if isinstance(record, Mapping)
    }
    record = records.get(relative)
    if not isinstance(record, Mapping):
        raise BenchmarkEvidenceError("dataset file missing from bound scope")
    payload = (REPO / relative).read_bytes()
    if hashlib.sha256(payload).hexdigest() != record.get("sha256"):
        raise BenchmarkEvidenceError("dataset bytes differ from bound snapshot")
    return payload


def _measure_item(
    item: dict[str, Any],
    *,
    compile_goals: Callable[[str], Any],
    engine_pick: Callable[..., dict[str, Any] | None],
    facts_about: Callable,
) -> dict[str, Any]:
    started = time.perf_counter()
    compilation = None
    engine = None
    error_type: str | None = None
    choice_terms_with_facts = 0
    target_terms_with_facts = 0
    try:
        compilation = compile_goals(item["q"])
        if compilation.compiled:
            for choice in item["choices"].values():
                choice_terms_with_facts += int(bool(facts_about(choice)))
            for goal in compilation.goals:
                target_terms_with_facts += int(bool(facts_about(goal.target)))
        engine = engine_pick(
            item["q"],
            item["choices"],
            facts_about,
            compilation=compilation,
        )
    except Exception as exc:
        error_type = type(exc).__name__
    latency_ms = round((time.perf_counter() - started) * 1000.0, 6)

    if error_type is not None:
        status = "error"
        fired = False
        correct = False
        output_digest = None
    elif engine is None:
        status = "abstain"
        fired = False
        correct = False
        output_digest = None
    else:
        choice = engine.get("choice_key")
        grounded = engine.get("mode") == "grounded"
        hops = engine.get("hops")
        compiler_schema = getattr(compilation, "schema_version", None)
        if (
            choice not in item["choices"]
            or not grounded
            or type(hops) is not int
            or hops < 1
            or engine.get("compiler_schema") not in {None, compiler_schema}
        ):
            status = "error"
            fired = False
            correct = False
            output_digest = None
            error_type = "InvalidGroundedEngineResult"
        else:
            correct = choice == item["gold"]
            status = "correct" if correct else "wrong"
            fired = True
            output_digest = hashlib.sha256(str(choice).encode("utf-8")).hexdigest()

    compiled = bool(compilation is not None and compilation.compiled)
    goal_count = len(compilation.goals) if compilation is not None else 0
    return {
        "status": status,
        "fired": fired,
        "correct": correct,
        "output_sha256": output_digest,
        "latency_ms": latency_ms,
        "metadata": {
            "ordinal": item["ordinal"],
            "compiled": compiled,
            "compiler_status": (
                compilation.status if compilation is not None else "error"
            ),
            "compiler_family": (
                compilation.surface_family if compilation is not None else None
            ),
            "compiler_reason": (
                compilation.reason if compilation is not None else None
            ),
            "goal_count": goal_count,
            "choice_count": len(item["choices"]),
            "uniform_random_chance": round(1 / len(item["choices"]), 12),
            "choice_terms_with_facts": choice_terms_with_facts,
            "target_terms_with_facts": target_terms_with_facts,
            "grounded": bool(fired),
            "hops": int(engine.get("hops") or 0) if fired and engine else 0,
            "multistep_fired": bool(
                engine.get("multistep_fired") is True
            ) if fired and engine else False,
            "engine_mode": engine.get("mode") if fired and engine else None,
            "error_type": error_type,
            "category_hash": (
                hashlib.sha256(str(item["category"]).encode("utf-8")).hexdigest()
                if item.get("category")
                else None
            ),
        },
    }


def _derived_engine_diagnostics(items: list[dict[str, Any]]) -> dict[str, Any]:
    n = len(items)
    compiled = sum(row["metadata"]["compiled"] for row in items)
    grounded = sum(row["metadata"]["grounded"] for row in items)
    multistep = sum(row["metadata"]["multistep_fired"] for row in items)
    return {
        "compiled_items": compiled,
        "compiled_rate": round(compiled / n, 12),
        "grounded_fires": grounded,
        "grounded_firing_rate": round(grounded / n, 12),
        "multistep_fires": multistep,
        "multistep_firing_rate": round(multistep / n, 12),
        "max_proof_hops": max(
            (row["metadata"]["hops"] for row in items),
            default=0,
        ),
    }


def validate_deliberator_semantics(
    manifest: Mapping[str, Any],
    *,
    require_current_dataset: bool = True,
) -> list[str]:
    findings: list[str] = []
    benchmark = manifest.get("benchmark")
    config = manifest.get("config")
    if not isinstance(benchmark, Mapping) or not isinstance(config, Mapping):
        return ["DELIBERATOR benchmark/config missing"]
    if config.get("condition") != "isolated_engine_on":
        findings.append("DELIBERATOR condition must be isolated_engine_on")
    if config.get("paired_off_on") is not False:
        findings.append("DELIBERATOR paired_off_on must be false")
    if config.get("paired_accuracy_lift") is not None:
        findings.append("DELIBERATOR paired_accuracy_lift must be null")
    if config.get("accuracy_scope") != "isolated_grounded_engine_only":
        findings.append("DELIBERATOR accuracy scope mismatch")
    items = manifest.get("items")
    if not isinstance(items, list) or not items:
        return [*findings, "DELIBERATOR items missing"]
    for index, row in enumerate(items):
        metadata = row.get("metadata") if isinstance(row, Mapping) else None
        if not isinstance(metadata, Mapping) or metadata.get("ordinal") != index:
            findings.append("DELIBERATOR item ordinal mismatch")
            break
        if metadata.get("grounded") is not (row.get("fired") is True):
            findings.append("DELIBERATOR grounded/fired mismatch")
            break
        if metadata.get("multistep_fired") and not row.get("fired"):
            findings.append("DELIBERATOR multistep without firing")
            break
    if require_current_dataset:
        benchmark_name = config.get("benchmark")
        slice_size = config.get("slice_size")
        nonce_hex = config.get("gpqa_permutation_nonce_hex")
        try:
            relative = _dataset_path(str(benchmark_name), int(slice_size or 5))
            payload = _read_bound_dataset(relative, manifest["dataset"])
            if benchmark_name == "gpqa":
                nonce = bytes.fromhex(str(nonce_hex))
                expected = _load_gpqa_bytes(payload, nonce=nonce)
            else:
                expected = _load_mmlu_pro_bytes(
                    payload,
                    slice_size=int(slice_size),
                )
        except (BenchmarkEvidenceError, KeyError, TypeError, ValueError) as exc:
            findings.append(
                f"DELIBERATOR dataset census failed: {type(exc).__name__}"
            )
        else:
            expected_ids = [
                item_id(
                    {
                        "benchmark": benchmark_name,
                        "ordinal": item["ordinal"],
                        "q": item["q"],
                        "choices": item["choices"],
                        "gold": item["gold"],
                    }
                )
                for item in expected
            ]
            actual_ids = [
                row.get("item_id")
                for row in items
                if isinstance(row, Mapping)
            ]
            if actual_ids != expected_ids:
                findings.append(
                    "DELIBERATOR items do not match bound dataset census"
                )
    return findings


def run(
    *,
    benchmark: str,
    slice_size: int,
    store_name: str,
    output: Path | None,
) -> tuple[dict[str, Any], Path]:
    if benchmark not in {"gpqa", "mmlu-pro"}:
        raise ValueError("benchmark must be gpqa or mmlu-pro")
    if benchmark == "mmlu-pro" and slice_size not in _MMLU_SLICES:
        raise ValueError(f"MMLU-Pro slice must be one of {sorted(_MMLU_SLICES)}")
    run_id = _new_run_id(benchmark)
    destination = ensure_safe_report_output(
        REPO,
        output or REPORTS / f"deliberator_isolated_{run_id}.json",
    )
    dataset_relative = _dataset_path(benchmark, slice_size)
    source_before = bind_files(REPO, _EVALUATOR_SOURCE_PATHS)
    dataset_before = bind_files(REPO, [dataset_relative])
    dataset_payload = _read_bound_dataset(dataset_relative, dataset_before)
    permutation_nonce = secrets.token_bytes(32) if benchmark == "gpqa" else b""
    benchmark_items = (
        _load_gpqa_bytes(dataset_payload, nonce=permutation_nonce)
        if benchmark == "gpqa"
        else _load_mmlu_pro_bytes(dataset_payload, slice_size=slice_size)
    )
    store_paths_before = _store_paths(store_name)
    candidate_before = bind_files(
        REPO,
        [*_CANDIDATE_SOURCE_PATHS, *store_paths_before],
    )
    started_at = utc_now()

    original_store = os.environ.get("WORLD_PACK_STORE")
    original_engine = os.environ.get("ATANOR_S2_ENGINE")
    store = None
    outcomes: list[dict[str, Any]] = []
    try:
        os.environ["WORLD_PACK_STORE"] = store_name
        os.environ["ATANOR_S2_ENGINE"] = "1"
        from scripts.benchmark_openbook import _load_store, _resolving_fa
        from packages.reasoning_vm.deliberator.compiler import compile_mcq_goals
        from packages.reasoning_vm.deliberator.mcq_adapter import engine_pick

        store, store_meta = _load_store(read_only=True)
        if store_meta.get("store") != store_name:
            raise BenchmarkEvidenceError("selected store silently fell back")
        if hasattr(store, "shards"):
            read_only = all(
                getattr(shard, "_read_only", False)
                for shard in store.shards
            )
        else:
            read_only = getattr(store, "_read_only", False)
        if not read_only:
            raise BenchmarkEvidenceError("graph store did not open read-only")
        raw_facts = lambda term: store.facts_about(term, limit=24)  # noqa: E731
        facts_about = _resolving_fa(raw_facts)
        for index, benchmark_item in enumerate(benchmark_items, start=1):
            measured = _measure_item(
                benchmark_item,
                compile_goals=compile_mcq_goals,
                engine_pick=engine_pick,
                facts_about=facts_about,
            )
            measured["item_id"] = item_id(
                {
                    "benchmark": benchmark,
                    "ordinal": benchmark_item["ordinal"],
                    "q": benchmark_item["q"],
                    "choices": benchmark_item["choices"],
                    "gold": benchmark_item["gold"],
                }
            )
            outcomes.append(measured)
            if index % 40 == 0 or index == len(benchmark_items):
                diagnostics = _derived_engine_diagnostics(outcomes)
                print(
                    f"{benchmark} {index}/{len(benchmark_items)} "
                    f"compiled={diagnostics['compiled_items']} "
                    f"fired={diagnostics['grounded_fires']}",
                    flush=True,
                )
    finally:
        close = getattr(store, "close", None)
        if callable(close):
            close()
        if original_store is None:
            os.environ.pop("WORLD_PACK_STORE", None)
        else:
            os.environ["WORLD_PACK_STORE"] = original_store
        if original_engine is None:
            os.environ.pop("ATANOR_S2_ENGINE", None)
        else:
            os.environ["ATANOR_S2_ENGINE"] = original_engine

    store_paths_after = _store_paths(store_name)
    if store_paths_after != store_paths_before:
        raise BenchmarkEvidenceError("graph store file inventory changed during run")
    source_after = bind_files(REPO, _EVALUATOR_SOURCE_PATHS)
    dataset_after = bind_files(REPO, [dataset_relative])
    candidate_after = bind_files(
        REPO,
        [*_CANDIDATE_SOURCE_PATHS, *store_paths_after],
    )
    payload = {
        "schema_version": BENCHMARK_EVIDENCE_SCHEMA,
        "evidence_kind": BENCHMARK_EVIDENCE_KIND,
        "run_id": run_id,
        "started_at": started_at,
        "completed_at": utc_now(),
        "benchmark": {
            "id": "gpqa-diamond" if benchmark == "gpqa" else "mmlu-pro",
            "version": "local-gated-csv" if benchmark == "gpqa" else f"slice-{slice_size}",
            "split": "full_local_exposed" if benchmark == "gpqa" else f"fixed_slice_{slice_size}",
            "protocol": "isolated grounded DELIBERATOR compiler/firing scan",
            "expected_item_count": len(benchmark_items),
        },
        "config": {
            "benchmark": benchmark,
            "slice_size": slice_size if benchmark == "mmlu-pro" else None,
            "store": store_name,
            "engine_flag": "forced_on",
            "condition": "isolated_engine_on",
            "paired_off_on": False,
            "paired_accuracy_lift": None,
            "accuracy_scope": "isolated_grounded_engine_only",
            "gpqa_permutation_nonce_hex": (
                permutation_nonce.hex() if benchmark == "gpqa" else None
            ),
            "gold_in_engine_call": False,
        },
        "environment": environment_record(),
        "source": source_before,
        "candidate": candidate_before,
        "dataset": dataset_before,
        "selection": selection_record(outcomes),
        "evaluator": {
            "identity": "deliberator_benchmark_receipt.isolated_mcq.v2",
            "source_digest_sha256": source_before["content_sha256"],
            "independent": False,
            "externally_signed": False,
            "limitations": [
                "The evaluator and candidate run in the same local process.",
                "This isolated scan does not measure paired full-cascade lift.",
                "The GPQA nonce is absent from engine inputs but process isolation is absent.",
            ],
        },
        "metrics": aggregate_items(outcomes),
        "items": outcomes,
        "integrity": {
            "source_same_before_after": source_before == source_after,
            "candidate_same_before_after": candidate_before == candidate_after,
            "dataset_same_before_after": dataset_before == dataset_after,
            "network_isolation_enforced": False,
            "shipped_state_isolation_enforced": False,
            "production_authority": False,
            "e5_claimed": False,
            "limitations": [
                "The selected graph store is read-only but OS sandboxing is absent.",
                "GPQA and fixed MMLU-Pro slices have prior local exposure.",
                "Firing rate without paired accuracy lift is not progress.",
                "The checksum is recomputable and does not authenticate the run.",
            ],
        },
    }
    manifest = finalize_manifest(payload)
    semantic_findings = validate_deliberator_semantics(manifest)
    if semantic_findings:
        raise BenchmarkEvidenceError("; ".join(semantic_findings))
    write_manifest_exclusive(destination, manifest)
    return manifest, destination


def main(argv: list[str] | None = None) -> int:
    arguments = list(argv if argv is not None else sys.argv[1:])
    if arguments and arguments[0] == "verify":
        parser = argparse.ArgumentParser(description="Verify DELIBERATOR evidence")
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
                    label="DELIBERATOR receipt",
                )
                semantic = validate_deliberator_semantics(
                    value,
                    require_current_dataset=not parsed.historical,
                )
            except (BenchmarkEvidenceError, OSError) as exc:
                semantic = [str(exc)]
            result["semantic_findings"] = semantic
            result["semantic_valid"] = not semantic
            result["valid"] = result["valid"] and not semantic
        print(json.dumps(result, sort_keys=True))
        return 0 if result["valid"] else 2

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("benchmark", choices=("gpqa", "mmlu-pro"))
    parser.add_argument("--slice", type=int, default=5)
    parser.add_argument("--store", default="world_pack_full")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args(arguments)
    try:
        manifest, path = run(
            benchmark=args.benchmark,
            slice_size=args.slice,
            store_name=args.store,
            output=args.output,
        )
    except (OSError, RuntimeError, ValueError) as exc:
        print(
            json.dumps({"error": str(exc), "type": type(exc).__name__}),
            file=sys.stderr,
        )
        return 2
    diagnostics = _derived_engine_diagnostics(manifest["items"])
    print(
        json.dumps(
            {
                "manifest": str(path.resolve()),
                "manifest_checksum_sha256": manifest[
                    "manifest_checksum_sha256"
                ],
                "n": manifest["metrics"]["n"],
                **diagnostics,
                "isolated_engine_strict_accuracy": manifest["metrics"][
                    "strict_accuracy"
                ],
                "paired_accuracy_lift": None,
                "authenticity_established": False,
                "e5_claimed": False,
            },
            sort_keys=True,
        )
    )
    return 0 if manifest["metrics"]["error"] == 0 else 2


if __name__ == "__main__":
    raise SystemExit(main())
