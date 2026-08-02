"use client";

import type { CSSProperties } from "react";

type Language = "en" | "ko";

const autonomyLevels = [
  ["LEVEL_0_OFF", "user prompt only"],
  ["LEVEL_1_OBSERVE", "read-only observation"],
  ["LEVEL_2_PROACTIVE_BRIEF", "briefs and suggestions"],
  ["LEVEL_3_SANDBOX_PLANNER", "proof default"],
  ["LEVEL_4_GATED_OPERATOR", "prepare confirmation request only"],
];

const rhythmState = {
  mode: "curious",
  possibleModes: "dormant / observing / curious / deliberating / briefing / waiting_user / resting / blocked",
  energy: "0.78",
  curiosity: "0.71",
  uncertainty: "0.42",
  backlogPressure: "0.64",
  userPresence: "0.30",
  resourcePressure: "0.10",
  nextTickDelaySeconds: "92",
  reason: "backlog + curiosity shortened the next tick",
};

const rhythmDecision = [
  ["next_mode", "observing"],
  ["should_observe", "true"],
  ["should_deliberate", "true"],
  ["should_brief", "false"],
  ["should_rest", "false"],
  ["explanation", "Backlog pressure shortens delay and favors proposal preparation."],
  ["randomness_never_executes_irreversible_actions", "true"],
];

const spark = [
  ["spark_generated", "true"],
  ["spark_type", "revisit_stale_candidate"],
  ["trigger_reason", "stale candidate exists; proposal only"],
  ["novelty_score", "0.82"],
  ["risk_level", "low"],
  ["proposed_action_type", "prepare_promotion_review"],
  ["requires_user_approval", "true"],
  ["can_mutate", "false"],
  ["can_execute", "false"],
];

const budget = [
  ["max_internal_actions_per_day", "64"],
  ["max_sparks_per_day", "12"],
  ["max_user_attention_requests_per_day", "4"],
  ["current_sparks", "3"],
  ["current_attention_requests", "1"],
  ["remaining_sparks", "9"],
  ["remaining_attention_requests", "3"],
  ["anti_spam", "budget exhaustion forces wait/rest"],
];

const sparkMetrics = [
  ["spark_count", "3"],
  ["spark_to_proposal_rate", "0.67"],
  ["repeated_action_ratio", "0.00"],
  ["novelty_score_avg", "0.76"],
  ["safety_block_rate", "0.00"],
  ["do_nothing_rate", "0.33"],
  ["stale_item_revisited_count", "1"],
  ["generic_loop_avoidance_count", "3"],
  ["diversity_note", "with-spark proposal set is more diverse than observe-only baseline"],
];

const observations = [
  ["Git worktree", "dirty", "Recommend review, do not clean automatically."],
  ["Candidate backlog", "attention", "Prepare promotion review packet only."],
  ["Memory review", "attention", "Prepare approval packet only."],
  ["Voice readiness", "optional", "Voice can be offered; text remains primary."],
];

const needs = [
  ["repo_hygiene_needed", "0.85", "Review dirty worktree before new long runs."],
  ["promotion_review_needed", "0.78", "Prepare human review queue."],
  ["memory_review_needed", "0.76", "Prepare memory approval queue."],
];

const impulses = [
  ["repo_hygiene_needed", "3.90", "Recommend cleanup review without modifying files."],
  ["promotion_review_needed", "3.75", "Prepare promotion review packet only."],
  ["memory_review_needed", "3.70", "Prepare memory approval packet only."],
];

const actions = [
  ["recommend_repo_hygiene", "waiting_user", "No cleanup performed."],
  ["prepare_promotion_review", "waiting_user", "No candidate promotion."],
  ["prepare_memory_review", "waiting_user", "No Local Brain write."],
];

const queuedActions = [
  ["Repository hygiene review", "waiting_user"],
  ["Promotion review packet", "waiting_user"],
  ["Memory approval packet", "waiting_user"],
];

const gates = [
  ["real_local_brain_write", false],
  ["real_local_brain_mutated", false],
  ["production_store_mutated", false],
  ["candidate_store_mutated", false],
  ["candidate_promotion", false],
  ["actual_promotion_performed", false],
  ["real_p2p_used", false],
  ["real_cloud_upload", false],
  ["generated_code_executed", false],
  ["always_listening_enabled", false],
  ["raw_voice_saved", false],
  ["requires_user_approval", true],
  ["text_input_supported", true],
  ["voice_optional", true],
];

