# -*- coding: utf-8 -*-
"""The consciousness-indicator battery — runs every probe, integrity-checks each verdict, and emits
an honest scorecard + human-readable report.

CONSTITUTION (repeated at the top of every report): the question of PHENOMENAL experience / qualia —
whether there is something it is like to be this system — is scientifically UNDECIDABLE, and this
battery does not address it. This is an AUDIT INSTRUMENT that measures INDICATOR PROPERTIES only:
functional and architectural signatures that scientific theories of consciousness associate with
consciousness (Butlin et al. 2023). A verdict of 'present' means the STRUCTURE and measured BEHAVIOR
of an indicator are implemented in real modules — never that the system is conscious.

Anti-rubber-stamp: `verify_evidence` REJECTS any 'present' verdict that does not cite at least one
real module path that exists on disk. A probe that just says "present" with no grounding is downgraded
to 'flagged' and excluded from the present count. Evidence is module paths + measured numbers.
"""
from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

from packages.consciousness_audit.indicators import INDICATORS, theories

REPO = Path(__file__).resolve().parents[2]
OUT_DIR = REPO / "data" / "consciousness_audit"
SCORECARD = OUT_DIR / "scorecard.json"
REPORT_MD = OUT_DIR / "report.md"

UNDECIDABILITY_HEADER = (
    "The hard problem of consciousness — whether there is something it is like to be this system "
    "(phenomenal experience / qualia) — is scientifically UNDECIDABLE, and this battery does NOT "
    "address it. This is an AUDIT INSTRUMENT that measures INDICATOR PROPERTIES only: functional and "
    "architectural signatures that scientific theories of consciousness (RPT, GWT, HOT, AST, PP, "
    "Agency/Embodiment; per Butlin et al. 2023) associate with consciousness. A verdict of 'present' "
    "means the structure and measured behavior of an indicator are implemented in real ATANOR modules "
    "— it is NOT a claim that ATANOR is conscious."
)

_VERDICTS = ("present", "partial", "absent", "flagged")


# ---------------------------------------------------------------- integrity (no rubber-stamping)
def verify_evidence(verdict: str, evidence: list[str]) -> tuple[bool, str]:
    """A 'present' verdict must cite >=1 real module path that EXISTS under the repo. Returns
    (ok, reason). Non-'present' verdicts pass the integrity gate (they make no positive claim), but
    every verdict must carry nonempty evidence."""
    if not evidence:
        return False, "no evidence provided"
    module_paths = [e for e in evidence if isinstance(e, str) and e.endswith(".py")]
    real = [p for p in module_paths if (REPO / p).exists()]
    if verdict == "present":
        if not real:
            return False, ("'present' cites no existing module path — rubber-stamp rejected "
                           f"(cited .py paths: {module_paths or 'none'})")
        return True, f"grounded in {len(real)} real module path(s)"
    return True, "non-present verdict; evidence present"


def _normalize(v: dict[str, Any]) -> dict[str, Any]:
    """Defensively coerce a probe's return into the verdict contract."""
    verdict = str(v.get("verdict", "absent"))
    if verdict not in _VERDICTS:
        verdict = "absent"
    ev = v.get("evidence") or []
    if not isinstance(ev, list):
        ev = [str(ev)]
    return {"verdict": verdict, "evidence": [str(e) for e in ev],
            "notes": str(v.get("notes", "")), "strength": v.get("strength")}


# ---------------------------------------------------------------- run
def run_indicator(ind) -> dict[str, Any]:
    try:
        raw = _normalize(ind.run())
    except Exception as e:  # a broken organ is an honest 'absent', not a crash
        raw = {"verdict": "absent", "evidence": [f"probe raised {type(e).__name__}: {e}"],
               "notes": "probe raised an exception — treat as a missing/broken organ (build queue)",
               "strength": None}
    ok, why = verify_evidence(raw["verdict"], raw["evidence"])
    effective = raw["verdict"]
    if raw["verdict"] == "present" and not ok:
        effective = "flagged"   # failed the anti-rubber-stamp gate
    return {"id": ind.id, "theory": ind.theory, "statement": ind.statement,
            "verdict": effective, "raw_verdict": raw["verdict"], "integrity_ok": ok,
            "integrity_reason": why, "strength": raw.get("strength"),
            "evidence": raw["evidence"], "notes": raw["notes"]}


