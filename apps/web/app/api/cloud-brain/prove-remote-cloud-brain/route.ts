import { NextResponse } from "next/server";
import { proxyJson } from "../../_backend";

export async function POST() {
  try {
    const proxied = await proxyJson("/api/cloud-brain/prove-remote-cloud-brain", { method: "POST" });
    if (proxied) return NextResponse.json(proxied.body, { status: proxied.status });
    return NextResponse.json(
      {
        active_source_mode: "local_broker_mode",
        remote_proof: {
          result: "FAIL",
          failures: ["local FastAPI proof endpoint is unavailable"],
        },
      },
      { status: 503 },
    );
  } catch (error) {
    return NextResponse.json(
      {
        remote_proof: {
          result: "FAIL",
          failures: [error instanceof Error ? error.message : "remote proof unavailable"],
        },
      },
      { status: 503 },
    );
  }
}
