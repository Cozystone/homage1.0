import { NextResponse } from "next/server";
import { proxyJson } from "../../_backend";

// Living worm culture: the LIF colony's current viz snapshot (generations,
// worms, neuron voltages). Observatory only — wired to no reasoning.
export async function GET() {
  const proxied = await proxyJson("/api/culture/state");
  return NextResponse.json(
    proxied?.body ?? { population: 0, alive: 0, worms: [] },
    { status: proxied?.status ?? 503 },
  );
}
