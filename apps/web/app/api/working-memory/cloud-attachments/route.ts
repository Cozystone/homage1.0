import { NextResponse } from "next/server";
import { proxyJson } from "../../_backend";

export async function GET() {
  const proxied = await proxyJson("/api/working-memory/cloud-attachments");
  return NextResponse.json(proxied?.body ?? { bundles: [], active_bundle_ids: [] }, { status: proxied?.status ?? 503 });
}
