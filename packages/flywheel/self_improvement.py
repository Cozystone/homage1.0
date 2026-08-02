# -*- coding: utf-8 -*-
"""Self-improvement loop — the AI improves its OWN speech from its OWN conversations,
so we stop hand-writing rules for every case.

Owner (2026-07-10): " — 
 . ." Correct. The rule branches are
TRAINING WHEELS; the destination is a system that closes its own loop. Every piece already
exists — this module wires them into one cycle:

 1. DIAGNOSE — read the live flywheel (data/flywheel/turns.jsonl), mine the failures the
 log already detects (abstain / re-ask / correction) and the weak lanes.
 The AI sees where IT falls short — no human labeling.
 2. LEARN — for the factual turns (whose answers carry grounded fact sentences), run
 speech self-play: the Speaker re-phrases the same verbatim facts many ways,
 the Critic keeps the best, and the winning discourse patterns are DISTILLED
 into the learned preferences the generator reads. Speech improves from the
 AI's own material, not a new rule.
 3. MEASURE — the learned intent router runs in SHADOW on every turn (its prediction is
 logged next to the gold intent). This reports its agreement %. When it
 crosses the promotion bar it can REPLACE the rule lanes — that is the exit
 from the rule-based era, driven by data, not by us.

Read-mostly + honest: it never fabricates, never edits the moral core, and writes only the
discourse-preferences distillate + a self-diagnosis report. The generator picks the change up
on its next read. This is 'the AI learns to speak better on its own', bounded by the same
grounding/honesty contract as everything else.
"""
from __future__ import annotations

import json
import os
import re
import time
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[2]
_TURNS = REPO / "data" / "flywheel" / "turns.jsonl"
_REPORT = REPO / "data" / "flywheel" / "self_improvement_report.json"

_ROUTER_PROMOTE_AT = 0.75   # learned router agreement needed before it can replace rules


_DISTILL_STATE = REPO / "data" / "flywheel" / "distill_state.json"
_DISTILL_CACHE: dict[str, Any] = {"sig": None, "at": 0.0, "result": None}
try:
    _st = json.loads(_DISTILL_STATE.read_text(encoding="utf-8"))
    _DISTILL_CACHE.update({"sig": tuple(_st["sig"]), "at": float(_st.get("at") or 0),
                           "result": _st.get("result")})
except Exception:
    pass
_FACT_KINDS = ("structured_triple_lookup", "ontology_graph_derivation", "verified_isa",
               "grounded_neighborhood_synthesis", "engaged_fact_inference",
               "base_brain_after_low_quality_grounding")


def _rows(limit: int = 8000) -> list[dict[str, Any]]:
    if not _TURNS.exists():
        return []
    out = []
    for line in _TURNS.read_text(encoding="utf-8").splitlines()[-limit:]:
        try:
            out.append(json.loads(line))
        except Exception:
            continue
    return out