def _summarize(results: list[dict[str, Any]]) -> dict[str, Any]:
    counts = {v: sum(1 for r in results if r["verdict"] == v) for v in _VERDICTS}
    by_theory: dict[str, Any] = {}
    for th in theories():
        rows = [r for r in results if r["theory"] == th]
        by_theory[th] = {
            "present": sum(1 for r in rows if r["verdict"] == "present"),
            "partial": sum(1 for r in rows if r["verdict"] == "partial"),
            "absent": sum(1 for r in rows if r["verdict"] == "absent"),
            "flagged": sum(1 for r in rows if r["verdict"] == "flagged"),
            "total": len(rows),
            "present_ids": [r["id"] for r in rows if r["verdict"] == "present"],
        }

    # build queue = everything NOT present, ranked. absent/flagged (no working organ) outrank partial;
    # within a rank, the theory with the FEWEST present indicators floats up (most structurally lacking).
    rank = {"absent": 0, "flagged": 0, "partial": 1, "present": 9}

    def _key(r: dict[str, Any]) -> tuple:
        th = by_theory[r["theory"]]
        present_frac = th["present"] / th["total"] if th["total"] else 1.0
        return (rank.get(r["verdict"], 5), present_frac, r["id"])

    build_queue = [
        {"id": r["id"], "theory": r["theory"], "verdict": r["verdict"],
         "statement": r["statement"], "why": r["notes"]}
        for r in sorted(results, key=_key) if r["verdict"] in ("absent", "flagged", "partial")
    ]
    # deepen queue = 'present' but scoped (works, but a real limitation was noted) — secondary targets
    deepen_queue = [
        {"id": r["id"], "theory": r["theory"], "why": r["notes"]}
        for r in results if r["verdict"] == "present" and r.get("strength") == "scoped"
    ]
    return {"counts": counts, "by_theory": by_theory,
            "build_queue": build_queue, "deepen_queue": deepen_queue,
            "n_indicators": len(results)}


def run_all(*, save: bool = True) -> dict[str, Any]:
    results = [run_indicator(ind) for ind in INDICATORS]
    scorecard = {
        "instrument": "consciousness_audit",
        "epistemic_status": "indicator_properties_only_not_a_consciousness_claim",
        "undecidability": UNDECIDABILITY_HEADER,
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "reference": "Butlin, Long, et al. (2023), Consciousness in Artificial Intelligence.",
        **_summarize(results),
        "results": results,
    }
    if save:
        OUT_DIR.mkdir(parents=True, exist_ok=True)
        SCORECARD.write_text(json.dumps(scorecard, ensure_ascii=False, indent=2), encoding="utf-8")
        REPORT_MD.write_text(render_report(scorecard), encoding="utf-8")
        scorecard["_paths"] = {"scorecard": str(SCORECARD), "report": str(REPORT_MD)}
    return scorecard


# ---------------------------------------------------------------- human-readable report
_SYMBOL = {"present": "[PRESENT]", "partial": "[partial]", "absent": "[ABSENT]", "flagged": "[FLAGGED]"}


def render_report(sc: dict[str, Any]) -> str:
    L: list[str] = []
    L.append("# ATANOR Consciousness-Indicator Audit")
    L.append("")
    L.append("> **Epistemic status — read first.** " + UNDECIDABILITY_HEADER)
    L.append("")
    L.append(f"_Generated {sc.get('generated_at')} — {sc.get('reference')}_")
    L.append("")
    c = sc["counts"]
    L.append(f"**Totals:** {c['present']} present · {c['partial']} partial · {c['absent']} absent · "
             f"{c['flagged']} flagged (integrity-rejected), across {sc['n_indicators']} indicators.")
    L.append("")
    L.append("## By theory")
    L.append("")
    L.append("| Theory | Present | Partial | Absent | Flagged | Present indicators |")
    L.append("|---|---|---|---|---|---|")
    for th, row in sc["by_theory"].items():
        L.append(f"| {th} | {row['present']}/{row['total']} | {row['partial']} | {row['absent']} | "
                 f"{row['flagged']} | {', '.join(row['present_ids']) or '—'} |")
    L.append("")
    L.append("## Indicators")
    L.append("")
    for r in sc["results"]:
        L.append(f"### {_SYMBOL.get(r['verdict'], r['verdict'])} {r['id']} · {r['theory']}")
        L.append(f"*{r['statement']}*")
        L.append("")
        if r["verdict"] == "flagged":
            L.append(f"- **Integrity:** REJECTED — {r['integrity_reason']} (raw verdict was "
                     f"'{r['raw_verdict']}').")
        else:
            L.append(f"- **Integrity:** {r['integrity_reason']}.")
        L.append(f"- **Notes:** {r['notes']}")
        L.append("- **Evidence:**")
        for e in r["evidence"]:
            L.append(f"    - `{e}`" if e.endswith(".py") or "/" in e.split(" ")[0] else f"    - {e}")
        L.append("")
    L.append("## Build queue (what U2 must build/strengthen next)")
    L.append("")
    if sc["build_queue"]:
        for i, q in enumerate(sc["build_queue"], 1):
            L.append(f"{i}. **{q['id']}** ({q['theory']}, {q['verdict']}) — {q['why']}")
    else:
        L.append("_No absent/partial indicators — every property is at least present._")
    if sc["deepen_queue"]:
        L.append("")
        L.append("### Deepen (present but scoped — secondary targets)")
        for q in sc["deepen_queue"]:
            L.append(f"- **{q['id']}** ({q['theory']}) — {q['why']}")
    L.append("")
    L.append("---")
    L.append("_This instrument reports indicator properties only. It is not, and cannot be, a "
             "measurement of phenomenal consciousness._")
    return "\n".join(L)


if __name__ == "__main__":
    sc = run_all()
    c = sc["counts"]
    print(f"present={c['present']} partial={c['partial']} absent={c['absent']} flagged={c['flagged']}")
    for th, row in sc["by_theory"].items():
        print(f"  {th}: {row['present']}/{row['total']} present  {row['present_ids']}")
    print("build queue:")
    for q in sc["build_queue"]:
        print(f"  - {q['id']} ({q['verdict']})")
    print("scorecard:", SCORECARD)
