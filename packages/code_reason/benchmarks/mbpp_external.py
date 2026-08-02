# -*- coding: utf-8 -*-
"""MBPP — the first EXTERNALLY authored yardstick for the code engine.

    python -m packages.code_reason.benchmarks.mbpp_external            # both slices
    python -m packages.code_reason.benchmarks.mbpp_external --slice sealed

WHY AN OUTSIDE BENCHMARK. `mastery_v1` reports 40/40. That number measures my hand, not the engine: I
wrote the tasks and I wrote the algorithm schemas that solve them. MBPP (Austin et al. 2021) was authored
by people who never saw this engine, which is the only property that makes a solve rate mean anything.

THE SPLIT IS THE POINT, and it is fixed by `docs/ATANOR_code_mastery_prereg.md` before any measurement:

    TUNE   (even task_id) -- may be inspected and iterated against
    SEALED (odd  task_id) -- measured once for the baseline, then left alone

The real risk was never a bad first number; it was tuning against the benchmark and then reporting that
benchmark. Any future claim of improvement has to show on the sealed slice, and an improvement visible
only on the tune slice will be reported as memorization.

NOTHING IS RESHAPED TO SUIT THE ENGINE. The task text becomes the docstring verbatim, the asserts become
the test verbatim, and the signature is recovered from the reference's `def` line -- the signature only,
never the body. A task whose signature cannot be recovered counts as an ABSTENTION, not an exclusion,
because dropping the tasks that do not fit is how a benchmark quietly becomes a demo.

WHAT IS REPORTED. Solve rate, abstention rate, and -- the one number that is a gate rather than a
measurement -- FABRICATION: a body that passed the visible asserts but fails MBPP's held-out
`challenge_test_list`. Solve rate is a capability claim and may be low without shame. Fabrication above
zero is a defect, because it means something shipped that the verifier should have caught.
"""
from __future__ import annotations

import argparse
import json
import re
import time
from dataclasses import replace
from pathlib import Path

from packages.code_reason.authorship_harness import Task, _run_candidate
from packages.code_reason.code_author import author

REPO = Path(__file__).resolve().parents[3]
OUT = REPO / "data" / "code_reason" / "mbpp_external.json"


def _fn_name(asserts: list[str]) -> str | None:
    """The function under test, read from the asserts rather than guessed from the prose."""
    for a in asserts:
        m = re.search(r"assert\s+\(?\s*(\w+)\s*\(", a)
        if m and m.group(1) not in ("abs", "round", "set", "len", "math", "isinstance", "tuple"):
            return m.group(1)
    return None


def _signature(code: str, fname: str) -> str | None:
    """The reference's `def` line for the tested function -- the SIGNATURE only, never the body.

    Giving the signature is standard for this benchmark family (HumanEval hands over the whole stub);
    what must never leak is the reference implementation."""
    for m in re.finditer(r"^def\s+(\w+)\s*\(([^)]*)\)\s*:", code, re.M):
        if m.group(1) == fname:
            return f"def {fname}({m.group(2)}):"
    return None


def _helpers(code: str, fname: str) -> str:
    """Some MBPP references define helper functions the tests do not call directly but the task needs
    (e.g. a `is_prime` used by the answer). Those are part of the PROBLEM SETUP, not the solution, so
    they are only carried over when they are not the tested function itself."""
    out = []
    for m in re.finditer(r"^(import\s+[\w., ]+|from\s+[\w.]+\s+import\s+[\w., *]+)$", code, re.M):
        out.append(m.group(0))
    return "\n".join(out)


def to_tasks(records: list[dict]) -> tuple[list[Task], int]:
    """Convert MBPP records to harness Tasks. Returns (tasks, n_unconvertible)."""
    tasks: list[Task] = []
    bad = 0
    for r in records:
        asserts = list(r.get("test_list") or [])
        fname = _fn_name(asserts)
        sig = _signature(r.get("code") or "", fname) if fname else None
        if not (fname and sig and asserts):
            bad += 1
            continue
        setup = (r.get("test_setup_code") or "").strip()
        imports = _helpers(r.get("code") or "", fname)
        preamble = "\n".join(x for x in (imports, setup) if x)
        visible = ("\n".join(asserts))
        hidden = "\n".join(r.get("challenge_test_list") or [])
        if preamble:
            visible = preamble + "\n" + visible
            hidden = (preamble + "\n" + hidden) if hidden else ""
        tasks.append(Task(name=f"mbpp_{r['task_id']}", signature=sig,
                          docstring=(r.get("text") or "").strip(),
                          test=visible, hidden=hidden))
    return tasks, bad


