import { NextResponse } from "next/server";
import { proxyJson } from "../../_backend";

export async function POST(request: Request) {
  const body = await request.text();
  const proxied = await proxyJson("/api/answer-quality/run", {
    method: "POST",
    headers: { "content-type": "application/json" },
    body,
  });
  return NextResponse.json(
    proxied?.body ?? {
      error: "answer_quality_backend_unavailable",
      evaluation_mode: "deterministic_local_heuristic",
      external_llm_judge_used: false,
      feedback_auto_promoted: false,
    },
    { status: proxied?.status ?? 503 },
  );
}
