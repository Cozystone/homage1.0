from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts import baseline_suite as baseline  # noqa: E402


def test_checked_in_smoke_catalog_is_bounded_and_never_declares_store_tree() -> None:
    catalog_path = (
        REPO_ROOT
        / "data"
        / "eval"
        / "catalog"
        / "baseline_suite_v1.json"
    )
    catalog, _, _ = baseline.load_catalog(catalog_path, REPO_ROOT)
    profile = baseline.validate_profile(catalog, "smoke", REPO_ROOT)

    assert profile["worst_case_seconds"] == baseline.MAX_SMOKE_SECONDS == 120
    assert profile["environment"]["ATANOR_DISABLE_PACK"] == "1"
    assert profile["environment"]["ATANOR_NETWORK_DISABLED"] == "1"
    by_id = {recipe["id"]: recipe for recipe in profile["recipes"]}
    assert set(by_id) == {
        "g0_fail_closed_integrity",
        "g0_architecture_registry",
        "g0_signed_shipped_graph_authority",
    }
    assert {
        recipe_id: recipe["timeout_seconds"]
        for recipe_id, recipe in by_id.items()
    } == {
        "g0_fail_closed_integrity": 20,
        "g0_architecture_registry": 10,
        "g0_signed_shipped_graph_authority": 30,
    }
    for recipe in profile["recipes"]:
        assert recipe["repeat"] >= 2
        assert "-qq" in recipe["command"]
        assert "-q" not in recipe["command"]
    canonical = "data/graph_scale/kg_triples"
    for recipe in profile["recipes"]:
        for group in ("suite_paths", "dataset_paths", "artifact_paths"):
            for path in recipe[group]:
                assert path != canonical and not path.startswith(canonical + "/")
                assert (REPO_ROOT / path).is_file()
    authority = by_id["g0_signed_shipped_graph_authority"]
    required_suites = {
        "packages/graph_scale/tests/test_graph_paths.py",
        "packages/graph_scale/tests/test_mutation_batch.py",
        "scripts/tests/test_create_graph_mutation_batch.py",
        "scripts/tests/test_graph_mutation_candidate.py",
        "scripts/tests/test_legacy_graph_writers_fail_closed.py",
        "scripts/tests/test_promotion_swap_boundary.py",
        "apps/api/tests/test_browser_forget_authority.py",
        "apps/api/tests/test_agora_graph_lifecycle_language.py",
        "apps/api/tests/test_cloud_brain_live_mutation_boundaries.py",
    }
    assert required_suites.issubset(authority["suite_paths"])
    assert required_suites.issubset(authority["command"])
    assert {
        "packages/cognitive_core/canonical.py",
        "packages/graph_scale/graph_paths.py",
        "packages/graph_scale/mutation_batch.py",
        "scripts/create_graph_mutation_batch.py",
    }.issubset(authority["artifact_paths"])
    reasoning = baseline.validate_profile(
        catalog,
        "reasoning_control",
        REPO_ROOT,
    )
    assert reasoning["worst_case_seconds"] == 10
    assert reasoning["recipes"][0]["repeat"] >= 2
    assert "-qq" in reasoning["recipes"][0]["command"]
    assert "-q" not in reasoning["recipes"][0]["command"]
    spine = baseline.validate_profile(
        catalog,
        "cognitive_spine_control",
        REPO_ROOT,
    )
    assert spine["worst_case_seconds"] == 40
    assert spine["environment"]["ATANOR_COGNITIVE_SHADOW"] == "0"
    assert spine["environment"]["ATANOR_CONTINUOUS_SELF_CYCLE_SHADOW"] == "0"
    assert spine["recipes"][0]["repeat"] >= 2
    assert "-qq" in spine["recipes"][0]["command"]
    assert "-q" not in spine["recipes"][0]["command"]
    assert {
        "packages/cognitive_core/cycle.py",
        "packages/cognitive_core/cycle_ledger.py",
        "packages/cognitive_core/replay.py",
        "packages/cognitive_core/chat_shadow.py",
        "packages/cognitive_core/continuous_self_shadow.py",
        "packages/continuous_self/loop.py",
        "packages/continuous_self/self_state.py",
        "apps/api/app/routers/dual_brain.py",
        "apps/api/app/routers/continuous_self.py",
    }.issubset(spine["recipes"][0]["artifact_paths"])
    world4d = baseline.validate_profile(
        catalog,
        "world4d_shadow_control",
        REPO_ROOT,
    )
    assert world4d["worst_case_seconds"] == 20
    assert world4d["environment"]["ATANOR_WORLD4D_SHADOW"] == "0"
    assert world4d["recipes"][0]["repeat"] >= 2
    assert "-qq" in world4d["recipes"][0]["command"]
    assert "-q" not in world4d["recipes"][0]["command"]
    assert {
        "data/temporal_reasoning/precedence_field.json",
        "packages/world4d/contracts.py",
        "packages/world4d/provider.py",
        "packages/world4d/block_universe_provider.py",
        "packages/world4d/shadow.py",
        "packages/cgsr/cgsr/response_workspace.py",
    }.issubset(world4d["recipes"][0]["artifact_paths"])


