import { NextRequest, NextResponse } from "next/server";
import { proxyJson } from "../../_backend";

export async function POST(request: NextRequest) {
  const body = await request.text();
  const proxied = await proxyJson("/api/working-memory/local-cloud-exchange", {
    method: "POST",
    body,
    headers: { "Content-Type": "application/json" },
  });

  if (proxied) {
    return NextResponse.json(proxied.body, { status: proxied.status });
  }

  return NextResponse.json(
    {
      status: "backend_unavailable",
      answer: "Cloud Brain query backend is unavailable. No evidence was fabricated.",
      cloud_chunks: [],
      evidence_bundles: [],
      candidate_fragments: [],
      attached_nodes: 0,
      attached_relations: 0,
      local_write: false,
      temporary: true,
      pair_edges_sent: 0,
    },
    { status: 503 },
  );
}
