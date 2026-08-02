"use client";

import { useState } from "react";
import AnswerPathScene from "./AnswerPathScene";

/** 사고과정 투명 뷰 — the reasoning certificate rendered the way people read
 * thinking (owner directive 2026-07-08): what path was taken → what was
 * consulted (clickable links) → why this answer, as a step stream instead of
 * a graph render. Honest by construction: only fields the certificate really
 * carries are shown; nothing is narrated that did not happen. The graph view
 * stays available behind a secondary toggle. */

type Cert = Record<string, unknown>;

const KIND_KO: Record<string, string> = {
  web_search_grounding: "웹 검색에서 근거를 찾아 답했습니다",
  web_attribution_extraction: "웹 문서에서 귀속 정보(인물·창작자)를 추출했습니다",
  web_no_relevant_source: "웹에서 이 주제를 정면으로 다루는 근거를 찾지 못해 추측하지 않았습니다",
  web_unreachable: "웹에 연결하지 못해 로컬 지식 범위에서만 판단했습니다",
  conversation_control: "대화 제어 지시로 처리했습니다",
  user_model_aggregation: "이 기기에 저장된 사용자 기록에서 집계했습니다",
  learning_ledger_introspection: "실시간 학습 원장을 직접 읽었습니다",
  graph_traversal: "지식 그래프의 근거 경로를 따라 답을 구성했습니다",
  curated_kg: "큐레이션 지식그래프에서 조회했습니다",
  base_brain: "기본 지식 그래프에서 답을 구성했습니다",
  deterministic_chained_reasoning: "결정론적 연쇄 추론으로 그래프를 단계별로 따라갔습니다",
  ontology_graph_derivation: "온톨로지 그래프에서 근거 경로를 활성화해 답했습니다",
};

const STEP_KO: Record<string, string> = {
  web_source: "참고 문서",
  web_status: "웹 상태",
  web_relevance_gate: "관련성 게이트",
  web_attribution: "귀속 추출",
  control: "제어 판단",
  aggregate: "로컬 집계",
  kg_lookup: "그래프 조회",
  relation: "관계 추적",
  inference: "추론 단계",
  retrieve: "지식 조회",
  chain: "연쇄 추론",
};

const GUARANTEE_KO: Array<[string, boolean, string]> = [
  ["external_llm", false, "외부 LLM 0회"],
  ["fabricated_facts", false, "지어낸 사실 없음"],
  ["source_cited", true, "출처 인용"],
  ["evidence_grounded", true, "근거 기반"],
  ["off_topic_source_used", false, "무관 문서 배제"],
  ["grafted_to_brain", false, "미검증 지식 미주입"],
];

const INK = "#1b1b1b";
const GRAY = "#8a8a8a";
const HAIR = "#e7e5e2";
const ACC = "#d2521f";

function asUrl(s: unknown): string | null {
  const t = String(s ?? "");
  return /^https?:\/\//.test(t) ? t : null;
}

/** The concept labels the answer actually walked, in order — anchor first,
 * then subjects/objects parsed from chained-step facts ("대한민국: 수도=서울특별시"),
 * then evidence concepts. Feeds the cloud graph's synapse-trace replay. */
function traceHref(cert: Cert, anchorLabel: string): string {
  const labels: string[] = [];
  const push = (value: unknown) => {
    const t = String(value ?? "").trim();
    if (t && t.length <= 40 && !/^https?:/.test(t) && !labels.includes(t)) labels.push(t);
  };
  push(anchorLabel);
  const steps = Array.isArray(cert.steps) ? (cert.steps as Array<Record<string, unknown>>) : [];
  for (const step of steps) {
    const m = /^([^:=]{1,30}):\s*([^=]{1,30})=(.{1,40})$/.exec(String(step.fact ?? "").trim());
    if (m) {
      push(m[1]);
      push(m[3]);
    }
  }
  for (const concept of (Array.isArray(cert.evidence_concepts) ? (cert.evidence_concepts as unknown[]) : [])) push(concept);
  return `/?section=cloud${labels.length ? `&trace=${encodeURIComponent(labels.slice(0, 6).join(","))}` : ""}`;
}

