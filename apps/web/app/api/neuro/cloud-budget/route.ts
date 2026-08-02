import { NextResponse } from "next/server";
import { proxyJson } from "../../_backend";

export async function GET() {
  try {
    const proxied = await proxyJson("/api/neuro/cloud-budget/free");
    if (proxied) return NextResponse.json(proxied.body, { status: proxied.status });
  } catch {
    // fall through to honest disconnected fallback
  }
  return NextResponse.json({
    plan: "free",
    cloud_budget: { plan: "free", monthly_price_usd: 0, cloud_budget_units: 1, contribution_required: false },
    brain_balance: { local: 1, cloud: 0, seed: 0, working_memory: 0 },
    provider_state: "unavailable",
  });
}

export async function POST(request: Request) {
  const body = await request.json().catch(() => ({}));
  try {
    const proxied = await proxyJson("/api/neuro/cloud-budget", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    if (proxied) return NextResponse.json(proxied.body, { status: proxied.status });
  } catch {
    // fall through to honest disconnected fallback
  }
  return NextResponse.json({
    plan: body?.plan ?? "free",
    cloud_budget: { plan: body?.plan ?? "free", monthly_price_usd: 0, cloud_budget_units: 0, contribution_required: true },
    brain_balance: { local: 1, cloud: 0, seed: 0, working_memory: 0 },
    provider_state: "unavailable",
  });
}
