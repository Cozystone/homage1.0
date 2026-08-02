from __future__ import annotations

import math
from datetime import datetime, timezone
from typing import Any, Literal

from fastapi import APIRouter
from pydantic import BaseModel, Field

from app.services.web_search import DEFAULT_QUERY, search_web

router = APIRouter(prefix="/api/factory", tags=["factory"])

LearningVolume = Literal["lite", "standard", "deep", "max", "infinite"]


class BuildStartRequest(BaseModel):
    learning_volume: LearningVolume = "standard"
    target_nodes: int | None = Field(default=None, ge=100, le=500_000)
    seed_urls: list[str] | None = None
    search_query: str | None = None
    web_search: bool = True
    web_search_provider: str | None = None


MAX_TARGET_NODES = 500_000
MAX_VISUAL_NODE_BUDGET = 2_000
MAX_CHUNK_BUDGET = 4_096
MAX_TEXT_BUDGET_CHARS = 4_800_000


SEED_URLS = [
    "https://www.reddit.com/r/MachineLearning/comments/1ookxb0/r_knowledge_graph_traversal_with_llms_and/?tl=ko",
    "https://github.com/glacier-creative-git/similarity-graph-traversal-semantic-rag-research",
    "https://github.com/microsoft/graphrag",
    "https://github.com/666ghj/MiroFish",
]

PRESETS = {
    "lite": {"chunkBudget": 32, "label": "Lite", "targetNodes": 3_000, "textBudgetChars": 12_000, "textBudgetLabel": "12k chars", "visualNodeBudget": 12},
    "standard": {"chunkBudget": 128, "label": "Standard", "targetNodes": 10_000, "textBudgetChars": 48_000, "textBudgetLabel": "48k chars", "visualNodeBudget": 24},
    "deep": {"chunkBudget": 384, "label": "Deep", "targetNodes": 25_000, "textBudgetChars": 160_000, "textBudgetLabel": "160k chars", "visualNodeBudget": 36},
    "max": {"chunkBudget": 4096, "label": "Max", "targetNodes": 500_000, "textBudgetChars": 4_500_000, "textBudgetLabel": "4.5m chars", "visualNodeBudget": 2000},
    "infinite": {"chunkBudget": 4096, "label": "Infinite", "targetNodes": None, "textBudgetChars": 4_800_000, "textBudgetLabel": "continuous", "visualNodeBudget": 2000},
}
MEMORY_TOPICS = [
    ("entity-cache", "Entity Cache", "ontology"),
    ("claim-store", "Claim Store", "guardrail"),
    ("chunk-router", "Chunk Router", "retrieval"),
    ("event-gate", "SNN Event Gate", "source"),
    ("fewshot-proto", "Few-shot Prototype", "training"),
    ("self-supervised", "Masked Signal", "training"),
    ("quant-plan", "Quantization Plan", "training"),
    ("replay-buffer", "Replay Buffer", "ontology"),
    ("citation-map", "Citation Map", "retrieval"),
    ("quality-band", "Quality Band", "guardrail"),
    ("semantic-anchor", "Semantic Anchor", "retrieval"),
    ("synapse-plastic", "Synapse Plasticity", "ontology"),
    ("distill-student", "Distilled Student", "training"),
    ("energy-route", "Energy Route", "visualization"),
    ("memory-index", "Memory Index", "ontology"),
    ("context-bridge", "Context Bridge", "retrieval"),
    ("source-license", "Source License", "guardrail"),
    ("edge-summary", "Edge Summary", "visualization"),
    ("task-router", "Task Router", "training"),
    ("novelty-score", "Novelty Score", "ontology"),
    ("graph-window", "Graph Window", "visualization"),
    ("guard-memory", "Guard Memory", "guardrail"),
    ("token-pack", "Token Pack", "source"),
    ("adaptive-batch", "Adaptive Batch", "training"),
    ("extracts-signal", "Extracts Signal", "verb"),
    ("evidence-phrase", "Evidence Phrase", "phrase"),
    ("co-occurs", "Co-occurrence", "relation"),
]


