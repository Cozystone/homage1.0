# -*- coding: utf-8 -*-
"""Run the honest SWE-bench_Verified stage diagnostic over a fixed, deterministic sample.

    python -X utf8 -m packages.swe_eval.run_verified

Writes data/swe_eval/report.json (and report.md via report.py). No Docker needed for the diagnostic;
the optional gold self-test of the eval path lives in local_eval.py and is run separately.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[2]
OUT = REPO / "data" / "swe_eval"

# Fixed, deterministic sample — indices 0..9 of SWE-bench_Verified (sorted by instance_id => all
# astropy/astropy, spanning 7 subsystems). No Date, no random. One blobless clone covers all ten.
SAMPLE_INDICES = list(range(10))
DATASET = "princeton-nlp/SWE-bench_Verified"


def _load(indices: list[int]) -> list[dict[str, Any]]:
    from datasets import load_dataset
    ds = load_dataset(DATASET, split="test")
    return [dict(ds[i]) for i in indices]


def _aggregate(results: list[Any]) -> dict[str, Any]:
    from packages.swe_eval.pipeline import STAGES
    n = len(results)
    order = {s: i for i, s in enumerate(STAGES)}
    reached_at_least = {s: sum(1 for r in results if order[r.reached] >= order[s]) for s in STAGES}
    stopped = {}
    for r in results:
        key = r.stopped_at or "cleared_all"
        stopped[key] = stopped.get(key, 0) + 1
    ranked = [r for r in results if r.gold_rank > 0]
    return {
        "n": n,
        "reached_at_least": reached_at_least,
        "stopped_at": stopped,
        "localization": {
            "top1_hit": sum(r.top1_hit for r in results),
            "top5_hit": sum(r.top5_hit for r in results),
            "top10_hit": sum(r.top10_hit for r in results),
            "function_target_found": sum(r.function_target_found for r in results),
            "mean_gold_rank_when_ranked": round(sum(r.gold_rank for r in ranked) / max(1, len(ranked)), 2),
            "n_ranked": len(ranked),
        },
        "localization_fused": {          # lexical RE-RANKED by the failing-test signal (W-A top-1 lever)
            "top1_hit": sum(r.fused_top1_hit for r in results),
            "top5_hit": sum(r.fused_top5_hit for r in results),
            "top10_hit": sum(r.fused_top10_hit for r in results),
            "signal": "failing-test package/stem/import/symbol proximity; uses the given test, never the gold",
        },
        "patch_generation": {
            "code_author_applicable": sum(r.code_author_applicable for r in results),
            "total_literal_examples_parsed": sum(r.n_literal_examples for r in results),
            "self_repair_all_refused": all("refused" in (r.self_repair_verdict or "") for r in results),
            "patches_produced": sum(1 for r in results if r.patch is not None),
        },
        "multi_file": {
            "single_file_instances": sum(1 for r in results if r.n_gold_files == 1),
            "multi_file_instances": sum(1 for r in results if r.n_gold_files > 1),
            "max_gold_files": max((r.n_gold_files for r in results), default=0),
        },
        "resolved": sum(r.resolved for r in results),
    }


def main(run_probes: bool = True) -> dict[str, Any]:
    from packages.swe_eval import pipeline as pl

    insts = _load(SAMPLE_INDICES)
    liveness = pl.organ_liveness()
    results = [pl.run_instance(it) for it in insts]
    agg = _aggregate(results)

    probes: dict[str, Any] = {}
    if run_probes:
        from packages.swe_eval import probes as pb
        try:
            probes["multilingual"] = pb.probe_multilingual(n=2)
        except Exception as e:
            probes["multilingual"] = {"loads": False, "error": f"{type(e).__name__}: {str(e)[:150]}"}
        for name in ("pro", "multimodal"):
            try:
                probes[name] = pb.probe_loadable(name)
            except Exception as e:
                probes[name] = {"loads": False, "error": f"{type(e).__name__}: {str(e)[:150]}"}

    # preserve a previously folded-in eval section (the Docker gold self-test) across re-runs
    prior_eval: dict[str, Any] = {"note": "populated by local_eval.py gold self-test; run separately (Docker)."}
    prior = OUT / "report.json"
    if prior.exists():
        try:
            prev = json.loads(prior.read_text(encoding="utf-8"))
            if isinstance(prev.get("eval"), dict) and prev["eval"].get("gold_selftest"):
                prior_eval = prev["eval"]
        except Exception:
            pass

    report = {
        "dataset": DATASET,
        "sample_indices": SAMPLE_INDICES,
        "doctrine": "fail-0: never emit an unverifiable patch; abstention is honest, not failure.",
        "organ_liveness_control": liveness,
        "instances": [r.__dict__ for r in results],
        "aggregate": agg,
        "probes": probes,
        "eval": prior_eval,
    }
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return report


def run_patch(instance_ids: list[str] | None = None, *, budget: int = 400,
              topk_files: int = 5) -> dict[str, Any]:
    """The FUSED patch path: localize (deliberation) -> propose (edit schemas) -> VERIFY (regression
    gate) -> ship only a green diff. Runs the reachable single-file/single-function subset, writes
    data/swe_eval/patch_report.json (the scorecard the self_evolution repo_engineering domain reads).

    Honest scope: the regression gate needs each instance's prebuilt swebench image; an instance with
    no runnable image is recorded UNDECIDED (eval env absent), never counted as a failure or a pass.
    """
    from packages.swe_eval import patch_pipeline as pp
    ids = instance_ids or ["astropy__astropy-12907"]     # the reachable single-token subset
    insts = _load_by_ids(ids)
    results = [pp.run_instance_patch(it, budget=budget, topk_files=topk_files) for it in insts]
    attempted = [r for r in results if not (r.verdict and r.verdict.get("law") == "insufficient-eval-environment")]
    resolved = sum(1 for r in results if r.resolved)
    report = {
        "dataset": DATASET,
        "doctrine": "fail-0: ship a diff ONLY when the repo's own FAIL_TO_PASS+PASS_TO_PASS regression "
                    "gate is green; otherwise abstain. Every stage calls an existing verified organ.",
        "fusion_wiring": {
            "localization": "packages.deliberator.repo_engineering.deliberate_localization "
                            "(file_scan line-scorer -> import graph -> code_situation AST; MEC-scheduled)",
            "patch_generation": "code_author/L3 reframe (from-scratch, abstains on repo funcs) + "
                                "packages.swe_eval.edit_schemas domain-blind mutation (the reachable path)",
            "verification": "packages.swe_eval.regression_gate (isomorphic to physics_truth: accept "
                            "only green; drive pytest in the instance image with LF, no swebench CRLF)",
        },
        "aggregate": {
            "n": len(results),
            "n_attempted_with_eval_env": len(attempted),
            "resolved": resolved,
            "verified_diffs": sum(1 for r in results if r.verified_diff),
            "localization_top5": sum(1 for r in results if r.localization_top5_hit),
        },
        "instances": [{k: v for k, v in r.__dict__.items() if k != "localization_cert"} for r in results],
    }
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "patch_report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2),
                                           encoding="utf-8")
    return report


def _load_by_ids(ids: list[str]) -> list[dict[str, Any]]:
    from datasets import load_dataset
    ds = load_dataset(DATASET, split="test")
    want = set(ids)
    return [dict(ds[i]) for i in range(len(ds)) if ds[i]["instance_id"] in want]


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    if "--patch" in sys.argv:
        rep = run_patch()
        a = rep["aggregate"]
        print(f"FUSED patch path: resolved {a['resolved']}/{a['n']}  "
              f"verified_diffs={a['verified_diffs']}  (eval-env attempts={a['n_attempted_with_eval_env']})")
        print("patch_report.json written to", str(OUT / "patch_report.json"))
        sys.exit(0)
    rep = main(run_probes="--no-probes" not in sys.argv)
    a = rep["aggregate"]
    print(f"resolved {a['resolved']}/{a['n']}  |  stopped_at={a['stopped_at']}")
    print(f"localization (lexical) top1/top5/top10 = {a['localization']['top1_hit']}/"
          f"{a['localization']['top5_hit']}/{a['localization']['top10_hit']}  "
          f"func_target={a['localization']['function_target_found']}")
    print(f"localization (FUSED)   top1/top5/top10 = {a['localization_fused']['top1_hit']}/"
          f"{a['localization_fused']['top5_hit']}/{a['localization_fused']['top10_hit']}")
    print(f"organ liveness (seed code tasks): {rep['organ_liveness_control']['authored_pass']}/"
          f"{rep['organ_liveness_control']['seed_tasks']}")
    print("report.json written to", str(OUT / "report.json"))