def _git(repo: Path, *args: str) -> None:
    subprocess.run(
        ["git", *args],
        cwd=repo,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=True,
        timeout=10,
    )


def _make_repo(tmp_path: Path, *, mode: str = "success") -> tuple[Path, Path]:
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "dataset.json").write_text('{"value":1}\n', encoding="utf-8")
    if mode == "success":
        script = (
            "from pathlib import Path\n"
            "import json, sys\n"
            "Path(sys.argv[1]).write_text(json.dumps({'score': 1}, sort_keys=True), encoding='utf-8')\n"
            "print('stable-output')\n"
        )
    elif mode == "timeout":
        script = "import time\ntime.sleep(5)\n"
    elif mode == "failure":
        script = "import sys\nprint('failed-diagnostic')\nsys.exit(3)\n"
    elif mode == "mutation":
        script = (
            "from pathlib import Path\n"
            "import sys\n"
            "Path('dataset.json').write_text('{\"value\":2}\\n', encoding='utf-8')\n"
            "Path(sys.argv[1]).write_text('{}', encoding='utf-8')\n"
        )
    elif mode == "output_flood":
        script = (
            "import sys\n"
            f"sys.stdout.buffer.write(b'x' * ({baseline.MAX_STREAM_CAPTURE_BYTES} + 131072))\n"
            "sys.stdout.buffer.flush()\n"
        )
    else:
        raise AssertionError(mode)
    (repo / "probe.py").write_text(script, encoding="utf-8")
    _git(repo, "init", "-q")
    _git(repo, "config", "user.email", "baseline@example.invalid")
    _git(repo, "config", "user.name", "Baseline Test")
    _git(repo, "add", "dataset.json", "probe.py")
    _git(repo, "commit", "-q", "-m", "fixture")
    catalog = repo / "catalog.json"
    catalog.write_text(
        json.dumps(
            {
                "schema": baseline.CATALOG_SCHEMA,
                "catalog_id": "test-catalog",
                "profiles": {
                    "smoke": {
                        "max_total_seconds": 4,
                        "env_allowlist": [
                            "ATANOR_DISABLE_PACK",
                            "ATANOR_NETWORK_DISABLED",
                            "PYTHONHASHSEED",
                        ],
                        "environment": {
                            "ATANOR_DISABLE_PACK": "1",
                            "ATANOR_NETWORK_DISABLED": "1",
                            "PYTHONHASHSEED": "0",
                        },
                        "recipes": [
                            {
                                "id": "probe",
                                "network_required": False,
                                "command": ["{python}", "probe.py", "{run_dir}/result.json"],
                                "cwd": ".",
                                "timeout_seconds": 1,
                                "repeat": 2,
                                "suite_paths": ["probe.py"],
                                "dataset_paths": ["dataset.json"],
                                "artifact_paths": ["probe.py"],
                                "mutation_sensitive_paths": ["dataset.json"],
                                "report_paths": ["result.json"],
                            }
                        ],
                    }
                },
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    _git(repo, "add", "catalog.json")
    _git(repo, "commit", "-q", "-m", "catalog")
    return repo, catalog


def test_success_manifest_is_digest_only_reproduced_and_verifiable(tmp_path: Path) -> None:
    repo, catalog = _make_repo(tmp_path)
    output = tmp_path / "evidence.json"

    manifest, written = baseline.run_suite(
        profile_name="smoke",
        catalog_path=catalog,
        repo_root=repo,
        output_path=output,
    )

    assert written == output
    assert manifest["source"]["sealed"] is True
    assert manifest["successful"] is True
    assert manifest["successful_reproduced"] is True
    assert manifest["evidence_kind"] == "command_execution_only"
    assert manifest["source"]["runner"]["implementation"] == "scripts.baseline_suite"
    assert len(manifest["source"]["runner"]["sha256"]) == 64
    assert manifest["source"]["runner_mutation_detected"] is False
    assert manifest["inputs"]["suites"][0]["sha256"]
    assert manifest["inputs"]["datasets"][0]["sha256"]
    assert manifest["inputs"]["artifacts"][0]["sha256"]
    assert manifest["inputs"]["dependencies"] == []
    assert manifest["network_control"]["enforced"] is False
    assert manifest["network_control"]["mechanism"] == "cooperative_environment_flag_only"
    assert manifest["environment"]["values"]["ATANOR_DISABLE_PACK"] == "1"
    assert manifest["filesystem_control"]["enforced"] is False
    assert manifest["filesystem_control"]["mechanism"] == "catalog_policy_plus_post_hoc_observation"
    assert manifest["platform"]["hardware"]["logical_cpu_count"]
    assert manifest["platform"]["python_environment"]["executable"]["sha256"]
    assert (
        manifest["platform"]["python_environment"]["installed_distributions"]["entry_count"]
        > 0
    )
    assert manifest["platform"]["python_environment_mutation_detected"] is False
    attempts = manifest["recipes"][0]["attempts"]
    assert len(attempts) == 2
    assert all(attempt["exit_code"] == 0 for attempt in attempts)
    assert all(attempt["stdout"]["sha256"] for attempt in attempts)
    assert all(attempt["stderr"]["sha256"] for attempt in attempts)
    assert all(attempt["reports"][0]["sha256"] for attempt in attempts)
    assert manifest["recipes"][0]["repeat_metrics"]["benchmark_metrics"]["accuracy"] is None
    assert manifest["mutation_sensitive"]["before"] == manifest["mutation_sensitive"]["after"]
    assert baseline.compute_manifest_hash(manifest) == manifest["manifest_hash"]

    serialized = output.read_text(encoding="utf-8")
    assert "stable-output" not in serialized
    assert baseline.verify_manifest(output, repo_root=repo)["valid"] is True


def test_dirty_and_untracked_state_is_digested_without_contents(tmp_path: Path) -> None:
    repo, catalog = _make_repo(tmp_path)
    secret_text = "DO-NOT-COPY-THIS-SECRET-CONTENT"
    (repo / "private-token.txt").write_text(secret_text, encoding="utf-8")
    output = tmp_path / "dirty-evidence.json"

    manifest, _ = baseline.run_suite(
        profile_name="smoke",
        catalog_path=catalog,
        repo_root=repo,
        output_path=output,
    )

    assert manifest["source"]["sealed"] is False
    assert manifest["source"]["git"]["untracked_paths"]["entry_count"] == 1
    assert len(manifest["source"]["git"]["untracked_paths"]["sha256"]) == 64
    assert len(manifest["source"]["git"]["untracked_paths"]["content_sha256"]) == 64
    serialized = output.read_text(encoding="utf-8")
    assert secret_text not in serialized
    assert "private-token.txt" not in serialized


def test_untracked_content_change_is_detected_without_recording_secret(tmp_path: Path) -> None:
    repo, _ = _make_repo(tmp_path)
    secret = repo / "private-token.txt"
    secret.write_text("first secret", encoding="utf-8")
    before = baseline.collect_git_state(repo)
    secret.write_text("second secret", encoding="utf-8")
    after = baseline.collect_git_state(repo)

    assert before["untracked_paths"]["sha256"] == after["untracked_paths"]["sha256"]
    assert before["untracked_paths"]["content_sha256"] != after["untracked_paths"]["content_sha256"]
    assert baseline._same_git_fingerprint(before, after) is False
    assert "second secret" not in json.dumps(after)


def test_untracked_path_to_content_binding_detects_content_swaps(tmp_path: Path) -> None:
    repo, _ = _make_repo(tmp_path)
    left = repo / "left.private"
    right = repo / "right.private"
    left.write_text("alpha", encoding="utf-8")
    right.write_text("beta", encoding="utf-8")
    before = baseline.collect_git_state(repo)
    left.write_text("beta", encoding="utf-8")
    right.write_text("alpha", encoding="utf-8")
    after = baseline.collect_git_state(repo)

    assert before["untracked_paths"]["sha256"] == after["untracked_paths"]["sha256"]
    assert (
        before["untracked_paths"]["content_only_sha256"]
        == after["untracked_paths"]["content_only_sha256"]
    )
    assert before["untracked_paths"]["content_sha256"] != after["untracked_paths"]["content_sha256"]
    assert baseline._same_git_fingerprint(before, after) is False


def test_runner_source_is_bound_automatically_and_verified(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo, catalog = _make_repo(tmp_path)
    runner = repo / "runner_impl.py"
    runner.write_text("# baseline runner fixture v1\n", encoding="utf-8")
    _git(repo, "add", "runner_impl.py")
    _git(repo, "commit", "-q", "-m", "runner")
    monkeypatch.setattr(baseline, "RUNNER_SOURCE", runner)
    output = tmp_path / "runner-bound.json"

    manifest, _ = baseline.run_suite(
        profile_name="smoke",
        catalog_path=catalog,
        repo_root=repo,
        output_path=output,
    )

    assert manifest["source"]["runner"]["path"] == "runner_impl.py"
    assert manifest["source"]["runner"]["location"] == "repository"
    assert "runner_impl.py" not in catalog.read_text(encoding="utf-8")
    assert baseline.verify_manifest(output, repo_root=repo)["runner_source_matches"] is True

    runner.write_text("# baseline runner fixture v2\n", encoding="utf-8")
    result = baseline.verify_manifest(output, repo_root=repo)
    assert result["valid"] is False
    assert result["runner_source_matches"] is False
    assert "runner_source_mismatch" in result["errors"]


@pytest.mark.parametrize("mode", ["timeout", "failure"])
def test_repeated_timeout_or_failure_is_never_reproduced(tmp_path: Path, mode: str) -> None:
    repo, catalog = _make_repo(tmp_path, mode=mode)
    output = tmp_path / f"{mode}.json"

    manifest, _ = baseline.run_suite(
        profile_name="smoke",
        catalog_path=catalog,
        repo_root=repo,
        output_path=output,
    )

    repeat = manifest["recipes"][0]["repeat_metrics"]
    assert manifest["successful"] is False
    assert manifest["successful_reproduced"] is False
    assert repeat["successful_reproduced"] is False
    assert repeat["failed_attempts"] == 2
    if mode == "timeout":
        assert repeat["timeouts"] == 2
    else:
        assert all(attempt["exit_code"] == 3 for attempt in manifest["recipes"][0]["attempts"])


def test_output_capture_is_bounded_and_overflow_can_never_be_success(tmp_path: Path) -> None:
    repo, catalog = _make_repo(tmp_path, mode="output_flood")
    output = tmp_path / "output-flood.json"

    manifest, _ = baseline.run_suite(
        profile_name="smoke",
        catalog_path=catalog,
        repo_root=repo,
        output_path=output,
    )

    attempts = manifest["recipes"][0]["attempts"]
    assert manifest["successful"] is False
    assert manifest["successful_reproduced"] is False
    assert all(attempt["output_limit_exceeded"] is True for attempt in attempts)
    assert all(attempt["successful"] is False for attempt in attempts)
    assert all(attempt["stdout"]["truncated"] is True for attempt in attempts)
    assert all(
        attempt["stdout"]["bytes"] == baseline.MAX_STREAM_CAPTURE_BYTES
        for attempt in attempts
    )
    assert (
        manifest["recipes"][0]["repeat_metrics"]["output_limit_exceeded_attempts"]
        == 2
    )


def test_repository_mutation_is_measured_and_invalidates_success(tmp_path: Path) -> None:
    repo, catalog = _make_repo(tmp_path, mode="mutation")
    output = tmp_path / "mutation.json"

    manifest, _ = baseline.run_suite(
        profile_name="smoke",
        catalog_path=catalog,
        repo_root=repo,
        output_path=output,
    )

    assert manifest["mutation_sensitive"]["observed_path_mutation_detected"] is True
    assert manifest["source"]["repository_mutation_detected"] is True
    assert manifest["source"]["sealed"] is False
    assert manifest["successful"] is False
    assert manifest["successful_reproduced"] is False
    assert manifest["mutation_sensitive"]["before"] != manifest["mutation_sensitive"]["after"]


def test_ignored_declared_input_mutation_is_observed_automatically(tmp_path: Path) -> None:
    repo, catalog = _make_repo(tmp_path)
    ignored_dir = repo / "ignored-cache"
    ignored_dir.mkdir()
    ignored_input = ignored_dir / "state.bin"
    ignored_input.write_bytes(b"before")
    (repo / ".gitignore").write_text("ignored-cache/\n", encoding="utf-8")
    (repo / "probe.py").write_text(
        "from pathlib import Path\n"
        "import json, sys\n"
        "Path('ignored-cache/state.bin').write_bytes(b'after')\n"
        "Path(sys.argv[1]).write_text(json.dumps({'score': 1}), encoding='utf-8')\n",
        encoding="utf-8",
    )
    payload = json.loads(catalog.read_text(encoding="utf-8"))
    payload["profiles"]["smoke"]["recipes"][0]["artifact_paths"].append(
        "ignored-cache/state.bin"
    )
    catalog.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    _git(repo, "add", ".gitignore", "probe.py", "catalog.json")
    _git(repo, "commit", "-q", "-m", "ignored declared input")
    output = tmp_path / "ignored-mutation.json"

    manifest, _ = baseline.run_suite(
        profile_name="smoke",
        catalog_path=catalog,
        repo_root=repo,
        output_path=output,
    )

    assert manifest["source"]["repository_mutation_detected"] is False
    assert manifest["mutation_sensitive"]["observed_path_mutation_detected"] is True
    assert "ignored-cache/state.bin" in manifest["mutation_sensitive"]["automatic_input_paths"]
    assert manifest["successful"] is False
    assert "ignored paths outside these surfaces are not observed" in (
        manifest["mutation_sensitive"]["observation_scope"]
    )


def test_existing_evidence_is_never_overwritten(tmp_path: Path) -> None:
    repo, catalog = _make_repo(tmp_path)
    output = tmp_path / "existing.json"
    output.write_text("operator-owned\n", encoding="utf-8")

    with pytest.raises(baseline.BaselineError, match="refusing overwrite"):
        baseline.run_suite(
            profile_name="smoke",
            catalog_path=catalog,
            repo_root=repo,
            output_path=output,
        )

    assert output.read_text(encoding="utf-8") == "operator-owned\n"


def test_in_repo_evidence_output_is_excluded_exactly_and_remains_verifiable(tmp_path: Path) -> None:
    repo, catalog = _make_repo(tmp_path)
    output = repo / "reports" / "baseline-evidence.json"

    manifest, _ = baseline.run_suite(
        profile_name="smoke",
        catalog_path=catalog,
        repo_root=repo,
        output_path=output,
    )

    assert manifest["source"]["excluded_evidence_output"] == "reports/baseline-evidence.json"
    assert manifest["source"]["sealed"] is True
    assert output.is_file()
    assert baseline.verify_manifest(output, repo_root=repo)["valid"] is True


def test_tracked_evidence_output_path_cannot_be_hidden_from_source_state(tmp_path: Path) -> None:
    repo, catalog = _make_repo(tmp_path)
    output = repo / "tracked-evidence.json"
    output.write_text("old tracked evidence\n", encoding="utf-8")
    _git(repo, "add", "tracked-evidence.json")
    _git(repo, "commit", "-q", "-m", "tracked evidence")
    output.unlink()

    with pytest.raises(baseline.BaselineError, match="tracked repository path"):
        baseline.run_suite(
            profile_name="smoke",
            catalog_path=catalog,
            repo_root=repo,
            output_path=output,
        )


def test_verify_detects_manifest_tamper_and_source_change(tmp_path: Path) -> None:
    repo, catalog = _make_repo(tmp_path)
    output = tmp_path / "evidence.json"
    baseline.run_suite(profile_name="smoke", catalog_path=catalog, repo_root=repo, output_path=output)

    (repo / "dataset.json").write_text('{"value":9}\n', encoding="utf-8")
    source_result = baseline.verify_manifest(output, repo_root=repo)
    assert source_result["valid"] is False
    assert source_result["source_matches"] is False
    assert "datasets_mismatch" in source_result["errors"]

    payload = json.loads(output.read_text(encoding="utf-8"))
    payload["successful"] = False
    tampered = tmp_path / "tampered.json"
    tampered.write_text(json.dumps(payload), encoding="utf-8")
    tamper_result = baseline.verify_manifest(tampered, repo_root=repo)
    assert tamper_result["manifest_hash_valid"] is False
    assert "manifest_hash_mismatch" in tamper_result["errors"]

    dishonest = json.loads(output.read_text(encoding="utf-8"))
    dishonest["recipes"][0]["attempts"][0]["timed_out"] = True
    dishonest["recipes"][0]["attempts"][0]["successful"] = True
    dishonest["manifest_hash"] = baseline.compute_manifest_hash(dishonest)
    dishonest_path = tmp_path / "dishonest.json"
    dishonest_path.write_text(json.dumps(dishonest), encoding="utf-8")
    dishonest_result = baseline.verify_manifest(dishonest_path, repo_root=repo)
    assert dishonest_result["execution_semantics_valid"] is False
    assert "execution_semantics_invalid" in dishonest_result["errors"]

    wrong_kind = json.loads(output.read_text(encoding="utf-8"))
    wrong_kind["evidence_kind"] = "benchmark_capability"
    wrong_kind["manifest_hash"] = baseline.compute_manifest_hash(wrong_kind)
    wrong_kind_path = tmp_path / "wrong-kind.json"
    wrong_kind_path.write_text(json.dumps(wrong_kind), encoding="utf-8")
    wrong_kind_result = baseline.verify_manifest(wrong_kind_path, repo_root=repo)
    assert wrong_kind_result["execution_semantics_valid"] is False
    assert "execution_semantics_invalid" in wrong_kind_result["errors"]


def test_catalog_rejects_network_escape_inline_python_and_unbounded_smoke(tmp_path: Path) -> None:
    repo, catalog = _make_repo(tmp_path)
    base = json.loads(catalog.read_text(encoding="utf-8"))
    for index in range(6):
        candidate = json.loads(json.dumps(base))
        candidate_recipe = candidate["profiles"]["smoke"]["recipes"][0]
        if index == 0:
            candidate_recipe["network_required"] = True
        elif index == 1:
            candidate_recipe["cwd"] = ".."
        elif index == 2:
            candidate_recipe["command"] = ["{python}", "-c", "print(1)"]
        elif index == 3:
            candidate["profiles"]["smoke"]["max_total_seconds"] = 121
        elif index == 4:
            candidate["profiles"]["smoke"]["env_allowlist"] = ["OPENAI_API_KEY"]
        else:
            candidate_recipe["command"] = ["{python}", "../outside.py"]
        bad_catalog = repo / f"bad-{index}.json"
        bad_catalog.write_text(json.dumps(candidate), encoding="utf-8")
        parsed, _, _ = baseline.load_catalog(bad_catalog, repo)
        with pytest.raises(baseline.BaselineError):
            baseline.validate_profile(parsed, "smoke", repo)


def test_world_pack_warmer_is_forced_off_in_bounded_children(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo, catalog = _make_repo(tmp_path)
    parsed, _, _ = baseline.load_catalog(catalog, repo)
    profile = baseline.validate_profile(parsed, "smoke", repo)
    monkeypatch.setenv("ATANOR_DISABLE_PACK", "0")

    child = baseline._child_environment(profile)

    assert child["ATANOR_DISABLE_PACK"] == "1"
    profile["environment"]["ATANOR_DISABLE_PACK"] = "0"
    with pytest.raises(
        baseline.BaselineError,
        match="cannot enable the asynchronous world-pack warmer",
    ):
        baseline.validate_profile(
            {
                "profiles": {
                    "smoke": profile,
                }
            },
            "smoke",
            repo,
        )


def test_child_environment_preserves_python_launch_roots_without_recording_them(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo, catalog = _make_repo(tmp_path)
    parsed, _, _ = baseline.load_catalog(catalog, repo)
    profile = baseline.validate_profile(parsed, "smoke", repo)
    monkeypatch.setenv("APPDATA", str(tmp_path / "appdata"))
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "localappdata"))
    monkeypatch.setenv("ATANOR_TEST_SECRET", "must-not-cross")

    child = baseline._child_environment(profile)
    recorded = baseline._recorded_environment(profile, child)

    assert child["APPDATA"] == str(tmp_path / "appdata")
    assert child["LOCALAPPDATA"] == str(tmp_path / "localappdata")
    assert "ATANOR_TEST_SECRET" not in child
    assert "APPDATA" not in recorded["values"]
    assert "LOCALAPPDATA" not in recorded["values"]


def test_catalog_rejects_symlink_execution_target_and_cwd(tmp_path: Path) -> None:
    repo, catalog = _make_repo(tmp_path)
    outside_script = tmp_path / "outside_probe.py"
    outside_script.write_text("print('outside')\n", encoding="utf-8")
    outside_dir = tmp_path / "outside-dir"
    outside_dir.mkdir()
    try:
        (repo / "linked_probe.py").symlink_to(outside_script)
        (repo / "linked_cwd").symlink_to(outside_dir, target_is_directory=True)
    except (NotImplementedError, OSError) as exc:
        pytest.skip(f"symlink creation unavailable: {type(exc).__name__}")

    base = json.loads(catalog.read_text(encoding="utf-8"))
    linked_entry = json.loads(json.dumps(base))
    linked_entry["profiles"]["smoke"]["recipes"][0]["command"][1] = "linked_probe.py"
    entry_catalog = repo / "linked-entry-catalog.json"
    entry_catalog.write_text(json.dumps(linked_entry), encoding="utf-8")
    parsed_entry, _, _ = baseline.load_catalog(entry_catalog, repo)
    with pytest.raises(baseline.BaselineError, match="symlink or reparse"):
        baseline.validate_profile(parsed_entry, "smoke", repo)

    linked_cwd = json.loads(json.dumps(base))
    linked_cwd["profiles"]["smoke"]["recipes"][0]["cwd"] = "linked_cwd"
    cwd_catalog = repo / "linked-cwd-catalog.json"
    cwd_catalog.write_text(json.dumps(linked_cwd), encoding="utf-8")
    parsed_cwd, _, _ = baseline.load_catalog(cwd_catalog, repo)
    with pytest.raises(baseline.BaselineError, match="symlink or reparse"):
        baseline.validate_profile(parsed_cwd, "smoke", repo)


def test_execution_path_reparse_detection_fails_closed_without_os_link_privilege(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo, catalog = _make_repo(tmp_path)
    base = json.loads(catalog.read_text(encoding="utf-8"))
    candidate = json.loads(json.dumps(base))
    candidate["profiles"]["smoke"]["recipes"][0]["command"][1] = "probe.py"
    candidate_catalog = repo / "simulated-reparse-catalog.json"
    candidate_catalog.write_text(json.dumps(candidate), encoding="utf-8")
    parsed, _, _ = baseline.load_catalog(candidate_catalog, repo)
    real_detector = baseline._is_link_or_reparse

    def simulated_detector(path: Path) -> bool:
        return path.name == "probe.py" or real_detector(path)

    monkeypatch.setattr(baseline, "_is_link_or_reparse", simulated_detector)
    with pytest.raises(baseline.BaselineError, match="symlink or reparse"):
        baseline.validate_profile(parsed, "smoke", repo)


def test_report_parent_reparse_is_rechecked_after_execution(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    run_dir = tmp_path / "run"
    report_parent = run_dir / "nested"
    report_parent.mkdir(parents=True)
    (report_parent / "result.json").write_text("{}", encoding="utf-8")
    real_detector = baseline._is_link_or_reparse

    def simulated_detector(path: Path) -> bool:
        return path.name == "nested" or real_detector(path)

    monkeypatch.setattr(baseline, "_is_link_or_reparse", simulated_detector)
    reports = baseline._hash_reports(run_dir, ["nested/result.json"])
    assert reports == [
        {
            "path": "nested/result.json",
            "exists": True,
            "regular_file": False,
            "unsafe_path": True,
            "sha256": None,
            "bytes": 0,
        }
    ]


def test_pytest_arguments_are_allowlisted_and_targets_stay_in_repo(tmp_path: Path) -> None:
    repo, catalog = _make_repo(tmp_path)
    outside_test = tmp_path / "outside_test.py"
    outside_test.write_text("def test_outside(): pass\n", encoding="utf-8")
    base = json.loads(catalog.read_text(encoding="utf-8"))

    approved = json.loads(json.dumps(base))
    approved["profiles"]["smoke"]["recipes"][0]["command"] = [
        "{python}",
        "-m",
        "pytest",
        "probe.py",
        "--import-mode=importlib",
        "--disable-warnings",
        "--maxfail=1",
        "-q",
    ]
    approved_catalog = repo / "approved-pytest.json"
    approved_catalog.write_text(json.dumps(approved), encoding="utf-8")
    parsed, _, _ = baseline.load_catalog(approved_catalog, repo)
    baseline.validate_profile(parsed, "smoke", repo)

    bad_commands = [
        ["{python}", "-m", "pytest", "probe.py", "-p", "unsafe_plugin"],
        ["{python}", "-m", "pytest", "probe.py", "--override-ini=pythonpath=.."],
        ["{python}", "-m", "pytest", "../outside_test.py", "-q"],
        ["{python}", "-m", "pytest", "-q"],
        ["{python}", "-m", "pytest", "dataset.json", "-q"],
    ]
    for index, command in enumerate(bad_commands):
        candidate = json.loads(json.dumps(base))
        candidate["profiles"]["smoke"]["recipes"][0]["command"] = command
        bad_catalog = repo / f"bad-pytest-{index}.json"
        bad_catalog.write_text(json.dumps(candidate), encoding="utf-8")
        parsed_bad, _, _ = baseline.load_catalog(bad_catalog, repo)
        with pytest.raises(baseline.BaselineError):
            baseline.validate_profile(parsed_bad, "smoke", repo)


def test_canonical_hash_is_order_independent_and_rejects_nan() -> None:
    left = {"schema": baseline.MANIFEST_SCHEMA, "b": 2, "a": [1, 3]}
    right = {"a": [1, 3], "b": 2, "schema": baseline.MANIFEST_SCHEMA}
    assert baseline.compute_manifest_hash(left) == baseline.compute_manifest_hash(right)
    with pytest.raises(baseline.BaselineError):
        baseline.canonical_json_bytes({"bad": float("nan")})