export default function ThinkingTrace({ cert }: { cert: Cert }) {
  const [showGraph, setShowGraph] = useState(false);
  const kind = String(cert.derivation_kind ?? "");
  const kindLabel = KIND_KO[kind] ?? (kind ? `경로: ${kind}` : "");
  const anchor = (cert.anchor_concept ?? null) as { id?: string; label?: string } | null;
  const steps = Array.isArray(cert.steps) ? (cert.steps as Array<Record<string, unknown>>) : [];
  const confidence = typeof cert.confidence === "number" ? Math.round((cert.confidence as number) * 100) : null;
  const basis = String(cert.confidence_basis ?? "");
  const guarantees = (cert.guarantees ?? {}) as Record<string, unknown>;
  const chips = GUARANTEE_KO.filter(([key, expect]) => guarantees[key] === expect).map(([, , label]) => label);

  return (
    <div style={{ marginTop: 8, border: `1px solid ${HAIR}`, borderRadius: 10, padding: "12px 14px", background: "#fbfaf8" }}>
      {kindLabel ? (
        <div style={{ fontSize: 12.5, color: INK, fontWeight: 600, marginBottom: steps.length ? 8 : 0 }}>{kindLabel}</div>
      ) : null}
      {anchor?.label ? (
        <div style={{ fontSize: 11.5, color: GRAY, marginBottom: 8 }}>
          중심 개념&nbsp;
          <span style={{ color: INK, fontWeight: 600 }}>{String(anchor.label)}</span>
          &nbsp;·&nbsp;
          <a href={traceHref(cert, String(anchor.label))} style={{ color: ACC, textDecoration: "none" }}>그래프에서 보기 →</a>
        </div>
      ) : null}
      {steps.length ? (
        <ol style={{ listStyle: "none", margin: 0, padding: 0 }}>
          {steps.map((step, i) => {
            const type = String(step.type ?? "");
            const label = STEP_KO[type] ?? type;
            const fact = String(step.fact ?? "");
            const url = asUrl(step.source);
            return (
              <li key={i} style={{ display: "flex", gap: 10, padding: "5px 0", borderTop: i ? `1px solid ${HAIR}` : "none" }}>
                <span style={{ color: GRAY, fontSize: 11, minWidth: 64, paddingTop: 1 }}>{label}</span>
                <span style={{ fontSize: 12, color: INK, lineHeight: 1.55, flex: 1 }}>
                  {fact}
                  {url ? (
                    <>
                      {fact ? " " : null}
                      <a href={url} target="_blank" rel="noreferrer" style={{ color: ACC, textDecoration: "none", wordBreak: "break-all" }}>
                        {new URL(url).hostname.replace(/^www\./, "")} ↗
                      </a>
                    </>
                  ) : null}
                </span>
              </li>
            );
          })}
        </ol>
      ) : null}
      <div style={{ display: "flex", flexWrap: "wrap", alignItems: "center", gap: 6, marginTop: 10 }}>
        {confidence !== null ? (
          <span style={{ fontSize: 11, color: GRAY }}>확신도 {confidence}%{basis ? ` · ${basis}` : ""}</span>
        ) : null}
        {chips.map((c) => (
          <span key={c} style={{ fontSize: 10.5, color: GRAY, border: `1px solid ${HAIR}`, borderRadius: 999, padding: "1px 8px" }}>{c}</span>
        ))}
        <button
          type="button"
          onClick={() => setShowGraph((v) => !v)}
          style={{ marginLeft: "auto", background: "transparent", border: "none", color: GRAY, fontSize: 11, cursor: "pointer", padding: 0 }}
        >
          {showGraph ? "그래프 뷰 접기" : "그래프 뷰"}
        </button>
      </div>
      {showGraph ? <AnswerPathScene cert={cert} /> : null}
    </div>
  );
}
