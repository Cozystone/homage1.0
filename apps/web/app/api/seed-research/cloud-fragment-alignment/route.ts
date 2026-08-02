import { NextResponse } from "next/server";
import { proxyJson } from "../../_backend";

const fallbackSummary = () => ({
  proof_exists: false,
  candidate_fragments_checked: 0,
  public_fragments_checked: 0,
  rejected_private_fragments: 0,
  fragments_aligned_to_seed: 0,
  concepts_aligned_total: 0,
  edges_aligned_total: 0,
  matched_fragment_ids: [],
  local_brain_state: {
    local_brain_initialized: false,
    local_total_nodes: 0,
    local_total_edges: 0,
  },
  external_llm_used: false,
  external_sllm_used: false,
  rule_based_answer_engine: false,
  final_answer_generation_claimed: false,
  claim: "Public Cloud candidate fragments can align to Seed Graph concepts and relations as retrieval/verification anchors.",
});

export async function GET() {
  try {
    const proxied = await proxyJson("/api/seed-research/cloud-fragment-alignment");
    if (proxied) return NextResponse.json(proxied.body, { status: proxied.status });
    return NextResponse.json(fallbackSummary());
  } catch {
    return NextResponse.json(fallbackSummary(), { status: 200 });
  }
}
