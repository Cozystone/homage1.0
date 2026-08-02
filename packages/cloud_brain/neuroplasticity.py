#!/usr/bin/env python3
"""Neuroplasticity for the knowledge graph — bidirectional, usage-driven, self-tuning.

The graph already had ONE plasticity mechanism: ingestion-frequency strengthening
(re-observing a fact raises its edge weight; see semantic_dedupe). That is only half of
biological plasticity. This module adds the missing halves and removes a rule-based crutch:

A. DECAY / pruning (LTD): edges not reinforced weaken over time; very weak ones are
 pruned. Strengthening is no longer monotonic — unused associations fade, which also
 bounds memory (ties into the durable "bounded" invariant).
B. USAGE-time reinforcement: edges TRAVERSED during answering/reasoning are strengthened
 ("fire together while THINKING -> wire together"), not only when a sentence is re-read.
 So the graph learns from use, not just from repetition.
C. Distribution-derived predicate informativeness (replaces the hand-listed light-verb
 stoplist in the decomposer — that was a rule table). A predicate used by a huge,
 diverse set of subjects carries little relational information (copula / / );
 a selective predicate ( / ) is informative. Computed IDF-style from the
 graph's own statistics — no hardcoded word list. This is the LAD/grammar vs learned-
 knowledge boundary made data-driven.

Pure functions (no I/O) so they are testable and can run inside the bounded maintenance
tick or be wired into the activation path.
"""

from __future__ import annotations

import math
from datetime import datetime, timezone
from typing import Any, Iterable

# ---- C. predicate informativeness (graph-derived; replaces the rule list) ----

def predicate_informativeness(relations: Iterable[dict[str, Any]]) -> dict[str, float]:
    """IDF-style score per predicate from the graph's own distribution.

    df(p) = number of DISTINCT subject concepts that use predicate p. A predicate used
    by almost every subject (copula/light verb) gets df≈N -> score≈0; a selective
    predicate gets a high score. Returns predicate -> score in [0, 1]. No word list.
    """
    subjects_by_pred: dict[str, set] = {}
    all_subjects: set = set()
    for r in relations:
        p = str(r.get("relation") or "")
        s = r.get("source_concept_id")
        if not p or s is None:
            continue
        # IS_A is taxonomy (scored 1.0 in plasticity_tick); {ROLE}_OF are parse-structure
        # labels (OBJ_OF/SUBJ_OF), not knowledge — neither is a real predicate, so exclude
        # both from the IDF base (else the ubiquitous _OF drags every real predicate's df up).
        if p == "IS_A" or p.endswith("_OF"):
            continue
        subjects_by_pred.setdefault(p, set()).add(s)
        all_subjects.add(s)
    n = max(len(all_subjects), 1)
    log_n = math.log(n + 1.0)
    scores: dict[str, float] = {}
    for p, subs in subjects_by_pred.items():
        df = len(subs)
        idf = math.log((n + 1.0) / (df + 1.0)) / log_n if log_n > 0 else 0.0
        scores[p] = round(max(0.0, min(1.0, idf)), 4)
    return scores


def is_low_information(predicate: str, scores: dict[str, float], threshold: float = 0.2) -> bool:
    """Data-derived replacement for the light-verb stoplist."""
    return scores.get(str(predicate), 1.0) < threshold


# ---- A. decay / pruning (LTD) ----

def _age_days(updated_at: str | None, now: datetime) -> float:
    if not updated_at:
        return 0.0
    try:
        t = datetime.fromisoformat(str(updated_at).replace("Z", "+00:00"))
        if t.tzinfo is None:
            t = t.replace(tzinfo=timezone.utc)
        return max(0.0, (now - t).total_seconds() / 86400.0)
    except Exception:
        return 0.0


def decayed_weight(weight: float, updated_at: str | None, now: datetime,
                   half_life_days: float = 30.0) -> float:
    """Exponential time-decay since last reinforcement (LTD). Half-life in days."""
    w = float(weight or 0.0)
    age = _age_days(updated_at, now)
    if age <= 0 or half_life_days <= 0:
        return w
    return round(w * (0.5 ** (age / half_life_days)), 4)


