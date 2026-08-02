from __future__ import annotations

import copy
import importlib.util
import json
from pathlib import Path
import sys

import pytest


REPO = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location(
    "gwip_capability_design",
    REPO / "scripts" / "gwip_capability_design.py",
)
assert SPEC is not None and SPEC.loader is not None
gwip = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = gwip
SPEC.loader.exec_module(gwip)


FIXTURE_SEED = "capability-design-fixture-seed-not-final"
FIXTURE_NONCE = "capability-design-fixture-nonce-not-final"


@pytest.fixture(scope="module")
def prereg() -> dict:
    return gwip.load_preregistration()[0]


@pytest.fixture(scope="module")
def pairs(prereg: dict) -> tuple:
    return gwip.generate_capability_pairs(
        prereg,
        generator_seed=FIXTURE_SEED,
        generator_nonce=FIXTURE_NONCE,
    )


def test_frozen_preregistration_is_exact_and_rejects_threshold_drift(
    tmp_path: Path,
) -> None:
    value, digest = gwip.load_preregistration()
    assert value == gwip.FROZEN_PREREGISTRATION
    assert len(digest) == 64
    assert value["pair_count"] == 64
    assert value["candidate_episode_count"] == 1024
    assert value["source_modulus"] == 13
    assert value["target_modulus"] == 17
    assert value["counterfactual_modulus"] == 19
    assert value["bootstrap_resamples"] == 10_000
    assert value["bootstrap_seed"] == 2026072702

    altered = copy.deepcopy(value)
    altered["transfer_score_minimum"] = 0.0
    path = tmp_path / "altered-prereg.json"
    path.write_text(json.dumps(altered), encoding="utf-8")
    with pytest.raises(
        gwip.CapabilityDesignError,
        match="frozen exact contract",
    ):
        gwip.load_preregistration(path)


def test_generator_is_deterministic_post_seed_input_only_and_changes_with_nonce(
    prereg: dict,
    pairs: tuple,
) -> None:
    repeated = gwip.generate_capability_pairs(
        prereg,
        generator_seed=FIXTURE_SEED,
        generator_nonce=FIXTURE_NONCE,
    )
    changed = gwip.generate_capability_pairs(
        prereg,
        generator_seed=FIXTURE_SEED,
        generator_nonce=FIXTURE_NONCE + "-changed",
    )
    assert repeated == pairs
    assert gwip.private_cohort_digest(repeated) == gwip.private_cohort_digest(pairs)
    assert gwip.private_cohort_digest(changed) != gwip.private_cohort_digest(pairs)
    assert len(pairs) == 64
    assert [item.pair_index for item in pairs] == list(range(64))
    with pytest.raises(gwip.CapabilityDesignError, match="canonical opaque"):
        gwip.generate_capability_pairs(
            prereg,
            generator_seed="ambiguous|seed-token",
            generator_nonce=FIXTURE_NONCE,
        )
    with pytest.raises(gwip.CapabilityDesignError, match="empty or non-contiguous"):
        gwip.private_cohort_digest(pairs[:-1])


def test_each_pair_has_frozen_affine_shape_and_cross_modulus_identity(
    pairs: tuple,
) -> None:
    seen_cues: set[str] = set()
    for pair in pairs:
        assert len(pair.programs) == 4
        assert len(set(pair.programs)) == 4
        assert sum(program.is_nonzero_translation for program in pair.programs) == 1
        assert all(
            -3 <= program.multiplier <= 3
            and program.multiplier != 0
            and -3 <= program.offset <= 3
            and (program.multiplier, program.offset) != (1, 0)
            for program in pair.programs
        )
        assert not (set(pair.payload_cues) & seen_cues)
        seen_cues.update(pair.payload_cues)
        assert len(pair.source.state_refs) == 13
        assert len(pair.target.state_refs) == 17
        assert len(pair.counterfactual.state_refs) == 19
        assert len(pair.source.episodes) == len(pair.target.episodes) == 4
        assert pair.counterfactual.episodes == ()

        for index, program in enumerate(pair.programs):
            source = pair.source.actions[index]
            target = pair.target.actions[index]
            hidden = pair.counterfactual.actions[index]
            assert source.program == target.program == hidden.program == program
            assert source.payload == target.payload == hidden.payload
            assert (
                source.payload_signature
                == target.payload_signature
                == hidden.payload_signature
                == gwip.canonical_digest(source.payload)
            )
            assert len({source.action_ref, target.action_ref, hidden.action_ref}) == 3
            for environment in (pair.source, pair.target, pair.counterfactual):
                for value in range(environment.modulus):
                    assert environment.transition(
                        environment.state_ref_for_value(value),
                        environment.actions[index].action_ref,
                    ) == environment.state_ref_for_value(
                        program.apply(value, environment.modulus)
                    )


