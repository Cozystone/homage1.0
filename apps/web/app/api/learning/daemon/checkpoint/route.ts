import { NextResponse } from "next/server";
import { demoLearningDaemonCheckpoint } from "../../../_alphaDemo";
import { proxyJson } from "../../../_backend";

export async function POST(request: Request) {
  const body = await request.json().catch(() => ({ reason: "manual" }));
  try {
    const proxied = await proxyJson("/api/learning/daemon/checkpoint", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    if (proxied) return NextResponse.json(proxied.body, { status: proxied.status });
    return NextResponse.json(demoLearningDaemonCheckpoint());
  } catch {
    return NextResponse.json(demoLearningDaemonCheckpoint());
  }
}
