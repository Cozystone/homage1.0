"use client";

import { useMemo, useRef, useState } from "react";

/**
 * P5-⑪: the semantic-zoom answer-path view.
 *
 * ATANOR composes an answer from ontology-graph edges, so every answer carries a
 * reasoning_certificate whose `steps` ARE a small derivation graph: an anchor
 * concept → relation hops → target concepts. This renders that REAL graph (nothing
 * decorative or fabricated) with:
 *   - CSS-3D depth (perspective + tilt; drag to orbit) — light, no WebGL,
 *   - SEMANTIC ZOOM: the amount of detail shown scales with zoom. Far out you see
 *     just the anchor and how many grounding concepts it used; zoom in and the
 *     relation edges + labels appear; zoom in further and the anchor's grounding
 *     sentence + confidence surface. Different information at different scales, the
 *     way a map reveals streets as you zoom — not just a bigger picture.
 *
 * Honest contract: it only ever draws what the certificate actually contains. An
 * abstained/thin certificate shows an honest empty state, never invented nodes.
 */

type Cert = Record<string, unknown>;

type PathNode = {
  id: string;
  label: string;
  tier: 0 | 1 | 2;
  fact?: string;
};

type PathEdge = { from: string; to: string; relation: string };

function parseCertificate(cert: Cert): {
  kind: string;
  nodes: PathNode[];
  edges: PathEdge[];
  anchorFact: string;
  confidence: number;
  confidenceBasis: string;
} {
  const kind = String(cert.derivation_kind || "");
  const steps = Array.isArray(cert.steps) ? (cert.steps as Record<string, unknown>[]) : [];
  const anchor = (cert.anchor_concept as Record<string, unknown>) || {};
  const nodes = new Map<string, PathNode>();
  const edges: PathEdge[] = [];

  const anchorLabel = String(anchor.label || "");
  let anchorFact = "";
  const add = (label: string, tier: 0 | 1 | 2, fact?: string) => {
    const key = label.trim().toLowerCase();
    if (!key) return;
    if (!nodes.has(key)) nodes.set(key, { id: key, label, tier, fact });
    else if (fact && !nodes.get(key)!.fact) nodes.get(key)!.fact = fact;
  };

  for (const s of steps) {
    const type = String(s.type || "");
    if (type === "anchor_definition") {
      anchorFact = String(s.fact || "");
      add(String(s.label || anchorLabel), 0, anchorFact);
    } else if (type === "graph_relation") {
      const from = String(s.from || anchorLabel);
      const to = String(s.to || "");
      add(from, 0);
      if (to) {
        add(to, 1);
        edges.push({ from, to, relation: String(s.relation || "관련") });
      }
    } else if (type === "graph_relation_second_hop") {
      const from = String(s.from || "");
      const to = String(s.to || "");
      if (from) add(from, 1);
      if (to) {
        add(to, 2);
        edges.push({ from, to, relation: String(s.relation || "관련") });
      }
    }
  }
  // Ensure the anchor exists even for certs whose first step was dropped.
  if (anchorLabel) add(anchorLabel, 0, anchorFact);

  return {
    kind,
    nodes: Array.from(nodes.values()),
    edges,
    anchorFact,
    confidence: Number(cert.confidence || 0),
    confidenceBasis: String(cert.confidence_basis || ""),
  };
}

const W = 460;
const H = 300;
const CX = W / 2;
const CY = H / 2;

function layout(nodes: PathNode[]): Map<string, { x: number; y: number; z: number }> {
  const pos = new Map<string, { x: number; y: number; z: number }>();
  const tiers: Record<number, PathNode[]> = { 0: [], 1: [], 2: [] };
  for (const n of nodes) tiers[n.tier].push(n);
  // anchor(s) at centre; first hop on an inner ring; second hop on an outer ring.
  tiers[0].forEach((n, i) => {
    const a = (i / Math.max(1, tiers[0].length)) * Math.PI * 2;
    const r = tiers[0].length > 1 ? 34 : 0;
    pos.set(n.id, { x: CX + Math.cos(a) * r, y: CY + Math.sin(a) * r, z: 40 });
  });
  const ring = (list: PathNode[], radius: number, z: number, phase: number) => {
    list.forEach((n, i) => {
      const a = phase + (i / Math.max(1, list.length)) * Math.PI * 2;
      pos.set(n.id, { x: CX + Math.cos(a) * radius, y: CY + Math.sin(a) * radius, z });
    });
  };
  ring(tiers[1], 96, 0, -Math.PI / 2);
  ring(tiers[2], 138, -30, -Math.PI / 3);
  return pos;
}

