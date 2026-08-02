import { NextRequest, NextResponse } from "next/server";

import { proxyJson } from "../../_backend";

type RouteContext = {
  params: Promise<{ path?: string[] }>;
};

async function proxyAgentic(request: NextRequest, context: RouteContext) {
  const params = await context.params;
  const suffix = (params.path ?? []).map(encodeURIComponent).join("/");
  const search = request.nextUrl.search || "";
  const targetPath = `/api/agentic-os/${suffix}${search}`;
  const body = request.method === "GET" || request.method === "HEAD" ? undefined : await request.text();
  const proxied = await proxyJson(targetPath, {
    method: request.method,
    headers: {
      "content-type": request.headers.get("content-type") ?? "application/json",
    },
    body,
  });
  if (!proxied) {
    return NextResponse.json({ available: false, reason: "agentic_os_backend_unavailable" }, { status: 502 });
  }
  return NextResponse.json(proxied.body, { status: proxied.status });
}

export async function GET(request: NextRequest, context: RouteContext) {
  return proxyAgentic(request, context);
}

export async function POST(request: NextRequest, context: RouteContext) {
  return proxyAgentic(request, context);
}