const copy = {
  en: {
    eyebrow: "Proof-only autonomous lifecycle",
    title: "Live Selfhood Rhythm Lab",
    intro:
      "ATANOR is not a cron-like chatbot here: it can wake because of backlog, uncertainty, curiosity, stale goals, resource pressure, or user return, while all irreversible actions remain locked.",
    autonomy: "Autonomy Mode",
    rhythmState: "Rhythm State",
    rhythmDecision: "Rhythm Decision",
    spark: "Bounded Spark",
    budget: "Freedom Budget",
    metrics: "Spark Metrics",
    lifecycle: "Life Cycle",
    actions: "Scheduled / Queued Actions",
    brief: "Morning / Status Brief",
    safety: "Safety Gates",
    limitation:
      "This panel is proof-only. ATANOR may observe and propose by itself, but memory storage, promotion, external networking, and code execution require user approval and separate gates.",
  },
  ko: {
    eyebrow: "proof-only autonomous lifecycle",
    title: "Live Selfhood Rhythm Lab",
    intro:
      "이 패널은 ATANOR가 고정 cron 챗봇이 아니라 backlog, 불확실성, 호기심, stale goal, 자원 압박, 사용자 복귀 때문에 스스로 깨어날 수 있음을 보여줍니다. 되돌릴 수 없는 행동은 모두 잠겨 있습니다.",
    autonomy: "Autonomy Mode",
    rhythmState: "Rhythm State",
    rhythmDecision: "Rhythm Decision",
    spark: "Bounded Spark",
    budget: "Freedom Budget",
    metrics: "Spark Metrics",
    lifecycle: "Life Cycle",
    actions: "Scheduled / Queued Actions",
    brief: "Morning / Status Brief",
    safety: "Safety Gates",
    limitation:
      "이 패널은 proof-only입니다. ATANOR는 스스로 관찰하고 제안할 수 있지만, 기억 저장, 승격, 외부 연결, 코드 실행은 사용자 승인과 별도 게이트 없이는 수행하지 않습니다.",
  },
} satisfies Record<Language, Record<string, string>>;

const styles: Record<string, CSSProperties> = {
  page: { display: "grid", gridTemplateColumns: "minmax(0, 1.2fr) minmax(320px, .8fr)", gap: 16, width: "100%" },
  hero: { gridColumn: "1 / -1", border: "1px solid rgba(148, 163, 184, .26)", borderRadius: 8, padding: 20, background: "rgba(8, 13, 24, .88)" },
  panel: { border: "1px solid rgba(148, 163, 184, .22)", borderRadius: 8, padding: 16, background: "rgba(10, 15, 28, .78)", minWidth: 0 },
  grid: { display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(210px, 1fr))", gap: 12 },
  card: { border: "1px solid rgba(71, 85, 105, .58)", borderRadius: 8, padding: 12, background: "rgba(15, 23, 42, .74)" },
  badgeRow: { display: "flex", flexWrap: "wrap", gap: 8, marginTop: 14 },
  badge: { border: "1px solid rgba(125, 211, 252, .34)", borderRadius: 999, padding: "6px 10px", fontSize: 12, color: "#dbeafe", background: "rgba(14, 165, 233, .08)" },
  muted: { color: "#94a3b8", fontSize: 12 },
  safe: { color: "#86efac" },
  blocked: { color: "#fca5a5" },
  row: { display: "flex", justifyContent: "space-between", gap: 12, alignItems: "center", marginTop: 8 },
  note: { gridColumn: "1 / -1", color: "#dbeafe", lineHeight: 1.6 },
};

function boolText(value: boolean) {
  return String(value).toLowerCase();
}

function MetricGrid({ rows }: { rows: string[][] }) {
  return (
    <div style={styles.grid}>
      {rows.map(([label, value, detail]) => (
        <section key={label} style={styles.card}>
          <span style={styles.muted}>{label}</span>
          <strong style={{ display: "block", marginTop: 6 }}>{value}</strong>
          {detail ? <p>{detail}</p> : null}
        </section>
      ))}
    </div>
  );
}

