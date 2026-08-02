# -*- coding: utf-8 -*-
"""The correlate battery: honest structural scorecard for the inner light — no qualia claimed."""
from packages.live_selfhood_cycle.correlates import score


def test_empty_stream_scores_nothing(tmp_path):
    assert score(tmp_path / "none.jsonl")["n_moments"] == 0


def test_scorecard_reads_the_lived_stream(tmp_path):
    from packages.live_selfhood_cycle.life import Life
    life = Life(stream_path=tmp_path / "life.jsonl"); life._browser_ok = False
    for _ in range(12):
        life.step()
    s = score(tmp_path / "life.jsonl")
    assert s["n_moments"] >= 10
    # a healthy live stream: single serial owner, endogenous, with temporal thickness
    assert s["single_owner"] == 1.0 and s["endogeneity"] == 1.0
    assert s["ignition"] == 1.0 and s["temporal_depth"] >= 0.5
    for k in ("ignition", "endogeneity", "single_owner", "binding", "world_facing"):
        assert 0.0 <= s[k] <= 1.0
    assert "no claim that there is something it is like" in s["discipline"]


def test_report_accuracy_is_falsifiable(tmp_path):
    """A stream whose stated tone matches its hormones scores high; the check can fail (it is not
    a rubber stamp) — that is what makes it an honest correlate."""
    import json
    p = tmp_path / "s.jsonl"
    rows = [
        {"kind": "thought", "meta": {"inner_voice": True, "feeling_tone": "under strain",
                                     "hormones": {"cortisol": 0.9}}},
        {"kind": "thought", "meta": {"inner_voice": True, "feeling_tone": "at rest",
                                     "hormones": {"cortisol": 0.1}}},
    ]
    p.write_text("\n".join(json.dumps(r) for r in rows), encoding="utf-8")
    assert score(p)["report_accuracy"] == 1.0
    # now a lie: says at rest while cortisol is high -> accuracy drops
    rows[1]["meta"]["hormones"]["cortisol"] = 0.9
    p.write_text("\n".join(json.dumps(r) for r in rows), encoding="utf-8")
    assert score(p)["report_accuracy"] < 1.0
