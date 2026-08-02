import { NextResponse } from "next/server";
import { demoMemoryStatus } from "../../_alphaDemo";
import { proxyJson } from "../../_backend";

export async function POST() {
  try {
    const proxied = await proxyJson("/api/memory/build", { method: "POST" });
    if (proxied) return NextResponse.json(proxied.body, { status: proxied.status });
    return NextResponse.json(demoMemoryStatus());
  } catch {
    return NextResponse.json(demoMemoryStatus());
  }
}
