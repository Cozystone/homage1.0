import { NextResponse } from "next/server";
import { proxyJson } from "../../../_backend";

export async function GET() {
  const proxied = await proxyJson("/api/cloud-brain/sphere/manifest");
  if (proxied) return NextResponse.json(proxied.body, { status: proxied.status });
  return NextResponse.json({
    scale_mode: "spherical_chunk_materialization",
    logical_total_nodes: "0",
    logical_total_edges: "0",
    max_logical_nodes: "9999999999999999",
    trillion_target: "1000000000000",
    actual_materialized_nodes: 0,
    rendered_nodes: 0,
    compression_used: false,
    semantic_aggregate_nodes_used: false,
    claim: "Every logical node remains individually addressable. The renderer materializes only visible spherical chunks.",
  });
}
