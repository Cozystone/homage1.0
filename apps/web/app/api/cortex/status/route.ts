import { NextResponse } from "next/server";
import { proxyJson } from "../../_backend";

export async function GET() {
  const proxied = await proxyJson("/api/cortex/status");
  return NextResponse.json(
    proxied?.body ?? {
      state: "unavailable",
      architecture: "CORTEX-G2",
      external_llm_used: false,
      external_sllm_used: false,
      local_brain_write: false,
      final_answer_generation_claimed: false,
    },
    { status: proxied?.status ?? 503 },
  );
}