@router.post("/build/start")
async def build_start(payload: BuildStartRequest) -> dict[str, Any]:
    preset = _learning_preset(payload.learning_volume, payload.target_nodes)
    search_payload = (
        await search_web(payload.search_query or DEFAULT_QUERY, 6, payload.web_search_provider)
        if payload.web_search
        else {"provider": "disabled", "query": payload.search_query or DEFAULT_QUERY, "results": [], "status": "disabled"}
    )
    search_urls = [result["url"] for result in search_payload.get("results", []) if result.get("url")]
    merged_urls = [*(payload.seed_urls or []), *search_urls, *SEED_URLS]
    deduped_urls = list(dict.fromkeys(merged_urls))[:8]
    docs = [_harvest_doc(url, index, search_payload) for index, url in enumerate(deduped_urls)]
    units = _training_units(docs, preset)
    graph = _graph_for_preset(preset)
    nodes = graph["nodes"]
    edges = graph["edges"]
    frames = _graph_frames(len(nodes))
    continuous = preset["id"] == "infinite"
    training_gate = {
        "threshold_nodes": 8,
        "threshold_edges": 7,
        "chunk_count": len(units),
        "node_count": len(nodes),
        "edge_count": len(edges),
        "evidence_count": len(docs),
        "text_budget_chars": preset["textBudgetChars"],
        "ready": len(nodes) >= 8 and len(edges) >= 7,
        "render_strategy": (
            "continuous collection accumulates graph events; the lab view appends live nodes without hidden history."
            if continuous
            else "target_nodes is a long-run storage goal; graph_3d renders a bounded representative sample."
        ),
        "visual_node_budget": preset["visualNodeBudget"],
        "target_nodes": preset["targetNodes"],
        "target_semantics": "unbounded_continuous_goal" if preset["targetNodes"] is None else "long_run_storage_goal",
        "representative_node_count": len(nodes),
        "representative_edge_count": len(edges),
        "target_realized": False if preset["targetNodes"] is None else len(nodes) >= preset["targetNodes"],
        "sampling_explanation": (
            "infinite mode has no target_nodes cap; graph_3d contains a bounded rolling representative sample for browser rendering."
            if preset["targetNodes"] is None
            else "target_nodes is the long-run ontology budget; graph_3d contains a bounded representative sample for browser rendering."
        ),
        "continuous": continuous,
        "next_action": (
            "Continue Harvest/DataGate/Ontology growth until the operator presses stop."
            if continuous
            else "Representative build sample is ready; persistent graph events are the next milestone."
        ),
    }
    return {
        "run_id": f"build-{int(datetime.now(timezone.utc).timestamp() * 1000)}",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "mode": "alpha-continuous-harvest" if continuous else "alpha-live-harvest",
        "harvest_docs": docs,
        "web_search": search_payload,
        "learning_profile": {
            "id": preset["id"],
            "label": preset["label"],
            "text_budget_chars": preset["textBudgetChars"],
            "text_budget_label": preset["textBudgetLabel"],
            "chunk_budget": preset["chunkBudget"],
            "target_nodes": preset["targetNodes"],
            "visual_node_budget": preset["visualNodeBudget"],
        },
        "training_units": units[:24],
        "graph_3d": graph,
        "graph_frames": frames,
        "training_gate": training_gate,
        "learning_trace": [
            {"step": "Harvest", "state": "running" if continuous else "complete", "detail": f"{len(docs)} reference sources captured via {search_payload.get('provider', 'static')} / {len(units)} text chunks scheduled"},
            {"step": "DataGate", "state": "complete", "detail": f"{preset['textBudgetLabel']} text budget passed through compressed chunk routing"},
            {"step": "Ontology Forge", "state": "running" if continuous else "complete", "detail": f"{len(nodes)} representative nodes and {len(edges)} typed relations created"},
            {"step": "GraphRAG", "state": "complete", "detail": "Anchor traversal path and evidence bundle generated"},
            {"step": "ATANOR Oven", "state": "ready" if training_gate["ready"] else "waiting", "detail": training_gate["next_action"]},
        ],
        "notes": [
            "Alpha stores representative graph samples for the browser; target_nodes is the long-run storage/training budget.",
            "Durable graph event persistence is the next milestone before target_nodes can be fully realized locally.",
        ],
    }


