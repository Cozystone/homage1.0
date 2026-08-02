import { NextResponse } from "next/server";
import { proxyJson } from "../../_backend";

export async function POST(request: Request) {
  const body = await request.text();
  const proxied = await proxyJson("/api/answer-quality/run-repair-comparison", {
    method: "POST",
    headers: { "content-type": "application/json" },
    body,
  });
  return NextResponse.json(
    proxied?.body ?? {
      error: "answer_quality_repair_backend_unavailable",
      feedback_auto_promoted: false,
      external_llm_judge_used: false,
    },
    { status: proxied?.status ?? 503 },
  );
}
