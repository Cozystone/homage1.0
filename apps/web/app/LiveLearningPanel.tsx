"use client";

import { useEffect, useRef, useState } from "react";
import { useCloudLearningMetrics } from "./useCloudLearningMetrics";

/**
 * Live view of the infinite cumulative-learning loop. Reads the SHARED cloud
 * learning metrics (one app-wide SSE/poll subscription — 난제 P4) and shows real,
 * measured growth — a toggle switches between the CONCEPT graph and the SURFACE
 * graph growth. No fabricated numbers: these are the loop's own per-tick added
 * counts.
 */

type Metrics = {
  running: boolean;
  uptime_seconds: number;
  ticks: number;
  sentences_fed: number;
  sentences_accepted: number;
  concepts_added: number;
  relations_added: number;
  surface_added: number;
  sentences_per_second: number;
  concepts_per_minute: number;
  accept_rate: number;
  last_titles: string[];
  last_error: string | null;
  source: string;
  firehose_per_second?: number;
  firehose_processed?: number;
  firehose_unique?: number;
  firehose_sources?: number;
  relation_checks_per_second?: number;
  corroborated_pairs?: number;
  corroborated_concepts?: number;
  relation_recent?: string[];
};

type View = "concept" | "surface";

export default function LiveLearningPanel({
  apiBase = "",
  view: controlledView,
  onViewChange,
}: {
  apiBase?: string;
  view?: View;
  onViewChange?: (view: View) => void;
}) {
  const m = (useCloudLearningMetrics() as Metrics | null) ?? null;
  const [internalView, setInternalView] = useState<View>("concept");
  const view = controlledView ?? internalView;
  const setView = (next: View) => {
    setInternalView(next);
    onViewChange?.(next);
  };
  const [series, setSeries] = useState<number[]>([]);
  const [loadPct, setLoadPct] = useState<number | null>(null);
  const prevRef = useRef<number>(0);

  // A determinate 0→100% bar that only appears while a *new* panel view is being
  // brought up (initial mount or a 개념↔Surface switch) — once it fills it hides,
  // so steady state shows no bar. Covers any blank gap on first paint.
  useEffect(() => {
    setLoadPct(0);
    let p = 0;
    const id = setInterval(() => {
      p = Math.min(100, p + 16 + Math.random() * 16);
      setLoadPct(p);
      if (p >= 100) {
        clearInterval(id);
        window.setTimeout(() => setLoadPct(null), 170);
      }
    }, 45);
    return () => clearInterval(id);
  }, [view]);

  // Reset the sparkline baseline whenever the view (concept↔surface) changes so the
  // delta series tracks the currently-selected metric.
  useEffect(() => {
    prevRef.current = 0;
    setSeries([]);
  }, [view]);

  // Append a per-update delta whenever the shared metrics change (no own polling —
  // the subscription in useCloudLearningMetrics is the single app-wide transport).
  useEffect(() => {
    if (!m) return;
    const total = view === "concept" ? m.concepts_added : m.surface_added;
    if (typeof total !== "number") return;
    const delta = Math.max(0, total - prevRef.current);
    prevRef.current = total;
    setSeries((s) => [...s.slice(-59), delta]);
  }, [m, view]);

  const primary = m ? (view === "concept" ? m.concepts_added : m.surface_added) : 0;
  const rate = m ? (view === "concept" ? m.concepts_per_minute : Math.round((m.surface_added / Math.max(1, m.uptime_seconds)) * 60)) : 0;
  const max = Math.max(1, ...series);

  return (
    <div className="atanor-livelearn">
      <div className="atanor-livelearn-head">
        <span className={`atanor-livelearn-dot${m?.running ? " is-live" : ""}`} />
        <strong>실시간 누적학습</strong>
        <span className="atanor-livelearn-status">{m?.running ? "LEARNING" : "paused"}</span>
        <div className="atanor-livelearn-toggle">
          <button data-active={view === "concept"} onClick={() => setView("concept")}>개념 그래프</button>
          <button data-active={view === "surface"} onClick={() => setView("surface")}>Surface 그래프</button>
        </div>
      </div>

      {loadPct !== null ? (
        <div className="atanor-livelearn-load" role="progressbar" aria-valuenow={Math.round(loadPct)} aria-valuemin={0} aria-valuemax={100} aria-label={`${view === "concept" ? "개념 그래프" : "Surface 그래프"} 로딩 ${Math.round(loadPct)}%`}>
          <i style={{ width: `${loadPct}%` }} />
        </div>
      ) : null}

      <div className="atanor-livelearn-big">
        <span className="atanor-livelearn-num">{primary.toLocaleString()}</span>
        <span className="atanor-livelearn-unit">{view === "concept" ? "개념 추가" : "construction 추가"} · +{rate}/분</span>
      </div>

      <div className="atanor-livelearn-spark" aria-hidden="true">
        {series.map((v, i) => (
          <i key={i} style={{ height: `${Math.round((v / max) * 100)}%` }} data-fresh={i === series.length - 1 && v > 0 ? "true" : "false"} />
        ))}
      </div>

      <div className="atanor-livelearn-grid">
        <div><b>{m?.sentences_fed.toLocaleString() ?? 0}</b><span>문장 투입</span></div>
        <div><b>{m ? `${Math.round(m.accept_rate * 100)}%` : "—"}</b><span>수용률</span></div>
        <div><b>{m?.relations_added.toLocaleString() ?? 0}</b><span>관계 추가</span></div>
        <div><b>{m?.sentences_per_second ?? 0}</b><span>문장/초</span></div>
      </div>
      <div className="atanor-livelearn-firehose">
        <span>발화 파이어호스</span>
        <b>{(m?.firehose_unique ?? 0).toLocaleString()}문장</b>
        <i>{m?.firehose_per_second ? `${m.firehose_per_second.toLocaleString()}/초` : "코퍼스 대기"}</i>
        <em>{(m?.relation_checks_per_second ?? 0).toLocaleString()} 관계 점검/초</em>
      </div>
      {((m?.corroborated_concepts ?? 0) > 0 || (m?.corroborated_pairs ?? 0) > 0) && (
        <div className="atanor-livelearn-corroboration">
          <span title="동일 개념이 2개 이상 독립 출처에서 확인된 수 — 교차출처 중복확인(팩트체킹 원리)">
            ✓ 다출처 확인 개념 <b>{(m?.corroborated_concepts ?? 0).toLocaleString()}</b>개
            {(m?.corroborated_pairs ?? 0) > 0 && (
              <> · 확인 연결 <b>{(m?.corroborated_pairs ?? 0).toLocaleString()}</b>쌍</>
            )}
          </span>
          {m?.relation_recent && m.relation_recent.some(r => r.startsWith("✓")) && (
            <ul className="atanor-livelearn-corr-recent">
              {m.relation_recent.filter(r => r.startsWith("✓")).slice(0, 3).map((r, i) => (
                <li key={i}>{r}</li>
              ))}
            </ul>
          )}
        </div>
      )}
      <div className="atanor-livelearn-foot">
        수집(발화)≠이해(개념) 분리 · 실제 공개 문장 · 가짜 성장 없음{m?.last_error ? ` · ${m.last_error}` : ""}
      </div>
    </div>
  );
}
