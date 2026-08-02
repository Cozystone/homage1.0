import { NextResponse } from "next/server";
import { proxyJson } from "../../../_backend";

const emptySurfaceGraph = {
  nodes: [],
  edges: [],
  metadata: {
    surface_graph_available: false,
    graph_pending_reason: "backend_unavailable_or_no_candidate_store",
    materialized_surface_nodes: 0,
    materialized_surface_edges: 0,
    total_constructions: 0,
  },
};

export async function GET(request: Request) {
  const { searchParams } = new URL(request.url);
  const max_nodes = searchParams.get("max_nodes") ?? "400";
  const max_edges = searchParams.get("max_edges") ?? "700";
  try {
    const proxied = await proxyJson(
      `/api/cloud-brain/surface-graph/graph?max_nodes=${encodeURIComponent(max_nodes)}&max_edges=${encodeURIComponent(max_edges)}`,
    );
    if (proxied) return NextResponse.json(proxied.body, { status: proxied.status });
    return NextResponse.json(emptySurfaceGraph);
  } catch {
    return NextResponse.json(emptySurfaceGraph);
  }
}
