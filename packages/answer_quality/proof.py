from __future__ import annotations

from typing import Any

from .comparison import run_answer_quality_benchmark
from .evaluators import evaluate_answer_quality, evaluate_template_smell, evaluate_trace_hygiene
from .models import honesty_flags, utc_now_iso
from .storage import PROOF_ROOT, ensure_dirs, write_json
from .surface_feedback import generate_surface_feedback


def run_answer_quality_proof() -> dict[str, Any]:
    ensure_dirs()
    trace_score = evaluate_answer_quality(
        candidate_id="proof_trace_leak",
        answer="Local Brain → Cloud Brain → Working Memory 경로로 답합니다.",
        query="GraphRAG 설명해줘",
        language="ko",
        mode="default",
        semantic_context=[],
    )
    natural_score = evaluate_answer_quality(
        candidate_id="proof_natural",
        answer="쿠버네티스는 여러 서버에 흩어진 컨테이너를 자동으로 배포하고 관리하는 시스템입니다.",
        query="쿠버네티스가 뭐야?",
        language="ko",
        mode="default",
        semantic_context=[{"concept": "Kubernetes", "claims": ["manages containers"]}],
    )
    recent = ["쉽게 말하면 A입니다.", "쉽게 말하면 B입니다.", "쉽게 말하면 C입니다."]
    template_score, template_flags, _ = evaluate_template_smell("쉽게 말하면 D입니다.", recent)
    mini_run = run_answer_quality_benchmark(limit=8)
    feedback = mini_run.get("surface_feedback", [])
    proof = {
        "result": "PASS" if "trace_leakage" in trace_score["flags"] and natural_score["directness"] >= 0.7 and template_score < 0.7 and feedback else "FAIL",
        "proved_at": utc_now_iso(),
        "trace_leakage": trace_score,
        "natural_answer": natural_score,
        "template_smell": {"score": template_score, "flags": template_flags},
        "mini_run": {
            "run_id": mini_run["run_id"],
            "overall": mini_run["average_scores"]["overall"],
            "feedback_count": len(feedback),
            "auto_promoted": False,
        },
        "claims": [
            "ATANOR can locally evaluate answer quality heuristically.",
            "It can detect trace leakage and template smell.",
            "It can generate reviewable Surface Brain feedback.",
            "It can compare baseline vs Surface Brain vs repaired answer paths.",
        ],
        "does_not_claim": [
            "GPT-level answer quality",
            "human-level language judgment",
            "external LLM judging",
            "perfect factuality evaluation",
            "automatic safe self-improvement without review",
        ],
        "honesty": honesty_flags(),
    }
    write_json(PROOF_ROOT / "answer_quality_proof.json", {"proof": proof})
    md = [
        "# Answer Quality Proof",
        "",
        f"- Result: {proof['result']}",
        f"- Trace hygiene leak flags: {trace_score['flags']}",
        f"- Natural answer overall: {natural_score['overall']}",
        f"- Template smell score: {template_score}",
        f"- Mini run: {mini_run['run_id']}",
        f"- Feedback items: {len(feedback)}",
        "",
        "## This proof claims",
        *[f"- {item}" for item in proof["claims"]],
        "",
        "## This proof does NOT claim",
        *[f"- {item}" for item in proof["does_not_claim"]],
    ]
    (PROOF_ROOT / "answer_quality_proof.md").write_text("\n".join(md) + "\n", encoding="utf-8")
    return {"proof": proof, "json_path": str(PROOF_ROOT / "answer_quality_proof.json"), "markdown_path": str(PROOF_ROOT / "answer_quality_proof.md")}


def main() -> None:
    import json

    print(json.dumps(run_answer_quality_proof(), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
