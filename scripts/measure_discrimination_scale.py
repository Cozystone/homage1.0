# -*- coding: utf-8 -*-
"""C3 discrimination at SCALE — the 4 capability, measured on the world pack, honestly.

The 5-item measure_discrimination.py proves the organ fires; this measures it at scale against
HARD, type-matched distractors auto-generated FROM THE GRAPH (a capital question whose four choices
are all real capitals of other countries), and runs BOTH scorers on the identical battery:

 - overlap : the legacy token-overlap heuristic (define-noun engine) — the below-guess path
 - discriminate: the verify-gated organ — infer (subject, relation), verify each choice, pick the
 single graph-supported one, ABSTAIN if it can't isolate one (un-hallucinatable)

The point is the CONTRAST on the same questions: overlap ≈ chance because every distractor is a
plausible same-type entity; discrimination isolates the one the graph backs and never picks a
plausible-but-wrong distractor. answered_acc for discriminate is high BY CONSTRUCTION (it answers
only when the graph verifies exactly one) — that IS the property we want: it crushes the MCQ where
the graph covers it, and abstains rather than bluff where it doesn't. No web, no LLM, deterministic.

 python scripts/measure_discrimination_scale.py [n_per_relation]
 WORLD_PACK_STORE=world_pack_full python scripts/measure_discrimination_scale.py 40
"""
from __future__ import annotations

import os
import random
import re
import sys
import time
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass
REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

import numpy as np                                                  # noqa: E402
from packages.reasoning_vm.discrimination import discriminate, _norm  # noqa: E402
from packages.graph_scale.triple_store import TripleStore            # noqa: E402

_QID = re.compile(r"^Q\d+$")

# relation → (cue word for the stem, functional?). FUNCTIONAL = single-valued (a country has ONE
# capital) → discrimination's "exactly one supported choice" is exact and un-hallucinatable there.
# MULTI-valued (a person has several occupations; a book, several authors) legitimately abstains
# more, since a distractor may also be a true target → n_sup>1 → abstain (honest, never bluff).
REL_CUE = {
    "capital": ("수도", True), "country": ("국가", True), "inception": ("설립", True),
    "discovered_by": ("발견한 사람", True),
    "author": ("저자", False), "creator": ("만든 사람", False), "occupation": ("직업", False),
}


def _load_shards() -> tuple[list[TripleStore], dict]:
    base = REPO / "data" / "graph_scale"
    name = os.environ.get("WORLD_PACK_STORE", "")
    for cand in ([name] if name else ["world_pack_sharded", "world_pack_full"]):
        d = base / cand
        if not d.exists():
            continue
        shard_dirs = sorted(d.glob("shard_*"))
        if shard_dirs:
            if not (d / "_COMPLETE.json").exists():        # crashed/partial build → skip, try next
                continue
            return ([TripleStore(sd, dict_backend="sharded", write_src=False) for sd in shard_dirs],
                    {"store": cand, "shards": len(shard_dirs)})
        return [TripleStore(d, dict_backend="sharded", write_src=False)], {"store": cand, "shards": 0}
    raise FileNotFoundError("no world_pack_sharded / world_pack_full store found")


def _qlabel(shards: list[TripleStore], qid: str, cache: dict[str, str]) -> str:
    """Resolve a Q-id object to its readable label ((Q64, qlabel, )); non-Q-id → itself."""
    if not _QID.match(qid):
        return qid
    if qid in cache:
        return cache[qid]
    lab = qid
    for sh in shards:
        try:
            hit = next((o for (s, p, o) in sh.facts_about(qid, limit=8) if p == "qlabel"), None)
        except Exception:
            hit = None
        if hit:
            lab = str(hit)
            break
    cache[qid] = lab
    return lab


