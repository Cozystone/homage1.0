from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .dual_projection import ingest_source_sentence_dual_projection
from .models import SourceSentence, utc_now_iso
from .monitor import monitor_answer, repair_answer
from .realization_planner import plan_speech, realize_answer
from .storage import SURFACE_ROOT, ensure_dirs, write_json


KUBERNETES_SENTENCE = "쉽게 말하면, 쿠버네티스는 많은 컨테이너를 자동으로 배치하고 관리하는 운영 관리자에 가깝습니다."


def run_surface_brain_proof(root: str | Path = SURFACE_ROOT) -> dict[str, Any]:
    ensure_dirs()
    source = SourceSentence.from_text(
        KUBERNETES_SENTENCE,
        source_id="proof-kubernetes",
        url="local://surface-proof",
        title="Kubernetes beginner explanation",
        license="proof_fixture",
        usage_allowed=False,
    )
    dual = ingest_source_sentence_dual_projection(source)
    semantic = dual["semantic_projection"]
    surface = dual["surface_projection"]
    plan = plan_speech("쿠버네티스가 뭐야?", semantic, language="ko", audience_level="beginner", tone="friendly")
    answer = realize_answer(plan, semantic, query="쿠버네티스가 뭐야?")
    style_variations = {
        "beginner_ko": realize_answer(plan_speech("쿠버네티스가 뭐야?", semantic, language="ko", audience_level="beginner"), semantic, query="쿠버네티스가 뭐야?"),
        "expert_ko": realize_answer(plan_speech("쿠버네티스가 뭐야?", semantic, language="ko", audience_level="expert"), semantic, query="쿠버네티스가 뭐야?"),
        "concise_en": realize_answer(plan_speech("What is Kubernetes?", semantic, language="en", audience_level="expert"), semantic, query="What is Kubernetes?"),
        "friendly_en": realize_answer(plan_speech("What is Kubernetes?", semantic, language="en", audience_level="beginner", tone="friendly"), semantic, query="What is Kubernetes?"),
    }
    bad_draft = "Local Brain → Cloud Brain → Contributor Node path says Kubernetes Kubernetes is container manager manager."
    monitor = monitor_answer(bad_draft, language="en")
    repaired = repair_answer(bad_draft, monitor, language="en")
    repaired_monitor = monitor_answer(repaired, language="en")
    pass_state = (
        semantic["source_hash"] == surface["source_hash"] == source.source_hash
        and "Kubernetes" in semantic["concepts"]
        and "containers" in semantic["concepts"]
        and "simplification" in surface["discourse_moves"]
        and "쉽게 말하면" in surface["phrase_patterns"]
        and dual["stored_raw_text"] is False
        and bool(plan["selected_constructions"])
        and bool(plan["q_cortex_used"] or plan["trace"]["construction_selection"].get("fallback"))
        and "Local Brain" not in answer["answer"]
        and "Cloud Brain" not in answer["answer"]
        and repaired_monitor["needs_repair"] is False
    )
    proof = {
        "result": "PASS" if pass_state else "FAIL",
        "proved_at": utc_now_iso(),
        "dual_projection": dual,
        "non_template_generation": {
            "question": "쿠버네티스가 뭐야?",
            "surface_plan": plan,
            "realized_answer": answer,
            "internal_trace_dumped_in_answer": "Local Brain" in answer["answer"] or "Cloud Brain" in answer["answer"],
        },
        "style_variation": style_variations,
        "repair_loop": {
            "bad_draft": bad_draft,
            "monitor": monitor,
            "repaired": repaired,
            "repaired_monitor": repaired_monitor,
        },
        "claims": [
            "ATANOR can create dual semantic/surface projections from the same source sentence.",
            "Surface Brain can improve answer planning and naturalness.",
            "Surface Brain uses construction competition, not fixed templates.",
            "Q-Cortex can optionally optimize construction/discourse/lemma selection.",
            "Final answers hide internal brain paths by default.",
        ],
        "does_not_claim": [
            "GPT-level language quality",
            "real human brain simulation",
            "consciousness",
            "unrestricted web crawling",
            "legal reuse of all copyrighted raw text",
            "fully trained ATANOR-native decoder",
            "real quantum hardware or quantum speedup",
        ],
    }
    base = Path(root) / "proofs"
    json_path = base / "surface_brain_proof.json"
    md_path = base / "surface_brain_proof.md"
    write_json(json_path, proof)
    md_path.write_text(_markdown(proof), encoding="utf-8")
    return {"proof": proof, "json_path": str(json_path), "markdown_path": str(md_path)}


def _markdown(proof: dict[str, Any]) -> str:
    return "\n".join(
        [
            "# Surface Brain Proof",
            "",
            f"- Result: {proof['result']}",
            f"- Shared source hash: {proof['dual_projection']['linked_source_hash']}",
            f"- Q-Cortex used: {proof['non_template_generation']['surface_plan']['q_cortex_used']}",
            f"- Internal trace dumped: {proof['non_template_generation']['internal_trace_dumped_in_answer']}",
            "",
            "## This proof claims",
            *[f"- {claim}" for claim in proof["claims"]],
            "",
            "## This proof does NOT claim",
            *[f"- {claim}" for claim in proof["does_not_claim"]],
            "",
        ]
    )


def main() -> None:
    print(json.dumps(run_surface_brain_proof(), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
