import { NextResponse } from "next/server";
import { proxyJson } from "../../_backend";

// Phase-interference scene: REAL trained concepts + resonance pairs from the
// engine's phase space. Empty fallback keeps the /interference page honest
// (it labels demo data as demo data).
export async function GET() {
  const proxied = await proxyJson("/api/base-brain/interference-scene");
  return NextResponse.json(
    proxied?.body ?? { nodes: [], links: [], prunes: [] },
    { status: proxied?.status ?? 503 },
  );
}
