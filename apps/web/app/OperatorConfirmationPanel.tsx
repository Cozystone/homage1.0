"use client";

import { useMemo, useState, type CSSProperties } from "react";

type Language = "en" | "ko";
type ConfirmationState = "not_entered" | "mismatch" | "confirmed";

const requiredPhrase = "I UNDERSTAND LOCAL BRAIN WRITE PREPARATION 8f71d4a9c203";

const preconditions = [
  ["approved_memory_manifest", true],
  ["write_dry_run_plan", true],
  ["backup_plan", true],
  ["rollback_plan", true],
  ["sandbox_transaction_proof", true],
  ["raw_voice_autosave_blocked", true],
  ["sensitive_raw_memory_blocked", true],
] as const;

const safetyGates = [
  ["operator_confirmation_required", true],
  ["allowed_to_prepare_real_write", false],
  ["allowed_to_apply_real_write", false],
  ["memory_apply_enabled", false],
  ["real_local_brain_write", false],
  ["production_store_mutated", false],
  ["candidate_promotion", false],
  ["external_llm_used", false],
] as const;

const copy = {
  en: {
    eyebrow: "Proof-only safety gate",
    title: "Operator Confirmation Gate",
    intro:
      "Require an explicit typed phrase before any future Local Brain write can be prepared. This panel never applies memory and never mutates Local Brain.",
    request: "Confirmation Request",
    preconditions: "Preconditions",
    confirmation: "Typed Confirmation",
    safety: "Safety Gates",
    phrase: "Required phrase",
    input: "Type the required phrase",
    prepare: "Preparation unlocked",
    locked: "Preparation locked",
    apply: "Apply real write",
  },
  ko: {
    eyebrow: "proof-only safety gate",
    title: "Operator Confirmation Gate",
    intro:
      "미래의 Local Brain 쓰기 준비 전에 명시적 typed phrase를 요구합니다. 이 패널은 memory apply와 Local Brain mutation을 수행하지 않습니다.",
    request: "Confirmation Request",
    preconditions: "Preconditions",
    confirmation: "Typed Confirmation",
    safety: "Safety Gates",
    phrase: "Required phrase",
    input: "Type the required phrase",
    prepare: "Preparation unlocked",
    locked: "Preparation locked",
    apply: "Apply real write",
  },
} satisfies Record<Language, Record<string, string>>;

const styles: Record<string, CSSProperties> = {
  page: {
    display: "grid",
    gridTemplateColumns: "minmax(0, 1.2fr) minmax(320px, .8fr)",
    gap: 16,
    width: "100%",
  },
  hero: {
    gridColumn: "1 / -1",
    border: "1px solid rgba(148, 163, 184, .26)",
    borderRadius: 8,
    padding: 20,
    background: "rgba(8, 13, 24, .88)",
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
    gridTemplateColumns: "repeat(auto-fit, minmax(210px, 1fr))",
    gap: 12,
  },
  card: {
    border: "1px solid rgba(71, 85, 105, .58)",
    borderRadius: 8,
    padding: 12,
    background: "rgba(15, 23, 42, .74)",
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
  blocked: { color: "#fca5a5" },
  input: {
    width: "100%",
    border: "1px solid rgba(148, 163, 184, .36)",
    borderRadius: 8,
    padding: "10px 12px",
    color: "#e2e8f0",
    background: "rgba(15, 23, 42, .82)",
  },
  button: {
    border: "1px solid rgba(148, 163, 184, .32)",
    borderRadius: 8,
    padding: "9px 12px",
    color: "#e2e8f0",
    background: "rgba(30, 41, 59, .72)",
  },
};

function boolText(value: boolean) {
  return String(value).toLowerCase();
}

function evaluatePhrase(value: string): ConfirmationState {
  if (!value.trim()) {
    return "not_entered";
  }
  return value.trim() === requiredPhrase ? "confirmed" : "mismatch";
}

export default function OperatorConfirmationPanel({ language }: { language: Language }) {
  const t = copy[language];
  const [typedPhrase, setTypedPhrase] = useState("");
  const confirmationState = useMemo(() => evaluatePhrase(typedPhrase), [typedPhrase]);
  const preparationUnlocked = confirmationState === "confirmed";

  return (
    <section style={styles.page} aria-label="Local Brain operator confirmation gate">
      <header style={styles.hero}>
        <span style={styles.muted}>{t.eyebrow}</span>
        <h2 style={{ margin: "6px 0 4px", fontSize: 34 }}>{t.title}</h2>
        <p style={{ maxWidth: 980, color: "#dbeafe", lineHeight: 1.58 }}>{t.intro}</p>
        <div style={styles.badgeRow}>
          {[
            "operator phrase required",
            "prepare only",
            "apply disabled",
            "Local Brain write false",
            "runtime confirmation records excluded",
          ].map((badge) => (
            <span key={badge} style={styles.badge}>
              {badge}
            </span>
          ))}
        </div>
      </header>

      <article style={styles.panel}>
        <h3>{t.request}</h3>
        <div style={styles.grid}>
          {[
            ["manifest_id", "manifest_local_memory_approval_001"],
            ["write_plan_id", "write_dry_run_plan_001"],
            ["backup_plan_id", "backup_plan_001"],
            ["rollback_plan_id", "rollback_plan_001"],
            ["sandbox_transaction_id", "sandbox_tx_001"],
            ["expires_in", "24h"],
          ].map(([label, value]) => (
            <section key={label} style={styles.card}>
              <span style={styles.muted}>{label}</span>
              <strong style={{ display: "block", marginTop: 6 }}>{value}</strong>
            </section>
          ))}
        </div>
      </article>

      <aside style={styles.panel}>
        <h3>{t.confirmation}</h3>
        <p style={styles.muted}>{t.phrase}</p>
        <code style={{ display: "block", marginBottom: 12, wordBreak: "break-word", color: "#dbeafe" }}>{requiredPhrase}</code>
        <input
          aria-label={t.input}
          value={typedPhrase}
          onChange={(event) => setTypedPhrase(event.target.value)}
          placeholder={t.input}
          style={styles.input}
        />
        <p style={{ marginTop: 12 }}>
          <strong style={preparationUnlocked ? styles.safe : styles.blocked}>
            {preparationUnlocked ? t.prepare : t.locked}
          </strong>
        </p>
        <button type="button" aria-disabled="true" disabled style={{ ...styles.button, opacity: 0.55, cursor: "not-allowed" }}>
          {t.apply}: disabled
        </button>
      </aside>

      <article style={styles.panel}>
        <h3>{t.preconditions}</h3>
        <div style={styles.grid}>
          {preconditions.map(([label, value]) => (
            <section key={label} style={styles.card}>
              <span style={styles.muted}>{label}</span>
              <strong style={value ? styles.safe : styles.blocked}>{boolText(value)}</strong>
            </section>
          ))}
        </div>
      </article>

      <article style={styles.panel}>
        <h3>{t.safety}</h3>
        <div style={styles.grid}>
          {safetyGates.map(([label, value]) => (
            <section key={label} style={styles.card}>
              <span style={styles.muted}>{label}</span>
              <strong style={value ? styles.safe : styles.blocked}>{boolText(value)}</strong>
            </section>
          ))}
        </div>
      </article>
    </section>
  );
}
