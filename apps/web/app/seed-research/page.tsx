"use client";

import { useEffect, useMemo, useState } from "react";

type SeedNode = {
  id: string;
  label: string;
  labels?: Record<string, string>;
  aliases?: Record<string, string[]>;
  definition?: Record<string, string>;
  type?: string;
  trust_state?: string;
  verification_state?: string;
  confidence?: number;
  x?: number;
  y?: number;
};

type SeedEdge = {
  edge_id: string;
  source: string;
  relation: string;
  target: string;
  confidence?: number;
  trust_state?: string;
};

type ViewerExport = {
  badge: string;
  run_id: string | null;
  read_only: boolean;
  not_local_brain: boolean;
  concept_count: number;
  relation_count: number;
  visible_concept_count: number;
  visible_relation_count: number;
  nodes: SeedNode[];
  edges: SeedEdge[];
  filters?: { relation_types?: string[]; trust_states?: string[] };
  metrics?: Record<string, unknown>;
  local_brain_isolation?: Record<string, unknown>;
};

type RuntimeTrace = {
  query: string;
  local_graph_state: {
    local_brain_initialized: boolean;
    local_total_nodes: number;
    local_total_edges: number;
    seed_written_to_local_brain: boolean;
    seed_counted_as_learned_memory: boolean;
  };
  seed_anchor_trace: {
    seed_anchor_ready: boolean;
    seed_used: boolean;
    matched_seed_concepts: Array<{ concept_id: string; label: string; confidence?: number }>;
    matched_seed_edges: Array<{ source: string; relation: string; target: string; confidence?: number }>;
    final_answer_generation_claimed: boolean;
    external_llm_used: boolean;
    external_sllm_used: boolean;
    rule_based_answer_engine: boolean;
  };
  cloud_alignment_trace: {
    candidate_fragments_checked: number;
    public_fragments_checked?: number;
    fragments_aligned_to_seed: number;
    matched_fragment_ids?: string[];
  };
  runtime_claim: string;
};

type AlignmentSummary = {
  proof_exists: boolean;
  candidate_fragments_checked: number;
  public_fragments_checked: number;
  rejected_private_fragments: number;
  fragments_aligned_to_seed: number;
  concepts_aligned_total: number;
  edges_aligned_total: number;
  matched_fragment_ids: string[];
  local_brain_state: {
    local_brain_initialized: boolean;
    local_total_nodes: number;
    local_total_edges: number;
  };
  external_llm_used: boolean;
  external_sllm_used: boolean;
  rule_based_answer_engine: boolean;
  final_answer_generation_claimed: boolean;
};

const EMPTY_VIEWER: ViewerExport = {
  badge: "Seed Research Viewer",
  run_id: null,
  read_only: true,
  not_local_brain: true,
  concept_count: 0,
  relation_count: 0,
  visible_concept_count: 0,
  visible_relation_count: 0,
  nodes: [],
  edges: [],
};

