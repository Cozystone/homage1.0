import { NextResponse } from "next/server";
import { proxyJson } from "../../_backend";

type AnyRecord = Record<string, unknown>;

function asRecord(value: unknown): AnyRecord {
  return value && typeof value === "object" && !Array.isArray(value) ? value as AnyRecord : {};
}

function asArray(value: unknown): unknown[] {
  return Array.isArray(value) ? value : [];
}

function notConfigured(query: string, status = 200) {
  return NextResponse.json(
    {
      query,
      status: "web_not_configured",
      answer: "Cloud Brain has no configured evidence provider for this query. No evidence was fabricated.",
      cloud_chunks: [],
      attached_nodes: 0,
      attached_relations: 0,
      evidence_bundles: [],
      candidate_fragments: [],
      local_write: false,
      temporary: true,
      pair_edges_sent: 0,
    },
    { status },
  );
}

function normalizeExchange(query: string, exchange: AnyRecord) {
  const states = asArray(exchange.states).map(String);
  const chunk = asRecord(exchange.cloud_graph_chunk);
  const evidenceBundle = asRecord(exchange.evidence_bundle);
  const workingMemory = asRecord(exchange.working_memory);
  const overlay = asRecord(workingMemory.overlay_final ?? workingMemory.overlay ?? workingMemory.working_memory_overlay);
  const overlayInner = asRecord(overlay.working_memory_overlay ?? overlay);
  const truth = asRecord(exchange.truth);
  const promotion = asRecord(exchange.promotion);
  const chunkNodeCount = asArray(chunk.semantic_nodes).length;
  const chunkRelationCount = asArray(chunk.relations).length;
  const overlayNodeCount = Number(overlayInner.cloud_attached_nodes ?? 0);
  const overlayRelationCount = Number(overlayInner.cloud_attached_edges ?? 0);
  const cloudHit = states.includes("cloud_hit") || asArray(chunk.semantic_nodes).length > 0;
  const hasEvidence = asArray(evidenceBundle.evidence_refs).length > 0 || asArray(chunk.evidence_refs).length > 0;
  const attachedNodes = cloudHit || hasEvidence
    ? Math.max(Number.isFinite(overlayNodeCount) ? overlayNodeCount : 0, chunkNodeCount)
    : 0;
  const attachedRelations = cloudHit || hasEvidence
    ? Math.max(Number.isFinite(overlayRelationCount) ? overlayRelationCount : 0, chunkRelationCount)
    : 0;
  const status = cloudHit
    ? (hasEvidence ? "evidence_attached" : "cloud_hit")
    : states.includes("web_not_configured")
      ? "web_not_configured"
      : "cloud_miss";

  return {
    query: String(exchange.query ?? query),
    status,
    answer: status === "cloud_hit" || status === "evidence_attached"
      ? "Relevant Cloud Brain context was found and attached temporarily for this response."
      : "Cloud Brain did not find enough relevant public graph context. No evidence was fabricated.",
    cloud_chunks: Object.keys(chunk).length > 0 ? [chunk] : [],
    attached_nodes: Number.isFinite(attachedNodes) ? attachedNodes : 0,
    attached_relations: Number.isFinite(attachedRelations) ? attachedRelations : 0,
    evidence_bundles: Object.keys(evidenceBundle).length > 0 ? [evidenceBundle] : [],
    candidate_fragments: asArray(exchange.candidate_fragments),
    candidate_status: promotion.verified_cloud_fragment ? "verified_fragment" : promotion.candidate_pending ? "candidate_pending" : "none",
    local_write: String(truth.local_brain_write ?? exchange.local_write ?? "false").toLowerCase() === "true",
    temporary: true,
    pair_edges_sent: Number(truth.pair_edges_sent ?? 0) || 0,
  };
}

export async function POST(request: Request) {
  let payload: AnyRecord = {};
  let query = "GraphRAG memory";
  try {
    payload = await request.json() as AnyRecord;
    query = String(payload.query ?? query);
  } catch {
    // Keep the default read-only query.
  }

  try {
    const proxied = await proxyJson("/api/working-memory/local-cloud-exchange", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        query,
        pin_context: false,
        allow_web: Boolean(payload.allow_web_evidence ?? payload.allow_web ?? false),
        max_chunks: Number(payload.max_chunks ?? 1) || 1,
        max_latency_ms: 900,
      }),
    });

    if (!proxied) return notConfigured(query);
    if (proxied.status >= 500) return notConfigured(query);
    return NextResponse.json(normalizeExchange(query, asRecord(proxied.body)), { status: proxied.status });
  } catch {
    return notConfigured(query);
  }
}
