"""Online Hebbian retrieval: the edges used to answer get stronger and rank higher next time."""
from __future__ import annotations

import json
import pathlib
from datetime import datetime, timedelta, timezone

import pytest

from cloud_brain.hebbian_retrieval import apply_answer_reinforcement, rank_by_weight, select_and_reinforce
from cloud_brain.neuroplasticity import plasticity_tick, reinforce_traversed

NOW = datetime(2026, 7, 1, tzinfo=timezone.utc)


def _rels(n: int = 4) -> list[dict]:
    return [{"relation_id": f"r{i}", "relation": "USED_FOR", "weight": 0.5, "updated_at": NOW.isoformat()} for i in range(n)]


def test_used_edges_are_reinforced_and_unused_are_not():
    selected, updated = select_and_reinforce(_rels(4), NOW, max_relations=3)
    used = {x["relation_id"] for x in selected}
    for x in updated:
        if x["relation_id"] in used:
            assert x["weight"] > 0.5 and x["usage_count"] == 1  # traversed → strengthened
        else:
            assert x["weight"] == 0.5                            # untouched


def test_learning_changes_the_ranking():
    _, updated = select_and_reinforce(_rels(4), NOW, max_relations=3)
    top3 = {x["relation_id"] for x in rank_by_weight(updated, NOW)[:3]}
    assert top3 == {"r0", "r1", "r2"}  # the reinforced edges now surface first


def test_repeated_use_makes_one_edge_dominant():
    cur = _rels(4)
    for _ in range(6):  # the same edge keeps being the useful one
        by = {x["relation_id"]: x for x in cur}
        reinforce_traversed(by, ["r3"], NOW)
        cur = list(by.values())
    assert rank_by_weight(cur, NOW)[0]["relation_id"] == "r3"


def test_unused_edge_decays_and_is_pruned():
    old = (NOW - timedelta(days=400)).isoformat()
    rels = [
        {"relation_id": "hot", "relation": "CAUSES", "weight": 0.9, "updated_at": NOW.isoformat()},
        {"relation_id": "cold", "relation": "CAUSES", "weight": 0.9, "updated_at": old},
    ]
    res = plasticity_tick(rels, NOW, half_life_days=30.0, prune_floor=0.1)
    kept = {x["relation_id"] for x in res["kept"]}
    assert "hot" in kept and "cold" not in kept  # never-reinforced edge faded away (LTD)


_REL = (
    pathlib.Path(__file__).resolve().parents[3]
    / "data" / "cloud_brain" / "candidate_runs" / "clean_retrain_v1" / "relations.jsonl"
)


def test_reinforcement_persists_across_answers(tmp_path):
    # two answers over the SAME concept must accumulate on disk (learning survives, isn't lost).
    store = tmp_path / "relations.jsonl"
    rows = [{"relation_id": f"r{i}", "source_concept_id": "c1", "relation": "USED_FOR", "weight": 0.5, "updated_at": NOW.isoformat()} for i in range(4)]
    store.write_text("\n".join(json.dumps(r) for r in rows), encoding="utf-8")
    first = apply_answer_reinforcement(store, "c1", NOW, max_relations=3)
    assert first["reinforced"] == 3
    apply_answer_reinforcement(store, "c1", NOW, max_relations=3)  # answer again
    persisted = [json.loads(l) for l in store.read_text(encoding="utf-8").splitlines() if l.strip()]
    hot = [r for r in persisted if r["weight"] > 0.5]
    assert hot and max(r["weight"] for r in hot) >= 0.6  # two reinforcements accumulated on disk
    assert any(r["weight"] == 0.5 for r in persisted)     # the never-used edge stayed put


def test_apply_reinforcement_missing_store_is_safe():
    assert apply_answer_reinforcement("/nonexistent/relations.jsonl", "c1", NOW)["reinforced"] == 0


def test_graph_answer_learns_and_abstains(tmp_path):
    from cloud_brain.graph_answer import graph_answer_and_learn

    st = _realistic(tmp_path)
    out = graph_answer_and_learn(st, "엔비디아가 뭐야", NOW)
    assert out["answer"] and "엔비디아" in out["answer"] and len(out["reinforced"]) >= 1
    # the used edges are now stronger on disk (learned from being asked)
    persisted = [json.loads(l) for l in (st / "relations.jsonl").read_text(encoding="utf-8").splitlines() if l.strip()]
    assert any(p.get("usage_count", 0) >= 1 and p["weight"] > 0.9 for p in persisted)
    # no matching concept → honest abstain, no fabrication, no mutation
    assert graph_answer_and_learn(st, "존재하지않는개념xyz", NOW)["answer"] is None


