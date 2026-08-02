import { NextRequest, NextResponse } from "next/server";
import { proxyJson } from "../../_backend";

type RouteContext = {
  params: Promise<{ path: string[] }>;
};

async function forward(request: NextRequest, context: RouteContext) {
  const params = await context.params;
  const suffix = (params.path ?? []).join("/");
  const search = request.nextUrl.search || "";
  const body = request.method === "GET" || request.method === "HEAD" ? undefined : await request.text();
  const proxied = await proxyJson(`/api/graph-hub/${suffix}${search}`, {
    method: request.method,
    headers: body ? { "content-type": request.headers.get("content-type") ?? "application/json" } : undefined,
    body,
  });
  return NextResponse.json(proxied?.body ?? { error: "local_backend_unavailable" }, { status: proxied?.status ?? 503 });
}

export async function GET(request: NextRequest, context: RouteContext) {
  return forward(request, context);
}

export async function POST(request: NextRequest, context: RouteContext) {
  return forward(request, context);
}
