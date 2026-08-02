# -*- coding: utf-8 -*-
"""ARC-AGI No-LLM synthesis solver: a program must reproduce ALL train pairs before it answers."""
from packages.arc_agi.solver import (fractal, flip_h, crop_content, synthesize, solve_task)


def test_fractal_rule_007bbfb7():
    g = [[7, 0, 7], [7, 0, 7], [7, 7, 0]]
    out = fractal(g)
    assert len(out) == 9 and len(out[0]) == 9
    assert out[0][:3] == [7, 0, 7] and out[0][3:6] == [0, 0, 0]   # non-zero cell -> copy, zero -> blank


def test_synthesize_finds_flip_when_that_is_the_rule():
    train = [([[1, 2]], [[2, 1]]), ([[3, 4, 5]], [[5, 4, 3]])]
    prog = synthesize(train)
    assert prog is not None and prog([[9, 8]]) == [[8, 9]]        # learned horizontal flip


def test_synthesize_learns_colormap():
    train = [([[1, 1], [2, 2]], [[3, 3], [4, 4]])]
    prog = synthesize(train)
    assert prog is not None and prog([[1, 2]]) == [[3, 4]]        # 1->3, 2->4 consistent map


def test_verification_gate_abstains_when_no_program_fits():
    # the SAME input colour maps to DIFFERENT outputs across pairs -> no colour-map, no geometry, no
    # tiling reproduces it -> abstain (None). (A single pair can always be fit by some colour-map, so
    # two conflicting pairs are needed to prove the gate refuses.)
    train = [([[1, 1]], [[2, 2]]), ([[1, 1]], [[3, 3]])]
    prog = synthesize(train)
    assert prog is None                                          # never guesses


def test_solve_task_end_to_end_fractal():
    task = {"train": [{"input": [[1, 0], [0, 1]], "output": fractal([[1, 0], [0, 1]])}],
            "test": [{"input": [[2, 0], [0, 2]], "output": fractal([[2, 0], [0, 2]])}]}
    pred, solved = solve_task(task)
    assert solved is True                                        # synthesized fractal, verified, correct
