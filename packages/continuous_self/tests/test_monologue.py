# -*- coding: utf-8 -*-
"""Inner monologue self-play: generates lines inward, gates them (grounding via Critic
faithfulness + fluency), keeps survivors in the narrative corpus. Sandbox-only."""
import json

from packages.continuous_self import monologue as mono


class _FakeState:
    ticks = 7
    narrative = [{"text": "I read about virtual machines and learned something new."}]


def _setup(tmp_path, monkeypatch, enabled=True, last_at=0.0):
    st = tmp_path / "monologue.json"
    st.write_text(json.dumps({"enabled": enabled, "last_at": last_at}), encoding="utf-8")
    monkeypatch.setattr(mono, "_STATE", st)
    monkeypatch.setattr(mono, "_JOURNAL", tmp_path / "monologue.jsonl")


def test_disabled_and_rate_floor_do_nothing(tmp_path, monkeypatch):
    _setup(tmp_path, monkeypatch, enabled=False)
    assert mono.monologue_tick(_FakeState(), now=10_000)["acted"] is False
    _setup(tmp_path, monkeypatch, enabled=True, last_at=10_000)
    r = mono.monologue_tick(_FakeState(), now=10_050)     # 50s < 240 floor
    assert r["acted"] is False and r["reason"] == "rate_floor"


def test_accepted_line_lands_in_corpus_and_journal(tmp_path, monkeypatch):
    _setup(tmp_path, monkeypatch)
    # deterministic generator + gates: this test verifies the LOOP (speak→judge→keep),
    # not the LM. realize_thought itself is covered by its own module tests.
    import packages.continuous_self.thought_language as tl
    line = "It interests me that a virtual machine is an isolated execution environment."
    monkeypatch.setattr(tl, "realize_thought", lambda d, f, s: line)
    monkeypatch.setattr(mono, "realize_thought", tl.realize_thought, raising=False)
    import packages.base_brain.speech_selfplay as sp
    monkeypatch.setattr(sp, "critique", lambda t, f=None, question="": {"total": 0.9, "faithful": True})
    from packages.autonomy_kernel import narrative_corpus as nc
    monkeypatch.setattr(nc, "CORPUS", tmp_path / "corpus.jsonl")

    r = mono.monologue_tick(_FakeState(), now=10_000)
    assert r["acted"] is True and r["accepted"] >= 1
    assert line in nc.corpus_tail(10, sources=("monologue",))
    journal = (tmp_path / "monologue.jsonl").read_text(encoding="utf-8")
    assert "accepted" in journal and line[:10] in journal


def test_unfaithful_line_is_rejected(tmp_path, monkeypatch):
    _setup(tmp_path, monkeypatch)
    import packages.continuous_self.thought_language as tl
    monkeypatch.setattr(tl, "realize_thought", lambda d, f, s: "A fabricated claim cannot pass the gate here.")
    import packages.base_brain.speech_selfplay as sp
    monkeypatch.setattr(sp, "critique", lambda t, f=None, question="": {"total": 0.0, "faithful": False})
    from packages.autonomy_kernel import narrative_corpus as nc
    monkeypatch.setattr(nc, "CORPUS", tmp_path / "corpus.jsonl")

    r = mono.monologue_tick(_FakeState(), now=10_000)
    assert r["acted"] is True and r["accepted"] == 0
    assert nc.corpus_tail(10, sources=("monologue",)) == []