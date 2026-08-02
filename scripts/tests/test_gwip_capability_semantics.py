from __future__ import annotations

import copy
from pathlib import Path

import pytest

from scripts import gwip_capability_semantics as semantics


REGISTER = "/features/registers/0"
MODULUS = "/features/context/modulus"


def _observation(value: int, modulus: int = 7) -> dict:
    return {
        "caller_verified": True,
        "features": {
            "context": {"modulus": modulus},
            "registers": [value],
            "truthy_but_not_integer": True,
        },
        "outside_integer": 99,
        "schema_version": "hand.nonfinal.v1",
        "state_ref": f"hand-state-{modulus}-{value}",
        "terminal": False,
    }


def _payload(label: str) -> dict:
    return {"opaque": {"cue": label}, "weight": 1}


def _step(
    before: int,
    after: int,
    *,
    action_id: str = "hand-action",
    label: str = "alpha",
    episode_ref: str = "episode:0",
    step_index: int = 0,
    modulus: int = 7,
    success: bool = False,
) -> dict:
    return {
        "before_observation": _observation(before, modulus),
        "after_observation": _observation(after, modulus),
        "episode_ref": episode_ref,
        "selected_action": action_id,
        "step_index": step_index,
        "success": success,
        "valid_actions": [
            {"action_id": action_id, "payload": _payload(label)},
            {"action_id": "other-action", "payload": _payload("other")},
        ],
    }


def _honest_ledger() -> dict:
    # x' = 2*x+1 mod 7.  The fourth edge is in a separately reset episode,
    # so it is a genuinely later, distinct prequential confirmation edge.
    return semantics.reconstruct_edge_ledger(
        [
            _step(0, 1, step_index=0),
            _step(1, 3, step_index=1),
            _step(3, 0, step_index=2),
            _step(2, 5, episode_ref="episode:1", step_index=0),
        ]
    )


def _rule(
    signature: str,
    refs: list[str],
    *,
    multiplier: int = 2,
    offset: int = 1,
) -> dict:
    return {
        "action_signature": signature,
        "context_path": MODULUS,
        "expression": {
            "args": [
                {
                    "args": [
                        {
                            "args": [
                                {"op": "var", "path": REGISTER},
                                {"op": "const", "value": multiplier},
                            ],
                            "op": "mul",
                        },
                        {"op": "const", "value": offset},
                    ],
                    "op": "add",
                },
                {"op": "var", "path": MODULUS},
            ],
            "op": "mod",
        },
        "hypothesis": True,
        "input_path": REGISTER,
        "output_path": REGISTER,
        "schema_version": semantics.RULE_IR_SCHEMA,
        "support_edge_refs": sorted(refs),
    }


def _honest_rule_and_record(ledger: dict) -> tuple[dict, dict]:
    rows = ledger["rows"]
    rule = _rule(
        rows[0]["action_signature"],
        [row["edge_ref"] for row in rows[:3]],
    )
    key_material = copy.deepcopy(rule)
    key_material.pop("support_edge_refs")
    record = {
        "confirmation_edge_refs": [rows[3]["edge_ref"]],
        "emitted_ordinal": 3,
        "rule": rule,
        "rule_key": semantics.digest(key_material),
        "status": "usable",
    }
    return rule, record


def _memory_for(ledger: dict, records: list[dict]) -> dict:
    expected = semantics._expected_memory_rows(ledger["rows"])
    return {
        "action_sets": expected["action_sets"],
        "attempts": expected["attempts"],
        "concepts_by_state": expected["concepts_by_state"],
        "feature_edges": expected["feature_edges"],
        "rule_records": sorted(records, key=lambda item: item["rule_key"]),
        "schema_version": semantics.MEMORY_SCHEMA,
        "semantic_attempts": expected["semantic_attempts"],
        "target_state_digest": expected["target_state_digest"],
        "transitions": expected["transitions"],
    }


def _rule_events(
    rule: dict,
    *,
    carry_after_confirmation: bool = True,
    total_action_count: int = 4,
) -> dict:
    events = [
        {
            "action_count": 3,
            "phase": "learning",
            "rule_digests": [semantics.digest(rule)],
            "rules": [rule],
            "step_index": 2,
            "trace_index": 0,
        }
    ]
    if carry_after_confirmation:
        events.append(
            {
                "action_count": 4,
                "phase": "learning",
                "rule_digests": [semantics.digest(rule)],
                "rules": [rule],
                "step_index": 0,
                "trace_index": 1,
            }
        )
    body = {
        "events": events,
        "schema_version": semantics.RULE_EVENT_SCHEMA,
        "total_edge_count": total_action_count,
    }
    return {**body, "event_digest": semantics.digest(body)}


