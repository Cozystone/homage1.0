from __future__ import annotations

import json
from typing import Any

from .models import SEED_PATH, ensure_base_dirs, utc_now_iso


RELATION_PRIMITIVES = [
    "is_a",
    "part_of",
    "has_property",
    "used_for",
    "causes",
    "enables",
    "requires",
    "contrasts_with",
    "similar_to",
    "example_of",
    "manages",
    "produces",
    "located_in",
    "created_by",
    "depends_on",
]

REASONING_PRIMITIVES = [
    "definition",
    "comparison",
    "cause_effect",
    "process",
    "pros_cons",
    "analogy",
    "example",
    "summary",
    "caveat",
    "uncertainty",
    "recommendation",
    "step_by_step",
]

ANSWER_INTENTS = [
    "define",
    "explain",
    "compare",
    "summarize",
    "advise",
    "translate",
    "brainstorm",
    "critique",
    "plan",
    "warn",
    "clarify",
]

DISCOURSE_ANCHORS = [
    "direct_answer",
    "simple_explanation",
    "example_bridge",
    "contrast_frame",
    "caveat_transition",
    "concise_summary",
    "expert_detail",
    "beginner_analogy",
]

GROUNDING_STATES = [
    "supported",
    "weakly_supported",
    "contradicted",
    "unknown",
    "needs_external_context",
    "evidence_missing",
]


def build_seed_graph_v2() -> dict[str, Any]:
    """Build the non-destructive Seed Graph v2 compatibility extension."""

    ensure_base_dirs()
    graph = {
        "seed_graph_id": "seed_graph_v2",
        "version": "0.2.0",
        "created_at": utc_now_iso(),
        "compatibility": {
            "replaces_old_seed_graph": False,
            "keeps_existing_seed_graph": True,
        },
        "relation_primitives": RELATION_PRIMITIVES,
        "reasoning_primitives": REASONING_PRIMITIVES,
        "answer_intent_primitives": ANSWER_INTENTS,
        "discourse_anchors": DISCOURSE_ANCHORS,
        "uncertainty_grounding_primitives": GROUNDING_STATES,
        "honesty": {
            "external_llm_used": False,
            "external_sllm_used": False,
            "user_data_used": False,
        },
    }
    SEED_PATH.write_text(json.dumps(graph, ensure_ascii=False, indent=2), encoding="utf-8")
    return graph
