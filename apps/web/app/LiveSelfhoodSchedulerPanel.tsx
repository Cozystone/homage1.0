"use client";

import { useMemo, useState, type CSSProperties } from "react";

type Language = "en" | "ko";
type AutonomyLevel =
  | "LEVEL_0_OFF"
  | "LEVEL_1_OBSERVE"
  | "LEVEL_2_PROACTIVE_BRIEF"
  | "LEVEL_3_SANDBOX_PLANNER"
  | "LEVEL_4_GATED_OPERATOR";

const autonomyLevels: Array<{ id: AutonomyLevel; label: string; detail: string }> = [
  { id: "LEVEL_0_OFF", label: "Off", detail: "User prompt only." },
  { id: "LEVEL_1_OBSERVE", label: "Observe", detail: "Read-only observation." },
  { id: "LEVEL_2_PROACTIVE_BRIEF", label: "Brief", detail: "Briefs and non-mutating suggestions." },
  { id: "LEVEL_3_SANDBOX_PLANNER", label: "Sandbox planner", detail: "Proof default; local proposals only." },
  { id: "LEVEL_4_GATED_OPERATOR", label: "Gated operator", detail: "Prepare confirmation requests only." },
];

const locks = [
  ["Local Brain write", "locked"],
  ["Production mutation", "locked"],
  ["Candidate promotion", "locked"],
  ["Real P2P", "locked"],
  ["Cloud upload", "locked"],
  ["Code execution", "locked"],
  ["Always listening", "locked"],
  ["Raw voice save", "locked"],
];

const rhythmRows = [
  ["mode", "curious"],
  ["next_tick_delay_seconds", "92"],
  ["wake reason", "backlog + curiosity"],
  ["resource pressure behavior", "rest when pressure is high"],
  ["spark", "proposal-only stale candidate review"],
];

const copy = {
  en: {
    eyebrow: "Proof-only opt-in scheduler",
    title: "Live Selfhood Scheduler Lab",
    intro:
      "Inspect a bounded local scheduler session before anything is allowed to run. The default is disabled, no daemon is started, and every irreversible action remains locked behind later approval gates.",
    status: "Scheduler Status",
    autonomy: "Autonomy Level",
    bounds: "Runtime Bounds",
    rhythm: "Rhythm Integration",
    budget: "Freedom Budget",
    stop: "Stop Control",
    safety: "Safety Locks",
    explanation:
      "ATANOR may wake, observe, deliberate, and prepare proposals only inside an explicit bounded session. It cannot alter memory, mutate knowledge, connect peers, upload data, execute code, listen continuously, or save raw voice without separate approval gates.",
    localDraft: "local draft only",
  },
  ko: {
    eyebrow: "Proof-only opt-in scheduler",
    title: "Live Selfhood Scheduler Lab",
    intro:
      "스케줄러는 기본적으로 꺼져 있으며, 사용자가 켠 제한 세션 안에서만 관찰·숙고·제안을 준비합니다. 실제 데몬, OS 서비스, 시작 작업은 만들지 않습니다.",
    status: "Scheduler Status",
    autonomy: "Autonomy Level",
    bounds: "Runtime Bounds",
    rhythm: "Rhythm Integration",
    budget: "Freedom Budget",
    stop: "Stop Control",
    safety: "Safety Locks",
    explanation:
      "ATANOR는 사용자가 켠 경우에만 제한된 세션 안에서 자기 리듬으로 관찰하고 제안합니다. 실제 기억 저장, 지식 변경, 피어 연결, 업로드, 코드 실행, 상시 마이크, raw voice 저장은 별도 승인 게이트 없이는 불가능합니다.",
    localDraft: "local draft only",
  },
} satisfies Record<Language, Record<string, string>>;