def _learning_preset(volume: str, target_nodes_input: int | None) -> dict[str, Any]:
    base = PRESETS.get(volume, PRESETS["standard"])
    if volume == "infinite":
        return {
            **base,
            "id": volume,
            "targetNodes": None,
            "visualNodeBudget": MAX_VISUAL_NODE_BUDGET,
            "chunkBudget": MAX_CHUNK_BUDGET,
            "textBudgetChars": MAX_TEXT_BUDGET_CHARS,
            "textBudgetLabel": "continuous",
        }
    fallback_target_nodes = MAX_TARGET_NODES if volume == "max" else base["targetNodes"]
    target_nodes = max(100, min(MAX_TARGET_NODES, int(target_nodes_input or fallback_target_nodes)))
    visual_node_budget = max(base["visualNodeBudget"], min(MAX_VISUAL_NODE_BUDGET, round(target_nodes**0.5 * 4.8)))
    chunk_budget = max(base["chunkBudget"], min(MAX_CHUNK_BUDGET, round(target_nodes / 12)))
    text_budget_chars = max(base["textBudgetChars"], min(MAX_TEXT_BUDGET_CHARS, target_nodes * 9))
    text_budget_label = "continuous" if volume == "infinite" else (f"{round(text_budget_chars / 1000)}k chars")
    return {
        **base,
        "id": volume,
        "targetNodes": target_nodes,
        "visualNodeBudget": visual_node_budget,
        "chunkBudget": chunk_budget,
        "textBudgetChars": text_budget_chars,
        "textBudgetLabel": text_budget_label,
    }


def _harvest_doc(url: str, index: int, search_payload: dict[str, Any] | None = None) -> dict[str, Any]:
    search_results = {result.get("url"): result for result in (search_payload or {}).get("results", [])}
    result = search_results.get(url, {})
    return {
        "id": f"web-{index + 1:03d}",
        "url": url,
        "title": result.get("title") or url.split("//", 1)[-1].split("/", 1)[0],
        "status": "fallback",
        "snippet": result.get("snippet") or "Reference signal queued for local ATANOR Factory Build.",
        "source_type": result.get("source_type") or ("discussion" if "reddit" in url else "repository_or_docs"),
        "license_status": result.get("license_status") or "reference_only",
        "search_provider": result.get("provider") or (search_payload or {}).get("provider", "seed"),
        "search_query": (search_payload or {}).get("query"),
        "bing_query_url": (search_payload or {}).get("bing_query_url"),
    }


