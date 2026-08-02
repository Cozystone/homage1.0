import { NextResponse } from "next/server";
import { proxyJson } from "../../_backend";

export async function GET(request: Request) {
  const url = new URL(request.url);
  const query = url.search ? url.search : "";
  const proxied = await proxyJson(`/api/answer-quality/runs${query}`);
  return NextResponse.json(
    proxied?.body ?? {
      runs: [],
      count: 0,
      evaluation_mode: "deterministic_local_heuristic",
      external_llm_judge_used: false,
      feedback_auto_promoted: false,
    },
    { status: proxied?.status ?? 503 },
  );
}
