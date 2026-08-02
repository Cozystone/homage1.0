from __future__ import annotations

import hashlib
from collections import Counter
from typing import Any


SEED_PRIMITIVES = (
    "definition",
    "comparison",
    "cause",
    "effect",
    "evidence",
    "uncertainty",
    "process",
    "example",
    "analogy",
    "claim",
    "source",
    "verification",
    "user_intent",
    "audience_level",
    "style_request",
    "grounding_requirement",
    "refusal_boundary",
    "concise_answer",
    "native_korean_flow",
)


def local_seed_fingerprint(active_context: str | None = None) -> dict[str, Any]:
    context_terms = [term.casefold() for term in (active_context or "").replace("?", " ").replace(",", " ").split() if len(term) > 1]
    primitive_counts: Counter[str] = Counter({primitive: 1 for primitive in SEED_PRIMITIVES})
    for term in context_terms:
        for primitive in SEED_PRIMITIVES:
            if term in primitive or primitive in term:
                primitive_counts[primitive] += 1
    relation_histogram = {
        "semantic": primitive_counts["definition"] + primitive_counts["claim"],
        "evidence": primitive_counts["evidence"] + primitive_counts["verification"],
        "surface": primitive_counts["style_request"] + primitive_counts["native_korean_flow"],
        "planning": primitive_counts["user_intent"] + primitive_counts["process"],
    }
    encoded = "|".join(f"{key}:{primitive_counts[key]}" for key in sorted(primitive_counts))
    fingerprint_hash = hashlib.sha256(encoded.encode("utf-8")).hexdigest()
    return {
        "fingerprint_hash": fingerprint_hash,
        "primitive_distribution_hash": hashlib.sha256(repr(sorted(primitive_counts.items())).encode("utf-8")).hexdigest(),
        "relation_type_histogram": relation_histogram,
        "sqc_domain_vector_hash": hashlib.sha256("|".join(sorted(SEED_PRIMITIVES)).encode("utf-8")).hexdigest(),
        "phase_signature_summary": {
            "seed_primitives": len(SEED_PRIMITIVES),
            "context_terms_hashed": hashlib.sha256(" ".join(context_terms).encode("utf-8")).hexdigest()[:18] if context_terms else "none",
        },
        "raw_local_graph_included": False,
        "private_text_included": False,
    }
