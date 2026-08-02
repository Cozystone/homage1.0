"""Raw sidecar builders must respect the shipped-store authority boundary."""

from __future__ import annotations

import pickle
import sys

import pytest

from packages.graph_scale.triple_store import TripleStore
from scripts import build_isa_verdict, build_lang_gate
from scripts import landing_chain_lib


def _candidate_pair(tmp_path, monkeypatch):
    live = tmp_path / "kg_triples"
    live.mkdir()
    candidate = tmp_path / "kg_triples.staged_merge.test-sidecar"
    TripleStore(candidate)
    monkeypatch.setattr(
        landing_chain_lib,
        "CANONICAL_SHIPPED_ROOT",
        live,
    )
    return live, candidate


def test_language_gate_build_refuses_canonical_store(
        monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    live, _candidate = _candidate_pair(tmp_path, monkeypatch)
    monkeypatch.setattr(
        sys,
        "argv",
        ["build_lang_gate.py", "--store-root", str(live)],
    )

    with pytest.raises(RuntimeError, match="distinct from the shipped store"):
        build_lang_gate.main()


def test_isa_verdict_build_refuses_canonical_store(
        monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    live, _candidate = _candidate_pair(tmp_path, monkeypatch)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "build_isa_verdict.py",
            "--store-root",
            str(live),
            "--pairs-dir",
            str(tmp_path / "missing"),
        ],
    )

    with pytest.raises(RuntimeError, match="distinct from the shipped store"):
        build_isa_verdict.main()


def test_language_gate_builds_only_in_candidate_lane(
        monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    _live, candidate = _candidate_pair(tmp_path, monkeypatch)
    store = TripleStore(candidate)
    store.add("alpha", "is_a", "beta")
    store.flush()
    monkeypatch.setattr(
        sys,
        "argv",
        ["build_lang_gate.py", "--store-root", str(candidate)],
    )

    assert build_lang_gate.main() == 0
    assert (candidate / "lang_gate.col").read_bytes() == b"\x00"


def test_isa_verdict_builds_only_in_candidate_lane(
        monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    _live, candidate = _candidate_pair(tmp_path, monkeypatch)
    store = TripleStore(candidate)
    store.add("alpha", "is_a", "beta")
    store.flush()
    pairs = tmp_path / "pairs"
    pairs.mkdir()
    for name, value in (
        ("cn_isa_pairs.pkl", {("alpha", "beta")}),
        ("kaikki_isa_pairs.pkl", set()),
    ):
        with (pairs / name).open("wb") as handle:
            pickle.dump(value, handle)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "build_isa_verdict.py",
            "--store-root",
            str(candidate),
            "--pairs-dir",
            str(pairs),
        ],
    )

    assert build_isa_verdict.main() == 0
    assert (candidate / "isa_verdict.col").read_bytes() == b"\x01"
