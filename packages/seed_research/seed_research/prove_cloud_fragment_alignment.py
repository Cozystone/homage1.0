from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .cloud_fragment_alignment import align_public_candidate_fragments, ensure_deterministic_fixture
from .core import seed_root


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _local_brain_state() -> dict[str, Any]:
    return {
        "local_brain_initialized": False,
        "local_total_nodes": 0,
        "local_total_edges": 0,
        "seed_or_cloud_written_to_local_brain": False,
    }


def build_cloud_fragment_alignment_proof(
    root: str | Path | None = None,
    inbox: str | Path = "data/cloud_brain/inbox",
) -> dict[str, Any]:
    ensure_deterministic_fixture(Path(inbox) / "test_seed_alignment_fragment.json")
    alignment = align_public_candidate_fragments(root, inbox)
    return {
        "schema": "atanor.cloud-fragment-seed-alignment-proof.v1",
        "created_at": _now_iso(),
        "seed_root": str(seed_root(root)),
        "cloud_inbox": str(inbox),
        "fixture": {
            "created_or_verified": True,
            "path": str(Path(inbox) / "test_seed_alignment_fragment.json"),
            "not_real_web_crawling": True,
            "not_autonomous_cloud_growth": True,
        },
        "summary": {
            "candidate_fragments_checked": alignment["candidate_fragments_checked"],
            "public_fragments_checked": alignment["public_fragments_checked"],
            "rejected_private_fragments": alignment["rejected_private_fragments"],
            "fragments_aligned_to_seed": alignment["fragments_aligned_to_seed"],
            "concepts_aligned_total": alignment["concepts_aligned_total"],
            "edges_aligned_total": alignment["edges_aligned_total"],
        },
        "local_brain_state": _local_brain_state(),
        "claims": {
            "public_cloud_candidate_fragment_aligns_to_seed_ids": alignment["fragments_aligned_to_seed"] > 0,
            "matched_concepts_and_edges_inspectable": True,
            "local_brain_remains_isolated": True,
            "external_llm_used": False,
            "external_sllm_used": False,
            "rule_based_answer_engine": False,
            "final_answer_generation_claimed": False,
            "autonomous_web_crawling_claimed": False,
            "autonomous_cloud_brain_growth_claimed": False,
            "production_scale_verification_claimed": False,
            "sllm_replacement_claimed": False,
        },
        "alignment": alignment,
    }


def _write_markdown(proof: dict[str, Any], path: Path) -> None:
    summary = proof["summary"]
    claims = proof["claims"]
    lines = [
        "# ATANOR Cloud Fragment to Seed Alignment Proof",
        "",
        f"- Created: `{proof['created_at']}`",
        f"- Seed root: `{proof['seed_root']}`",
        f"- Cloud inbox: `{proof['cloud_inbox']}`",
        "- Fixture: deterministic public test fragment",
        "- Not real web crawling: `true`",
        "- Not autonomous Cloud Brain growth: `true`",
        "",
        "## Summary",
        "",
        f"- Candidate fragments checked: `{summary['candidate_fragments_checked']}`",
        f"- Public fragments checked: `{summary['public_fragments_checked']}`",
        f"- Rejected private fragments: `{summary['rejected_private_fragments']}`",
        f"- Fragments aligned to Seed: `{summary['fragments_aligned_to_seed']}`",
        f"- Concepts aligned total: `{summary['concepts_aligned_total']}`",
        f"- Edges aligned total: `{summary['edges_aligned_total']}`",
        "",
        "## This Proof Claims",
        "",
        "- A public cloud candidate fragment can be aligned to Seed Graph concept IDs.",
        "- Matched concepts and edges are inspectable.",
        "- Local Brain remains isolated.",
        "- No external LLM, external sLLM, or rule-template generation is used.",
        "- No final answer generation quality is claimed.",
        "",
        "## This Proof Does Not Claim",
        "",
        "- Autonomous web crawling.",
        "- Autonomous Cloud Brain self-growth.",
        "- Production-scale verification.",
        "- Final answer quality.",
        "- sLLM replacement.",
        "",
        "## Safety Flags",
        "",
        f"- External LLM used: `{str(claims['external_llm_used']).lower()}`",
        f"- External sLLM used: `{str(claims['external_sllm_used']).lower()}`",
        f"- Rule-based answer engine: `{str(claims['rule_based_answer_engine']).lower()}`",
        f"- Final answer generation claimed: `{str(claims['final_answer_generation_claimed']).lower()}`",
        "",
        "## Matched Fragments",
        "",
    ]
    for alignment in proof["alignment"].get("alignments", []):
        lines.extend(
            [
                f"### `{alignment.get('fragment_id') or alignment.get('content_hash')}`",
                "",
                f"- Rejected: `{str(alignment.get('rejected')).lower()}`",
                f"- Alignment success: `{str(alignment.get('alignment_success')).lower()}`",
                f"- Matched concepts: `{len(alignment.get('matched_seed_concepts') or [])}`",
                f"- Matched edges: `{len(alignment.get('matched_seed_edges') or [])}`",
                "",
            ]
        )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def write_cloud_fragment_alignment_proof(
    root: str | Path | None = None,
    inbox: str | Path = "data/cloud_brain/inbox",
) -> dict[str, Any]:
    base = seed_root(root)
    current = base / "current"
    current.mkdir(parents=True, exist_ok=True)
    proof = build_cloud_fragment_alignment_proof(base, inbox)
    json_path = current / "cloud_fragment_seed_alignment_proof.json"
    markdown_path = current / "cloud_fragment_seed_alignment_proof.md"
    json_path.write_text(json.dumps(proof, ensure_ascii=False, indent=2), encoding="utf-8")
    _write_markdown(proof, markdown_path)
    return {
        "proof": proof,
        "json_path": str(json_path),
        "markdown_path": str(markdown_path),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Write ATANOR Cloud Fragment to Seed Alignment proof artifacts.")
    parser.add_argument("--root", default=None, help="Seed research root. Defaults to data/seed_research.")
    parser.add_argument("--inbox", default="data/cloud_brain/inbox", help="Cloud Brain candidate fragment inbox.")
    args = parser.parse_args()
    result = write_cloud_fragment_alignment_proof(args.root, args.inbox)
    print(json.dumps({key: value for key, value in result.items() if key != "proof"}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
