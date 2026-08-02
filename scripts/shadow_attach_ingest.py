#!/usr/bin/env python3
"""Shadow-attach the RMMVe cascade onto the REAL ingestion path (Rollout #1).

GREEN / read-only. Runs real candidate sentences through the ACTUAL gate +
decomposer (verify_sentence -> decompose_sentence, the same calls run_once makes
at continuous_learning.py:350/358) and attaches the RMMVe grounding cascade as a
SHADOW — writing only a side report. It NEVER calls store.accumulate, so the
candidate store is not mutated; promotion is not wired.

Output (reports/shadow-attach/): for each candidate, the current binary gate
decision vs the shadow grounding {ctotal, decision, module_scores}, plus a
gate x shadow crosstab. The value signal = candidates the binary gate VERIFIES
but the cascade would FLAG (verified-but-ungrounded).

Firewall (Contract C1): the grounding block carries only scores/decisions, never
answer-bearing keys; asserted before writing.
"""

from __future__ import annotations

import argparse
import collections
import hashlib
import json
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
import rmmve_shadow_scorer as rss  # noqa: E402
from packages.cgsr.cgsr.ingestion.verification_gate import verify_sentence  # noqa: E402
from packages.cgsr.cgsr.ingestion.decomposer import decompose_sentence  # noqa: E402
from packages.cloud_brain.continuous_learning import source_sentence_from_payload  # noqa: E402
from packages.cloud_brain.verified_payload_feeder import LearningPayload  # noqa: E402

LIVE = REPO_ROOT / "data" / "cloud_brain" / "candidate_runs" / "wikipedia_grounded_live"


def build_payloads(limit: int) -> list[LearningPayload]:
    """Real evidence source text (broad sample), fresh provenance so the real
    decomposer re-runs over it. No synthesis."""
    out: list[LearningPayload] = []
    seen: set[str] = set()
    with (LIVE / "evidence.jsonl").open(encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue
            text = str(row.get("text") or row.get("source_text") or row.get("sentence") or "").strip()
            if not (20 < len(text) < 200) or text in seen:
                continue
            seen.add(text)
            ph = hashlib.sha256(("shadowattach::" + text).encode("utf-8")).hexdigest()
            out.append(LearningPayload(
                payload_id=ph[:24], source_type="approved_public_corpus",
                source_id=f"shadow_{ph[:12]}", text=text, normalized_text=text,
                language="ko", provenance_hash=ph,
                source_url_or_path="shadowattach://reingest/evidence",
                license_hint="public", collected_at="2026-06-30T00:00:00Z",
            ))
            if len(out) >= limit:
                break
    return out


def _score_frame(frame: dict[str, Any], store, names) -> dict[str, Any]:
    stem = dp0._pred_stem(dp0._lemma(str(frame.get("predicate", ""))))
    pred_anchor = 1 if (stem and stem in store["stems"]) else 0
    roles = frame.get("case_roles", [])
    heads = [str(r.get("head", "")).lower() for r in roles]
    entity_present = 1 if any(h and h in names for h in heads) else 0
    c_lov = round(0.5 * pred_anchor + 0.5 * entity_present, 4)
    agent_ok = 1 if any(str(r.get("role", "")) in rss.AGENT_ROLES for r in roles) else 0
    ctotal = round((c_lov + float(agent_ok)) / 2, 4)
    return {"c_lov": c_lov, "role_consistency": agent_ok, "ctotal": ctotal,
            "pred_anchor": pred_anchor, "entity_present": entity_present}


def _decide(best: dict[str, Any] | None) -> tuple[str, float]:
    if not best:
        return ("would_abstain", 0.0)
    ct = best["ctotal"]
    if ct <= 0:
        return ("would_abstain", ct)
    if best["role_consistency"] == 0:
        return ("would_flag", ct)
    if ct >= rss.THETA:
        return ("would_promote", ct)
    return ("would_flag", ct)


def run(limit: int) -> dict[str, Any]:
    store = dp0.load_store_predicates(LIVE)            # read-only snapshot
    names = rss._load_concept_names(LIVE)             # read-only snapshot
    payloads = build_payloads(limit)

    rows: list[dict[str, Any]] = []
    dedupe: set[str] = set()
    for pl in payloads:
        sentence = source_sentence_from_payload(pl)
        decision = verify_sentence(sentence, existing_dedupe_keys=dedupe)
        gate_status = decision.status
        gate_reason = decision.reason
        shadow_decision, ctotal, best, n_frames = "would_abstain", 0.0, None, 0
        if gate_status == "verified":
            result = decompose_sentence(sentence, decision, ingest_run_id="shadow_attach")
            frames = result.case_frames
            n_frames = len(frames)
            scored = [_score_frame(f, store, names) for f in frames]
            best = max(scored, key=lambda s: s["ctotal"]) if scored else None
            shadow_decision, ctotal = _decide(best)
        rows.append({
            "candidate_text": pl.text[:120],
            "gate_status": gate_status,
            "gate_reason": gate_reason,
            "n_case_frames": n_frames,
            "grounding": {
                "decision": shadow_decision,
                "ctotal": ctotal,
                "module_scores": best,
                "score_scope": "implemented_shadow_slice_not_full_rmmve",
            },
        })

    # gate x shadow crosstab
    crosstab: dict[str, collections.Counter] = collections.defaultdict(collections.Counter)
    for r in rows:
        crosstab[r["gate_status"]][r["grounding"]["decision"]] += 1
    # value signal: gate verified but shadow would flag/abstain (ungrounded)
    verified = [r for r in rows if r["gate_status"] == "verified"]
    verified_but_flagged = [r for r in verified if r["grounding"]["decision"] in ("would_flag", "would_abstain")]

    report = {
        "harness_id": "shadow_attach_ingest_v1",
        "report_schema_version": "0.1.0",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "non_destructive": True,
        "store_mutated": False,
        "accumulate_called": False,
        "firewall": "grounding block carries scores/decisions only; no answer fields",
        "store_dir": str(LIVE),
        "candidates": len(rows),
        "gate_x_shadow": {g: dict(c) for g, c in crosstab.items()},
        "verified_count": len(verified),
        "verified_but_ungrounded_count": len(verified_but_flagged),
        "verified_but_ungrounded_pct": round(len(verified_but_flagged) / len(verified), 4) if verified else 0.0,
        "per_candidate": rows,
    }
    # Contract C1 firewall: no answer-bearing keys anywhere.
    leaked = sorted(set(rss._iter_keys(report)) & rss._FORBIDDEN)
    if leaked:
        raise RuntimeError(f"firewall violation: answer keys present: {leaked}")
    return report


def main() -> int:
    ap = argparse.ArgumentParser(description="Shadow-attach RMMVe cascade to ingestion (read-only)")
    ap.add_argument("--limit", type=int, default=150)
    ap.add_argument("--out-dir", type=Path, default=REPO_ROOT / "reports" / "shadow-attach")
    args = ap.parse_args()

    report = run(args.limit)
    args.out_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    (args.out_dir / f"{ts}.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"[SHADOW] candidates={report['candidates']} store_mutated={report['store_mutated']}")
    print(f"[SHADOW] gate x shadow: {report['gate_x_shadow']}")
    print(f"[SHADOW] verified={report['verified_count']} verified_but_ungrounded="
          f"{report['verified_but_ungrounded_count']} ({report['verified_but_ungrounded_pct']})")
    print(f"[SHADOW] firewall OK. report: {args.out_dir / (ts + '.json')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
