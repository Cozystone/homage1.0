"""PII mutation reports must stay truthful at the shipped read-only boundary."""

from __future__ import annotations

import pytest

import packages.graph_scale.pii_guard as pii_guard
import packages.graph_scale.triple_store as triple_store_module
from packages.graph_scale.triple_store import TripleStore


def _reopen_as_canonical(root, monkeypatch) -> TripleStore:
    monkeypatch.setattr(
        triple_store_module,
        "_CANONICAL_SHIPPED_ROOT",
        root,
    )
    return TripleStore(root)


def _snapshot(root) -> dict[str, bytes]:
    return {
        str(path.relative_to(root)): path.read_bytes()
        for path in root.rglob("*")
        if path.is_file()
    }


def test_forget_failure_is_not_reported_as_rows_removed(
        tmp_path, monkeypatch) -> None:
    root = tmp_path / "canonical"
    seed = TripleStore(root)
    seed.add("person", "works_at", "company")
    seed.add("company", "employs", "person")
    seed.flush()
    before = _snapshot(root)
    monkeypatch.setattr(
        pii_guard,
        "LEDGER",
        tmp_path / "privacy-ledger.jsonl",
    )
    shipped = _reopen_as_canonical(root, monkeypatch)

    with pytest.raises(PermissionError, match="triple retraction refused"):
        pii_guard.forget(shipped, "person", apply=True)

    assert _snapshot(root) == before
    assert not pii_guard.LEDGER.exists()


def test_forget_observe_only_reports_matches_without_mutating_or_ledgering(
        tmp_path, monkeypatch) -> None:
    root = tmp_path / "canonical"
    seed = TripleStore(root)
    seed.add("person", "works_at", "company")
    seed.add("company", "employs", "person")
    seed.flush()
    before = _snapshot(root)
    monkeypatch.setattr(
        pii_guard,
        "LEDGER",
        tmp_path / "privacy-ledger.jsonl",
    )
    shipped = _reopen_as_canonical(root, monkeypatch)

    result = pii_guard.forget(shipped, "person", apply=False)

    assert result["rows_matched"] == 2
    assert result["rows_removed"] == 0
    assert result["applied"] is False
    assert result["complete_scan"] is True
    assert _snapshot(root) == before
    assert not pii_guard.LEDGER.exists()


def test_pii_sweep_failure_is_not_ledgered_as_quarantined(
        tmp_path, monkeypatch) -> None:
    root = tmp_path / "canonical"
    seed = TripleStore(root)
    seed.add("person", "contact", "010-1234-5678")
    seed.flush()
    monkeypatch.setattr(
        pii_guard,
        "LEDGER",
        tmp_path / "privacy-ledger.jsonl",
    )
    shipped = _reopen_as_canonical(root, monkeypatch)

    with pytest.raises(PermissionError, match="triple retraction refused"):
        pii_guard.scan_and_quarantine(shipped, apply=True)

    assert not pii_guard.LEDGER.exists()
