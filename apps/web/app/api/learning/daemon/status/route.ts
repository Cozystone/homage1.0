import { NextResponse } from "next/server";
import { demoLearningDaemonStatus } from "../../../_alphaDemo";
import { proxyJson } from "../../../_backend";

export async function GET() {
  try {
    const proxied = await proxyJson("/api/learning/daemon/status");
    if (proxied) return NextResponse.json(proxied.body, { status: proxied.status });
    return NextResponse.json(demoLearningDaemonStatus());
  } catch {
    return NextResponse.json(demoLearningDaemonStatus());
  }
}
