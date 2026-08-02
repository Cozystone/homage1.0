import { NextResponse } from "next/server";
import { proxyJson } from "../../../_backend";

export async function GET() {
  const proxied = await proxyJson("/api/brain/graph/status");
  return NextResponse.json(
    proxied?.body ?? {
      status: "unavailable",
      pipeline: "tab_aware_brain_graph_render_pipeline",
      surface_graph_full_render_disabled: true,
      cloud_attached_counts_as_local: false,
    },
    { status: proxied?.status ?? 503 },
  );
}
