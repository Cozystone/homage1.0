from __future__ import annotations

import copy
import hashlib
import importlib.util
import json
import sys
from pathlib import Path

import pytest


REPO = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location(
    "gwip_mechanism_eval",
    REPO / "scripts" / "gwip_mechanism_eval.py",
)
assert SPEC is not None and SPEC.loader is not None
gwip = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = gwip
SPEC.loader.exec_module(gwip)


def _tiny_prereg() -> dict:
    value, _ = gwip.load_preregistration()
    value = copy.deepcopy(value)
    value["mechanic_count"] = 4
    value["candidate_episode_count"] = 12
    value["random_policy_seeds"] = [0, 1]
    value["bootstrap_resamples"] = 200
    return value


def test_frozen_preregistration_is_strict_and_self_consistent(tmp_path: Path) -> None:
    value, digest = gwip.load_preregistration()
    assert value["schema_version"] == gwip.PREREG_SCHEMA
    assert value["mechanic_count"] == 48
    assert value["episodes_per_mechanic"] == 3
    assert value["candidate_episode_count"] == 144
    assert len(value["random_policy_seeds"]) == 32
    assert len(digest) == 64

    altered = copy.deepcopy(value)
    altered["minimum_mean_swae_delta"] = 0.0
    path = tmp_path / "prereg.json"
    path.write_text(json.dumps(altered), encoding="utf-8")
    with pytest.raises(gwip.EvaluationContractError, match="frozen preregistration"):
        gwip.load_preregistration(path)


def test_opaque_fst_generator_is_deterministic_bounded_and_reachable() -> None:
    prereg, _ = gwip.load_preregistration()
    first = gwip.generate_hidden_mechanics(
        prereg,
        generator_seed="fixture-seed-not-final",
        generator_nonce="fixture-nonce-not-final",
    )
    second = gwip.generate_hidden_mechanics(
        prereg,
        generator_seed="fixture-seed-not-final",
        generator_nonce="fixture-nonce-not-final",
    )
    changed = gwip.generate_hidden_mechanics(
        prereg,
        generator_seed="fixture-seed-not-final",
        generator_nonce="different-fixture-nonce",
    )

    assert first == second
    assert gwip.private_cohort_digest(first) == gwip.private_cohort_digest(second)
    assert gwip.private_cohort_digest(first) != gwip.private_cohort_digest(changed)
    assert len(first) == 48
    assert [item.evaluator_index for item in first] == list(range(48))

    for mechanic in first:
        assert 8 <= len(mechanic.state_refs) <= 12
        assert 3 <= len(mechanic.action_refs) <= 4
        assert len(set(mechanic.state_refs)) == len(mechanic.state_refs)
        assert len(set(mechanic.action_refs)) == len(mechanic.action_refs)
        assert len(mechanic.episodes) == 3
        assert mechanic.goal_ref in mechanic.state_refs
        assert len(mechanic.transitions) == (
            len(mechanic.state_refs) * len(mechanic.action_refs)
        )
        for episode in mechanic.episodes:
            assert episode.start_ref != mechanic.goal_ref
            assert 1 <= episode.optimal_steps <= prereg["step_budget"]
            assert (
                gwip.shortest_path_steps(
                    mechanic,
                    episode.start_ref,
                    mechanic.goal_ref,
                )
                == episode.optimal_steps
            )

        public = mechanic.public_descriptor()
        public_text = json.dumps(public, sort_keys=True)
        assert "transition" not in public_text.lower()
        assert mechanic.private_ref not in public_text
        assert "generator" not in public_text.lower()


def test_environment_exposes_only_opaque_contract_and_records_exact_calls() -> None:
    mechanic = gwip.generate_hidden_mechanics(
        gwip.load_preregistration()[0],
        generator_seed="fixture-seed",
        generator_nonce="fixture-nonce",
    )[0]
    environment = gwip.OpaqueFSTEnvironment(mechanic, episode_index=0, step_budget=20)

    reset = environment.reset(seed=0)
    observation = environment.observe()
    actions = environment.valid_actions()
    action = actions[0]
    before = observation["state_ref"]
    stepped = environment.step(action)
    expected = mechanic.transition(before, action)
    environment.stop("fixture_stop")

    assert reset == {"reset": True}
    assert observation == {
        "schema_version": gwip.OBSERVATION_SCHEMA,
        "state_ref": mechanic.episodes[0].start_ref,
        "terminal": False,
    }
    assert tuple(actions) == mechanic.action_refs
    assert stepped["observation"]["state_ref"] == expected
    assert stepped["terminal"] is (expected == mechanic.goal_ref)
    assert stepped["success"] is stepped["terminal"]
    assert stepped["stop_reason"] == ("goal_reached" if stepped["terminal"] else None)
    assert [entry["operation"] for entry in environment.call_log] == [
        "reset",
        "observe",
        "valid_actions",
        "step",
        "stop",
    ]
    assert "private_ref" not in json.dumps(environment.call_log)


