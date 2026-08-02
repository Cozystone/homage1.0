import { NextResponse } from "next/server";
import { proxyJson } from "../../../_backend";

export async function POST() {
  const proxied = await proxyJson("/api/working-memory/cloud-attachments/clear", { method: "POST" });
  return NextResponse.json(proxied?.body ?? { state: "unavailable" }, { status: proxied?.status ?? 503 });
}
