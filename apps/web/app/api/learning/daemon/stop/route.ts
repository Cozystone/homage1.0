import { NextResponse } from "next/server";
import { demoLearningDaemonStop } from "../../../_alphaDemo";
import { proxyJson } from "../../../_backend";

export async function POST(request: Request) {
  const body = await request.json().catch(() => ({ reason: "manual" }));
  try {
    const proxied = await proxyJson("/api/learning/daemon/stop", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    if (proxied) return NextResponse.json(proxied.body, { status: proxied.status });
    return NextResponse.json(demoLearningDaemonStop());
  } catch {
    return NextResponse.json(demoLearningDaemonStop());
  }
}