def test_source_target_public_surfaces_are_disjoint_except_payload_and_program(
    pairs: tuple,
) -> None:
    for pair in pairs:
        source = pair.source
        target = pair.target
        assert set(source.state_refs).isdisjoint(target.state_refs)
        assert {item.action_ref for item in source.actions}.isdisjoint(
            item.action_ref for item in target.actions
        )
        assert {
            item.edge_ref for item in source.transitions
        }.isdisjoint(item.edge_ref for item in target.transitions)
        assert {
            item.transition_tuple_digest for item in source.transitions
        }.isdisjoint(item.transition_tuple_digest for item in target.transitions)
        assert source.schema_version != target.schema_version
        assert {
            gwip.canonical_digest(item["payload"])
            for item in source.public_actions()
        } == {
            gwip.canonical_digest(item["payload"])
            for item in target.public_actions()
        }
        assert [
            gwip.canonical_digest(item["payload"])
            for item in source.public_actions()
        ] != [
            gwip.canonical_digest(item["payload"])
            for item in target.public_actions()
        ]
        assert len(
            {
                source.action_presentation_order,
                target.action_presentation_order,
                pair.counterfactual.action_presentation_order,
            }
        ) == 3
        environments = (source, target, pair.counterfactual)
        for left_index, left in enumerate(environments):
            for right in environments[left_index + 1 :]:
                assert all(
                    left.action_presentation_order[position]
                    != right.action_presentation_order[position]
                    for position in range(4)
                )


def test_episode_oracles_observations_and_goals_are_evaluator_derived(
    pairs: tuple,
) -> None:
    pair = pairs[0]
    for environment in (pair.source, pair.target):
        assert len({item.start_ref for item in environment.episodes}) == 4
        assert len({item.goal_ref for item in environment.episodes}) == 4
        for episode in environment.episodes:
            state = episode.start_ref
            for action_ref in episode.oracle_action_refs:
                state = environment.transition(state, action_ref)
            assert state == episode.goal_ref
            observation = environment.observation(
                episode.start_ref,
                goal_ref=episode.goal_ref,
            )
            assert observation == {
                "schema_version": environment.schema_version,
                "state_ref": episode.start_ref,
                "features": {
                    "registers": [episode.start_value],
                    "context": {"modulus": environment.modulus},
                },
                "terminal": False,
            }
            assert environment.goal_metadata(episode.episode_index) == {
                "target_constraints": [
                    {
                        "path": "/features/registers/0",
                        "op": "eq",
                        "value": episode.goal_value,
                    }
                ]
            }


def test_schedule_ordinals_and_latin_target_order_are_frozen() -> None:
    rows = gwip.candidate_schedule_rows()
    assert len(rows) == 1024
    assert [item["ordinal"] for item in rows] == list(range(1024))
    assert gwip.support_semantic_ordinal(0, 0) == 0
    assert gwip.support_semantic_ordinal(63, 3) == 255
    assert gwip.target_semantic_ordinal(0, "matched_warm", 0) == 256
    assert gwip.target_semantic_ordinal(63, "mismatched_warm", 3) == 1023
    assert len({gwip.target_arm_order(index) for index in range(6)}) == 6
    assert gwip.target_arm_order(6) == gwip.target_arm_order(0)


