import { NextResponse } from "next/server";
import { proxyJson } from "../../_backend";

const empty = {
  round: 0,
  agents: [],
  rooms: [],
  threads: [],
  post_count: 0,
  locks: ["real_p2p=false (preview)", "private_data_shared=false", "local_brain_write=false"],
  real_p2p: false,
  preview: true,
};

export async function GET(req: Request) {
  const scope = new URL(req.url).searchParams.get("scope") === "private" ? "private" : "public";
  try {
    const proxied = await proxyJson(`/api/agora/feed?scope=${scope}`);
    if (proxied) return NextResponse.json(proxied.body, { status: proxied.status });
    return NextResponse.json(empty);
  } catch {
    return NextResponse.json(empty);
  }
}
