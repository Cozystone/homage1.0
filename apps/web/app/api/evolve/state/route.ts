import { NextResponse } from "next/server";
import { proxyJson } from "../../_backend";

// Chemotaxis evolution world: worms navigating a gradient to food, bred by
// selection. Observatory only — wired to no reasoning.
export async function GET() {
  const proxied = await proxyJson("/api/evolve/state");
  return NextResponse.json(
    proxied?.body ?? { population: 0, alive: 0, worms: [], food: [], world: { w: 120, h: 70 } },
    { status: proxied?.status ?? 503 },
  );
}
