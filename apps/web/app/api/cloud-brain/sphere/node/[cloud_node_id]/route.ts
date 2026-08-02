import { NextResponse } from "next/server";
import { proxyJson } from "../../../../_backend";

export async function GET(_request: Request, context: { params: Promise<{ cloud_node_id: string }> }) {
  const { cloud_node_id } = await context.params;
  const proxied = await proxyJson(`/api/cloud-brain/sphere/node/${encodeURIComponent(cloud_node_id)}`);
  if (proxied) return NextResponse.json(proxied.body, { status: proxied.status });
  return NextResponse.json({ error: "Cloud Brain sphere node backend unavailable" }, { status: 503 });
}