export default function AnswerPathScene({ cert }: { cert: Cert }) {
  const parsed = useMemo(() => parseCertificate(cert), [cert]);
  const [zoom, setZoom] = useState(1);
  const [tilt, setTilt] = useState(18);
  const [spin, setSpin] = useState(0);
  const drag = useRef<{ x: number; y: number; spin: number; tilt: number } | null>(null);

  const pos = useMemo(() => layout(parsed.nodes), [parsed.nodes]);

  // Semantic-zoom level of detail.
  const showEdges = zoom >= 0.9;
  const showRelationLabels = zoom >= 1.35;
  const showFact = zoom >= 1.7;
  const showSecondHop = zoom >= 1.1;

  const groundingCount = parsed.nodes.filter((n) => n.tier > 0).length;
  const isThin = parsed.nodes.length <= 1 || parsed.kind === "abstained";

  const onWheel = (e: React.WheelEvent) => {
    e.preventDefault();
    setZoom((z) => Math.min(2.4, Math.max(0.6, z - e.deltaY * 0.0016)));
  };
  const onDown = (e: React.MouseEvent) => {
    drag.current = { x: e.clientX, y: e.clientY, spin, tilt };
  };
  const onMove = (e: React.MouseEvent) => {
    if (!drag.current) return;
    setSpin(drag.current.spin + (e.clientX - drag.current.x) * 0.4);
    setTilt(Math.min(52, Math.max(-8, drag.current.tilt - (e.clientY - drag.current.y) * 0.25)));
  };
  const onUp = () => {
    drag.current = null;
  };

  if (isThin) {
    return (
      <div className="atanor-answerpath is-thin">
        <span className="atanor-answerpath-thin-icon">◍</span>
        <span>
          {parsed.kind === "abstained" || !parsed.kind
            ? "이 답변은 확정 근거가 없어 보류했어요 — 그릴 파생 경로가 없습니다."
            : parsed.kind.startsWith("web")
              ? "웹 출처 기반 답변 — 그래프 파생 경로 대신 인용 출처로 근거를 표시합니다."
              : "그래프 파생 경로가 없는 답변입니다."}
        </span>
      </div>
    );
  }

  const visibleNodes = parsed.nodes.filter((n) => n.tier < 2 || showSecondHop);
  const visibleIds = new Set(visibleNodes.map((n) => n.id));
  const visibleEdges = showEdges
    ? parsed.edges.filter((e) => {
        const f = e.from.trim().toLowerCase();
        const t = e.to.trim().toLowerCase();
        return visibleIds.has(f) && visibleIds.has(t);
      })
    : [];

  return (
    <div className="atanor-answerpath">
      <div className="atanor-answerpath-head">
        <span className="atanor-answerpath-title">근거 경로</span>
        <span className="atanor-answerpath-meta">
          그래프 파생 · 근거 개념 {groundingCount}개 · 신뢰도 {Math.round(parsed.confidence * 100)}%
        </span>
      </div>
      <div
        className="atanor-answerpath-stage"
        onWheel={onWheel}
        onMouseDown={onDown}
        onMouseMove={onMove}
        onMouseUp={onUp}
        onMouseLeave={onUp}
        role="img"
        aria-label={`근거 경로: 앵커 개념에서 ${groundingCount}개 근거 개념으로 이어지는 그래프 파생`}
      >
        <div
          className="atanor-answerpath-space"
          style={{ transform: `perspective(720px) rotateX(${tilt}deg) rotateZ(${spin * 0.15}deg) scale(${zoom})` }}
        >
          <svg viewBox={`0 0 ${W} ${H}`} width="100%" height="100%">
            {visibleEdges.map((e, i) => {
              const a = pos.get(e.from.trim().toLowerCase());
              const b = pos.get(e.to.trim().toLowerCase());
              if (!a || !b) return null;
              const mx = (a.x + b.x) / 2;
              const my = (a.y + b.y) / 2;
              return (
                <g key={`e${i}`} className="atanor-answerpath-edge">
                  <line x1={a.x} y1={a.y} x2={b.x} y2={b.y} />
                  {showRelationLabels ? (
                    <text x={mx} y={my - 3} textAnchor="middle" className="atanor-answerpath-rel">
                      {e.relation}
                    </text>
                  ) : null}
                </g>
              );
            })}
            {visibleNodes.map((n) => {
              const p = pos.get(n.id);
              if (!p) return null;
              const r = n.tier === 0 ? 13 : n.tier === 1 ? 9 : 7;
              return (
                <g key={n.id} className={`atanor-answerpath-node tier-${n.tier}`}>
                  <circle cx={p.x} cy={p.y} r={r} />
                  <text x={p.x} y={p.y + r + 12} textAnchor="middle">
                    {n.label.length > 14 ? `${n.label.slice(0, 14)}…` : n.label}
                  </text>
                </g>
              );
            })}
          </svg>
        </div>
        {showFact && parsed.anchorFact ? (
          <div className="atanor-answerpath-fact">
            <b>앵커 근거</b> {parsed.anchorFact.length > 120 ? `${parsed.anchorFact.slice(0, 120)}…` : parsed.anchorFact}
          </div>
        ) : null}
      </div>
      <div className="atanor-answerpath-foot">
        <input
          type="range"
          min={0.6}
          max={2.4}
          step={0.05}
          value={zoom}
          onChange={(e) => setZoom(Number(e.target.value))}
          aria-label="시맨틱 줌"
        />
        <span className="atanor-answerpath-hint">
          {zoom < 0.9
            ? "멀리서 보기 — 앵커 개념"
            : zoom < 1.35
              ? "관계 엣지"
              : zoom < 1.7
                ? "관계 라벨 + 2차 홉"
                : "앵커 근거 문장 + 상세"}
          {" · 스크롤=줌, 드래그=회전"}
        </span>
      </div>
    </div>
  );
}
