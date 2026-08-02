import { NextResponse } from "next/server";
import { proxyJson } from "../../../../../_backend";

export async function GET(_request: Request, context: { params: Promise<{ tile_id: string }> }) {
  const { tile_id } = await context.params;
  const proxied = await proxyJson(`/api/cloud-brain/sphere/tile/${encodeURIComponent(tile_id)}/children`);
  if (proxied) return NextResponse.json(proxied.body, { status: proxied.status });
  return NextResponse.json({ error: "Cloud Brain sphere tile children backend unavailable" }, { status: 503 });
}