def diagnose(rows: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    """What is the AI failing at, measured from its own log — no human labels."""
    rows = rows if rows is not None else _rows()
    try:
        from .logger import mine_failures
        failures = mine_failures()
    except Exception:
        failures = {}
    from collections import Counter
    lanes = Counter(r.get("lane") or "?" for r in rows)
    # weak turns: low confidence or abstain-shaped answers
    weak = [r for r in rows if float(r.get("conf") or 0) < 0.2
            or any(m in str(r.get("a") or "") for m in ("근거가 부족", "확인 가능한 근거", "실시간 근거"))]
    weak_lanes = Counter(r.get("lane") or "?" for r in weak)
    return {
        "turns": len(rows),
        "failure_signals": {k: (len(v) if isinstance(v, list) else v)
                            for k, v in (failures or {}).items()},
        "weak_turns": len(weak),
        "weak_lanes": weak_lanes.most_common(6),
        "lane_distribution": lanes.most_common(10),
    }


def router_readiness(rows: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    """How close is the LEARNED router (shadow) to replacing the rule lanes? Agreement with
    the gold intent, per-intent, plus a promotion verdict. This is the exit from rule-based."""
    rows = rows if rows is not None else _rows()
    have = [r for r in rows if r.get("router") and r.get("gold_intent")]
    agree = sum(1 for r in have if r["router"] == r["gold_intent"])
    n = len(have)
    from collections import Counter
    conf_per = Counter()
    tot_per = Counter()
    for r in have:
        gi = r["gold_intent"]
        tot_per[gi] += 1
        if r["router"] == gi:
            conf_per[gi] += 1
    per_intent = {gi: {"agree": conf_per[gi], "total": tot_per[gi],
                       "rate": round(conf_per[gi] / max(1, tot_per[gi]), 2)}
                  for gi in tot_per}
    rate = agree / max(1, n)
    return {
        "samples": n,
        "agreement": round(rate, 3),
        "promote_at": _ROUTER_PROMOTE_AT,
        "ready_to_replace_rules": rate >= _ROUTER_PROMOTE_AT and n >= 200,
        "verdict": ("learned router can take over — promote it above the rule lanes"
                    if rate >= _ROUTER_PROMOTE_AT and n >= 200
                    else f"router at {round(rate*100)}% — keep rules as training wheels, "
                         "keep feeding the flywheel until it crosses "
                         f"{round(_ROUTER_PROMOTE_AT*100)}%"),
        "weakest_intents": sorted(per_intent.items(), key=lambda kv: kv[1]["rate"])[:5],
    }


_SENT = re.compile(r"[^.!?。\n]+[.!?。]?")


def harvest_discourse_examples(rows: list[dict[str, Any]] | None = None,
                               max_examples: int = 40) -> list[tuple[list[str], str]]:
    """Turn the AI's own FACTUAL answers into self-play material: (grounded fact sentences,
    question). The answer's own sentences are already grounded, so re-phrasing them teaches
    discourse WITHOUT inventing facts."""
    rows = rows if rows is not None else _rows()
    ex: list[tuple[list[str], str]] = []
    seen: set[str] = set()
    for r in rows:
        if str(r.get("kind") or "") not in _FACT_KINDS:
            continue
        q = str(r.get("q") or "").strip()
        a = str(r.get("a") or "").strip()
        if not q or not a or q in seen:
            continue
        # keep the substantive fact clauses, drop hedge/boilerplate scaffolding
        sents = [s.strip() for s in _SENT.findall(a) if len(s.strip()) >= 12]
        sents = [s for s in sents if not any(b in s for b in
                 ("근거가 부족", "웹 검색", "실시간 웹", "종합하면", "더 궁금", "확인 가능한 근거"))]
        if len(sents) >= 2:
            seen.add(q)
            ex.append((sents[:5], q))
        if len(ex) >= max_examples:
            break
    return ex


def improve_speech(*, variants: int = 6, max_examples: int = 40) -> dict[str, Any]:
    """LEARN: harvest examples from the log and run speech self-play to distill better
    discourse into the preferences file the generator reads. Grows the 'flesh' from the AI's
    own conversations — the autonomous alternative to us adding phrasing rules."""
    examples = harvest_discourse_examples(max_examples=max_examples)
    if len(examples) < 3:
        return {"trained": 0, "reason": "not enough grounded factual turns yet"}
    try:
        from packages.base_brain.speech_selfplay import train_discourse
        res = train_discourse(examples, variants=variants, log=lambda *_: None)
    except Exception as exc:  # pragma: no cover - never break
        return {"trained": 0, "error": str(exc)}
    return {"trained": res.get("trained", 0), "patterns": res.get("patterns", 0),
            "top_patterns": res.get("top", []), "distillate": res.get("distillate")}


def distill_router(rows: list[dict[str, Any]] | None = None, *, min_support: int = 6) -> dict[str, Any]:
    """THE EXIT FROM RULES (2026-07-10 breakthrough): the hand-written rule LANES are rich,
    accurate labels — a labeling function (Snorkel/weak-supervision). Train the learned router
    to DISTILL them: label = the lane the rules chose, NOT the coarse `gold_intent` (which is
    80% 'definition' garbage and made the old router look like 37%). The model distills the
    rules + generalizes; once its holdout crosses the bar it REPLACES them. Every rule we ever
    wrote becomes training data for its own successor — so we stop adding rules forever."""
    rows = rows if rows is not None else _rows()
    from collections import Counter
    pairs = [(str(r.get("q") or ""), str(r.get("lane") or "")) for r in rows
             if r.get("q") and r.get("lane")]
    # GOLD LABELS (2026-07-13, anti self-poisoning): log rows record the lane that FIRED —
    # including the hijacks the adversarial battery graded as failures — so pure log
    # distillation teaches the candidate to IMITATE its own mistakes (measured: the daemon's
    # 20-min recycle overwrote the gold-merged model and the felt hijack came back). The
    # human/battery-verified gold set is merged EVERY training run, weighted x10, so the
    # correction is permanent, not a one-shot.
    try:
        _gold_path = _REPORT.parent.parent / "answer_quality" / "router_gold_labels.jsonl"
        if _gold_path.exists():
            _gold = [json.loads(l) for l in _gold_path.read_text(encoding="utf-8").splitlines() if l.strip()]
            pairs += [(str(g["q"]), str(g["lane"])) for g in _gold if g.get("q") and g.get("lane")] * 10
    except Exception:
        pass
    lane_count = Counter(l for _q, l in pairs)
    data = [(q, l) for q, l in pairs if lane_count[l] >= min_support]
    if len(data) < 40:
        return {"trained": 0, "reason": "not enough labeled turns yet"}

    # this retraining at 74.5% of ALL engine CPU — daemons (20-min recycle, CLS hourly) and the
    # goals-progress probe each re-ran a full 30-epoch fit over the SAME grown log. Two gates:
    #   (a) signature — identical labeled data ⇒ return the cached result instantly;
    #   (b) cooldown — even with new turns, at most one real fit per ATANOR_DISTILL_COOLDOWN_S.
    # The organ is unchanged (same data, same fit, same promotion bar) — it just stops redoing
    # work it has already done. goals.py's measure-by-retrain automatically hits this cache too.
    import time as _time
    import hashlib as _hl

    _sig = (len(data),
            _hl.md5(repr(data[:3]).encode()).hexdigest()[:16],
            _hl.md5(repr(data[-3:]).encode()).hexdigest()[:16])
    _cooldown = float(os.environ.get("ATANOR_DISTILL_COOLDOWN_S", "900"))
    _cached = _DISTILL_CACHE.get("result")
    if _cached is not None:
        if _DISTILL_CACHE.get("sig") == _sig:
            return {**_cached, "skipped": "unchanged labeled data (cached result)"}
        if _time.time() - float(_DISTILL_CACHE.get("at") or 0) < _cooldown:
            return {**_cached, "deferred": f"cooldown {_cooldown:.0f}s (new data waits for the next window)"}
    try:
        from packages.learned_router.router import train, MODEL_DIR
        # NEVER clobber the production intent-shape router — the distillation is a SEPARATE
        # candidate model (measures the lane-prediction readiness). Promotion is deliberate.
        res = train(data, epochs=30,
                    out_path=MODEL_DIR / "router_lane_candidate.npz",
                    meta_path=MODEL_DIR / "router_lane_candidate.meta.json")
    except Exception as exc:  # pragma: no cover
        return {"trained": 0, "error": str(exc)}
    result = {"trained": len(data), "lanes": res.get("classes"),
              "train_acc": round(res.get("train_acc", 0), 3),
              "holdout_acc": round(res.get("holdout_acc", 0), 3),
              "label_source": "rule_lanes (distillation, not coarse gold_intent)"}
    _DISTILL_CACHE.update({"sig": _sig, "at": _time.time(), "result": dict(result)})
    try:  # persist so a restart doesn't retrain on data it already fit (boot retrain was 300s+)
        _DISTILL_STATE.parent.mkdir(parents=True, exist_ok=True)
        _DISTILL_STATE.write_text(json.dumps({"sig": list(_sig), "at": _DISTILL_CACHE["at"],
                                              "result": result}), encoding="utf-8")
    except Exception:
        pass
    return result


def run_cycle() -> dict[str, Any]:
    """One self-improvement cycle: diagnose → learn speech → DISTILL the rules into the learned
    router → measure. Safe to run on a schedule; writes only distillates + a report. Run often
    enough, this makes the hand-written rules obsolete — the rules teach their own replacement."""
    rows = _rows()
    # Vision #1: learn discourse STYLE from the real prose the AI has read (grows as it reads
    # more) — the realizer flows less like a dictionary. Style only, never content/facts.
    try:
        from packages.base_brain.discourse_learner import learn as _learn_discourse
        discourse = _learn_discourse()
    except Exception as exc:  # pragma: no cover
        discourse = {"learned": 0, "error": str(exc)}
    distill = distill_router(rows)
    # promotion verdict from the DISTILLATION holdout (the honest forward signal), not the
    # stale logged shadow (old model × garbage gold_intent). Crossing the bar = the learned
    # router can start deciding where rules are silent — the exit from the rule era.
    hold = float(distill.get("holdout_acc") or 0)
    promotion = {
        "holdout": hold,
        "bar": _ROUTER_PROMOTE_AT,
        "labeled_turns": distill.get("trained", 0),
        "crossed_quality_bar": hold >= _ROUTER_PROMOTE_AT,
        "verdict": ("learned router meets the quality bar — ready to decide as a fallback "
                    "where no rule fires; grow labeled turns for full promotion"
                    if hold >= _ROUTER_PROMOTE_AT else
                    f"router at {round(hold*100)}% holdout — keep distilling the rules until "
                    f"it clears {round(_ROUTER_PROMOTE_AT*100)}%"),
    }
    report = {
        "at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "diagnosis": diagnose(rows),
        "speech_learning": improve_speech(),
        "discourse_from_real_prose": discourse,
        "router_distillation": distill,
        "router_promotion": promotion,
        "router_readiness_shadow_historical": router_readiness(rows),
    }
    try:
        _REPORT.parent.mkdir(parents=True, exist_ok=True)
        _REPORT.write_text(json.dumps(report, ensure_ascii=False, indent=1), encoding="utf-8")
    except Exception:
        pass
    return report
