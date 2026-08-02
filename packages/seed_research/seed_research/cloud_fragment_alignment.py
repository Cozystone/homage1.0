from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from .core import read_jsonl, seed_root
from .runtime_anchor import _tokens


FIXTURE_PATH = Path("data/cloud_brain/inbox/test_seed_alignment_fragment.json")
PRIVATE_KEY_MARKERS = {
    "raw_text",
    "chat_log",
    "chat_logs",
    "payload_vault",
    "payloadVault",
    "local_brain_data",
    "private_graph",
}
PRIVATE_TEXT_MARKERS = [
    "payload vault",
    "payload_vault",
    "local brain private",
    "private local brain",
    "chat log",
    "chat history",
    "appdata",
    "c:\\",
    "/users/",
    "/home/",
    "localhost",
    "127.0.0.1",
    "0.0.0.0",
]
PRIVATE_IP_RE = re.compile(r"\b(?:10|127|192\.168|172\.(?:1[6-9]|2\d|3[0-1]))(?:\.\d{1,3}){2,3}\b")


def deterministic_fixture() -> dict[str, Any]:
    return {
        "fragment_id": "candidate_seed_alignment_001",
        "content_hash": "deterministic_test_seed_alignment_001",
        "source_scope": "cloud",
        "privacy_scope": "public",
        "origin": "manual_seed_alignment_fixture",
        "source_url": "fixture://seed-alignment/evidence-claim",
        "source_id": "seed_alignment_fixture_001",
        "title": "Evidence and Claim Alignment Fixture",
        "text": "Evidence supports a claim. A source provides evidence. Verification evaluates whether a claim is supported by evidence.",
        "trust_state": "unverified",
        "verification_state": "web_seed_pending",
        "ingestion_state": "pending",
        "created_by": "seed_alignment_proof_fixture",
        "fixture": True,
        "fixture_scope": "deterministic_cloud_fragment_seed_alignment_proof",
        "not_real_web_crawling": True,
        "not_autonomous_cloud_growth": True,
    }


