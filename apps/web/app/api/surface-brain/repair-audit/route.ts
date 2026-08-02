import { NextResponse } from "next/server";
import { proxyJson } from "../../_backend";

export async function GET(request: Request) {
  const url = new URL(request.url);
  const proxied = await proxyJson(`/api/surface-brain/repair-audit${url.search || ""}`);
  return NextResponse.json(proxied?.body ?? { events: [], count: 0 }, { status: proxied?.status ?? 503 });
}