def _support_binding(pair_index: int, ledger: dict, memory: dict) -> dict:
    body = {
        "ledger": ledger,
        "ledger_digest": ledger["ledger_digest"],
        "memory": memory,
        "memory_digest": semantics.digest(memory),
        "pair_index": pair_index,
        "schema_version": semantics.SUPPORT_BINDING_SCHEMA,
    }
    return {**body, "binding_digest": semantics.digest(body)}


def _serialized_trace_step(step: dict, edge_ref: str) -> dict:
    return {
        "learned_edge_ref": edge_ref,
        "learning_proof": {"metadata": {"transition_rule_hypotheses": []}},
        "post_observation": step["after_observation"],
        "pre_observation": step["before_observation"],
        "proposal": {"deliberator_proof": {"transition_rule_hypotheses": []}},
        "proposal_proof": {"metadata": {"transition_rule_hypotheses": []}},
        "selected_action": step["selected_action"],
        "step_index": 0,
        "step_result": {
            "observation": step["after_observation"],
            "success": step["success"],
        },
        "valid_actions": step["valid_actions"],
    }


def test_semantic_module_has_no_candidate_import() -> None:
    source = Path(semantics.__file__).read_text(encoding="utf-8")
    assert "packages.fusion_loop" not in source
    assert "interactive_organs" not in source
    assert "validate_rule_ir" not in source
    assert "evaluate_rule_ir" not in source


def test_projection_is_strictly_below_features_and_excludes_bools() -> None:
    projection = semantics.strict_feature_projection(_observation(4))
    assert projection == {MODULUS: 7, REGISTER: 4}
    assert "/outside_integer" not in projection
    assert "/caller_verified" not in projection
    assert "/features/truthy_but_not_integer" not in projection

    forged = _observation(4)
    forged.pop("features")
    with pytest.raises(semantics.SemanticEvidenceError):
        semantics.strict_feature_projection(forged)


def test_payload_signature_binds_complete_actual_payload() -> None:
    payload = _payload("alpha")
    assert semantics.payload_signature(payload) == semantics.digest(payload)
    changed_nested = copy.deepcopy(payload)
    changed_nested["opaque"]["cue"] = "forged"
    changed_extra = {**payload, "caller_verified": True}
    assert semantics.payload_signature(changed_nested) != semantics.payload_signature(payload)
    assert semantics.payload_signature(changed_extra) != semantics.payload_signature(payload)
    with pytest.raises(semantics.SemanticEvidenceError):
        semantics.payload_signature({})


def test_rule_parser_and_interpreter_are_exact_and_fail_closed() -> None:
    ledger = _honest_ledger()
    rule, _record = _honest_rule_and_record(ledger)
    parsed = semantics.parse_rule_ir(rule)
    assert semantics.affine_coefficients(parsed) == (2, 1)
    result = semantics.execute_rule_ir(
        parsed,
        {REGISTER: 6, MODULUS: 7},
    )
    assert result[REGISTER] == 6  # (2*6+1) mod 7

    extra_status = {**rule, "verified": True}
    with pytest.raises(semantics.SemanticEvidenceError):
        semantics.parse_rule_ir(extra_status)
    outside = copy.deepcopy(rule)
    outside["input_path"] = "/outside_integer"
    outside["expression"]["args"][0]["args"][0]["args"][0]["path"] = "/outside_integer"
    with pytest.raises(semantics.SemanticEvidenceError):
        semantics.parse_rule_ir(outside)
    bool_const = copy.deepcopy(rule)
    bool_const["expression"]["args"][0]["args"][1]["value"] = True
    with pytest.raises(semantics.SemanticEvidenceError):
        semantics.parse_rule_ir(bool_const)


