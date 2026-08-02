from __future__ import annotations

import hashlib
from typing import Any

from .cartridge_profiler import profile_installed_cartridge
from .cartridge_profile import SynergyMatchResult, to_dict
from .local_fingerprint import SEED_PRIMITIVES, local_seed_fingerprint


def _bounded_pct(value: float) -> float:
    return round(max(0.0, min(100.0, value)), 2)


def _cartridge_fingerprint(report: dict[str, Any]) -> dict[str, Any]:
    tags = [str(tag).casefold() for tag in report.get("ontology_tags") or []]
    toc = [str(row).casefold() for row in report.get("structural_toc") or []]
    payload = "|".join(sorted(tags + toc))
    return {
        "fingerprint_hash": hashlib.sha256(payload.encode("utf-8")).hexdigest(),
        "tags": tags,
        "toc": toc,
        "raw_cartridge_loaded": bool(report.get("full_load_performed")),
    }


def score_cartridge_synergy(cartridge_id: str, *, active_context: str | None = None) -> dict[str, Any]:
    local = local_seed_fingerprint(active_context)
    report = profile_installed_cartridge(cartridge_id, offline_inspection=False)
    cartridge = _cartridge_fingerprint(report)
    tags = set(cartridge["tags"])
    primitive_matches = {primitive for primitive in SEED_PRIMITIVES if primitive in tags or any(primitive in tag for tag in tags)}
    context_terms = {term.casefold() for term in (active_context or "").replace("?", " ").replace(",", " ").split() if len(term) > 1}
    context_matches = {term for term in context_terms if any(term in tag for tag in tags)}
    overlap_score = min(1.0, (len(primitive_matches) * 0.08) + (len(context_matches) * 0.16))
    novelty_score = max(0.0, min(1.0, 0.55 + len(tags - set(SEED_PRIMITIVES)) * 0.03 - overlap_score * 0.2))
    soundness = float(report.get("soundness_score") or 0.0)
    malicious_risk = float(report.get("malicious_pattern_risk") or 0.0)
    constructive = _bounded_pct((0.48 + overlap_score * 0.26 + novelty_score * 0.12 + soundness * 0.14) * 100)
    conflict = _bounded_pct((1.0 - soundness + malicious_risk) * 18)
    recommended_chunks = max(1, min(6, int(round(1 + overlap_score * 4 + novelty_score))))
    predicted_latency = int(160 + recommended_chunks * 42 + int(report.get("profile", {}).get("relation_count") or 0) * 2)
    risk_flags: list[str] = []
    if conflict > 10:
        risk_flags.append("review_conflict_risk")
    if malicious_risk > 0:
        risk_flags.append("malicious_pattern_review")
    if report.get("inspection_status") == "rejected":
        risk_flags.append("profiler_rejected")
    safe = report.get("inspection_status") != "rejected" and conflict <= 18 and malicious_risk < 0.2
    result = SynergyMatchResult(
        local_fingerprint_hash=str(local["fingerprint_hash"]),
        cartridge_fingerprint_hash=str(cartridge["fingerprint_hash"]),
        constructive_interference_pct=constructive,
        conflict_node_pct=conflict,
        overlap_score=round(overlap_score, 4),
        novelty_score=round(novelty_score, 4),
        predicted_latency_ms=predicted_latency,
        recommended_active_chunks=recommended_chunks,
        risk_flags=risk_flags,
        explanation="Predicted estimate from hashed Seed primitive distribution, cartridge tags, topology health, and portable chunk metadata.",
        safe_to_trial=safe,
    )
    return {
        **to_dict(result),
        "raw_local_graph_uploaded": False,
        "raw_local_graph_included": False,
        "full_cloud_store_scan": False,
        "pair_edges_sent": 0,
    }
