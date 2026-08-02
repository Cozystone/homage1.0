import { NextResponse } from "next/server";
import { demoCloudBrainPrune } from "../../_alphaDemo";
import { proxyJson } from "../../_backend";

export async function POST(request: Request) {
  const body = await request.text();
  let parsed = {};
  try {
    parsed = JSON.parse(body || "{}");
  } catch {
    // Use empty input.
  }
  try {
    const proxied = await proxyJson("/api/cloud-brain/prune", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body,
    });
    if (proxied) return NextResponse.json(proxied.body, { status: proxied.status });
    return NextResponse.json(demoCloudBrainPrune(parsed));
  } catch {
    return NextResponse.json(demoCloudBrainPrune(parsed));
  }
}
