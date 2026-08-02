# -*- coding: utf-8 -*-
"""Stakes (plan S1) — the layer that turns hormone lights into hunger. The tests check the four
properties that make it stakes and not theater: vitals are READ from real records, selection is
gradient COMPETITION (not a threshold ladder), neglect has TEETH with earned recovery, and the
ablation switch produces a measurably different agent (the G-S1 experiment's mechanism)."""
from __future__ import annotations

import os
import time

import packages.continuous_self.stakes as st
from packages.continuous_self.stakes import Vitals, choose


# ---------- vitals are measurements, not inventions ----------

def test_vitals_read_from_real_file_ages(tmp_path, monkeypatch):
    (tmp_path / "data" / "advisor_loop").mkdir(parents=True)
    (tmp_path / "data" / "brain_link").mkdir(parents=True)
    learned = tmp_path / "data" / "advisor_loop" / "world_model_learned.jsonl"
    social = tmp_path / "data" / "brain_link" / "overnight_transcript.log"
    learned.write_text("{}\n", encoding="utf-8")
    social.write_text("x\n", encoding="utf-8")
    now = time.time()
    os.utime(learned, (now - 18 * 3600, now - 18 * 3600))    # exactly one knowledge half-life
    os.utime(social, (now - 6 * 3600, now - 6 * 3600))       # exactly one social half-life
    v = st.read_vitals(tmp_path)
    assert abs(v.knowledge - 0.5) < 0.02                     # decay is the declared physiology
    assert abs(v.social - 0.5) < 0.02


def test_never_fed_is_the_hungriest_state(tmp_path):
    v = st.read_vitals(tmp_path)                             # no records at all
    assert v.knowledge == 0.0 and v.social == 0.0            # not an error — starving


# ---------- gradient competition, not a threshold ladder ----------

def test_steepest_deficit_wins():
    v = Vitals(knowledge=0.9, social=0.2, coherence=0.9, energy=0.9)
    assert choose(v)["action"] == "converse"                 # social is the steepest hunger
    v = Vitals(knowledge=0.1, social=0.9, coherence=0.9, energy=0.9)
    assert choose(v)["action"] == "explore"
    v = Vitals(knowledge=0.9, social=0.9, coherence=0.15, energy=0.9)
    assert choose(v)["action"] == "repair"


def test_no_real_deficit_means_honest_quiet():
    v = Vitals(knowledge=0.95, social=0.95, coherence=0.95, energy=0.95)
    out = choose(v)
    assert out["action"] == "idle" and "no vital" in out["reason"]


def test_reason_names_the_deficit():
    out = choose(Vitals(knowledge=0.1, social=0.9, coherence=0.9, energy=0.9))
    assert "knowledge" in out["reason"] and "explore" in out["reason"]


def test_parent_command_overrides_everything():
    v = Vitals(knowledge=0.0, social=0.0, coherence=0.0, energy=0.0)   # starving everywhere
    assert choose(v, has_command=True)["action"] == "obey_command"     # constitution holds


# ---------- teeth: neglect costs capability; recovery is earned ----------

def test_social_starvation_rusts_skills_and_recovery_is_earned(monkeypatch):
    monkeypatch.setenv("ATANOR_STAKES", "1")
    starved = Vitals(knowledge=0.9, social=0.1, coherence=0.9, energy=0.9)
    assert st.social_warmup_needed(starved) == st.WARMUP_TURNS
    fed = Vitals(knowledge=0.9, social=0.9, coherence=0.9, energy=0.9)
    assert st.social_warmup_needed(fed) == 0
    # the drive side: hunger initiates sooner
    assert st.dialogue_pace(100.0, starved) < st.dialogue_pace(100.0, fed)


def test_warmup_gates_skilled_moves_until_earned():
    """The atrophy tooth in the real conversation engine: a rusty agent cannot debate or
    synthesize — only plain exchange — until warm-up is EARNED by conversing."""
    from packages.brain_link.conversation import Agent, step
    a = Agent("pc", knowledge={"bird": [["bird", "is_a", "reptile"]]}, curiosity=["bird"],
              web=False, warmup=2)
    b = Agent("edge", knowledge={"bird": [["bird", "is_a", "animal"]]}, web=False)
    t1 = step(a, None)                    # ask
    t2 = step(b, t1)                      # answer (bones voiced)
    t3 = step(a, t2)                      # rusty: would have been a COMPARE — must not be
    assert t3.act != "compare"
    assert a.warmup == 1                  # the exchange itself re-limbered a little


def test_coherence_debt_shrinks_discretionary_budget(monkeypatch):
    monkeypatch.setenv("ATANOR_STAKES", "1")
    indebted = Vitals(knowledge=0.9, social=0.9, coherence=0.3, energy=0.9)
    clean = Vitals(knowledge=0.9, social=0.9, coherence=1.0, energy=0.9)
    assert st.discretionary_budget(indebted) < st.discretionary_budget(clean)
    assert st.discretionary_budget(clean) == 1.0


# ---------- ablation: the G-S1 experiment's mechanism ----------

def test_ablation_freezes_the_teeth(monkeypatch):
    starved = Vitals(knowledge=0.9, social=0.05, coherence=0.2, energy=0.9)
    monkeypatch.setenv("ATANOR_STAKES", "0")
    assert st.social_warmup_needed(starved) == 0             # lights-only mode
    assert st.discretionary_budget(starved) == 1.0
    assert st.dialogue_pace(100.0, starved) == 100.0
    monkeypatch.setenv("ATANOR_STAKES", "1")
    assert st.social_warmup_needed(starved) > 0              # the teeth are back
