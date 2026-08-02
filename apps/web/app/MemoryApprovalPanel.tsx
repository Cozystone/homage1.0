"use client";

import { useMemo, useState, type CSSProperties } from "react";

type Language = "en" | "ko";
type Decision = "approve" | "reject" | "defer" | "edit_required" | "sensitive_block";

type Candidate = {
  id: string;
  label: string;
  type: string;
  source: string;
  sensitivity: string;
  recommendation: Decision;
  summary: string;
};

const candidates: Candidate[] = [
  {
    id: "memory:preference:concise",
    label: "Preference",
    type: "preference",
    source: "text",
    sensitivity: "personal",
    recommendation: "approve",
    summary: "User prefers concise answers when context is already clear.",
  },
  {
    id: "memory:project:atanor",
    label: "Project Context",
    type: "project_context",
    source: "selfhood_runtime_proposal",
    sensitivity: "public",
    recommendation: "approve",
    summary: "ATANOR keeps Local Brain writes behind explicit review and manifest gates.",
  },
  {
    id: "memory:sensitive:contact",
    label: "Sensitive",
    type: "sensitive",
    source: "text",
    sensitivity: "sensitive",
    recommendation: "sensitive_block",
    summary: "Raw contact-like text was detected and must not be written as raw memory.",
  },
  {
    id: "memory:voice:uncertain",
    label: "Voice Transcript",
    type: "unknown",
    source: "voice_transcript",
    sensitivity: "personal",
    recommendation: "edit_required",
    summary: "Voice-derived memory candidates require text review; raw transcript auto-save is blocked.",
  },
];

const decisions: Decision[] = ["approve", "reject", "defer", "edit_required", "sensitive_block"];

const copy = {
  en: {
    eyebrow: "Review metadata only",
    title: "Local Memory Approval",
    intro: "Inspect proposed memories, record review decisions, and preview a non-applying manifest while real Local Brain writes remain locked.",
    status: "Status",
    candidates: "Memory Candidates",
    controls: "Decision Controls",
    manifest: "Manifest Draft Preview",
    safety: "Safety Gates",
  },
  ko: {
    eyebrow: "review metadata only",
    title: "Local Memory Approval",
    intro: "제안된 메모리를 검토하고 결정을 기록하며, 실제 Local Brain 쓰기는 잠근 상태로 적용되지 않는 manifest 초안을 미리 봅니다.",
    status: "상태",
    candidates: "Memory Candidates",
    controls: "Decision Controls",
    manifest: "Manifest Draft Preview",
    safety: "Safety Gates",
  },
} satisfies Record<Language, Record<string, string>>;

const styles: Record<string, CSSProperties> = {
  page: { display: "grid", gridTemplateColumns: "minmax(0, 1.25fr) minmax(320px, .75fr)", gap: 16, width: "100%" },
  hero: { gridColumn: "1 / -1", border: "1px solid rgba(148, 163, 184, .26)", borderRadius: 8, padding: 20, background: "rgba(8, 13, 24, .88)" },
  panel: { border: "1px solid rgba(148, 163, 184, .22)", borderRadius: 8, padding: 16, background: "rgba(10, 15, 28, .78)", minWidth: 0 },
  grid: { display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(220px, 1fr))", gap: 12 },
  card: { border: "1px solid rgba(71, 85, 105, .58)", borderRadius: 8, padding: 12, background: "rgba(15, 23, 42, .74)" },
  badgeRow: { display: "flex", flexWrap: "wrap", gap: 8, marginTop: 14 },
  badge: { border: "1px solid rgba(125, 211, 252, .34)", borderRadius: 999, padding: "6px 10px", fontSize: 12, color: "#dbeafe", background: "rgba(14, 165, 233, .08)" },
  row: { display: "flex", justifyContent: "space-between", gap: 12, alignItems: "center", marginTop: 8 },
  muted: { color: "#94a3b8", fontSize: 12 },
  safe: { color: "#86efac" },
  blocked: { color: "#fca5a5" },
  buttonRow: { display: "flex", flexWrap: "wrap", gap: 8, marginTop: 10 },
  button: { border: "1px solid rgba(148, 163, 184, .4)", borderRadius: 8, padding: "8px 10px", background: "rgba(30, 41, 59, .72)", color: "#e2e8f0", cursor: "pointer" },
};

function boolText(value: boolean) {
  return String(value).toLowerCase();
}

