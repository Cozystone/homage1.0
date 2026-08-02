import { NextResponse } from "next/server";
import { proxyJson } from "../../_backend";

const defaultHardware = {
  cpu: "AMD Ryzen 9 9950X3D",
  gpu: "ZOTAC GAMING GeForce RTX 5080 AMP EXTREME INFINITY",
  vram_gb: 16,
  motherboard: "ASUS ROG CROSSHAIR X870E HERO",
  ram_gb: 32,
  storage: "GIGABYTE AORUS Gen4 7300 V2",
  storage_gb: 1000,
  psu: "SuperFlower SF-1200F14XP LEADEX VII PRO PLATINUM ATX 3.1",
  cooler: "CoolerMaster MASTERLIQUID 360 ATMOS",
  case: "Antec FLUX MESH BTF Black",
};

function boundedNumber(value: unknown, fallback: number, min: number, max: number) {
  const parsed = Number(value);
  return Number.isFinite(parsed) ? Math.max(min, Math.min(max, parsed)) : fallback;
}

function diskBudgetState(input: {
  diskTotalGb: number;
  diskFreeGb: number;
  desiredReserveGb: number;
  currentGrowthBudgetGb?: number;
  projectedGrowthGb?: number;
}) {
  const total = Math.max(1, input.diskTotalGb);
  const free = Math.max(0, Math.min(total, input.diskFreeGb));
  const hardMin = Number(Math.min(20, Math.max(10, total * 0.02)).toFixed(1));
  const softMin = Number(Math.min(50, Math.max(30, total * 0.05)).toFixed(1));
  const desired = Number(input.desiredReserveGb.toFixed(1));
  let status: "safe" | "caution" | "constrained" | "critical";
  let action: "normal" | "slow_growth" | "compact" | "pause_growth";
  let message: string;
  if (free < hardMin) {
    status = "critical";
    action = "pause_growth";
    message = `Disk free: ${free.toFixed(1)}GB. Growth is paused to protect the local store.`;
  } else if (free < softMin) {
    status = "constrained";
    action = "compact";
    message = `Disk free: ${free.toFixed(1)}GB. Growth is slowed and compaction is recommended.`;
  } else if (free < desired) {
    status = "caution";
    action = "slow_growth";
    message = `Disk free: ${free.toFixed(1)}GB. Normal operation is safe. Large Cloud Brain growth reserve is not met, so growth runs in conservative mode.`;
  } else {
    status = "safe";
    action = "normal";
    message = `Disk free: ${free.toFixed(1)}GB. Normal operation and selected growth mode are within budget.`;
  }
  return {
    disk_total_gb: Number(total.toFixed(1)),
    disk_free_gb: Number(free.toFixed(1)),
    hard_min_free_gb: hardMin,
    soft_min_free_gb: softMin,
    desired_reserve_gb: desired,
    current_growth_budget_gb: Number(Math.max(0, input.currentGrowthBudgetGb ?? free - softMin).toFixed(1)),
    projected_growth_gb: input.projectedGrowthGb ?? null,
    status,
    action,
    message,
  };
}

