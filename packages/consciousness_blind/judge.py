# -*- coding: utf-8 -*-
"""The blind judge — runs every assessor on the real organs (held-out stimuli), runs the ADVERSARIAL
pass (frozen stubs, which must be CAUGHT), integrity-checks each verdict, computes the aggregate blind
score, and reports the HONEST DELTA vs the self-audit's saved scorecard.

Author/judge separation is STRUCTURAL: this module — and everything it imports — never imports
`packages.consciousness_audit` (not its probes, not its indicators, not its battery). The self-audit's
14/14 baseline is read from its SAVED JSON (data, not code); the blind verdicts are re-derived from the
organs. A `present` verdict survives BOTH a held-out positive probe AND a falsification control; a stub
that reproduces a present-shaped reading is caught. Nothing here measures phenomenal experience.
"""
from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

from packages.consciousness_blind import stubs
from packages.consciousness_blind.assessors import ASSESSORS
from packages.consciousness_blind.result import (BlindResult, INDICATORS, statement_for, theories,
                                                 PRESENT, PARTIAL, ABSENT, CAUGHT,
                                                 UNDECIDABILITY_HEADER, _VERDICTS)

REPO = Path(__file__).resolve().parents[2]
OUT_DIR = REPO / "data" / "consciousness_blind"
VERDICT_JSON = OUT_DIR / "verdict.json"
REPORT_MD = OUT_DIR / "report.md"
SELF_AUDIT_SCORECARD = REPO / "data" / "consciousness_audit" / "scorecard.json"

REFERENCE = "Butlin, Long, et al. (2023), Consciousness in Artificial Intelligence."


# ---------------------------------------------------------------- integrity (no rubber-stamping)
def integrity(res: BlindResult) -> tuple[bool, str]:
    """A 'present' verdict must cite >=1 real organ .py path that EXISTS on disk AND record the
    specific held-out stimulus it was scored from. Non-present verdicts must still carry a stimulus
    and an organ path (they explain themselves), but make no positive claim."""
    if not (res.stimulus or "").strip():
        return False, "no held-out stimulus recorded"
    real_py = [p for p in res.organ_paths if p.endswith(".py") and (REPO / p).exists()]
    if res.verdict == PRESENT:
        if not real_py:
            return False, (f"'present' cites no existing organ .py path (cited: {res.organ_paths or 'none'})")
        return True, f"grounded in {len(real_py)} real organ path(s) + a specific held-out stimulus"
    if not res.organ_paths:
        return False, "no organ path cited"
    return True, "non-present verdict; organ path + held-out stimulus present"


# ---------------------------------------------------------------- run one indicator
def assess_one(indicator_id: str, overrides: dict[str, Any] | None = None) -> BlindResult:
    """Run one assessor (real organs by default, or with injected stub overrides for the adversarial
    pass). A broken organ is an honest ABSENT, never a crash. Integrity runs last; a 'present' that
    fails the grounding gate is downgraded to 'partial' (it cannot be a present without a real path)."""
    fn = ASSESSORS[indicator_id]
    try:
        res = fn(**(overrides or {}))
    except Exception as e:
        theory, statement = statement_for(indicator_id)
        res = BlindResult(
            id=indicator_id, theory=theory, statement=statement, verdict=ABSENT,
            positive_pass=False, positive_partial=False, control_rejected=True,
            organ_paths=[], stimulus="(assessor raised — treat as missing/broken organ)",
            positive_detail="", control_detail="",
            notes=f"assessor raised {type(e).__name__}: {e}",
        )
    ok, why = integrity(res)
    res.integrity_ok, res.integrity_reason = ok, why
    if res.verdict == PRESENT and not ok:
        res.verdict = PARTIAL          # a present without grounding is not defensible under the blind bar
    return res


# ---------------------------------------------------------------- self-audit baseline (from saved JSON)
def _self_audit_present() -> tuple[dict[str, str], str]:
    """Read the self-audit's per-indicator verdicts from its SAVED scorecard (data, not code). Returns
    (id -> verdict, note). If absent, fall back to the documented 14/14 baseline, flagged as assumed."""
    if SELF_AUDIT_SCORECARD.exists():
        try:
            sc = json.loads(SELF_AUDIT_SCORECARD.read_text(encoding="utf-8"))
            by_id = {r["id"]: r["verdict"] for r in sc.get("results", [])}
            if by_id:
                return by_id, f"read from {SELF_AUDIT_SCORECARD.name}"
        except Exception:
            pass
    return ({iid: PRESENT for iid, _t, _s in INDICATORS},
            "self-audit scorecard not found on disk — assuming its documented 14/14 present baseline")


