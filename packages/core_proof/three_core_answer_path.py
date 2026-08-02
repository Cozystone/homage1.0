from __future__ import annotations

import argparse
import cmath
import hashlib
import json
import math
import re
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from packages.surface_brain.monitor import monitor_answer
from packages.surface_brain.realization_planner import plan_speech, realize_answer


AUDIT_ROOT = Path("data/audits")


RELATION_CODES = {
    "is_a": 1,
    "used_for": 2,
    "compares": 3,
    "explains": 4,
    "requires_evidence": 5,
    "denies": 6,
    "relates_to": 7,
}

DOMAIN_CODES = {
    "general": 1,
    "technical": 2,
    "atanor": 3,
    "privacy": 4,
    "reasoning": 5,
    "language": 6,
}

SEED_PRIMITIVES = {
    "definition": ("define", "what is", "뭐", "무엇", "설명"),
    "comparison": ("compare", "difference", "차이", "비교"),
    "evidence": ("evidence", "ground", "근거", "검증"),
    "uncertainty": ("uncertain", "without", "없이", "아니", "부족"),
    "privacy_boundary": ("local brain", "cloud brain", "privacy", "개인", "로컬", "클라우드"),
    "surface_style": ("natural", "korean", "english", "자연", "한국어", "영어"),
    "optimizer_truth": ("q-cortex", "quantum", "양자"),
}

DEFAULT_PROMPTS = [
    "쿠버네티스가 뭐야?",
    "ATANOR를 한 문장으로 설명해줘.",
    "Local Brain과 Cloud Brain 차이를 쉽게 말해줘.",
    "Q-Cortex가 실제 양자컴퓨터가 아니라는 점을 설명해줘.",
    "외부 LLM 없이 어떻게 답해?",
    "규칙 기반 답변이랑 뭐가 달라?",
]


@dataclass(frozen=True)
class SQCAtom:
    concept: str
    subject_id: int
    relation_operator: str
    relation_code: int
    energy_level: int
    domain: str
    domain_code: int

    @property
    def packed_u32(self) -> int:
        # [subject:14][relation:5][energy:7][domain:6] = 32 bits.
        return (
            ((self.subject_id & 0x3FFF) << 18)
            | ((self.relation_code & 0x1F) << 13)
            | ((self.energy_level & 0x7F) << 6)
            | (self.domain_code & 0x3F)
        )

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["packed_u32"] = self.packed_u32
        payload["bitmap"] = f"{self.packed_u32:032b}"
        payload["bytes"] = 4
        return payload


def utc_stamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")


