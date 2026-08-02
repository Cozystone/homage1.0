import { NextResponse } from "next/server";
import { proxyJson } from "../../../_backend";

export async function POST() {
  const proxied = await proxyJson("/api/brain/graph/proof", { method: "POST" });
  return NextResponse.json(
    proxied?.body ?? { passed: false, reason: "local_backend_unavailable" },
    { status: proxied?.status ?? 503 },
  );
}
