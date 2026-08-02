from __future__ import annotations

import hashlib
import math
import re
from collections import defaultdict
from typing import Any


MAX_DIRECT_EDGES = 8
DOMAIN_LABELS = (
    "graph_accumulation",
    "semantic_routing",
    "evidence_grounding",
    "surface_planning",
    "working_memory",
    "resonance_validation",
    "chunk_materialization",
    "answer_repair",
)


def _hash_unit(seed: str, salt: str = "") -> float:
    digest = hashlib.sha256(f"{salt}:{seed}".encode("utf-8")).hexdigest()
    return int(digest[:12], 16) / float(0xFFFFFFFFFFFF)


def _stable_int(seed: str, modulo: int) -> int:
    if modulo <= 1:
        return 0
    digest = hashlib.sha256(seed.encode("utf-8")).hexdigest()
    return int(digest[:10], 16) % modulo


def _label_for_node(node: dict[str, Any]) -> str:
    return str(node.get("label") or node.get("canonical_name") or node.get("concept_id") or node.get("id") or "")


def semantic_domain_for_node(node: dict[str, Any]) -> str:
    metadata = node.get("metadata") if isinstance(node.get("metadata"), dict) else {}
    explicit = node.get("planetary_domain") or metadata.get("planetary_domain")
    if explicit:
        return str(explicit)
    label = _label_for_node(node).casefold()
    normalized = re.sub(r"[\s\-]+", "_", label)
    for domain in DOMAIN_LABELS:
        if domain in normalized or domain.replace("_", " ") in label:
            return domain
    match = re.search(r"atanorseedconcept(\d+)", normalized)
    if match:
        return DOMAIN_LABELS[int(match.group(1)) % len(DOMAIN_LABELS)]
    return DOMAIN_LABELS[_stable_int(str(node.get("id") or label), len(DOMAIN_LABELS))]


def planetary_position(node_id: str, domain: str, *, local_index: int = 0) -> tuple[float, float, float]:
    """Place a materialized semantic node in a deterministic spherical chunk.

    Every rendered point remains a real semantic node. Domains are kept as
    metadata for color/grouping, but the spatial position is a deterministic
    spherical hash so the cloud reads as a volumetric shell instead of a domain
    slab or hub-spoke sheet.
    """
    ordinal = _stable_int(f"{domain}:{node_id}:sphere", 10_000_000)
    golden_fraction = (ordinal * 0.6180339887498949 + _hash_unit(domain, "domain_phase")) % 1.0
    theta = math.tau * golden_fraction
    cos_phi = max(-0.98, min(0.98, 1.0 - 2.0 * _hash_unit(node_id, "sphere_z")))
    sin_phi = math.sqrt(max(0.0, 1.0 - cos_phi * cos_phi))

    # A bounded volume shell gives depth without pretending every logical node is
    # rendered. The cube root keeps density visually even across the sphere.
    radius_unit = _hash_unit(f"{node_id}:{local_index}", "sphere_radius")
    local_radius = 3.65 + 3.95 * (radius_unit ** (1.0 / 3.0))
    return (
        round(math.cos(theta) * sin_phi * local_radius, 5),
        round(cos_phi * local_radius, 5),
        round(math.sin(theta) * sin_phi * local_radius, 5),
    )


def _edge_weight(edge: dict[str, Any]) -> float:
    try:
        return float(edge.get("weight") or edge.get("confidence") or 0.5)
    except (TypeError, ValueError):
        return 0.5


def _edge_key(edge: dict[str, Any]) -> str:
    return str(edge.get("id") or f"{edge.get('source')}:{edge.get('relation')}:{edge.get('target')}")


def _make_seed_node(node_id: str, label: str, domain: str, role: str, source_node_id: str, index: int) -> dict[str, Any]:
    x, y, z = planetary_position(node_id, domain, local_index=index)
    return {
        "id": node_id,
        "label": label,
        "concept_id": node_id,
        "aliases": [label],
        "language_labels": {"en": label},
        "trust": 0.62,
        "confidence": 0.62,
        "seen_count": 1,
        "source_scope": "cloud",
        "proof_store_only": True,
        "provenance_type": "planetary_topology_runtime",
        "source_label": "Planetary topology materialization",
        "is_demo_sample": False,
        "is_autonomous_growth": False,
        "local_brain_write": False,
        "x": x,
        "y": y,
        "z": z,
        "metadata": {
            "planetary_domain": domain,
            "topology_role": role,
            "source_super_node_id": source_node_id,
            "is_semantic_node": False,
            "is_materialization_container": True,
            "counts_as_logical_cloud_node": False,
        },
    }


