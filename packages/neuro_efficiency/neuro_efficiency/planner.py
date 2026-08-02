from __future__ import annotations

from datetime import datetime, timezone
import re
from typing import Any


DEFAULT_WORKLOAD = (
    "Brain-inspired Alpha workload: SNN event processing, neuromorphic memory, "
    "modular GraphRAG, continual learning, few-shot prototypes, self-supervised "
    "masking, pruning, quantization, distillation, guardrail verification, and "
    "low-power deployment."
)

MODULES = [
    {
        "id": "event_gate",
        "name": "SNN Event Gate",
        "role": "Route only salient state changes into downstream modules.",
        "keywords": {"snn", "spike", "spiking", "event", "events", "neuromorphic", "lowpower", "low-power"},
    },
    {
        "id": "modular_router",
        "name": "Modular Specialist Router",
        "role": "Activate a small expert set instead of the whole model.",
        "keywords": {"module", "modular", "specialist", "distributed", "router", "hybrid"},
    },
    {
        "id": "memory_consolidator",
        "name": "Continual Memory",
        "role": "Protect important memories with EWC-style consolidation and replay.",
        "keywords": {"continual", "ewc", "forgetting", "plasticity", "memory", "synapse", "synaptic"},
    },
    {
        "id": "prototype_memory",
        "name": "Few-Shot Prototype Memory",
        "role": "Store compact class/task prototypes for one-shot adaptation.",
        "keywords": {"few", "fewshot", "few-shot", "one", "oneshot", "one-shot", "prototype", "small", "data"},
    },
    {
        "id": "masking_teacher",
        "name": "Self-Supervised Masking",
        "role": "Pretrain from local unlabeled data with masked reconstruction tasks.",
        "keywords": {"self", "selfsupervised", "self-supervised", "mask", "masked", "contrastive", "mae"},
    },
    {
        "id": "compression_distiller",
        "name": "Compression Distiller",
        "role": "Schedule pruning, quantization, and distillation for low-resource runs.",
        "keywords": {"pruning", "prune", "quantization", "quantize", "distillation", "distill", "efficient", "energy"},
    },
    {
        "id": "graph_guard",
        "name": "GraphRAG Guard Verifier",
        "role": "Ground responses against ontology evidence and guardrail checks.",
        "keywords": {"graphrag", "graph", "ontology", "evidence", "guard", "guardrail", "verify", "reasoning"},
    },
]

RESEARCH_BASIS = [
    {
        "topic": "Surrogate-gradient SNN training",
        "source": "Neftci, Mostafa, Zenke, 2019",
        "url": "https://arxiv.org/abs/1901.09948",
        "decision": "Use event sparsity as a first software control point before replacing core models with SNNs.",
    },
    {
        "topic": "SpikingJelly SNN framework",
        "source": "Fang et al., 2023",
        "url": "https://pmc.ncbi.nlm.nih.gov/articles/PMC10558124/",
        "decision": "Keep SNN integration framework-friendly so future PyTorch/SNN experiments can plug in.",
    },
    {
        "topic": "Elastic Weight Consolidation",
        "source": "Kirkpatrick et al., 2017",
        "url": "https://arxiv.org/abs/1612.00796",
        "decision": "Track protected modules and replay budget to reduce catastrophic forgetting.",
    },
    {
        "topic": "Prototypical Networks",
        "source": "Snell, Swersky, Zemel, 2017",
        "url": "https://arxiv.org/abs/1703.05175",
        "decision": "Represent few-shot memory as compact prototypes instead of full examples.",
    },
    {
        "topic": "Masked Autoencoders",
        "source": "He et al., 2021",
        "url": "https://arxiv.org/abs/2111.06377",
        "decision": "Use high-mask self-supervised reconstruction for cheap local adaptation signals.",
    },
    {
        "topic": "Model compression survey",
        "source": "Pruning Deep Neural Networks for Green Energy-Efficient Models, 2024",
        "url": "https://link.springer.com/article/10.1007/s12559-024-10313-0",
        "decision": "Expose pruning, quantization, and distillation as explicit deployment levers.",
    },
]


