"use client";

/**
 * Experimental answer-interface surface.
 *
 * The engine attaches an `answer_visual` to math / geometry answers, and this
 * component renders the matching interface — a formula card, or a GeoGebra-like
 * labeled figure. The mapping (registry_hint → renderer) is intentionally
 * data-driven so ATANOR can later add its own kinds: a new `kind` here + a new
 * `answer_visual` from the engine is all it takes to teach the agent a new way
 * to answer a class of question.
 */

export type AnswerVisual = {
  kind: "formula" | "geometry_figure" | "function_plot" | string;
  title?: string;
  formula?: string;
  registry_hint?: string;
  // geometry_figure only:
  shape?: "square" | "rectangle" | "circle" | "triangle" | string;
  params?: Record<string, number>;
  metric?: "perimeter" | "area" | string;
  result?: number;
  // function_plot only:
  expr?: string;
  domain?: [number, number];
  points?: [number, number][];
};

export type SurfaceTheme = "dark" | "light";

type Palette = { accent: string; ink: string; dim: string; fill: string; grid: string };

function palette(theme: SurfaceTheme): Palette {
  return theme === "light"
    ? { accent: "#2563eb", ink: "#1d2330", dim: "#6b7280", fill: "rgba(37, 99, 235, 0.08)", grid: "rgba(37, 99, 235, 0.12)" }
    : { accent: "#7db4ff", ink: "#dbe6ff", dim: "#8aa0c8", fill: "rgba(125, 180, 255, 0.12)", grid: "rgba(125, 180, 255, 0.14)" };
}

function fmt(n: number | undefined): string {
  if (n === undefined || Number.isNaN(n)) return "";
  return Math.abs(n - Math.round(n)) < 1e-9 ? String(Math.round(n)) : String(Math.round(n * 100) / 100);
}

function GeometryFigure({ v, pal }: { v: AnswerVisual; pal: Palette }) {
  const { accent: ACCENT, ink: INK, dim: DIM, fill: FILL } = pal;
  const p = v.params ?? {};
  const W = 260;
  const H = 210; // extra vertical room so the top dimension label isn't clipped
  let svg: React.ReactNode = null;

  if (v.shape === "square" || v.shape === "rectangle") {
    const w = p.side ?? p.width ?? 1;
    const h = p.side ?? p.height ?? w;
    const scale = Math.min(130 / Math.max(w, h), 50);
    const bw = Math.max(40, w * scale);
    const bh = Math.max(30, h * scale);
    const x = (W - bw) / 2;
    const y = (H - bh) / 2;
    svg = (
      <>
        <rect x={x} y={y} width={bw} height={bh} fill={FILL} stroke={ACCENT} strokeWidth={2} rx={3} />
        <text x={x + bw / 2} y={y - 8} fill={INK} fontSize={13} textAnchor="middle">{fmt(w)}</text>
        <text x={x - 10} y={y + bh / 2} fill={INK} fontSize={13} textAnchor="end" dominantBaseline="middle">{fmt(h)}</text>
      </>
    );
  } else if (v.shape === "circle") {
    const r = p.radius ?? 1;
    const rr = Math.min(70, Math.max(34, r * 12));
    const cx = W / 2;
    const cy = H / 2;
    svg = (
      <>
        <circle cx={cx} cy={cy} r={rr} fill={FILL} stroke={ACCENT} strokeWidth={2} />
        <line x1={cx} y1={cy} x2={cx + rr} y2={cy} stroke={ACCENT} strokeWidth={1.5} strokeDasharray="3 3" />
        <circle cx={cx} cy={cy} r={2.5} fill={ACCENT} />
        <text x={cx + rr / 2} y={cy - 6} fill={INK} fontSize={12} textAnchor="middle">r = {fmt(r)}</text>
      </>
    );
  } else if (v.shape === "triangle") {
    const b = p.base ?? 1;
    const h = p.height ?? 1;
    const scale = Math.min(150 / Math.max(b, h), 50);
    const bw = Math.max(50, b * scale);
    const bh = Math.max(40, h * scale);
    const x0 = (W - bw) / 2;
    const yb = (H + bh) / 2;
    const apex = x0 + bw / 2;
    svg = (
      <>
        <polygon points={`${x0},${yb} ${x0 + bw},${yb} ${apex},${yb - bh}`} fill={FILL} stroke={ACCENT} strokeWidth={2} />
        <line x1={apex} y1={yb} x2={apex} y2={yb - bh} stroke={ACCENT} strokeWidth={1} strokeDasharray="3 3" />
        <text x={x0 + bw / 2} y={yb + 16} fill={INK} fontSize={12} textAnchor="middle">밑변 {fmt(b)}</text>
        <text x={apex + 8} y={yb - bh / 2} fill={DIM} fontSize={12}>높이 {fmt(h)}</text>
      </>
    );
  }

  return (
    <svg viewBox={`0 0 ${W} ${H}`} width="100%" style={{ maxWidth: 300, display: "block", margin: "0 auto" }}>
      {svg}
    </svg>
  );
}

