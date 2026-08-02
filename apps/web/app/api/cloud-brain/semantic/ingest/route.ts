import { NextRequest, NextResponse } from "next/server";
import { proxyJson } from "../../../_backend";

export async function POST(request: NextRequest) {
  const body = await request.text();
  const proxied = await proxyJson("/api/cloud-brain/semantic/ingest", {
    method: "POST",
    body,
  });
  return NextResponse.json(proxied?.body ?? { error: "local_backend_unavailable" }, { status: proxied?.status ?? 503 });
}