def build_neuro_efficiency_plan(workload: dict[str, Any] | None = None) -> dict[str, Any]:
    profile = workload or {}
    text = str(profile.get("text") or DEFAULT_WORKLOAD)
    task_type = str(profile.get("task_type") or "alpha-dashboard")
    target_device = str(profile.get("target_device") or "low-spec-cpu-gpu")
    token_budget = _bounded_int(profile.get("token_budget"), default=512, minimum=64, maximum=8192)
    module_budget = _bounded_int(profile.get("module_budget"), default=4, minimum=2, maximum=len(MODULES))

    tokens = _tokenize(text)
    token_count = max(1, len(tokens))
    event_gate = _event_gate(tokens, token_budget)
    modules = _score_modules(tokens)
    active_modules = _active_modules(modules, module_budget)
    compression = _compression_plan(event_gate["sparsity"], target_device)
    learning_plan = _learning_plan(tokens, active_modules, task_type)
    energy_estimate = _energy_estimate(token_count, len(modules), len(active_modules), event_gate, compression)

    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "architecture": "ATANOR Neuro-Efficiency Layer",
        "objective": "Run adaptive AI workloads with sparse events, modular routing, compact memory, and explicit compression controls.",
        "workload": {
            "task_type": task_type,
            "target_device": target_device,
            "token_count": token_count,
            "token_budget": token_budget,
        },
        "event_gate": event_gate,
        "module_routing": {
            "budget": module_budget,
            "active_modules": [module["id"] for module in active_modules],
            "modules": modules,
        },
        "learning_plan": learning_plan,
        "compression": compression,
        "energy_estimate": energy_estimate,
        "recommendations": _recommendations(event_gate, active_modules, compression, learning_plan),
        "research_basis": RESEARCH_BASIS,
    }


def _tokenize(text: str) -> list[str]:
    tokens = re.findall(r"[A-Za-z0-9][A-Za-z0-9_-]*", text.lower())
    return tokens or _tokenize(DEFAULT_WORKLOAD)


def _bounded_int(value: Any, *, default: int, minimum: int, maximum: int) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        parsed = default
    return max(minimum, min(maximum, parsed))


def _clamp(value: float, minimum: float, maximum: float) -> float:
    return max(minimum, min(maximum, value))


def _round(value: float) -> float:
    return round(value, 3)


def _event_gate(tokens: list[str], token_budget: int) -> dict[str, Any]:
    token_count = len(tokens)
    unique_ratio = len(set(tokens)) / max(1, token_count)
    transitions = sum(1 for index in range(1, token_count) if tokens[index] != tokens[index - 1])
    transition_ratio = transitions / max(1, token_count - 1)
    salient_terms = {
        "snn",
        "spiking",
        "event",
        "neuromorphic",
        "continual",
        "few-shot",
        "self-supervised",
        "pruning",
        "quantization",
        "distillation",
        "graphrag",
        "guardrail",
    }
    salience_ratio = sum(1 for token in tokens if token in salient_terms) / max(1, token_count)
    event_density = _clamp(0.16 + unique_ratio * 0.26 + transition_ratio * 0.18 + salience_ratio * 0.26, 0.2, 0.72)
    active_events = max(1, round(token_count * event_density))
    budget_pressure = _clamp(token_count / max(1, token_budget), 0.05, 2.0)
    latency_mode = "burst" if budget_pressure < 0.45 else "adaptive" if budget_pressure < 1.0 else "throttled"
    return {
        "event_density": _round(event_density),
        "sparsity": _round(1.0 - event_density),
        "active_events": active_events,
        "suppressed_events": max(0, token_count - active_events),
        "latency_mode": latency_mode,
        "trigger": "token novelty + neuromorphic salience",
    }


def _score_modules(tokens: list[str]) -> list[dict[str, Any]]:
    token_set = set(tokens)
    scored = []
    for module in MODULES:
        matches = len(token_set.intersection(module["keywords"]))
        score = _clamp(0.22 + matches * 0.16, 0.05, 0.98)
        state = "active" if score >= 0.38 else "standby"
        scored.append(
            {
                "id": module["id"],
                "name": module["name"],
                "role": module["role"],
                "score": _round(score),
                "state": state,
            }
        )
    return sorted(scored, key=lambda item: item["score"], reverse=True)