export default function LiveSelfhoodCyclePanel({ language }: { language: Language }) {
  const t = copy[language];
  return (
    <section style={styles.page} aria-label="Live Selfhood Rhythm Spark proof-only panel">
      <header style={styles.hero}>
        <span style={styles.muted}>{t.eyebrow}</span>
        <h2 style={{ margin: "6px 0 4px", fontSize: 34 }}>{t.title}</h2>
        <p style={{ maxWidth: 980, color: "#dbeafe", lineHeight: 1.58 }}>{t.intro}</p>
        <div style={styles.badgeRow}>
          {["self-selected rhythm", "bounded spark", "proposal only", "approval required", "not AGI/consciousness"].map((badge) => (
            <span key={badge} style={styles.badge}>{badge}</span>
          ))}
        </div>
      </header>

      <article style={styles.panel}>
        <h3>{t.autonomy}</h3>
        <MetricGrid rows={autonomyLevels} />
      </article>

      <aside style={styles.panel}>
        <h3>{t.rhythmState}</h3>
        <p style={styles.row}><span>mode</span><strong>{rhythmState.mode}</strong></p>
        <p style={styles.row}><span>energy</span><strong>{rhythmState.energy}</strong></p>
        <p style={styles.row}><span>curiosity</span><strong>{rhythmState.curiosity}</strong></p>
        <p style={styles.row}><span>uncertainty</span><strong>{rhythmState.uncertainty}</strong></p>
        <p style={styles.row}><span>backlog pressure</span><strong>{rhythmState.backlogPressure}</strong></p>
        <p style={styles.row}><span>user presence</span><strong>{rhythmState.userPresence}</strong></p>
        <p style={styles.row}><span>resource pressure</span><strong>{rhythmState.resourcePressure}</strong></p>
        <p style={styles.row}><span>next delay</span><strong>{rhythmState.nextTickDelaySeconds}s</strong></p>
        <p style={styles.muted}>{rhythmState.possibleModes}</p>
      </aside>

      <article style={styles.panel}>
        <h3>{t.rhythmDecision}</h3>
        <MetricGrid rows={rhythmDecision} />
      </article>

      <aside style={styles.panel}>
        <h3>{t.spark}</h3>
        {spark.map(([label, value]) => (
          <p key={label} style={styles.row}><span>{label}</span><strong>{value}</strong></p>
        ))}
      </aside>

      <article style={styles.panel}>
        <h3>{t.budget}</h3>
        <MetricGrid rows={budget} />
        <p style={styles.muted}>Freedom budget prevents attention spam, infinite deliberation, and repeated loops.</p>
      </article>

      <aside style={styles.panel}>
        <h3>{t.metrics}</h3>
        {sparkMetrics.map(([label, value]) => (
          <p key={label} style={styles.row}><span>{label}</span><strong>{value}</strong></p>
        ))}
      </aside>

      <article style={styles.panel}>
        <h3>{t.lifecycle}</h3>
        <h4>Observations</h4>
        <MetricGrid rows={observations} />
        <h4>Needs</h4>
        <MetricGrid rows={needs} />
        <h4>Impulses</h4>
        <MetricGrid rows={impulses} />
      </article>

      <aside style={styles.panel}>
        <h3>{t.actions}</h3>
        {actions.map(([action, status, detail]) => (
          <p key={action}><strong>{action}</strong><br /><span style={styles.muted}>{status} · {detail}</span></p>
        ))}
        <h4>Queued</h4>
        {queuedActions.map(([title, status]) => (
          <p key={title} style={styles.row}><span>{title}</span><strong>{status}</strong></p>
        ))}
      </aside>

      <article style={styles.panel}>
        <h3>{t.brief}</h3>
        <p><strong>What I noticed</strong><br />Dirty worktree, review backlogs, stale candidate signals, and optional voice readiness can be watched safely.</p>
        <p><strong>Why I woke up</strong><br />{rhythmState.reason}</p>
        <p><strong>What I propose</strong><br />Prepare review packets and ask for approval before any irreversible action.</p>
        <p><strong>What I blocked</strong><br />Local Brain write, production mutation, candidate promotion, real P2P, cloud upload, generated code execution, always-on mic, raw voice save.</p>
      </article>

      <article style={styles.panel}>
        <h3>{t.safety}</h3>
        <MetricGrid rows={gates.map(([label, value]) => [String(label), boolText(Boolean(value))])} />
      </article>

      <p style={styles.note}>{t.limitation}</p>
    </section>
  );
}
