import { NextResponse } from "next/server";
import { proxyJson } from "../../_backend";

export async function GET() {
  try {
    const proxied = await proxyJson("/api/neuro/cost-scenarios");
    if (proxied) return NextResponse.json(proxied.body, { status: proxied.status });
  } catch {
    // fall through to explicit unavailable state
  }
  return NextResponse.json({
    scenarios: {},
    base_unit_economics: {},
    provider_state: "unavailable",
    note: "Backend cost scenarios unavailable.",
  });
}
