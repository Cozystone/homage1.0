from __future__ import annotations

import copy
import json
import os
from pathlib import Path
import subprocess
import sys

import pytest

from packages.cognitive_core import (
    CanonicalEntityRef,
    CycleEvent,
    CyclePhase,
    CycleReceipt,
    CycleStatus,
    EntityKind,
    FrozenMap,
    adapt_contract,
    apply_state_patch,
    replay_cycle,
)
from packages.cognitive_core.tests.cycle_fixtures import make_receipt


def test_semantic_identity_is_distinct_from_occurrence_identity():
    payload = FrozenMap({"value": 1})
    first = CanonicalEntityRef(
        kind=EntityKind.OBSERVATION,
        cycle_id="cycle_one",
        ordinal=0,
        payload=payload,
    )
    repeated = CanonicalEntityRef(
        kind=EntityKind.OBSERVATION,
        cycle_id="cycle_one",
        ordinal=1,
        payload=payload,
    )
    another_cycle = CanonicalEntityRef(
        kind=EntityKind.OBSERVATION,
        cycle_id="cycle_two",
        ordinal=0,
        payload=payload,
    )
    assert first.semantic_id == repeated.semantic_id == another_cycle.semantic_id
    assert len({first.occurrence_id, repeated.occurrence_id, another_cycle.occurrence_id}) == 3


@pytest.mark.parametrize("kind", tuple(EntityKind))
def test_every_required_entity_kind_has_canonical_semantic_and_occurrence_ids(kind):
    entity = CanonicalEntityRef(
        kind=kind,
        cycle_id="cycle_kinds",
        ordinal=list(EntityKind).index(kind),
        payload=FrozenMap({"kind_probe": kind.value}),
    )
    assert entity.semantic_id.startswith(f"sem_{kind.value}_")
    assert entity.occurrence_id.startswith(f"occ_{kind.value}_")
    assert entity.authoritative is False
    assert entity.observer_only is True


def test_cycle_round_trip_replays_to_identical_state_and_hash():
    receipt = make_receipt()
    adapted = adapt_contract(receipt.to_dict())
    assert isinstance(adapted, CycleReceipt)
    assert adapted.to_dict() == receipt.to_dict()
    replayed = replay_cycle(adapted)
    assert replayed.state.to_dict() == {"status": "completed"}
    assert replayed.state_hash == receipt.terminal_state_hash
    assert replayed.authoritative is False


def test_cycle_receipt_rejects_authority_and_identity_tampering():
    payload = make_receipt().to_dict()
    payload["authoritative"] = True
    with pytest.raises(ValueError, match="authoritative"):
        CycleReceipt.from_dict(payload)

    payload = make_receipt().to_dict()
    payload["events"][0]["state_after_hash"] = "0" * 64
    with pytest.raises(ValueError):
        CycleReceipt.from_dict(payload)

    payload = make_receipt().to_dict()
    payload["entities"][0]["payload"]["content_sha256"] = "c" * 64
    with pytest.raises(ValueError, match="canonical content"):
        CycleReceipt.from_dict(payload)


def test_event_chain_requires_contiguous_parent_linkage():
    receipt = make_receipt()
    payload = copy.deepcopy(receipt.to_dict())
    payload["events"][1]["parent_event_id"] = None
    payload["events"][1].pop("event_id")
    with pytest.raises(ValueError, match="parent linkage"):
        CycleReceipt.from_dict(payload)


def test_receipt_status_must_match_terminal_event_status():
    payload = copy.deepcopy(make_receipt().to_dict())
    payload["status"] = "failed"
    payload.pop("receipt_id")
    with pytest.raises(ValueError, match="replayed terminal state status"):
        CycleReceipt.from_dict(payload)


def test_receipt_rejects_terminal_state_without_exact_status():
    receipt = make_receipt()
    running = apply_state_patch(receipt.initial_state, receipt.events[0].state_patch)
    terminal, _ = CycleEvent.transition(
        cycle_id=receipt.request_cycle.cycle_id,
        sequence=1,
        phase=CyclePhase.TERMINAL,
        parent_event_id=receipt.events[0].event_id,
        entity_occurrence_ids=(receipt.entities[1].occurrence_id,),
        state_before=running,
        state_patch={"set": {"legacy_outcome": "returned"}, "delete": []},
    )
    with pytest.raises(ValueError, match="replayed terminal state status"):
        CycleReceipt(
            request_cycle=receipt.request_cycle,
            status=CycleStatus.FAILED,
            entities=receipt.entities,
            events=(receipt.events[0], terminal),
            initial_state=receipt.initial_state,
            terminal_state_hash=terminal.state_after_hash,
            input_hash=receipt.input_hash,
            output_hash=None,
            selected_route="fixture",
            limitations=("fixture_only",),
        )


def test_state_patch_is_small_deterministic_and_fail_closed():
    state = apply_state_patch(
        {"a": 1, "b": 2},
        {"set": {"c": 3}, "delete": ["a"]},
    )
    assert state.to_dict() == {"b": 2, "c": 3}
    with pytest.raises(ValueError, match="supports only"):
        apply_state_patch({}, {"merge": {"x": 1}})
    with pytest.raises(ValueError, match="same key"):
        apply_state_patch({}, {"set": {"x": 1}, "delete": ["x"]})


def test_replay_hash_is_independent_of_python_hash_seed(tmp_path):
    receipt_path = tmp_path / "receipt.json"
    receipt_path.write_text(
        json.dumps(make_receipt().to_dict(), ensure_ascii=False),
        encoding="utf-8",
    )
    repo = Path(__file__).resolve().parents[3]
    program = (
        "import json,sys;"
        "from packages.cognitive_core import replay_cycle;"
        "p=json.load(open(sys.argv[1],encoding='utf-8'));"
        "print(replay_cycle(p).state_hash)"
    )
    outputs = []
    for seed in ("1", "777"):
        env = dict(os.environ)
        env["PYTHONHASHSEED"] = seed
        completed = subprocess.run(
            [sys.executable, "-c", program, str(receipt_path)],
            cwd=repo,
            env=env,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            check=True,
            timeout=10,
        )
        outputs.append(completed.stdout.strip())
    assert outputs[0] == outputs[1] == make_receipt().terminal_state_hash
