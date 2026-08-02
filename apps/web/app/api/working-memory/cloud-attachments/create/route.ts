import { NextRequest, NextResponse } from "next/server";
import { proxyJson } from "../../../_backend";

export async function POST(request: NextRequest) {
  const body = await request.text();
  const proxied = await proxyJson("/api/working-memory/cloud-attachments/create", {
    method: "POST",
    body,
    headers: { "Content-Type": "application/json" },
  });
  return NextResponse.json(proxied?.body ?? { state: "unavailable" }, { status: proxied?.status ?? 503 });
}
