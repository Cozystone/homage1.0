import { NextRequest, NextResponse } from "next/server";
import { proxyJson } from "../../../_backend";

const LOCAL_EDGE_HOSTS = new Set(["127.0.0.1", "localhost", "::1", "[::1]"]);

function fallbackAdvertiseStatus() {
  return {
    state: "viewer_only",
    advertised: false,
    reason: "local_companion_unavailable",
    architecture: "edge_compute_broker",
    cloud_required: false,
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

async function proxyLocalEdgeAdvertise(request: NextRequest) {
  const baseUrl = localBackendBase(request);
  if (!baseUrl) return null;
  const response = await fetch(`${baseUrl}/api/network/edge/advertise`, {
    method: "POST",
    cache: "no-store",
  });
  if (response.status === 404 || response.status === 405) return null;
  return {
    body: await response.json(),
    status: response.status,
  };
}

export async function POST(request: NextRequest) {
  try {
    const local = await proxyLocalEdgeAdvertise(request);
    if (local) return NextResponse.json(local.body, { status: local.status });
    const proxied = await proxyJson("/api/network/edge/advertise", { method: "POST" });
    if (proxied) return NextResponse.json(proxied.body, { status: proxied.status });
    return NextResponse.json(fallbackAdvertiseStatus());
  } catch {
    return NextResponse.json(fallbackAdvertiseStatus());
  }
}
