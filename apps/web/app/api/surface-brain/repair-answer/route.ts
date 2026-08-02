import { NextResponse } from "next/server";
import { proxyJson } from "../../_backend";

export async function POST(request: Request) {
  const body = await request.text();
  const proxied = await proxyJson("/api/surface-brain/repair-answer", {
    method: "POST",
    headers: { "content-type": "application/json" },
    body,
  });
  return NextResponse.json(
    proxied?.body ?? { error: "surface_repair_backend_unavailable" },
    { status: proxied?.status ?? 503 },
  );
}