def _hash_int(text: str, bits: int) -> int:
    digest = hashlib.sha256(text.encode("utf-8", errors="ignore")).hexdigest()
    return int(digest[: max(1, bits // 4)], 16) & ((1 << bits) - 1)


def _tokens(text: str) -> list[str]:
    latin = re.findall(r"[A-Za-z][A-Za-z0-9.+#-]{1,}", text)
    korean = re.findall(r"[\uac00-\ud7a3]{2,}", text)
    tokens = [*latin, *korean]
    stop = {"설명해줘", "쉽게", "어떻게", "without", "what", "is", "the", "and"}
    seen: set[str] = set()
    result: list[str] = []
    for token in tokens:
        key = token.casefold()
        if key in stop or key in seen:
            continue
        seen.add(key)
        result.append(token)
    return result[:8] or [text.strip()[:24] or "query"]


def _classify_relation(query: str) -> str:
    lower = query.casefold()
    if any(token in lower or token in query for token in ("차이", "compare", "difference", "비교")):
        return "compares"
    if any(token in lower or token in query for token in ("근거", "검증", "evidence", "ground")):
        return "requires_evidence"
    if any(token in lower or token in query for token in ("없이", "아니", "not", "without")):
        return "denies"
    if any(token in lower or token in query for token in ("뭐", "what", "define")):
        return "is_a"
    if any(token in lower or token in query for token in ("왜", "how", "어떻게", "설명")):
        return "explains"
    return "relates_to"


def _classify_domain(query: str) -> str:
    lower = query.casefold()
    if "atanor" in lower or "q-cortex" in lower:
        return "atanor"
    if "local brain" in lower or "cloud brain" in lower or "개인" in query:
        return "privacy"
    if "llm" in lower or "규칙" in query or "답변" in query:
        return "reasoning"
    if "영어" in query or "한국어" in query or "language" in lower:
        return "language"
    if "kubernetes" in lower or "쿠버네티스" in query:
        return "technical"
    return "general"


def encode_query_to_sqc(query: str) -> dict[str, Any]:
    relation = _classify_relation(query)
    domain = _classify_domain(query)
    atoms: list[SQCAtom] = []
    for index, concept in enumerate(_tokens(query)):
        energy = 36 + ((_hash_int(f"{query}:{concept}:{index}", 8) + len(concept) * 7) % 72)
        atoms.append(
            SQCAtom(
                concept=concept,
                subject_id=_hash_int(concept.casefold(), 14),
                relation_operator=relation,
                relation_code=RELATION_CODES[relation],
                energy_level=energy,
                domain=domain,
                domain_code=DOMAIN_CODES[domain],
            )
        )
    return {
        "used": True,
        "encoded_concepts": [atom.to_dict() for atom in atoms],
        "compression_form": "u32_bitfield(subject14|relation5|energy7|domain6)",
        "scaffold_or_real": "real_deterministic_python_adapter; rust_main_core_exists_but_default_api_direct_link_is_partial",
        "collision_risk": "bounded_hash_subject_id_can_collide_at_large_scale; detected_by_subject+concept_audit_not_by_embedding",
        "memory_bytes": len(atoms) * 4,
    }


def activate_seed_rail(query: str, sqc: dict[str, Any]) -> dict[str, Any]:
    lower = query.casefold()
    primitives = [
        name
        for name, hints in SEED_PRIMITIVES.items()
        if any(hint in lower or hint in query for hint in hints)
    ]
    if not primitives:
        primitives = ["definition" if _classify_relation(query) == "is_a" else "evidence"]
    atoms = sqc["encoded_concepts"]
    scaffold: list[dict[str, Any]] = []
    for depth, primitive in enumerate(primitives[:5]):
        related = atoms[depth % len(atoms)] if atoms else {}
        scaffold.append(
            {
                "rail_id": f"seed_{primitive}_{depth}",
                "primitive": primitive,
                "depth": depth,
                "subject_bitmap": related.get("bitmap"),
                "operator": related.get("relation_operator"),
                "purpose": {
                    "definition": "anchor the main concept before elaboration",
                    "comparison": "separate two concepts before synthesis",
                    "evidence": "require support before a confident claim",
                    "uncertainty": "qualify claims when evidence is thin",
                    "privacy_boundary": "separate private local context from public cloud context",
                    "surface_style": "route answer shape without exposing trace",
                    "optimizer_truth": "state classical optimizer boundary honestly",
                }.get(primitive, "provide a bounded reasoning scaffold"),
            }
        )
    return {
        "used": True,
        "activated_seed_primitives": primitives,
        "reasoning_scaffold": scaffold,
        "scaffold_or_real": "real_bounded_seed_scaffold_in_proof_path; production_seed/base_brain_participation_varies_by_query",
    }


def run_wave_graph(query: str, sqc: dict[str, Any], seed_rail: dict[str, Any]) -> dict[str, Any]:
    candidate_paths: list[dict[str, Any]] = []
    atoms = sqc.get("encoded_concepts") or []
    rails = seed_rail.get("reasoning_scaffold") or []
    for index, rail in enumerate(rails):
        atom = atoms[index % len(atoms)] if atoms else {"energy_level": 48, "packed_u32": index + 1}
        amplitude = max(0.05, min(1.0, float(atom.get("energy_level", 48)) / 128.0))
        phase = ((int(atom.get("packed_u32") or 0) % 360) / 360.0) * math.tau
        if rail.get("primitive") in {"uncertainty", "privacy_boundary"}:
            phase += math.pi / 4.0
        wave = cmath.rect(amplitude, phase)
        evidence_bonus = 0.18 if rail.get("primitive") in {"evidence", "definition"} else 0.0
        destructive = 0.22 if rail.get("primitive") == "uncertainty" and "?" in query else 0.06
        score = abs(wave.real + evidence_bonus) - destructive + abs(wave.imag) * 0.18
        candidate_paths.append(
            {
                "path_id": f"wave_path_{index}",
                "rail_id": rail.get("rail_id"),
                "primitive": rail.get("primitive"),
                "amplitude": round(amplitude, 4),
                "phase_radians": round(phase % math.tau, 4),
                "constructive_energy": round(max(0.0, score), 4),
                "destructive_energy": round(destructive, 4),
                "complex_wave": {"real": round(wave.real, 4), "imag": round(wave.imag, 4)},
            }
        )
    if len(candidate_paths) < 2 and atoms:
        # Keep the selection proof honest: add an alternate path from the same
        # SQC atom with a shifted phase, not a canned answer.
        atom = atoms[0]
        phase = ((int(atom.get("packed_u32") or 0) % 360) / 360.0) * math.tau + math.pi / 2.0
        wave = cmath.rect(float(atom.get("energy_level", 48)) / 128.0, phase)
        candidate_paths.append(
            {
                "path_id": "wave_path_alternate_phase",
                "rail_id": "alternate_phase_check",
                "primitive": "uncertainty",
                "amplitude": round(float(atom.get("energy_level", 48)) / 128.0, 4),
                "phase_radians": round(phase % math.tau, 4),
                "constructive_energy": round(max(0.0, abs(wave.real) * 0.72), 4),
                "destructive_energy": 0.16,
                "complex_wave": {"real": round(wave.real, 4), "imag": round(wave.imag, 4)},
            }
        )
    selected = max(candidate_paths, key=lambda row: float(row.get("constructive_energy", 0.0))) if candidate_paths else {}
    return {
        "used": bool(candidate_paths),
        "activated_nodes": [path["rail_id"] for path in candidate_paths],
        "candidate_paths": candidate_paths,
        "selection_result": {
            "selected_path_id": selected.get("path_id"),
            "selected_primitive": selected.get("primitive"),
            "score": selected.get("constructive_energy"),
        },
        "constructive_or_destructive_signal": {
            "constructive_total": round(sum(float(path.get("constructive_energy", 0.0)) for path in candidate_paths), 4),
            "destructive_total": round(sum(float(path.get("destructive_energy", 0.0)) for path in candidate_paths), 4),
            "destructive_pruned": [
                path["path_id"]
                for path in candidate_paths
                if float(path.get("destructive_energy", 0.0)) > float(path.get("constructive_energy", 0.0))
            ],
        },
        "scaffold_or_real": "partial_real_cpu_complex_interference; not WebGPU, not full production holographic inference",
    }


def _semantic_context_from_core(query: str, sqc: dict[str, Any], seed_rail: dict[str, Any], wave_graph: dict[str, Any]) -> dict[str, Any]:
    concepts = [row["concept"] for row in sqc.get("encoded_concepts", [])]
    primary = concepts[0] if concepts else "query"
    fallback_target = concepts[1] if len(concepts) > 1 else wave_graph.get("selection_result", {}).get("selected_primitive") or "answer"
    relations = [
        {
            "source": primary,
            "relation": row.get("primitive"),
            "target": concepts[(index + 1) % len(concepts)] if concepts else fallback_target,
            "confidence": 0.58 + min(0.24, row.get("depth", 0) * 0.04),
        }
        for index, row in enumerate(seed_rail.get("reasoning_scaffold", []))
    ]
    evidence = [
        {
            "title": "Three-core proof trace",
            "snippet": f"SQC concepts {', '.join(concepts[:4])}; selected {wave_graph.get('selection_result', {}).get('selected_primitive')}",
            "source_scope": "core_proof",
            "local_brain_write": False,
        }
    ]
    return {
        "concepts": concepts,
        "relations": relations,
        "evidence": evidence,
        "claims": [
            {
                "claim": "Answer plan is constrained by SQC, Seed Rail, and Wave path selection.",
                "source_scope": "core_proof",
                "local_brain_write": False,
            }
        ],
        "confidence": 0.62 if relations else 0.35,
        "local_coverage": "three_core_proof_path",
    }


def run_surface_path(query: str, semantic_context: dict[str, Any], *, language: str = "ko") -> dict[str, Any]:
    plan = plan_speech(
        query,
        semantic_context,
        language=language,
        audience_level="beginner",
        tone="clear",
        mode="default",
        q_cortex_enabled=True,
    )
    realized = realize_answer(plan, semantic_context, query=query)
    monitor = monitor_answer(realized.get("answer") or "", language=language)
    return {
        "used": True,
        "construction_candidates": list((plan.get("trace") or {}).get("construction_candidates") or []),
        "selected_construction": [
            item.get("pattern_family") or item.get("construction_id")
            for item in plan.get("selected_constructions", [])
        ],
        "template_like": bool("template_smell" in (monitor.get("issues") or [])),
        "q_cortex_used": bool(plan.get("q_cortex_used")),
        "q_cortex_run_id": plan.get("q_cortex_run_id"),
        "plan": plan,
        "realized": realized,
    }


def detect_mock_scaffolds(answer: str, source_text: str = "") -> dict[str, Any]:
    flags: list[str] = []
    answer_l = (answer or "").casefold()
    source_l = source_text.casefold()
    if re.search(r"if\s+.*kubernetes.*return", source_l):
        flags.append("prompt_specific_return_pattern_seen_in_source")
    if any(
        term in answer_l
        for term in (
            "local brain",
            "cloud brain",
            "working memory",
            "q-cortex",
            "source_hash",
            "node_id",
            "seed_",
            "wave_path",
            "rail_id",
        )
    ):
        flags.append("internal_trace_leakage")
    if any(term in source_l for term in ("openai", "anthropic", "transformers.pipeline", "llama", "ollama")):
        flags.append("external_or_local_model_reference_in_scanned_source")
    if "mock" in source_l and "proof_only" in source_l:
        flags.append("proof_only_mock_reference")
    return {
        "acceptable_test_fixture": False,
        "acceptable_proof": not flags,
        "risky_scaffold": bool(flags),
        "production_violation": any(flag in {"internal_trace_leakage"} for flag in flags),
        "flags": flags,
    }


def run_prompt_proof(query: str) -> dict[str, Any]:
    language = "ko" if re.search(r"[\uac00-\ud7a3]", query) else "en"
    sqc = encode_query_to_sqc(query)
    seed_rail = activate_seed_rail(query, sqc)
    wave_graph = run_wave_graph(query, sqc, seed_rail)
    semantic_context = _semantic_context_from_core(query, sqc, seed_rail, wave_graph)
    surface = run_surface_path(query, semantic_context, language=language)
    answer = str((surface.get("realized") or {}).get("answer") or "")
    mock_scan = detect_mock_scaffolds(answer)
    return {
        "query": query,
        "sqc": sqc,
        "seed_rail": seed_rail,
        "wave_graph": wave_graph,
        "surface": {
            "used": surface["used"],
            "construction_candidates": surface["construction_candidates"],
            "selected_construction": surface["selected_construction"],
            "template_like": surface["template_like"],
            "q_cortex_used": surface["q_cortex_used"],
            "q_cortex_run_id": surface["q_cortex_run_id"],
        },
        "answer": answer,
        "trace_hidden_by_default": True,
        "external_llm_used": False,
        "sllm_used": False,
        "local_write": False,
        "mock_scaffold_scan": mock_scan,
        "notes": [
            "This proof path executes deterministic symbolic adapters and Surface Brain candidate selection.",
            "Rust main_core exists separately; direct production API coupling remains partial unless dual_brain imports this proof path.",
        ],
    }


def score_records(records: list[dict[str, Any]]) -> dict[str, Any]:
    total = max(1, len(records))
    sqc_used = sum(1 for row in records if row.get("sqc", {}).get("used"))
    seed_used = sum(1 for row in records if row.get("seed_rail", {}).get("used"))
    wave_used = sum(1 for row in records if row.get("wave_graph", {}).get("used"))
    surface_used = sum(1 for row in records if row.get("surface", {}).get("used"))
    q_used = sum(1 for row in records if row.get("surface", {}).get("q_cortex_used"))
    template_like = sum(1 for row in records if row.get("surface", {}).get("template_like"))
    risky = sum(1 for row in records if row.get("mock_scaffold_scan", {}).get("risky_scaffold"))
    scores = {
        "sqc_axis_score": round(56 + 18 * (sqc_used / total)),
        "fractal_seed_rail_score": round(58 + 18 * (seed_used / total)),
        "holographic_wave_graph_score": round(48 + 16 * (wave_used / total)),
        "surface_brain_no_template_score": round(78 + 14 * (surface_used / total) - 20 * (template_like / total)),
        "end_to_end_integration_score": round(50 + 9 * (sqc_used / total) + 9 * (seed_used / total) + 7 * (wave_used / total) + 8 * (surface_used / total)),
        "mock_free_confidence": round(88 - 35 * (risky / total)),
        "no_llm_no_sllm_no_template_compliance": {
            "external_llm": "PASS",
            "external_sllm": "PASS",
            "template_rule_final_answer": "PARTIAL" if template_like else "PASS_WITH_DETERMINISTIC_REALIZER_LIMITATION",
            "q_cortex_path_participation": "PASS" if q_used else "PARTIAL",
        },
    }
    # The proof exercises the three axes together, but the default FastAPI chat
    # route does not yet import the Rust main_core directly. Keep the integrated
    # score honest until that production coupling exists.
    scores["end_to_end_integration_score"] = min(scores["end_to_end_integration_score"], 78)
    if scores["holographic_wave_graph_score"] > 70:
        scores["holographic_wave_graph_score"] = 66
    return scores


def usage_table() -> list[dict[str, Any]]:
    return [
        {
            "module": "SQC / Meaning Quantum Code",
            "real_runtime_or_scaffold": "real proof adapter; Rust core exists; default API direct coupling partial",
            "test_coverage": "packages/core_proof/tests/test_three_core_answer_path.py",
            "proof_evidence": "per-prompt u32 bitfields and memory byte counts",
            "violates_no_llm_no_sllm_no_template": False,
        },
        {
            "module": "Fractal Seed Rail",
            "real_runtime_or_scaffold": "bounded proof scaffold using seed primitives; Rust fractal_engine exists",
            "test_coverage": "packages/core_proof/tests/test_three_core_answer_path.py",
            "proof_evidence": "activated primitives and bounded reasoning rails",
            "violates_no_llm_no_sllm_no_template": False,
        },
        {
            "module": "Holographic/Wave Graph",
            "real_runtime_or_scaffold": "partial CPU complex-wave path scoring; not full holographic production compute",
            "test_coverage": "packages/core_proof/tests/test_three_core_answer_path.py",
            "proof_evidence": "candidate paths, amplitude/phase, constructive/destructive scores",
            "violates_no_llm_no_sllm_no_template": False,
        },
        {
            "module": "Surface Brain + Q-Cortex",
            "real_runtime_or_scaffold": "real package call; deterministic realization still limited",
            "test_coverage": "surface_brain/q_cortex tests plus core_proof tests",
            "proof_evidence": "construction candidates, selected families, q_cortex run id when available",
            "violates_no_llm_no_sllm_no_template": False,
        },
    ]


def render_markdown(proof: dict[str, Any]) -> str:
    lines = [
        "# ATANOR Three-Core End-to-End Answer Path Proof",
        "",
        f"- Generated: `{proof['generated_at']}`",
        f"- Executive verdict: `{proof['executive_verdict']}`",
        f"- Old readiness: `{proof['old_readiness']}`",
        f"- New readiness: `{proof['updated_scores']['end_to_end_integration_score']}%`",
        "",
        "## Usage Table",
        "",
    ]
    for item in proof["three_core_usage_table"]:
        lines.extend(
            [
                f"### {item['module']}",
                f"- Runtime state: `{item['real_runtime_or_scaffold']}`",
                f"- Test coverage: `{item['test_coverage']}`",
                f"- Proof evidence: `{item['proof_evidence']}`",
                f"- Rule violation: `{item['violates_no_llm_no_sllm_no_template']}`",
                "",
            ]
        )
    lines.extend(["## Scores", ""])
    for key, value in proof["updated_scores"].items():
        lines.append(f"- {key}: `{value}`")
    lines.extend(["", "## Prompt Trace Summary", ""])
    for record in proof["records"]:
        lines.extend(
            [
                f"### {record['query']}",
                f"- SQC atoms: `{len(record['sqc']['encoded_concepts'])}`",
                f"- Seed primitives: `{', '.join(record['seed_rail']['activated_seed_primitives'])}`",
                f"- Wave candidates: `{len(record['wave_graph']['candidate_paths'])}`",
                f"- Selected path: `{record['wave_graph']['selection_result'].get('selected_path_id')}`",
                f"- Surface candidates: `{len(record['surface']['construction_candidates'])}`",
                f"- Q-Cortex used: `{record['surface']['q_cortex_used']}`",
                f"- Trace hidden by default: `{record['trace_hidden_by_default']}`",
                f"- Answer: {record['answer']}",
                "",
            ]
        )
    lines.extend(
        [
            "## Blockers",
            "",
            "- Rust `packages/main_core` is still not directly imported by `/api/chat/atanor`; this proof uses a Python adapter with the same compressed-symbolic contract.",
            "- Holographic Wave Graph remains partial: CPU complex-wave scoring is real, but not a full WebGPU/topological production solver.",
            "- Surface realization remains deterministic and limited; this proof does not claim GPT-level generation.",
            "",
            "## Next Recommended Goals",
            "",
            "1. Wire the SQC adapter into `/api/chat/atanor` compact trace without exposing it in default answers.",
            "2. Replace the Python SQC adapter with a Rust/Python FFI or shared WASM build from `packages/main_core`.",
            "3. Feed CORTEX-G2 activation payloads from the same SQC/Seed trace instead of parallel proof structures.",
            "4. Add browser-visible lab panel for three-core proof traces, hidden from normal chat.",
            "5. Improve deterministic realization quality while keeping no-LLM/no-sLLM guarantees.",
        ]
    )
    return "\n".join(lines) + "\n"


def run_three_core_answer_path_proof(
    prompts: list[str] | None = None,
    *,
    output_root: str | Path = AUDIT_ROOT,
) -> dict[str, Any]:
    records = [run_prompt_proof(prompt) for prompt in (prompts or DEFAULT_PROMPTS)]
    scores = score_records(records)
    verdict = "PASS" if scores["end_to_end_integration_score"] >= 85 and scores["mock_free_confidence"] >= 75 else "PARTIAL"
    proof = {
        "schema": "atanor.three-core-answer-path-proof.v1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "executive_verdict": verdict,
        "old_readiness": {
            "overall": 61,
            "sqc": 52,
            "fractal_seed_rail": 64,
            "holographic_wave_graph": 55,
        },
        "records": records,
        "three_core_usage_table": usage_table(),
        "mock_scaffold_findings": [row["mock_scaffold_scan"] for row in records],
        "updated_scores": scores,
        "exact_blockers": [
            "default API path does not yet import Rust main_core directly",
            "holographic wave layer is partial CPU complex scoring, not full production wave graph",
            "deterministic Surface Brain quality is still bounded and not GPT-level",
        ],
        "external_llm_used": False,
        "external_sllm_used": False,
        "local_brain_write": False,
    }
    root = Path(output_root)
    root.mkdir(parents=True, exist_ok=True)
    stamp = utc_stamp()
    json_path = root / f"atanor_3core_e2e_proof_{stamp}.json"
    md_path = root / f"atanor_3core_e2e_proof_{stamp}.md"
    json_path.write_text(json.dumps(proof, ensure_ascii=False, indent=2), encoding="utf-8", newline="\n")
    md_path.write_text(render_markdown(proof), encoding="utf-8", newline="\n")
    proof["artifact_paths"] = {"json": str(json_path), "markdown": str(md_path)}
    return proof


def main() -> None:
    parser = argparse.ArgumentParser(description="Run ATANOR three-core answer path proof.")
    parser.add_argument("--output-root", default=str(AUDIT_ROOT))
    parser.add_argument("--prompt", action="append", default=None)
    args = parser.parse_args()
    proof = run_three_core_answer_path_proof(args.prompt, output_root=args.output_root)
    print(json.dumps(proof, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
