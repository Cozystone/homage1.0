import { NextRequest, NextResponse } from "next/server";
import { backendBaseUrl } from "../../_backend";

export async function GET(request: NextRequest) {
  const search = request.nextUrl.search || "";
  const baseUrl = backendBaseUrl();
  if (!baseUrl) {
    return NextResponse.json(
      {
        view: request.nextUrl.searchParams.get("view") ?? "local",
        nodes: [],
        edges: [],
        layers_missing: [{ layer: "brain_graph", reason: "local_backend_unavailable" }],
        honesty: { missing_layers_are_reported: true },
      },
      { status: 503 },
    );
  }

  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), 8000);
  let response: Response;
  try {
    response = await fetch(`${baseUrl}/api/brain/graph${search}`, {
      cache: "no-store",
      signal: controller.signal,
    });
  } catch (error) {
    return NextResponse.json(
      {
        view: request.nextUrl.searchParams.get("view") ?? "local",
        nodes: [],
        edges: [],
        layers_missing: [{ layer: "brain_graph", reason: "backend_graph_timeout" }],
        error: error instanceof Error ? error.message : "backend graph request failed",
        honesty: { missing_layers_are_reported: true },
      },
      { status: 504 },
    );
  } finally {
    clearTimeout(timeout);
  }
  if (response.status === 404 || response.status === 405) {
    return NextResponse.json(
      {
        view: request.nextUrl.searchParams.get("view") ?? "local",
        nodes: [],
        edges: [],
        layers_missing: [{ layer: "brain_graph", reason: "local_backend_unavailable" }],
        honesty: { missing_layers_are_reported: true },
      },
      { status: 503 },
    );
  }
  return new Response(response.body, {
    status: response.status,
    headers: {
      "content-type": response.headers.get("content-type") ?? "application/json",
      "cache-control": "no-store",
    },
  });
}