export default function SeedResearchViewerPage() {
  const [viewer, setViewer] = useState<ViewerExport>(EMPTY_VIEWER);
  const [search, setSearch] = useState("");
  const [relationType, setRelationType] = useState("all");
  const [trustState, setTrustState] = useState("all");
  const [selectedNodeId, setSelectedNodeId] = useState<string | null>(null);
  const [selectedEdgeId, setSelectedEdgeId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [traceQuery, setTraceQuery] = useState("Evidence Claim");
  const [runtimeTrace, setRuntimeTrace] = useState<RuntimeTrace | null>(null);
  const [traceError, setTraceError] = useState<string | null>(null);
  const [alignmentSummary, setAlignmentSummary] = useState<AlignmentSummary | null>(null);
  const [alignmentError, setAlignmentError] = useState<string | null>(null);
  const [alignmentRunning, setAlignmentRunning] = useState(false);

  useEffect(() => {
    const controller = new AbortController();
    const params = new URLSearchParams({ search, relation_type: relationType, trust_state: trustState });
    fetch(`/api/seed-research/viewer?${params.toString()}`, { cache: "no-store", signal: controller.signal })
      .then(async (response) => {
        if (!response.ok) throw new Error(`Seed viewer returned ${response.status}`);
        return response.json();
      })
      .then((data: ViewerExport) => {
        setViewer(data);
        setError(null);
      })
      .catch((caught) => {
        if (!controller.signal.aborted) setError(caught instanceof Error ? caught.message : "Seed viewer failed");
      });
    return () => controller.abort();
  }, [search, relationType, trustState]);

  useEffect(() => {
    const controller = new AbortController();
    const handle = window.setTimeout(() => {
      fetch(`/api/seed-research/runtime-trace?q=${encodeURIComponent(traceQuery || "Evidence Claim")}`, {
        cache: "no-store",
        signal: controller.signal,
      })
        .then(async (response) => {
          if (!response.ok) throw new Error(`Runtime trace returned ${response.status}`);
          return response.json();
        })
        .then((data: RuntimeTrace) => {
          setRuntimeTrace(data);
          setTraceError(null);
        })
        .catch((caught) => {
          if (!controller.signal.aborted) setTraceError(caught instanceof Error ? caught.message : "Runtime trace failed");
        });
    }, 180);
    return () => {
      window.clearTimeout(handle);
      controller.abort();
    };
  }, [traceQuery]);

  function refreshAlignmentSummary(signal?: AbortSignal) {
    return fetch("/api/seed-research/cloud-fragment-alignment", { cache: "no-store", signal })
      .then(async (response) => {
        if (!response.ok) throw new Error(`Alignment summary returned ${response.status}`);
        return response.json();
      })
      .then((data: AlignmentSummary) => {
        setAlignmentSummary(data);
        setAlignmentError(null);
      });
  }

  useEffect(() => {
    const controller = new AbortController();
    refreshAlignmentSummary(controller.signal).catch((caught) => {
      if (!controller.signal.aborted) setAlignmentError(caught instanceof Error ? caught.message : "Alignment summary failed");
    });
    return () => controller.abort();
  }, []);

  async function runAlignmentProof() {
    setAlignmentRunning(true);
    try {
      const response = await fetch("/api/seed-research/cloud-fragment-alignment/run", { method: "POST", cache: "no-store" });
      if (!response.ok) throw new Error(`Alignment proof returned ${response.status}`);
      const data = await response.json();
      setAlignmentSummary(data);
      setAlignmentError(null);
    } catch (caught) {
      setAlignmentError(caught instanceof Error ? caught.message : "Alignment proof failed");
    } finally {
      setAlignmentRunning(false);
    }
  }

  const nodesById = useMemo(() => new Map(viewer.nodes.map((node) => [node.id, node])), [viewer.nodes]);
  const selectedNode = selectedNodeId ? nodesById.get(selectedNodeId) ?? null : null;
  const selectedEdge = selectedEdgeId ? viewer.edges.find((edge) => edge.edge_id === selectedEdgeId) ?? null : null;
  const relationTypes = ["all", ...(viewer.filters?.relation_types ?? [])];
  const trustStates = ["all", ...(viewer.filters?.trust_states ?? [])];

  function exportVisibleSubgraph() {
    const blob = new Blob([JSON.stringify({
      schema: "atanor.seed-research.visible-subgraph.v1",
      run_id: viewer.run_id,
      nodes: viewer.nodes,
      edges: viewer.edges,
      exported_at: new Date().toISOString(),
    }, null, 2)], { type: "application/json" });
    const url = URL.createObjectURL(blob);
    const anchor = document.createElement("a");
    anchor.href = url;
    anchor.download = `atanor-seed-${viewer.run_id ?? "current"}-visible-subgraph.json`;
    anchor.click();
    URL.revokeObjectURL(url);
  }

  return (
    <main className="seed-shell">
      <style jsx global>{`
        body {
          margin: 0;
          background: #050505;
          color: #f6f6f0;
          font-family: Helvetica, Arial, sans-serif;
        }
        .seed-shell {
          background: radial-gradient(circle at 52% 22%, rgba(255, 138, 0, 0.08), transparent 28%), #050505;
          display: grid;
          gap: 18px;
          grid-template-rows: auto minmax(0, 1fr);
          height: 100vh;
          overflow: hidden;
          padding: 24px;
        }
        .seed-top {
          align-items: center;
          border-bottom: 1px solid rgba(255,255,255,0.12);
          display: flex;
          justify-content: space-between;
          padding-bottom: 16px;
        }
        .seed-top h1 {
          font-size: 22px;
          letter-spacing: 0.08em;
          margin: 0;
          text-transform: uppercase;
        }
        .seed-top p {
          color: rgba(246,246,240,0.62);
          font-size: 12px;
          margin: 6px 0 0;
        }
        .seed-badge {
          border: 1px solid rgba(255, 138, 0, 0.55);
          color: #ff9f1c;
          font-size: 11px;
          font-weight: 800;
          letter-spacing: 0.08em;
          padding: 10px 13px;
          text-transform: uppercase;
        }
        .seed-grid {
          display: grid;
          gap: 18px;
          grid-template-columns: 320px minmax(0, 1fr) 360px;
          min-height: 0;
        }
        .seed-panel {
          background: rgba(10, 10, 10, 0.88);
          border: 1px solid rgba(255,255,255,0.12);
          min-height: 0;
          padding: 16px;
        }
        .seed-panel h2 {
          font-size: 13px;
          letter-spacing: 0.08em;
          margin: 0 0 14px;
          text-transform: uppercase;
        }
        .seed-controls {
          display: grid;
          gap: 12px;
        }
        .seed-controls input,
        .seed-controls select {
          background: #070707;
          border: 1px solid rgba(255,255,255,0.16);
          color: #f6f6f0;
          font: 700 13px Helvetica, Arial, sans-serif;
          height: 42px;
          padding: 0 12px;
        }
        .seed-stats {
          display: grid;
          gap: 10px;
          grid-template-columns: repeat(2, 1fr);
          margin-top: 16px;
        }
        .seed-stat {
          border: 1px solid rgba(255,255,255,0.1);
          padding: 12px;
        }
        .seed-stat span {
          color: rgba(246,246,240,0.55);
          display: block;
          font-size: 10px;
          letter-spacing: 0.08em;
          text-transform: uppercase;
        }
        .seed-stat strong {
          display: block;
          font-size: 22px;
          margin-top: 8px;
        }
        .seed-canvas {
          background: radial-gradient(circle at center, rgba(255,255,255,0.055), transparent 38%), #000;
          height: 100%;
          min-height: 0;
          position: relative;
          overflow: hidden;
        }
        .seed-edge {
          background: rgba(255, 138, 0, 0.24);
          height: 1px;
          left: 50%;
          position: absolute;
          top: 50%;
          transform-origin: 0 0;
        }
        .seed-node {
          background: #f6f6f0;
          border: 1px solid rgba(255,255,255,0.85);
          box-shadow: 0 0 18px rgba(255,255,255,0.22);
          cursor: pointer;
          height: 10px;
          margin: -5px 0 0 -5px;
          position: absolute;
          width: 10px;
        }
        .seed-node[data-trust="seed_candidate"] {
          background: #ff9f1c;
          border-color: #ff9f1c;
          box-shadow: 0 0 24px rgba(255, 138, 0, 0.38);
        }
        .seed-node[data-selected="true"] {
          outline: 2px solid #ff9f1c;
          outline-offset: 5px;
        }
        .seed-list {
          display: grid;
          gap: 8px;
          max-height: 30vh;
          overflow: auto;
        }
        .seed-list button {
          background: transparent;
          border: 1px solid rgba(255,255,255,0.1);
          color: #f6f6f0;
          cursor: pointer;
          font: 700 12px Helvetica, Arial, sans-serif;
          padding: 9px 10px;
          text-align: left;
        }
        .seed-detail {
          color: rgba(246,246,240,0.74);
          display: grid;
          font-size: 12px;
          gap: 9px;
          line-height: 1.55;
        }
        .seed-detail strong {
          color: #fff;
          font-size: 17px;
        }
        .seed-export {
          background: #f6f6f0;
          border: 0;
          color: #050505;
          cursor: pointer;
          font: 900 12px Helvetica, Arial, sans-serif;
          height: 42px;
          letter-spacing: 0.06em;
          margin-top: 14px;
          text-transform: uppercase;
          width: 100%;
        }
        .seed-error {
          color: #ff9f1c;
          font-size: 12px;
          margin-top: 12px;
        }
        .runtime-proof {
          border: 1px solid rgba(255, 138, 0, 0.25);
          margin-top: 16px;
          padding: 12px;
        }
        .runtime-proof input {
          background: #030303;
          border: 1px solid rgba(255,255,255,0.14);
          color: #f6f6f0;
          font: 700 12px Helvetica, Arial, sans-serif;
          height: 38px;
          margin-bottom: 10px;
          padding: 0 10px;
          width: calc(100% - 22px);
        }
        .runtime-proof-row {
          align-items: center;
          border-top: 1px solid rgba(255,255,255,0.08);
          display: flex;
          font-size: 11px;
          justify-content: space-between;
          padding: 7px 0;
        }
        .runtime-proof-row span {
          color: rgba(246,246,240,0.54);
        }
        .runtime-proof-row strong {
          color: #f6f6f0;
          font-size: 11px;
        }
        .runtime-proof-list {
          color: rgba(246,246,240,0.64);
          display: grid;
          font-size: 11px;
          gap: 6px;
          max-height: 80px;
          overflow: auto;
          padding-top: 8px;
        }
        .alignment-proof-button {
          background: #ff9f1c;
          border: 0;
          color: #050505;
          cursor: pointer;
          font: 900 11px Helvetica, Arial, sans-serif;
          height: 36px;
          letter-spacing: 0.05em;
          margin: 10px 0;
          text-transform: uppercase;
          width: 100%;
        }
        .alignment-note {
          color: rgba(246,246,240,0.52);
          font-size: 10px;
          line-height: 1.45;
          margin: 8px 0 0;
        }
      `}</style>

      <header className="seed-top">
        <div>
          <h1>ATANOR Seed Graph Research</h1>
          <p>Read-only research projection. This is not Local Brain memory.</p>
        </div>
        <span className="seed-badge">{viewer.badge} / {viewer.run_id ?? "no run"}</span>
      </header>

      <section className="seed-grid">
        <aside className="seed-panel">
          <h2>Research Controls</h2>
          <div className="seed-controls">
            <input value={search} onChange={(event) => setSearch(event.target.value)} placeholder="Search concept label or alias" />
            <select value={relationType} onChange={(event) => setRelationType(event.target.value)}>
              {relationTypes.map((relation) => <option key={relation}>{relation}</option>)}
            </select>
            <select value={trustState} onChange={(event) => setTrustState(event.target.value)}>
              {trustStates.map((state) => <option key={state}>{state}</option>)}
            </select>
          </div>
          <div className="seed-stats">
            <div className="seed-stat"><span>Concepts</span><strong>{viewer.visible_concept_count}</strong></div>
            <div className="seed-stat"><span>Relations</span><strong>{viewer.visible_relation_count}</strong></div>
            <div className="seed-stat"><span>Total Concepts</span><strong>{viewer.concept_count}</strong></div>
            <div className="seed-stat"><span>Total Edges</span><strong>{viewer.relation_count}</strong></div>
          </div>
          <button className="seed-export" onClick={exportVisibleSubgraph}>Export Visible Subgraph</button>
          {error ? <p className="seed-error">{error}</p> : null}
          <div className="runtime-proof">
            <h2>Runtime Anchor Proof</h2>
            <input value={traceQuery} onChange={(event) => setTraceQuery(event.target.value)} placeholder="Runtime proof query" />
            {runtimeTrace ? (
              <>
                <div className="runtime-proof-row"><span>Seed used</span><strong>{String(runtimeTrace.seed_anchor_trace.seed_used)}</strong></div>
                <div className="runtime-proof-row"><span>Local initialized</span><strong>{String(runtimeTrace.local_graph_state.local_brain_initialized)}</strong></div>
                <div className="runtime-proof-row"><span>Local nodes/edges</span><strong>{runtimeTrace.local_graph_state.local_total_nodes} / {runtimeTrace.local_graph_state.local_total_edges}</strong></div>
                <div className="runtime-proof-row"><span>Cloud candidates</span><strong>{runtimeTrace.cloud_alignment_trace.candidate_fragments_checked}</strong></div>
                <div className="runtime-proof-row"><span>Fragments aligned</span><strong>{runtimeTrace.cloud_alignment_trace.fragments_aligned_to_seed}</strong></div>
                <div className="runtime-proof-row"><span>External LLM</span><strong>{String(runtimeTrace.seed_anchor_trace.external_llm_used)}</strong></div>
                <div className="runtime-proof-row"><span>External sLLM</span><strong>{String(runtimeTrace.seed_anchor_trace.external_sllm_used)}</strong></div>
                <div className="runtime-proof-row"><span>Rule template</span><strong>{String(runtimeTrace.seed_anchor_trace.rule_based_answer_engine)}</strong></div>
                <div className="runtime-proof-row"><span>Final generation</span><strong>{String(runtimeTrace.seed_anchor_trace.final_answer_generation_claimed)}</strong></div>
                <div className="runtime-proof-list">
                  {runtimeTrace.seed_anchor_trace.matched_seed_concepts.slice(0, 6).map((concept) => (
                    <span key={concept.concept_id}>{concept.label} - {concept.concept_id}</span>
                  ))}
                </div>
              </>
            ) : (
              <div className="runtime-proof-row"><span>Trace</span><strong>loading</strong></div>
            )}
            {traceError ? <p className="seed-error">{traceError}</p> : null}
          </div>
          <div className="runtime-proof">
            <h2>Cloud Fragment - Seed Alignment</h2>
            <button className="alignment-proof-button" onClick={runAlignmentProof} disabled={alignmentRunning}>
              {alignmentRunning ? "Running..." : "Run Alignment Proof"}
            </button>
            {alignmentSummary ? (
              <>
                <div className="runtime-proof-row"><span>Proof exists</span><strong>{String(alignmentSummary.proof_exists)}</strong></div>
                <div className="runtime-proof-row"><span>Candidates checked</span><strong>{alignmentSummary.candidate_fragments_checked}</strong></div>
                <div className="runtime-proof-row"><span>Public checked</span><strong>{alignmentSummary.public_fragments_checked}</strong></div>
                <div className="runtime-proof-row"><span>Aligned fragments</span><strong>{alignmentSummary.fragments_aligned_to_seed}</strong></div>
                <div className="runtime-proof-row"><span>Concepts aligned</span><strong>{alignmentSummary.concepts_aligned_total}</strong></div>
                <div className="runtime-proof-row"><span>Edges aligned</span><strong>{alignmentSummary.edges_aligned_total}</strong></div>
                <div className="runtime-proof-row"><span>Local Brain</span><strong>{alignmentSummary.local_brain_state.local_total_nodes} / {alignmentSummary.local_brain_state.local_total_edges}</strong></div>
                <div className="runtime-proof-row"><span>External LLM</span><strong>{String(alignmentSummary.external_llm_used)}</strong></div>
                <div className="runtime-proof-row"><span>External sLLM</span><strong>{String(alignmentSummary.external_sllm_used)}</strong></div>
                <div className="runtime-proof-row"><span>Rule template</span><strong>{String(alignmentSummary.rule_based_answer_engine)}</strong></div>
                <div className="runtime-proof-row"><span>Final generation</span><strong>{String(alignmentSummary.final_answer_generation_claimed)}</strong></div>
                <div className="runtime-proof-list">
                  {alignmentSummary.matched_fragment_ids.map((id) => <span key={id}>{id}</span>)}
                </div>
              </>
            ) : (
              <div className="runtime-proof-row"><span>Proof</span><strong>not loaded</strong></div>
            )}
            <p className="alignment-note">Deterministic public fixture only. Not autonomous web crawling or Cloud Brain self-growth.</p>
            {alignmentError ? <p className="seed-error">{alignmentError}</p> : null}
          </div>
        </aside>

        <section className="seed-panel seed-canvas" aria-label="Seed graph viewer">
          {viewer.edges.map((edge) => {
            const source = nodesById.get(edge.source);
            const target = nodesById.get(edge.target);
            if (!source || !target) return null;
            const sx = 50 + (Number(source.x ?? 0) * 8);
            const sy = 50 - (Number(source.y ?? 0) * 8);
            const tx = 50 + (Number(target.x ?? 0) * 8);
            const ty = 50 - (Number(target.y ?? 0) * 8);
            const dx = tx - sx;
            const dy = ty - sy;
            const length = Math.sqrt(dx * dx + dy * dy);
            const angle = Math.atan2(dy, dx) * 180 / Math.PI;
            return (
              <button
                key={edge.edge_id}
                className="seed-edge"
                style={{ left: `${sx}%`, top: `${sy}%`, width: `${length}%`, transform: `rotate(${angle}deg)` }}
                onClick={() => setSelectedEdgeId(edge.edge_id)}
                title={`${edge.source} ${edge.relation} ${edge.target}`}
              />
            );
          })}
          {viewer.nodes.map((node) => (
            <button
              key={node.id}
              className="seed-node"
              data-trust={node.trust_state}
              data-selected={selectedNodeId === node.id}
              style={{ left: `${50 + (Number(node.x ?? 0) * 8)}%`, top: `${50 - (Number(node.y ?? 0) * 8)}%` }}
              onClick={() => {
                setSelectedNodeId(node.id);
                setSelectedEdgeId(null);
              }}
              title={`${node.label} / ${node.labels?.ko ?? ""}`}
            />
          ))}
        </section>

        <aside className="seed-panel">
          <h2>Inspect</h2>
          <div className="seed-detail">
            {selectedEdge ? (
              <>
                <strong>{selectedEdge.relation}</strong>
                <span>{selectedEdge.source}</span>
                <span>{`-> ${selectedEdge.target}`}</span>
                <span>confidence {selectedEdge.confidence ?? 0}</span>
                <span>{selectedEdge.trust_state}</span>
              </>
            ) : selectedNode ? (
              <>
                <strong>{selectedNode.label}</strong>
                <span>{selectedNode.labels?.ko} / {selectedNode.labels?.en}</span>
                <span>{selectedNode.definition?.ko || selectedNode.definition?.en}</span>
                <span>{selectedNode.type}</span>
                <span>{selectedNode.trust_state} / {selectedNode.verification_state}</span>
                <span>aliases: {[...(selectedNode.aliases?.ko ?? []), ...(selectedNode.aliases?.en ?? [])].join(", ")}</span>
              </>
            ) : (
              <>
                <strong>Seed Research Viewer</strong>
                <span>Click a node or edge to inspect the generated seed artifact.</span>
                <span>Reads Local Brain: {String(viewer.local_brain_isolation?.reads_local_brain ?? false)}</span>
                <span>Writes Local Brain: {String(viewer.local_brain_isolation?.writes_local_brain ?? false)}</span>
              </>
            )}
          </div>
          <h2 style={{ marginTop: 22 }}>Concept Index</h2>
          <div className="seed-list">
            {viewer.nodes.slice(0, 64).map((node) => (
              <button key={node.id} onClick={() => setSelectedNodeId(node.id)}>
                {node.label} / {node.labels?.ko ?? node.id}
              </button>
            ))}
          </div>
        </aside>
      </section>
    </main>
  );
}

