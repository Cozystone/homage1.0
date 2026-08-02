import { NextRequest, NextResponse } from "next/server";
import { proxyJson } from "../../_backend";
import { filterSeedViewer, loadBundledSeedViewer } from "../_seedFallback";

export async function GET(request: NextRequest) {
  const params = request.nextUrl.searchParams.toString();
  const path = `/api/seed-research/viewer${params ? `?${params}` : ""}`;
  try {
    const proxied = await proxyJson(path);
    if (proxied) return NextResponse.json(proxied.body, { status: proxied.status });
    const bundled = await loadBundledSeedViewer();
    if (bundled) {
      return NextResponse.json(filterSeedViewer(
        bundled,
        request.nextUrl.searchParams.get("search") ?? "",
        request.nextUrl.searchParams.get("relation_type") ?? "all",
        request.nextUrl.searchParams.get("trust_state") ?? "all",
      ));
    }
    return NextResponse.json({
      mode: "seed_research_viewer",
      read_only: true,
      not_local_brain: true,
      run_id: null,
      badge: "Seed Research Viewer",
      concept_count: 0,
      relation_count: 0,
      visible_concept_count: 0,
      visible_relation_count: 0,
      nodes: [],
      edges: [],
      filters: { relation_types: [], trust_states: [] },
      local_brain_isolation: {
        reads_local_brain: false,
        writes_local_brain: false,
        source_file: "data/seed_research/current/viewer_export.json",
      },
    });
  } catch {
    const bundled = await loadBundledSeedViewer();
    if (bundled) {
      return NextResponse.json(filterSeedViewer(
        bundled,
        request.nextUrl.searchParams.get("search") ?? "",
        request.nextUrl.searchParams.get("relation_type") ?? "all",
        request.nextUrl.searchParams.get("trust_state") ?? "all",
      ));
    }
    return NextResponse.json({ error: "Seed Research Viewer unavailable" }, { status: 503 });
  }
}
