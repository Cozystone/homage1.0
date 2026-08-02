import { NextRequest, NextResponse } from "next/server";
import { proxyJson } from "../../../_backend";

export async function GET(request: NextRequest) {
  const params = request.nextUrl.searchParams.toString();
  const proxied = await proxyJson(`/api/cloud-brain/sphere/materialize${params ? `?${params}` : ""}`);
  if (proxied) return NextResponse.json(proxied.body, { status: proxied.status });
  return NextResponse.json({ error: "Cloud Brain sphere materialization backend unavailable" }, { status: 503 });
}