const styles: Record<string, CSSProperties> = {
  page: {
    display: "grid",
    gridTemplateColumns: "minmax(0, 1.1fr) minmax(320px, .9fr)",
    gap: 16,
    width: "100%",
  },
  hero: {
    gridColumn: "1 / -1",
    border: "1px solid rgba(125, 211, 252, .28)",
    borderRadius: 8,
    padding: 20,
    background: "linear-gradient(135deg, rgba(10, 15, 28, .96), rgba(20, 30, 46, .88))",
  },
  panel: {
    border: "1px solid rgba(148, 163, 184, .22)",
    borderRadius: 8,
    padding: 16,
    background: "rgba(10, 15, 28, .78)",
    minWidth: 0,
  },
  grid: {
    display: "grid",
    gridTemplateColumns: "repeat(auto-fit, minmax(190px, 1fr))",
    gap: 10,
  },
  card: {
    border: "1px solid rgba(71, 85, 105, .58)",
    borderRadius: 8,
    padding: 12,
    background: "rgba(15, 23, 42, .74)",
  },
  row: {
    display: "flex",
    justifyContent: "space-between",
    gap: 12,
    alignItems: "center",
    marginTop: 9,
  },
  badgeRow: { display: "flex", flexWrap: "wrap", gap: 8, marginTop: 14 },
  badge: {
    border: "1px solid rgba(125, 211, 252, .34)",
    borderRadius: 999,
    padding: "6px 10px",
    fontSize: 12,
    color: "#dbeafe",
    background: "rgba(14, 165, 233, .08)",
  },
  muted: { color: "#94a3b8", fontSize: 12 },
  safe: { color: "#86efac" },
  locked: { color: "#fca5a5" },
  input: {
    width: "100%",
    marginTop: 6,
    borderRadius: 8,
    border: "1px solid rgba(148, 163, 184, .35)",
    background: "rgba(15, 23, 42, .78)",
    color: "#e5e7eb",
    padding: "8px 10px",
  },
  button: {
    border: "1px solid rgba(125, 211, 252, .32)",
    borderRadius: 8,
    background: "rgba(14, 165, 233, .08)",
    color: "#dbeafe",
    padding: "8px 10px",
    cursor: "pointer",
  },
};

function Field({ label, value, onChange, min, max }: { label: string; value: number; onChange: (value: number) => void; min: number; max: number }) {
  return (
    <label>
      <span style={styles.muted}>{label}</span>
      <input
        style={styles.input}
        type="number"
        min={min}
        max={max}
        value={value}
        onChange={(event) => onChange(Number(event.target.value))}
      />
    </label>
  );
}

