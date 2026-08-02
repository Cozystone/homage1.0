# -*- coding: utf-8 -*-
"""The learner's topic selection must CONSUME the failure-receipt steer — avoiding junk domains and
jumping toward knowledge gaps — closing the self-correction loop. Tests the pure chooser."""
from packages.autonomy_kernel.intrinsic_drive import _steer_topic


def test_no_bias_takes_top_frontier_candidate():
    assert _steer_topic(["양자컴퓨터", "블랙홀"], {}) == "양자컴퓨터"


def test_avoids_junk_domain():
    bias = {"avoid_topics": [{"topic": "라리가일정"}], "seek_topics": [], "jump_probability": 0.15}

    assert _steer_topic(["라리가일정", "광합성"], bias, rng=lambda: 0.99) == "광합성"


def test_jumps_to_gap_under_jump_probability():
    bias = {"avoid_topics": [], "seek_topics": [{"topic": "상대성이론"}], "jump_probability": 0.8}
    # rng below jump_probability → jump toward the gap the engine keeps abstaining on
    assert _steer_topic(["아무거나"], bias, rng=lambda: 0.1, pick=lambda xs: xs[0]) == "상대성이론"


def test_high_jump_prob_still_respects_low_roll():
    bias = {"avoid_topics": [], "seek_topics": [{"topic": "상대성이론"}], "jump_probability": 0.8}
    # rng ABOVE jump_probability → do NOT jump; take the frontier candidate
    assert _steer_topic(["양자컴퓨터"], bias, rng=lambda: 0.95) == "양자컴퓨터"


def test_all_candidates_junk_falls_to_gap():
    bias = {"avoid_topics": [{"topic": "a"}, {"topic": "b"}],
            "seek_topics": [{"topic": "상대성이론"}], "jump_probability": 0.15}
    assert _steer_topic(["a", "b"], bias, rng=lambda: 0.99, pick=lambda xs: xs[0]) == "상대성이론"


def test_empty_everything_is_safe_default():
    assert _steer_topic([], {}) == "세상"


def test_closed_loop_record_to_steer(tmp_path):
    """The whole loop on the REAL functions: record failures → search_bias → the learner's chooser
    steers away from the junk domain and toward the knowledge gap."""
    import packages.flywheel.failure_receipts as fr
    fr._ARCHIVE = tmp_path / "r.jsonl"                        # isolate the ledger
    for _ in range(8):
        fr.record_receipt(topic="라리가일정", causes=["foreign"], source="critic", kind="junk")
    for _ in range(8):
        fr.record_receipt(topic="상대성이론", causes=["abstain"], source="flywheel", kind="gap")
    bias = fr.search_bias()
    # the junk domain is skipped even when it is the top frontier candidate
    assert _steer_topic(["라리가일정", "광합성"], bias, rng=lambda: 0.99) == "광합성"
    # a jump goes to the gap the engine keeps abstaining on
    assert _steer_topic(["라리가일정"], bias, rng=lambda: 0.0, pick=lambda xs: xs[0]) == "상대성이론"
