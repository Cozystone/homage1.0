# -*- coding: utf-8 -*-
"""DELIBERATOR System-2 — honest benchmark measurement of the wired engine's contribution.

Two things it reports, separating ENGINE from KNOWLEDGE:
  • ISOLATED engine fire-rate  — over every MCQ, how often the System-2 back-chainer produces a
    verify-gated GROUNDED derivation, and its accuracy when it does. This is the engine's grounded
    contribution on the LIVE graph; a near-zero fire-rate on closed-book PhD science is the honest
    KNOWLEDGE-absent signal (the engine has nothing in the graph to chain over), not an engine defect.
  • BEFORE/AFTER strict_acc     — the full `answer_exam` cascade with the engine tier ON vs OFF
    (ATANOR_S2_ENGINE), same items, same store. The engine tier is additive & verify-gated, so AFTER
    can only differ where the engine grounded a pick — the measured lift, honestly.

GPQA license (BINDING): reads the gated CSV from the gitignored cache only; prints aggregates +
topic tokens, never question/option text; report is written under reports/ (gitignored).

  python scripts/deliberator_engine_probe.py gpqa            # isolated engine fire-rate on GPQA
  python scripts/deliberator_engine_probe.py mmlu-pro 15     # isolated on an MMLU-Pro slice
  python scripts/deliberator_engine_probe.py mmlu-pro 5 --ba # full before/after on the slice
"""
from __future__ import annotations

import csv
import hashlib
import io
import json
import math
import os
import subprocess
import sys
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

if __name__ == "__main__":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
for _d in sorted((REPO / "packages").iterdir(), reverse=True):
    if (_d / "pyproject.toml").exists() and str(_d) not in sys.path:
        sys.path.insert(0, str(_d))

GPQA = REPO / "data" / "benchmarks" / "gpqa" / "gpqa_diamond.csv"
MMLU_PRO = REPO / "data" / "benchmarks" / "mmlu_pro"
REPORTS = REPO / "reports" / "benchmarks"
PROBE_SCHEMA = "atanor.deliberator.engine_probe.v3"

_SOURCE_PATHS = (
    "scripts/deliberator_engine_probe.py",
    "scripts/benchmark_openbook.py",
    "packages/reasoning_vm/deliberator/compiler.py",
    "packages/reasoning_vm/deliberator/mcq_adapter.py",
    "packages/reasoning_vm/deliberator/reasoner.py",
    "packages/reasoning_vm/deliberator/back_chain.py",
    "packages/reasoning_vm/exam_answer.py",
    "packages/reasoning_vm/discrimination.py",
    "packages/reasoning_vm/statement_entailment.py",
    "packages/graph_scale/triple_store.py",
    "packages/graph_scale/sharded_term_dict.py",
    "packages/graph_scale/multi_shard_store.py",
)
_STORE_MANIFEST_NAMES = frozenset(
    {"_COMPLETE.json", "BUILD_REPORT.json", "VERIFY_REPORT.json", "meta.json"}
)


def _canonical_bytes(value) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _run_git(*args: str) -> bytes:
    completed = subprocess.run(
        ["git", *args],
        cwd=REPO,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=20,
        shell=False,
        check=False,
    )
    return completed.stdout if completed.returncode == 0 else b""


def _source_provenance() -> dict:
    """Bind the exact executable source scope without exposing benchmark text."""
    records = []
    for relative in _SOURCE_PATHS:
        path = REPO / relative
        records.append(
            {
                "path": relative,
                "sha256": _sha256_file(path),
                "bytes": path.stat().st_size,
            }
        )
    tracked_diff = _run_git(
        "diff",
        "--no-ext-diff",
        "--binary",
        "HEAD",
        "--",
        *_SOURCE_PATHS,
    )
    status = _run_git(
        "status",
        "--porcelain=v1",
        "-z",
        "--",
        *_SOURCE_PATHS,
    )
    head = _run_git("rev-parse", "HEAD").decode("ascii", errors="replace").strip() or None
    return {
        "git_head": head,
        "scope": "probe executable sources listed in files; not a whole-repository seal",
        "files": records,
        "source_content_sha256": hashlib.sha256(_canonical_bytes(records)).hexdigest(),
        "relevant_tracked_diff_sha256": hashlib.sha256(tracked_diff).hexdigest(),
        "relevant_git_status_sha256": hashlib.sha256(status).hexdigest(),
        "relevant_source_dirty": bool(status),
        "compiler_sha256": next(
            record["sha256"]
            for record in records
            if record["path"].endswith("/compiler.py")
        ),
    }


