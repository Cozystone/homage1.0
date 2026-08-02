# -*- coding: utf-8 -*-
"""Mechanism-proof harness (docs/ATANOR_vjepa_fusion.md §7) — the deliverable, run as a test.

On a rendered synthetic world with ground-truth events, it asserts the ROBUST, honest invariants of
the fusion (not a hoped-for effect size that could flake):

  * the coder is inside the neuro-budget and does not collapse;
  * on the HELD-OUT sequence (generalization, not memorization) latent event-marking beats the pixel
    retinal-delta baseline overall (AP);
  * on the high-pixel-delta lighting NON-event, latent false-fires strictly less than the pixel delta
    (the V-JEPA invariance win);
  * on the low-pixel-delta sub-symbolic event, the discrete scene-graph baseline is STRUCTURALLY blind
    (recall 0) while latent catches it (recall > 0) — the complementarity the design predicts.

The measured effect sizes and the full BETTER/EQUAL/WORSE verdict live in ``run_mechanism_proof``'s
printed scorecard; here we only pin what must always hold."""
from __future__ import annotations

from packages.perception.vjepa_harness import generate, run_mechanism_proof


def test_generated_world_has_disjoint_ground_truth_classes():
    """The audit's ground truth must be clean: sub-symbolic events are NOT scene-graph changes, and the
    adversarial non-events are not secretly events."""
    seq = generate(90001, scripted=True)
    assert seq.subsymbolic and not (seq.subsymbolic & seq.symbolic)
    assert seq.lighting and not (seq.lighting & seq.event_frames())
    assert seq.noise and not (seq.noise & seq.event_frames())


def test_mechanism_proof_invariants():
    r = run_mechanism_proof(epochs=120, n_train=6, verbose=False)

    # neuro-budget + no collapse
    assert r["param_count"] < 1_000_000
    assert r["param_count_incl_target"] <= 25_000_000
    assert r["collapse"]["ok"] is True and r["collapse"]["latent_std_min"] > 1e-2

    v = r["verdict"]
    # generalization: on the held-out sequence latent beats the pixel baseline overall (AP)
    assert v["latent_ap"] > v["pixel_ap"], v

    # adversarial 1 — high-pixel-delta lighting NON-event: latent false-fires strictly less than pixel
    assert v["latent_fp_lighting"] < v["pixel_fp_lighting"], v

    # adversarial 2 — low-pixel-delta sub-symbolic event: discrete is structurally blind, latent is not
    assert v["discrete_recall_subsymbolic"] == 0.0, v
    assert v["latent_recall_subsymbolic"] > 0.0, v
