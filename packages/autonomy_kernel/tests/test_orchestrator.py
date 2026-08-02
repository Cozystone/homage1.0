# -*- coding: utf-8 -*-
from packages.autonomy_kernel import orchestrator as orch


def test_deficit_road_map_respects_the_gate_boundary():
    """Every deficit routes to a road, and outward/irreversible roads are GATED, inward ones safe."""
    for kind, road in orch._DEFICIT_ROAD.items():
        assert road in orch._SAFE_ROADS or road in orch._GATED_ROADS
    # the outward roads must be gated, never auto-fireable
    assert "web_learn" in orch._GATED_ROADS
    assert "self_code_mod" in orch._GATED_ROADS
    assert "agora_broadcast" in orch._GATED_ROADS
    # inward improvement is safe/auto
    assert "self_improve" in orch._SAFE_ROADS


def test_cycle_acts_on_safe_and_only_proposes_gated(monkeypatch, tmp_path):
    monkeypatch.setattr(orch, "_LEDGER", tmp_path / "dec.jsonl")
    # isolate the goal system (own file + constant metric) so the cycle test is fast + hermetic
    from packages.autonomy_kernel import goals as _goals
    monkeypatch.setattr(_goals, "_GOALS", tmp_path / "goals.json")
    monkeypatch.setattr(_goals, "_read_metric", lambda name: 0.5)
    # a mix: one deficit → safe road, one → gated road
    monkeypatch.setattr(orch, "sense_deficits", lambda: [
        {"kind": "speech_weak", "severity": 0.5, "evidence": "x"},
        {"kind": "knowledge_gap", "severity": 0.6, "evidence": "y"},
    ])
    fired = {"safe": 0}
    monkeypatch.setattr(orch, "_dispatch_safe", lambda road: fired.__setitem__("safe", fired["safe"] + 1) or {"ran": road})
    monkeypatch.setattr(orch, "_update_self_model", lambda *a, **k: None)
    r = orch.cycle()
    acted_roads = {a["road"] for a in r["acted"]}
    proposed_roads = {p["road"] for p in r["proposed_gated"]}
    assert "self_improve" in acted_roads         # inward deficit was acted on automatically
    assert "web_learn" in proposed_roads         # outward deficit was only PROPOSED
    assert fired["safe"] == 1                     # exactly the safe road ran; the gated one did NOT


def test_maybe_run_self_throttles(monkeypatch, tmp_path):
    import time as _t
    monkeypatch.setattr(orch, "_LAST_RUN", tmp_path / "last.txt")
    monkeypatch.setattr(orch, "_MIN_INTERVAL_SEC", 9999)
    ran = {"n": 0}
    monkeypatch.setattr(orch, "cycle", lambda *a, **k: ran.__setitem__("n", ran["n"] + 1) or {})
    assert orch.maybe_run() is not None      # first call runs (no prior timestamp)
    assert ran["n"] == 1
    assert orch.maybe_run() is None          # within interval → throttled, does NOT run again
    assert ran["n"] == 1


def test_self_correction_fixes_clear_miss_only():
    from packages.autonomy_kernel.answer_metacognition import suggest_correction
    # broken challenge answer (deflection) → gets a fitting substitute
    fix = suggest_correction("너 지금 나 무시하는거야?",
                             "‘무시하’은(는) 지금 실시간 웹으로 교차 확인해 이어서 답합니다.",
                             {"derivation_kind": "engaged_fact_inference"})
    assert fix and "미안" in fix
    # a grounded factual answer is NEVER overridden
    assert suggest_correction("고래는 물고기야?", "아니요, 고래는 물고기가 아니라 동물의 한 종류예요.",
                              {"derivation_kind": "verified_isa", "confidence": 0.7}) is None
    # a real definition query answered with a definition is fine
    assert suggest_correction("사랑이 뭐야?", "사랑은 감정적 상태이다.",
                              {"derivation_kind": "ontology_graph_derivation"}) is None