def _store_fingerprint(store_meta: dict) -> dict:
    """Record manifests plus an inventory seal; do not overclaim a content seal."""
    store_name = str(store_meta.get("store") or "")
    root = REPO / "data" / "graph_scale" / store_name
    if not root.is_dir():
        return {
            "store": store_name,
            "present": False,
            "content_bound": False,
            "reason": "store_directory_not_found",
        }

    inventory = hashlib.sha256()
    manifests = []
    file_count = 0
    total_bytes = 0
    for current, dirs, files in os.walk(root, followlinks=False):
        dirs[:] = sorted(
            name
            for name in dirs
            if not (Path(current) / name).is_symlink()
        )
        for name in sorted(files):
            path = Path(current) / name
            try:
                stat = path.stat()
            except OSError:
                continue
            relative = path.relative_to(root).as_posix()
            file_count += 1
            total_bytes += stat.st_size
            inventory.update(
                _canonical_bytes(
                    {
                        "path": relative,
                        "bytes": stat.st_size,
                        "mtime_ns": stat.st_mtime_ns,
                    }
                )
            )
            if name in _STORE_MANIFEST_NAMES:
                manifests.append(
                    {
                        "path": relative,
                        "sha256": _sha256_file(path),
                        "bytes": stat.st_size,
                    }
                )
    manifests.sort(key=lambda item: item["path"])
    return {
        "store": store_name,
        "present": True,
        "root": f"data/graph_scale/{store_name}",
        "file_count": file_count,
        "bytes": total_bytes,
        "inventory_sha256": inventory.hexdigest(),
        "manifest_files": manifests,
        "manifest_set_sha256": hashlib.sha256(_canonical_bytes(manifests)).hexdigest(),
        # Current stores do not expose per-artifact hashes in a signed manifest.
        "content_bound": False,
        "integrity_level": "manifest_files_plus_path_size_mtime_inventory_only",
    }


def _item_id(item: dict) -> str:
    return hashlib.sha256(
        _canonical_bytes(
            {
                "q": item["q"],
                "choices": item["choices"],
                "gold": item["gold"],
            }
        )
    ).hexdigest()


def _mcnemar_exact_two_sided(improved: int, regressed: int) -> float:
    discordant = improved + regressed
    if discordant == 0:
        return 1.0
    lower = min(improved, regressed)
    tail = sum(math.comb(discordant, k) for k in range(lower + 1)) / (2 ** discordant)
    return min(1.0, 2.0 * tail)


def _new_run_id(bench: str) -> str:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S.%fZ")
    return f"{stamp}_{bench}_{uuid.uuid4().hex[:12]}"


def _shuffled(question, correct, incorrect):
    seed = int(hashlib.sha256(question.encode("utf-8")).hexdigest(), 16)
    opts = [correct] + list(incorrect)
    order = list(range(4))
    for i in range(3, 0, -1):
        seed, j = divmod(seed, i + 1)
        order[i], order[j] = order[j], order[i]
    letters = "ABCD"
    return {letters[k]: str(opts[order[k]]).strip() for k in range(4)}, letters[order.index(0)]


def _load_gpqa():
    rows = list(csv.DictReader(GPQA.open(encoding="utf-8")))
    out = []
    for r in rows:
        q = str(r.get("Question") or "").strip()
        cor = str(r.get("Correct Answer") or "").strip()
        inc = [str(r.get(f"Incorrect Answer {i}") or "").strip() for i in (1, 2, 3)]
        if q and cor and all(inc):
            ch, gold = _shuffled(q, cor, inc)
            out.append({"q": q, "choices": ch, "gold": gold})
    return out


