# -*- coding: utf-8 -*-
"""Ignition (plan S2) — the serial bottleneck that makes a subject out of a pipeline. The tests
assert the four things a pipeline CANNOT do: exactly one candidate wins, the winner binds the
future (commitment debt biases the next competition toward closure), the same input is processed
DIFFERENTLY by internal state (the G-S2 signature), and the history is one owned, tamper-evident
ledger with an attention-schema self-report."""
from __future__ import annotations

import packages.continuous_self.ignition as ig
from packages.continuous_self.ignition import Candidate, compete


def _fresh(tmp_path, monkeypatch):
    monkeypatch.setattr(ig, "LEDGER", tmp_path / "ign.jsonl")


# ---------- serial selection: exactly one ignites ----------

def test_single_winner_and_report(tmp_path, monkeypatch):
    _fresh(tmp_path, monkeypatch)
    cands = [Candidate("utterance", "birds", 0.85),
             Candidate("vital", "social", 0.60),
             Candidate("curiosity", "rivers", 0.45)]
    out = compete(cands, now=1000.0)
    assert out.winner.topic == "birds"                 # the loudest, alone
    assert len(out.suppressed) == 2 and out.decisive
    assert "attending to utterance:birds" in out.report()
    assert "birds" in out.report() and "over" in out.report()


def test_empty_competition_is_none(tmp_path, monkeypatch):
    _fresh(tmp_path, monkeypatch)
    assert compete([], now=1.0) is None


# ---------- the future is bound: commitment debt biases the next tick ----------

def test_open_commitment_biases_toward_closure(tmp_path, monkeypatch):
    _fresh(tmp_path, monkeypatch)
    # tick 1: a vital wins and becomes an open commitment
    t1 = compete([Candidate("vital", "repair", 0.55), Candidate("curiosity", "stars", 0.50)],
                 now=1000.0)
    assert t1.winner.topic == "repair"
    ig.record_ignition(t1)
    # tick 2: a FRESH curiosity is intrinsically louder — but the open 'repair' commitment, aged,
    # gets a closure bias and holds the workspace. A memoryless pipeline would switch; a subject
    # finishes what it started.
    t2 = compete([Candidate("vital", "repair", 0.55), Candidate("curiosity", "comets", 0.66)],
                 now=1000.0 + 3600)                     # one hour later
    assert t2.winner.topic == "repair"                 # debt bias > the fresher rival
    # once closed, the pressure is gone and the fresh rival finally wins
    ig.close_commitment("vital", "repair", "done")
    t3 = compete([Candidate("vital", "repair", 0.55), Candidate("curiosity", "comets", 0.66)],
                 now=1000.0 + 7200)
    assert t3.winner.topic == "comets"


def test_commitment_debt_counts_open_only(tmp_path, monkeypatch):
    _fresh(tmp_path, monkeypatch)
    ig.record_ignition(compete([Candidate("vital", "a", 0.9)], now=1.0))
    ig.record_ignition(compete([Candidate("vital", "b", 0.9)], now=2.0))
    assert ig.commitment_debt() == 2
    ig.close_commitment("vital", "a")
    assert ig.commitment_debt() == 1
    ig.abandon_commitment("vital", "b", reason="superseded")
    assert ig.commitment_debt() == 0


# ---------- the G-S2 signature: same input, different processing by internal state ----------

def test_same_input_different_order_by_state(tmp_path, monkeypatch):
    """A pipeline maps input->output identically every time. Here the SAME incoming utterance is
    attended to in one state and SUPPRESSED in another, purely because internal commitment debt
    changed what is loudest — the thing a fixed treatment plant cannot do."""
    _fresh(tmp_path, monkeypatch)
    incoming = Candidate("utterance", "weather", 0.62)
    # state A: nothing open -> the utterance wins and is processed
    a = compete([incoming, Candidate("vital", "repair", 0.55)], now=1000.0)
    assert a.winner.topic == "weather"
    # state B: a repair commitment has been open for hours -> its closure bias now outweighs the
    # very same utterance, which is suppressed this tick
    ig.record_ignition(compete([Candidate("vital", "repair", 0.55)], now=1.0))
    b = compete([incoming, Candidate("vital", "repair", 0.55)], now=1.0 + 5 * 3600)
    assert b.winner.topic == "repair"
    assert any(c.topic == "weather" for c in b.suppressed)     # identical input, suppressed now


# ---------- one owned, tamper-evident history ----------

def test_ledger_chain_is_tamper_evident(tmp_path, monkeypatch):
    _fresh(tmp_path, monkeypatch)
    for i in range(3):
        ig.record_ignition(compete([Candidate("curiosity", f"c{i}", 0.9)], now=float(i)))
    assert ig.verify_chain() is True
    # corrupt a middle line's topic; the chain must detect it
    lines = (tmp_path / "ign.jsonl").read_text(encoding="utf-8").splitlines()
    lines[1] = lines[1].replace("c1", "TAMPERED")
    (tmp_path / "ign.jsonl").write_text("\n".join(lines) + "\n", encoding="utf-8")
    assert ig.verify_chain() is False


# ---------- candidate gathering reads real state ----------

def test_gather_pulls_from_real_state(tmp_path, monkeypatch):
    _fresh(tmp_path, monkeypatch)
    from packages.continuous_self.stakes import Vitals

    class _In:
        act = "ask"
        concept = "gravity"

    cands = ig.gather_candidates(incoming=_In(), curiosity=["tides", "moon"],
                                 vitals=Vitals(0.9, 0.1, 0.9, 0.9), now=100.0)
    kinds = {c.kind for c in cands}
    assert "utterance" in kinds and "vital" in kinds and "curiosity" in kinds
    utter = next(c for c in cands if c.kind == "utterance")
    vital = next(c for c in cands if c.kind == "vital")
    assert utter.topic == "gravity"
    assert vital.topic == "social"                     # the steepest hunger entered the workspace
