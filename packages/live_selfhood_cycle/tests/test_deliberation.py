from packages.live_selfhood_cycle.deliberation import deliberate_action
from packages.live_selfhood_cycle.models import Impulse, ScheduledAction


def test_deliberation_is_local_and_review_only():
    impulse = Impulse("i", "memory_review_needed", 1, 1, 1, 1, 0, 1, "reason", "step")
    action = ScheduledAction("a", "prepare_memory_review", "Memory review", "Prepare review")
    result = deliberate_action(impulse, [], action)
    assert "external_llm_used=false" in result.safety_notes
    assert result.recommendation == "prepare_review_packet"
