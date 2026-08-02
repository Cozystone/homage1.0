from __future__ import annotations

from packages.continuous_self.loop import ContinuousSelf
from packages.continuous_self.self_state import Observation


def test_step_advances_and_persists(tmp_path):
    obs = Observation(learning_active=True, concepts_delta=4)
    cs = ContinuousSelf(tmp_path / "self.json", lambda: obs)
    t0 = cs.state.ticks
    cs.step()
    assert cs.state.ticks == t0 + 1
    assert (tmp_path / "self.json").exists(), "the self persists after each step"
    snap = cs.snapshot()
    assert snap["continuous"] is True and "vitals" in snap


def test_faulty_sensor_never_kills_the_life(tmp_path):
    def boom() -> Observation:
        raise RuntimeError("sensor down")

    cs = ContinuousSelf(tmp_path / "self.json", boom)
    cs.step()  # must not raise
    assert cs.state.ticks == 1


def test_resume_continuity_through_the_loop(tmp_path):
    path = tmp_path / "self.json"
    a = ContinuousSelf(path, lambda: Observation(concepts_delta=2))
    a.step()
    born = a.state.born_at
    # a "restart": a brand-new ContinuousSelf pointed at the same persisted file
    b = ContinuousSelf(path, lambda: Observation())
    assert b.state.born_at == born, "the restarted loop resumes the SAME self"
    assert b.state.resumed_count == 1
