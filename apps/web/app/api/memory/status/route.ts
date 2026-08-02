import { NextResponse } from "next/server";
import { demoMemoryStatus } from "../../_alphaDemo";
import { proxyJson } from "../../_backend";

export async function GET() {
  try {
    const proxied = await proxyJson("/api/memory/status");
    if (proxied) return NextResponse.json(proxied.body, { status: proxied.status });
    return NextResponse.json(demoMemoryStatus());
  } catch {
    return NextResponse.json(demoMemoryStatus());
  }
}