def test_ledger_reconstructs_action_payload_and_rejects_forged_bindings() -> None:
    step = _step(0, 1)
    ledger = semantics.reconstruct_edge_ledger([step])
    row = ledger["rows"][0]
    assert row["action_signature"] == semantics.payload_signature(_payload("alpha"))
    assert row["edge_ref"].startswith("transition_edge_")

    forged_payload = copy.deepcopy(step)
    forged_payload["action_payload"] = _payload("forged")
    with pytest.raises(semantics.SemanticEvidenceError):
        semantics.reconstruct_edge_ledger([forged_payload])

    forged_ref = copy.deepcopy(step)
    forged_ref["learned_edge_ref"] = "transition_edge_caller_attested"
    with pytest.raises(semantics.SemanticEvidenceError):
        semantics.reconstruct_edge_ledger([forged_ref])


def test_repeated_actual_edge_is_counted_but_feature_memory_is_deduplicated() -> None:
    first = _step(0, 1, episode_ref="episode:0")
    repeated = _step(0, 1, episode_ref="episode:1")
    ledger = semantics.reconstruct_edge_ledger([first, repeated])
    assert len(ledger["rows"]) == 2
    assert ledger["rows"][0]["edge_ref"] == ledger["rows"][1]["edge_ref"]
    expected = semantics._expected_memory_rows(ledger["rows"])
    assert len(expected["feature_edges"]) == 1
    assert expected["transitions"][0]["count"] == 2
    assert expected["semantic_attempts"][0]["count"] == 1


def test_support_fit_uniqueness_and_prequential_record_are_independent() -> None:
    ledger = _honest_ledger()
    rule, record = _honest_rule_and_record(ledger)
    support = semantics.verify_rule_support(rule, ledger, emission_ordinal=3)
    assert support["passed"], support
    assert support["coefficient"] == [2, 1]
    assert support["distinct_input_count"] == 3
    chronology = semantics.verify_rule_record(record, ledger)
    assert chronology["passed"], chronology
    assert chronology["confirmation_count"] == 1

    forged_refs = copy.deepcopy(rule)
    forged_refs["support_edge_refs"] = sorted(rule["support_edge_refs"][:2] + ["caller-edge"])
    assert not semantics.verify_rule_support(
        forged_refs, ledger, emission_ordinal=3
    )["passed"]

    forged_coefficient = copy.deepcopy(rule)
    forged_coefficient["expression"]["args"][0]["args"][0]["args"][1]["value"] = 3
    assert not semantics.verify_rule_support(
        forged_coefficient, ledger, emission_ordinal=3
    )["passed"]


def test_memory_and_rule_timeline_reconstruct_from_actual_ledger() -> None:
    ledger = _honest_ledger()
    rule, record = _honest_rule_and_record(ledger)
    memory = _memory_for(ledger, [record])
    memory_report = semantics.verify_memory_against_ledger(memory, ledger)
    assert memory_report["passed"], memory_report

    timeline = semantics.verify_rule_timeline(
        ledger,
        _rule_events(rule),
        memory,
    )
    assert timeline["passed"], timeline

    forged_memory = copy.deepcopy(memory)
    forged_memory["feature_edges"][0]["before"][REGISTER] = 6
    assert not semantics.verify_memory_against_ledger(forged_memory, ledger)["passed"]

    early_events = _rule_events(rule)
    early_events["events"][0]["action_count"] = 2
    assert not semantics.verify_rule_timeline(ledger, early_events, memory)["passed"]


def test_four_episode_support_memory_chain_is_rebuilt_before_binding() -> None:
    actions = [
        _step(0, 1, episode_ref="support:0", step_index=0),
        _step(1, 3, episode_ref="support:1", step_index=0),
        _step(3, 0, episode_ref="support:2", step_index=0),
        _step(2, 5, episode_ref="support:3", step_index=0),
    ]
    full_ledger = semantics.reconstruct_edge_ledger(actions)
    rule, usable = _honest_rule_and_record(full_ledger)
    provisional = copy.deepcopy(usable)
    provisional["confirmation_edge_refs"] = []
    provisional["status"] = "provisional"
    traces = []
    memory_before = semantics.canonical_empty_memory()
    for index, step in enumerate(actions):
        prefix = semantics.reconstruct_edge_ledger(actions[: index + 1])
        records = []
        if index == 2:
            records = [provisional]
        elif index == 3:
            records = [usable]
        memory_after = _memory_for(prefix, records)
        traces.append(
            {
                "semantic_trace": {
                    "memory_after": memory_after,
                    "memory_before": memory_before,
                    "steps": [
                        _serialized_trace_step(
                            step,
                            full_ledger["rows"][index]["edge_ref"],
                        )
                    ],
                }
            }
        )
        memory_before = memory_after

    verified = semantics.verify_support_memory_chain(traces, pair_index=0)
    assert verified["passed"], verified
    binding = semantics.build_support_memory_binding(pair_index=0, traces=traces)
    assert binding["passed"], binding
    assert binding["binding"]["memory"] == traces[-1]["semantic_trace"]["memory_after"]

    forged = copy.deepcopy(traces)
    forged[2]["semantic_trace"]["memory_before"] = semantics.canonical_empty_memory()
    assert not semantics.verify_support_memory_chain(forged, pair_index=0)["passed"]


