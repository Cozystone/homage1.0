import { NextResponse } from "next/server";
import { proxyJson } from "../../_backend";

export async function POST(request: Request) {
  const body = await request.text();
  const proxied = await proxyJson("/api/surface-brain/feedback-to-repair-candidates", {
    method: "POST",
    headers: { "content-type": "application/json" },
    body,
  });
  return NextResponse.json(
    proxied?.body ?? {
      candidates: [],
      auto_promoted: false,
      review_required: true,
      error: "surface_feedback_adapter_backend_unavailable",
    },
    { status: proxied?.status ?? 503 },
  );
}
