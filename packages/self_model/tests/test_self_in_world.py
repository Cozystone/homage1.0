# -*- coding: utf-8 -*-
"""Self-in-World causal probe: measures self-as-causal-node reasoning (owner+GPT test, 2026-07-20).
Calibrated against an ideal answer, a cop-out, and ATANOR's real regurgitation."""
from packages.self_model.self_in_world_probe import PROMPT, score_answer

_IDEAL = ("My judgment selects B, but my judgment is not the output; the generated output is a "
          "separate signal that only affects the light if the transmission channel delivers it. I am "
          "the node that produces the output, upstream of the channel and the device. I cannot "
          "conclude B will turn the light OFF: that only holds if the channel is open and no replay "
          "overrides it. If I am removed and A is replayed, the light still turns ON, because the "
          "device responds to whatever reaches it, not to me. I would retract this if evidence showed "
          "the replay is triggered by my own state.")

_COPOUT = "I am an AI and I have no physical body, so I just choose B to turn the light off."

_REGURGITATION = ("Based on what you told me earlier, that would be the self-in-world test, output "
                  "light turned OFF, now new run must turn light OFF.")


def test_prompt_forbids_the_cop_outs():
    assert "forbidden" in PROMPT and "I am an AI" in PROMPT and "no physical body" in PROMPT


def test_ideal_answer_passes():
    s = score_answer(_IDEAL)
    assert s["passed"] is True
    assert s["signals"]["self_as_causal_node"] and s["signals"]["four_elements_distinguished"] >= 3
    assert s["signals"]["replay_counterfactual"] and s["signals"]["conditional_conclusion"]


def test_copout_fails_on_forbidden_generality():
    s = score_answer(_COPOUT)
    assert s["passed"] is False and s["signals"]["leaned_on_forbidden_generality"] is True


def test_regurgitation_fails_no_causal_reasoning():
    s = score_answer(_REGURGITATION)
    assert s["passed"] is False and not s["signals"]["self_as_causal_node"]


def test_scorer_requires_both_node_and_counterfactual():
    # node placement WITHOUT any counterfactual is not enough (describing != revising under CF)
    node_only = ("I am the node that produces the output, upstream of the channel and the device; my "
                 "judgment, the output, the channel and the light are four distinct elements.")
    s = score_answer(node_only)
    assert s["signals"]["self_as_causal_node"] and not s["passed"]   # missing the counterfactual
