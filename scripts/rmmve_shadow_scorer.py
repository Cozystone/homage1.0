#!/usr/bin/env python3
"""RMMVe shadow scorer (READ-ONLY) — ATLASky TruthFlow cascade, ATANOR slice.

A shadow (non-mutating) implementation of the Ranked Multi-Modal Verification
cascade adapted to ATANOR, per Codex's consult on docs/atlasky_adoption_plan.md:

  module order:  hard-gate(reuse) -> LOV(local grounding) -> local role
  consistency -> [POV / WSV / phase-resonance : DEFERRED]
  aggregation:   Ctotal = mean(activated module scores)   (paper Eq.3)
  decision:      would_promote if Ctotal >= THETA, else would_flag/would_abstain
  early term:    if a cheap module clears its theta, skip the rest (paper Alg.1)

HARD FIREWALL (Codex Q4): the score is *integration/promotion eligibility only*,
never answer evidence. The report carries NO answer_text/person/target_answer
fields, and that is asserted before writing. No POV glossary, no WSV web pull,
no baseless resonance (the three BLOCKERs) — those modules are explicitly marked
deferred rather than faked.

Module score form (paper Eq.2):  C_i = w_i * ( a_i*metric1 + (1-a_i)*metric2 ).
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = REPO_ROOT / "scripts"
for p in (str(REPO_ROOT), str(SCRIPTS)):
    if p not in sys.path:
        sys.path.insert(0, p)

import derivation_p0_audit as dp0  # noqa: E402

THETA = 0.5            # global promotion-eligibility threshold (Codex: start simple)
THETA_LOV = 0.8        # LOV "alone-sufficient" signal threshold (informational only)
AGENT_ROLES = ("SUBJ", "TOPIC")   # who/attribution needs an agent-bearing frame
# Codex review: local_role_consistency is a REQUIRED module for attribution — an
# agentive candidate may NOT promote on local grounding alone.
ALLOWED_DECISIONS = ("would_promote", "would_flag", "would_abstain")


def _load_concept_names(store_dir: Path) -> set[str]:
    names: set[str] = set()
    cp = store_dir / "concepts.jsonl"
    if not cp.exists():
        return names
    with cp.open(encoding="utf-8") as fh:
        for line in fh:
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue
            nm = str(row.get("canonical_name", "")).strip()
            if len(nm) >= 2:
                names.add(nm.lower())
    return names


def _load_frames_by_pred_stem(store_dir: Path) -> dict[str, set[str]]:
    """stem -> set of role names seen on frames carrying that predicate."""
    out: dict[str, set[str]] = {}
    cf = store_dir / "case_frames.jsonl"
    if not cf.exists():
        return out
    with cf.open(encoding="utf-8") as fh:
        for line in fh:
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue
            stem = dp0._pred_stem(dp0._lemma(str(row.get("predicate", ""))))
            if not stem:
                continue
            roles = {str(r.get("role", "")) for r in row.get("case_roles", [])}
            out.setdefault(stem, set()).update(roles)
    return out


def _entity_present(question: str, derived: dict[str, Any] | None, names: set[str]) -> int:
    q = question.lower()
    surface = (derived or {}).get("surface", "")
    # any known concept name appears in the question (excluding the agentive noun)
    for nm in names:
        if nm and nm in q and nm != surface.lower():
            return 1
    return 0


def score_question(q: dict[str, Any], store, names, frames) -> dict[str, Any]:
    question = q.get("question", "")
    derived = dp0.detect_agentive_derivation(question)

    module_scores: dict[str, float] = {}
    activated: list[str] = []
    deferred = {
        "POV": "needs a sourced public ontology cache (hand glossary would be a rule table)",
        "WSV": "needs live web; a single pulled sentence would bypass the composer",
        "phase_resonance": "needs wave-engine wiring; must not promote evidence-less candidates",
    }

    if not derived:
        return {
            "id": q.get("id"), "label": q.get("label"), "question": question,
            "derived": None, "module_scores": {}, "activated_modules": [],
            "deferred_modules": list(deferred), "ctotal": 0.0,
            "decision": "would_abstain",
            "decision_basis": "no productive derivation -> not eligible for routing layer",
            "lov_alone_sufficient": False,
        }

    stem = derived["predicate_stem"]
    pred_anchor = 1 if (stem and (derived["predicate_candidate"] in store["lemmas"] or stem in store["stems"])) else 0
    ent = _entity_present(question, derived, names)

    # M1 LOV (local ontology / grounding): w=1, a=0.5
    c_lov = round(1.0 * (0.5 * pred_anchor + 0.5 * ent), 4)
    module_scores["LOV"] = c_lov
    activated.append("LOV")
    lov_alone_sufficient = c_lov >= THETA_LOV   # informational; does NOT skip M2

    # M2 local role consistency — REQUIRED module for attribution (Codex review):
    # always run it; an agentive candidate cannot promote without an
    # agent-bearing frame, even if LOV alone would have cleared early.
    roles = frames.get(stem, set())
    agent_ok = 1 if any(r in roles for r in AGENT_ROLES) else 0
    c_cons = round(float(agent_ok), 4)
    module_scores["local_role_consistency"] = c_cons
    activated.append("local_role_consistency")

    ctotal = round(sum(module_scores[m] for m in activated) / len(activated), 4)
    if ctotal <= 0:
        decision = "would_abstain"
        basis = "Ctotal 0 -> no local grounding"
    elif agent_ok == 0:
        # some grounding exists but the REQUIRED consistency module failed
        decision = "would_flag"
        basis = "required module local_role_consistency failed (no agent-bearing frame) -> flag, not promote"
    elif ctotal >= THETA:
        decision = "would_promote"
        basis = f"Ctotal {ctotal} >= THETA {THETA} (eligibility only, NOT an answer)"
    else:
        decision = "would_flag"
        basis = f"0 < Ctotal {ctotal} < THETA {THETA} -> flag for review"

    return {
        "id": q.get("id"), "label": q.get("label"), "question": question,
        "derived": {"predicate_candidate": derived["predicate_candidate"], "method": derived["method"]},
        "module_scores": module_scores, "activated_modules": activated,
        "deferred_modules": list(deferred), "ctotal": ctotal,
        "decision": decision, "decision_basis": basis,
        "lov_alone_sufficient": lov_alone_sufficient,
    }


_FORBIDDEN = dp0.FORBIDDEN_ANSWER_KEYS


def _iter_keys(obj: Any):
    if isinstance(obj, dict):
        for k, v in obj.items():
            yield k
            yield from _iter_keys(v)
    elif isinstance(obj, (list, tuple)):
        for it in obj:
            yield from _iter_keys(it)


def run(fixture: Path, store_dir: Path) -> dict[str, Any]:
    fx = json.loads(fixture.read_text(encoding="utf-8"))
    store = dp0.load_store_predicates(store_dir)
    names = _load_concept_names(store_dir)
    frames = _load_frames_by_pred_stem(store_dir)

    rows = [score_question(q, store, names, frames) for q in fx.get("questions", [])]
    bad = sorted({r["decision"] for r in rows if r["decision"] not in ALLOWED_DECISIONS})
    if bad:
        raise RuntimeError(f"decision enum violation (not in ALLOWED_DECISIONS): {bad}")
    by_decision: dict[str, int] = {}
    for r in rows:
        by_decision[r["decision"]] = by_decision.get(r["decision"], 0) + 1
    promote = [r for r in rows if r["decision"] == "would_promote"]
    avg_ctotal_promO = round(sum(r["ctotal"] for r in promote) / len(promote), 4) if promote else 0.0

    report = {
        "scorer_id": "rmmve_shadow_v0",
        "report_schema_version": "0.1.0",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "non_destructive": True,
        "firewall": "Ctotal is promotion-eligibility ONLY; report carries no answer fields",
        "score_scope": "implemented_shadow_slice_not_full_rmmve",
        "store_dir": str(store_dir),
        "theta": THETA, "theta_lov": THETA_LOV,
        "deferred_modules": ["POV", "WSV", "phase_resonance"],
        "decision_counts": by_decision,
        "avg_ctotal_of_would_promote": avg_ctotal_promO,
        "per_question": rows,
    }
    leaked = sorted(set(_iter_keys(report)) & _FORBIDDEN)
    if leaked:
        raise RuntimeError(f"firewall violation: answer keys present: {leaked}")
    return report


def main() -> int:
    ap = argparse.ArgumentParser(description="RMMVe shadow scorer (read-only)")
    ap.add_argument("--store", type=Path, default=dp0.DEFAULT_STORE)
    ap.add_argument("--fixture", type=Path, default=dp0.DEFAULT_FIXTURE)
    ap.add_argument("--out-dir", type=Path, default=REPO_ROOT / "reports" / "rmmve-shadow")
    args = ap.parse_args()

    report = run(args.fixture, args.store)
    args.out_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    (args.out_dir / f"{ts}.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"[RMMVe] decisions={report['decision_counts']}")
    print(f"[RMMVe] avg Ctotal(would_promote)={report['avg_ctotal_of_would_promote']} deferred={report['deferred_modules']}")
    print(f"[RMMVe] firewall OK (no answer fields). report: {args.out_dir / (ts + '.json')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
