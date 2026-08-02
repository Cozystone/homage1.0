import { NextResponse } from "next/server";
import { proxyJson } from "../../_backend";

export async function GET(request: Request) {
  const url = new URL(request.url);
  const proxied = await proxyJson(`/api/answer-quality/repair-comparisons${url.search}`);
  return NextResponse.json(
    proxied?.body ?? {
      repair_comparisons: [],
      count: 0,
      feedback_auto_promoted: false,
      external_llm_judge_used: false,
    },
    { status: proxied?.status ?? 503 },
  );
}
