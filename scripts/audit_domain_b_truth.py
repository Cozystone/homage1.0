# -*- coding: utf-8 -*-
"""Audit domain B's ground truth against the behaviour of the entities it labels. READ-ONLY.

    python scripts/audit_domain_b_truth.py

Owner picked route (b): the three wrong predictions in the V7-3 transfer reading looked like B being
wrong rather than the predictor. `Deposition` is labelled `literary work` and carries `creator`,
`made_of`, `located_in`, `religion`; `Traveler` is labelled `video game` and carries `author` and
`part_of`.

WHAT THIS IS NOT ALLOWED TO BE. B is frozen — code, data AND evaluation. Its labels are its answer
key, so correcting them after seeing a REGRESSED verdict is exactly what the seal exists to prevent,
and "the answer key was wrong" is precisely the argument anyone would reach for. So this AUDITS and
changes nothing. What it produces is information about what B's accuracy metric has been measuring.

THE RULE IS FIXED BEFORE THE RESULT IS SEEN, and it is applied to every entity rather than to the
three that were noticed. An entity's label is called CONTESTED when the kind its own predicates
speak for — by the same lift the substrate uses, run against B's own frozen prevalences — outranks
its labelled kind by a margin. Auditing only the three that went wrong would find exactly the three
that went wrong; that is not a measurement, it is a restatement.

THE CONTROL, because a contested rate means nothing on its own. The same rule is run against SHUFFLED
labels. If real labels are contested at about the rate shuffled ones are, the audit is detecting the
predictor's disagreement rather than the key's error, and it says nothing about B.

WHAT A HIGH CONTESTED RATE WOULD MEAN. Not that the substrate is right and the graph wrong — a
predicate profile can disagree with a correct label. It would mean B's `accuracy_on_placed` has an
error floor it cannot see below, so BOTH readings of the transfer gate, baseline and post-change,
were taken against a key with known noise in it. That is a fact about the instrument, and it is the
kind of fact this project keeps finding by asking.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

OUT = Path("data/transfer_gate/domain_b_truth_audit.json")


def main() -> None:
    from packages.kind_prediction.eval import CORPUS, PREVALENCES
    from packages.substrate import behaviour_of, decisive_kind

    n = len(CORPUS)
    kinds = sorted(PREVALENCES) if isinstance(PREVALENCES, dict) else []
    print(f"domain B: {n} entities, {len(kinds)} kinds in the frozen prevalences")

    rows = []
    for row in CORPUS:
        facts = [tuple(f) for f in row["facts"]]
        got, score, _why = decisive_kind(behaviour_of(row["entity"], facts), PREVALENCES)
        rows.append({"entity": row["entity"], "labelled": row["kind"], "predicted": got,
                     "score": float(score) if score is not None else None,
                     "n_facts": len(facts),
                     "preds": sorted({f[1] for f in facts})[:8]})

    placed = [r for r in rows if r["predicted"] is not None]
    disagree = [r for r in placed if r["predicted"] != r["labelled"]]
    print(f"placed {len(placed)}/{n}   disagreements {len(disagree)}")

    # THE CONTROL: shuffle the labels and re-count disagreements under the same rule.
    rng = np.random.default_rng(0)
    labels = [r["labelled"] for r in rows]
    ctrl = []
    for _ in range(200):
        sh = list(labels)
        rng.shuffle(sh)
        d = sum(1 for r, L in zip(rows, sh) if r["predicted"] is not None and r["predicted"] != L)
        ctrl.append(d / max(len(placed), 1))
    ctrl = np.array(ctrl)
    real_rate = len(disagree) / max(len(placed), 1)
    print(f"\ndisagreement rate: real {real_rate:.4f}   shuffled control "
          f"{ctrl.mean():.4f} (p10 {np.percentile(ctrl,10):.4f})")
    print(f"  -> the predictor agrees with the key far more than with noise: "
          f"{'YES' if real_rate < ctrl.mean() - 0.2 else 'NO'}")

    print(f"\n=== every disagreement, with the entity's own predicates ===")
    for r in disagree:
        print(f"  {r['entity'][:34]:36} labelled {r['labelled'][:18]:20} "
              f"predicted {str(r['predicted'])[:18]:20} preds={r['preds'][:5]}")

    # How many entities does the graph label with a kind whose OWN prevalence profile the entity's
    # predicates barely match? Reported as a distribution rather than a verdict.
    scores = [r["score"] for r in placed if r["score"] is not None]
    if scores:
        s = np.array(scores)
        print(f"\ndecisiveness of placed entities: median {np.median(s):.3f}  "
              f"p10 {np.percentile(s,10):.3f}  p90 {np.percentile(s,90):.3f}")

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(
        {"n_entities": n, "placed": len(placed), "disagreements": len(disagree),
         "disagreement_rate": round(real_rate, 5),
         "shuffled_control_mean": round(float(ctrl.mean()), 5),
         "shuffled_control_p10": round(float(np.percentile(ctrl, 10)), 5),
         "detail": disagree,
         "read_only": True,
         "claims": "how often B's key disagrees with the entity's own predicate behaviour",
         "not_claimed": "that the key is wrong where they disagree; a profile can disagree with a "
                        "correct label. Nothing here edits B."},
        indent=2, ensure_ascii=False), encoding="utf-8")
    print("\nwrote", OUT, "(nothing in B was modified)")


if __name__ == "__main__":
    main()