def test_environment_rejects_invalid_order_and_step_21_without_mutation() -> None:
    mechanic = gwip.generate_hidden_mechanics(
        gwip.load_preregistration()[0],
        generator_seed="fixture-seed",
        generator_nonce="fixture-nonce",
    )[0]
    environment = gwip.OpaqueFSTEnvironment(mechanic, episode_index=0, step_budget=20)
    with pytest.raises(gwip.EvaluationContractError, match="reset"):
        environment.observe()
    environment.reset(seed=0)
    with pytest.raises(gwip.EvaluationContractError, match="valid action"):
        environment.step("invented-action")

    action = environment.valid_actions()[0]
    for _ in range(20):
        environment.step(action)
    before = environment.state_ref
    calls_before = copy.deepcopy(environment.call_log)
    with pytest.raises(gwip.StepBudgetExhausted):
        environment.step(action)
    assert environment.state_ref == before
    assert environment.call_log == calls_before


def test_reactive_and_random_controls_are_frozen_and_reproducible() -> None:
    observation = {
        "schema_version": gwip.OBSERVATION_SCHEMA,
        "state_ref": "s_opaque",
        "terminal": False,
    }
    actions = ("a_three", "a_one", "a_two")
    expected = min(
        actions,
        key=lambda action: gwip.sha256_text(
            gwip.canonical_digest(observation) + action
        ),
    )
    reactive = gwip.ReactivePolicy()
    assert reactive.choose_action(observation, actions) == expected
    assert reactive.choose_action(observation, tuple(reversed(actions))) == expected

    random_a = gwip.RandomPolicy(
        policy_seed=7,
        mechanic_binding="m" * 64,
    )
    random_b = gwip.RandomPolicy(
        policy_seed=7,
        mechanic_binding="m" * 64,
    )
    seq_a = [random_a.choose_action(observation, actions) for _ in range(20)]
    seq_b = [random_b.choose_action(observation, actions) for _ in range(20)]
    assert seq_a == seq_b
    assert set(seq_a) <= set(actions)
    assert len(set(seq_a)) > 1


def test_counterbalanced_arm_order_uses_each_permutation_eight_times() -> None:
    orders = [gwip.counterbalanced_arm_order(index) for index in range(48)]
    assert len(set(orders)) == 6
    assert all(orders.count(order) == 8 for order in set(orders))
    assert all(set(order) == {"candidate", "reactive", "random"} for order in orders)


def test_swae_and_mechanic_grain_aggregation_are_exact() -> None:
    assert gwip.episode_swae(success=True, optimal_steps=2, executed_steps=4) == 0.5
    assert gwip.episode_swae(success=False, optimal_steps=2, executed_steps=4) == 0.0
    assert gwip.episode_swae(success=False, optimal_steps=2, executed_steps=0) == 0.0
    with pytest.raises(gwip.EvaluationContractError):
        gwip.episode_swae(success=True, optimal_steps=0, executed_steps=4)

    episodes = [
        gwip.EpisodeMetric(0, 0, True, 2, 2, 1.0, "goal_reached"),
        gwip.EpisodeMetric(0, 1, True, 2, 4, 0.5, "goal_reached"),
        gwip.EpisodeMetric(0, 2, False, 2, 20, 0.0, "step_budget"),
        gwip.EpisodeMetric(1, 0, True, 1, 1, 1.0, "goal_reached"),
        gwip.EpisodeMetric(1, 1, True, 2, 2, 1.0, "goal_reached"),
        gwip.EpisodeMetric(1, 2, True, 3, 3, 1.0, "goal_reached"),
    ]
    aggregate = gwip.aggregate_mechanics(
        episodes,
        mechanic_count=2,
        episodes_per_mechanic=3,
    )
    assert aggregate.mechanic_swae == pytest.approx((0.5, 1.0))
    assert aggregate.mean_swae == pytest.approx(0.75)
    assert aggregate.success_rate == pytest.approx(5 / 6)