def _synthetic_prior_inventory(*, colliding_token: str | None = None):
    private_refs = {
        f"prior-mechanic-{index:02d}" for index in range(48)
    }
    states = {
        f"prior-state-{index:02d}-{state}"
        for index in range(48)
        for state in range(8)
    }
    if colliding_token is not None:
        states.add(colliding_token)
    return gwip.PriorMechanismNonoverlapInput(
        cohort_binding="a" * 64,
        private_mechanic_refs=frozenset(private_refs),
        state_tokens=frozenset(states),
        action_tokens=frozenset(
            f"prior-action-{index:02d}" for index in range(48)
        ),
        payload_cues=frozenset(),
        start_tokens=frozenset(
            f"prior-state-{index:02d}-0" for index in range(48)
        ),
        goal_tokens=frozenset(
            f"prior-state-{index:02d}-1" for index in range(48)
        ),
        observation_tokens=frozenset(
            f"prior-observation-{index:02d}-{state}"
            for index in range(48)
            for state in range(8)
        ),
        transition_edge_tokens=frozenset(
            f"prior-edge-{index:02d}" for index in range(48)
        ),
        transition_tuple_digests=frozenset(
            gwip.canonical_digest(
                {
                    "state_ref": f"prior-state-{index:02d}-0",
                    "action_ref": f"prior-action-{index:02d}",
                    "next_state_ref": f"prior-state-{index:02d}-1",
                }
            )
            for index in range(48)
        ),
        state_counts=(8,) * 48,
    )


def test_prior_mechanism_nonoverlap_interface_fails_closed_on_collision(
    pairs: tuple,
) -> None:
    clean = gwip.audit_prior_mechanism_nonoverlap(
        pairs, _synthetic_prior_inventory()
    )
    assert clean["passed"] is True
    assert clean["token_overlap"] == []
    collision = pairs[0].source.state_refs[0]
    dirty = gwip.audit_prior_mechanism_nonoverlap(
        pairs, _synthetic_prior_inventory(colliding_token=collision)
    )
    assert dirty["passed"] is False
    assert dirty["token_overlap"] == [collision]
    with pytest.raises(gwip.CapabilityDesignError, match="inventory is incomplete"):
        gwip.PriorMechanismNonoverlapInput(
            **{
                **_synthetic_prior_inventory().__dict__,
                "observation_tokens": frozenset(),
            }
        )


def test_freshness_inventory_uses_runtime_observation_and_edge_namespaces(
    pairs: tuple,
) -> None:
    pair = pairs[0]
    environment = pair.source
    episode = environment.episodes[0]
    inventory = gwip.capability_nonoverlap_inventory((pair,))
    before = environment.observation(
        environment.state_refs[0],
        goal_ref=episode.goal_ref,
    )
    transition = next(
        item
        for item in environment.transitions
        if item.state_ref == environment.state_refs[0]
    )
    after = environment.observation(
        transition.next_state_ref,
        goal_ref=episode.goal_ref,
    )
    before_digest = gwip.canonical_digest(before)
    expected_edge = (
        "transition_edge_"
        + gwip.canonical_digest(
            {
                "action_id": transition.action_ref,
                "from": before_digest,
                "to": gwip.canonical_digest(after),
            }
        )[:32]
    )
    assert before_digest in inventory["observation_tokens"]
    assert expected_edge in inventory["transition_edge_tokens"]
    assert transition.edge_ref not in inventory["transition_edge_tokens"]


def _rule_for_action(action, *, multiplier: int, offset: int) -> dict:
    return {
        "schema_version": "atanor.gwip-feature-rule.v1",
        "action_signature": action.payload_signature,
        "input_path": "/features/registers/0",
        "output_path": "/features/registers/0",
        "context_path": "/features/context/modulus",
        "expression": {
            "op": "mod",
            "args": [
                {
                    "op": "add",
                    "args": [
                        {
                            "op": "mul",
                            "args": [
                                {
                                    "op": "var",
                                    "path": "/features/registers/0",
                                },
                                {"op": "const", "value": multiplier},
                            ],
                        },
                        {"op": "const", "value": offset},
                    ],
                },
                {
                    "op": "var",
                    "path": "/features/context/modulus",
                },
            ],
        },
        "support_edge_refs": [
            f"observed-edge-{action.action_index}-{index}" for index in range(3)
        ],
        "hypothesis": True,
    }


def test_independent_rule_executor_scores_all_76_hidden_cells(
    prereg: dict,
    pairs: tuple,
) -> None:
    pair = pairs[0]
    rules = [
        _rule_for_action(
            action,
            multiplier=action.program.multiplier,
            offset=action.program.offset,
        )
        for action in pair.source.actions
    ]
    score = gwip.score_counterfactual_rule_set(
        rules,
        pair=pair,
        preregistration=prereg,
    )
    assert score.valid is True
    assert score.correct_predictions == score.prediction_count == 76
    assert score.precision == score.coverage == 1.0
    assert score.qualifies(prereg) is True

    incomplete = gwip.score_counterfactual_rule_set(
        rules[:3],
        pair=pair,
        preregistration=prereg,
    )
    assert incomplete.valid is True
    assert incomplete.prediction_count == 57
    assert incomplete.coverage == 0.75
    assert incomplete.qualifies(prereg) is False


