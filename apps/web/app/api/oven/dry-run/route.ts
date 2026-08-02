import { NextResponse } from "next/server";
import { demoState } from "../../_alphaDemo";
import { proxyJson } from "../../_backend";

export async function POST() {
  try {
    const proxied = await proxyJson("/api/oven/dry-run", { method: "POST" });
    if (proxied) return NextResponse.json(proxied.body, { status: proxied.status });
    return NextResponse.json({ ...demoState.oven, started_at: new Date().toISOString(), finished_at: new Date().toISOString() });
  } catch {
    return NextResponse.json({ ...demoState.oven, started_at: new Date().toISOString(), finished_at: new Date().toISOString() });
  }
}
