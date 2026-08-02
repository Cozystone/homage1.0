"use client";

import type { CSSProperties } from "react";

type Language = "en" | "ko";

type RuntimeState = "idle" | "observing" | "deliberating" | "awaiting_user_approval" | "blocked";

type Axis = {
  name: string;
  status: string;
  detail: string;
};

type Gate = {
  label: string;
  value: boolean;
};

const state: RuntimeState = "awaiting_user_approval";

const axes: Axis[] = [
  { name: "Autonomy Kernel", status: "connected", detail: "world/self snapshot + deficit signal" },
  { name: "Digital Life Kernel", status: "connected", detail: "proposal model only" },
  { name: "MiroFish", status: "connected", detail: "deterministic local deliberation" },
  { name: "Promotion Gate", status: "dry-run", detail: "candidate review, no promotion" },
  { name: "Tabularis", status: "connected", detail: "direct identifier risk check" },
  { name: "Atlas Router", status: "dry-run", detail: "no real P2P route" },
  { name: "Voice Loop", status: "optional", detail: "text first, mock/fallback voice output" },
  { name: "Logical Sphere", status: "read-only", detail: "verified/candidate/rendered count semantics" },
];

const gates: Gate[] = [
  { label: "production_store_mutated", value: false },
  { label: "local_brain_write", value: false },
  { label: "candidate_promotion", value: false },
  { label: "actual_promotion_performed", value: false },
  { label: "external_llm_used", value: false },
  { label: "real_p2p_used", value: false },
  { label: "real_cloud_upload", value: false },
  { label: "generated_code_executed", value: false },
  { label: "real_hot_swap_performed", value: false },
  { label: "always_listening_enabled", value: false },
];

const latestCycle = {
  inputType: "candidate_run_result",
  signal: "promotion_candidate",
  deliberation: "MiroFish prepared a local review packet and kept promotion behind user approval.",
  privacy: "safe_for_cloud_brain=true, raw_private_data_exported=false",
  promotion: "dry_run_only=true, actual_promotion_performed=false",
  route: "route_allowed=true, real_p2p_used=false",
  proposalTitle: "Review candidate learning output",
  proposalSummary: "Prepare a human-reviewed promotion checklist for candidate-only knowledge.",
  textOutput: "후보 학습 결과는 dry-run 승격 검토 대상으로만 평가했습니다. 실제 승격은 하지 않았고 사용자 승인이 필요합니다.",
  voiceOutput: "optional mock/fallback event only",
};

const brief = {
  noticed: "ATANOR noticed a candidate-learning result that may need human review.",
  proposes: "Prepare a bounded promotion review packet without touching production memory.",
  requiresApproval: "Any promotion, Local Brain write, P2P route, hot-swap, or durable memory action.",
  blocked: "Production mutation, Local Brain write, real P2P, cloud upload, generated code execution, always-on microphone.",
};

const copy = {
  en: {
    title: "Selfhood Runtime Lab",
    eyebrow: "Demo/proof summary",
    intro: "A proof-only self-model runtime surface. It observes, detects deficits, deliberates, checks gates, and proposes actions while waiting for explicit user approval.",
    runtime: "Runtime State",
    axes: "Connected Axes",
    latest: "Latest Selfhood Cycle",
    safety: "Safety Gates",
    morning: "Morning Brief / Morning Gift",
    limitations: "Limitations",
    proofOnly: "proof-only",
    approval: "user approval required",
    text: "text input supported",
    voice: "voice optional",
    notConsciousness: "not real consciousness",
    notAgi: "not AGI",
  },
  ko: {
    title: "Selfhood Runtime Lab",
    eyebrow: "데모 / proof summary",
    intro: "proof-only 자기 모델 런타임 화면입니다. 관찰, 결핍 감지, 숙의, 안전 게이트 점검, 제안 생성까지만 수행하고 명시적 사용자 승인을 기다립니다.",
    runtime: "런타임 상태",
    axes: "연결된 축",
    latest: "최근 Selfhood Cycle",
    safety: "안전 게이트",
    morning: "Morning Brief / Morning Gift",
    limitations: "한계",
    proofOnly: "proof-only",
    approval: "사용자 승인 필요",
    text: "텍스트 입력 지원",
    voice: "음성 선택 사항",
    notConsciousness: "실제 의식 아님",
    notAgi: "AGI 아님",
  },
} satisfies Record<Language, Record<string, string>>;

