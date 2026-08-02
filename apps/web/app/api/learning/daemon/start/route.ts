import { NextResponse } from "next/server";
import { demoLearningDaemonStart } from "../../../_alphaDemo";
import { proxyJson } from "../../../_backend";

export async function POST(request: Request) {
  const body = await request.json().catch(() => ({ interval_seconds: 30, resume: true }));
  try {
    const proxied = await proxyJson("/api/learning/daemon/start", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    if (proxied) return NextResponse.json(proxied.body, { status: proxied.status });
    return NextResponse.json(demoLearningDaemonStart());
  } catch {
    return NextResponse.json(demoLearningDaemonStart());
  }
}
