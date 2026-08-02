import { NextResponse } from "next/server";
import { proxyJson } from "../../../../_backend";

const empty = {
  running: false,
  uptime_seconds: 0,
  ticks: 0,
  sentences_fed: 0,
  sentences_accepted: 0,
  concepts_added: 0,
  relations_added: 0,
  surface_added: 0,
  sentences_per_second: 0,
  concepts_per_minute: 0,
  accept_rate: 0,
  last_titles: [],
  last_error: null,
  source: "wikipedia_random_public_extract",
  mock_growth: false,
};

export async function GET() {
  try {
    const proxied = await proxyJson("/api/cloud-brain/learning/continuous/metrics");
    if (proxied) return NextResponse.json(proxied.body, { status: proxied.status });
    return NextResponse.json(empty);
  } catch {
    return NextResponse.json(empty);
  }
}
