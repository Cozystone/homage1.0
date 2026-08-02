import { NextResponse } from "next/server";
import { proxyJson } from "../../../_backend";

export async function POST() {
  try {
    const proxied = await proxyJson("/api/seed-research/cloud-fragment-alignment/run", { method: "POST" });
    if (proxied) return NextResponse.json(proxied.body, { status: proxied.status });
    return NextResponse.json({ error: "Local seed alignment backend unavailable" }, { status: 503 });
  } catch {
    return NextResponse.json({ error: "Cloud Fragment to Seed alignment proof failed" }, { status: 503 });
  }
}