const styles: Record<string, CSSProperties> = {
  page: { display: "grid", gridTemplateColumns: "minmax(0, 1.35fr) minmax(300px, .65fr)", gap: 16, width: "100%" },
  hero: { gridColumn: "1 / -1", border: "1px solid rgba(148, 163, 184, .26)", borderRadius: 8, padding: 20, background: "rgba(8, 13, 24, .86)" },
  badgeRow: { display: "flex", flexWrap: "wrap", gap: 8, marginTop: 14 },
  badge: { border: "1px solid rgba(125, 211, 252, .34)", borderRadius: 999, padding: "6px 10px", fontSize: 12, color: "#dbeafe", background: "rgba(14, 165, 233, .08)" },
  panel: { border: "1px solid rgba(148, 163, 184, .22)", borderRadius: 8, padding: 16, background: "rgba(10, 15, 28, .78)", minWidth: 0 },
  grid: { display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(210px, 1fr))", gap: 12 },
  card: { border: "1px solid rgba(71, 85, 105, .55)", borderRadius: 8, padding: 12, background: "rgba(15, 23, 42, .72)" },
  row: { display: "flex", justifyContent: "space-between", gap: 12, alignItems: "center", marginTop: 8 },
  muted: { color: "#94a3b8", fontSize: 12 },
  valueFalse: { color: "#86efac" },
  valueTrue: { color: "#fca5a5" },
};

function boolText(value: boolean) {
  return String(value).toLowerCase();
}

export default function SelfhoodRuntimePanel({ language }: { language: Language }) {
  const t = copy[language];
  return (
    <section style={styles.page} aria-label="Selfhood Runtime Lab proof-only panel">
      <header style={styles.hero}>
        <span style={styles.muted}>{t.eyebrow}</span>
        <h2 style={{ margin: "6px 0 4px", fontSize: 34 }}>{t.title}</h2>
        <p style={{ maxWidth: 940, color: "#dbeafe", lineHeight: 1.58 }}>{t.intro}</p>
        <div style={styles.badgeRow}>
          {[t.proofOnly, t.approval, t.text, t.voice, t.notConsciousness, t.notAgi].map((badge) => (
            <span key={badge} style={styles.badge}>{badge}</span>
          ))}
        </div>
      </header>

      <article style={styles.panel}>
        <h3>{t.runtime}</h3>
        <div style={styles.grid}>
          {[
            ["current_state", state],
            ["proof_verdict", "SELFHOOD_RUNTIME_V0_PROOF_ONLY"],
            ["requires_user_approval", "true"],
            ["text_input_supported", "true"],
            ["voice_optional", "true"],
          ].map(([label, value]) => (
            <section key={label} style={styles.card}>
              <span style={styles.muted}>{label}</span>
              <strong style={{ display: "block", marginTop: 6 }}>{value}</strong>
            </section>
          ))}
        </div>
      </article>

      <aside style={styles.panel}>
        <h3>{t.safety}</h3>
        {gates.map((gate) => (
          <p key={gate.label} style={styles.row}>
            <span>{gate.label}</span>
            <strong style={gate.value ? styles.valueTrue : styles.valueFalse}>{boolText(gate.value)}</strong>
          </p>
        ))}
      </aside>

      <article style={styles.panel}>
        <h3>{t.axes}</h3>
        <div style={styles.grid}>
          {axes.map((axis) => (
            <section key={axis.name} style={styles.card}>
              <span style={styles.muted}>{axis.status}</span>
              <h4>{axis.name}</h4>
              <p style={styles.muted}>{axis.detail}</p>
            </section>
          ))}
        </div>
      </article>

      <aside style={styles.panel}>
        <h3>{t.morning}</h3>
        <p><span style={styles.muted}>What ATANOR noticed</span><br /><strong>{brief.noticed}</strong></p>
        <p><span style={styles.muted}>What ATANOR proposes</span><br /><strong>{brief.proposes}</strong></p>
        <p><span style={styles.muted}>What requires user approval</span><br /><strong>{brief.requiresApproval}</strong></p>
        <p><span style={styles.muted}>What was blocked by safety gates</span><br /><strong>{brief.blocked}</strong></p>
      </aside>

      <article style={styles.panel}>
        <h3>{t.latest}</h3>
        <div style={styles.grid}>
          {[
            ["input_type", latestCycle.inputType],
            ["detected_signal", latestCycle.signal],
            ["deliberation_summary", latestCycle.deliberation],
            ["privacy_check", latestCycle.privacy],
            ["promotion_dry_run", latestCycle.promotion],
            ["route_check", latestCycle.route],
            ["proposal_title", latestCycle.proposalTitle],
            ["proposal_summary", latestCycle.proposalSummary],
            ["text_output", latestCycle.textOutput],
            ["voice_output_event", latestCycle.voiceOutput],
          ].map(([label, value]) => (
            <section key={label} style={styles.card}>
              <span style={styles.muted}>{label}</span>
              <p>{value}</p>
            </section>
          ))}
        </div>
      </article>

      <aside style={styles.panel}>
        <h3>{t.limitations}</h3>
        {[
          "proof-only",
          "not real consciousness",
          "not AGI",
          "no production mutation",
          "no Local Brain write",
          "no candidate store mutation",
          "no real P2P",
          "no automatic memory write",
          "no approval action backend yet",
        ].map((item) => (
          <p key={item} style={styles.row}><span>{item}</span><strong>locked</strong></p>
        ))}
      </aside>
    </section>
  );
}
