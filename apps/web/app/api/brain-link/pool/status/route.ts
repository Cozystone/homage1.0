import { NextResponse } from "next/server";
import { proxyJson } from "../../../_backend";

export async function GET() {
  const proxied = await proxyJson("/api/brain-link/pool/status");
  return NextResponse.json(
    proxied?.body ?? { peers: [], peer_count: 0, online_peers: 0, queue_remaining: 0, architecture: "p2p_shared_compute_pool" },
    { status: proxied?.status ?? 503 },
  );
}
