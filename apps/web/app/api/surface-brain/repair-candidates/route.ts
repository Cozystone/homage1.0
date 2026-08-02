import { NextResponse } from "next/server";
import { proxyJson } from "../../_backend";

export async function GET(request: Request) {
  const url = new URL(request.url);
  const suffix = url.search || "";
  const proxied = await proxyJson(`/api/surface-brain/repair-candidates${suffix}`);
  return NextResponse.json(
    proxied?.body ?? { candidates: [], count: 0, review_required: true },
    { status: proxied?.status ?? 503 },
  );
}
