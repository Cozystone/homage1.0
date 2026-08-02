import { NextRequest, NextResponse } from "next/server";
import { proxyJson } from "../../../_backend";

const LOCAL_EDGE_HOSTS = new Set(["127.0.0.1", "localhost", "::1", "[::1]"]);

function fallbackEdgeStatus() {
  return {
    state: "viewer_only",
    architecture: "edge_compute_broker",
    cloud_required: false,
    capacity: {
      peer_id: "deployment-viewer",
      tier: "viewer",
      idle: false,
      endpoint: null,
      task_types: ["status_view"],
      max_batch_nodes: 0,
      max_batch_edges: 0,
      heartbeat_ttl_seconds: 0,
      generated_at: Math.floor(Date.now() / 1000),
    },
  };
}

function localBackendBase(request: NextRequest) {
  const requested = request.nextUrl.searchParams.get("backend") ?? request.nextUrl.searchParams.get("api");
  if (!requested) return null;
  try {
    const url = new URL(requested);
    if (!["http:", "https:"].includes(url.protocol)) return null;
    if (!LOCAL_EDGE_HOSTS.has(url.hostname)) return null;
    return url.origin;
  } catch {
    return null;
  }
}

async function proxyLocalEdgeStatus(request: NextRequest) {
  const baseUrl = localBackendBase(request);
  if (!baseUrl) return null;
  const response = await fetch(`${baseUrl}/api/network/edge/status`, {
    cache: "no-store",
  });
  if (response.status === 404 || response.status === 405) return null;
  return {
    body: await response.json(),
    status: response.status,
  };
}

export async function GET(request: NextRequest) {
  try {
    const local = await proxyLocalEdgeStatus(request);
    if (local) return NextResponse.json(local.body, { status: local.status });
    const proxied = await proxyJson("/api/network/edge/status");
    if (proxied) return NextResponse.json(proxied.body, { status: proxied.status });
    return NextResponse.json(fallbackEdgeStatus());
  } catch {
    return NextResponse.json(fallbackEdgeStatus());
  }
}
