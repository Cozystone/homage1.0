import { NextRequest, NextResponse } from "next/server";
import { proxyJson } from "../../_backend";
import { bundledRuntimeTrace } from "../_seedFallback";

const fallbackTrace = (query: string) => ({
  query,
  local_graph_state: {
    local_brain_initialized: false,
    local_total_nodes: 0,
    local_total_edges: 0,
    local_evidence_sufficient: false,
    seed_written_to_local_brain: false,
    seed_counted_as_learned_memory: false,
  },
  seed_anchor_trace: {
    seed_anchor_ready: false,
    seed_used: false,
    matched_seed_concepts: [],
    matched_seed_edges: [],
    anchor_role: "backend_unavailable",
    final_answer_generation_claimed: false,
    external_llm_used: false,
    external_sllm_used: false,
    rule_based_answer_engine: false,
  },
  cloud_alignment_trace: {
    cloud_checked: false,
    candidate_fragments_checked: 0,
    fragments_aligned_to_seed: 0,
    alignment_ready: false,
    aligned_fragment_ids: [],
  },
  runtime_claim: "Seed runtime anchor trace is unavailable until the local backend responds.",
});

export async function GET(request: NextRequest) {
  const query = request.nextUrl.searchParams.get("q") ?? "Evidence Claim";
  try {
    const proxied = await proxyJson(`/api/seed-research/runtime-trace?q=${encodeURIComponent(query)}`);
    if (proxied) return NextResponse.json(proxied.body, { status: proxied.status });
    const bundled = await bundledRuntimeTrace(query);
    if (bundled.seed_anchor_trace.seed_anchor_ready) return NextResponse.json(bundled);
    return NextResponse.json(fallbackTrace(query));
  } catch {
    const bundled = await bundledRuntimeTrace(query);
    if (bundled.seed_anchor_trace.seed_anchor_ready) return NextResponse.json(bundled);
    return NextResponse.json(fallbackTrace(query), { status: 200 });
  }
}

export async function POST(request: NextRequest) {
  const body = await request.json().catch(() => ({}));
  const query = typeof body.query === "string" && body.query.trim() ? body.query.trim() : "Evidence Claim";
  try {
    const proxied = await proxyJson("/api/seed-research/runtime-trace", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ query }),
    });
    if (proxied) return NextResponse.json(proxied.body, { status: proxied.status });
    const bundled = await bundledRuntimeTrace(query);
    if (bundled.seed_anchor_trace.seed_anchor_ready) return NextResponse.json(bundled);
    return NextResponse.json(fallbackTrace(query));
  } catch {
    const bundled = await bundledRuntimeTrace(query);
    if (bundled.seed_anchor_trace.seed_anchor_ready) return NextResponse.json(bundled);
    return NextResponse.json(fallbackTrace(query), { status: 200 });
  }
}
