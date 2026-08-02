from __future__ import annotations

import hashlib
from typing import Any

from .executive_critic import score_candidate
from .storage import DEFAULT_CORTEX_ROOT, append_jsonl, ensure_cortex_dirs, now_iso


VALID_MODES = {"near_walk", "far_walk", "analogy_walk", "counterfactual_walk", "constraint_walk"}


def _candidate_id(seed: str) -> str:
    return f"cc_{hashlib.sha256(seed.encode('utf-8')).hexdigest()[:16]}"


def run_creative_walk(prompt: str, mode: str = "far_walk") -> dict[str, Any]:
    ensure_cortex_dirs()
    mode = mode if mode in VALID_MODES else "far_walk"
    base = prompt.strip()[:280] or "ATANOR graph idea"
    templates = {
        "near_walk": [
            f"Map '{base}' to adjacent Seed/Cloud nodes and explain only the closest verified path.",
            f"Use a bounded salience frame to separate direct evidence from weak context for '{base}'.",
        ],
        "far_walk": [
            f"Recombine '{base}' with distant graph resonance: local trace + public fragment + crystal candidate.",
            f"Search for a non-obvious bridge where '{base}' can become a transparent planning path.",
        ],
        "analogy_walk": [
            f"Treat '{base}' like a circuit: activation, inhibition, prediction error, and crystal reuse.",
            f"Map '{base}' to a city relay: anchors are hubs, cloud shards are temporary roads.",
        ],
        "counterfactual_walk": [
            f"If '{base}' cannot use remote Cloud Brain, keep a single-peer contributor path and mark all claims as local proof.",
            f"If evidence for '{base}' is missing, generate questions rather than facts.",
        ],
        "constraint_walk": [
            f"Implement '{base}' under local-only, no external LLM, no Local Brain write constraints.",
            f"Bound '{base}' by top-k workspace, render budget, and privacy-preserving contributor shards.",
        ],
    }
    candidates = [
        {
            "candidate_id": _candidate_id(f"{mode}:{base}:{index}"),
            "mode": mode,
            "idea": idea,
            "stored_as_truth": False,
            "stored_as_idea_candidate": True,
        }
        for index, idea in enumerate(templates[mode])
    ]
    scores = [score_candidate(candidate) for candidate in candidates]
    by_id = {score["candidate_id"]: score for score in scores}
    recommended = sorted(candidates, key=lambda row: by_id[row["candidate_id"]]["score"], reverse=True)[:2]
    result = {
        "creative_run_id": f"cw_{hashlib.sha256(f'{mode}:{base}:{now_iso()}'.encode('utf-8')).hexdigest()[:18]}",
        "prompt": prompt,
        "mode": mode,
        "candidates": candidates,
        "critic_scores": scores,
        "recommended_candidates": recommended,
        "stored_as_truth": False,
        "stored_as_idea_candidate": True,
        "external_llm_used": False,
        "external_sllm_used": False,
        "local_brain_write": False,
    }
    append_jsonl(DEFAULT_CORTEX_ROOT / "creative_candidates.jsonl", {**result, "recorded_at": now_iso()})
    return result
