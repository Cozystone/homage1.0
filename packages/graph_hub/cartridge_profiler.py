from __future__ import annotations

import hashlib
from collections import Counter
from pathlib import Path
from typing import Any

from .cartridge_format import validate_cartridge_schema, verify_cartridge_checksum
from .cartridge_mount import attach_cartridge_namespace, list_mounted_cartridges
from .cartridge_profile import CartridgeCentroid, CartridgeProfile, ProfilerReport, to_dict
from .catalog import get_catalog_item
from .installer import get_installed_cartridge
from .models import read_json, stable_id
from .soundness import graph_soundness_checks


def _hash_jsonish(value: Any) -> str:
    return hashlib.sha256(repr(value).encode("utf-8")).hexdigest()[:24]


def _centroids(nodes: list[dict[str, Any]], edges: list[dict[str, Any]], limit: int = 6) -> list[dict[str, Any]]:
    degree: Counter[str] = Counter()
    labels = {str(node.get("id")): str(node.get("label") or node.get("id")) for node in nodes}
    for edge in edges:
        source = str(edge.get("source") or "")
        target = str(edge.get("target") or "")
        degree[source] += 1
        degree[target] += 1
    rows = [
        to_dict(CartridgeCentroid(label=labels.get(node_id, node_id), degree=count, risk="high_fanout" if count > 24 else "normal"))
        for node_id, count in degree.most_common(limit)
    ]
    return rows


def _toc(cartridge: dict[str, Any], nodes: list[dict[str, Any]], edges: list[dict[str, Any]]) -> list[str]:
    contents = cartridge.get("contents") or {}
    surface = contents.get("surface_graph") or {}
    toc = [
        f"semantic:{len(nodes)} nodes",
        f"relations:{len(edges)} edges",
        f"surface:{len(surface.get('constructions') or [])} constructions",
        f"patterns:{len(contents.get('reasoning_patterns') or [])} reasoning patterns",
    ]
    return toc


def profile_cartridge_payload(cartridge: dict[str, Any], *, full_load_performed: bool) -> dict[str, Any]:
    cartridge_id = str(cartridge.get("cartridge_id") or "unknown")
    validation = validate_cartridge_schema(cartridge)
    contents = cartridge.get("contents") or {}
    semantic = contents.get("semantic_graph") or {}
    nodes = list(semantic.get("nodes") or [])
    edges = list(semantic.get("edges") or [])
    tags = [str(tag) for tag in (cartridge.get("metadata") or {}).get("tags") or []]
    soundness = graph_soundness_checks(nodes, edges)
    issues = list(soundness["issues"])
    if not validation["valid"]:
        issues.extend({"issue_id": err, "severity": "blocker", "message": err} for err in validation["errors"])
    signature_status = "valid" if validation["valid"] else "invalid"
    if full_load_performed:
        signature_status = "valid" if validation["valid"] else "invalid"
    blocker_count = sum(1 for issue in issues if issue.get("severity") == "blocker")
    review_count = sum(1 for issue in issues if issue.get("severity") == "review")
    if blocker_count:
        inspection_status = "rejected"
        recommendation = "reject_until_blockers_fixed"
    elif review_count:
        inspection_status = "review_required"
        recommendation = "manual_review_before_trial"
    else:
        inspection_status = "passed"
        recommendation = "safe_for_bounded_trial"
    report = ProfilerReport(
        cartridge_id=cartridge_id,
        inspection_status=inspection_status,
        ontology_tags=tags,
        centroid_summary=_centroids(nodes, edges),
        structural_toc=_toc(cartridge, nodes, edges),
        soundness_score=float(soundness["soundness_score"]),
        topology_health_score=float(soundness["topology_health_score"]),
        malicious_pattern_risk=float(soundness["malicious_pattern_risk"]),
        issues=issues,
        simulated_queries=list(soundness["simulated_queries"]),
        pair_edges_sent=0,
        full_load_performed=full_load_performed,
        recommendation=recommendation,
    )
    return to_dict(report)


def profile_installed_cartridge(cartridge_id: str, *, offline_inspection: bool = False) -> dict[str, Any]:
    installed = get_installed_cartridge(cartridge_id)
    if not installed:
        raise FileNotFoundError(f"not_installed:{cartridge_id}")
    if offline_inspection:
        payload = read_json(Path(str(installed.get("path") or "")), {})
        return profile_cartridge_payload(payload if isinstance(payload, dict) else {}, full_load_performed=True)

    mounted = next((row for row in list_mounted_cartridges() if row.get("cartridge_id") == cartridge_id), None)
    if not mounted:
        mounted = attach_cartridge_namespace(cartridge_id)
    manifest = mounted.get("manifest") or {}
    try:
        catalog = get_catalog_item(cartridge_id)
    except FileNotFoundError:
        catalog = {}
    stats = installed.get("stats") if isinstance(installed.get("stats"), dict) else {}
    tags = [str(tag) for tag in catalog.get("tags") or []]
    profile = CartridgeProfile(
        cartridge_id=cartridge_id,
        namespace=str(manifest.get("namespace") or f"cart:{cartridge_id}"),
        name=str(manifest.get("name") or catalog.get("name") or cartridge_id),
        version=str(manifest.get("version") or installed.get("version") or "0.1.0"),
        domain=str(manifest.get("domain") or catalog.get("category") or "installed_graph_cartridge"),
        node_count=int(stats.get("semantic_nodes") or manifest.get("node_count") or 0),
        relation_count=int(stats.get("semantic_edges") or manifest.get("relation_count") or 0),
        chunk_count=int(manifest.get("chunk_count") or 0),
        centroid_nodes=[],
        semantic_tags=tags,
        structural_toc=[
            f"semantic:{int(stats.get('semantic_nodes') or 0)} nodes",
            f"relations:{int(stats.get('semantic_edges') or 0)} edges",
            f"surface:{int(stats.get('surface_constructions') or 0)} constructions",
        ],
        sqc_dictionary_hash=stable_id("sqc", "|".join(tags) or cartridge_id),
        phase_index_hash=_hash_jsonish(mounted.get("chunk_index") or []),
        merkle_root=str(manifest.get("merkle_root") or ""),
        signature_status="valid" if installed.get("checksum_valid") else "checksum_unverified",
        read_only=True,
        created_at=str(manifest.get("created_at") or installed.get("installed_at") or ""),
    )
    issue = {
        "issue_id": "manifest_only_profile",
        "severity": "info",
        "message": "Profile used installed registry, catalog metadata, and portable chunk index without loading full cartridge payload.",
    }
    report = ProfilerReport(
        cartridge_id=cartridge_id,
        inspection_status="passed" if installed.get("checksum_valid", True) else "review_required",
        ontology_tags=tags,
        centroid_summary=profile.centroid_nodes,
        structural_toc=profile.structural_toc,
        soundness_score=0.82 if installed.get("checksum_valid", True) else 0.62,
        topology_health_score=0.8,
        malicious_pattern_risk=0.0,
        issues=[issue],
        simulated_queries=[],
        pair_edges_sent=0,
        full_load_performed=False,
        recommendation="safe_for_bounded_trial" if installed.get("checksum_valid", True) else "manual_review_before_trial",
    )
    return {**to_dict(report), "profile": to_dict(profile)}