def test_independent_rule_parser_rejects_caller_metadata_and_boolean_features(
    prereg: dict,
    pairs: tuple,
) -> None:
    action = pairs[0].source.actions[0]
    rule = _rule_for_action(
        action,
        multiplier=action.program.multiplier,
        offset=action.program.offset,
    )
    rule["input_path"] = "/verified"
    with pytest.raises(gwip.CapabilityDesignError, match="feature paths"):
        gwip.validate_rule_ir_independently(rule, prereg)

    projection = gwip.project_evaluator_features(
        {
            "features": {
                "registers": [3, False],
                "context": {"modulus": 19},
            },
            "verified": 1,
            "status": 7,
        }
    )
    assert projection == {
        "/features/context/modulus": 19,
        "/features/registers/0": 3,
    }


def test_controls_are_deterministic_and_bound_to_pair(pairs: tuple) -> None:
    environment = pairs[0].source
    episode = environment.episodes[0]
    observation = environment.observation(
        episode.start_ref, goal_ref=episode.goal_ref
    )
    actions = [item.action_ref for item in environment.actions]
    assert gwip.ReactiveControl.choose_action(observation, actions) == (
        gwip.ReactiveControl.choose_action(observation, actions)
    )
    first = gwip.RandomControl(policy_seed=7, pair_binding=pairs[0].private_ref)
    second = gwip.RandomControl(policy_seed=7, pair_binding=pairs[0].private_ref)
    assert [
        first.choose_action(observation, actions) for _ in range(16)
    ] == [
        second.choose_action(observation, actions) for _ in range(16)
    ]


def test_regret_utility_bootstrap_and_nearest_rank_boundaries() -> None:
    assert gwip.normalized_regret(
        success=False,
        optimal_steps=1,
        executed_steps=24,
        step_budget=24,
    ) == 1.0
    assert gwip.normalized_regret(
        success=True,
        optimal_steps=4,
        executed_steps=4,
        step_budget=24,
    ) == 0.0
    assert gwip.normalized_regret(
        success=True,
        optimal_steps=4,
        executed_steps=14,
        step_budget=24,
    ) == 0.5
    assert gwip.utility_from_regret(0.5) == 0.5
    with pytest.raises(gwip.CapabilityDesignError, match="oracle"):
        gwip.normalized_regret(
            success=True,
            optimal_steps=4,
            executed_steps=3,
            step_budget=24,
        )
    assert gwip.nearest_rank_percentile(range(1, 65), 0.5) == 32
    assert gwip.nearest_rank_percentile(range(1, 65), 0.75) == 48
    assert gwip.paired_bootstrap_lcb(
        [0.125] * 64,
        resamples=10_000,
        seed=2026072702,
    ) == pytest.approx(0.125)


def _outcomes(*, success: bool, steps: int) -> tuple:
    return tuple(
        gwip.EpisodeOutcome(
            pair_index=pair,
            episode_index=episode,
            success=success,
            optimal_steps=1,
            executed_steps=steps,
        )
        for pair in range(64)
        for episode in range(4)
    )


def _green_rule_evidence() -> tuple:
    check = gwip.CounterfactualRuleCheck(True, 76, 76, 76)
    return tuple(
        gwip.PairRuleEvidence(
            pair_index=pair,
            checkpoints=(gwip.RuleCheckpoint(16, check),),
            final_checkpoint=gwip.RuleCheckpoint(64, check),
        )
        for pair in range(64)
    )


def _derive_green(prereg: dict) -> dict:
    candidate = _outcomes(success=True, steps=1)
    failures = _outcomes(success=False, steps=24)
    return gwip.derive_capability_metrics(
        candidate_support=candidate,
        reactive_support=failures,
        random_support={seed: failures for seed in range(32)},
        target_outcomes={
            "matched_warm": candidate,
            "cold": failures,
            "mismatched_warm": failures,
        },
        rule_evidence=_green_rule_evidence(),
        hard_gates={name: True for name in gwip.REQUIRED_HARD_GATES},
        preregistration=prereg,
    )