def _active_modules(modules: list[dict[str, Any]], module_budget: int) -> list[dict[str, Any]]:
    active = [module for module in modules if module["state"] == "active"][:module_budget]
    if len(active) < 3:
        active = modules[: min(module_budget, 3)]
    return active


def _compression_plan(sparsity: float, target_device: str) -> dict[str, Any]:
    low_power_target = any(fragment in target_device.lower() for fragment in ("low", "edge", "fpga", "neuromorphic", "cpu"))
    pruning_target = 0.38 if low_power_target else 0.25
    if sparsity > 0.55:
        pruning_target += 0.07
    quantization_bits = 8 if low_power_target else 16
    return {
        "pruning_target": _round(_clamp(pruning_target, 0.15, 0.55)),
        "quantization_bits": quantization_bits,
        "distillation": "self-distill active specialists into a compact student checkpoint",
        "activation_checkpointing": low_power_target,
        "deployment_note": "Prefer event-sparse batches before hardware-specific SNN or FPGA kernels.",
    }


def _learning_plan(tokens: list[str], active_modules: list[dict[str, Any]], task_type: str) -> dict[str, Any]:
    unique_count = len(set(tokens))
    prototype_slots = max(8, min(64, unique_count // 2 + len(active_modules) * 2))
    mask_ratio = 0.42 if "vision" not in task_type.lower() else 0.75
    protected_modules = [
        module["id"]
        for module in active_modules
        if module["id"] in {"memory_consolidator", "prototype_memory", "graph_guard", "modular_router"}
    ]
    if not protected_modules:
        protected_modules = [module["id"] for module in active_modules[:2]]
    return {
        "continual": {
            "strategy": "EWC-style consolidation + tiny replay buffer",
            "ewc_lambda": 0.42,
            "replay_budget": prototype_slots,
            "protected_modules": protected_modules,
        },
        "few_shot": {
            "strategy": "cosine prototype memory",
            "prototype_slots": prototype_slots,
            "update_rule": "merge low-distance examples; fork high-novelty examples",
        },
        "self_supervised": {
            "strategy": "masked span reconstruction + graph edge prediction",
            "mask_ratio": mask_ratio,
            "local_signal": "use accepted DataGate documents and Ontology Forge edges",
        },
    }


def _energy_estimate(
    token_count: int,
    module_count: int,
    active_module_count: int,
    event_gate: dict[str, Any],
    compression: dict[str, Any],
) -> dict[str, Any]:
    dense_cost = float(token_count * module_count * 32)
    quantization_factor = compression["quantization_bits"] / 32
    pruning_factor = 1.0 - compression["pruning_target"]
    routing_factor = active_module_count / max(1, module_count)
    efficient_cost = dense_cost * event_gate["event_density"] * quantization_factor * pruning_factor * routing_factor
    reduction = _clamp(1.0 - efficient_cost / dense_cost, 0.0, 0.98)
    return {
        "dense_cost_units": round(dense_cost, 2),
        "efficient_cost_units": round(efficient_cost, 2),
        "reduction_ratio": _round(reduction),
        "summary": f"{round(reduction * 100)}% fewer scheduled compute units estimated",
    }


def _recommendations(
    event_gate: dict[str, Any],
    active_modules: list[dict[str, Any]],
    compression: dict[str, Any],
    learning_plan: dict[str, Any],
) -> list[str]:
    recommendations = [
        "Keep the transformer/GraphRAG path as the reference brain while testing event-gated specialists.",
        "Log active event density per run so pruning and quantization decisions use measured workload sparsity.",
        "Protect ontology and guard memories during continual updates before allowing broad model plasticity.",
    ]
    if event_gate["sparsity"] < 0.45:
        recommendations.append("Raise salience thresholds or add temporal batching before trying low-power hardware.")
    if compression["quantization_bits"] == 8:
        recommendations.append("Validate 8-bit quantization on guard and retrieval outputs before enabling for all modules.")
    if learning_plan["few_shot"]["prototype_slots"] < 16:
        recommendations.append("Collect more accepted examples before relying on prototype memory for routing.")
    if not any(module["id"] == "event_gate" for module in active_modules):
        recommendations.append("Force the event gate on for edge deployments even when workload salience is low.")
    return recommendations
