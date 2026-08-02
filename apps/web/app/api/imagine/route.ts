import { NextResponse } from "next/server";
import { proxyJson } from "../_backend";

// Generative particle synthesis: any concept -> its own animated form,
// synthesised from the concept's graph signature. No LLM, no image model.
export async function POST(req: Request) {
  let body: unknown = {};
  try {
    body = await req.json();
  } catch {
    body = {};
  }
  const proxied = await proxyJson("/api/agentic-os/imagine", {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify(body),
  });
  return NextResponse.json(proxied?.body ?? { particles: [], particle_count: 0 }, {
    status: proxied?.status ?? 503,
  });
}
