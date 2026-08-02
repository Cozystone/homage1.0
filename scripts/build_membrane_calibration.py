# -*- coding: utf-8 -*-
"""Build the membrane (M1 conformal gate) calibration artifact from the LIVE answer path.

What it does (real, no fabrication)
-----------------------------------
1. Load a seal knowledge dataset ({subject, relation, accept:[...gold...], ...} per line).
2. For each item, build a natural-language query and run it through the SHIPPED live answer
   path (graph_scale.answer_bridge.answer_from_triples) -- the SAME path the gate wraps.
   The membrane flag is forced OFF here so we measure the RAW answer + its real signals.
3. For every ANSWERED candidate, compute the nonconformity with the SAME functions the gate
   uses at inference (live_wiring.build_signal_vector -> conformal.nonconformity), and label it
   correct/wrong by matching the answer against the gold `accept` aliases.
4. Calibrate per-relation (Mondrian) + a pooled fallback via packages.conformal_gate.conformal,
   and save q_hat to data/conformal_gate/membrane_calibration.json (NOT under data/graph_scale/).

Honesty / scope
---------------
* This is RUNNABLE on a small real slice (default --limit 80) to prove the pipeline end-to-end.
* A production-grade calibration needs the FULL seal holdout run against the full store; that is
  an OPERATOR step (S1 Wikidata ingest is mid-flight). Use --limit 0 for the whole file once the
  store is settled and a single-writer window is open.
* If too few real answered pairs are collected, NO artifact is written (never fabricate a q_hat).

Usage
-----
    python -X utf8 scripts/build_membrane_calibration.py \
        --dataset data/eval/seal_knowledge_dev.jsonl --limit 80 --alpha 0.1 --language en
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

# Measure RAW answers: the gate must be OFF while we calibrate it (else it would pre-filter).
os.environ["ATANOR_MEMBRANE_LIVE"] = "0"
# ...but turn the LEVERS on (coverage routing + rich-signal plumbing) so we calibrate the SAME
# answers + signals the live gate will use. CALIBRATE arms the levers WITHOUT arming the gate
# (see conformal_gate.live_wiring.signals_live): the calibrator must not let the gate pre-filter
# the very set it is being calibrated on.
os.environ["ATANOR_MEMBRANE_CALIBRATE"] = "1"

_DEFAULT_OUT = REPO / "data" / "conformal_gate" / "membrane_calibration.json"

# Minimal English relation -> question templates (surface only; no knowledge encoded).
_Q_TEMPLATES = {
    "capital": "What is the capital of {s}?",
    "country": "What country is {s} in?",
    "located_in": "Where is {s} located?",
    "currency": "What is the currency of {s}?",
    "population": "What is the population of {s}?",
    "language": "What language is spoken in {s}?",
}


def _build_query(subject: str, relation: str, language: str) -> str:
    if language.startswith("ko"):
        return f"{subject}의 {relation}은?"
    tmpl = _Q_TEMPLATES.get(relation, "What is the {r} of {s}?")
    return tmpl.format(s=subject, r=relation.replace("_", " "))


def _norm(text: str) -> str:
    return "".join(ch.lower() for ch in str(text) if ch.isalnum() or ch.isspace()).strip()


def _is_correct(answer: str, accept: list) -> bool:
    a = _norm(answer)
    return any(_norm(g) and _norm(g) in a for g in (accept or []))


def _load_dataset(path: Path, limit: int) -> list[dict]:
    items: list[dict] = []
    with path.open(encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue
            if row.get("subject") and row.get("relation") and row.get("accept"):
                items.append(row)
            if limit and len(items) >= limit:
                break
    return items


# --------------------------------------------------------------------------------------
# DEFINE-LANE bin (--define-dataset). Adds a SEPARATE Mondrian bin (its own q_hat) for the
# base_brain_zero_user_data define lane (derivation_kind 'ontology_graph_derivation') from
# define-lane answers, and MERGES it into the existing artifact -- the relational_edge_lookup /
# grounded_composition bins and the pooled fallback are PRESERVED byte-for-byte (this mode never
# recomputes them). Good definitions land at LOW nonconformity (subject_coverage ~1.0), confident
# wrong-referent defines at HIGH ('black hole' -> 'Black is a color', coverage 0.5). The gate then
# ABSTAINS wrong-referent defines while good definitions PASS -- on the define lane's OWN scale, not
# the relational q_hat (which is a coarser, different distribution).
# --------------------------------------------------------------------------------------
def _load_define_dataset(path: Path) -> list[dict]:
    rows: list[dict] = []
    with path.open(encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue
            if row.get("query") and row.get("expect") in ("accept", "abstain"):
                rows.append(row)
    return rows


def _define_merge(args) -> int:
    """Compute the define-lane bin from define-lane answers and MERGE it into the existing artifact
    (preserving every other bin + the fallback). Never recomputes the relational q_hat."""
    from packages.base_brain.zero_user_answer import answer_with_base_brain
    from packages.conformal_gate import conformal as C
    from packages.conformal_gate.live_wiring import build_signal_vector, qhat_to_json
    from packages.conformal_gate.nonconformity import nonconformity

    out_path = Path(args.out)
    if not out_path.exists():
        print(f"[define-calib] existing artifact not found: {out_path}. This mode ADDS the define "
              f"bin to an existing calibration; run the relational calibration first.", file=sys.stderr)
        return 2
    doc = json.loads(out_path.read_text(encoding="utf-8"))
    prior_rel = (doc.get("bin_q_hat") or {}).get("relational_edge_lookup")
    prior_fallback = doc.get("fallback_q_hat")

    ds_path = Path(args.define_dataset)
    if not ds_path.exists():
        print(f"[define-calib] define dataset not found: {ds_path}", file=sys.stderr)
        return 2
    items = _load_define_dataset(ds_path)
    print(f"[define-calib] {len(items)} define items from {ds_path.name}, alpha={args.alpha}, "
          f"language={args.language}")

    scores: list[float] = []
    labels: list[int] = []          # 1 = good define (accept), 0 = wrong-referent (should abstain)
    kept: list[tuple] = []
    n_skip = 0
    for row in items:
        q, expect = row["query"], row["expect"]
        try:
            res = answer_with_base_brain(q, language=args.language)
        except Exception as exc:
            print(f"  ! {q!r}: answer path error: {exc}")
            n_skip += 1
            continue
        cert = res.get("reasoning_certificate") or {}
        conf = float(res.get("confidence") or 0.0)
        # ONLY the confident define kind populates this bin. A low-confidence / engage / abstain
        # answer is already hedged (not a breach), so it must not skew the define-bin calibration.
        if cert.get("derivation_kind") != "ontology_graph_derivation" or conf < 0.6:
            n_skip += 1
            continue
        s = float(nonconformity(build_signal_vector(res)))
        label = 1 if expect == "accept" else 0
        scores.append(s)
        labels.append(label)
        kept.append((s, expect, q, conf))

    n_wrong = labels.count(0)
    n_correct = labels.count(1)
    print(f"[define-calib] in-bin={len(scores)} (good={n_correct}, wrong={n_wrong}), "
          f"skipped(not-confident-define)={n_skip}")
    if n_wrong < args.min_wrong:
        print(f"[define-calib] INSUFFICIENT wrong exemplars ({n_wrong} < min {args.min_wrong}) to "
              f"calibrate a define q_hat honestly. NOT writing (never fabricate a threshold).")
        return 1

    wrong_scores = [s for s, l in zip(scores, labels) if l == 0]
    q_hat = C.selective_threshold(wrong_scores, args.alpha)
    good_pass = sum(1 for s, l in zip(scores, labels) if l == 1 and C.accept(s, q_hat))
    wrong_gate = sum(1 for s, l in zip(scores, labels) if l == 0 and not C.accept(s, q_hat))
    good_pass_rate = good_pass / max(1, n_correct)
    wrong_gate_rate = wrong_gate / max(1, n_wrong)

    for s, expect, q, conf in sorted(kept):
        verdict = "PASS " if C.accept(s, q_hat) else "GATE "
        tag = "good" if expect == "accept" else "WRONG"
        print(f"  [{tag}] {verdict} nc={s:.3f} conf={conf:.2f} :: {q[:52]!r}")

    # MERGE: add the define bin, PRESERVE every other bin + the fallback byte-for-byte.
    doc.setdefault("bin_q_hat", {})["ontology_graph_derivation"] = qhat_to_json(q_hat)
    doc["define_bin"] = {
        "q_hat": qhat_to_json(q_hat),
        "alpha": args.alpha,
        "n_good": n_correct,
        "n_wrong": n_wrong,
        "good_pass_rate": round(good_pass_rate, 4),
        "wrong_gate_rate": round(wrong_gate_rate, 4),
        "signals": "subject_coverage + graded_confidence + support_path_count",
        "dataset": ds_path.name,
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "note": ("define-lane bin (base_brain_zero_user_data / ontology_graph_derivation). The "
                 "relational_edge_lookup q_hat and grounded_composition bin are PRESERVED unchanged; "
                 "this bin was ADDED, not a rescale. Owner-approved define-lane closure 2026-07-24."),
    }
    # sanity: never let the merge silently move the relational bin or the fallback.
    if (doc.get("bin_q_hat") or {}).get("relational_edge_lookup") != prior_rel:
        print("[define-calib] ABORT: relational_edge_lookup q_hat changed during merge.", file=sys.stderr)
        return 3
    if doc.get("fallback_q_hat") != prior_fallback:
        print("[define-calib] ABORT: fallback_q_hat changed during merge.", file=sys.stderr)
        return 3
    out_path.write_text(json.dumps(doc, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[define-calib] wrote define bin ontology_graph_derivation q_hat={q_hat:.6f} into {out_path.name}")
    print(f"[define-calib] good-define PASS-rate={good_pass_rate:.1%} ({good_pass}/{n_correct}) | "
          f"wrong-define GATE-rate={wrong_gate_rate:.1%} ({wrong_gate}/{n_wrong})")
    print(f"[define-calib] PRESERVED relational_edge_lookup q_hat={prior_rel} fallback={prior_fallback}")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--dataset", default=str(REPO / "data" / "eval" / "seal_knowledge_dev.jsonl"))
    ap.add_argument("--limit", type=int, default=80, help="max items (0 = whole file; operator/full run)")
    ap.add_argument("--alpha", type=float, default=0.1, help="target P(accept|wrong) bound")
    ap.add_argument("--language", default="en")
    ap.add_argument("--out", default=str(_DEFAULT_OUT))
    ap.add_argument("--min-pairs", type=int, default=12, help="min answered pairs required to write an artifact")
    ap.add_argument("--define-dataset", default=None,
                    help="path to a define-lane dataset ({query, expect:accept|abstain} per line). When "
                         "given, compute+MERGE the define bin into the existing artifact (relational bins "
                         "preserved) and exit; do not run the relational calibration.")
    ap.add_argument("--min-wrong", type=int, default=8,
                    help="min wrong-referent define exemplars required to calibrate the define bin")
    args = ap.parse_args()

    # DEFINE-LANE bin merge: separate q_hat for the ungated define lane, added to the existing
    # artifact without touching the relational_edge_lookup / grounded_composition bins.
    if args.define_dataset:
        return _define_merge(args)

    from packages.graph_scale.answer_bridge import answer_from_triples
    from packages.conformal_gate import conformal as C
    from packages.conformal_gate.live_wiring import build_signal_vector, bin_key_for, qhat_to_json
    from packages.conformal_gate.nonconformity import nonconformity

    ds_path = Path(args.dataset)
    if not ds_path.exists():
        print(f"[membrane-calib] dataset not found: {ds_path}", file=sys.stderr)
        return 2
    items = _load_dataset(ds_path, args.limit)
    print(f"[membrane-calib] {len(items)} items from {ds_path.name} (limit={args.limit or 'ALL'}), "
          f"language={args.language}, alpha={args.alpha}")

    scores: list[float] = []
    labels: list[int] = []           # 1 correct, 0 wrong
    bins: list[str] = []
    n_answered = n_miss = 0
    t0 = time.time()
    for row in items:
        subj, rel = row["subject"], row["relation"]
        q = _build_query(subj, rel, args.language)
        try:
            res = answer_from_triples(q, args.language)
        except Exception as exc:                       # a lane fault is a real miss, not a crash
            res = None
            print(f"  ! {subj}/{rel}: answer path error: {exc}")
        # Any abstention kind (honest_abstain, honest_abstain_relational, structural_abstention,
        # conformal_abstention) is a MISS, not a wrong answer — it emitted no factual candidate.
        if (not res or not res.get("answer")
                or "abstain" in str(res.get("answer_kind") or "").lower()):
            n_miss += 1
            continue
        sv = build_signal_vector(res)
        s = nonconformity(sv)
        correct = _is_correct(res.get("answer", ""), row.get("accept"))
        scores.append(float(s))
        labels.append(1 if correct else 0)
        bins.append(bin_key_for(res, q) or rel)
        n_answered += 1

    dt = time.time() - t0
    n_wrong = labels.count(0)
    n_correct = labels.count(1)
    print(f"[membrane-calib] answered={n_answered} miss/abstain={n_miss} "
          f"(correct={n_correct}, wrong={n_wrong}) in {dt:.1f}s")
    if n_answered:
        auc = C.empirical_auc(scores, labels)
        print(f"[membrane-calib] nonconformity AUC (wrong-above-correct) = {auc:.4f}")

    if n_answered < args.min_pairs or n_wrong == 0:
        print(f"[membrane-calib] INSUFFICIENT real pairs to calibrate honestly "
              f"(answered={n_answered} < min {args.min_pairs}, or wrong={n_wrong}==0). "
              f"NOT writing an artifact (never fabricate a q_hat).")
        print("[membrane-calib] OPERATOR STEP: rerun against the full store with a larger/whole "
              "slice (e.g. --dataset data/eval/seal_knowledge_holdout.jsonl --limit 0) in a "
              "single-reader window once S1 ingest is settled.")
        return 1

    # Per-relation Mondrian + pooled fallback (both from the real conformal math).
    bin_q = C.calibrate_mondrian(scores, labels, bins, args.alpha)
    fallback = C.calibrate(scores, labels, args.alpha)
    q_pooled = fallback
    rep = C.evaluate(scores, labels, q_pooled, args.alpha)

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    doc = {
        "version": 1,
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "method": "mondrian",
        "alpha": args.alpha,
        "bins_field": "derivation_kind|relation",
        "bin_q_hat": {str(k): qhat_to_json(v) for k, v in bin_q.items()},
        "fallback_q_hat": qhat_to_json(fallback),
        "calibration_n": n_answered,
        "n_wrong": n_wrong,
        "n_correct": n_correct,
        # PER-ITEM PAIRS, without which no certificate can be computed from this file. The summary
        # statistics below describe the set the threshold was fitted ON, and split conformal's
        # guarantee requires the threshold and the measurement to come from DISJOINT halves. Storing
        # only the summary made the artifact self-consistent and unusable for the one thing M1 needs.
        "pairs": [{"score": float(s), "wrong": bool(l == 0), "bin": str(b)}
                  for s, l, b in zip(scores, labels, bins)],
        "achieved": {
            "pooled_accept_rate": rep.accept_rate,
            "pooled_abstain_rate": rep.abstain_rate,
            "pooled_false_accept_given_wrong": rep.false_accept_given_wrong,
        },
        "source": {"dataset": ds_path.name, "limit": args.limit, "language": args.language},
        "scope_note": ("SMALL-SLICE proof run. A production calibration needs the full seal holdout "
                       "over the full store (operator step; S1 ingest mid-flight)."),
    }
    out_path.write_text(json.dumps(doc, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[membrane-calib] wrote {out_path}")
    print(f"[membrane-calib] pooled q_hat={fallback} bins={list(doc['bin_q_hat'].keys())} "
          f"pooled P(accept|wrong)={rep.false_accept_given_wrong:.3f} "
          f"abstain_rate={rep.abstain_rate:.3f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