function FunctionPlot({ v, pal }: { v: AnswerVisual; pal: Palette }) {
  const { accent: ACCENT, dim: DIM, grid: GRID } = pal;
  const pts = v.points ?? [];
  const W = 300;
  const H = 200;
  const pad = 24;
  if (pts.length < 2) return null;
  const xs = pts.map((p) => p[0]);
  const ys = pts.map((p) => p[1]);
  const xmin = Math.min(...xs);
  const xmax = Math.max(...xs);
  let ymin = Math.min(...ys);
  let ymax = Math.max(...ys);
  if (ymin === ymax) { ymin -= 1; ymax += 1; }
  const sx = (x: number) => pad + ((x - xmin) / (xmax - xmin || 1)) * (W - 2 * pad);
  const sy = (y: number) => H - pad - ((y - ymin) / (ymax - ymin || 1)) * (H - 2 * pad);
  const path = pts.map((p, i) => `${i === 0 ? "M" : "L"}${sx(p[0]).toFixed(1)},${sy(p[1]).toFixed(1)}`).join(" ");
  const x0 = xmin <= 0 && xmax >= 0 ? sx(0) : null; // y-axis if 0 in domain
  const y0 = ymin <= 0 && ymax >= 0 ? sy(0) : null; // x-axis if 0 in range
  return (
    <svg viewBox={`0 0 ${W} ${H}`} width="100%" style={{ maxWidth: 320, display: "block", margin: "0 auto" }}>
      <rect x={pad} y={pad} width={W - 2 * pad} height={H - 2 * pad} fill="none" stroke={GRID} />
      {[0.25, 0.5, 0.75].map((t) => (
        <line key={`gx${t}`} x1={pad + t * (W - 2 * pad)} y1={pad} x2={pad + t * (W - 2 * pad)} y2={H - pad} stroke={GRID} opacity={0.5} />
      ))}
      {[0.25, 0.5, 0.75].map((t) => (
        <line key={`gy${t}`} x1={pad} y1={pad + t * (H - 2 * pad)} x2={W - pad} y2={pad + t * (H - 2 * pad)} stroke={GRID} opacity={0.5} />
      ))}
      {y0 !== null ? <line x1={pad} y1={y0} x2={W - pad} y2={y0} stroke={DIM} strokeWidth={1} /> : null}
      {x0 !== null ? <line x1={x0} y1={pad} x2={x0} y2={H - pad} stroke={DIM} strokeWidth={1} /> : null}
      <path d={path} fill="none" stroke={ACCENT} strokeWidth={2} strokeLinejoin="round" strokeLinecap="round" />
      <text x={pad} y={H - 6} fill={DIM} fontSize={10}>{fmt(xmin)}</text>
      <text x={W - pad} y={H - 6} fill={DIM} fontSize={10} textAnchor="end">{fmt(xmax)}</text>
    </svg>
  );
}

export default function AnswerExperimentSurface({ visual, theme = "dark" }: { visual: AnswerVisual; theme?: SurfaceTheme }) {
  const isGeo = visual.kind === "geometry_figure";
  const isPlot = visual.kind === "function_plot";
  const fallbackTitle = isGeo ? "도형" : isPlot ? "함수 그래프" : "수식";
  const pal = palette(theme);
  return (
    <div className="atanor-answer-experiment" data-kind={visual.kind} data-theme={theme}>
      <div className="atanor-answer-experiment-head">
        <span className="atanor-answer-experiment-dot" />
        <span>{visual.title || fallbackTitle}</span>
        {visual.registry_hint ? <code className="atanor-answer-experiment-hint">{visual.registry_hint}</code> : null}
      </div>
      {isGeo ? <GeometryFigure v={visual} pal={pal} /> : null}
      {isPlot ? <FunctionPlot v={visual} pal={pal} /> : null}
      {visual.formula ? <div className="atanor-answer-experiment-formula">{visual.formula}</div> : null}
    </div>
  );
}
