import { NextRequest, NextResponse } from "next/server";
import { backendBaseUrl } from "../../_backend";

const LOCAL_GRAPH_HOSTS = new Set(["127.0.0.1", "localhost", "::1", "[::1]"]);

function backendFromRequest(request: NextRequest) {
  const requested = request.nextUrl.searchParams.get("backend") ?? request.nextUrl.searchParams.get("api");
  if (!requested) return backendBaseUrl();
  try {
    const url = new URL(requested);
    if (!["http:", "https:"].includes(url.protocol)) return backendBaseUrl();
    if (!LOCAL_GRAPH_HOSTS.has(url.hostname)) return backendBaseUrl();
    return url.origin;
  } catch {
    return backendBaseUrl();
  }
}

export async function GET(request: NextRequest) {
  const backend = backendFromRequest(request);
  if (!backend) {
    return NextResponse.json({ state: "viewer_only", nodes: [], edges: [] });
  }
  const limit = request.nextUrl.searchParams.get("limit") ?? "5000";
  const includeCloudAttached = request.nextUrl.searchParams.get("include_cloud_attached") ?? "false";
  let response: Response;
  try {
    response = await fetch(`${backend}/api/graph/subgraph?limit=${encodeURIComponent(limit)}&include_cloud_attached=${encodeURIComponent(includeCloudAttached)}`, {
      cache: "no-store",
    });
  } catch {
    // Backend unreachable (e.g. engine restarting). Return an empty graph instead of
    // letting `fetch failed` reject unhandled — an escaped rejection crashes `next dev`.
    return NextResponse.json({ state: "engine_unreachable", nodes: [], edges: [] });
  }
  if (!response.ok) {
    return NextResponse.json(
      { state: "graph_proxy_failed", status: response.status, nodes: [], edges: [] },
      { status: response.status },
    );
  }
  return NextResponse.json(await response.json());
}
