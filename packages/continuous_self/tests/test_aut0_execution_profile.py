from __future__ import annotations

import sys
from types import SimpleNamespace

from packages.continuous_self import homeostasis
from packages.continuous_self.loop import (
    AUT0_LOCAL_CONTINUOUS_SELF_PROFILE,
    ContinuousSelf,
)
from packages.continuous_self.self_state import Observation


def test_aut0_local_profile_advances_core_without_forbidden_effects(
    monkeypatch,
    tmp_path,
) -> None:
    forbidden_calls: list[str] = []

    def forbidden(name: str):
        def _call(*_args, **_kwargs):
            forbidden_calls.append(name)
            raise AssertionError(f"{name} must be absent from the AUT-0 profile")

        return _call

    monkeypatch.setitem(
        sys.modules,
        "packages.autonomy_kernel.orchestrator",
        SimpleNamespace(trigger_background=forbidden("background_improvement")),
    )
    monkeypatch.setitem(
        sys.modules,
        "packages.autonomy_kernel.intrinsic_drive",
        SimpleNamespace(act=forbidden("intrinsic_drive")),
    )
    monkeypatch.setitem(
        sys.modules,
        "packages.autonomy_kernel.server_roamer",
        SimpleNamespace(roam_tick=forbidden("server_roaming")),
    )
    monkeypatch.setitem(
        sys.modules,
        "packages.autonomy_kernel.moltbook_conversation",
        SimpleNamespace(converse_tick=forbidden("commons_conversation")),
    )
    monkeypatch.setitem(
        sys.modules,
        "packages.graph_scale.lexical_field",
        SimpleNamespace(maybe_retrain=forbidden("lexical_retraining")),
    )
    monkeypatch.setitem(
        sys.modules,
        "packages.continuous_self.monologue",
        SimpleNamespace(monologue_tick=forbidden("inner_monologue")),
    )
    monkeypatch.setitem(
        sys.modules,
        "packages.continuous_self.self_modification",
        SimpleNamespace(
            apply_approved=forbidden("parameter_apply"),
            list_proposals=forbidden("proposal_read"),
            propose_self_tuning=forbidden("parameter_proposal"),
        ),
    )
    monkeypatch.setitem(
        sys.modules,
        "packages.continuous_self.code_self_modification",
        SimpleNamespace(
            propose_code_improvement=forbidden("code_proposal"),
            stage_approved=forbidden("code_stage"),
        ),
    )
    monkeypatch.setattr(
        homeostasis,
        "consume_felt_events",
        lambda _state, **_kwargs: None,
    )

    local_probes: list[str] = []

    def local_probe(kind: str) -> dict[str, bool]:
        local_probes.append(kind)
        return {"observed": True}

    state_path = tmp_path / "self.json"
    self_model = ContinuousSelf(
        state_path,
        lambda: Observation(
            concepts_delta=2,
            relations_delta=1,
            uncertainty_signal=0.8,
            resource_pressure=0.7,
            deficit_count=3,
        ),
        observe_fn=local_probe,
        identity_fn=lambda _question, _topic: "local grounded identity",
        research_fn=forbidden("web_research"),
        initiative_every=1,
    )
    self_model.state.ticks = 3_599
    self_model.state.self_question = "What remains unresolved?"
    self_model.state.self_question_open = True
    pressure_before = self_model.state.introspective_pressure
    hormones_before = dict(self_model.state.hormones)

    result = self_model.step(profile=AUT0_LOCAL_CONTINUOUS_SELF_PROFILE)

    assert result is self_model.state
    assert result.ticks == 3_600
    assert result.introspective_pressure > pressure_before
    assert result.hormones != hormones_before
    assert result.goals
    assert local_probes
    assert state_path.is_file()
    assert forbidden_calls == []
