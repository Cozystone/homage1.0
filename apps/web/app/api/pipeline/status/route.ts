import { NextResponse } from "next/server";
import { demoPipelineStatus } from "../../_alphaDemo";
import { proxyJson } from "../../_backend";

export async function GET() {
  try {
    const proxied = await proxyJson("/api/pipeline/status");
    if (proxied) {
      return NextResponse.json(proxied.body, { status: proxied.status });
    }
    return NextResponse.json(demoPipelineStatus());
  } catch (error) {
    return NextResponse.json(demoPipelineStatus());
  }
}