def _make_topology_edge(source: str, target: str, relation: str, role: str, hub_id: str, index: int) -> dict[str, Any]:
    edge_id = f"planet-edge:{role}:{hub_id}:{index}:{hashlib.sha256(f'{source}:{target}:{relation}'.encode('utf-8')).hexdigest()[:10]}"
    return {
        "id": edge_id,
        "source": source,
        "target": target,
        "relation": relation,
        "weight": 0.42,
        "confidence": 0.62,
        "seen_count": 1,
        "source_scope": "cloud",
        "proof_store_only": True,
        "provenance_type": "planetary_topology_runtime",
        "source_label": "Planetary topology materialization",
        "is_demo_sample": False,
        "is_autonomous_growth": False,
        "local_brain_write": False,
        "metadata": {
            "topology_role": role,
            "source_super_node_id": hub_id,
            "is_semantic_relation": False,
            "is_materialization_edge": True,
        },
    }


def _rewire_edge(edge: dict[str, Any], hub_id: str, relay_id: str, index: int) -> dict[str, Any]:
    rewired = dict(edge)
    original_source = str(edge.get("source"))
    original_target = str(edge.get("target"))
    rewired["id"] = f"planet-rewired:{_edge_key(edge)}:{index}:{relay_id}"
    if original_source == hub_id:
        rewired["source"] = relay_id
    elif original_target == hub_id:
        rewired["target"] = relay_id
    rewired["metadata"] = {
        **(edge.get("metadata") if isinstance(edge.get("metadata"), dict) else {}),
        "topology_role": "rewired_semantic_edge",
        "rewired_from_super_node": hub_id,
        "original_source": original_source,
        "original_target": original_target,
        "direct_edge_cap": MAX_DIRECT_EDGES,
    }
    return rewired