def load_mbpp() -> list[dict]:
    from datasets import load_dataset
    ds = load_dataset("google-research-datasets/mbpp", "full")
    rows: list[dict] = []
    for split in ds:
        rows.extend(dict(r) for r in ds[split])
    return rows


def run_slice(tasks: list[Task], label: str, *, verbose: bool = True) -> dict:
    solved = abstained = fabricated = 0
    by_source: dict[str, int] = {}
    fabricated_names: list[str] = []
    solved_names: list[str] = []
    t0 = time.time()
    for i, t in enumerate(tasks, 1):
        try:
            a = author(t)
        except Exception:
            a = None                       # a crash is an abstention, never a silent skip
        if a is None or not a.verified:
            abstained += 1
        else:
            solved += 1
            solved_names.append(t.name)
            by_source[a.source] = by_source.get(a.source, 0) + 1
            if t.hidden:                   # held-out check: did it only LOOK right?
                if not _run_candidate(replace(t, test=t.hidden), a.body).passed:
                    fabricated += 1
                    fabricated_names.append(t.name)
        if verbose and i % 50 == 0:
            print(f"  [{label}] {i}/{len(tasks)}  solved {solved}  abstained {abstained}  "
                  f"fabricated {fabricated}  ({time.time()-t0:.0f}s)", flush=True)
    n = max(1, len(tasks))
    return {
        "slice": label,
        "n_tasks": len(tasks),
        "solved": solved,
        "solve_rate": round(solved / n, 4),
        "abstained": abstained,
        "abstention_rate": round(abstained / n, 4),
        "fabricated": fabricated,
        "fabrication_rate": round(fabricated / max(1, solved), 4),
        "with_hidden_tests": sum(1 for t in tasks if t.hidden),
        "by_source": by_source,
        "fabricated_names": fabricated_names[:40],
        "solved_names": solved_names[:60],
        "elapsed_s": round(time.time() - t0, 1),
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--slice", choices=("both", "tune", "sealed"), default="both")
    ap.add_argument("--limit", type=int, default=0, help="debug only; 0 = the whole slice")
    args = ap.parse_args()

    rows = load_mbpp()
    tune_rows = [r for r in rows if r["task_id"] % 2 == 0]
    sealed_rows = [r for r in rows if r["task_id"] % 2 == 1]
    tune, bad_t = to_tasks(tune_rows)
    sealed, bad_s = to_tasks(sealed_rows)
    if args.limit:
        tune, sealed = tune[:args.limit], sealed[:args.limit]

    print(f"MBPP loaded: {len(rows)} records -> tune {len(tune)} (+{bad_t} unconvertible), "
          f"sealed {len(sealed)} (+{bad_s} unconvertible)")
    print("engine measured AS-IS; unconvertible tasks count as abstentions, not exclusions\n")

    out: dict = {"total_records": len(rows), "unconvertible": {"tune": bad_t, "sealed": bad_s}}
    if args.slice in ("both", "tune"):
        out["tune"] = run_slice(tune, "tune")
    if args.slice in ("both", "sealed"):
        out["sealed"] = run_slice(sealed, "sealed")

    # unconvertible tasks are abstentions of the whole pipeline, so fold them into the honest rate
    for key, bad, total in (("tune", bad_t, len(tune_rows)), ("sealed", bad_s, len(sealed_rows))):
        if key in out:
            s = out[key]
            s["solve_rate_over_all_records"] = round(s["solved"] / max(1, total), 4)
            s["records_in_split"] = total

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(out, indent=2), encoding="utf-8")
    print("\n" + "=" * 70)
    for key in ("tune", "sealed"):
        if key not in out:
            continue
        s = out[key]
        print(f"{key.upper():<7} solve {s['solved']}/{s['n_tasks']} = {s['solve_rate']:.1%}   "
              f"(over all {s['records_in_split']} records: {s['solve_rate_over_all_records']:.1%})")
        print(f"        abstain {s['abstention_rate']:.1%}   "
              f"FABRICATION {s['fabricated']} of {s['solved']} solved "
              f"({s['with_hidden_tests']} had held-out tests)")
        print(f"        by source: {s['by_source']}")
    print(f"\nwrote {OUT}")


if __name__ == "__main__":
    main()
