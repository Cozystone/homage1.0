import { NextResponse } from "next/server";
import { proxyJson } from "../../_backend";

const fallback = {
  available: false,
  state: "fallback",
  message: "Deployed sandbox telemetry fallback. Local backend can read nvidia-smi when available.",
  gpu_name: "Deployment sandbox",
  utilization: 0,
  vram_used: 0,
  vram_total: 0,
  temperature: null,
  power_draw: null,
};

export async function GET() {
  try {
    const proxied = await proxyJson("/api/telemetry/gpu");
    if (proxied) return NextResponse.json(proxied.body, { status: proxied.status });
    return NextResponse.json(fallback);
  } catch {
    return NextResponse.json(fallback);
  }
}
