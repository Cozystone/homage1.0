# -*- coding: utf-8 -*-
"""Repair cycle — the CLOSED loop: notice a recurring defect, obtain an applicable patch, stage it,
judge it by the constitution and by measurement, then keep it or put everything back.

Owner (2026-07-21): "자기수리 폐루프 완성해." The open loop's limit was measured, not guessed: over
one autonomous night GPT-5.4 reported the same surface defect three separate times and the code
never changed, because the only thing that could turn a critique into an edit was a human reading
logs in the morning. This module removes that step.

  defect (repeated sightings)  ->  ask the advisor for ONE search/replace edit
      ->  protocol checks (constitution / scope / exact-once anchor / it must still parse)
      ->  STAGE: write it, with the original held in memory and restored in `finally`
      ->  JUDGE: full test suite green?  every measured gate held or improved?
      ->  ALLOW: keep it.   REJECT: restore byte-for-byte.   ERROR: restore byte-for-byte.
  Every outcome is journaled with its reason.

The judgement is `auto_self_modification.evaluate_change` — not re-implemented here, so the child
cannot get a softer verdict by asking a different organ. Tests are constitutionally immutable, so a
patch can never make itself pass by editing the examiner.

Honest scope: staging is an in-place write guarded by an unconditional restore, not a second
checkout — the window is one test run long and any failure (including a crash) puts the file back.
The claim this loop earns is "safe and non-regressing by the measured battery", never "correct".
"""
from __future__ import annotations

import json
import re
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

from packages.advisor_loop.advisor_session import ask_cli
from packages.continuous_self.auto_self_modification import evaluate_change, live_battery
from packages.self_repair import defect_ledger as dl
from packages.self_repair.patch_protocol import (PATCH_FORMAT, Edit, apply_text, check_eligible,
                                                 parse_patch)

REPO = Path(__file__).resolve().parents[2]
LOG = REPO / "data" / "self_repair" / "cycles.jsonl"

# The suite that must stay green. Broad enough that a body change cannot quietly break a neighbour.
TEST_PATHS = ["packages/realizer_struct", "packages/brain_link/tests",
              "packages/advisor_loop/tests", "packages/situation_model",
              "packages/continuous_self"]


_FAILED_RE = re.compile(r"^FAILED\s+(\S+)", re.M)


def run_tests(timeout_s: int = 600) -> tuple[bool, str, set[str]]:
    """The real suite, in a subprocess (a fresh interpreter sees the patched file on disk).
    Returns (all_green, summary_line, set_of_failing_test_ids)."""
    try:
        p = subprocess.run([sys.executable, "-m", "pytest", *TEST_PATHS, "-q",
                            "--import-mode=importlib"],
                           cwd=str(REPO), capture_output=True, text=True, timeout=timeout_s,
                           encoding="utf-8", errors="replace")
    except subprocess.TimeoutExpired:
        return False, "test suite timed out", {"<timeout>"}
    out = p.stdout or ""
    failed = set(_FAILED_RE.findall(out))
    tail = out.strip().splitlines()
    return p.returncode == 0, (tail[-1] if tail else "no test output"), failed


# The advisor CLI runs through a cmd.exe shim, whose command line dies past ~8191 characters. A
# 7000-char file dump blew straight through it and came back as a truncated-message error, so the
# whole prompt is budgeted — and the source is a RELEVANT WINDOW, not the file head.
MAX_PROMPT_CHARS = 6200
MAX_SOURCE_CHARS = 3200
WINDOW_PAD = 14


def _relevant_window(path_text: str, terms: set[str]) -> str:
    """The region of the file the defect is actually about, numbered so an anchor can be copied
    verbatim. Sending the head of a long file usually misses the fault entirely; scoring lines by
    the defect's own vocabulary lands on it."""
    lines = path_text.splitlines()
    scores = [(sum(1 for t in terms if t and t in ln.lower()), i) for i, ln in enumerate(lines)]
    best = max(scores, default=(0, 0))
    centre = best[1] if best[0] else 0
    lo = max(0, centre - WINDOW_PAD)
    body, used = [], 0
    for i in range(lo, len(lines)):
        row = f"{i + 1:4d}| {lines[i]}"
        if used + len(row) > MAX_SOURCE_CHARS:
            body.append(f"... ({len(lines) - i} more lines)")
            break
        body.append(row)
        used += len(row) + 1
    return "\n".join(body)


def _source_excerpt(hints: list[str], terms: set[str] | None = None) -> tuple[str, str]:
    """The file the reviewers were looking at, windowed to the defect. Without real source the
    advisor cannot produce a verbatim anchor and honestly answers NO PATCH — the first live cycle
    failed exactly there. Returns (path, numbered_text)."""
    for h in hints:
        p = REPO / h
        if p.is_file():
            return h, _relevant_window(p.read_text(encoding="utf-8"), terms or set())
    return "", ""


