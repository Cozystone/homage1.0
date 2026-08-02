import { NextResponse } from "next/server";
import { demoCloudBrainConsolidate } from "../../_alphaDemo";
import { proxyJson } from "../../_backend";

export async function POST(request: Request) {
  const body = await request.text();
  try {
    const proxied = await proxyJson("/api/cloud-brain/consolidate", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body,
    });
    if (proxied) return NextResponse.json(proxied.body, { status: proxied.status });
    return NextResponse.json(demoCloudBrainConsolidate());
  } catch {
    return NextResponse.json(demoCloudBrainConsolidate());
  }
}
