"use client";

import type { CSSProperties } from "react";

type Language = "en" | "ko";

const reviewItems = [
  {
    id: "concept:kubernetes",
    type: "concept",
    summary: "Kubernetes concept with sourced definition",
    effect: "create",
    recommendation: "approve_for_future_manifest",
    score: "91%",
  },
  {
    id: "case_frame:generic_use",
    type: "case_frame",
    summary: "Generic predicate frame that needs more review",
    effect: "create",
    recommendation: "defer",
    score: "72%",
  },
  {
    id: "relation:conflict",
    type: "relation",
    summary: "Relation candidate with conflicting evidence",
    effect: "strengthen",
    recommendation: "conflict_review",
    score: "66%",
  },
];

const gates = [
  ["actual_promotion_performed", "false"],
  ["production_store_mutated", "false"],
  ["candidate_store_mutated", "false"],
  ["local_brain_write", "false"],
  ["external_llm_used", "false"],
  ["real_p2p_used", "false"],
  ["generated_code_executed", "false"],
  ["requires_user_approval", "true"],
];

const copy = {
  en: {
    eyebrow: "Review-only demo",
    title: "Candidate Promotion Review",
    intro: "Human review records can approve, reject, defer, or request evidence, but no candidate item is promoted to production here.",
    dryRun: "Dry-run Summary",
    items: "Review Items",
    decisions: "Decision Options",
    manifest: "Manifest Draft Preview",
    safety: "Safety Gates",
  },
  ko: {
    eyebrow: "review-only 데모",
    title: "Candidate Promotion Review",
    intro: "사람이 approve, reject, defer, evidence 요청 결정을 기록할 수 있지만 여기서는 어떤 후보도 production으로 승격하지 않습니다.",
    dryRun: "Dry-run 요약",
    items: "검토 항목",
    decisions: "결정 옵션",
    manifest: "Manifest 초안 미리보기",
    safety: "안전 게이트",
  },
} satisfies Record<Language, Record<string, string>>;

const styles: Record<string, CSSProperties> = {
  page: { display: "grid", gridTemplateColumns: "minmax(0, 1.25fr) minmax(300px, .75fr)", gap: 16, width: "100%" },
  hero: { gridColumn: "1 / -1", border: "1px solid rgba(148, 163, 184, .26)", borderRadius: 8, padding: 20, background: "rgba(8, 13, 24, .86)" },
  panel: { border: "1px solid rgba(148, 163, 184, .22)", borderRadius: 8, padding: 16, background: "rgba(10, 15, 28, .78)", minWidth: 0 },
  grid: { display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(210px, 1fr))", gap: 12 },
  card: { border: "1px solid rgba(71, 85, 105, .55)", borderRadius: 8, padding: 12, background: "rgba(15, 23, 42, .72)" },
  badgeRow: { display: "flex", flexWrap: "wrap", gap: 8, marginTop: 14 },
  badge: { border: "1px solid rgba(125, 211, 252, .34)", borderRadius: 999, padding: "6px 10px", fontSize: 12, color: "#dbeafe", background: "rgba(14, 165, 233, .08)" },
  row: { display: "flex", justifyContent: "space-between", gap: 12, alignItems: "center", marginTop: 8 },
  muted: { color: "#94a3b8", fontSize: 12 },
  safe: { color: "#86efac" },
};

export default function PromotionReviewPanel({ language }: { language: Language }) {
  const t = copy[language];
  return (
    <section style={styles.page} aria-label="Candidate Promotion Review demo panel">
      <header style={styles.hero}>
        <span style={styles.muted}>{t.eyebrow}</span>
        <h2 style={{ margin: "6px 0 4px", fontSize: 34 }}>{t.title}</h2>
        <p style={{ maxWidth: 920, color: "#dbeafe", lineHeight: 1.58 }}>{t.intro}</p>
        <div style={styles.badgeRow}>
          {["dry-run only", "review metadata only", "manifest draft only", "production unchanged", "user approval required"].map((badge) => (
            <span key={badge} style={styles.badge}>{badge}</span>
          ))}
        </div>
      </header>

      <article style={styles.panel}>
        <h3>{t.dryRun}</h3>
        <div style={styles.grid}>
          {[
            ["source_run", "candidate_fixture_run"],
            ["review_status", "in_review"],
            ["estimated_concepts", "1 create / 0 promote"],
            ["estimated_relations", "1 strengthen / 0 promote"],
            ["actual_promotion", "false"],
            ["verified_store_change", "false"],
          ].map(([label, value]) => (
            <section key={label} style={styles.card}>
              <span style={styles.muted}>{label}</span>
              <strong style={{ display: "block", marginTop: 6 }}>{value}</strong>
            </section>
          ))}
        </div>
      </article>

      <aside style={styles.panel}>
        <h3>{t.decisions}</h3>
        {["approve_for_future_manifest", "reject", "defer", "needs_more_evidence", "conflict_review"].map((decision) => (
          <p key={decision} style={styles.row}><span>{decision}</span><strong>record only</strong></p>
        ))}
      </aside>

      <article style={styles.panel}>
        <h3>{t.items}</h3>
        <div style={styles.grid}>
          {reviewItems.map((item) => (
            <section key={item.id} style={styles.card}>
              <span style={styles.muted}>{item.type} · {item.effect}</span>
              <h4>{item.id}</h4>
              <p>{item.summary}</p>
              <p style={styles.muted}>recommendation: {item.recommendation}</p>
              <strong>{item.score}</strong>
            </section>
          ))}
        </div>
      </article>

      <aside style={styles.panel}>
        <h3>{t.manifest}</h3>
        <p style={styles.row}><span>signed</span><strong>false</strong></p>
        <p style={styles.row}><span>ready_for_real_promotion</span><strong>false</strong></p>
        <p style={styles.row}><span>approved_item_ids</span><strong>1</strong></p>
        <p style={styles.row}><span>rejected_item_ids</span><strong>1</strong></p>
        <p style={styles.row}><span>deferred_item_ids</span><strong>1</strong></p>
      </aside>

      <article style={styles.panel}>
        <h3>{t.safety}</h3>
        <div style={styles.grid}>
          {gates.map(([label, value]) => (
            <section key={label} style={styles.card}>
              <span style={styles.muted}>{label}</span>
              <strong style={styles.safe}>{value}</strong>
            </section>
          ))}
        </div>
      </article>
    </section>
  );
}