function demoStabilityPlan(input: Record<string, any> = {}) {
  const hardware = { ...defaultHardware, ...(input.hardware_profile ?? {}) };
  const ramGb = boundedNumber(hardware.ram_gb, 32, 8, 512);
  const vramGb = boundedNumber(hardware.vram_gb, 16, 4, 192);
  const storageGb = boundedNumber(hardware.storage_gb, 1000, 128, 16000);
  const diskFreeGb = boundedNumber(hardware.disk_free_gb ?? input.disk_free_gb, storageGb, 0, storageGb);
  const targetNodes = boundedNumber(input.target_nodes, 10_000, 1_000, 500_000);
  const targetEdges = boundedNumber(input.target_edges, Math.max(30_000, targetNodes * 4), 2_000, 3_000_000);
  const ramSoft = Number((ramGb * 0.72).toFixed(1));
  const vramSoft = Number((vramGb * 0.74).toFixed(1));
  const hotWindowNodes = Math.min(Math.max(2048, Math.floor(targetNodes / 10)), 24000);
  const desiredReserveGb = Number(Math.max(120, storageGb * 0.2).toFixed(1));
  const graphBudgetGb = Number(Math.max(80, storageGb - desiredReserveGb - 120).toFixed(1));
  const diskBudget = diskBudgetState({
    diskTotalGb: storageGb,
    diskFreeGb,
    desiredReserveGb,
    currentGrowthBudgetGb: Math.min(graphBudgetGb, Math.max(0, diskFreeGb - 20)),
    projectedGrowthGb: Math.min(graphBudgetGb, Math.max(1, targetEdges / 1_000_000 * 0.35)),
  });

  return {
    generated_at: new Date().toISOString(),
    profile_name: "ATANOR Sustained Learning Profile",
    hardware_profile: hardware,
    target_workload: {
      duration_hours: boundedNumber(input.duration_hours, 72, 1, 720),
      target_nodes: targetNodes,
      target_edges: targetEdges,
      expected_relation_density: Number((targetEdges / Math.max(1, targetNodes)).toFixed(2)),
    },
    runtime_envelope: {
      ram_soft_gb: ramSoft,
      ram_hard_gb: Number((ramGb * 0.86).toFixed(1)),
      vram_soft_gb: vramSoft,
      vram_hard_gb: Number((vramGb * 0.9).toFixed(1)),
      storage_reserve_gb: desiredReserveGb,
      graph_store_budget_gb: graphBudgetGb,
      disk_budget: diskBudget,
      checkpoint_ring_gb: Number(Math.min(160, Math.max(48, storageGb * 0.08)).toFixed(1)),
    },
    queue_policy: {
      harvest_pending_cap: Math.min(4096, Math.max(512, Math.floor(targetNodes / 4))),
      datagate_batch_docs: ramGb < 64 ? 64 : 128,
      ontology_delta_chunks: ramGb < 64 ? 256 : 512,
      node_write_batch: diskBudget.status === "critical" ? 0 : diskBudget.status === "constrained" ? 200 : 500,
      edge_write_batch: diskBudget.status === "critical" ? 0 : diskBudget.status === "constrained" ? 800 : diskBudget.status === "caution" ? 1500 : 2000,
      rag_query_concurrency: 2,
      training_microbatch_policy: "bf16/8-bit where safe, gradient accumulation, activation checkpointing, never full-corpus in VRAM",
    },
    graph_policy: {
      storage_model: "append-only graph event log + SQLite WAL hot index + periodic compacted snapshots",
      identity_model: "stable normalized node ids; merge duplicate labels before writing edges",
      edge_model: "one edge row per typed relation with evidence_count, confidence, status, and last_seen_at",
      hot_window_nodes: hotWindowNodes,
      hot_window_edges: Math.min(Math.max(12000, hotWindowNodes * 8), 240000),
      ui_render_nodes: Math.min(2000, Math.max(240, Math.floor(hotWindowNodes / 8))),
      ui_render_strategy: "LOD sampling: render active frontier, top-confidence anchors, and community summaries only",
      compaction_trigger: { event_log_mb: 512, edge_duplication_ratio: 1.35, ram_soft_gb: ramSoft },
    },
    checkpoint_policy: {
      run_state_interval_minutes: 5,
      ontology_snapshot_interval_minutes: 20,
      training_checkpoint_interval_minutes: 15,
      checkpoint_keep_last: 8,
      resume_contract: "all stages are idempotent by run_id, document_id, chunk_id, node_id, and edge key",
    },
    backpressure_policy: [
      { condition: "RAM >= soft watermark", action: "pause harvest, flush ontology batches, compact hot graph window, keep RAG read-only" },
      { condition: "VRAM >= soft watermark", action: "pause ATANOR Oven batches, keep DataGate/Ontology on CPU, lower microbatch size" },
      { condition: "graph writer lag > 2 batches", action: "stop creating new relations; only merge known nodes until writer catches up" },
      { condition: "disk free < hard minimum", action: "pause growth, keep graph read-only, allow checkpoint, require operator review" },
      { condition: "disk free < soft minimum", action: "slow growth, recommend compaction, prevent new large ingestion" },
      { condition: "disk free < desired large-growth reserve", action: "normal UI allowed; run large Cloud Brain growth in conservative mode" },
    ],
  };
}

export async function GET() {
  try {
    const proxied = await proxyJson("/api/neuro/stability");
    if (proxied) return NextResponse.json(proxied.body, { status: proxied.status });
    return NextResponse.json(demoStabilityPlan());
  } catch {
    return NextResponse.json(demoStabilityPlan());
  }
}

export async function POST(request: Request) {
  const body = await request.json().catch(() => ({}));
  try {
    const proxied = await proxyJson("/api/neuro/stability", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    if (proxied) return NextResponse.json(proxied.body, { status: proxied.status });
    return NextResponse.json(demoStabilityPlan(body));
  } catch {
    return NextResponse.json(demoStabilityPlan(body));
  }
}
