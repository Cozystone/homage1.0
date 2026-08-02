import { NextRequest, NextResponse } from "next/server";
import { proxyJson } from "../../_backend";

const LOCAL_EDGE_HOSTS = new Set(["127.0.0.1", "localhost", "::1", "[::1]"]);

function fallbackBrainSyncStatus() {
  return {
    state: "viewer_only",
    architecture: "local_first_patch_sync",
    orchestrator_state: "viewer_only",
    local_weight: 1,
    cloud_weight: 0,
    fragment_requested: false,
    fragment_reason: "local_companion_unavailable",
    local_brain_primary: true,
    cloud_brain_role: "bounded_public_fragment_assist",
    uploads_raw_private_payloads: false,
    uploads_full_local_graph: false,
    fragment_attach_layer: "working_memory",
    promotion_requires_snapshot: true,
    active_working_memory_fragments: 0,
    status_lines: [
      "Local companion is not connected.",
      "Cloud Brain telemetry remains read-only until the local sidecar is available.",
    ],
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

async function proxyLocalBrainSyncStatus(request: NextRequest) {
  const baseUrl = localBackendBase(request);
  if (!baseUrl) return null;
  const response = await fetch(`${baseUrl}/api/brain-sync/status`, {
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
    const local = await proxyLocalBrainSyncStatus(request);
    if (local) return NextResponse.json(local.body, { status: local.status });
    const proxied = await proxyJson("/api/brain-sync/status");
    if (proxied) return NextResponse.json(proxied.body, { status: proxied.status });
    return NextResponse.json(fallbackBrainSyncStatus());
  } catch {
    return NextResponse.json(fallbackBrainSyncStatus());
  }
}