def test_contradiction_must_remove_rule_from_events_and_final_memory() -> None:
    honest = _honest_ledger()
    contradiction = _step(
        4,
        4,  # honest rule predicts 2
        episode_ref="episode:2",
        step_index=0,
    )
    ledger = semantics.reconstruct_edge_ledger(
        [
            _step(0, 1, step_index=0),
            _step(1, 3, step_index=1),
            _step(3, 0, step_index=2),
            _step(2, 5, episode_ref="episode:1", step_index=0),
            contradiction,
        ]
    )
    rule, record = _honest_rule_and_record(honest)
    invalidated_memory = _memory_for(ledger, [])
    clean_events = _rule_events(rule, total_action_count=5)
    clean = semantics.verify_rule_timeline(ledger, clean_events, invalidated_memory)
    assert clean["passed"], clean

    forged_events = _rule_events(rule, total_action_count=5)
    forged_events["events"].append(
        {
            "action_count": 5,
            "phase": "learning",
            "rule_digests": [semantics.digest(rule)],
            "rules": [rule],
            "step_index": 0,
            "trace_index": 2,
        }
    )
    forged_body = {
        "events": forged_events["events"],
        "schema_version": forged_events["schema_version"],
        "total_edge_count": forged_events["total_edge_count"],
    }
    forged_events["event_digest"] = semantics.digest(forged_body)
    forged_memory = _memory_for(ledger, [record])
    forged = semantics.verify_rule_timeline(ledger, forged_events, forged_memory)
    assert not forged["passed"]
    assert any("contradiction" in finding for finding in forged["findings"])


def test_raw_trace_rule_extraction_tracks_proposal_vs_learning_chronology() -> None:
    ledger = _honest_ledger()
    rule, _record = _honest_rule_and_record(ledger)
    step = {
        "learned_edge_ref": ledger["rows"][0]["edge_ref"],
        "learning_proof": {
            "metadata": {"transition_rule_hypotheses": [rule]}
        },
        "post_observation": _observation(1),
        "pre_observation": _observation(0),
        "proposal": {
            "deliberator_proof": {"transition_rule_hypotheses": []}
        },
        "proposal_proof": {
            "metadata": {"transition_rule_hypotheses": []}
        },
        "selected_action": "hand-action",
        "step_index": 0,
        "step_result": {
            "observation": _observation(1),
            "success": False,
        },
        "valid_actions": [
            {"action_id": "hand-action", "payload": _payload("alpha")},
            {"action_id": "other-action", "payload": _payload("other")},
        ],
    }
    trace = {"semantic_trace": {"steps": [step]}}
    extraction = semantics.extract_candidate_rule_events(trace)
    assert extraction["passed"], extraction
    learning = [item for item in extraction["events"] if item["phase"] == "learning"]
    proposal = [item for item in extraction["events"] if item["phase"] == "proposal"]
    assert learning[0]["action_count"] == 1
    assert learning[0]["rule_digests"] == [semantics.digest(rule)]
    assert proposal[0]["action_count"] == 0
    normalized = semantics.evaluator_steps_from_trace(trace, episode_ref="trace:0")
    assert semantics.reconstruct_edge_ledger(normalized)["rows"][0][
        "action_signature"
    ] == ledger["rows"][0]["action_signature"]


