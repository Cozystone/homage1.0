import { NextResponse } from "next/server";
import { proxyJson } from "../../_backend";

export async function GET() {
  const proxied = await proxyJson("/api/base-brain/proof");
  return NextResponse.json(proxied?.body ?? { status: "BLOCKED" }, { status: proxied?.status ?? 503 });
}
