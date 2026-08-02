import { NextResponse } from "next/server";
import { proxyJson } from "../../../_backend";

// Honest fallback: when no backend is reachable the four count domains stay
// explicitly unknown/zero with their separation flags intact — the UI must never
// substitute a rendered sample or stale total for real store counts.
const emptyLogicalSphereSummary = {
  generated_at: null,
  store_name: "verified_store_v0",
  verified: {
    verified_concepts: 0,
    verified_relations: 0,
    verified_evidence: 0,
    verified_case_frames: 0,
    source: null,
    source_status: "backend_unavailable",
  },
  candidate: {
    candidate_concepts: 0,
    candidate_relations: 0,
    candidate_evidence: 0,
    candidate_case_frames: 0,
    candidate_surface_items: 0,
    candidate_cgsr_items: 0,
    candidate_rhfc_items: 0,
    source: null,
    source_status: "backend_unavailable",
    candidate_is_verified: false,
  },
  working_memory: {
    working_memory_nodes: null,
    working_memory_relations: null,
    working_memory_fragments: null,
    source: null,
    source_status: "unknown_not_implemented",
    temporary: true,
  },
  rendered: {
    rendered_nodes: null,
    rendered_edges: null,
    materialized_nodes: null,
    materialized_edges: null,
    active_chunks: null,
    visible_scale_chunks: null,
    virtualization_enabled: null,
    source: null,
    source_status: "unknown_ui_owned",
  },
  explanations: {
    verified_counts_change_only_after_promotion: true,
    candidate_counts_are_unpromoted_learning: true,
    rendered_counts_are_view_budget_not_total_graph: true,
    working_memory_is_temporary: true,
    local_brain_write_default: false,
  },
  invariants: {
    production_store_mutated: false,
    local_brain_write: false,
    candidate_promotion: false,
    external_llm_used: false,
    mock_growth: false,
    real_p2p_used: false,
    generated_code_executed: false,
  },
};

export async function GET() {
  try {
    const proxied = await proxyJson("/api/cloud-brain/logical-sphere/summary");
    if (proxied) return NextResponse.json(proxied.body, { status: proxied.status });
    return NextResponse.json(emptyLogicalSphereSummary);
  } catch {
    return NextResponse.json(emptyLogicalSphereSummary);
  }
}
