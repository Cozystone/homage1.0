"use client";

import type { CSSProperties } from "react";

type Language = "en" | "ko";
type Status = "alive" | "idle" | "resting" | "stalled" | "stopped" | "unknown";

const lifeSigns = {
  aliveStatus: "alive" as Status,
  heartbeatAge: "4.2s",
  tickCount: 3,
  lastTick: "manual_ping · backlog + curiosity",
  nextTickDelay: "92s",
  rhythmMode: "curious",
  wakeReason: "candidate backlog and user-attention queue",
  latestObservation: "promotion review backlog detected",
  latestNeed: "operator confirmation needed",
  latestImpulse: "prepare a review proposal",
  latestSpark: "revisit stale candidate",
  latestAction: "prepare operator confirmation request",
  latestBrief: "Morning status brief ready",
  pendingApprovals: ["operator confirmation request", "promotion review proposal"],
  safetyBlocks: [
    "Local Brain write locked",
    "production mutation locked",
    "candidate promotion locked",
    "real P2P locked",
    "generated code locked",
    "always listening locked",
  ],
};

const copy = {
  en: {
    eyebrow: "Proof-only life signs",
    title: "Live Selfhood Monitor",
    intro:
      "A read-only panel for functional heartbeat, rhythm, sparks, proposals, briefs, approvals, and safety blocks. It does not start a daemon and does not prove consciousness.",
    alive: "Alive Status",
    doing: "What ATANOR Is Doing",
    woke: "Why It Woke Up",
    wants: "What It Wants To Do",
    prepared: "What It Prepared To Say",
    safety: "Safety Blocks",
    controls: "Monitor Controls",
  },
  ko: {
    eyebrow: "Proof-only life signs",
    title: "Live Selfhood Monitor",
    intro:
      "기능적 heartbeat, rhythm, spark, 제안, brief, 승인 대기, safety block을 읽기 전용으로 보여주는 패널입니다. daemon을 시작하지 않고 의식 증명도 주장하지 않습니다.",
    alive: "Alive Status",
    doing: "What ATANOR Is Doing",
    woke: "Why It Woke Up",
    wants: "What It Wants To Do",
    prepared: "What It Prepared To Say",
    safety: "Safety Blocks",
    controls: "Monitor Controls",
  },
} satisfies Record<Language, Record<string, string>>;

const statusColor: Record<Status, string> = {
  alive: "#86efac",
  idle: "#bae6fd",
  resting: "#fde68a",
  stalled: "#fdba74",
  stopped: "#fca5a5",
  unknown: "#cbd5e1",
};

const styles: Record<string, CSSProperties> = {
  shell: {
    display: "grid",
    gridTemplateColumns: "minmax(0, 1fr) minmax(320px, .88fr)",
    gap: 16,
    width: "100%",
  },
  hero: {
    gridColumn: "1 / -1",
    border: "1px solid rgba(45, 212, 191, .28)",
    borderRadius: 8,
    padding: 20,
    background: "linear-gradient(135deg, rgba(12, 18, 24, .96), rgba(27, 36, 36, .88))",
  },
  panel: {
    border: "1px solid rgba(148, 163, 184, .24)",
    borderRadius: 8,
    padding: 16,
    background: "rgba(12, 18, 24, .78)",
    minWidth: 0,
  },
  grid: {
    display: "grid",
    gridTemplateColumns: "repeat(auto-fit, minmax(180px, 1fr))",
    gap: 10,
  },
  row: {
    display: "flex",
    justifyContent: "space-between",
    gap: 12,
    alignItems: "center",
    marginTop: 9,
  },
  card: {
    border: "1px solid rgba(71, 85, 105, .58)",
    borderRadius: 8,
    padding: 12,
    background: "rgba(15, 23, 42, .72)",
  },
  badge: {
    border: "1px solid rgba(45, 212, 191, .34)",
    borderRadius: 999,
    padding: "6px 10px",
    fontSize: 12,
    color: "#ccfbf1",
    background: "rgba(20, 184, 166, .08)",
  },
  badgeRow: { display: "flex", flexWrap: "wrap", gap: 8, marginTop: 14 },
  muted: { color: "#94a3b8", fontSize: 12 },
  locked: { color: "#fca5a5" },
};