def build_request(defect: dl.Defect) -> str:
    """Ask for an EDIT, not an essay — the advisors' own repeated words, plus the real source
    region. Kept inside MAX_PROMPT_CHARS: the transport silently dies on an oversized command
    line, and a request that never arrives looks exactly like an advisor with nothing to say."""
    quotes = "\n".join(f"  - {q[:260]}" for q in defect.best_quotes(2))
    terms = {t for q in defect.best_quotes(2) for t in dl._terms(q)}
    path, source = _source_excerpt(defect.hints, terms)
    where = (f"\nFile under review: {path}\n```\n{source}\n```\n" if source else "\n")
    req = (
        "You are repairing ATANOR, a No-LLM graph-native AI. Reviewers independently reported this "
        f"same defect {defect.sightings} time(s):\n{quotes}\n{where}\n"
        "Propose ONE minimal fix as a search/replace edit in EXACTLY this format, nothing else:\n"
        f"{PATCH_FORMAT}\n\n"
        "Hard rules: OLD must be a SINGLE LINE that currently exists in that file, copied verbatim "
        "WITHOUT its line number, and unique in the file. Change as little as possible. You may not "
        "edit tests or any gate — those are immutable and auto-refused. If no real single-line edit "
        "fixes it, reply exactly: NO PATCH. Output the block only, no commentary."
    )
    return req if len(req) <= MAX_PROMPT_CHARS else req[:MAX_PROMPT_CHARS]


def _journal(rec: dict[str, Any]) -> None:
    LOG.parent.mkdir(parents=True, exist_ok=True)
    with LOG.open("a", encoding="utf-8") as f:
        f.write(json.dumps(rec, ensure_ascii=False) + "\n")


def stage_and_judge(edit: Edit, battery_before: dict[str, float],
                    failing_before: set[str] | None = None) -> dict[str, Any]:
    """Write the edit, run the real gate, and restore unconditionally unless it is ALLOWED.
    The restore lives in `finally`: a crash mid-judgement still puts the file back.

    `failing_before` is the suite's PRE-EXISTING failure set. Judging on absolute green was tried
    and proved to be a reject-everything machine: one unrelated red test (test_voice, failing on
    its own) made every conceivable repair look like self-damage — a gate that can never say yes is
    not a safety property, it is a broken instrument that merely looks strict. "No self-damage"
    honestly means INTRODUCES NO NEW FAILURE; inherited breakage is not this patch's doing (and is
    never silently cleared — the caller journals it)."""
    original, patched = apply_text(edit)
    target = edit.target()
    known = failing_before or set()
    keep = False
    try:
        target.write_text(patched, encoding="utf-8")
        ok, tail, failed = run_tests()
        new_failures = sorted(failed - known)
        verdict = evaluate_change(changed_paths=[edit.path],
                                  run_battery=live_battery,
                                  tests_pass=lambda: not new_failures,
                                  battery_before=battery_before)
        keep = verdict.allow
        return {"allow": verdict.allow, "reason": verdict.reason, "tests_tail": tail,
                "regressions": verdict.regressions, "new_failures": new_failures,
                "preexisting_failures": sorted(known), "all_green": ok,
                "battery_before": verdict.battery_before, "battery_after": verdict.battery_after}
    finally:
        if not keep:
            target.write_text(original, encoding="utf-8")     # byte-for-byte, always


def run_cycle(advisor: str = "openclaw", now_utc: float = 0.0) -> dict[str, Any]:
    """One full closed-loop attempt. Returns the outcome record (also journaled)."""
    ts = now_utc or time.time()
    defect = dl.top_defect(exclude_keys=dl.attempted_keys())
    if defect is None:
        rec = {"outcome": "no_defect", "detail": "no unattempted defect in the ledger", "ts": ts}
        _journal(rec)
        return rec

    def _finish(outcome: str, detail: str, extra: dict | None = None) -> dict[str, Any]:
        dl.journal(defect, outcome, detail, now_utc=ts)
        rec = {"outcome": outcome, "detail": detail, "defect_key": defect.key,
               "sightings": defect.sightings, "advisor": advisor, "ts": ts} | (extra or {})
        _journal(rec)
        return rec

    try:
        reply = ask_cli(advisor, build_request(defect), timeout_s=300).reply
    except Exception as e:
        return _finish("advisor_unavailable", type(e).__name__)
    if "NO PATCH" in reply.upper():
        return _finish("no_patch_offered", "advisor declined to propose an edit")
    edit, why = parse_patch(reply)
    if edit is None:
        return _finish("unparseable", why, {"reply_head": reply[:200]})
    refusal = check_eligible(edit)
    if refusal:
        return _finish("refused", refusal, {"path": edit.path})

    before = live_battery()
    _, base_tail, failing_before = run_tests()      # what is ALREADY red, before we touch it
    try:
        judged = stage_and_judge(edit, before, failing_before)
    except Exception as e:                    # the file is already restored by `finally`
        return _finish("staging_error", f"{type(e).__name__}: {e}", {"path": edit.path})
    outcome = "applied" if judged["allow"] else "rejected"
    return _finish(outcome, judged["reason"],
                   {"path": edit.path, "tests_tail": judged["tests_tail"],
                    "new_failures": judged["new_failures"],
                    "preexisting_failures": judged["preexisting_failures"],
                    "regressions": judged["regressions"],
                    "battery_before": judged["battery_before"],
                    "battery_after": judged["battery_after"],
                    "old": edit.old[:300], "new": edit.new[:300]})
