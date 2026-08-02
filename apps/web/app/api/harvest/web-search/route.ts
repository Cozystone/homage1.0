import { NextResponse } from "next/server";
import { proxyJson } from "../../_backend";
import { defaultWebSearchQuery, searchWeb, webSearchProviderStatus } from "../../_webSearch";

export async function GET(request: Request) {
  const url = new URL(request.url);
  const provider = url.searchParams.get("provider");
  return NextResponse.json(webSearchProviderStatus(provider));
}

export async function POST(request: Request) {
  const body = await request.text();
  try {
    const proxied = await proxyJson("/api/harvest/web-search", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body,
    });
    if (proxied?.body?.results) return NextResponse.json(proxied.body, { status: proxied.status });
  } catch {
    // Fall through to deployable local provider.
  }

  let query = defaultWebSearchQuery;
  let count = 5;
  let provider: string | null = null;
  try {
    const parsed = JSON.parse(body || "{}");
    query = parsed.query ?? query;
    count = parsed.count ?? count;
    provider = parsed.provider ?? null;
  } catch {
    // Use defaults.
  }
  return NextResponse.json(await searchWeb(query, count, provider));
}
