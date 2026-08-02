import { NextResponse } from "next/server";
import { proxyJson } from "../../../_backend";

export async function GET() {
  const proxied = await proxyJson("/api/brain-link/pool/graph");
  return NextResponse.json(
    proxied?.body ?? { nodes: [], edges: [], peer_count: 0, architecture: "p2p_shared_compute_pool" },
    { status: proxied?.status ?? 503 },
  );
}
