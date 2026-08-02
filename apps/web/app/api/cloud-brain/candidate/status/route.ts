import { NextResponse } from "next/server";
import { proxyJson } from "../../../_backend";

const emptyCandidateStatus = {
  candidate_status_endpoint: true,
  candidate_available: false,
  candidate_store_path: null,
  reason: "backend_unavailable_or_no_candidate_store",
  candidate_concepts: 0,
  candidate_relations: 0,
  candidate_evidence: 0,
  candidate_case_frames: 0,
  surface_candidates: 0,
  cgsr_frames: 0,
  rhfc_candidates: 0,
  production_store_mutated: false,
  candidate_is_verified: false,
  safe_for_review: false,
  local_brain_write: false,
  false_confident: 0,
  forgetting_count: 0,
  eval_rows_used_for_learning: false,
  external_llm_used: false,
  mock_growth: false,
  pair_edges_sent: 0,
  private_data_used_for_cloud_learning: false,
  unsupported_claims: 0,
};

export async function GET() {
  try {
    const proxied = await proxyJson("/api/cloud-brain/candidate/status");
    if (proxied) return NextResponse.json(proxied.body, { status: proxied.status });
    return NextResponse.json(emptyCandidateStatus);
  } catch {
    return NextResponse.json(emptyCandidateStatus);
  }
}