export default function MemoryApprovalPanel({ language }: { language: Language }) {
  const t = copy[language];
  const [selected, setSelected] = useState(candidates[0].id);
  const [decisionById, setDecisionById] = useState<Record<string, Decision>>(() =>
    Object.fromEntries(candidates.map((candidate) => [candidate.id, candidate.recommendation])),
  );

  const manifest = useMemo(() => {
    const approved = candidates.filter((candidate) => decisionById[candidate.id] === "approve").map((candidate) => candidate.id);
    const rejected = candidates
      .filter((candidate) => ["reject", "sensitive_block"].includes(decisionById[candidate.id]))
      .map((candidate) => candidate.id);
    const deferred = candidates
      .filter((candidate) => ["defer", "edit_required"].includes(decisionById[candidate.id]))
      .map((candidate) => candidate.id);
    const canonicalHash = `${approved.join("|")}:${rejected.join("|")}:${deferred.join("|")}`.length.toString(16).padStart(8, "0");
    return { approved, rejected, deferred, canonicalHash };
  }, [decisionById]);

  const selectedCandidate = candidates.find((candidate) => candidate.id === selected) ?? candidates[0];

  return (
    <section style={styles.page} aria-label="Local Memory Approval review panel">
      <header style={styles.hero}>
        <span style={styles.muted}>{t.eyebrow}</span>
        <h2 style={{ margin: "6px 0 4px", fontSize: 34 }}>{t.title}</h2>
        <p style={{ maxWidth: 980, color: "#dbeafe", lineHeight: 1.58 }}>{t.intro}</p>
        <div style={styles.badgeRow}>
          {["review mode", "Local Brain write locked", "apply disabled", "voice raw auto-save blocked", "sensitive raw write blocked"].map((badge) => (
            <span key={badge} style={styles.badge}>{badge}</span>
          ))}
        </div>
      </header>

      <article style={styles.panel}>
        <h3>{t.status}</h3>
        <div style={styles.grid}>
          {[
            ["proof_review_mode", "true"],
            ["local_brain_write", "false"],
            ["apply_enabled", "false"],
            ["voice_raw_blocked", "true"],
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
        <h3>{t.controls}</h3>
        <p style={styles.muted}>{selectedCandidate.label}</p>
        <strong>{selectedCandidate.id}</strong>
        <div style={styles.buttonRow}>
          {decisions.map((decision) => (
            <button
              key={decision}
              type="button"
              style={{
                ...styles.button,
                borderColor: decisionById[selectedCandidate.id] === decision ? "rgba(125, 211, 252, .9)" : "rgba(148, 163, 184, .4)",
              }}
              onClick={() => setDecisionById((current) => ({ ...current, [selectedCandidate.id]: decision }))}
            >
              {decision}
            </button>
          ))}
        </div>
        <p style={{ ...styles.muted, marginTop: 12 }}>
          Decisions are local review metadata only. This panel does not apply memory.
        </p>
      </aside>

      <article style={styles.panel}>
        <h3>{t.candidates}</h3>
        <div style={styles.grid}>
          {candidates.map((candidate) => (
            <button key={candidate.id} type="button" style={{ ...styles.card, textAlign: "left", color: "#e2e8f0" }} onClick={() => setSelected(candidate.id)}>
              <span style={styles.muted}>{candidate.source} / {candidate.sensitivity}</span>
              <h4>{candidate.label}</h4>
              <p>{candidate.summary}</p>
              <p style={styles.muted}>recommendation: {candidate.recommendation}</p>
              <strong>decision: {decisionById[candidate.id]}</strong>
            </button>
          ))}
        </div>
      </article>

      <aside style={styles.panel}>
        <h3>{t.manifest}</h3>
        <p style={styles.row}><span>approved ids</span><strong>{manifest.approved.length}</strong></p>
        <p style={styles.row}><span>rejected ids</span><strong>{manifest.rejected.length}</strong></p>
        <p style={styles.row}><span>deferred ids</span><strong>{manifest.deferred.length}</strong></p>
        <p style={styles.row}><span>canonical hash</span><strong>{manifest.canonicalHash}</strong></p>
        <p style={styles.row}><span>ready_for_memory_write</span><strong style={styles.blocked}>false</strong></p>
        <p style={styles.row}><span>apply_enabled</span><strong style={styles.blocked}>false</strong></p>
      </aside>

      <article style={styles.panel}>
        <h3>{t.safety}</h3>
        <div style={styles.grid}>
          {[
            ["real_local_brain_write", false],
            ["production_mutation", false],
            ["candidate_mutation", false],
            ["raw_voice_saved", false],
            ["sensitive_raw_write_blocked", true],
            ["requires_user_approval", true],
          ].map(([label, value]) => (
            <section key={String(label)} style={styles.card}>
              <span style={styles.muted}>{label}</span>
              <strong style={value ? styles.safe : styles.blocked}>{boolText(Boolean(value))}</strong>
            </section>
          ))}
        </div>
      </article>
    </section>
  );
}
