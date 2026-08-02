import { NextResponse } from "next/server";
import { demoDataGateRun } from "../../_alphaDemo";
import { proxyJson } from "../../_backend";

export async function POST(request: Request) {
  try {
    const body = await request.text();
    const proxied = await proxyJson("/api/datagate/run", {
      method: "POST",
      headers: body ? { "Content-Type": "application/json" } : undefined,
      body: body || undefined,
    });
    if (proxied) {
      return NextResponse.json(proxied.body, { status: proxied.status });
    }
    return NextResponse.json(demoDataGateRun(), { status: 202 });
  } catch (error) {
    return NextResponse.json(demoDataGateRun(), { status: 202 });
  }
}
