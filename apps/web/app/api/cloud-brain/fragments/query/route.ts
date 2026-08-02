import { NextRequest, NextResponse } from "next/server";
import { proxyJson } from "../../../_backend";

export async function GET(request: NextRequest) {
  const params = request.nextUrl.searchParams.toString();
  try {
    const proxied = await proxyJson(`/api/cloud-brain/fragments/query${params ? `?${params}` : ""}`);
    if (proxied) return NextResponse.json(proxied.body, { status: proxied.status });
    return NextResponse.json({
      query: request.nextUrl.searchParams.get("q") ?? "",
      results: [],
      external_llm_used: false,
      external_sllm_used: false,
      final_answer_generation_claimed: false,
    });
  } catch {
    return NextResponse.json({ error: "Cloud Brain fragment query unavailable" }, { status: 503 });
  }
}
