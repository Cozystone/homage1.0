import { NextResponse } from "next/server";
import { proxyJson } from "../../_backend";

export async function GET() {
  const proxied = await proxyJson("/api/answer-quality/status");
  return NextResponse.json(
    proxied?.body ?? {
      state: "unavailable",
      label: "Answer Quality Lab",
      evaluation_mode: "deterministic_local_heuristic",
      external_llm_judge_used: false,
      external_llm_generation_used: false,
      feedback_auto_promoted: false,
    },
    { status: proxied?.status ?? 503 },
  );
}