def _collect(shards: list[TripleStore], relation: str, cap: int, qcache: dict[str, str]
             ) -> list[tuple[str, str]]:
    """(subject, target_label) pairs for `relation`, scanned straight off the memmapped columns."""
    out: list[tuple[str, str]] = []
    seen_subj: set[str] = set()
    for sh in shards:
        pid = sh.terms.lookup(relation)
        if pid is None:
            continue
        cols = sh.open_columns()
        p_col, s_col, o_col = cols["p"], cols["s"], cols["o"]
        if len(p_col) == 0:
            continue
        idx = np.where(p_col == pid)[0]
        for i in idx:
            subj = sh.terms.term(int(s_col[i]))
            if not subj or subj in seen_subj or _QID.match(subj):
                continue
            tgt = _qlabel(shards, sh.terms.term(int(o_col[i])), qcache)
            if not tgt or _QID.match(tgt):
                continue
            seen_subj.add(subj)
            out.append((subj, tgt))
            if len(out) >= cap:
                return out
    return out


# ── overlap scorer (legacy heuristic) — reused to contrast against discrimination ────────────────
def _overlap_pick(stem: str, choices: dict[str, str], shards: list[TripleStore],
                  qcache: dict[str, str]) -> str | None:
    """Score each choice by token overlap with the subject's stored evidence (fresh of the stem)."""
    from scripts.benchmark_openbook import _tokens
    subj = re.split(r"의\s", stem)[0].strip()
    ev: set[str] = set()
    for sh in shards:
        try:
            for (s, p, o) in sh.facts_about(subj, limit=40):
                ev |= _tokens(_qlabel(shards, str(o), qcache))
        except Exception:
            continue
    fresh = ev - _tokens(stem)
    scores = {k: (len(_tokens(v) & fresh) / max(1, len(_tokens(v)))) if v else 0.0
              for k, v in choices.items()}
    best = max(scores, key=scores.get) if scores else None
    top2 = sorted(scores.values(), reverse=True)[:2]
    if best is None or scores[best] <= 0.0 or top2 == [scores[best], scores[best]]:
        return None                                     # tie / no evidence → abstain (same as harness)
    return best


