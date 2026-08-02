import { NextResponse } from "next/server";
import { proxyJson } from "../../../_backend";

export async function POST() {
  const proxied = await proxyJson("/api/cloud-brain/semantic/proof", { method: "POST" });
  return NextResponse.json(proxied?.body ?? { passed: false, error: "local_backend_unavailable" }, { status: proxied?.status ?? 503 });
}
