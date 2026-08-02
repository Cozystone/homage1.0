from packages.live_selfhood_cycle.clock import SimulatedLifeClock, make_tick


def test_simulated_clock_generates_deterministic_tick_ids():
    clock = SimulatedLifeClock()
    assert clock.tick("startup").tick_id == "tick-0001"
    assert clock.tick("morning").tick_id == "tick-0002"


def test_make_tick_preserves_type_and_level():
    tick = make_tick("manual_ping", "test", "LEVEL_2_PROACTIVE_BRIEF", tick_id="t")
    assert tick.tick_type == "manual_ping"
    assert tick.autonomy_level == "LEVEL_2_PROACTIVE_BRIEF"