def apply_decay_and_prune(rows: list[dict[str, Any]], now: datetime, *,
                          half_life_days: float = 30.0, prune_floor: float = 0.05,
                          weight_key: str = "weight") -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Decay every row's weight by age; drop rows that fall below prune_floor.

    Reinforced rows (recent updated_at) barely move; long-unused ones fade and are pruned,
    which bounds memory. Returns (kept_rows_with_decayed_weight, pruned_rows).
    """
    kept, pruned = [], []
    for row in rows:
        dw = decayed_weight(row.get(weight_key, 0.5), row.get("updated_at"), now, half_life_days)
        if dw < prune_floor:
            pruned.append(row)
            continue
        new = dict(row)
        new[weight_key] = dw
        kept.append(new)
    return kept, pruned


# ---- B. usage-time reinforcement (Hebbian-on-thinking) ----

def reinforce(row: dict[str, Any], now: datetime, *, amount: float = 0.05,
              weight_key: str = "weight") -> dict[str, Any]:
    """Strengthen an edge that was TRAVERSED during answering. Bumps weight (capped) and
    refreshes updated_at so decay restarts — usage protects an edge from fading."""
    new = dict(row)
    new[weight_key] = round(min(1.0, float(row.get(weight_key) or 0.5) + amount), 4)
    new["updated_at"] = now.isoformat()
    new["usage_count"] = int(row.get("usage_count") or 0) + 1
    return new


def reinforce_traversed(relations: dict[str, dict[str, Any]], traversed_ids: Iterable[str],
                        now: datetime, *, amount: float = 0.05) -> int:
    """Apply usage reinforcement to the relation ids traversed in a reasoning step."""
    hit = 0
    for rid in traversed_ids:
        if rid in relations:
            relations[rid] = reinforce(relations[rid], now, amount=amount)
            hit += 1
    return hit


# ---- the bounded maintenance tick (ties A + B + C together) ----

def plasticity_tick(relations: list[dict[str, Any]], now: datetime, *,
                    half_life_days: float = 30.0, prune_floor: float = 0.05,
                    info_blend: float = 0.5) -> dict[str, Any]:
    """One maintenance pass over predicate edges — the graph's 'sleep consolidation'.

    1. informativeness (C): each edge's importance is blended toward its predicate's
       data-derived informativeness (low-info copula/light verbs sink, selective
       predicates rise) — no rule list.
    2. decay (A): weights fade by age since last reinforcement.
    3. prune (A): edges below the floor are dropped -> bounded memory.
    Usage reinforcement (B) happens separately, at answer time, and protects an edge by
    raising its weight + refreshing recency so this tick does not prune it.

    Returns the kept edges (new weights) + pruned + stats. Pure; caller persists.
    """
    scores = predicate_informativeness(relations)
    blended: list[dict[str, Any]] = []
    for r in relations:
        pred = str(r.get("relation") or "")
        if pred == "IS_A":
            info = 1.0                          # taxonomy stays strong
        elif pred.endswith("_OF"):
            info = 0.0                          # parse-structure role labels -> decay + prune
        else:
            info = scores.get(pred, 0.5)
        w0 = float(r.get("weight") if r.get("weight") is not None else info)
        new = dict(r)
        new["weight"] = round((1 - info_blend) * w0 + info_blend * info, 4)
        new["info_weight"] = info
        blended.append(new)
    kept, pruned = apply_decay_and_prune(blended, now, half_life_days=half_life_days,
                                         prune_floor=prune_floor)
    return {"kept": kept, "pruned": pruned,
            "stats": {"in": len(relations), "kept": len(kept), "pruned": len(pruned),
                      "distinct_predicates": len(scores)}}



#
# The stability-plasticity dilemma has no perfect solution; what removes its TOXICITY
# is making forgetting a DEMOTION instead of a deletion. Pruned edges go to a cold
# archive (disk, append-only) with a forgetting log, and can be restored if pruning
# turns out to have been wrong — bounded hot memory, zero irreversible loss.

def archive_pruned(store_root: Any, pruned: list[dict[str, Any]], now: datetime,
                   *, reason: str = "plasticity_prune") -> int:
    """Append pruned rows to the cold archive + forgetting log. Returns rows archived."""
    import json as _json
    from pathlib import Path as _Path

    root = _Path(store_root)
    root.mkdir(parents=True, exist_ok=True)
    archive = root / "pruned_archive.jsonl"
    log = root / "forgetting_log.jsonl"
    stamp = now.replace(microsecond=0).isoformat().replace("+00:00", "Z")
    with archive.open("a", encoding="utf-8") as fh:
        for row in pruned:
            fh.write(_json.dumps({**row, "archived_at": stamp, "archive_reason": reason},
                                 ensure_ascii=False) + "\n")
    with log.open("a", encoding="utf-8") as fh:
        fh.write(_json.dumps({"at": stamp, "reason": reason, "count": len(pruned),
                              "sample_keys": [str(r.get("dedupe_key") or "") for r in pruned[:5]]},
                             ensure_ascii=False) + "\n")
    return len(pruned)


def restore_archived(store_root: Any, dedupe_keys: set[str]) -> list[dict[str, Any]]:
    """Recover archived rows by dedupe_key (weight reset above the prune floor so the
    next tick does not instantly re-prune them). The archive itself is never mutated —
    restore is an append-elsewhere read, so history stays intact."""
    import json as _json
    from pathlib import Path as _Path

    archive = _Path(store_root) / "pruned_archive.jsonl"
    if not archive.exists():
        return []
    restored: dict[str, dict[str, Any]] = {}
    for line in archive.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            row = _json.loads(line)
        except _json.JSONDecodeError:
            continue
        key = str(row.get("dedupe_key") or "")
        if key in dedupe_keys:
            row = {k: v for k, v in row.items() if k not in {"archived_at", "archive_reason"}}
            row["weight"] = max(float(row.get("weight") or 0.0), 0.2)
            restored[key] = row  # last archived version wins
    return list(restored.values())


# ---- self-test ----

def _self_test() -> dict[str, Any]:
    now = datetime(2026, 7, 1, tzinfo=timezone.utc)
    # C: informativeness — a copula-like predicate used by many subjects scores low,
    # a selective one scores high, with NO hardcoded list.
    rels = []
    for i in range(50):
        rels.append({"relation": "be", "source_concept_id": f"s{i}", "target_concept_id": "t"})
    rels.append({"relation": "발견하다", "source_concept_id": "s0", "target_concept_id": "핵분열"})
    rels.append({"relation": "발견하다", "source_concept_id": "s1", "target_concept_id": "핵분열"})
    scores = predicate_informativeness(rels)
    info_ok = scores["발견하다"] > scores["be"] and is_low_information("be", scores) and not is_low_information("발견하다", scores)
    # A: decay — an old edge fades below floor and is pruned; a fresh one survives.
    rows = [
        {"id": "old", "weight": 0.6, "updated_at": "2026-01-01T00:00:00Z"},
        {"id": "fresh", "weight": 0.6, "updated_at": "2026-06-30T00:00:00Z"},
    ]
    kept, pruned = apply_decay_and_prune(rows, now, half_life_days=30.0, prune_floor=0.05)
    decay_ok = any(r["id"] == "fresh" for r in kept) and any(r["id"] == "old" for r in pruned)
    # B: usage reinforcement — traversing an edge raises weight and refreshes recency.
    rel_map = {"r1": {"weight": 0.4, "updated_at": "2026-01-01T00:00:00Z"}}
    reinforce_traversed(rel_map, ["r1"], now, amount=0.05)
    use_ok = rel_map["r1"]["weight"] == 0.45 and rel_map["r1"]["usage_count"] == 1
    return {"informativeness": info_ok, "decay_prune": decay_ok, "usage_reinforce": use_ok,
            "all_pass": info_ok and decay_ok and use_ok,
            "sample_scores": {"be": scores["be"], "발견하다": scores["발견하다"]}}


if __name__ == "__main__":
    import json
    print(json.dumps(_self_test(), ensure_ascii=False, indent=2))
