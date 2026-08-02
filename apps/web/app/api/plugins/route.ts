import { NextResponse } from "next/server";
import { proxyJson } from "../_backend";
import { fallbackList } from "./_catalog";

// GET /api/plugins — live list from the engine, or a static catalogue fallback
// so the Plugin Kit UI always renders (even while :8502 is restarting).
export async function GET() {
  try {
    const proxied = await proxyJson("/api/plugins");
    if (proxied && proxied.status < 400) {
      return NextResponse.json(proxied.body, { status: proxied.status });
    }
  } catch {
    /* fall through to static catalogue */
  }
  return NextResponse.json(fallbackList());
}