def test_random_arm_is_averaged_within_mechanic_before_comparison() -> None:
    prereg, _ = gwip.load_preregistration()
    mechanic_count = prereg["mechanic_count"]
    episode_count = prereg["candidate_episode_count"]
    arms = [
        gwip.PolicyAggregate(
            (0.2 + seed / 1000,) * mechanic_count,
            0.2 + seed / 1000,
            0.5,
            episode_count,
        )
        for seed in prereg["random_policy_seeds"]
    ]
    averaged = gwip.average_random_aggregates(
        arms,
        preregistration=prereg,
    )
    expected = sum(0.2 + seed / 1000 for seed in range(32)) / 32
    assert averaged.mechanic_swae == pytest.approx((expected,) * 48)
    assert averaged.mean_swae == pytest.approx(expected)
    assert averaged.success_rate == pytest.approx(0.5)
    with pytest.raises(gwip.EvaluationContractError, match="seed census"):
        gwip.average_random_aggregates(
            arms[:-1],
            preregistration=prereg,
        )


def test_one_sided_paired_bootstrap_is_deterministic_and_mechanic_grain() -> None:
    candidate = tuple(0.8 + (index % 3) * 0.01 for index in range(48))
    baseline = tuple(0.4 + (index % 2) * 0.01 for index in range(48))
    first = gwip.paired_bootstrap_lcb(
        candidate,
        baseline,
        resamples=10_000,
        seed=2026072701,
    )
    second = gwip.paired_bootstrap_lcb(
        candidate,
        baseline,
        resamples=10_000,
        seed=2026072701,
    )
    assert first == second
    assert first > 0.35
    assert (
        gwip.paired_bootstrap_lcb(
            tuple(0.5 for _ in range(48)),
            tuple(0.5 for _ in range(48)),
            resamples=10_000,
            seed=2026072701,
        )
        == 0.0
    )


def test_preregistered_verdict_requires_both_baselines_and_success() -> None:
    prereg, _ = gwip.load_preregistration()
    candidate = gwip.PolicyAggregate((0.8,) * 48, 0.8, 0.9, 144)
    reactive = gwip.PolicyAggregate((0.4,) * 48, 0.4, 0.8, 144)
    random = gwip.PolicyAggregate((0.5,) * 48, 0.5, 0.85, 144)
    green = gwip.score_efficiency_gate(candidate, reactive, random, prereg)
    assert green["passed"] is True
    assert green["comparisons"]["reactive"]["passed"] is True
    assert green["comparisons"]["random"]["passed"] is True

    too_close = gwip.PolicyAggregate((0.77,) * 48, 0.77, 0.85, 144)
    no_go = gwip.score_efficiency_gate(too_close, reactive, too_close, prereg)
    assert no_go["passed"] is False
    assert no_go["comparisons"]["random"]["mean_delta"] == 0.0

    lower_success = gwip.PolicyAggregate((0.9,) * 48, 0.9, 0.7, 144)
    regressed = gwip.score_efficiency_gate(lower_success, reactive, random, prereg)
    assert regressed["passed"] is False
    assert regressed["comparisons"]["reactive"]["success_non_regression"] is False


