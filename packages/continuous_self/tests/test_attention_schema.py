"""AST: the schema is a simplified, honest model OF the self's attention, and
awareness-talk is generated FROM the schema."""
from __future__ import annotations

from packages.continuous_self.attention_schema import _obj, _topic, awareness_report, build_schema
from packages.continuous_self.self_state import Observation, SelfState, evolve


def _lived(mode_obs: Observation, steps: int = 5) -> SelfState:
    s = SelfState()
    for _ in range(steps):
        evolve(s, mode_obs, rate=0.4)
    return s


def test_schema_tracks_the_real_attention_object():
    s = _lived(Observation(learning_active=True, concepts_delta=4))
    sch = build_schema(s)
    assert sch["object_key"] == "incoming_knowledge"
    assert sch["attending_to"] == "흘러 들어오는 새 지식"


def test_schema_models_its_own_limits():
    s = _lived(Observation(learning_active=True, concepts_delta=4))
    sch = build_schema(s)
    # the unattended list exists, excludes the attended object, is bounded
    assert sch["not_attending_to"], "a schema models attention's LIMITS"
    assert sch["attending_to"] not in sch["not_attending_to"]
    assert len(sch["not_attending_to"]) <= 3


def test_schema_declares_its_epistemic_status():
    sch = build_schema(_lived(Observation()))
    assert "철학적으로 미결" in sch["epistemic_status"], "the schema never over-claims"


def test_awareness_report_is_generated_from_the_schema():
    s = _lived(Observation(learning_active=True, uncertainty_signal=0.9), steps=8)
    sch = build_schema(s)
    rep = awareness_report(sch)
    assert sch["attending_to"] in rep
    assert "주의 밖" in rep  # the report includes what it is NOT aware of


def test_korean_object_particle_agreement():

    assert _obj("지식") == "지식을"
    assert _obj("목표") == "목표를"
    assert _obj("사람") == "사람을"
    assert _topic("불확실함") == "불확실함은"
    assert _topic("목표") == "목표는"


def test_awareness_report_has_no_particle_bug():
    s = SelfState(attention=0.5)
    s.mode = "learning"
    s.narrative.append({"at": 0, "kind": "learn", "text": "x", "driver": "growth"})
    rep = awareness_report(build_schema(s))
    assert "지식를" not in rep and "지식을" in rep


def test_manner_follows_real_attention_intensity():
    focused = SelfState(attention=0.9)
    focused.narrative.append({"at": 0, "kind": "observe", "text": "x", "driver": "growth"})
    diffuse = SelfState(attention=0.2)
    diffuse.narrative.append({"at": 0, "kind": "rest", "text": "y", "driver": "idle"})
    assert build_schema(focused)["manner"] == "집중해서"
    assert build_schema(diffuse)["manner"] == "느슨하게"
