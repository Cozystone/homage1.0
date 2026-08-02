from __future__ import annotations

from packages.cognitive_core import (
    CanonicalEntityRef,
    CycleEvent,
    CyclePhase,
    CycleReceipt,
    CycleStatus,
    EntityKind,
    FrozenMap,
    RequestCycle,
)


def make_receipt(
    *,
    cycle_id: str = "cycle_test_root",
    request_id: str = "request_test_root",
    parent_cycle_id: str | None = None,
) -> CycleReceipt:
    observation = CanonicalEntityRef(
        kind=EntityKind.OBSERVATION,
        cycle_id=cycle_id,
        ordinal=0,
        payload=FrozenMap({"content_sha256": "a" * 64, "raw_content_stored": False}),
    )
    proposition = CanonicalEntityRef(
        kind=EntityKind.PROPOSITION,
        cycle_id=cycle_id,
        ordinal=1,
        payload=FrozenMap({"content_sha256": "b" * 64, "raw_content_stored": False}),
    )
    request_cycle = RequestCycle(
        request_id=request_id,
        cycle_id=cycle_id,
        session_id="session_test",
        parent_cycle_id=parent_cycle_id,
        seed=7,
        input_observation_id=observation.occurrence_id,
    )
    initial = FrozenMap({"status": "created"})
    ingress, running = CycleEvent.transition(
        cycle_id=cycle_id,
        sequence=0,
        phase=CyclePhase.INGRESS,
        parent_event_id=None,
        entity_occurrence_ids=(observation.occurrence_id,),
        state_before=initial,
        state_patch={"set": {"status": "running"}, "delete": []},
    )
    terminal, completed = CycleEvent.transition(
        cycle_id=cycle_id,
        sequence=1,
        phase=CyclePhase.TERMINAL,
        parent_event_id=ingress.event_id,
        entity_occurrence_ids=(proposition.occurrence_id,),
        state_before=running,
        state_patch={"set": {"status": "completed"}, "delete": []},
    )
    return CycleReceipt(
        request_cycle=request_cycle,
        status=CycleStatus.COMPLETED,
        entities=(observation, proposition),
        events=(ingress, terminal),
        initial_state=initial,
        terminal_state_hash=terminal.state_after_hash,
        input_hash="a" * 64,
        output_hash="b" * 64,
        selected_route="fixture",
        limitations=("fixture_only",),
    )
