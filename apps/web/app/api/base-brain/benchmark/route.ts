import { NextResponse } from "next/server";
import { proxyJson } from "../../_backend";

export async function POST(request: Request) {
  const body = await request.json().catch(() => ({}));
  const proxied = await proxyJson("/api/base-brain/benchmark", {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify(body),
  });
  return NextResponse.json(proxied?.body ?? { total_prompts: 0, results: [] }, { status: proxied?.status ?? 503 });
}
