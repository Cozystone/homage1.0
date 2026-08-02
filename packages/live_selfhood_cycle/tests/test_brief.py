from packages.live_selfhood_cycle.brief import generate_brief
from packages.live_selfhood_cycle.clock import make_tick
from packages.live_selfhood_cycle.models import Need, ScheduledAction


def test_morning_brief_contains_required_sections():
    brief = generate_brief(
        make_tick("morning", "test"),
        [],
        [Need("n", "morning_brief_needed", "brief")],
        [],
        [ScheduledAction("a", "prepare_morning_brief", "Morning", "Brief")],
        [],
    )
    assert brief is not None
    assert "What I noticed" in brief.sections
    assert "What requires your approval" in brief.sections
