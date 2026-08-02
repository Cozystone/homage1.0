"""PHFE v0.4b — compare_mode (the first rung of the driver ladder).

`compare_mode` is the SAFE first step of promoting the fold from hidden trace
toward an answer driver (spec §7): the folded structure produces a *recommended*
reasoning core, which we compare against the path the current engine actually
used — and only LOG the agreement. The answer is never changed here
(`answer_changed = False`, `fold_driver_mode = "compare_mode"`).

Pure functions, no side effects.
"""

from __future__ import annotations

from typing import Any

from .folding import FoldedState


def folded_core(folded_state: FoldedState, *, top_k: int = 5,
                namespace: str | None = None) -> list[str]:
    """Return the central-core node_ids: high coherence, near the center.

    core_score = coherence / (1 + radius). Central, stable, well-supported nodes
    win — these are the rail the folded structure 'recommends'.

    `namespace` (e.g. "concept:") restricts the core to one node family: the field
    also holds emotion/self nodes that can never appear in answer evidence, and a
    core containing them makes any evidence comparison structurally zero (measured
    live: agreement 0.0 on every battery question before this filter existed).
    """

    scored = [
        (node.coherence / (1.0 + node.radius), node.node_id)
        for node in folded_state.nodes
        if namespace is None or str(node.node_id).startswith(namespace)
    ]
    # deterministic: score desc, then node_id asc
    scored.sort(key=lambda item: (-item[0], item[1]))
    return [node_id for _, node_id in scored[: max(0, top_k)]]


def compare_fold_to_answer(
    folded_state: FoldedState,
    answer_evidence_ids: list[str] | tuple[str, ...],
    *,
    top_k: int = 5,
    namespace: str | None = "concept:",
) -> dict[str, Any]:
    """Compare the folded core to the answer's evidence — log only, no change.

    `answer_evidence_ids` are the node_ids the current answer actually drew on
    (e.g. matched concepts / reasoning_certificate evidence). Returns agreement
    diagnostics; never alters the answer. The core is restricted to the evidence's
    namespace so the comparison is apples-to-apples.
    """

    core = folded_core(folded_state, top_k=top_k, namespace=namespace)
    core_set = set(core)
    evidence_set = {str(item) for item in answer_evidence_ids if str(item).strip()}
    overlap = core_set & evidence_set
    union = core_set | evidence_set

    jaccard = (len(overlap) / len(union)) if union else 0.0
    recall = (len(overlap) / len(evidence_set)) if evidence_set else 0.0

    return {
        "fold_driver_mode": "compare_mode",
        "answer_changed": False,
        "answer_source_unchanged": True,
        "folded_core": core,
        "answer_evidence": sorted(evidence_set),
        "agreement_overlap": len(overlap),
        "agreement_jaccard": round(jaccard, 4),
        "agreement_recall": round(recall, 4),
        "global_coherence": folded_state.metadata.get("global_coherence"),
        "active_node_count": folded_state.metadata.get("active_node_count"),
        "original_brain_state_mutated": False,
        "external_llm_used": False,
        "local_brain_write": False,
        "candidate_promotion": False,
        "note": (
            "Folded core is compared to the current answer's evidence for logging "
            "only. The answer is produced by the existing engine; the fold does not "
            "drive it at this stage."
        ),
    }
