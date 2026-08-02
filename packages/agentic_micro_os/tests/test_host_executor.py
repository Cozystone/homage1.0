from __future__ import annotations

from packages.agentic_micro_os.host_executor import HostExecutionRequest, HostExecutor, SAFE_TEST_TOKEN
from packages.agentic_micro_os.operator_confirm import FULL_HOST_CONFIRMATION_PHRASE
from packages.agentic_micro_os.permission_gate import AutonomySubSwitches, PermissionScope, gate_for_test


def _executor(tmp_path) -> HostExecutor:
    gate = gate_for_test(tmp_path)
    return HostExecutor(gate=gate, project_root=tmp_path, runtime_tmp_dir=tmp_path / "runtime" / "agentic_micro_os" / "tmp")


def test_default_denies_shell(tmp_path) -> None:
    executor = _executor(tmp_path)

    result = executor.execute(HostExecutionRequest(action_type="echo", content="hello"))

    assert result.allowed is False
    assert result.executed is False


def test_tier4_without_shell_switch_denies_shell(tmp_path) -> None:
    executor = _executor(tmp_path)
    executor.gate.enable_full_host(
        enabled_by="owner",
        typed_phrase=FULL_HOST_CONFIRMATION_PHRASE,
        duration_sec=600,
        sub_switches=AutonomySubSwitches(shell=False),
    )

    result = executor.execute(HostExecutionRequest(action_type="echo", content="hello"))

    assert result.allowed is False
    assert result.executed is False


def test_tier4_with_shell_switch_allows_echo_only(tmp_path) -> None:
    executor = _executor(tmp_path)
    executor.gate.enable_full_host(
        enabled_by="owner",
        typed_phrase=FULL_HOST_CONFIRMATION_PHRASE,
        duration_sec=600,
        sub_switches=AutonomySubSwitches(shell=True),
    )

    echo = executor.execute(HostExecutionRequest(action_type="echo", content="hello"))
    arbitrary = executor.execute(HostExecutionRequest(action_type="run_arbitrary_command", content="whoami"))

    assert echo.allowed is True
    assert echo.executed is True
    assert echo.stdout_excerpt == "hello"
    assert arbitrary.allowed is False
    assert arbitrary.executed is False


def test_temp_file_write_allowed_only_in_runtime_tmp(tmp_path) -> None:
    executor = _executor(tmp_path)

    allowed = executor.execute(
        HostExecutionRequest(
            action_type="write_temp_file",
            path="note.txt",
            content="ok",
            safe_test_token=SAFE_TEST_TOKEN,
        )
    )
    rejected = executor.execute(
        HostExecutionRequest(
            action_type="write_temp_file",
            path=str(tmp_path / "outside.txt"),
            content="bad",
            safe_test_token=SAFE_TEST_TOKEN,
        )
    )

    assert allowed.allowed is True
    assert allowed.executed is True
    assert allowed.mutation_performed is True
    assert (tmp_path / "runtime" / "agentic_micro_os" / "tmp" / "note.txt").read_text(encoding="utf-8") == "ok"
    assert rejected.allowed is False
    assert rejected.executed is False


def test_non_temp_write_delete_git_push_and_brain_writes_rejected(tmp_path) -> None:
    executor = _executor(tmp_path)

    for action in ["overwrite_non_temp_file", "delete_file", "git_commit", "git_push", "local_brain_write", "cloud_production_write"]:
        result = executor.execute(HostExecutionRequest(action_type=action, safe_test_token=SAFE_TEST_TOKEN))
        assert result.allowed is False
        assert result.executed is False


def test_emergency_stop_blocks_all_actions(tmp_path) -> None:
    executor = _executor(tmp_path)
    executor.gate.emergency_stop.trigger("stop")

    result = executor.execute(HostExecutionRequest(action_type="echo", content="hello", safe_test_token=SAFE_TEST_TOKEN))

    assert result.allowed is False
    assert result.executed is False
    assert "emergency stop" in result.denied_reason


def test_audit_log_created_for_allowed_and_denied(tmp_path) -> None:
    executor = _executor(tmp_path)

    executor.execute(HostExecutionRequest(action_type="echo", content="hello", safe_test_token=SAFE_TEST_TOKEN))
    executor.execute(HostExecutionRequest(action_type="delete_file", safe_test_token=SAFE_TEST_TOKEN))

    lines = (tmp_path / "host_audit.jsonl").read_text(encoding="utf-8").splitlines()
    assert len(lines) == 2
    assert "permission_allowed" in lines[0]
    assert "host_executor_denied" in lines[1]


def test_git_status_allowed_as_harmless_diagnostic(tmp_path) -> None:
    executor = HostExecutor(gate=gate_for_test(tmp_path), project_root=__import__("pathlib").Path.cwd(), runtime_tmp_dir=tmp_path / "tmp")

    result = executor.execute(HostExecutionRequest(action_type="git_status", safe_test_token=SAFE_TEST_TOKEN))

    assert result.allowed is True
    assert result.executed is True
    assert result.exit_code == 0


def test_read_text_file_and_list_directory_with_safe_test_token(tmp_path) -> None:
    executor = _executor(tmp_path)
    note = tmp_path / "runtime" / "agentic_micro_os" / "tmp" / "note.txt"
    note.parent.mkdir(parents=True)
    note.write_text("hello", encoding="utf-8")

    read = executor.execute(HostExecutionRequest(action_type="read_text_file", path=str(note), safe_test_token=SAFE_TEST_TOKEN))
    listed = executor.execute(HostExecutionRequest(action_type="list_directory", path=str(note.parent), safe_test_token=SAFE_TEST_TOKEN))

    assert read.allowed is True
    assert read.stdout_excerpt == "hello"
    assert listed.allowed is True
    assert "note.txt" in listed.stdout_excerpt
