import { NextResponse } from "next/server";
import { proxyJson } from "../../_backend";

export async function GET() {
  const proxied = await proxyJson("/api/base-brain/status");
  return NextResponse.json(
    proxied?.body ?? {
      state: "unavailable",
      pack_exists: false,
      zero_user_data: true,
      external_llm_used: false,
      external_sllm_used: false,
      external_web_used: false,
    },
    { status: proxied?.status ?? 503 },
  );
}
