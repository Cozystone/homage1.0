# -*- coding: utf-8 -*-
"""The end-to-end pipeline for ONE SWE-bench instance, instrumented STAGE BY STAGE.

The deliverable is not a resolved%, it is a precise map of WHERE ATANOR's real code organs stop on a
repo-scale bug. Every stage below is run with the ACTUAL organ, and the outcome is recorded, never
narrated:

  (a) comprehension     — repo_reader: blobless clone + tree at base_commit (single-function AST is
                          the only structural model we have).
  (b) file localization — localizer (self_repair's lexical principle, file-lifted); scored vs gold.
  (b2) function target  — code_situation.build over the localized file: does the issue name a
                          function/class that exists there? (real organ, real repo code)
  (c) patch generation  — the two real organs are asked, and both honestly decline at this scale:
                            * code_author.author needs a single-function Task (signature + docstring
                              + literal-assert visible test). A SWE-bench instance has none, so no
                              Task can be formed and the FAIL_TO_PASS node-ids parse to ZERO literal
                              (args->expected) examples. Inapplicable -> abstain.
                            * self_repair.check_eligible on the real target path REFUSES: the repair
                              organ is scoped to packages/ only and does single-LINE edits with an
                              advisor draft (No-LLM: none). We capture its verbatim refusal.
  (d) multi-file scope   — recorded from the gold patch (how many files a real fix touches).
  (e) verification       — nothing to verify (fail-0: never emit an unverifiable diff). resolved=False.

STAGES lists the furthest stage reached. patch is always None here — abstention is the honest floor.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from packages.code_reason import code_author as ca
from packages.code_reason import code_situation as cs
from packages.code_reason.authorship_harness import Task
from packages.self_repair.patch_protocol import Edit, check_eligible
from packages.swe_eval import localizer as loc
from packages.swe_eval import repo_reader as rr

# Linear pipeline gates every instance passes through. `function_target` is NOT here: it is a
# SUB-capability of localization (did we identify the function to edit within the file?), measured
# separately (function_target_found), because the pipeline does not STOP on it — reporting it as a
# 10/10 linear stage would conflate "passed through" with "succeeded".
STAGES = ["loaded", "comprehension", "file_localization", "patch_generation", "verification"]

# The shape code_author.author requires of a visible test: assert f(...) == <literal>.
_LITERAL_ASSERT = re.compile(r"assert\s+\w+\s*\(.*\)\s*==")


@dataclass
class InstanceResult:
    instance_id: str
    repo: str
    base_commit: str
    reached: str = "loaded"                       # furthest stage
    stopped_at: str = ""                          # the stage that blocked us
    n_py_files: int = 0
    gold_files: list[str] = field(default_factory=list)
    n_gold_files: int = 0
    top1: str | None = None
    top1_hit: bool = False
    top5_hit: bool = False
    top10_hit: bool = False
    gold_rank: int = -1                           # 1-based rank of first gold file (-1 = not ranked)
    # FUSED localization (lexical RE-RANKED by the failing-test signal — the W-A top-1 lever). Measured
    # on the SAME sample; uses the given failing test, never the gold patch.
    fused_top1: str | None = None
    fused_top1_hit: bool = False
    fused_top5_hit: bool = False
    fused_top10_hit: bool = False
    fused_gold_rank: int = -1
    function_target_found: bool = False
    n_literal_examples: int = 0                   # examples code_author could parse (expect 0)
    code_author_applicable: bool = False
    self_repair_verdict: str = ""
    patch: str | None = None
    resolved: bool = False
    notes: list[str] = field(default_factory=list)


def _first_gold_rank(ranked: list[tuple[str, float]], gold: set[str]) -> int:
    for i, (p, _) in enumerate(ranked, 1):
        if p in gold:
            return i
    return -1


def run_instance(inst: dict[str, Any], clone_timeout_s: int = 300) -> InstanceResult:
    r = InstanceResult(instance_id=inst["instance_id"], repo=inst["repo"],
                       base_commit=inst["base_commit"])
    gold = loc.gold_files(inst["patch"])
    r.gold_files, r.n_gold_files = gold, len(gold)

    # (a) COMPREHENSION -------------------------------------------------------------------------
    clone = rr.ensure_clone(inst["repo"], timeout_s=clone_timeout_s)
    if not clone.ok:
        r.stopped_at = "comprehension"
        r.notes.append(f"clone: {clone.detail}")
        return r
    py_files = rr.list_py_files(clone.path, inst["base_commit"])
    r.n_py_files = len(py_files)
    if not py_files:
        r.stopped_at = "comprehension"
        r.notes.append("tree: could not list files at base_commit (checkout/fetch failed)")
        return r
    r.reached = "comprehension"

    # (b) FILE LOCALIZATION ---------------------------------------------------------------------
    read_at_base = lambda p: rr.read_file(clone.path, inst["base_commit"], p)
    lz = loc.localize(inst["problem_statement"], py_files, read_file=read_at_base)
    goldset = set(gold)
    r.top1 = lz.top1
    r.top1_hit = bool(set(lz.topk(1)) & goldset)
    r.top5_hit = bool(set(lz.topk(5)) & goldset)
    r.top10_hit = bool(set(lz.topk(10)) & goldset)
    r.gold_rank = _first_gold_rank(lz.ranked, goldset)
    # FUSED: re-rank by the failing-test signal (spec, not gold) — the top-1 lever
    import json as _json
    f2p_raw = inst.get("FAIL_TO_PASS", [])
    f2p_list = _json.loads(f2p_raw) if isinstance(f2p_raw, str) else list(f2p_raw)
    fz, _sig = loc.localize_fused(inst["problem_statement"], py_files, read_at_base,
                                  f2p=f2p_list, test_patch=inst.get("test_patch", ""))
    r.fused_top1 = fz.top1
    r.fused_top1_hit = bool(set(fz.topk(1)) & goldset)
    r.fused_top5_hit = bool(set(fz.topk(5)) & goldset)
    r.fused_top10_hit = bool(set(fz.topk(10)) & goldset)
    r.fused_gold_rank = _first_gold_rank(fz.ranked, goldset)
    r.reached = "file_localization"

    # (b2) FUNCTION TARGET (real code_situation over the true edit file) -------------------------
    issue_toks = loc._tokens(inst["problem_statement"])
    target_file = gold[0] if gold else lz.top1
    src = rr.read_file(clone.path, inst["base_commit"], target_file) if target_file else None
    if src:
        sits = rr.read_functions(src)
        fn_names = {s.name.lower() for s in sits}
        class_names = {c.lower() for c in re.findall(r"^\s*class\s+(\w+)", src, re.M)}
        r.function_target_found = bool((fn_names | class_names) & issue_toks)
        r.notes.append(f"code_situation read {len(sits)} functions in {target_file}; "
                       f"function target {'identified' if r.function_target_found else 'NOT identified'}")

    # (c) PATCH GENERATION — ask both real organs; both decline at repo scale -------------------
    # code_author: can we even FORM a Task? Parse the visible test for literal (args->expected).
    task = Task(name=r.instance_id, signature="def _unknown():",
                docstring=inst["problem_statement"][:500],
                test="\n".join(_as_asserts(inst)))
    examples = ca._parse_examples(task)
    r.n_literal_examples = len(examples)
    r.code_author_applicable = bool(_LITERAL_ASSERT.search(task.test)) and len(examples) > 0
    if not r.code_author_applicable:
        r.notes.append("code_author: inapplicable — no single-function spec; FAIL_TO_PASS parses to "
                       f"{len(examples)} literal examples")
    # self_repair: ask the real eligibility gate about the true target path
    verdict = check_eligible(Edit(path=target_file or "unknown.py",
                                  old="# anchor", new="# anchor2")) or "eligible"
    r.self_repair_verdict = verdict[:180]
    r.notes.append(f"self_repair.check_eligible -> {r.self_repair_verdict}")

    r.reached = "patch_generation"          # we reached the stage; we did not clear it
    r.stopped_at = "patch_generation"       # fail-0: no verifiable diff -> abstain
    r.patch = None

    # (e) VERIFICATION — nothing to verify; abstention is honest, resolved stays False -----------
    r.resolved = False
    return r


def _as_asserts(inst: dict[str, Any]) -> list[str]:
    """Best-effort: expose FAIL_TO_PASS as the 'visible test'. They are pytest node-ids, not literal
    asserts, which is exactly the shape gap this records (parses to zero code_author examples)."""
    import json
    f2p = inst.get("FAIL_TO_PASS", [])
    if isinstance(f2p, str):
        try:
            f2p = json.loads(f2p)
        except Exception:
            f2p = [f2p]
    return [f"# FAIL_TO_PASS: {t}" for t in f2p]


def organ_liveness() -> dict[str, Any]:
    """Control: run code_author on its own in-domain seed tasks, to prove the author organ is LIVE
    (so a 0/N on SWE-bench is attributable to SCALE, not a broken organ)."""
    from packages.code_reason.authorship_harness import seed_tasks
    res = ca.author_suite(seed_tasks())
    return {"seed_tasks": res["n_tasks"], "authored_pass": res["authored_pass"],
            "authorship_rate": res["authorship_rate"], "by_source": res["by_source"]}