def test_metrics_green_red_and_fresh_replication_only_are_conjunctive(
    prereg: dict,
) -> None:
    green = _derive_green(prereg)
    assert green["verdict"] == "CAPABILITY_GREEN"
    assert green["capability_claim"] is True
    assert green["all_metrics_passed"] is True
    assert green["public_benchmark_claim"] is False
    assert green["production_activation_authorized"] is False

    candidate = _outcomes(success=True, steps=1)
    failures = _outcomes(success=False, steps=24)
    hard_gates = {name: True for name in gwip.REQUIRED_HARD_GATES}
    hard_gates["adversarial_self_attestation_rejection"] = False
    red = gwip.derive_capability_metrics(
        candidate_support=candidate,
        reactive_support=failures,
        random_support={seed: failures for seed in range(32)},
        target_outcomes={
            "matched_warm": candidate,
            "cold": failures,
            "mismatched_warm": failures,
        },
        rule_evidence=_green_rule_evidence(),
        hard_gates=hard_gates,
        preregistration=prereg,
    )
    assert red["verdict"] == "CAPABILITY_RED"
    assert red["capability_claim"] is False

    invalid = gwip.CounterfactualRuleCheck(False, 0, 0, 76, ("no rule",))
    no_rules = tuple(
        gwip.PairRuleEvidence(
            pair_index=pair,
            checkpoints=(),
            final_checkpoint=gwip.RuleCheckpoint(64, invalid),
        )
        for pair in range(64)
    )
    no_go = gwip.derive_capability_metrics(
        candidate_support=candidate,
        reactive_support=failures,
        random_support={seed: failures for seed in range(32)},
        target_outcomes={
            "matched_warm": candidate,
            "cold": failures,
            "mismatched_warm": failures,
        },
        rule_evidence=no_rules,
        hard_gates={name: True for name in gwip.REQUIRED_HARD_GATES},
        preregistration=prereg,
    )
    assert no_go["verdict"] == "NO_GO"
    assert no_go["explanatory_sublabel"] == "FRESH_REPLICATION_ONLY"
    assert no_go["capability_claim"] is False


def test_rule_discovery_nearest_rank_threshold_is_not_relaxed(
    prereg: dict,
) -> None:
    passing = gwip.CounterfactualRuleCheck(True, 76, 76, 76)
    failing = gwip.CounterfactualRuleCheck(False, 0, 0, 76, ("censored",))
    evidence = tuple(
        gwip.PairRuleEvidence(
            pair_index=pair,
            checkpoints=(
                gwip.RuleCheckpoint(
                    32 if pair < 32 else 64,
                    passing if pair < 48 else failing,
                ),
            ),
            final_checkpoint=gwip.RuleCheckpoint(
                64,
                passing if pair < 48 else failing,
            ),
        )
        for pair in range(64)
    )
    result = gwip.derive_rule_discovery(evidence, prereg)
    assert result["discovered_pair_count"] == 48
    assert result["median_discovery_action_nearest_rank"] == 32
    assert result["p75_discovery_action_nearest_rank"] == 64
    assert result["passed"] is True

    under = list(evidence)
    under[47] = gwip.PairRuleEvidence(
        pair_index=47,
        checkpoints=(),
        final_checkpoint=gwip.RuleCheckpoint(64, failing),
    )
    failed = gwip.derive_rule_discovery(tuple(under), prereg)
    assert failed["discovered_pair_count"] == 47
    assert failed["p75_discovery_action_nearest_rank"] == 97
    assert failed["passed"] is False


def test_human_exemplar_selector_uses_regret_steps_then_indices() -> None:
    rows = list(_outcomes(success=False, steps=24))
    rows[7] = gwip.EpisodeOutcome(1, 3, True, 1, 3)
    rows[4] = gwip.EpisodeOutcome(1, 0, True, 1, 2)
    rows[0] = gwip.EpisodeOutcome(0, 0, True, 1, 2)
    assert gwip.select_human_exemplar(tuple(rows)) == (0, 0)
    assert gwip.select_human_exemplar(_outcomes(success=False, steps=24)) == (
        0,
        0,
    )
