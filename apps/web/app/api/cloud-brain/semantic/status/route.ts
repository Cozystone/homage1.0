import { NextResponse } from "next/server";
import { proxyJson } from "../../../_backend";

export async function GET() {
  const proxied = await proxyJson("/api/cloud-brain/semantic/status");
  return NextResponse.json(
    proxied?.body ?? { concepts: 0, relations: 0, evidence: 0, proof_store_only: true },
    { status: proxied?.status ?? 503 },
  );
}
