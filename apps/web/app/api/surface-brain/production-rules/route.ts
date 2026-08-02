import { NextResponse } from "next/server";
import { proxyJson } from "../../_backend";

export async function GET() {
  const proxied = await proxyJson("/api/surface-brain/production-rules");
  return NextResponse.json(proxied?.body ?? { production_rules: [], count: 0 }, { status: proxied?.status ?? 503 });
}
