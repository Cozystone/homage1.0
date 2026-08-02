# -*- coding: utf-8 -*-
"""Repo-engineering deliberation — fault LOCALIZATION conducted as a DELIBERATION.

This is the allowed, minimal wiring the SWE-bench wave adds to the deliberator: a repo-engineering
PLAN over the same propose -> schedule -> dispatch -> VERIFY -> compose -> honest-abstain loop the
System-2 controller already runs, REUSING its primitives verbatim:

  * ``record_span`` (packages.metacog) — the MEC watch hook, so every localization hop is timed and
    folded into the same learned baselines as every other deliberation.
  * ``controller._schedule`` — the exact dependency-aware, cheap-first scheduler. With re-steer on it
    runs the CHEAP signals (path/​line score, import graph) BEFORE the EXPENSIVE per-function AST read
    — the mandate's "MEC schedules cheap signals before expensive AST", for free.
  * ``SubGoal`` / ``StepOutcome`` / the certificate shape — identical typed contracts.

What is NEW (and only this) is a small ORGAN ROUTER whose three adapters each CALL an already-verified
organ, never re-implement one:
  * ``file_scan``       -> packages.swe_eval.localizer.localize   (self_repair's line-scorer, file-lifted)
  * ``callgraph``       -> packages.swe_eval.callgraph.corroborate (a cheap import/def graph)
  * ``function_target`` -> packages.swe_eval.repo_reader.read_functions == code_situation AST reader

The deliberation proposes a structurally grounded localization candidate with a certificate. It
ABSTAINS honestly if it cannot even name a candidate file (fail-0: it never invents an edit site).
It holds ZERO parameters — a
controller over existing organs, exactly like the base deliberator. Localization is not patch
verification; the independent FAIL_TO_PASS/PASS_TO_PASS gate remains the final acceptance boundary.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Callable

from packages.deliberator.steps import SubGoal, StepOutcome
from packages.deliberator.controller import _schedule

try:
    from packages.metacog.probes import record_span
    _MEC = True
except Exception:                                     # pragma: no cover - MEC expected present
    _MEC = False

    def record_span(*_a, **_k):                        # type: ignore
        return None


# repo-engineering organ cost ranks (declared control constants, NOT knowledge). The AST read of a
# large file is the costliest, so MEC's cheap-first re-steer runs the path score + import graph first.
REPO_COST_RANK: dict[str, int] = {
    "file_scan": 1,        # lexical path+content score over the tree (cheap)
    "test_proximity": 2,   # re-rank by the failing-test signal (reads only test-proximate files; cheap)
    "callgraph": 3,        # a shallow import/def graph over the narrowed candidates
    "function_target": 5,  # per-function AST parse of the localized file (expensive)
}


@dataclass
class LocalizationResult:
    goal: str
    top_file: str | None
    ranked_files: list[str]
    target_function: str | None
    abstained: bool
    steps: list[StepOutcome] = field(default_factory=list)
    certificate: dict[str, Any] = field(default_factory=dict)
    mec: dict[str, Any] = field(default_factory=dict)
    reason: str | None = None

    @property
    def hops(self) -> int:
        return len(self.steps)


# ── organ adapters (each CALLS a verified organ; returns the deliberator's StepOutcome contract) ──

def _run_file_scan(problem: str, py_files: list[str],
                   read_file: Callable[[str], str | None]):
    """Returns (StepOutcome, Localization|None). The full lexical Localization is handed back so the
    test_proximity hop can re-rank the WHOLE candidate set (a gold file can sit at lexical rank 40 and
    still be the true site once the failing test is known)."""
    from packages.swe_eval import localizer as loc
    lz = loc.localize(problem, py_files, read_file=read_file)
    if not lz.ranked:
        return StepOutcome("file_scan", "rank candidate files", None, False,
                           {"organ": "file_scan", "grounded": False,
                            "reason": "no non-test candidate file scored above zero"}), None
    top = lz.ranked[0][0]
    return StepOutcome("file_scan", "rank candidate files", top, True,
                       {"organ": "file_scan", "grounded": True, "top1": top,
                        "top5": lz.topk(5), "considered": lz.considered,
                        "method": "lexical path+content score (self_repair line-scorer, file-lifted)"},
                       bind_value=top), lz


def _run_test_proximity(base_lz, sig, read_file: Callable[[str], str | None]) -> StepOutcome:
    """Re-rank the lexical localization by the FAILING-TEST signal (the mandate's stack-trace + call-
    graph-proximity-to-the-test lever): PRIMARY key = the test's package membership, then stem/import/
    symbol affinity, then the lexical score. Grounds when the test signal is active; it never fabricates
    a site — with no test signal it abstains and the lexical ranking stands."""
    from packages.swe_eval import localizer as loc
    if base_lz is None or not sig.active:
        return StepOutcome("test_proximity", "re-rank by the failing test", None, False,
                           {"organ": "test_proximity", "grounded": False,
                            "reason": "no failing-test signal available -> keep the lexical ranking"})
    fused = loc.fuse_ranking(base_lz.ranked, sig, read_file)
    top = fused[0][0] if fused else None
    top5 = [p for p, _ in fused[:5]]
    return StepOutcome("test_proximity", "re-rank by the failing test", top, bool(top),
                       {"organ": "test_proximity", "grounded": bool(top), "top1": top, "top5": top5,
                        "test_files": sig.test_files, "pkg_dirs": sig.pkg_dirs,
                        "test_stems": sig.test_stems,
                        "n_imported_modules": len(sig.imported_modules),
                        "method": "failing-test proximity (package tier -> stem/import/symbol -> lexical); "
                                  "uses the given test, never the gold patch"},
                       bind_value=top)


def _run_callgraph(issue_tokens: set[str], top_file: str, candidates: list[str],
                   read_file: Callable[[str], str | None]) -> StepOutcome:
    from packages.swe_eval import callgraph as cg
    corr = cg.corroborate(issue_tokens, top_file, candidates, read_file)
    grounded = bool(corr.top_defines or corr.defines_issue_symbol or corr.importers_of_top)
    return StepOutcome("callgraph", "corroborate the top file structurally", top_file, grounded,
                       {"organ": "callgraph", "grounded": grounded,
                        "top_defines_issue_symbol": corr.top_defines,
                        "other_files_defining_issue_symbol": corr.defines_issue_symbol,
                        "importers_of_top": corr.importers_of_top,
                        "reason": None if grounded else "no structural corroboration for the top file"},
                       bind_value=top_file)


def _run_function_target(issue_tokens: set[str], top_file: str,
                         read_file: Callable[[str], str | None]) -> StepOutcome:
    from packages.swe_eval import repo_reader as rr
    src = read_file(top_file)
    if not src:
        return StepOutcome("function_target", "find an issue-named candidate function", None, False,
                           {"organ": "function_target", "grounded": False,
                            "authority": "candidate_only",
                            "reason": f"could not read {top_file} at base_commit"})
    sits = rr.read_functions(src)     # == code_situation.build over every function (the AST reader)
    named = [s for s in sits if s.name.lower() in issue_tokens]
    target = named[0].name if named else None
    grounded = bool(target)
    return StepOutcome("function_target", "find an issue-named candidate function", target, grounded,
                       {"organ": "function_target", "grounded": grounded,
                        "authority": "candidate_only",
                        "n_functions_read": len(sits),
                        "function_identified": target,
                        "candidate_functions": [s.name for s in named][:8],
                        "reason": None if grounded else "no issue-named function candidate found in the AST",
                        "method": "structural issue-token/AST-name overlap; candidate only, not proof of edit site"},
                       bind_value=target)


# ── the deliberation (reuses controller._schedule + record_span + the certificate contract) ───────

def deliberate_localization(problem_statement: str, py_files: list[str],
                            read_file: Callable[[str], str | None],
                            issue_tokens: set[str], *, f2p: list[str] | None = None,
                            test_patch: str = "", resteer: bool = True,
                            mec: bool = True) -> LocalizationResult:
    """Propose an edit-site candidate through structurally grounded localization.

    file_scan (cheap) grounds a lexical ranking;
    when the FAILING TEST is known, a test_proximity hop re-ranks by the test's package/stem/import/
    symbol signal (the W-A top-1 lever); MEC then runs the cheap callgraph corroboration before the
    expensive AST function read; the answer composes a ranked localization + certificate ONLY from
    grounded steps. The result remains candidate-only; the regression gate verifies a patch.
    Abstains if no file grounds. Uses the given failing test, never the gold patch.
    """
    from packages.swe_eval import localizer as loc
    t_all = time.perf_counter()
    sig = loc.build_test_signal(f2p or [], test_patch, read_file)
    have_test = sig.active
    # the plan: file_scan binds `top_file`; when a failing-test signal exists, test_proximity re-ranks
    # and RE-binds the top file (function_target + callgraph then consume the re-ranked top). The
    # EXPENSIVE function_target (per-function AST read) is DECLARED before the cheap callgraph on
    # purpose — so the MEC cheap-first re-steer visibly REALLOCATES the order (cheap graph before the
    # expensive AST), the mandate's "MEC schedules cheap signals before expensive AST".
    site = "top_file2" if have_test else "top_file"
    plan = [SubGoal("file_scan", "which file?", {"problem": "{__seed__}"}, binds="top_file")]
    if have_test:
        plan.append(SubGoal("test_proximity", "re-rank by the failing test",
                            {"top_file": "{top_file}"}, binds="top_file2"))
    plan += [
        SubGoal("function_target", "which candidate function, if any?",
                {"top_file": "{" + site + "}"}, binds="target_fn"),
        SubGoal("callgraph", "why this file? (structural corroboration)",
                {"top_file": "{" + site + "}"}, binds="corroborated"),
    ]
    # reuse the deliberator's own cost-ranked, dependency-aware scheduler by temporarily exposing the
    # repo organ costs to it (it reads COST_RANK.get(organ, 9); unknown organs sort last, which would
    # break cheap-first — so we schedule with a repo-aware key of the same shape).
    order = _schedule_repo(plan, resteer)

    steps: list[StepOutcome] = []
    top_file: str | None = None
    target_fn: str | None = None
    ranked_files: list[str] = []
    base_lz = None
    abstained = False
    reason: str | None = None
    ungrounded: dict[str, Any] | None = None

    for idx in order:
        sg = plan[idx]
        if sg.organ == "file_scan":
            out, base_lz = _run_file_scan(problem_statement, py_files, read_file)
            if out.grounded:
                top_file = out.bind_value
                ranked_files = out.certificate.get("top5", [])
        elif sg.organ == "test_proximity":
            if base_lz is None:
                continue
            out = _run_test_proximity(base_lz, sig, read_file)
            if out.grounded:
                top_file = out.bind_value
                ranked_files = out.certificate.get("top5", ranked_files)
        elif sg.organ == "callgraph":
            if not top_file:
                continue
            out = _run_callgraph(issue_tokens, top_file, ranked_files or py_files[:25], read_file)
        elif sg.organ == "function_target":
            if not top_file:
                continue
            out = _run_function_target(issue_tokens, top_file, read_file)
            if out.grounded:
                target_fn = out.bind_value
        else:
            continue
        steps.append(out)
        if mec:
            record_span(f"repo_deliberation.step.{out.organ}", out.ms if out.ms else 0.0,
                        ok=out.grounded, meta={"grounded": out.grounded, "abstained": not out.grounded})
        # only file_scan is REQUIRED — without a file there is nothing to localize -> honest abstain
        if sg.organ == "file_scan" and not out.grounded:
            abstained = True
            reason = "I can't ground any candidate file for this issue, so I won't guess an edit site."
            ungrounded = {"organ": out.organ, "certificate": out.certificate}
            break

    total_ms = (time.perf_counter() - t_all) * 1000.0
    if mec:
        record_span("repo_deliberation.localization", total_ms, ok=(not abstained),
                    meta={"goal": "fault localization", "hops": len(steps), "abstained": abstained})

    baseline_order = list(range(len(plan)))
    certificate = {
        "goal": "fault localization",
        "plan_size": len(plan),
        "hops_executed": len(steps),
        "abstained": abstained,
        "execution_order": order,
        "top_file": top_file,
        "ranked_files": ranked_files,
        "target_function": target_fn,
        "steps": [{"organ": s.organ, "grounded": s.grounded, "answer": s.answer,
                   "certificate": s.certificate} for s in steps],
        "guarantees": {
            "external_llm": False,
            "free_generation": False,
            "fabricated_facts": False,
            # This is a localization proposal, not the independent regression
            # verdict. Structural grounding must not be renamed verification.
            "every_executed_step_verified": False,
            "every_executed_step_structurally_grounded": (
                all(s.grounded for s in steps) if steps else False
            ),
            "localization_authority": "candidate_only",
            "patch_verification_performed": False,
            "abstained_rather_than_guess_site": abstained,
        },
    }
    mec_summary = {
        "wrapped": bool(mec and _MEC),
        "resteer": resteer,
        "execution_order": order,
        "baseline_order": baseline_order,
        "reordered": order != baseline_order,
        "localization_ms": round(total_ms, 3),
        "note": ("MEC scheduled the cheap file/import signals before the expensive per-function AST "
                 "read; it only reallocates order and reports latency — it never fabricates a step"),
    }
    return LocalizationResult(goal="fault localization", top_file=top_file, ranked_files=ranked_files,
                              target_function=target_fn, abstained=abstained, steps=steps,
                              certificate=certificate, mec=mec_summary, reason=reason)


def _schedule_repo(plan: list[SubGoal], resteer: bool) -> list[int]:
    """Dependency-aware, cheap-first order over the repo plan — the same algorithm as
    controller._schedule but keyed by REPO_COST_RANK (so file_scan(1) < callgraph(2) < AST(5))."""
    n = len(plan)
    produced_by = {sg.binds: i for i, sg in enumerate(plan) if sg.binds}
    deps = [{produced_by[name] for name in sg.references() if name in produced_by} for sg in plan]
    order: list[int] = []
    done: set[int] = set()
    while len(order) < n:
        ready = [i for i in range(n) if i not in done and deps[i] <= done] or \
                [i for i in range(n) if i not in done]
        if resteer:
            nxt = min(ready, key=lambda i: (REPO_COST_RANK.get(plan[i].organ, 9), i))
        else:
            nxt = min(ready)
        order.append(nxt)
        done.add(nxt)
    return order


def ledger_entry():
    """A zero-parameter ledger row for the repo-engineering deliberation, mirroring the base
    deliberator's honest declaration (a controller over existing organs; never a fact source)."""
    from packages.neuro_ledger.ledger import Organ
    return Organ(
        id="repo_engineering_deliberation",
        path="packages/deliberator/repo_engineering.py",
        role="repo-engineering LOCALIZATION deliberation: decomposes 'where is the fault' into "
             "which-file / why-this-file / which-function typed sub-goals, dispatches each to an "
             "EXISTING organ (localizer line-scorer, import/def graph, code_situation AST reader), "
             "MEC-schedules cheap signals before the expensive AST read, and composes a ranked "
             "localization with a certificate or abstains; holds NO trained weights",
        gate="repo-engineering deliberation (reuses controller._schedule + metacog.record_span; "
             "each hop behind its organ's own grounding)",
        artifacts=[],
        fact_source=False,
        enforced=False,
        status="active",
        fallback_params=0,
    )