def _store(tmp_path, concepts, relations):
    (tmp_path / "concepts.jsonl").write_text("\n".join(json.dumps(c) for c in concepts), encoding="utf-8")
    (tmp_path / "relations.jsonl").write_text("\n".join(json.dumps(r) for r in relations), encoding="utf-8")
    return tmp_path


def _realistic(tmp_path):


    # bare label (no outgoing, one child) — noise the filter drops.
    concepts = [{"concept_id": c, "canonical_name": n} for c, n in [
        ("nv", "엔비디아"), ("intel", "인텔"), ("ss", "삼성"), ("firm", "기업"), ("co", "회사"), ("org", "조직"), ("gpu", "GPU"), ("adj", "미국의")]]
    rels = [
        {"relation_id": "1", "source_concept_id": "nv", "target_concept_id": "firm", "relation": "IS_A", "weight": 0.9, "updated_at": NOW.isoformat()},
        {"relation_id": "2", "source_concept_id": "nv", "target_concept_id": "co", "relation": "IS_A", "weight": 0.9, "updated_at": NOW.isoformat()},
        {"relation_id": "3", "source_concept_id": "intel", "target_concept_id": "firm", "relation": "IS_A", "weight": 0.9, "updated_at": NOW.isoformat()},
        {"relation_id": "4", "source_concept_id": "ss", "target_concept_id": "co", "relation": "IS_A", "weight": 0.9, "updated_at": NOW.isoformat()},
        {"relation_id": "5", "source_concept_id": "firm", "target_concept_id": "org", "relation": "IS_A", "weight": 0.9, "updated_at": NOW.isoformat()},
        {"relation_id": "6", "source_concept_id": "co", "target_concept_id": "org", "relation": "IS_A", "weight": 0.9, "updated_at": NOW.isoformat()},
        {"relation_id": "7", "source_concept_id": "nv", "target_concept_id": "adj", "relation": "IS_A", "weight": 0.5, "updated_at": NOW.isoformat()},  # noise parent
    ]
    return _store(tmp_path, concepts, rels)


def test_trust_gate_answers_a_covered_concept_and_drops_noise_parent(tmp_path):
    from cloud_brain.graph_answer import graph_answer_and_learn

    good = graph_answer_and_learn(_realistic(tmp_path), "엔비디아", NOW)
    assert good["answer"] and "엔비디아는" in good["answer"]
    assert "기업" in good["answer"] and "회사" in good["answer"]  # trusted hypernyms kept
    assert "미국의" not in good["answer"]                          # noise-parent IS_A dropped by the filter


def test_trust_gate_defers_a_noise_hub(tmp_path):
    from cloud_brain.graph_answer import graph_answer_and_learn

    # a stopword/parse-noise hub whose parents are all bare one-off labels → filter strips them all
    # → the concept has no trusted edges → defer (never emit garbage).
    concepts = [{"concept_id": "hub", "canonical_name": "일"}] + [{"concept_id": f"t{i}", "canonical_name": n} for i, n in enumerate(["무신", "디자이너", "장군", "느낌", "마을", "기록"])]
    rels = [{"relation_id": f"r{i}", "source_concept_id": "hub", "target_concept_id": f"t{i}", "relation": "IS_A", "weight": 0.5, "updated_at": NOW.isoformat()} for i in range(6)]
    assert graph_answer_and_learn(_store(tmp_path, concepts, rels), "일", NOW)["answer"] is None


@pytest.mark.skipif(not _REL.exists(), reason="real graph not present")
def test_on_real_relations_learning_reorders_a_concepts_edges():
    by_src: dict[str, list[dict]] = {}
    for line in _REL.open(encoding="utf-8"):
        d = json.loads(line)
        by_src.setdefault(d["source_concept_id"], []).append(d)
    concept, rels = max(by_src.items(), key=lambda kv: len(kv[1]))
    assert len(rels) >= 4
    selected, updated = select_and_reinforce(rels, NOW, max_relations=3)
    used = {r["relation_id"] for r in selected}
    assert all(x["weight"] > 0.5 for x in updated if x["relation_id"] in used)
    top3 = {x["relation_id"] for x in rank_by_weight(updated, NOW)[:3]}
    assert top3 == used  # on real data, the traversed edges now rank on top
