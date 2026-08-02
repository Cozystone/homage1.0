import { NextResponse } from "next/server";
import { proxyJson } from "../../../../_backend";

type RouteContext = {
  params: Promise<{ rule_id: string }>;
};

export async function POST(_request: Request, context: RouteContext) {
  const { rule_id } = await context.params;
  const proxied = await proxyJson(`/api/surface-brain/production-rules/${encodeURIComponent(rule_id)}/enable`, { method: "POST" });
  return NextResponse.json(proxied?.body ?? { error: "production_rule_enable_backend_unavailable" }, { status: proxied?.status ?? 503 });
}
