import { NextResponse } from "next/server";
import { proxyJson } from "../../_backend";

export async function POST() {
  try {
    const proxied = await proxyJson("/api/cloud-brain/prove-controlled-self-growth", { method: "POST" });
    if (proxied) return NextResponse.json(proxied.body, { status: proxied.status });
    return NextResponse.json({ error: "Local Cloud Brain proof backend unavailable" }, { status: 503 });
  } catch {
    return NextResponse.json({ error: "Controlled self-growth proof failed" }, { status: 503 });
  }
}