def _load_mmlu_pro(n):
    fp = MMLU_PRO / f"slice_{n}.jsonl"
    return [{"q": r["question"], "choices": r["choices"], "gold": r["gold"], "cat": r.get("category")}
            for r in (json.loads(ln) for ln in fp.read_text(encoding="utf-8").splitlines())]


def _stable_guess(stem, choices):
    keys = sorted(choices)
    h = int(hashlib.sha256(("stable-guess::" + str(stem)).encode("utf-8", "ignore")).hexdigest(), 16)
    return keys[h % len(keys)]


def main() -> int:
    bench = sys.argv[1] if len(sys.argv) > 1 else "mmlu-pro"
    n = int(sys.argv[2]) if len(sys.argv) > 2 and sys.argv[2].isdigit() else 5
    do_ba = "--ba" in sys.argv
    run_id = _new_run_id(bench)
    started_at = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    source_provenance = _source_provenance()

    from scripts.benchmark_openbook import _load_store, _resolving_fa
    from packages.reasoning_vm.deliberator.compiler import compile_mcq_goals
    from packages.reasoning_vm.deliberator.mcq_adapter import engine_pick
    kg, meta = _load_store()
    store_before = _store_fingerprint(meta)
    fa = lambda t: kg.facts_about(t, limit=24)          # noqa: E731
    rfa = _resolving_fa(fa)

    items = _load_gpqa() if bench == "gpqa" else _load_mmlu_pro(n)
    label = "GPQA-Diamond" if bench == "gpqa" else f"MMLU-Pro(slice_{n})"
    print(f"{label}  n={len(items)}  store={meta.get('store')}", flush=True)

    # ── isolated engine fire-rate ──────────────────────────────────────────────────────────────
    t0 = time.time()
    fires = fired_correct = multistep_fires = 0
    engine_calls = engine_abstentions = engine_errors = 0
    compiler_errors = coverage_errors = 0
    engine_error_types: dict[str, int] = {}
    compiler_error_types: dict[str, int] = {}
    coverage_error_types: dict[str, int] = {}
    compiled_items = typed_goal_candidates = 0
    compiled_with_choice_facts = compiled_with_target_facts = 0
    compiled_with_choice_and_target_facts = 0
    choice_terms = choice_terms_with_facts = 0
    target_terms = target_terms_with_facts = 0
    max_proof_hops = 0
    for i, it in enumerate(items):
        try:
            compilation = compile_mcq_goals(it["q"])
        except Exception as exc:
            compiler_errors += 1
            error_name = type(exc).__name__
            compiler_error_types[error_name] = compiler_error_types.get(error_name, 0) + 1
            compilation = None
        if compilation is not None and compilation.compiled:
            compiled_items += 1
            typed_goal_candidates += len(compilation.goals)
            choice_terms += len(it["choices"])
            target_terms += len(compilation.goals)
            choice_coverage = []
            for choice in it["choices"].values():
                try:
                    choice_coverage.append(bool(rfa(choice)))
                except Exception as exc:
                    coverage_errors += 1
                    error_name = type(exc).__name__
                    coverage_error_types[error_name] = coverage_error_types.get(error_name, 0) + 1
                    choice_coverage.append(False)
            target_coverage = []
            for goal in compilation.goals:
                try:
                    target_coverage.append(bool(rfa(goal.target)))
                except Exception as exc:
                    coverage_errors += 1
                    error_name = type(exc).__name__
                    coverage_error_types[error_name] = coverage_error_types.get(error_name, 0) + 1
                    target_coverage.append(False)
            choice_terms_with_facts += sum(choice_coverage)
            target_terms_with_facts += sum(target_coverage)
            any_choice_facts = any(choice_coverage)
            any_target_facts = any(target_coverage)
            compiled_with_choice_facts += int(any_choice_facts)
            compiled_with_target_facts += int(any_target_facts)
            compiled_with_choice_and_target_facts += int(
                any_choice_facts and any_target_facts
            )
        engine_calls += 1
        try:
            ep = engine_pick(it["q"], it["choices"], rfa)
        except Exception as exc:
            engine_errors += 1
            error_name = type(exc).__name__
            engine_error_types[error_name] = engine_error_types.get(error_name, 0) + 1
            ep = None
        if ep and ep.get("choice_key") is not None:
            fires += 1
            fired_correct += int(ep["choice_key"] == it["gold"])
            multistep_fires += int(ep.get("multistep_fired") is True)
            max_proof_hops = max(max_proof_hops, int(ep.get("hops") or 0))
        elif engine_errors + engine_abstentions + fires < engine_calls:
            engine_abstentions += 1
        if (i + 1) % 40 == 0:
            print(f"  …engine scanned {i+1}/{len(items)}  fires={fires}", flush=True)
    dataset = GPQA if bench == "gpqa" else MMLU_PRO / f"slice_{n}.jsonl"
    rep = {"schema_version": PROBE_SCHEMA,
           "run_id": run_id,
           "started_at": started_at,
           "benchmark": label, "n": len(items), "store": meta.get("store"),
           "dataset_sha256": hashlib.sha256(dataset.read_bytes()).hexdigest(),
           "source_provenance": source_provenance,
           "store_fingerprint_before": store_before,
           "compiler_scope": "explicit_category_membership_only",
           "compiler_exercised": True,
           "compiler_errors": compiler_errors,
           "compiler_error_types": dict(sorted(compiler_error_types.items())),
           "compiled_items": compiled_items,
           "compiled_rate": round(compiled_items / max(1, len(items)), 4),
           "typed_goal_candidates": typed_goal_candidates,
           "compiled_items_with_any_choice_facts": compiled_with_choice_facts,
           "compiled_items_with_any_target_facts": compiled_with_target_facts,
           "compiled_items_with_choice_and_target_facts": compiled_with_choice_and_target_facts,
           "choice_term_graph_coverage": round(
               choice_terms_with_facts / choice_terms, 4
           ) if choice_terms else None,
           "target_term_graph_coverage": round(
               target_terms_with_facts / target_terms, 4
           ) if target_terms else None,
           "coverage_lookup_errors": coverage_errors,
           "coverage_error_types": dict(sorted(coverage_error_types.items())),
           "engine_fire_rate": round(fires / max(1, len(items)), 4), "engine_fires": fires,
           "engine_calls": engine_calls,
           "engine_abstentions": engine_abstentions,
           "engine_errors": engine_errors,
           "engine_error_types": dict(sorted(engine_error_types.items())),
           "fire_rate_when_compiled": round(fires / compiled_items, 4) if compiled_items else None,
           "engine_multistep_fires": multistep_fires,
           "engine_multistep_fire_rate": round(multistep_fires / max(1, len(items)), 4),
           "max_proof_hops": max_proof_hops,
           "engine_fired_accuracy": round(fired_correct / fires, 4) if fires else None,
           "engine_scan_sec": round(time.time() - t0, 1)}

    # ── full before/after strict_acc (optional; slower) ───────────────────────────────────────
    ba_errors = 0
    ba_error_types: dict[str, int] = {}
    if do_ba:
        from packages.reasoning_vm.exam_answer import answer_exam
        original_flag = os.environ.get("ATANOR_S2_ENGINE")
        condition_correct = {"before_engine_off": 0, "after_engine_on": 0}
        condition_seconds = {"before_engine_off": 0.0, "after_engine_on": 0.0}
        paired = []
        try:
            for index, it in enumerate(items):
                # Counterbalance order by item to expose/cache-neutralize sequential bias.
                conditions = (
                    (("0", "before_engine_off"), ("1", "after_engine_on"))
                    if index % 2 == 0
                    else (("1", "after_engine_on"), ("0", "before_engine_off"))
                )
                item_results: dict[str, dict] = {}
                for flag, tag in conditions:
                    os.environ["ATANOR_S2_ENGINE"] = flag
                    condition_start = time.perf_counter()
                    try:
                        answer = answer_exam(it["q"], it["choices"], rfa)
                        if not isinstance(answer, dict):
                            raise TypeError("answer_exam returned a non-dict result")
                        pick = answer.get("choice_key") or _stable_guess(
                            it["q"], it["choices"]
                        )
                    except Exception as exc:
                        ba_errors += 1
                        error_name = f"{tag}:{type(exc).__name__}"
                        ba_error_types[error_name] = ba_error_types.get(error_name, 0) + 1
                        pick = _stable_guess(it["q"], it["choices"])
                    condition_seconds[tag] += time.perf_counter() - condition_start
                    is_correct = pick == it["gold"]
                    condition_correct[tag] += int(is_correct)
                    item_results[tag] = {
                        "correct": is_correct,
                        "pick_hash": hashlib.sha256(str(pick).encode("utf-8")).hexdigest(),
                    }
                paired.append(
                    {
                        "item_id": _item_id(it),
                        "off_correct": item_results["before_engine_off"]["correct"],
                        "on_correct": item_results["after_engine_on"]["correct"],
                    }
                )
        finally:
            if original_flag is None:
                os.environ.pop("ATANOR_S2_ENGINE", None)
            else:
                os.environ["ATANOR_S2_ENGINE"] = original_flag

        improved_ids = [
            item["item_id"]
            for item in paired
            if not item["off_correct"] and item["on_correct"]
        ]
        regressed_ids = [
            item["item_id"]
            for item in paired
            if item["off_correct"] and not item["on_correct"]
        ]
        both_correct = sum(
            item["off_correct"] and item["on_correct"] for item in paired
        )
        both_wrong = sum(
            not item["off_correct"] and not item["on_correct"] for item in paired
        )
        for tag in ("before_engine_off", "after_engine_on"):
            rep[tag] = {
                "strict_acc": round(
                    condition_correct[tag] / max(1, len(items)), 4
                ),
                "correct": condition_correct[tag],
                "sec": round(condition_seconds[tag], 3),
            }
        rep["paired_effect"] = {
            "design": "per-item counterbalanced OFF/ON; identical item/store",
            "both_correct": both_correct,
            "both_wrong": both_wrong,
            "off_wrong_on_right": len(improved_ids),
            "off_right_on_wrong": len(regressed_ids),
            "paired_accuracy_lift": round(
                (len(improved_ids) - len(regressed_ids)) / max(1, len(items)),
                6,
            ),
            "mcnemar_exact_two_sided_p": round(
                _mcnemar_exact_two_sided(len(improved_ids), len(regressed_ids)),
                12,
            ),
            "improved_item_ids_sha256": hashlib.sha256(
                _canonical_bytes(sorted(improved_ids))
            ).hexdigest(),
            "regressed_item_ids_sha256": hashlib.sha256(
                _canonical_bytes(sorted(regressed_ids))
            ).hexdigest(),
            "question_or_choice_text_in_report": False,
        }
        rep["before_after_errors"] = ba_errors
        rep["before_after_error_types"] = dict(sorted(ba_error_types.items()))

    store_after = _store_fingerprint(meta)
    rep["store_fingerprint_after"] = store_after
    rep["store_mutated_during_probe"] = (
        store_before.get("inventory_sha256") != store_after.get("inventory_sha256")
        or store_before.get("manifest_set_sha256") != store_after.get("manifest_set_sha256")
    )
    rep["completed_at"] = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    print("\nRESULT", json.dumps(rep, ensure_ascii=False))
    REPORTS.mkdir(parents=True, exist_ok=True)
    out = REPORTS / f"deliberator_engine_{run_id}.json"
    with out.open("x", encoding="utf-8") as handle:
        json.dump(rep, handle, ensure_ascii=False, indent=2, allow_nan=False)
        handle.write("\n")
    print("wrote", out, "(NOT committed)")
    clean_run = (
        compiler_errors == 0
        and engine_errors == 0
        and coverage_errors == 0
        and ba_errors == 0
        and rep["store_mutated_during_probe"] is False
    )
    return 0 if clean_run else 2


if __name__ == "__main__":
    raise SystemExit(main())
