from __future__ import annotations

import re


OVERCLAIMS = [
    "always", "never", "guarantees", "completely eliminates",
    "항상", "절대", "완전히 제거", "보장",
]


def _tokens(text: str) -> set[str]:
    return {token.lower() for token in re.findall(r"[A-Za-z가-힣][A-Za-z0-9가-힣_-]{1,}", text)}


def _sentences(text: str) -> list[str]:
    return [part.strip() for part in re.split(r"(?<=[.!?。])\s+|\n+", text) if part.strip()]


def check_guard(draft_answer: str, evidence_bundle: dict | None = None, ontology: dict | None = None) -> dict:
    """Return a non-authoritative lexical-overlap diagnostic.

    Token overlap can rank review attention, but it cannot establish that
    evidence entails a claim.  Every result therefore carries no support
    authority; independent evidence/answer binding remains out of scope.
    """
    evidence_bundle = evidence_bundle or {}
    ontology = ontology or {}
    evidence_text = " ".join(doc.get("snippet", "") for doc in evidence_bundle.get("evidence_docs", []))
    evidence_tokens = _tokens(evidence_text)
    nodes = ontology.get("nodes", [])
    node_labels = [node.get("label", "") for node in nodes]
    node_tokens = set().union(*[_tokens(label) for label in node_labels]) if node_labels else set()

    claim_reports = []
    warnings = []
    for sentence in _sentences(draft_answer):
        claim_tokens = _tokens(sentence)
        evidence_overlap = len(claim_tokens & evidence_tokens)
        ontology_overlap = len(claim_tokens & node_tokens)
        if evidence_overlap >= 3 or (evidence_overlap >= 1 and ontology_overlap >= 1):
            support = "lexical_match"
        elif evidence_overlap >= 1 or ontology_overlap >= 1:
            support = "lexical_match_weak"
        else:
            support = "no_match"
        overclaims = [phrase for phrase in OVERCLAIMS if phrase.lower() in sentence.lower()]
        if overclaims:
            warnings.append(f"Overclaim language: {', '.join(overclaims)}")
        claim_reports.append({
            "claim": sentence,
            "support": support,
            "support_authority": "none",
            "basis": "unverified_token_overlap",
            "evidence_overlap": evidence_overlap,
            "ontology_overlap": ontology_overlap,
            "warnings": overclaims,
        })

    score = 100
    score -= sum(35 for claim in claim_reports if claim["support"] == "no_match")
    score -= sum(15 for claim in claim_reports if claim["support"] == "lexical_match_weak")
    score -= len(warnings) * 10
    score = max(0, min(100, score))
    return {
        "claims": claim_reports,
        "support_authority": "none",
        "basis": "unverified_token_overlap",
        "warnings": warnings,
        "recommended_revision_notes": [
            "Attach independently verified evidence to claims without a lexical match.",
            "Soften absolute language when evidence is limited.",
        ] if warnings or any(c["support"] != "lexical_match" for c in claim_reports) else [],
        "overall_guard_score": score,
    }
