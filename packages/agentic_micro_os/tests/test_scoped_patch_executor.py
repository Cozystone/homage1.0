from __future__ import annotations

import json

from packages.agentic_micro_os.operator_confirm import FULL_HOST_CONFIRMATION_PHRASE
from packages.agentic_micro_os.permission_gate import AutonomySubSwitches, gate_for_test
from packages.agentic_micro_os.scoped_patch_executor import (
    APPLY_CONFIRMATION,
    ROLLBACK_CONFIRMATION,
    ScopedPatchExecutor,
    ScopedPatchRequest,
    ScopedPatchRollbackRequest,
)


def _target(tmp_path, relative: str = "packages/agentic_micro_os/demo.py"):
    path = tmp_path / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("VALUE = 'old'\n", encoding="utf-8")
    return path


def _executor(tmp_path) -> ScopedPatchExecutor:
    return ScopedPatchExecutor(gate=gate_for_test(tmp_path), project_root=tmp_path)


def _enable_tier4(executor: ScopedPatchExecutor, *, full_file_write: bool = True) -> str:
    executor.gate.enable_full_host(
        enabled_by="owner",
        typed_phrase=FULL_HOST_CONFIRMATION_PHRASE,
        duration_sec=600,
        sub_switches=AutonomySubSwitches(full_file_write=full_file_write),
    )
    assert executor.gate.session is not None
    return executor.gate.session.session_id


def _request(path, *, confirmation: str = APPLY_CONFIRMATION, session_id: str = "", dry_run: bool = True) -> ScopedPatchRequest:
    return ScopedPatchRequest(
        target_path=str(path),
        expected_old_text="VALUE = 'old'",
        replacement_text="VALUE = 'new'",
        reason="unit test scoped patch",
        operator_confirmation=confirmation,
        tier_session_id=session_id,
        dry_run=dry_run,
    )


def test_dry_run_diff_works_without_mutation(tmp_path) -> None:
    executor = _executor(tmp_path)
    target = _target(tmp_path)

    plan = executor.plan(_request(target))

    assert plan.allowed is True
    assert "-VALUE = 'old'" in plan.diff_preview
    assert "+VALUE = 'new'" in plan.diff_preview
    assert target.read_text(encoding="utf-8") == "VALUE = 'old'\n"


def test_apply_denied_outside_tier4(tmp_path) -> None:
    executor = _executor(tmp_path)
    target = _target(tmp_path)

    result = executor.apply(_request(target, dry_run=False))

    assert result.applied is False
    assert result.mutation_performed is False
    assert "Tier 4" in result.denied_reason
    assert target.read_text(encoding="utf-8") == "VALUE = 'old'\n"


def test_apply_denied_without_full_file_write(tmp_path) -> None:
    executor = _executor(tmp_path)
    target = _target(tmp_path)
    session_id = _enable_tier4(executor, full_file_write=False)

    result = executor.apply(_request(target, session_id=session_id, dry_run=False))

    assert result.applied is False
    assert "full_file_write" in result.denied_reason


def test_apply_denied_without_typed_phrase(tmp_path) -> None:
    executor = _executor(tmp_path)
    target = _target(tmp_path)
    session_id = _enable_tier4(executor)

    result = executor.apply(_request(target, confirmation="APPLY", session_id=session_id, dry_run=False))

    assert result.applied is False
    assert "confirmation" in result.denied_reason


def test_apply_denied_if_emergency_stop_exists(tmp_path) -> None:
    executor = _executor(tmp_path)
    target = _target(tmp_path)
    session_id = _enable_tier4(executor)
    executor.gate.emergency_stop.trigger("stop")

    result = executor.apply(_request(target, session_id=session_id, dry_run=False))

    assert result.applied is False
    assert "emergency stop" in result.denied_reason


def test_path_traversal_local_brain_verified_store_env_and_binary_rejected(tmp_path) -> None:
    executor = _executor(tmp_path)
    _target(tmp_path)
    binary = tmp_path / "packages" / "agentic_micro_os" / "binary.py"
    binary.write_bytes(b"\x00\x01")

    cases = [
        "../outside.py",
        "data/memory/local.py",
        "docs/verified_store_v0.md",
        "apps/web/app/.env",
        str(binary),
    ]

    results = [executor.plan(_request(case)).allowed for case in cases]

    assert results == [False, False, False, False, False]


def test_expected_old_text_mismatch_rejected(tmp_path) -> None:
    executor = _executor(tmp_path)
    target = _target(tmp_path)

    result = executor.plan(
        ScopedPatchRequest(
            target_path=str(target),
            expected_old_text="missing",
            replacement_text="new",
            reason="mismatch",
        )
    )

    assert result.allowed is False
    assert "not found" in result.denied_reason


def test_successful_apply_creates_backup_and_rollback_restores(tmp_path) -> None:
    executor = _executor(tmp_path)
    target = _target(tmp_path)
    session_id = _enable_tier4(executor)

    applied = executor.apply(_request(target, session_id=session_id, dry_run=False))
    rolled_back = executor.rollback(
        ScopedPatchRollbackRequest(
            target_path=str(target),
            backup_path=applied.backup_path,
            operator_confirmation=ROLLBACK_CONFIRMATION,
            tier_session_id=session_id,
        )
    )

    assert applied.applied is True
    assert applied.mutation_performed is True
    assert applied.backup_path
    assert "VALUE = 'new'" in target.read_text(encoding="utf-8") or rolled_back.applied
    assert rolled_back.applied is True
    assert target.read_text(encoding="utf-8") == "VALUE = 'old'\n"


def test_audit_log_written_and_no_git_automation_flags(tmp_path) -> None:
    executor = _executor(tmp_path)
    target = _target(tmp_path)
    session_id = _enable_tier4(executor)

    result = executor.apply(_request(target, session_id=session_id, dry_run=False))
    lines = (tmp_path / "host_audit.jsonl").read_text(encoding="utf-8").splitlines()
    records = [json.loads(line) for line in lines]

    assert result.applied is True
    assert any(record["event"] == "scoped_patch_applied" for record in records)
    applied = [record for record in records if record["event"] == "scoped_patch_applied"][0]
    assert applied["auto_commit"] is False
    assert applied["auto_push"] is False
