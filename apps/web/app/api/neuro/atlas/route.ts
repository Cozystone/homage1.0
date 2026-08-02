import { NextResponse } from "next/server";
import { proxyJson } from "../../_backend";

const fallbackAtlas = {
  schema: "atanor.atlas.v1",
  mode: "preview",
  provider: "local",
  broker_state: "local_broker_mode",
  hub: {
    label: "Seoul Hub",
    lat: 37.5665,
    lng: 126.978,
    role: "Local visual origin hub.",
  },
  nodes: [
    {
      display_id: "anon-region-seoul-hub",
      region_label: "Seoul",
      country_code: "KR",
      approximate_lat: 37.56,
      approximate_lng: 126.97,
      jitter_seed: "seoul-hub",
      state: "idle",
      activity_level: 0.42,
      last_seen_bucket: "today",
      source: "local",
    },
  ],
  stats: {
    active_contributor_nodes: 0,
    public_tasks_per_min: 0,
    fragments_verified_today: 0,
    source_noise_rejected_today: 0,
    pending_credits: 0,
    confirmed_credits: 0,
  },
  my_node: {
    state: "Idle",
    mode: "Contributor Preview",
    cpu_limit_percent: 20,
    ram_limit_gb: 2,
    network_mode: "broker_metadata_only",
    today_credit: 0,
    private_data: "Not Shared",
  },
  relay: {
    active_region: "East Asia",
    sequence: ["East Asia", "Europe", "North America", "Pacific"],
    status: "local_preview",
  },
  privacy: {
    raw_ip_stored: false,
    raw_ip_returned: false,
    exact_location_shown: false,
    private_data_shared: false,
    contributor_identifier_exposed: false,
    device_identifier_exposed: false,
    ip_geo_provider: "none",
    display_precision: "coarse_region_jittered",
  },
  disclaimer: "ATANOR Atlas is not a surveillance map. It is an anonymous regional visualization of Cloud Brain contribution signals.",
};

export async function GET() {
  try {
    const proxied = await proxyJson("/api/neuro/atlas");
    if (proxied) return NextResponse.json(proxied.body, { status: proxied.status });
  } catch {
    // Keep the user-facing Atlas honest when no local companion is reachable.
  }
  return NextResponse.json(fallbackAtlas);
}
