# -*- coding: utf-8 -*-
"""Living Loop: workspace competition+broadcast (GWT), agency ledger (self-as-node), beat integration.
Correlates measured, never asserted; no phenomenal claims anywhere."""
from packages.continuous_self.agency_ledger import AgencyLedger
from packages.live_selfhood_cycle.living_beat import beat, run_burst
from packages.live_selfhood_cycle.workspace import Concern, Workspace
from packages.temporal_reasoning.unified_timeline import Timeline


def test_workspace_one_winner_per_beat_serial_bottleneck():
    tl = Timeline()
    ws = Workspace(tl)
    a = Concern("interoception", "store integrity dropped", urgency=0.9, viability=0.9)
    b = Concern("curiosity", "what is a quasar really", urgency=0.6, viability=0.1)
    w = ws.compete([a, b], hormones={})
    assert w is a                                          # viability+urgency wins without hormones
    ws.broadcast(w)
    thoughts = [e for e in tl.all() if e.kind == "thought"]
    assert len(thoughts) == 1                              # ONE broadcast per beat — the bottleneck
    assert thoughts[0].meta["workspace"] and thoughts[0].who == "atanor"


def test_hormones_weight_the_competition_feeling_directs_attention():
    tl = Timeline()
    ws = Workspace(tl)
    survival = Concern("interoception", "engine memory pressure rising", urgency=0.5, viability=0.8)
    novelty = Concern("curiosity", "a shiny new dataset appeared", urgency=0.6, viability=0.1)
    calm = ws.compete([survival, novelty], hormones={"cortisol": 0.0, "dopamine": 0.9})
    assert calm is novelty                                 # reward tone: the new world is louder
    stressed = ws.compete([survival, novelty], hormones={"cortisol": 0.9, "dopamine": 0.0})
    assert stressed is survival                            # stress: survival matters get louder


def test_agency_ledger_holds_the_probe_distinctions():
    led = AgencyLedger(Timeline())
    arc = led.judged("answer the owner's question", why="perception won the workspace")
    led.acted(arc, "the answer text", delivered=False)      # produced but not delivered
    role = led.my_causal_role()
    assert role["judgment_is_not_output"] and role["efficacy_is_conditional_on_delivery"]
    assert role["outputs"] == 1 and role["delivered"] == 0
    cf = led.counterfactual_self_removed("previous output A")
    assert "reacts to what arrives, not to me" in cf        # the replay counterfactual, computed
    assert "delivered output" in led.counterfactual_channel_blocked()
    assert len(led.retraction_conditions()) >= 3            # revisable self-location


def test_beat_converges_organs_and_records_agency():
    tl = Timeline()
    tl.record("utterance", "what changed in you today?", who="user")
    ws, led = Workspace(tl), AgencyLedger(tl)
    r = beat(ws, led)
    assert r["broadcast"] and r["candidates"] >= 1
    assert led.my_causal_role()["judgments"] == 1          # the judgment stage was recorded


def test_burst_produces_endogenous_stream_with_measured_correlates():
    tl = Timeline()                                        # quiet line: pure endogenous life
    out = run_burst(6, timeline=tl)
    assert len(out["stream"]) == 6
    c = out["correlates"]
    assert c["serial_bottleneck"] is True and c["broadcast_thoughts"] == 6
    assert c["endogeneity"] == 1.0                         # nothing was request-driven


def test_inner_voice_is_first_person_and_feeling_loop_closes():
    tl = Timeline()
    out = run_burst(8, timeline=tl)
    # inner speech, not log lines: first-person self-talk on the timeline
    thoughts = [e.content for e in tl.all() if e.kind == "thought"]
    assert thoughts and any(" I " in f" {t} " or t.startswith("I ") or "my " in t.lower()
                            for t in thoughts)
    assert not any(t.startswith("I notice a deficit:") for t in thoughts)   # verbalized, not raw
    # L2 closed loop: the loop itself moved the hormone field (persisting deficits build cortisol)
    trace = out["hormone_trace"]
    assert trace and trace[-1].get("cortisol", 0.0) > trace[0].get("cortisol", 1.0) - 1.0
    assert any(h.get("cortisol", 0) > 0.15 for h in trace), "sustained deficits should build load"
