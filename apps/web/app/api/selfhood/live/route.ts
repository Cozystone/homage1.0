import { NextResponse } from "next/server";
import { proxyJson } from "../../_backend";

// The continuously-alive self runs on the LOCAL companion (:8502), not the cloud.
export const dynamic = "force-dynamic";

export async function GET() {
  try {
    const proxied = await proxyJson("/api/selfhood/live");
    if (proxied) return NextResponse.json(proxied.body, { status: proxied.status });
  } catch {
    /* fall through */
  }
  return NextResponse.json({ continuous: false, offline: true });
}
