import { NextResponse } from "next/server";
import { proxyJson } from "../../_backend";

// Catch-all passthrough for /api/plugins/<...> (enable, permissions/<cap>, run,
// runs). Plugin ids contain "@" and caps contain ":" — both are valid single
// path segments, reconstructed verbatim for the engine.
function backendPath(parts: string[]): string {
  return "/api/plugins/" + parts.map((p) => encodeURIComponent(p)).join("/");
}

export async function GET(_req: Request, ctx: { params: Promise<{ path: string[] }> }) {
  const { path } = await ctx.params;
  try {
    const proxied = await proxyJson(backendPath(path));
    if (proxied) return NextResponse.json(proxied.body, { status: proxied.status });
  } catch {
    /* fall through */
  }
  return NextResponse.json({ error: "engine_unavailable", detail: "엔진(:8502)에 연결할 수 없습니다." }, { status: 503 });
}

export async function POST(req: Request, ctx: { params: Promise<{ path: string[] }> }) {
  const { path } = await ctx.params;
  const body = await req.json().catch(() => ({}));
  try {
    const proxied = await proxyJson(backendPath(path), {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    if (proxied) return NextResponse.json(proxied.body, { status: proxied.status });
  } catch {
    /* fall through */
  }
  return NextResponse.json(
    { error: "engine_unavailable", detail: "엔진(:8502)이 실행 중이어야 수집/권한 변경이 적용됩니다." },
    { status: 503 },
  );
}
