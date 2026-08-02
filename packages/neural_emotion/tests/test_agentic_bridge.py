from packages.neural_emotion.agentic_bridge import agentic_controls
from packages.neural_emotion.models import EmotionVector


def test_agentic_controls_never_bypass_permission_gate() -> None:
    controls = agentic_controls(EmotionVector(caution=0.95, curiosity=0.9), risk=0.95)

    assert controls["pause_or_require_approval"] is True
    assert controls["permission_gate_bypass"] is False
    assert controls["autonomy_tier_changed"] is False
    assert controls["writes_local_brain"] is False
    assert controls["mutates_production_store"] is False
