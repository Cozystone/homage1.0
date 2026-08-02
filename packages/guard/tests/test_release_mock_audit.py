from __future__ import annotations

from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from guard.release_mock_audit import audit_mock_risks


def test_release_mock_audit_blocks_fake_counts(tmp_path: Path) -> None:
    path = tmp_path / "app.py"
    path.write_text('FAKE_GRAPH_COUNT = 1000\n', encoding="utf-8")

    report = audit_mock_risks([tmp_path], repo_root=tmp_path)

    assert report["passed"] is False
    assert report["counts"]["BLOCKER"] == 1
    assert report["risks"][0]["category"] == "release_blocker"


def test_release_mock_audit_allows_honest_local_mock_boundary(tmp_path: Path) -> None:
    path = tmp_path / "proof.py"
    path.write_text('billing_mode = "local_mock"  # proof-only local billing simulation\n', encoding="utf-8")

    report = audit_mock_risks([tmp_path], repo_root=tmp_path)

    assert report["passed"] is True
    assert report["counts"]["INFO"] == 1


def test_release_mock_audit_marks_unknown_mock_for_review(tmp_path: Path) -> None:
    path = tmp_path / "runtime.py"
    path.write_text('result = run_mock_purchase()\n', encoding="utf-8")

    report = audit_mock_risks([tmp_path], repo_root=tmp_path)

    assert report["passed"] is True
    assert report["counts"]["REVIEW"] == 1


def test_release_mock_audit_allows_honesty_false_flags(tmp_path: Path) -> None:
    path = tmp_path / "status.py"
    path.write_text('"fake_counts": False\n', encoding="utf-8")

    report = audit_mock_risks([tmp_path], repo_root=tmp_path)

    assert report["passed"] is True
    assert report["counts"]["INFO"] == 1


def test_release_mock_audit_downgrades_ui_placeholder_false_positive(tmp_path: Path) -> None:
    path = tmp_path / "page.tsx"
    path.write_text('input placeholder="Search cartridges"\n', encoding="utf-8")

    report = audit_mock_risks([tmp_path], repo_root=tmp_path)

    assert report["passed"] is True
    assert report["counts"]["INFO"] == 1


def test_release_mock_audit_downgrades_sql_placeholder_false_positive(tmp_path: Path) -> None:
    path = tmp_path / "store.py"
    path.write_text('placeholders = ",".join("?" for _ in ids)\nquery = f"WHERE id IN ({placeholders})"\n', encoding="utf-8")

    report = audit_mock_risks([tmp_path], repo_root=tmp_path)

    assert report["passed"] is True
    assert report["counts"]["INFO"] == 2


def test_release_mock_audit_downgrades_negative_fake_statement(tmp_path: Path) -> None:
    path = tmp_path / "readme.md"
    path.write_text("ATANOR does not compress nodes into fake aggregate nodes.\n", encoding="utf-8")

    report = audit_mock_risks([tmp_path], repo_root=tmp_path)

    assert report["passed"] is True
    assert report["counts"]["INFO"] == 1


def test_release_mock_audit_downgrades_canned_false_flag(tmp_path: Path) -> None:
    path = tmp_path / "status.ts"
    path.write_text("canned_response: false,\n", encoding="utf-8")

    report = audit_mock_risks([tmp_path], repo_root=tmp_path)

    assert report["passed"] is True
    assert report["counts"]["INFO"] == 1


def test_release_mock_audit_allowlist_requires_reason_and_expiry(tmp_path: Path) -> None:
    app = tmp_path / "runtime.py"
    app.write_text("run_mock_purchase()\n", encoding="utf-8")
    allowlist = tmp_path / "allowlist.json"
    allowlist.write_text('{"allowlist": [{"key": "runtime.py:1:mock", "reason": "tracked local simulation"}]}\n', encoding="utf-8")

    try:
        audit_mock_risks([tmp_path], repo_root=tmp_path, allowlist_path=allowlist)
    except ValueError as exc:
        assert "requires key, reason, and expires" in str(exc)
    else:
        raise AssertionError("allowlist entry without expiry should fail")


def test_release_mock_audit_allowlist_with_expiry_downgrades_to_info(tmp_path: Path) -> None:
    app = tmp_path / "runtime.py"
    app.write_text("run_mock_purchase()\n", encoding="utf-8")
    allowlist = tmp_path / "allowlist.json"
    allowlist.write_text(
        '{"allowlist": [{"key": "runtime.py:1:mock", "reason": "tracked local simulation", "expires": "2026-12-31"}]}\n',
        encoding="utf-8",
    )

    report = audit_mock_risks([tmp_path], repo_root=tmp_path, allowlist_path=allowlist)

    assert report["passed"] is True
    assert report["counts"]["INFO"] == 1