def test_counterfactual_p19_scores_all_76_cells_and_catches_wrong_rule() -> None:
    programs = [(1, 2), (2, 1), (-1, 3), (3, -2)]
    rules = []
    action_programs = {}
    for index, (a, b) in enumerate(programs):
        signature = semantics.payload_signature(_payload(f"program-{index}"))
        action_programs[signature] = [a, b]
        rules.append(_rule(signature, ["edge-a", "edge-b", "edge-c"], multiplier=a, offset=b))
    score = semantics.score_counterfactuals(rules, action_programs)
    assert score["passed"], score
    assert score["total_cells"] == 76
    assert score["predicted_cells"] == 76
    assert score["correct_predictions"] == 76
    assert score["precision"] == 1.0
    assert score["coverage"] == 1.0

    forged = copy.deepcopy(rules)
    forged[0]["expression"]["args"][0]["args"][1]["value"] = 1
    bad_score = semantics.score_counterfactuals(forged, action_programs)
    assert not bad_score["passed"]
    assert bad_score["precision"] < 1.0


def test_target_memory_binding_is_evaluator_derived_for_all_three_arms() -> None:
    ledger_zero = semantics.reconstruct_edge_ledger([_step(0, 1)])
    ledger_one = semantics.reconstruct_edge_ledger(
        [_step(2, 5, action_id="pair-one-action", label="pair-one")]
    )
    memory_zero = _memory_for(ledger_zero, [])
    memory_one = _memory_for(ledger_one, [])
    supports = {
        0: _support_binding(0, ledger_zero, memory_zero),
        1: _support_binding(1, ledger_one, memory_one),
    }
    matched = semantics.bind_target_memory(
        arm="matched_warm",
        pair_index=0,
        support_bindings=supports,
        pair_count=2,
    )
    mismatch = semantics.bind_target_memory(
        arm="mismatched_warm",
        pair_index=0,
        support_bindings=supports,
        pair_count=2,
    )
    cold = semantics.bind_target_memory(
        arm="cold",
        pair_index=0,
        support_bindings=supports,
        pair_count=2,
    )
    assert matched["source_pair_index"] == 0
    assert mismatch["source_pair_index"] == 1
    assert cold["source_pair_index"] is None
    assert semantics.verify_target_memory_binding(
        actual_memory_before=memory_zero,
        arm="matched_warm",
        pair_index=0,
        support_bindings=supports,
        pair_count=2,
        claimed_binding=matched,
    )["passed"]
    assert semantics.verify_target_memory_binding(
        actual_memory_before=memory_one,
        arm="mismatched_warm",
        pair_index=0,
        support_bindings=supports,
        pair_count=2,
        claimed_binding=mismatch,
    )["passed"]
    assert semantics.verify_target_memory_binding(
        actual_memory_before=semantics.canonical_empty_memory(),
        arm="cold",
        pair_index=0,
        support_bindings=supports,
        pair_count=2,
        claimed_binding=cold,
    )["passed"]

    # A caller can relabel/reseal its own memory, but cannot change the
    # evaluator-derived bytes that this comparison requires.
    forged_actual = copy.deepcopy(memory_zero)
    forged_actual["caller_arm"] = "matched_warm"
    assert not semantics.verify_target_memory_binding(
        actual_memory_before=forged_actual,
        arm="matched_warm",
        pair_index=0,
        support_bindings=supports,
        pair_count=2,
        claimed_binding=matched,
    )["passed"]
    forged_binding = copy.deepcopy(matched)
    forged_binding["source_pair_index"] = 1
    forged_body = {
        key: value for key, value in forged_binding.items() if key != "binding_digest"
    }
    forged_binding["binding_digest"] = semantics.digest(forged_body)
    assert not semantics.verify_target_memory_binding(
        actual_memory_before=memory_zero,
        arm="matched_warm",
        pair_index=0,
        support_bindings=supports,
        pair_count=2,
        claimed_binding=forged_binding,
    )["passed"]

    forged_supports = copy.deepcopy(supports)
    forged_supports[0]["memory"]["target_state_digest"] = semantics.digest(
        {"caller": "self-attested"}
    )
    forged_supports[0]["memory_digest"] = semantics.digest(
        forged_supports[0]["memory"]
    )
    forged_support_body = {
        key: value
        for key, value in forged_supports[0].items()
        if key != "binding_digest"
    }
    forged_supports[0]["binding_digest"] = semantics.digest(forged_support_body)
    with pytest.raises(semantics.SemanticEvidenceError):
        semantics.bind_target_memory(
            arm="matched_warm",
            pair_index=0,
            support_bindings=forged_supports,
            pair_count=2,
        )
