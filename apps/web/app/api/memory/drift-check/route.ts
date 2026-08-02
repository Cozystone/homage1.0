import { NextResponse } from "next/server";
import { demoMemoryDriftCheck } from "../../_alphaDemo";
import { proxyJson } from "../../_backend";

export async function GET() {
  try {
    const proxied = await proxyJson("/api/memory/drift-check");
    if (proxied) return NextResponse.json(proxied.body, { status: proxied.status });
    return NextResponse.json(demoMemoryDriftCheck());
  } catch {
    return NextResponse.json(demoMemoryDriftCheck());
  }
}