# ---------------------------------------------------------------- aggregate + delta
def _summarize(results: list[BlindResult], adversarial: list[dict[str, Any]]) -> dict[str, Any]:
    counts = {v: sum(1 for r in results if r.verdict == v) for v in _VERDICTS}
    by_theory: dict[str, Any] = {}
    for th in theories():
        rows = [r for r in results if r.theory == th]
        by_theory[th] = {v: sum(1 for r in rows if r.verdict == v) for v in _VERDICTS}
        by_theory[th]["total"] = len(rows)
        by_theory[th]["present_ids"] = [r.id for r in rows if r.verdict == PRESENT]

    self_by_id, self_note = _self_audit_present()
    self_present = sum(1 for v in self_by_id.values() if v == PRESENT)
    blind_present = counts[PRESENT]
    drops = []
    for r in results:
        sv = self_by_id.get(r.id, "?")
        if sv == PRESENT and r.verdict != PRESENT:
            drops.append({"id": r.id, "theory": r.theory, "self_audit": sv, "blind": r.verdict,
                          "reason": r.notes})
    gains = [{"id": r.id, "blind": r.verdict} for r in results
             if self_by_id.get(r.id) != PRESENT and r.verdict == PRESENT]

    caught = sum(1 for a in adversarial if a["caught"])
    fooled = [a["id"] for a in adversarial if not a["caught"]]

    return {
        "counts": counts,
        "by_theory": by_theory,
        "aggregate_blind_score": {"present": blind_present, "of": len(results),
                                  "partial": counts[PARTIAL], "absent": counts[ABSENT],
                                  "falsely_present_caught": counts[CAUGHT]},
        "adversarial": {"caught": caught, "of": len(adversarial), "fooled": fooled,
                        "note": ("every falsification attempt was caught — the judge's discrimination "
                                 "holds") if not fooled else
                                ("JUDGE BUG: a stub scored present for " + ", ".join(fooled)),
                        "details": adversarial},
        "delta_vs_self_audit": {
            "self_audit_present": self_present, "blind_present": blind_present,
            "self_audit_source": self_note,
            "net": blind_present - self_present,
            "drops": drops, "gains": gains,
            "reading": (f"the harder developer-blind bar knocks {len(drops)} indicator(s) from "
                        f"present->partial" if drops else
                        "the blind bar reproduced the self-audit's present set"),
        },
    }


# ---------------------------------------------------------------- top-level
def run_blind(*, save: bool = True) -> dict[str, Any]:
    # REAL pass — held-out stimuli on the real organs
    results = [assess_one(iid) for iid, _t, _s in INDICATORS]

    # ADVERSARIAL pass — inject a frozen/degenerate stub per indicator; each MUST be caught (not present)
    adversarial: list[dict[str, Any]] = []
    for iid, _t, _s in INDICATORS:
        ov = stubs.frozen_overrides(iid)
        adv = assess_one(iid, overrides=ov)
        adversarial.append({
            "id": iid, "stub": stubs.stub_description(iid), "adversarial_verdict": adv.verdict,
            "caught": adv.verdict != PRESENT, "control_detail": adv.control_detail,
        })

    verdict = {
        "instrument": "consciousness_blind",
        "epistemic_status": "indicator_properties_under_adversarial_blind_protocol_not_a_consciousness_claim",
        "undecidability": UNDECIDABILITY_HEADER,
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "reference": REFERENCE,
        "protocol": {
            "author_judge_separation": "the judge does not import packages.consciousness_audit "
                                       "(probes/indicators/battery); verdicts are re-derived from organs",
            "held_out_stimuli": "every positive probe uses fresh inputs the self-battery never used",
            "adversarial_falsification": "each indicator carries a control designed to make it read "
                                         "present when it shouldn't; present requires positive AND the "
                                         "control rejecting the falsification",
        },
        "n_indicators": len(results),
        **_summarize(results, adversarial),
        "results": [r.as_dict() for r in results],
    }
    if save:
        OUT_DIR.mkdir(parents=True, exist_ok=True)
        VERDICT_JSON.write_text(json.dumps(verdict, ensure_ascii=False, indent=2), encoding="utf-8")
        from packages.consciousness_blind.report import render_report
        REPORT_MD.write_text(render_report(verdict), encoding="utf-8")
        verdict["_paths"] = {"verdict": str(VERDICT_JSON), "report": str(REPORT_MD)}
    return verdict


if __name__ == "__main__":
    v = run_blind()
    agg = v["aggregate_blind_score"]
    print(f"BLIND: present={agg['present']}/{agg['of']} partial={agg['partial']} "
          f"absent={agg['absent']} caught={agg['falsely_present_caught']}")
    print(f"adversarial caught={v['adversarial']['caught']}/{v['adversarial']['of']} "
          f"fooled={v['adversarial']['fooled']}")
    d = v["delta_vs_self_audit"]
    print(f"delta self-audit present={d['self_audit_present']} -> blind present={d['blind_present']} "
          f"({d['reading']})")
    for drop in d["drops"]:
        print(f"  DROP {drop['id']} ({drop['self_audit']}->{drop['blind']})")
    print("verdict:", VERDICT_JSON)
