# -*- coding: utf-8 -*-
"""Life: the always-on mind — metabolic tempo (a pulse, not a schedule), capabilities in the flow."""
from packages.live_selfhood_cycle.life import Life
from packages.neural_emotion.metabolic_governor import regime


def _life(tmp_path):
    return Life(stream_path=tmp_path / "life_stream.jsonl")


def test_tempo_is_a_pulse_not_a_schedule(tmp_path):
    life = _life(tmp_path)
    calm = life.tempo()
    life.endocrine.sense("threat", 1.0)                    # arousal quickens the pulse
    aroused = life.tempo()
    assert aroused < calm
    life2 = _life(tmp_path)
    life2.endocrine.sense("recovery", 1.0)
    life2.endocrine.sense("wellbeing", 1.0)                # rest slows it
    assert life2.tempo() >= calm
    assert 2.0 <= aroused <= 60.0 and 2.0 <= life2.tempo() <= 60.0   # bounded, always


def test_step_lives_on_the_persistent_timeline(tmp_path):
    life = _life(tmp_path)
    r1 = life.step()
    r2 = life.step()
    assert r1.get("broadcast") and r2.get("broadcast")
    assert (tmp_path / "life_stream.jsonl").exists()       # the life persists (continuity)
    lines = (tmp_path / "life_stream.jsonl").read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) >= 2                                  # thoughts written as they are lived


def test_self_inspection_finding_becomes_a_concern_the_next_beat(tmp_path):
    """The self-repair loop closes: a queued wiring finding re-enters as an interoceptive concern
    the organism then attends to (noticing its own loose joint -> working on it)."""
    life = _life(tmp_path)
    life._findings.append("UNSALTED hash at scripts/build_c1_battery.py:136")
    r = life.step()
    # the finding surfaced into the stream as something ATANOR is now attending to
    thoughts = " ".join(e.content for e in life.timeline.all() if e.kind == "thought")
    assert "found this in my own wiring" in thoughts or "UNSALTED" in thoughts
    assert not life._findings                              # it left the queue (being worked, not re-raised)


def test_capabilities_emerge_from_state_not_from_calls(tmp_path):
    """The governor is read, never 'called as a favor': which act happens follows from
    (what won) x (what the field affords). We verify the affordance gating both ways."""
    life = _life(tmp_path)
    # CHRONIC load (repeated, like real life) -> repair attention becomes affordable
    life.endocrine.sense("sustained_load", 1.0)
    life.endocrine.sense("sustained_load", 1.0)
    r = regime(dict(life.endocrine.levels))
    assert r["repair_priority"] > 0.6                       # the state affords self-repair attention
    # and exploration is dampened by the same state (one field, many consequences)
    calm = Life(stream_path=tmp_path / "b.jsonl")
    assert regime(dict(calm.endocrine.levels))["exploration_temperature"] >= r["exploration_temperature"]
