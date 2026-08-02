import { NextResponse } from "next/server";
import { proxyJson } from "../../_backend";

export async function GET() {
  try {
    const proxied = await proxyJson("/api/cloud-brain/controlled-self-growth-proof");
    if (proxied) return NextResponse.json(proxied.body, { status: proxied.status });
    return NextResponse.json({
      proof_exists: false,
      controlled_self_growth: false,
      mode: "controlled_fixture_only",
      autonomous_broad_crawling: false,
      local_brain_state: {
        local_brain_initialized: false,
        local_total_nodes: 0,
        local_total_edges: 0,
      },
      external_llm_used: false,
      external_sllm_used: false,
      rule_based_answer_engine: false,
      final_answer_generation_claimed: false,
    });
  } catch {
    return NextResponse.json({ error: "Controlled self-growth proof unavailable" }, { status: 503 });
  }
}
