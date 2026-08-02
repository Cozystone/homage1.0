import { NextResponse } from "next/server";
import { proxyJson } from "../../../_backend";

// Visual memory recall: measured color/composition signature -> particle-field
// parameters (Phase 4-2). learn=1 lets the page trigger a bounded on-miss learn.
export async function GET(
  req: Request,
  { params }: { params: Promise<{ concept: string }> },
) {
  const { concept } = await params;
  const url = new URL(req.url);
  const learn = url.searchParams.get("learn") === "1" ? "?learn=true" : "";
  const proxied = await proxyJson(
    `/api/base-brain/visual-memory/${encodeURIComponent(concept)}${learn}`,
  );
  return NextResponse.json(
    proxied?.body ?? { scene: null },
    { status: proxied?.status ?? 503 },
  );
}
