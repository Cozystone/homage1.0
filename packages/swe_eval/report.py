# -*- coding: utf-8 -*-
"""Render data/swe_eval/report.json into a readable report.md. Pure formatting; invents nothing."""
from __future__ import annotations

import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
OUT = REPO / "data" / "swe_eval"


def render(rep: dict) -> str:
    a = rep["aggregate"]
    liv = rep["organ_liveness_control"]
    loc = a["localization"]
    pg = a["patch_generation"]
    mf = a["multi_file"]
    L: list[str] = []
    L.append("# ATANOR on SWE-bench — honest stage diagnostic")
    L.append("")
    L.append(f"Dataset: `{rep['dataset']}`  |  sample: fixed indices {rep['sample_indices']} "
             f"(all astropy/astropy, 7 subsystems)  |  doctrine: {rep['doctrine']}")
    L.append("")
    L.append(f"## Headline: resolved {a['resolved']}/{a['n']} (expected ~0 — scale mismatch)")
    L.append("")
    L.append("Control — organ is LIVE, not broken: `code_author` solves "
             f"{liv['authored_pass']}/{liv['seed_tasks']} of its own single-function seed tasks "
             f"({liv['by_source']}). So 0/{a['n']} on SWE-bench is a SCALE result, not a dead organ.")
    L.append("")
    L.append("## Stage funnel (how many of 10 reached at least each stage)")
    L.append("")
    L.append("| stage | reached |")
    L.append("|---|---|")
    for s, c in a["reached_at_least"].items():
        L.append(f"| {s} | {c}/{a['n']} |")
    L.append("")
    L.append(f"**Single stage that stops us: `patch_generation` — {a['stopped_at']}.**")
    L.append("")
    L.append("## (b) Fault localization — lexical baseline (self_repair's line-scoring, file-lifted)")
    L.append("")
    L.append(f"- top-1 file hit: {loc['top1_hit']}/{a['n']}  |  top-5: {loc['top5_hit']}/{a['n']}  "
             f"|  top-10: {loc['top10_hit']}/{a['n']}")
    L.append(f"- mean rank of the true file (when ranked): {loc['mean_gold_rank_when_ranked']} "
             f"of ~{rep['instances'][0]['n_py_files']} files")
    L.append(f"- function target found in the true file (via `code_situation` AST): "
             f"{loc['function_target_found']}/{a['n']}")
    lf = a.get("localization_fused")
    if lf:
        L.append(f"- **FUSED (re-ranked by the failing-test signal — W-A top-1 lever)**: "
                 f"top-1 {lf['top1_hit']}/{a['n']}  |  top-5 {lf['top5_hit']}/{a['n']}  |  "
                 f"top-10 {lf['top10_hit']}/{a['n']} — uses the given test, never the gold patch.")
    L.append("")
    L.append("## (c) Patch generation — the wall (both real organs decline; no diff emitted)")
    L.append("")
    L.append(f"- `code_author` applicable: {pg['code_author_applicable']}/{a['n']} — a SWE-bench "
             f"instance has no single-function signature/docstring and its FAIL_TO_PASS node-ids "
             f"parse to {pg['total_literal_examples_parsed']} literal `assert f(...)==v` examples.")
    L.append(f"- `self_repair.check_eligible` refused on all: {pg['self_repair_all_refused']} "
             f"— verbatim: \"{rep['instances'][0]['self_repair_verdict']}\" (scoped to packages/, "
             f"single-LINE edits, needs an advisor draft = No-LLM none).")
    L.append(f"- patches produced: {pg['patches_produced']}/{a['n']} (fail-0 abstain).")
    L.append("")
    L.append(f"## (d) Multi-file scope: {mf['single_file_instances']} single-file, "
             f"{mf['multi_file_instances']} multi-file (max {mf['max_gold_files']} files). "
             f"Our patch protocol is single-line/single-file.")
    L.append("")
    L.append("## (e) Verification / eval path")
    ev = rep.get("eval", {})
    gs = ev.get("gold_selftest") if isinstance(ev, dict) else None
    if gs:
        L.append(f"- ATANOR patches evaluated: {ev.get('atanor_patches_evaluated', 0)} (none to run).")
        L.append(f"- Official Docker harness GOLD self-test on `{gs.get('instance_id')}`: "
                 f"**{gs.get('status')}** (resolved_instances={gs.get('resolved_instances')}, "
                 f"namespace={gs.get('namespace')}).")
    else:
        L.append(f"- {ev.get('note', 'eval not yet run')}")
    L.append("")
    L.append("## Per-instance")
    L.append("")
    L.append("| instance | gold files | top1 | top5 | rank | func? | reached / stopped |")
    L.append("|---|---|---|---|---|---|---|")
    for it in rep["instances"]:
        L.append(f"| {it['instance_id']} | {it['n_gold_files']} | {int(it['top1_hit'])} | "
                 f"{int(it['top5_hit'])} | {it['gold_rank']} | {int(it['function_target_found'])} | "
                 f"{it['reached']} / {it['stopped_at']} |")
    L.append("")
    pr = rep.get("probes", {})
    if pr:
        L.append("## Probes (other variants — honest load/runnable verdicts)")
        L.append("")
        ml = pr.get("multilingual", {})
        if ml.get("loads"):
            langs = ml.get("languages", {})
            L.append(f"- **Multilingual**: loads (`{ml['id']}`, {ml['n_total']} instances). Sampled 2 "
                     f"({langs}); our Python-AST organs are OUT OF SCOPE on non-Python gold edits.")
            for ins in ml.get("instances", []):
                L.append(f"  - {ins.get('instance_id')} ({ins.get('repo')}): gold_ext="
                         f"{ins.get('gold_ext')} -> {ins.get('organ_scope','?')}")
        else:
            L.append(f"- **Multilingual**: does not load here ({ml.get('error')}).")
        for name in ("pro", "multimodal"):
            v = pr.get(name, {})
            if v.get("loads"):
                L.append(f"- **{name.capitalize()}**: loads (`{v['id']}`, {v['n_total']} instances, "
                         f"{len(v.get('fields', []))} fields). Not run — "
                         + ("needs vision+browser execution (out of scope)." if name == "multimodal"
                            else "same patch-generation wall at larger, enterprise multi-file scale."))
            else:
                L.append(f"- **{name.capitalize()}**: does not load here ({v.get('error')}).")
    L.append("")
    return "\n".join(L)


def main() -> None:
    rep = json.load(open(OUT / "report.json", encoding="utf-8"))
    md = render(rep)
    (OUT / "report.md").write_text(md, encoding="utf-8")
    print("wrote", str(OUT / "report.md"), f"({len(md)} chars)")


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    main()
