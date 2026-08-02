import { NextResponse } from "next/server";
import { proxyJson } from "../../../_backend";

type RouteContext = {
  params: Promise<{ candidate_id: string }>;
};

export async function GET(_request: Request, context: RouteContext) {
  const { candidate_id } = await context.params;
  const proxied = await proxyJson(`/api/surface-brain/repair-candidates/${encodeURIComponent(candidate_id)}`);
  return NextResponse.json(proxied?.body ?? { error: "repair_candidate_backend_unavailable" }, { status: proxied?.status ?? 503 });
}
