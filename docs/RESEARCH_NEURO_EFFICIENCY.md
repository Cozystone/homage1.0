# Research Note: Neuro-Efficiency Layer

Date: 2026-06-11

## Goal

Derive a practical architecture improvement for ATANOR from brain-inspired
AI research: sparse event processing, neuromorphic principles, modular routing,
continual learning, few-shot memory, self-supervision, and energy-aware
compression.

## Source Review

- Neftci, Mostafa, Zenke, "Surrogate Gradient Learning in Spiking Neural
  Networks" (2019): https://arxiv.org/abs/1901.09948
  - SNNs are attractive for sparse, event-based computation, but practical
    training normally needs surrogate-gradient approximations. Decision:
    introduce event gating now, defer full SNN replacement until there is a
    measurable workload and training harness.
- SpikingJelly / Fang et al. (2023): https://pmc.ncbi.nlm.nih.gov/articles/PMC10558124/
  - PyTorch-native SNN tooling makes later ANN-to-SNN or direct SNN experiments
    plausible. Decision: keep the ATANOR layer framework-neutral and expose
    event density as a future SNN integration metric.
- Kirkpatrick et al., "Overcoming catastrophic forgetting in neural networks"
  (EWC, 2017): https://arxiv.org/abs/1612.00796
  - Continual learning should protect important weights/memories instead of
    allowing broad plasticity. Decision: track protected modules, EWC-like
    lambda, and replay budget.
- Snell, Swersky, Zemel, "Prototypical Networks for Few-shot Learning" (2017):
  https://arxiv.org/abs/1703.05175
  - Compact prototypes are a simple, useful inductive bias for low-data
    adaptation. Decision: represent few-shot memory as slots instead of storing
    every example.
- He et al., "Masked Autoencoders Are Scalable Vision Learners" (2021):
  https://arxiv.org/abs/2111.06377
  - High-ratio masking can create efficient self-supervised learning signals.
    Decision: add masked reconstruction plus graph-edge prediction as local
    pretraining signals.
- Pruning deep neural networks survey (2024):
  https://link.springer.com/article/10.1007/s12559-024-10313-0
  - Compression is not one trick; pruning, quantization, distillation, and
    architecture design need to be scheduled as deployment levers. Decision:
    expose pruning target, quantization bits, and distillation note in the API.
- Intel Loihi architecture overview:
  https://open-neuromorphic.org/neuromorphic-computing/hardware/loihi-intel/
  - Neuromorphic hardware benefits from memory-compute proximity and
    asynchronous event scheduling. Decision: model the software analogue first:
    event density, active specialists, and compact memory.

## Structural Improvement

The immediate improvement is a new `Neuro-Efficiency Layer`, not a full rewrite
of ATANOR-Core into an SNN.

The layer computes:

- `event_gate`: estimated event density and sparsity from workload novelty and
  neuromorphic salience.
- `module_routing`: active specialist modules under a module budget.
- `learning_plan`: EWC-style continual protection, few-shot prototype memory,
  and self-supervised masking settings.
- `compression`: pruning, quantization, distillation, and checkpointing levers.
- `energy_estimate`: dense vs event/modular/compressed scheduled compute units.

This gives ATANOR a measurable low-resource control surface while preserving
the current deterministic Alpha pipeline.

## Implementation

- Python package: `packages/neuro_efficiency`
- FastAPI route: `GET/POST /api/neuro/plan`
- Next.js fallback route: `apps/web/app/api/neuro/plan/route.ts`
- BakeBoard panel: "Neuro-Efficiency Layer"

The panel visualizes estimated compute reduction, event sparsity, active
modules, precision, continual learning protection, prototype memory, masking,
and compression.

## Next Research Milestones

1. Log real token/event traces from DataGate and GraphRAG queries.
2. Compare deterministic event gating with a small trainable salience model.
3. Run a local SNN toy experiment with SpikingJelly against the same event
   density metric.
4. Add calibration tests for 8-bit quantization on Guardrail and GraphRAG
   outputs.
5. Persist continual-learning snapshots so EWC/prototype settings affect real
   update decisions instead of only planning.
