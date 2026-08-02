import { NextResponse } from "next/server";
import { proxyJson } from "../../_backend";

async function forward(request: Request, context: { params: Promise<{ path?: string[] }> }) {
  const params = await context.params;
  const suffix = (params.path ?? []).map(encodeURIComponent).join("/");
  const url = new URL(request.url);
  const targetPath = `/api/construction-bank/${suffix}${url.search}`;
  const body = request.method === "GET" ? undefined : await request.text();
  const proxied = await proxyJson(targetPath, {
    method: request.method,
    headers: { "content-type": request.headers.get("content-type") ?? "application/json" },
    body,
  });
  if (proxied) return NextResponse.json(proxied.body, { status: proxied.status });
  return NextResponse.json({ error: "construction bank backend unavailable" }, { status: 502 });
}

export async function GET(request: Request, context: { params: Promise<{ path?: string[] }> }) {
  return forward(request, context);
}

export async function POST(request: Request, context: { params: Promise<{ path?: string[] }> }) {
  return forward(request, context);
}