def test_static_domain_audit_rejects_arc_imports_vocabulary_and_domain_branches(
    tmp_path: Path,
) -> None:
    clean = tmp_path / "clean.py"
    clean.write_text(
        "def choose(observation, actions):\n"
        "    return sorted(actions)[0] if observation else None\n",
        encoding="utf-8",
    )
    assert gwip.audit_candidate_sources([clean], repository_root=tmp_path)["passed"] is True

    arc_import = tmp_path / "arc_import.py"
    arc_import.write_text("from packages.arc_agi import solver\n", encoding="utf-8")
    report = gwip.audit_candidate_sources([arc_import], repository_root=tmp_path)
    assert report["passed"] is False
    assert any("forbidden import" in finding for finding in report["findings"])

    vocabulary = tmp_path / "vocabulary.py"
    vocabulary.write_text("def choose(grid):\n    return grid\n", encoding="utf-8")
    report = gwip.audit_candidate_sources([vocabulary], repository_root=tmp_path)
    assert report["passed"] is False
    assert any("forbidden candidate vocabulary" in finding for finding in report["findings"])

    branch = tmp_path / "branch.py"
    branch.write_text(
        "def choose(domain, actions):\n"
        "    if domain == 'maze':\n"
        "        return actions[0]\n"
        "    return actions[-1]\n",
        encoding="utf-8",
    )
    report = gwip.audit_candidate_sources([branch], repository_root=tmp_path)
    assert report["passed"] is False
    assert any("domain-specific branch" in finding for finding in report["findings"])

    for name, source in {
        "main_import.py": "import __main__\n",
        "frame_escape.py": "import sys\nvalue = sys._getframe()\n",
        "registry_escape.py": "import sys\nvalue = sys.modules\n",
        "dynamic_main.py": "value = __import__('__main__')\n",
        "object_graph_escape.py": "import gc\nvalue = gc.get_objects()\n",
    }.items():
        path = tmp_path / name
        path.write_text(source, encoding="utf-8")
        report = gwip.audit_candidate_sources([path], repository_root=tmp_path)
        assert report["passed"] is False, (name, report)

    benign_gc = tmp_path / "benign_gc.py"
    benign_gc.write_text("import gc\ngc.collect()\n", encoding="utf-8")
    assert (
        gwip.audit_candidate_sources([benign_gc], repository_root=tmp_path)["passed"]
        is True
    )


def test_runtime_import_delta_rejects_only_new_forbidden_modules() -> None:
    before = {"sys", "packages.arc_agi"}
    clean = gwip.audit_runtime_import_delta(before, before | {"packages.fusion_loop"})
    assert clean["passed"] is True
    tainted = gwip.audit_runtime_import_delta(
        before,
        before | {"packages.vsa_reasoning.tests.test_arc_probe"},
    )
    assert tainted["passed"] is False


def test_call_order_audit_requires_one_stop_and_exact_cycles() -> None:
    valid = [
        {"operation": "reset"},
        {"operation": "observe"},
        {"operation": "valid_actions"},
        {"operation": "step"},
        {"operation": "observe"},
        {"operation": "valid_actions"},
        {"operation": "step"},
        {"operation": "stop"},
    ]
    assert gwip.audit_environment_call_order(valid, step_budget=20)["passed"] is True
    operator_stop = [
        {"operation": "reset"},
        {"operation": "observe"},
        {"operation": "stop"},
    ]
    assert (
        gwip.audit_environment_call_order(operator_stop, step_budget=20)["passed"]
        is True
    )
    invalid = valid[:-1] + [{"operation": "step"}, {"operation": "stop"}]
    report = gwip.audit_environment_call_order(invalid, step_budget=20)
    assert report["passed"] is False


def _episode_trace() -> gwip.EpisodeTrace:
    return gwip.EpisodeTrace(
        policy="candidate",
        evaluator_mechanic_index=0,
        episode_index=0,
        goal_ref="s_goal",
        initial_observation={"state_ref": "s_start", "terminal": False},
        steps=(
            gwip.TraceStep(
                step_index=0,
                observation={"state_ref": "s_start", "terminal": False},
                valid_actions=("a_left", "a_right"),
                selected_action="a_right",
                authority_reason="run_lease_action_authorized",
                authority_binding="b" * 64,
                post_observation={"state_ref": "s_goal", "terminal": True},
                learned_edge_ref="edge_opaque",
                world_snapshot_ref="world_opaque",
                goal_ir_ref="goal_opaque",
                proposal_ref="proposal_opaque",
                decision_receipt_ref="decision_opaque",
            ),
        ),
        stop_reason="goal_reached",
        success=True,
        optimal_steps=1,
        semantic_trace_digest="c" * 64,
    )


def test_human_episode_renderer_shows_complete_reset_to_stop_trace() -> None:
    rendered = gwip.render_episode(_episode_trace())
    assert "RESET" in rendered
    assert "OBSERVE" in rendered
    assert "VALID_ACTIONS" in rendered
    assert "AUTHORIZE" in rendered
    assert "STEP" in rendered
    assert "STOP" in rendered
    assert rendered.index("RESET") < rendered.index("OBSERVE") < rendered.index("STOP")
    assert "goal_reached" in rendered


