from __future__ import annotations

from packages.autonomy_kernel.event_stream import AutonomyEvent, InMemoryEventStream, utc_now
from packages.autonomy_kernel.kernel.consciousness_loop import AutonomyKernel
from packages.autonomy_kernel.models import SelfModelSnapshot, WorldModelSnapshot


def test_event_stream_append_consume_clear() -> None:
    stream = InMemoryEventStream()
    stream.append_event(AutonomyEvent("e", utc_now(), "test", "autonomy.insight", 1, "Title", "Summary"))
    assert len(stream.list_events()) == 1
    assert len(stream.consume_events()) == 1
    assert stream.list_events() == []


def test_morning_brief_created() -> None:
    world = WorldModelSnapshot("w", 1, 1, 1, ["q"], [], [], utc_now())
    self_model = SelfModelSnapshot("s", 0, ["goal"], [], {"disk_free_gib": 100, "ram_free_gib": 8}, [], [], utc_now())
    kernel = AutonomyKernel(world, self_model)
    events = kernel.run_until_brief()
    assert any(event.event_type == "autonomy.morning_brief" for event in events)

