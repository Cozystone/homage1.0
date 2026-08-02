import { NextResponse } from "next/server";
import { proxyJson } from "../../_backend";

type RouteContext = {
  params: Promise<{ path?: string[] }>;
};

async function proxyInnerVoice(request: Request, context: RouteContext) {
  const params = await context.params;
  const path = `/${(params.path ?? []).join("/")}`;
  const url = new URL(request.url);
  const body = request.method === "GET" || request.method === "HEAD" ? undefined : await request.text();
  try {
    const proxied = await proxyJson(`/api/inner-voice${path}${url.search}`, {
      method: request.method,
      headers: body ? { "Content-Type": request.headers.get("content-type") ?? "application/json" } : undefined,
      body,
    });
    if (proxied) return NextResponse.json(proxied.body, { status: proxied.status });
  } catch (error) {
    return NextResponse.json(
      {
        available: false,
        error: error instanceof Error ? error.message : "Inner Voice proxy failed",
      },
      { status: 502 },
    );
  }
  return NextResponse.json({ available: false, error: "Inner Voice proxy unavailable" }, { status: 502 });
}

export async function GET(request: Request, context: RouteContext) {
  return proxyInnerVoice(request, context);
}

export async function POST(request: Request, context: RouteContext) {
  return proxyInnerVoice(request, context);
}
