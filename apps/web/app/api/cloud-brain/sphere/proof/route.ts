import { NextResponse } from "next/server";
import { proxyJson } from "../../../_backend";

export async function POST() {
  const proxied = await proxyJson("/api/cloud-brain/sphere/proof", { method: "POST" });
  if (proxied) return NextResponse.json(proxied.body, { status: proxied.status });
  return NextResponse.json({ error: "Cloud Brain sphere proof backend unavailable" }, { status: 503 });
}
