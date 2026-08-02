import { NextResponse } from "next/server";
import { demoCloudBrainStatus } from "../../_alphaDemo";
import { proxyJson } from "../../_backend";

export async function GET() {
  try {
    const proxied = await proxyJson("/api/cloud-brain/status");
    if (proxied) return NextResponse.json(proxied.body, { status: proxied.status });
    return NextResponse.json(demoCloudBrainStatus());
  } catch {
    return NextResponse.json(demoCloudBrainStatus());
  }
}
