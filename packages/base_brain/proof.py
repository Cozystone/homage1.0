from __future__ import annotations

import json
from typing import Any

from .benchmark_runner import run_zero_user_benchmark
from .models import PACK_PATH, PROOF_JSON_PATH, PROOF_MD_PATH, honesty_flags, utc_now_iso
from .pack_builder import build_base_brain_pack_v0
from .zero_user_answer import answer_with_base_brain


def _forbidden_leakage(answer: str) -> list[str]:
    terms = ["Local Brain", "Cloud Brain", "Working Memory", "Q-Cortex", "source_hash", "node_id"]
    return [term for term in terms if term in answer]


def run_base_brain_proof() -> dict[str, Any]:
    pack = build_base_brain_pack_v0(write=False)  # introspection only — never clobber a promoted pack
    ko_answer = answer_with_base_brain("쿠버네티스가 뭐야?", language="ko", audience_level="beginner")
    en_answer = answer_with_base_brain("What is Kubernetes?", language="en", audience_level="beginner")
    unsupported = answer_with_base_brain("오늘 내 동네 비가 올지 알려줘.", language="ko", audience_level="beginner")
    benchmark = run_zero_user_benchmark(limit=10)
    semantic_count = len(pack.get("semantic_graph", {}).get("concepts", []))
    surface_count = len(pack.get("surface_graph", {}).get("constructions", []))
    leakages = _forbidden_leakage(str(ko_answer.get("answer") or "")) + _forbidden_leakage(str(en_answer.get("answer") or ""))
    proof_pass = (
        PACK_PATH.exists()
        and semantic_count >= 30
        and surface_count >= 16
        and bool(ko_answer.get("answer"))
        and bool(en_answer.get("answer"))
        and int(ko_answer.get("semantic_context_count") or 0) > 0
        and int(ko_answer.get("surface_candidate_count") or 0) > 0
        and benchmark.get("useful_answer_count", 0) >= 7
        and benchmark.get("trace_hygiene_rate") == 1.0
        and not leakages
        and not ko_answer.get("external_llm_used")
        and not ko_answer.get("external_sllm_used")
        and not ko_answer.get("external_web_used")
    )
    result: dict[str, Any] = {
        "proof_id": "base_brain_v0_proof",
        "created_at": utc_now_iso(),
        "status": "PASS" if proof_pass else "FAIL",
        "pack_built": PACK_PATH.exists(),
        "semantic_count": semantic_count,
        "semantic_relation_count": pack.get("semantic_graph", {}).get("relation_count", 0),
        "surface_count": surface_count,
        "benchmark_prompts_run": benchmark.get("total_prompts"),
        "useful_answer_count": benchmark.get("useful_answer_count"),
        "trace_hygiene_rate": benchmark.get("trace_hygiene_rate"),
        "average_answer_quality": benchmark.get("average_answer_quality"),
        "example_answers": {
            "korean": ko_answer.get("answer"),
            "english": en_answer.get("answer"),
            "unsupported": unsupported.get("answer"),
        },
        "zero_user_answer_flags": {
            "local_user_brain_used": ko_answer.get("local_user_brain_used"),
            "external_llm_used": ko_answer.get("external_llm_used"),
            "external_sllm_used": ko_answer.get("external_sllm_used"),
            "external_web_used": ko_answer.get("external_web_used"),
        },
        "leakages": leakages,
        "claims": [
            "ATANOR can answer a limited set of general questions with zero user data.",
            "It uses a local Base Brain Pack made of Seed Graph v2, Base Semantic Graph, and Base Surface Graph.",
            "It does not call external LLM/sLLM/web in the proof path.",
            "It can hide internal graph path by default.",
        ],
        "does_not_claim": [
            "GPT-level general intelligence",
            "complete world knowledge",
            "full web-scale Semantic Cloud Graph",
            "trained neural decoder",
            "perfect factuality",
            "no need for future cloud/contributor growth",
        ],
        **honesty_flags(),
    }
    PROOF_JSON_PATH.parent.mkdir(parents=True, exist_ok=True)
    PROOF_JSON_PATH.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    PROOF_MD_PATH.write_text(_proof_markdown(result), encoding="utf-8")
    return result


def _proof_markdown(result: dict[str, Any]) -> str:
    return "\n".join(
        [
            "# ATANOR Base Brain Pack v0 Proof",
            "",
            f"- Status: {result['status']}",
            f"- Semantic concepts: {result['semantic_count']}",
            f"- Semantic relations: {result['semantic_relation_count']}",
            f"- Surface constructions: {result['surface_count']}",
            f"- Benchmark prompts: {result['benchmark_prompts_run']}",
            f"- Useful answers: {result['useful_answer_count']}",
            f"- Trace hygiene: {result['trace_hygiene_rate']}",
            f"- External LLM used: {result['external_llm_used']}",
            f"- External sLLM used: {result['external_sllm_used']}",
            f"- External web used: {result['external_web_used']}",
            "",
            "## Claims",
            *[f"- {item}" for item in result["claims"]],
            "",
            "## Does Not Claim",
            *[f"- {item}" for item in result["does_not_claim"]],
            "",
            "## Example: Korean",
            str(result["example_answers"]["korean"]),
            "",
            "## Example: English",
            str(result["example_answers"]["english"]),
            "",
            "## Unsupported Question",
            str(result["example_answers"]["unsupported"]),
        ]
    )


if __name__ == "__main__":
    print(json.dumps(run_base_brain_proof(), ensure_ascii=False, indent=2))
