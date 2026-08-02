import { NextRequest, NextResponse } from "next/server";
import { proxyJson } from "../../../_backend";

export async function GET(request: NextRequest) {
  const proxied = await proxyJson(`/api/cloud-brain/semantic/graph${request.nextUrl.search}`);
  return NextResponse.json(
    proxied?.body ?? { nodes: [], edges: [], proof_store_only: true, old_mirror_snapshot_used: false },
    { status: proxied?.status ?? 503 },
  );
}