def _build_bounded_relay_tree(
    hub_id: str,
    hub_domain: str,
    leaf_nodes: list[dict[str, Any]],
    *,
    max_direct_edges: int,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    if len(leaf_nodes) <= max_direct_edges:
        edges = [
            _make_topology_edge(hub_id, str(leaf["id"]), "organizes_sub_seed", "hub_to_leaf_seed", hub_id, index)
            for index, leaf in enumerate(leaf_nodes)
        ]
        return [], edges
    fanout = max(2, max_direct_edges - 1)
    current = leaf_nodes
    all_internal: list[dict[str, Any]] = []
    all_edges: list[dict[str, Any]] = []
    depth = 0
    while len(current) > max_direct_edges:
        next_level: list[dict[str, Any]] = []
        for group_index in range(0, len(current), fanout):
            children = current[group_index:group_index + fanout]
            relay_id = f"planet-relay:{hub_id}:{depth}:{group_index // fanout}"
            relay = _make_seed_node(
                relay_id,
                f"{hub_domain} orbit {depth}-{group_index // fanout}",
                hub_domain,
                "orbit_relay",
                hub_id,
                group_index,
            )
            all_internal.append(relay)
            next_level.append(relay)
            for child_index, child in enumerate(children):
                all_edges.append(
                    _make_topology_edge(
                        relay_id,
                        str(child["id"]),
                        "splits_to_sub_seed",
                        "relay_to_child_seed",
                        hub_id,
                        group_index + child_index,
                    )
                )
        current = next_level
        depth += 1
    for index, child in enumerate(current):
        all_edges.append(_make_topology_edge(hub_id, str(child["id"]), "organizes_orbit", "hub_to_orbit", hub_id, index))
    return all_internal, all_edges


def planetize_graph_sample(
    nodes: list[dict[str, Any]],
    edges: list[dict[str, Any]],
    *,
    max_direct_edges: int = MAX_DIRECT_EDGES,
) -> dict[str, Any]:
    """Project a semantic graph sample into a bounded-degree planetary topology.

    The returned sub-seed and relay nodes are materialization containers, not
    semantic aggregate nodes. Real logical cloud nodes remain individually
    addressable; this only prevents any rendered/read-path node from becoming a
    black-hole hub with unbounded direct edges.
    """

    node_map = {str(node.get("id")): dict(node) for node in nodes if node.get("id")}
    domain_counts: dict[str, int] = defaultdict(int)
    for node_id, node in node_map.items():
        domain = semantic_domain_for_node(node)
        local_index = domain_counts[domain]
        domain_counts[domain] += 1
        x, y, z = planetary_position(node_id, domain, local_index=local_index)
        metadata = node.get("metadata") if isinstance(node.get("metadata"), dict) else {}
        node.update({
            "x": x,
            "y": y,
            "z": z,
            "cluster_id": f"planet:{domain}",
            "planetary_domain": domain,
            "metadata": {
                **metadata,
                "planetary_domain": domain,
                "cluster_id": f"planet:{domain}",
                "topology_role": metadata.get("topology_role") or "logical_cloud_node",
                "is_semantic_node": True,
                "is_materialization_container": False,
            },
        })

    incident: dict[str, list[dict[str, Any]]] = defaultdict(list)
    normalized_edges: list[dict[str, Any]] = []
    for edge in edges:
        source = str(edge.get("source") or "")
        target = str(edge.get("target") or "")
        if source not in node_map or target not in node_map or source == target:
            continue
        row = dict(edge)
        row["source"] = source
        row["target"] = target
        normalized_edges.append(row)
        incident[source].append(row)
        incident[target].append(row)

    hubs = {node_id for node_id, rows in incident.items() if len(rows) > max_direct_edges}
    if not hubs:
        return {
            "nodes": list(node_map.values()),
            "edges": normalized_edges,
            "topology": {
                "mode": "planetary_galaxy",
                "max_direct_edges": max_direct_edges,
                "super_nodes_split": 0,
                "sub_seed_nodes_created": 0,
                "relay_nodes_created": 0,
                "rewired_edges": 0,
                "domains": sorted(set(semantic_domain_for_node(node) for node in node_map.values())),
            },
        }

    untouched_edges = [
        edge for edge in normalized_edges
        if edge["source"] not in hubs and edge["target"] not in hubs
    ]
    synthetic_nodes: dict[str, dict[str, Any]] = {}
    synthetic_edges: list[dict[str, Any]] = []
    rewired_edges: list[dict[str, Any]] = []

    for hub_id in sorted(hubs):
        hub = node_map[hub_id]
        hub_domain = semantic_domain_for_node(hub)
        hub_edges = sorted(incident[hub_id], key=_edge_weight, reverse=True)
        leaf_nodes: list[dict[str, Any]] = []
        leaf_edge_groups: list[list[dict[str, Any]]] = []
        grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for edge in hub_edges:
            other_id = edge["target"] if edge["source"] == hub_id else edge["source"]
            other = node_map.get(other_id)
            other_domain = semantic_domain_for_node(other or {"id": other_id})
            grouped[other_domain].append(edge)
        leaf_index = 0
        leaf_capacity = max(1, max_direct_edges - 1)
        for domain, rows in sorted(grouped.items()):
            for offset in range(0, len(rows), leaf_capacity):
                chunk = rows[offset:offset + leaf_capacity]
                leaf_id = f"planet-subseed:{hub_id}:{domain}:{offset // leaf_capacity}"
                leaf = _make_seed_node(
                    leaf_id,
                    f"{domain} sub-seed",
                    domain,
                    "sub_seed",
                    hub_id,
                    leaf_index,
                )
                synthetic_nodes[leaf_id] = leaf
                leaf_nodes.append(leaf)
                leaf_edge_groups.append(chunk)
                leaf_index += 1
        internal_nodes, tree_edges = _build_bounded_relay_tree(hub_id, hub_domain, leaf_nodes, max_direct_edges=max_direct_edges)
        for node in internal_nodes:
            synthetic_nodes[str(node["id"])] = node
        synthetic_edges.extend(tree_edges)
        for leaf, chunk in zip(leaf_nodes, leaf_edge_groups):
            for edge_index, edge in enumerate(chunk):
                rewired_edges.append(_rewire_edge(edge, hub_id, str(leaf["id"]), edge_index))

    output_edges = untouched_edges + synthetic_edges + rewired_edges
    degree: dict[str, int] = defaultdict(int)
    for edge in output_edges:
        degree[str(edge.get("source"))] += 1
        degree[str(edge.get("target"))] += 1
    max_degree_after = max(degree.values()) if degree else 0
    return {
        "nodes": list(node_map.values()) + list(synthetic_nodes.values()),
        "edges": output_edges,
        "topology": {
            "mode": "planetary_galaxy",
            "max_direct_edges": max_direct_edges,
            "super_nodes_split": len(hubs),
            "sub_seed_nodes_created": len([node for node in synthetic_nodes.values() if node.get("metadata", {}).get("topology_role") == "sub_seed"]),
            "relay_nodes_created": len([node for node in synthetic_nodes.values() if node.get("metadata", {}).get("topology_role") == "orbit_relay"]),
            "rewired_edges": len(rewired_edges),
            "max_degree_before": max((len(rows) for rows in incident.values()), default=0),
            "max_degree_after": max_degree_after,
            "domains": sorted(set(semantic_domain_for_node(node) for node in node_map.values())),
            "semantic_aggregate_nodes_used": False,
            "materialization_containers_used": True,
        },
    }