def main() -> int:
    n_per = int(sys.argv[1]) if len(sys.argv) > 1 else 40
    rng = random.Random(20260715)
    shards, meta = _load_shards()
    qcache: dict[str, str] = {}

    def _fa(subject):                                   # resolving facts_about (union across shards)
        rows: list[tuple[str, str, str]] = []
        for sh in shards:
            try:
                rows += [(s, p, _qlabel(shards, str(o), qcache)) for (s, p, o) in sh.facts_about(subject, limit=40)]
            except Exception:
                continue
        return rows

    print(f"=== C3 discrimination at scale — store={meta} ===\n")
    tot = 0
    disc = {"answered": 0, "correct": 0, "wrong": 0}
    over = {"answered": 0, "correct": 0, "wrong": 0}
    func = {"answered": 0, "correct": 0, "wrong": 0}   # functional relations only → the gate cohort
    per_rel: dict[str, dict] = {}

    for relation, (cue, functional) in REL_CUE.items():
        pool = _collect(shards, relation, cap=max(60, n_per * 4), qcache=qcache)
        targets = list({t for _s, t in pool})
        if len(pool) < 4 or len(targets) < 4:
            per_rel[relation] = {"n": 0, "note": "insufficient graph coverage"}
            print(f"  {relation:14} — skipped (coverage {len(pool)} pairs, {len(targets)} targets)")
            continue
        rng.shuffle(pool)
        r_tot = r_disc_ok = r_over_ok = r_disc_ans = r_over_ans = 0
        for subj, gold in pool[:n_per]:
            distractors = [t for t in targets if _norm(t) != _norm(gold)]
            if len(distractors) < 3:
                continue
            picks = rng.sample(distractors, 3) + [gold]
            if len({_norm(p) for p in picks}) < 4:          # skip _norm-colliding choice sets
                continue
            rng.shuffle(picks)
            choices = {k: v for k, v in zip("ABCD", picks)}
            stem = f"{subj}의 {cue}는 무엇입니까?"

            v = discriminate(stem, choices, _fa)
            if v.status == "GROUNDED" and v.choice_key is not None:
                disc["answered"] += 1; r_disc_ans += 1
                ok = _norm(choices.get(v.choice_key, "")) == _norm(gold)   # compare VALUE, not letter
                disc["correct" if ok else "wrong"] += 1
                r_disc_ok += int(ok)
                if functional:
                    func["answered"] += 1; func["correct" if ok else "wrong"] += 1

            op = _overlap_pick(stem, choices, shards, qcache)
            if op is not None:
                over["answered"] += 1; r_over_ans += 1
                ok = _norm(choices.get(op, "")) == _norm(gold)
                over["correct" if ok else "wrong"] += 1
                r_over_ok += int(ok)

            tot += 1; r_tot += 1
        per_rel[relation] = {"n": r_tot, "functional": functional,
                             "disc_answered": r_disc_ans, "disc_correct": r_disc_ok,
                             "over_answered": r_over_ans, "over_correct": r_over_ok}
        da = f"{r_disc_ok}/{r_disc_ans}" if r_disc_ans else "0/0"
        oa = f"{r_over_ok}/{r_over_ans}" if r_over_ans else "0/0"
        tag = "func " if functional else "multi"
        print(f"  {relation:14} [{tag}] n={r_tot:3}  discriminate correct/answered={da:8}  overlap={oa}")

    def _acc(d):
        return round(d["correct"] / d["answered"], 3) if d["answered"] else None
    print(f"\n=== TOTAL over {tot} graph-covered factual MCQ (type-matched hard distractors) ===")
    print(f"  FUNCTIONAL (single-valued: capital/country/inception/discovered_by) — the clean cohort:")
    print(f"    discriminate : answered={func['answered']:3}  correct={func['correct']:3}  "
          f"wrong={func['wrong']}  acc={_acc(func)}  (verify-gated → wrong MUST be 0)")
    print(f"  ALL relations (incl. multi-valued author/creator/occupation):")
    print(f"    discriminate : answered={disc['answered']:3}/{tot}  acc={_acc(disc)}  wrong={disc['wrong']}")
    print(f"    overlap      : answered={over['answered']:3}/{tot}  acc={_acc(over)}  wrong={over['wrong']}")
    print("  note: overlap scores high HERE only because the gold literally sits in the subject's own\n"
          "  facts (factual lookup); on CONCEPTUAL exam MCQ (KMMLU) overlap fell below guess while\n"
          "  discrimination abstains rather than bluff. This battery isolates the un-hallucinatable\n"
          "  factual-lookup property, not a conceptual-MCQ claim (that needs C1 semantic entailment).")
    # honest gate: on FUNCTIONAL factual MCQ, discrimination isolates the graph-verified option with
    # ZERO wrong (never picks a plausible distractor) at meaningful coverage. Multi-valued relations
    # legitimately abstain more and are NOT gated (a distractor may also be a true target).
    ok = func["answered"] >= 8 and func["wrong"] == 0
    print(f"\n  C3-scale gate (functional MCQ: ≥8 answered + 0 wrong): {'PASS' if ok else 'not yet'}")

    import json
    rep = {"at": time.strftime("%Y-%m-%dT%H:%M:%S"), "store": meta, "n": tot,
           "functional_cohort": {**func, "acc_on_answered": _acc(func)},
           "discriminate_all": {**disc, "acc_on_answered": _acc(disc)},
           "overlap_all": {**over, "acc_on_answered": _acc(over)}, "per_relation": per_rel,
           "honest_note": "overlap scores high only because the gold sits in the subject's own facts; "
                          "on conceptual exam MCQ overlap fell below guess. Functional cohort isolates "
                          "the un-hallucinatable factual-lookup property; conceptual MCQ needs C1."}
    outdir = REPO / "reports" / "benchmarks"
    outdir.mkdir(parents=True, exist_ok=True)
    outp = outdir / f"discrimination_scale_{time.strftime('%Y%m%d_%H%M')}.json"
    outp.write_text(json.dumps(rep, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"  wrote {outp}")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
