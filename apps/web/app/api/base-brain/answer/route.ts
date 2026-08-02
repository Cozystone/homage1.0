import { NextResponse } from "next/server";
import { proxyJson } from "../../_backend";

export async function POST(request: Request) {
  const body = await request.json().catch(() => ({}));
  const proxied = await proxyJson("/api/base-brain/answer", {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify(body),
  });
  return NextResponse.json(
    proxied?.body ?? {
      answer: "Base Brain is unavailable.",
      external_llm_used: false,
      external_sllm_used: false,
      external_web_used: false,
    },
    { status: proxied?.status ?? 503 },
  );
}
