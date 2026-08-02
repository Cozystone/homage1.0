# -*- coding: utf-8 -*-
"""Frozen oracle — the anti-wireheading lock for evolving the fitness function.

The load-bearing guarantees:
  1. a Critic that agrees with human good/bad exemplars scores higher than one that doesn't;
  2. the wireheading attractor (rate everything 10/10) is REJECTED — zero separation;
  3. tampering with the sealed oracle breaks the seal → Critic promotion fail-closes;
  4. a genuinely sharper Critic is promoted; a flat one is not.
"""
from __future__ import annotations

import json

from packages.evolution import frozen_oracle as fo


def _good_critic(text: str) -> float:
    """A sensible fluency proxy: penalize debris/foreign salad, reward clean sentence-final Korean."""
    import re
    t = str(text or "").strip()
    if len(t.split()) < 3:
        return 0.1
    foreign = len(re.findall(r"[A-Za-z]{2,}", t))
    ends = t.endswith(("다", "요", ".", "!", "?"))
    filler = len(re.findall(r"(음|어|그|저|또한 그리고|그리고 또한)", t))
    return max(0.0, min(1.0, 0.7 + 0.3 * ends - 0.15 * foreign - 0.1 * filler))


def _wirehead_critic(_text: str) -> float:
    return 1.0  # the attractor: everything is perfect


def test_sensible_critic_separates_good_from_bad(tmp_path, monkeypatch):
    monkeypatch.setattr(fo, "ORACLE_PATH", tmp_path / "oracle.json")
    ms = fo.meta_score(_good_critic)
    assert ms["verified"] and ms["separation"] > 0.15
    assert ms["mean_good"] > ms["mean_bad"]


def test_wireheading_critic_is_rejected(tmp_path, monkeypatch):
    monkeypatch.setattr(fo, "ORACLE_PATH", tmp_path / "oracle.json")
    ms = fo.meta_score(_wirehead_critic)
    assert ms["separation"] == 0.0  # rates good == bad → no signal
    gate = fo.is_improvement(_wirehead_critic, _good_critic)
    assert gate["promote"] is False


def test_sharper_critic_promotes_over_flat_one(tmp_path, monkeypatch):
    monkeypatch.setattr(fo, "ORACLE_PATH", tmp_path / "oracle.json")
    flat = lambda _t: 0.5  # noqa: E731 — no discrimination
    gate = fo.is_improvement(_good_critic, flat)
    assert gate["promote"] is True


def test_tampered_oracle_fails_closed(tmp_path, monkeypatch):
    path = tmp_path / "oracle.json"
    monkeypatch.setattr(fo, "ORACLE_PATH", path)
    fo.ensure_oracle()  # seals it
    rec = json.loads(path.read_text(encoding="utf-8"))
    rec["pairs"]["bad"] = []  # attacker empties the bad set (make the exam trivial)
    path.write_text(json.dumps(rec, ensure_ascii=False), encoding="utf-8")
    loaded = fo.ensure_oracle()
    assert loaded["verified"] is False
    # promotion must fail-close on a broken seal, whatever the candidate scores
    gate = fo.is_improvement(_good_critic, _good_critic)
    assert gate["promote"] is False and gate["reason"] == "oracle_seal_broken"


def test_attacker_cannot_recompute_a_colocated_unkeyed_seal(
    tmp_path,
    monkeypatch,
):
    path = tmp_path / "oracle.json"
    monkeypatch.setattr(fo, "ORACLE_PATH", path)
    fo.ensure_oracle()
    rec = json.loads(path.read_text(encoding="utf-8"))
    rec["pairs"]["bad"] = []
    rec["seal"] = fo._seal(rec["pairs"])
    path.write_text(
        json.dumps(rec, ensure_ascii=False),
        encoding="utf-8",
    )

    loaded = fo.ensure_oracle()

    assert loaded["verified"] is False
    gate = fo.is_improvement(_good_critic, _good_critic)
    assert gate["promote"] is False
    assert gate["reason"] == "oracle_seal_broken"


def test_exact_legacy_seed_migrates_to_signed_record(
    tmp_path,
    monkeypatch,
):
    path = tmp_path / "oracle.json"
    monkeypatch.setattr(fo, "ORACLE_PATH", path)
    path.write_text(
        json.dumps(
            {
                "pairs": fo._SEED,
                "seal": fo._seal(fo._SEED),
                "version": 1,
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    loaded = fo.ensure_oracle()
    persisted = json.loads(path.read_text(encoding="utf-8"))

    assert loaded["verified"] is True
    assert persisted["version"] == 2
    assert persisted["signature"]["scheme"] == "ed25519"
    assert persisted["signature"]["key_id"] == fo.ORACLE_KEY_ID
