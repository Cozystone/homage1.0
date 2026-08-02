import { NextResponse } from "next/server";
import { proxyJson } from "../../_backend";

export async function POST(request: Request) {
  const body = await request.json().catch(() => ({}));
  try {
    const proxied = await proxyJson("/api/neuro/cost-estimate", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    if (proxied) return NextResponse.json(proxied.body, { status: proxied.status });
  } catch {
    // fall through to local-only fallback
  }
  return NextResponse.json({
    provider: body?.provider ?? "cloudflare",
    estimated_monthly_cost_usd: 0,
    provider_state: "unavailable",
    note: "Backend cost estimator unavailable.",
  });
}