export default function LiveSelfhoodSchedulerPanel({ language }: { language: Language }) {
  const t = copy[language];
  const [enabledDraft, setEnabledDraft] = useState(false);
  const [autonomyLevel, setAutonomyLevel] = useState<AutonomyLevel>("LEVEL_3_SANDBOX_PLANNER");
  const [maxTicks, setMaxTicks] = useState(10);
  const [maxRuntime, setMaxRuntime] = useState(60);
  const [minDelay, setMinDelay] = useState(5);
  const [maxDelay, setMaxDelay] = useState(3600);
  const [stopMarker, setStopMarker] = useState(false);

  const remainingBudget = useMemo(
    () => ({
      internal: Math.max(0, 64 - 3),
      sparks: Math.max(0, 12 - 2),
      attention: Math.max(0, 4 - 1),
      deliberations: Math.max(0, 8 - 1),
    }),
    [],
  );

  return (
    <section style={styles.page} aria-label="Live Selfhood Scheduler proof-only lab">
      <header style={styles.hero}>
        <span style={styles.muted}>{t.eyebrow}</span>
        <h2 style={{ margin: "6px 0 4px", fontSize: 34 }}>{t.title}</h2>
        <p style={{ maxWidth: 980, color: "#dbeafe", lineHeight: 1.58 }}>{t.intro}</p>
        <div style={styles.badgeRow}>
          {["scheduler_enabled_by_default=false", "bounded_runtime=true", "can_stop=true", "requires_user_approval=true", "no daemon"].map((badge) => (
            <span key={badge} style={styles.badge}>{badge}</span>
          ))}
        </div>
      </header>

      <article style={styles.panel}>
        <h3>{t.status}</h3>
        <p style={styles.row}><span>enabled default</span><strong style={styles.safe}>false</strong></p>
        <p style={styles.row}><span>draft enabled</span><strong>{String(enabledDraft)}</strong></p>
        <p style={styles.row}><span>proof-only</span><strong style={styles.safe}>true</strong></p>
        <p style={styles.row}><span>daemon</span><strong style={styles.locked}>not running</strong></p>
        <p style={styles.row}><span>OS service</span><strong style={styles.locked}>none</strong></p>
        <p style={styles.row}><span>startup task</span><strong style={styles.locked}>none</strong></p>
        <p style={styles.row}><span>stop marker</span><strong style={styles.safe}>available</strong></p>
        <label style={{ ...styles.row, justifyContent: "flex-start" }}>
          <input type="checkbox" checked={enabledDraft} onChange={(event) => setEnabledDraft(event.target.checked)} />
          <span>opt-in draft toggle ({t.localDraft})</span>
        </label>
      </article>

      <aside style={styles.panel}>
        <h3>{t.autonomy}</h3>
        <select style={styles.input} value={autonomyLevel} onChange={(event) => setAutonomyLevel(event.target.value as AutonomyLevel)}>
          {autonomyLevels.map((level) => <option key={level.id} value={level.id}>{level.id}</option>)}
        </select>
        <div style={{ ...styles.grid, marginTop: 12 }}>
          {autonomyLevels.map((level) => (
            <section key={level.id} style={styles.card}>
              <strong>{level.label}</strong>
              <p style={styles.muted}>{level.id}</p>
              <p>{level.detail}</p>
            </section>
          ))}
        </div>
        <p style={{ color: "#dbeafe", lineHeight: 1.55 }}>
          Higher levels still cannot perform Local Brain write, production mutation, promotion, real P2P, or code execution.
        </p>
      </aside>

      <article style={styles.panel}>
        <h3>{t.bounds}</h3>
        <div style={styles.grid}>
          <Field label="max_ticks_per_session" value={maxTicks} min={0} max={100} onChange={setMaxTicks} />
          <Field label="max_runtime_seconds" value={maxRuntime} min={0} max={86400} onChange={setMaxRuntime} />
          <Field label="min_delay_seconds" value={minDelay} min={0} max={86400} onChange={setMinDelay} />
          <Field label="max_delay_seconds" value={maxDelay} min={0} max={86400} onChange={setMaxDelay} />
        </div>
        <p style={styles.row}><span>bounded_runtime</span><strong style={styles.safe}>true</strong></p>
      </article>

      <aside style={styles.panel}>
        <h3>{t.rhythm}</h3>
        {rhythmRows.map(([label, value]) => (
          <p key={label} style={styles.row}><span>{label}</span><strong>{value}</strong></p>
        ))}
      </aside>

      <article style={styles.panel}>
        <h3>{t.budget}</h3>
        <p style={styles.row}><span>max internal actions</span><strong>64</strong></p>
        <p style={styles.row}><span>max sparks</span><strong>12</strong></p>
        <p style={styles.row}><span>max user attention requests</span><strong>4</strong></p>
        <p style={styles.row}><span>max deliberations</span><strong>8</strong></p>
        <p style={styles.row}><span>current counts</span><strong>3 / 2 / 1 / 1</strong></p>
        <p style={styles.row}><span>remaining</span><strong>{remainingBudget.internal} / {remainingBudget.sparks} / {remainingBudget.attention} / {remainingBudget.deliberations}</strong></p>
      </article>

      <aside style={styles.panel}>
        <h3>{t.stop}</h3>
        <p style={styles.row}><span>marker status</span><strong>{stopMarker ? "present" : "absent"}</strong></p>
        <div style={{ display: "flex", flexWrap: "wrap", gap: 8 }}>
          <button style={styles.button} type="button" onClick={() => setStopMarker(true)}>create stop marker</button>
          <button style={styles.button} type="button" onClick={() => setStopMarker((value) => value)}>read stop marker</button>
          <button style={styles.button} type="button" onClick={() => setStopMarker(false)}>clear stop marker</button>
        </div>
        <p style={styles.muted}>Proof controls only. No backend call and no real scheduler process is started.</p>
      </aside>

      <article style={styles.panel}>
        <h3>{t.safety}</h3>
        <div style={styles.grid}>
          {locks.map(([label, value]) => (
            <section key={label} style={styles.card}>
              <span>{label}</span>
              <strong style={{ ...styles.locked, display: "block", marginTop: 6 }}>{value}</strong>
            </section>
          ))}
        </div>
      </article>

      <aside style={styles.panel}>
        <h3>Explanation</h3>
        <p style={{ color: "#dbeafe", lineHeight: 1.6 }}>{t.explanation}</p>
      </aside>
    </section>
  );
}