def test_prepare_leases_creates_signed_external_write_once_plan(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    from packages.autonomy_envelope.run_lease import (
        GENERAL_INTERACTION_RUNNER_ID,
        RunLeaseBoundaryConfig,
        RunLeaseStore,
        verify_run_lease,
    )

    candidate_payload = {
        "commit": "1" * 40,
        "files": [{"path": "candidate.py", "sha256": "a" * 64}],
    }
    evaluator_payload = {
        "commit": "2" * 40,
        "files": [{"path": "evaluator.py", "sha256": "b" * 64}],
    }
    seed_binding = {
        "path": gwip.SEED_MANIFEST_RELATIVE_PATH,
        "commit": "3" * 40,
        "raw_sha256": "c" * 64,
        "candidate": {
            **candidate_payload,
            "source_digest": gwip.canonical_digest(candidate_payload),
        },
        "evaluator": {
            **evaluator_payload,
            "source_digest": gwip.canonical_digest(evaluator_payload),
        },
    }

    def fake_load_seed(
        path: Path,
        *,
        seed_manifest_commit: str,
        repository_root: Path,
    ) -> tuple[dict, dict]:
        assert path == REPO / gwip.SEED_MANIFEST_RELATIVE_PATH
        assert repository_root == REPO.resolve(strict=True)
        assert seed_manifest_commit == "3" * 40
        return {"candidate_commit": "1" * 40}, copy.deepcopy(seed_binding)

    monkeypatch.setattr(gwip, "load_and_verify_seed_manifest", fake_load_seed)
    external_root = (tmp_path / "gwip-operator-boundary").resolve()
    receipt = gwip.prepare_run_lease_plan(
        external_root,
        seed_manifest_commit="3" * 40,
    )
    assert receipt["entry_count"] == 144
    assert receipt["boundary_count"] == 144
    assert receipt["private_key_persisted"] is False
    assert Path(receipt["plan_path"]).parent == external_root
    assert Path(receipt["operator_public_key_path"]).parent == external_root
    assert not list(external_root.rglob("*private*"))

    preregistration, _ = gwip.load_preregistration()
    entries, binding = gwip.load_run_lease_plan(
        Path(receipt["plan_path"]),
        preregistration=preregistration,
    )
    assert len(entries) == 144
    assert binding["raw_sha256"] == receipt["plan_raw_sha256"]
    assert len({item["boundary_config_path"] for item in entries}) == 144
    assert len(
        {item["lease_document"]["lease_id"] for item in entries}
    ) == 144
    assert len({item["lease_document"]["nonce"] for item in entries}) == 144
    assert len(
        {
            item["live_context"]["nonce_replay_domain"]["ledger_id"]
            for item in entries
        }
    ) == 144
    assert len(
        {item["live_context"]["deployment_id"] for item in entries}
    ) == 144
    assert {
        "boundary_config_path",
        "lease_document",
        "live_context",
    }.isdisjoint(gwip._WORKER_REQUEST_FIELDS)
    wrong_seed_binding = copy.deepcopy(seed_binding)
    wrong_seed_binding["candidate"]["source_digest"] = "d" * 64
    with pytest.raises(
        gwip.EvaluationContractError,
        match="verified seed/source binding",
    ):
        gwip.verify_run_lease_plan_seed_binding(
            entries,
            seed_manifest_binding=wrong_seed_binding,
        )

    first = entries[0]
    boundary = RunLeaseBoundaryConfig.from_external_file(
        first["boundary_config_path"],
        repository_root=REPO,
    )
    verified = verify_run_lease(
        first["lease_document"],
        trust_root=boundary.trust_root,
        live_context=first["live_context"],
    )
    assert verified.ok is True
    forged_document = copy.deepcopy(first["lease_document"])
    forged_context = copy.deepcopy(first["live_context"])
    forged_document["runner_artifact_sha256"] = "f" * 64
    forged_context["runner_artifact_sha256"] = "f" * 64
    forged = verify_run_lease(
        forged_document,
        trust_root=boundary.trust_root,
        live_context=forged_context,
    )
    assert forged.ok is False
    assert forged.reason == "run_lease_payload_digest_mismatch"

    store = RunLeaseStore(boundary)
    activation = store.activate(
        document=first["lease_document"],
        live_context=first["live_context"],
    )
    assert activation.allowed is True
    authorization = store.authorize(
        lease_id=first["lease_document"]["lease_id"],
        runner_id=GENERAL_INTERACTION_RUNNER_ID,
        action_class="interaction.step",
        costs=gwip._FIXED_AUTHORIZATION_COSTS,
    )
    assert authorization.allowed is True
    finished = store.finish(
        lease_id=first["lease_document"]["lease_id"],
        runner_id=GENERAL_INTERACTION_RUNNER_ID,
        reason="fixture_stop",
    )
    assert finished.finished is True
    historical = gwip.verify_finished_run_lease_ledger(
        first,
        ordinal=0,
        mechanic_index=0,
        episode_index=0,
    )
    assert historical["state_ok"] is True
    assert historical["historical_signature_valid"] is True
    assert historical["execution_authority_restored"] is False

    with pytest.raises(
        gwip.EvaluationContractError,
        match="already exists",
    ):
        gwip.prepare_run_lease_plan(
            external_root,
            seed_manifest_commit="3" * 40,
        )


def test_candidate_worker_keeps_hidden_state_and_runlease_in_parent(
    tmp_path: Path,
) -> None:
    from packages.autonomy_envelope.run_lease import (
        GENERAL_INTERACTION_RUNNER_ID,
    )
    from packages.autonomy_envelope.tests.test_run_lease import (
        _live_context,
        _provision_boundary,
        _signed_lease,
    )

    private, boundary, _repository = _provision_boundary(tmp_path)
    context = _live_context(
        boundary,
        runner_id=GENERAL_INTERACTION_RUNNER_ID,
        max_actions=20,
    )
    context["limits"]["max_runtime_sec"] = 3_600
    context["limits"]["max_cycles"] = 20
    context["limits"]["max_scratch_write_bytes"] = 0
    context["capability_manifest"]["filesystem_policy_sha256"] = (
        gwip.sha256_text("atanor.gwip.filesystem.none.v1")
    )
    context["capability_manifest"]["network_policy_sha256"] = (
        gwip.sha256_text("atanor.gwip.network.none.v1")
    )
    context["capability_manifest"]["child_task_policy_sha256"] = (
        gwip.sha256_text("atanor.gwip.child-task.none.v1")
    )
    context["scratch_boundary"] = {
        "boundary_id": "gwip-no-scratch-000",
        "resolved_root_sha256": gwip.sha256_text(
            "atanor.gwip.no-scratch.root.v1:0"
        ),
        "identity_manifest_sha256": gwip.sha256_text(
            "atanor.gwip.no-scratch.identity.v1:0"
        ),
    }
    document = _signed_lease(
        private,
        boundary,
        context,
        lease_id="gwip-worker-integration-lease-0001",
        nonce="gwip-worker-integration-nonce-0001",
    )
    lease_entry = {
        "ordinal": 0,
        "mechanic_index": 0,
        "episode_index": 0,
        "boundary_config_path": str(boundary.config_path),
        "lease_document": document,
        "live_context": context,
    }
    preregistration, _ = gwip.load_preregistration()
    mechanic = gwip.generate_hidden_mechanics(
        preregistration,
        generator_seed="worker-integration-seed",
        generator_nonce="worker-integration-nonce",
    )[0]
    current_commit = (
        gwip._git_bytes(["rev-parse", "HEAD"]).decode("ascii").strip()
    )

    with gwip.sealed_candidate_source(current_commit) as (
        candidate_root,
        candidate_tree,
    ):
        result = gwip.run_candidate_episode_worker(
            mechanic=mechanic,
            episode_index=0,
            candidate_root=candidate_root,
            candidate_tree_before=candidate_tree,
            lease_entry=lease_entry,
            policy_memory=None,
            environment_seed=0,
            policy_seed=gwip.CANDIDATE_POLICY_SEED,
            step_budget=20,
            expected_worker_sha256=hashlib.sha256(
                gwip.WORKER.read_bytes()
            ).hexdigest(),
            timeout_seconds=60,
        )

    assert result["parent_run_lease"]["passed"] is True
    assert result["parent_run_lease"]["single_use_replay_reason"] == (
        "run_lease_replay"
    )
    assert result["trace_cross_check"]["passed"] is True
    assert gwip._independent_contract_replay(result["trace"]) is True
    transcript = {
        "authorizations": result["operational_authority"],
        "finish": result["trace"]["authority_finish"],
    }
    assert result["parent_run_lease"]["authority_transcript_sha256"] == (
        gwip.canonical_digest(transcript)
    )
    trusted_records = gwip._trusted_parent_source_records(candidate_tree)
    assert result["parent_run_lease"]["trusted_parent_source_sha256"] == (
        gwip.canonical_digest(trusted_records)
    )
    forged_trace = copy.deepcopy(result["trace"])
    forged_trace["cycle_receipt"]["events"][0]["state_patch"]["set"][
        "status"
    ] = "completed"
    assert gwip._independent_contract_replay(forged_trace) is False
    assert result["structural_verification"][
        "authority_independently_verified"
    ] is False
    assert result["isolation"]["kind"] == (
        "python_audit_guard_not_os_sandbox"
    )
    assert result["module_closure"]["passed"] is True
    assert {
        "boundary_config_path",
        "lease_document",
        "live_context",
    }.isdisjoint(gwip._WORKER_REQUEST_FIELDS)


def test_candidate_worker_rejects_wrong_evaluator_source_before_any_lease_use() -> None:
    preregistration, _ = gwip.load_preregistration()
    mechanic = gwip.generate_hidden_mechanics(
        preregistration,
        generator_seed="worker-binding-seed",
        generator_nonce="worker-binding-nonce",
    )[0]
    with pytest.raises(
        gwip.EvaluationContractError,
        match="worker source binding",
    ):
        gwip.run_candidate_episode_worker(
            mechanic=mechanic,
            episode_index=0,
            candidate_root=REPO,
            candidate_tree_before={},
            lease_entry={},
            policy_memory=None,
            environment_seed=0,
            policy_seed=gwip.CANDIDATE_POLICY_SEED,
            step_budget=20,
            expected_worker_sha256="0" * 64,
        )


def test_attempt_claim_is_explicitly_local_not_global_one_shot() -> None:
    payload = gwip._expected_attempt_payload(
        seed_manifest_binding={
            "commit": "1" * 40,
            "raw_sha256": "2" * 64,
        },
        source_binding={
            "candidate": {"source_digest": "3" * 64},
            "evaluator": {"source_digest": "4" * 64},
        },
        run_lease_plan_binding={"raw_sha256": "5" * 64},
    )
    assert payload["designated_local_attempt_claimed"] is True
    assert "one_shot_claimed" not in payload


def _minimal_raw_candidate_episode() -> dict:
    return {
        "scoring": {
            "policy": "candidate",
            "mechanic_index": 0,
            "episode_index": 0,
            "random_seed": None,
            "initial_observation": {"state_ref": "s_start", "terminal": False},
            "steps": [],
            "stop_reason": "fixture_stop",
            "success": False,
        },
        "trace": {
            "semantic_trace_digest": "c" * 64,
            "semantic_trace": {
                "goal": {"contract_id": "goal_opaque"},
                "steps": [
                    {
                        "step_index": 0,
                        "pre_observation": {
                            "state_ref": "s_start",
                            "terminal": False,
                        },
                        "valid_actions": [
                            {"action_id": "a_left", "payload": {}},
                            {"action_id": "a_right", "payload": {}},
                        ],
                        "selected_action": "a_right",
                        "authorization": {
                            "reason": "run_lease_action_authorized"
                        },
                        "post_observation": {
                            "state_ref": "s_goal",
                            "terminal": True,
                        },
                        "learned_edge_ref": "edge_opaque",
                        "world_snapshot": {"contract_id": "world_opaque"},
                        "proposal": {"proposal_id": "proposal_opaque"},
                        "decision_receipt": {
                            "contract_id": "decision_opaque"
                        },
                    }
                ],
            },
        },
        "operational_authority": [
            {"witness_id": "authorization_" + "a" * 32}
        ],
    }


def _derived_green() -> dict:
    metrics = {
        "candidate": gwip.PolicyAggregate(
            (0.8,) * 48, 0.8, 0.9, 144
        ).to_dict(),
        "reactive": gwip.PolicyAggregate(
            (0.4,) * 48, 0.4, 0.8, 144
        ).to_dict(),
        "random": gwip.PolicyAggregate(
            (0.5,) * 48, 0.5, 0.85, 144
        ).to_dict(),
    }
    return {
        "hard_gates": {name: True for name in gwip.REQUIRED_HARD_GATES},
        "hard_gates_passed": True,
        "derived": {
            "policy_metrics": metrics,
            "efficiency_gate": {"passed": True, "comparisons": {}},
        },
        "verdict": "MECHANISM_GREEN",
        "capability_claim": False,
        "public_benchmark_claim": False,
        "production_activation_authorized": False,
    }


def test_receipt_is_rebuilt_from_raw_and_resealed_aggregate_is_rejected(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    prereg, prereg_digest = gwip.load_preregistration()
    mechanics = gwip.generate_hidden_mechanics(
        prereg,
        generator_seed="fixture-seed",
        generator_nonce="fixture-nonce",
    )
    raw = {
        "candidate_episodes": [_minimal_raw_candidate_episode()],
        "preregistration_binding": {"raw_sha256": prereg_digest},
        "seed_manifest_binding": {},
        "source_binding": {},
        "cohort_binding": {},
    }
    monkeypatch.setattr(
        gwip,
        "verify_raw_evidence",
        lambda *_args, **_kwargs: _derived_green(),
    )
    arguments = {
        "raw_evidence": raw,
        "raw_evidence_sha256": "f" * 64,
        "preregistration": prereg,
        "preregistration_digest": prereg_digest,
        "seed_manifest_binding": {},
        "source_binding": {},
        "run_lease_plan_binding": {},
        "run_lease_entries": [],
        "mechanics": mechanics,
        "candidate_root": REPO,
        "attempt_binding": {},
    }
    receipt = gwip.build_one_shot_receipt(**arguments)
    assert receipt["verdict"] == "MECHANISM_GREEN"
    assert receipt["checksum_sha256"] == gwip.receipt_checksum(receipt)
    assert gwip.verify_one_shot_receipt(receipt, **arguments)["valid"] is True

    forged = copy.deepcopy(receipt)
    forged["policy_metrics"]["candidate"]["mean_swae"] = 1.0
    forged["checksum_sha256"] = gwip.receipt_checksum(forged)
    verified = gwip.verify_one_shot_receipt(forged, **arguments)
    assert verified["valid"] is False
    assert "raw-evidence recomputation" in verified["findings"][0]

    destination = tmp_path / "receipt.json"
    gwip.write_once_json(destination, receipt)
    with pytest.raises(FileExistsError):
        gwip.write_once_json(destination, receipt)


def test_raw_evidence_rejects_caller_aggregate_before_scoring() -> None:
    prereg, prereg_digest = gwip.load_preregistration()
    mechanics = gwip.generate_hidden_mechanics(
        prereg,
        generator_seed="fixture-seed",
        generator_nonce="fixture-nonce",
    )
    raw = {
        "schema_version": gwip.RAW_EVIDENCE_SCHEMA,
        "preregistration_binding": {
            "path": "data/eval/gwip_mechanism_prereg_v1.json",
            "raw_sha256": prereg_digest,
        },
        "seed_manifest_binding": {},
        "source_binding": {},
        "run_lease_plan_binding": {},
        "cohort_binding": {
            "private_cohort_sha256": gwip.private_cohort_digest(mechanics),
            "mechanic_count": 48,
            "candidate_episode_count": 144,
        },
        "attempt_binding": {},
        "execution_order": [],
        "candidate_episodes": [],
        "reactive_episodes": [],
        "random_episodes": [],
        "source_audit": {},
        "aggregate_metrics": {"candidate_mean_swae": 1.0},
        "verdict": None,
    }
    with pytest.raises(
        gwip.EvaluationContractError,
        match="independent binding",
    ):
        gwip.verify_raw_evidence(
            raw,
            preregistration=prereg,
            preregistration_digest=prereg_digest,
            seed_manifest_binding={},
            source_binding={},
            run_lease_plan_binding={},
            run_lease_entries=[],
            mechanics=mechanics,
            candidate_root=REPO,
            attempt_binding={},
        )


def test_candidate_public_type_resolution_is_isolated_behind_one_adapter() -> None:
    class Loop:
        pass

    class Policy:
        pass

    class Module:
        GenericWorldInteractionLoop = Loop

    class OrganModule:
        AtanorInteractivePolicy = Policy

    def importer(name: str):
        if name == "packages.fusion_loop.interactive":
            return Module
        if name == "packages.fusion_loop.interactive_organs":
            return OrganModule
        raise AssertionError(name)

    resolved = gwip.resolve_candidate_public_types(importer=importer)
    assert resolved.loop_type is Loop
    assert resolved.policy_type is Policy


def test_cli_exposes_validation_only_before_post_candidate_manifest() -> None:
    assert gwip.main(["validate-prereg"]) == 0
    with pytest.raises(SystemExit):
        gwip.main(["run"])
