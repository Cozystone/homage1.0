import { NextResponse } from "next/server";
import { proxyJson } from "../../../../_backend";

type RouteContext = {
  params: Promise<{ candidate_id: string }>;
};

export async function POST(request: Request, context: RouteContext) {
  const { candidate_id } = await context.params;
  const body = await request.text();
  const proxied = await proxyJson(`/api/surface-brain/repair-candidates/${encodeURIComponent(candidate_id)}/approve`, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body,
  });
  return NextResponse.json(proxied?.body ?? { error: "repair_candidate_approve_backend_unavailable" }, { status: proxied?.status ?? 503 });
}
