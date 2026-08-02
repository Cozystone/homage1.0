import { NextResponse } from "next/server";
import { proxyJson } from "../../_backend";

export async function GET() {
  try {
    const proxied = await proxyJson("/api/cloud-brain/source-inspector");
    if (proxied) return NextResponse.json(proxied.body, { status: proxied.status });
    return NextResponse.json(
      {
        active_source_mode: "local_broker_mode",
        honest_warning: "Cloud Brain source inspector is unavailable from this frontend context.",
        remote_cloudflare_broker: { configured: false, reachable: false },
      },
      { status: 503 },
    );
  } catch (error) {
    return NextResponse.json(
      {
        active_source_mode: "local_broker_mode",
        error: error instanceof Error ? error.message : "source inspector unavailable",
      },
      { status: 503 },
    );
  }
}
