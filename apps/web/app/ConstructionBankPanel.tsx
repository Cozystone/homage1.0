"use client";

import { useEffect, useState } from "react";

type AnyRecord = Record<string, any>;

const seedSources = [
  {
    source_type: "operator_example",
    language: "ko",
    route_type: "voice_status",
    act: "voice_question",
    text: "Fish 음성은 선택 기능입니다. 합성이 준비되지 않으면 텍스트 입력과 구슬 반응을 먼저 유지합니다.",
    source_refs: ["packages/voice_loop"],
    grounding_quality: "medium",
  },
  {
    source_type: "operator_example",
    language: "ko",
    route_type: "splatra_request",
    act: "open_chat",
    text: "SPLATRA 구슬 변경은 바로 적용하지 않고, 검토 가능한 UI 패치 후보로 남깁니다.",
    source_refs: ["apps/web/app/HologramVoiceOrb.tsx"],
    grounding_quality: "medium",
  },
  {
    source_type: "operator_example",
    language: "ko",
    route_type: "limitation_question",
    act: "open_chat",
    text: "ASM-v0는 일반 언어모델이 아닙니다. 검증된 근거와 construction 후보를 쓰되, 한계를 메타데이터로 남깁니다.",
    source_refs: ["packages/cgsr/cgsr/conversation_surface.py"],
    grounding_quality: "high",
  },
];

async function apiJson(path: string, init?: RequestInit): Promise<AnyRecord> {
  const response = await fetch(path, { ...init, cache: "no-store" });
  if (!response.ok) throw new Error(`HTTP ${response.status}`);
  return response.json();
}

export default function ConstructionBankPanel() {
  const [status, setStatus] = useState<AnyRecord | null>(null);
  const [candidates, setCandidates] = useState<AnyRecord[]>([]);
  const [retrieval, setRetrieval] = useState<AnyRecord | null>(null);
  const [compare, setCompare] = useState<AnyRecord | null>(null);
  const [comparePrompt, setComparePrompt] = useState("Fish2 소리 상태 알려줘");
  const [selectedId, setSelectedId] = useState("");
  const [message, setMessage] = useState("idle");

  async function refresh() {
    const [nextStatus, list] = await Promise.all([
      apiJson("/api/construction-bank/status"),
      apiJson("/api/construction-bank/candidates"),
    ]);
    setStatus(nextStatus);
    setCandidates(list.candidates ?? []);
    if (!selectedId && list.candidates?.[0]?.candidate_id) {
      setSelectedId(list.candidates[0].candidate_id);
    }
  }

  async function extractSeed() {
    const payload = await apiJson("/api/construction-bank/extract", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ sources: seedSources, store: true }),
    });
    setMessage(`extracted=${payload.extracted} stored=${payload.stored}`);
    await refresh();
  }

  async function previewRetrieve() {
    const payload = await apiJson("/api/construction-bank/retrieve", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({
        route_type: "voice_status",
        language: "ko",
        act: "voice_question",
        audience: "lab",
        mode: "lab",
      }),
    });
    setRetrieval(payload);
    setMessage(payload.self_grown_construction_used ? "using reviewed construction" : "preview or fallback");
  }

  async function comparePaths() {
    const payload = await apiJson("/api/construction-bank/compare", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ prompt: comparePrompt, mode: "lab" }),
    });
    setCompare(payload);
    setMessage(payload.metadata?.self_grown_construction_used ? "self-grown path selected" : "hand-authored fallback selected");
  }

  async function exportReview() {
    if (!selectedId) return;
    const payload = await apiJson("/api/construction-bank/export-review-item", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ candidate_id: selectedId }),
    });
    setMessage(`review item=${payload.review_item?.item_id ?? "created"}`);
    await refresh();
  }

  useEffect(() => {
    refresh().catch((error) => setMessage(error instanceof Error ? error.message : "refresh failed"));
  }, []);

  return (
    <article className="agentic-os-card agentic-os-review-card">
      <h3>Self-Grown Construction Bank</h3>
      <p>Proof-only candidate bank for ASM-v0 constructions. Product can use only safe promoted drafts; Lab can preview reviewed candidates.</p>
      <div className="agentic-os-flags">
        <span>total={String(status?.total_candidates ?? 0)}</span>
        <span>candidate={String(status?.by_status?.candidate ?? 0)}</span>
        <span>reviewed={String(status?.by_status?.reviewed ?? 0)}</span>
        <span>production_active={String(status?.production_active_count ?? 0)}</span>
      </div>
      <div className="agentic-os-actions">
        <button type="button" className="agentic-os-action" onClick={() => extractSeed()}>extract proof examples</button>
        <button type="button" className="agentic-os-action" onClick={() => previewRetrieve()}>preview retrieval</button>
        <button type="button" className="agentic-os-action" onClick={() => exportReview()} disabled={!selectedId}>send to Review Queue</button>
        <button type="button" className="agentic-os-action" onClick={() => refresh()}>refresh</button>
      </div>
      <label className="agentic-os-input-row">
        <span>compare prompt</span>
        <input value={comparePrompt} onChange={(event) => setComparePrompt(event.target.value)} />
        <button type="button" className="agentic-os-action" onClick={() => comparePaths()}>compare paths</button>
      </label>
      <p>{message}</p>
      <div className="agentic-os-review-list">
        {candidates.length === 0 ? <p>no construction candidates yet</p> : candidates.slice(0, 5).map((candidate) => (
          <button
            type="button"
            className="agentic-os-review-item"
            key={candidate.candidate_id}
            onClick={() => setSelectedId(candidate.candidate_id)}
            data-active={selectedId === candidate.candidate_id}
          >
            <div>
              <small>{candidate.source_type} · {candidate.route_type} · {candidate.status}</small>
              <strong>{candidate.construction_family}</strong>
              <p>{candidate.example_text}</p>
              <span>template={String(candidate.template_risk)} grounding={String(candidate.grounding_score)} natural={String(candidate.naturalness_score)}</span>
            </div>
          </button>
        ))}
      </div>
      {retrieval ? (
        <pre style={{ whiteSpace: "pre-wrap", maxHeight: 180, overflow: "auto" }}>
          {JSON.stringify({
            retrieved: retrieval.retrieved_self_grown_construction,
            used: retrieval.self_grown_construction_used,
            candidate: retrieval.construction_candidate_id,
            status: retrieval.candidate_status,
            reason: retrieval.activation_reason,
            rejection_reasons: retrieval.rejection_reasons,
            production_active: retrieval.production_active,
          }, null, 2)}
        </pre>
      ) : null}
      {compare ? (
        <div className="agentic-os-review-list">
          <strong>before / after preview</strong>
          <p><b>hand-authored:</b> {compare.hand_authored_answer ?? "abstain"}</p>
          <p><b>self-grown:</b> {compare.self_grown_candidate_answer ?? "not selected"}</p>
          <p><b>chosen:</b> {compare.chosen_answer ?? "abstain"}</p>
          <small>route={compare.route?.route_type} · reason={compare.metadata?.activation_reason} · rejected={(compare.rejection_reasons ?? []).join(", ") || "none"}</small>
        </div>
      ) : null}
    </article>
  );
}
