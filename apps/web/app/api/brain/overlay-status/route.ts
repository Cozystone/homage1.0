import { NextResponse } from "next/server";
import { proxyJson } from "../../_backend";

export async function GET() {
  const proxied = await proxyJson("/api/brain/overlay-status");
  return NextResponse.json(
    proxied?.body ?? {
      working_memory_active: false,
      local_active_nodes: 0,
      cloud_attached_nodes: 0,
      seed_anchor_nodes: 0,
      local_brain_write: false,
      cloud_attached_counts_as_local: false,
    },
    { status: proxied?.status ?? 503 },
  );
}