function Row({ label, value }: { label: string; value: string | number }) {
  return (
    <p style={styles.row}>
      <span>{label}</span>
      <strong>{value}</strong>
    </p>
  );
}

export default function LiveSelfhoodMonitorPanel({ language }: { language: Language }) {
  const t = copy[language];
  return (
    <section style={styles.shell} aria-label="Live Selfhood Life Signs proof-only monitor">
      <header style={styles.hero}>
        <span style={styles.muted}>{t.eyebrow}</span>
        <h2 style={{ margin: "6px 0 4px", fontSize: 34 }}>{t.title}</h2>
        <p style={{ maxWidth: 980, color: "#d1fae5", lineHeight: 1.58 }}>{t.intro}</p>
        <div style={styles.badgeRow}>
          {["monitor_read_only=true", "bounded_runtime=true", "can_stop=true", "requires_user_approval=true", "no daemon"].map((badge) => (
            <span key={badge} style={styles.badge}>{badge}</span>
          ))}
        </div>
      </header>

      <article style={styles.panel}>
        <h3>{t.alive}</h3>
        <p style={styles.row}><span>status</span><strong style={{ color: statusColor[lifeSigns.aliveStatus] }}>{lifeSigns.aliveStatus}</strong></p>
        <Row label="heartbeat age" value={lifeSigns.heartbeatAge} />
        <Row label="tick count" value={lifeSigns.tickCount} />
        <Row label="last tick" value={lifeSigns.lastTick} />
        <Row label="next tick delay" value={lifeSigns.nextTickDelay} />
      </article>

      <aside style={styles.panel}>
        <h3>{t.woke}</h3>
        <Row label="wake reason" value={lifeSigns.wakeReason} />
        <Row label="rhythm decision" value={lifeSigns.rhythmMode} />
        <Row label="spark trigger" value={lifeSigns.latestSpark} />
      </aside>

      <article style={styles.panel}>
        <h3>{t.doing}</h3>
        <div style={styles.grid}>
          {[
            ["observation", lifeSigns.latestObservation],
            ["need", lifeSigns.latestNeed],
            ["impulse", lifeSigns.latestImpulse],
            ["action", lifeSigns.latestAction],
            ["brief", lifeSigns.latestBrief],
          ].map(([label, value]) => (
            <section key={label} style={styles.card}>
              <span style={styles.muted}>{label}</span>
              <strong style={{ display: "block", marginTop: 6 }}>{value}</strong>
            </section>
          ))}
        </div>
      </article>

      <aside style={styles.panel}>
        <h3>{t.wants}</h3>
        <Row label="proposed action" value={lifeSigns.latestAction} />
        <ul>
          {lifeSigns.pendingApprovals.map((item) => <li key={item}>{item}</li>)}
        </ul>
      </aside>

      <article style={styles.panel}>
        <h3>{t.prepared}</h3>
        <Row label="latest text brief" value={lifeSigns.latestBrief} />
        <Row label="voice-ready response" value="none · voice optional" />
      </article>

      <aside style={styles.panel}>
        <h3>{t.controls}</h3>
        <Row label="default" value="disabled" />
        <Row label="bounded watch session" value="available" />
        <Row label="stop marker" value="supported" />
        <Row label="real daemon" value="not started" />
        <p style={styles.muted}>Static proof data only. This component makes no API call and performs no mutation.</p>
      </aside>

      <article style={{ ...styles.panel, gridColumn: "1 / -1" }}>
        <h3>{t.safety}</h3>
        <div style={styles.grid}>
          {lifeSigns.safetyBlocks.map((block) => (
            <section key={block} style={styles.card}>
              <span>{block}</span>
              <strong style={{ ...styles.locked, display: "block", marginTop: 6 }}>locked</strong>
            </section>
          ))}
        </div>
      </article>
    </section>
  );
}
