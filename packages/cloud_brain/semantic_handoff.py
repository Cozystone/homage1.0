from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .semantic_attach import attach_semantic_cloud_for_query
from .semantic_store import DEFAULT_SEMANTIC_CLOUD_ROOT, get_semantic_cloud_growth_status, utc_now_iso


HANDOFF_JSON_PATH = DEFAULT_SEMANTIC_CLOUD_ROOT / "proofs" / "semantic_cloud_growth_handoff.json"
HANDOFF_MD_PATH = DEFAULT_SEMANTIC_CLOUD_ROOT / "proofs" / "semantic_cloud_growth_handoff.md"


def write_semantic_cloud_growth_handoff(
    *,
    browser_verification_url: str = "http://127.0.0.1:3022/?lang=ko&section=cloud&workspace=lab",
    root: str | Path = DEFAULT_SEMANTIC_CLOUD_ROOT,
) -> dict[str, Any]:
    status = get_semantic_cloud_growth_status(root)
    attach = attach_semantic_cloud_for_query("쿠버네티스가 뭐야?", limit=8, cloud_root=root)
    handoff = {
        "handoff_id": "semantic_cloud_growth_handoff",
        "generated_at": utc_now_iso(),
        "proof_store_path": status["proof_store_path"],
        "concepts": status["concepts"],
        "relations": status["relations"],
        "evidence": status["evidence"],
        "last_growth_run": status.get("last_growth_run"),
        "duplicate_merge_behavior": "Duplicate concepts merge by deterministic canonical ID; repeated relations increment seen_count and bounded weight.",
        "attach_behavior": {
            "temporary": attach["temporary"],
            "attached_nodes": len(attach["attached_nodes"]),
            "attached_edges": len(attach["attached_edges"]),
            "local_brain_write": attach["local_brain_write"],
            "cloud_attached_counts_as_local": attach["cloud_attached_counts_as_local"],
        },
        "local_brain_write": False,
        "external_llm_used": False,
        "external_sllm_used": False,
        "old_mirror_snapshot_used_as_live_cloud": False,
        "global_cloud_claim": False,
        "proof_store_only": True,
        "browser_verification_url": browser_verification_url,
        "known_limitations": [
            "deterministic_v0_extraction_only",
            "small_local_proof_store",
            "not_global_cloud",
            "not_web_scale",
            "not_perfect_semantic_parser",
            "not_full_cross_lingual_entity_resolution",
        ],
    }
    HANDOFF_JSON_PATH.parent.mkdir(parents=True, exist_ok=True)
    HANDOFF_JSON_PATH.write_text(json.dumps(handoff, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    HANDOFF_MD_PATH.write_text(
        "\n".join(
            [
                "# Semantic Cloud Growth Loop Handoff",
                "",
                f"- Generated: {handoff['generated_at']}",
                f"- Proof store: `{handoff['proof_store_path']}`",
                f"- Concepts: {handoff['concepts']}",
                f"- Relations: {handoff['relations']}",
                f"- Evidence: {handoff['evidence']}",
                f"- Local Brain write: {handoff['local_brain_write']}",
                f"- External LLM used: {handoff['external_llm_used']}",
                f"- External sLLM used: {handoff['external_sllm_used']}",
                f"- Old mirror snapshot used as live cloud: {handoff['old_mirror_snapshot_used_as_live_cloud']}",
                f"- Browser verification URL: {handoff['browser_verification_url']}",
                "",
                "## Duplicate Merge Behavior",
                handoff["duplicate_merge_behavior"],
                "",
                "## Attach Behavior",
                f"- Temporary nodes: {handoff['attach_behavior']['attached_nodes']}",
                f"- Temporary edges: {handoff['attach_behavior']['attached_edges']}",
                f"- Cloud attached counts as local: {handoff['attach_behavior']['cloud_attached_counts_as_local']}",
                "",
                "## Known Limitations",
                *[f"- {item}" for item in handoff["known_limitations"]],
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    return handoff


def main() -> None:
    print(json.dumps(write_semantic_cloud_growth_handoff(), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