def ensure_deterministic_fixture(path: str | Path = FIXTURE_PATH) -> Path:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    if not target.exists():
        target.write_text(json.dumps(deterministic_fixture(), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return target


def _load_seed_current(root: str | Path | None = None) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    current = seed_root(root) / "current"
    concepts = read_jsonl(current / "seed_concepts.jsonl")
    edges = read_jsonl(current / "seed_edges.jsonl")
    aliases = read_jsonl(current / "seed_aliases.jsonl")
    return concepts, edges, aliases


def _concept_terms(concept: dict[str, Any], aliases: list[dict[str, Any]]) -> list[tuple[str, str]]:
    concept_id = str(concept.get("concept_id") or "")
    rows: list[tuple[str, str]] = []
    label = str(concept.get("label") or "")
    if label:
        rows.append((label, "label"))
    labels = concept.get("labels") if isinstance(concept.get("labels"), dict) else {}
    for value in labels.values():
        if value:
            rows.append((str(value), "label"))
    alias_map = concept.get("aliases") if isinstance(concept.get("aliases"), dict) else {}
    for values in alias_map.values():
        if isinstance(values, list):
            rows.extend((str(value), "alias") for value in values if value)
    for row in aliases:
        if row.get("concept_id") == concept_id and row.get("alias"):
            rows.append((str(row["alias"]), "alias"))
    rows.append((concept_id.removeprefix("seed.core.").replace("_", " "), "label"))

    dedup: dict[str, str] = {}
    for term, reason in rows:
        normalized = " ".join(_tokens(term))
        if normalized:
            dedup.setdefault(normalized, reason)
    return [(term, reason) for term, reason in dedup.items()]


def _fragment_text(fragment: dict[str, Any]) -> str:
    return f"{fragment.get('title', '')}\n{fragment.get('text', '')}"


def _is_private_fragment(fragment: dict[str, Any]) -> tuple[bool, str | None]:
    if fragment.get("privacy_scope") != "public":
        return True, "privacy_scope_not_public"
    keys = {str(key) for key in fragment.keys()}
    if keys.intersection(PRIVATE_KEY_MARKERS):
        return True, "private_key_marker"
    serialized = json.dumps(fragment, ensure_ascii=False).casefold()
    if any(marker in serialized for marker in PRIVATE_TEXT_MARKERS):
        return True, "private_text_marker"
    if PRIVATE_IP_RE.search(serialized):
        return True, "private_ip_marker"
    return False, None


def _match_concepts(fragment: dict[str, Any], concepts: list[dict[str, Any]], aliases: list[dict[str, Any]]) -> list[dict[str, Any]]:
    text = _fragment_text(fragment)
    text_tokens = set(_tokens(text))
    normalized_text = " ".join(_tokens(text))
    matches: list[dict[str, Any]] = []
    seen: set[str] = set()
    for concept in concepts:
        concept_id = str(concept.get("concept_id") or "")
        if not concept_id or concept_id in seen:
            continue
        for term, reason in _concept_terms(concept, aliases):
            term_tokens = set(term.split())
            if not term_tokens:
                continue
            phrase_hit = len(term) > 2 and term in normalized_text
            token_hit = bool(term_tokens.intersection(text_tokens))
            if phrase_hit or token_hit:
                matches.append(
                    {
                        "concept_id": concept_id,
                        "label": concept.get("label") or concept_id,
                        "matched_text": term,
                        "match_reason": reason,
                        "confidence": 1.0 if phrase_hit or len(term_tokens) == 1 else 0.92,
                    }
                )
                seen.add(concept_id)
                break
    matches.sort(key=lambda item: (item["concept_id"], item["matched_text"]))
    return matches


def _sentences(text: str) -> list[str]:
    return [part.strip() for part in re.split(r"[.!?\n]+", text) if part.strip()]


def _edge_relation_terms(relation: str) -> set[str]:
    terms = {relation, relation.replace("_", " ")}
    relation_map = {
        "supports": {"supports", "supported", "support"},
        "requires": {"requires", "needs", "require"},
        "has_source": {"source", "provides", "origin"},
        "verifies": {"verifies", "verification", "evaluates", "checks", "supported"},
        "has_evidence": {"evidence"},
    }
    terms.update(relation_map.get(relation, set()))
    return {term.casefold() for term in terms if term}


def _match_edges(fragment: dict[str, Any], edges: list[dict[str, Any]], concept_matches: list[dict[str, Any]]) -> list[dict[str, Any]]:
    concept_ids = {match["concept_id"] for match in concept_matches}
    label_by_id = {match["concept_id"]: str(match["label"]).casefold() for match in concept_matches}
    fragment_sentences = _sentences(_fragment_text(fragment))
    matched_edges: list[dict[str, Any]] = []
    for edge in edges:
        source = str(edge.get("source") or "")
        target = str(edge.get("target") or "")
        relation = str(edge.get("relation") or "")
        if source not in concept_ids or target not in concept_ids:
            continue
        relation_terms = _edge_relation_terms(relation)
        source_label = label_by_id.get(source, source.removeprefix("seed.core.")).casefold()
        target_label = label_by_id.get(target, target.removeprefix("seed.core.")).casefold()
        for sentence in fragment_sentences:
            lowered = sentence.casefold()
            has_source = source_label in lowered or source.removeprefix("seed.core.").replace("_", " ") in lowered
            has_target = target_label in lowered or target.removeprefix("seed.core.").replace("_", " ") in lowered
            has_relation = any(term in lowered for term in relation_terms)
            if has_source and has_target and has_relation:
                matched_edges.append(
                    {
                        "source": source,
                        "relation": relation,
                        "target": target,
                        "matched_text": sentence,
                        "confidence": 1.0,
                    }
                )
                break
    matched_edges.sort(key=lambda item: (item["source"], item["relation"], item["target"]))
    return matched_edges


def align_cloud_fragment_to_seed(fragment: dict[str, Any], root: str | Path | None = None) -> dict[str, Any]:
    rejected, reason = _is_private_fragment(fragment)
    base = {
        "fragment_id": str(fragment.get("fragment_id") or ""),
        "content_hash": str(fragment.get("content_hash") or ""),
        "privacy_scope": fragment.get("privacy_scope"),
        "source_scope": fragment.get("source_scope"),
        "alignment_attempted": not rejected,
        "alignment_success": False,
        "matched_seed_concepts": [],
        "matched_seed_edges": [],
        "verification_state": fragment.get("verification_state"),
        "trust_state": fragment.get("trust_state"),
        "writes_to_local_brain": False,
        "final_answer_generation_claimed": False,
        "external_llm_used": False,
        "external_sllm_used": False,
        "rule_based_answer_engine": False,
        "is_fixture": bool(fragment.get("fixture")),
        "not_real_web_crawling": bool(fragment.get("not_real_web_crawling")),
        "not_autonomous_cloud_growth": bool(fragment.get("not_autonomous_cloud_growth")),
    }
    if rejected:
        return {**base, "rejected": True, "reject_reason": reason}

    concepts, edges, aliases = _load_seed_current(root)
    concept_matches = _match_concepts(fragment, concepts, aliases)
    edge_matches = _match_edges(fragment, edges, concept_matches)
    return {
        **base,
        "rejected": False,
        "reject_reason": None,
        "alignment_success": bool(concept_matches),
        "matched_seed_concepts": concept_matches,
        "matched_seed_edges": edge_matches,
    }


def load_candidate_fragments(inbox: str | Path = "data/cloud_brain/inbox") -> list[dict[str, Any]]:
    folder = Path(inbox)
    if not folder.exists():
        return []
    rows: list[dict[str, Any]] = []
    for path in sorted(folder.glob("*.json")):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            continue
        if isinstance(payload, dict):
            rows.append(payload)
    return rows


def align_public_candidate_fragments(
    root: str | Path | None = None,
    inbox: str | Path = "data/cloud_brain/inbox",
) -> dict[str, Any]:
    fragments = load_candidate_fragments(inbox)
    alignments = [align_cloud_fragment_to_seed(fragment, root) for fragment in fragments]
    public_alignments = [item for item in alignments if not item.get("rejected")]
    aligned = [item for item in public_alignments if item.get("alignment_success")]
    matched_fragment_ids = [str(item.get("fragment_id") or item.get("content_hash") or "unknown") for item in aligned]
    concepts_total = sum(len(item.get("matched_seed_concepts") or []) for item in aligned)
    edges_total = sum(len(item.get("matched_seed_edges") or []) for item in aligned)
    return {
        "cloud_checked": True,
        "candidate_fragments_checked": len(fragments),
        "public_fragments_checked": len(public_alignments),
        "rejected_private_fragments": len(alignments) - len(public_alignments),
        "fragments_aligned_to_seed": len(aligned),
        "concepts_aligned_total": concepts_total,
        "edges_aligned_total": edges_total,
        "matched_fragment_ids": matched_fragment_ids,
        "matched_seed_concepts": [concept for item in aligned for concept in item.get("matched_seed_concepts", [])],
        "matched_seed_edges": [edge for item in aligned for edge in item.get("matched_seed_edges", [])],
        "alignment_ready": True,
        "writes_to_local_brain": False,
        "alignments": alignments,
    }
