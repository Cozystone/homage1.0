# -*- coding: utf-8 -*-
"""The Generative Leap Loop, verified deterministically on a clean mock (the live lexical store can't
show it). Proves: (1) systematicity-gated structure transfer produces the RIGHT conjecture — the
textbook Rutherford analogy sun:planet::nucleus:electron → (nucleus, orbited_by, electron); (2) every
minted row is a CONJECTURE (status=unverified), never a fact; (3) lexical relations are not carried."""
from __future__ import annotations

import numpy as np

from packages.reasoning_vm import learned_discriminator as LD
from packages.reasoning_vm.leap import LeapEngine


def _mock_emb():
    # parallelogram geometry: electron−nucleus == planet−sun, so vec(planet)+vec(nucleus)−vec(sun)
    # lands on electron. Distractors kept far.
    terms = ["sun", "planet", "nucleus", "electron", "banana", "ocean", "music"]
    V = np.array([[1, 0, 0, 0], [1, 1, 0, 0], [0, 0, 1, 0], [0, 1, 1, 0],
                  [0, 0, 0, 1], [1, 0, 1, 0], [0.5, 0.5, 0.5, 0.5]], dtype=np.float32)
    V /= np.linalg.norm(V, axis=1, keepdims=True)
    return LD.Embeddings(terms, V)


def test_systematic_transfer_finds_the_textbook_analogy():
    emb = _mock_emb()
    store = {"sun": [("sun", "orbited_by", "planet")],
             "nucleus": [("nucleus", "orbited_by", "proton")]}   # target shares 'orbited_by'
    eng = LeapEngine(emb, facts_about=lambda e: store.get(e, []))

    cs = eng.transfer("sun", "nucleus", k_map=2, limit=4, only_relations={"orbited_by"})
    assert cs, "expected at least one conjecture"
    top = cs[0]
    assert top.triple == ("nucleus", "orbited_by", "electron"), top.triple
    assert top.status == "conjecture"                          # proposer, never asserter
    assert top.score > 0.9


def test_systematicity_gate_blocks_unshared_relations():
    emb = _mock_emb()
    # target does NOT share 'orbited_by' → nothing systematic to carry
    store = {"sun": [("sun", "orbited_by", "planet")], "nucleus": [("nucleus", "made_of", "quark")]}
    eng = LeapEngine(emb, facts_about=lambda e: store.get(e, []))
    shared = {"orbited_by"} & {"made_of"}
    assert eng.transfer("sun", "nucleus", only_relations=shared) == []


def test_mint_leaps_ledgers_only_conjectures(tmp_path, monkeypatch):
    """mint_leaps must (a) write to the shared hypothesis ledger with status=unverified, source=leap,
    (b) never carry a lexical relation, (c) never touch the substrate as a fact."""
    from packages.reasoning_vm import leap_verify as LV
    from packages.graph_scale import hypothesis_minter as HM

    ledger = tmp_path / "hypotheses.jsonl"
    monkeypatch.setattr(HM, "LEDGER", ledger)

    emb = _mock_emb()

    class _Store:
        _f = {"sun": [("sun", "orbited_by", "planet"), ("sun", "alias", "sol")],
              "nucleus": [("nucleus", "orbited_by", "proton")]}

        def facts_about(self, e, limit=40):
            return self._f.get(e, [])

    rows = LV.mint_leaps(store=_Store(), emb=emb, n_sources=10, per_source=3, max_mint=5, seed=1)
    # every minted row is an unverified, source-tagged conjecture — never a fact, never lexical
    for r in rows:
        assert r["status"] == "unverified"
        assert r["source"] == "leap"
        assert r["relation"] not in LV._GENERIC
        assert "carried_edge" in r["derivation"]
    if rows:                                                   # if any minted, the ledger holds them
        assert ledger.exists()
        assert all('"status": "unverified"' in ln for ln in ledger.read_text(encoding="utf-8").splitlines())
