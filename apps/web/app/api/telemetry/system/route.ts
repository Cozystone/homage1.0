import { NextResponse } from "next/server";
import os from "node:os";
import { proxyJson } from "../../_backend";

function fallbackSystemTelemetry() {
  const total = os.totalmem();
  const free = os.freemem();
  const used = Math.max(0, total - free);
  return {
    source: process.env.VERCEL ? "deployment-sandbox" : "local-next",
    cpu_count: os.cpus().length,
    cpu_model: os.cpus()[0]?.model ?? "Unknown CPU",
    ram_total_gb: Number((total / 1024 ** 3).toFixed(2)),
    ram_available_gb: Number((free / 1024 ** 3).toFixed(2)),
    ram_used_gb: Number((used / 1024 ** 3).toFixed(2)),
    ram_used_percent: Number(((used / Math.max(1, total)) * 100).toFixed(1)),
    disk_total_gb: process.env.VERCEL ? 1 : null,
    disk_used_gb: process.env.VERCEL ? 0.1 : null,
    disk_free_gb: null,
    timestamp: new Date().toISOString(),
  };
}

export async function GET() {
  try {
    const proxied = await proxyJson("/api/telemetry/system");
    if (proxied) return NextResponse.json(proxied.body, { status: proxied.status });
    return NextResponse.json(fallbackSystemTelemetry());
  } catch {
    return NextResponse.json(fallbackSystemTelemetry());
  }
}