def _training_units(docs: list[dict[str, Any]], preset: dict[str, Any]) -> list[dict[str, Any]]:
    units = []
    for index in range(preset["chunkBudget"]):
        doc = docs[index % max(1, len(docs))]
        topic = MEMORY_TOPICS[index % len(MEMORY_TOPICS)]
        units.append(
            {
                "id": f"chunk-{index + 1:04d}",
                "source_id": doc["id"],
                "topic": topic[1],
                "char_budget": max(180, preset["textBudgetChars"] // max(1, preset["chunkBudget"])),
                "text_preview": f"{doc['snippet']} {topic[1]} GraphRAG ontology memory".strip()[:240],
                "route": "TRAINABLE" if index % 3 == 0 else "RAG_ONLY" if index % 3 == 1 else "REVIEW",
            }
        )
    return units


def _hash01(value: str, salt: int) -> float:
    hash_value = 2166136261 ^ salt
    for char in value:
        hash_value ^= ord(char)
        hash_value = (hash_value * 16777619) & 0xFFFFFFFF
    return hash_value / 0xFFFFFFFF


def _volume_offset(node_id: str, index: int) -> tuple[float, float, float]:
    u = _hash01(node_id, 13) * 2 - 1
    theta = _hash01(node_id, 29) * math.tau
    radial = math.sqrt(max(0.0001, 1 - u * u))
    radius = min(4.8, 0.92 + math.pow(index + 1, 1 / 3) * 0.27 + (index % 17) * 0.025)
    return (
        math.cos(theta) * radial * radius,
        u * radius * 0.96,
        math.sin(theta) * radial * radius,
    )


def _graph_for_preset(preset: dict[str, Any]) -> dict[str, Any]:
    base_nodes = [
        {"id": "harvest", "label": "Web Harvest", "type": "source", "x": -5, "y": 1.4, "z": -1.2, "confidence": 0.86},
        {"id": "reddit-kg", "label": "KG vs SSG", "type": "critique", "x": -2.8, "y": 2.3, "z": 0.6, "confidence": 0.9},
        {"id": "dedupe", "label": "Entity Dedupe", "type": "ontology", "x": -1.1, "y": 0.8, "z": 1.8, "confidence": 0.84},
        {"id": "mutable-kg", "label": "Mutable KG", "type": "ontology", "x": -0.2, "y": -1.2, "z": -0.7, "confidence": 0.79},
        {"id": "anchor", "label": "Anchor Chunk", "type": "retrieval", "x": 1.5, "y": 1.7, "z": -1.5, "confidence": 0.86},
        {"id": "traversal", "label": "Graph Traversal", "type": "retrieval", "x": 3.1, "y": 0.2, "z": 1.2, "confidence": 0.88},
        {"id": "3d", "label": "3D Triangulation", "type": "visualization", "x": 4.2, "y": -1.5, "z": -0.2, "confidence": 0.81},
        {"id": "guard", "label": "Guarded Evidence", "type": "guardrail", "x": 2.6, "y": -2.4, "z": 1.7, "confidence": 0.78},
        {"id": "oven", "label": "ATANOR Oven Gate", "type": "training", "x": 5.4, "y": 0.9, "z": 0.5, "confidence": 0.76},
    ]
    seed_budget = min(preset["visualNodeBudget"], max(12, round(preset["visualNodeBudget"] * 0.86)))
    extra_count = max(0, seed_budget - len(base_nodes))
    extra_nodes = []
    for index in range(extra_count):
        topic = MEMORY_TOPICS[index % len(MEMORY_TOPICS)]
        wave = index // len(MEMORY_TOPICS)
        anchor_node = base_nodes[index % len(base_nodes)]
        offset_x, offset_y, offset_z = _volume_offset(f"{topic[0]}-{wave}-{index}", index)
        center_pull = 0.1 + (index % 5) * 0.015
        extra_nodes.append(
            {
                "id": f"{topic[0]}-{wave + 1}" if wave else topic[0],
                "label": f"{topic[1]} {wave + 1}" if wave else topic[1],
                "type": topic[2],
                "x": anchor_node["x"] * (1 - center_pull) + offset_x,
                "y": anchor_node["y"] * (1 - center_pull) + offset_y,
                "z": anchor_node["z"] * (1 - center_pull) + offset_z,
                "confidence": 0.68 + (index % 8) * 0.025,
            }
        )
    nodes = [*base_nodes, *extra_nodes]
    base_edges = [
        {"source": "harvest", "target": "reddit-kg", "relation": "extracts_signal", "weight": 0.82},
        {"source": "reddit-kg", "target": "dedupe", "relation": "requires", "weight": 0.86},
        {"source": "dedupe", "target": "mutable-kg", "relation": "stabilizes", "weight": 0.74},
        {"source": "mutable-kg", "target": "anchor", "relation": "seeds", "weight": 0.69},
        {"source": "anchor", "target": "traversal", "relation": "starts", "weight": 0.88},
        {"source": "traversal", "target": "3d", "relation": "projects", "weight": 0.73},
        {"source": "traversal", "target": "guard", "relation": "grounds", "weight": 0.8},
        {"source": "guard", "target": "oven", "relation": "approves_training", "weight": 0.71},
    ]
    extra_edges = []
    for index, node in enumerate(extra_nodes):
        anchor = base_nodes[index % len(base_nodes)]["id"]
        extra_edges.append({"source": anchor, "target": node["id"], "relation": "compresses_chunk", "weight": 0.62 + (index % 5) * 0.04})
        previous_same_anchor = index - len(base_nodes)
        if previous_same_anchor >= 0:
            extra_edges.append({"source": extra_nodes[previous_same_anchor]["id"], "target": node["id"], "relation": "associates", "weight": 0.52})
    return {
        "nodes": nodes,
        "edges": [*base_edges, *extra_edges],
        "traversal_path": ["harvest", "reddit-kg", "dedupe", "mutable-kg", "anchor", "traversal", "guard", "oven", *[node["id"] for node in extra_nodes[:8]]],
    }


def _graph_frames(node_count: int) -> list[dict[str, Any]]:
    counts: list[int] = []
    for count in [min(12, node_count), math.ceil(node_count * 0.25), math.ceil(node_count * 0.5), math.ceil(node_count * 0.75), node_count]:
        if not counts or count > counts[-1]:
            counts.append(count)
    messages = [
        "Collection seeded sentence chunks and graph anchors",
        "Sentence elements were decomposed into candidate nodes",
        "Ontology relations were calculated",
        "GraphRAG neighborhood projection expanded",
        "Output gate reached selected text budget",
    ]
    return [
        {"tick": index + 1, "node_count": count, "edge_count": max(1, count - 1), "message": messages[index]}
        for index, count in enumerate(counts)
    ]
