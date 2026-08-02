"use client";

import { useCallback, useEffect, useState } from "react";

/**
 * Plugin popover — opens UPWARD from the chat-bar "+" button (GPT/Claude tools-
 * menu pattern), not a right-side drawer. Two modes:
 *   - 사용 (use): quick-pick the enabled sentence sources, run inline.
 *   - 관리 (manage): enable/disable + the capability risk tiers + default-deny
 *     approval gate (pc:control needs a typed phrase).
 * Collected sentences flow into the Cloud-Brain firehose (수집 ≠ 이해, separate).
 */

type Cap = { id: string; risk: string; label: string; label_en: string; state: string };
type Plugin = {
  id: string; name: string; marketplace: string; version: string; kind: string;
  icon: string; description: string; max_risk: string; enabled: boolean; ready: boolean;
  composer: { slash: string; label: string; placeholder: string; field: string | null };
  capabilities: Cap[];
};
type ListResp = { plugins: Plugin[]; marketplaces: string[]; pc_control_phrase: string; offline?: boolean };

const RISK_COLOR: Record<string, string> = { safe: "#16a34a", sensitive: "#d97706", dangerous: "#dc2626" };
const RISK_KO: Record<string, string> = { safe: "안전", sensitive: "민감", dangerous: "위험" };
const ICON: Record<string, string> = {
  "clipboard-paste": "📋", "message-square": "💬", globe: "🌐", rss: "📡",
  "book-open": "📖", "file-text": "📄", clipboard: "📎", monitor: "🖥️",
};

export default function PluginKitPanel({ open, onClose, language = "ko" }: {
  open: boolean; onClose: () => void; language?: "ko" | "en";
}) {
  const ko = language === "ko";
  const [data, setData] = useState<ListResp | null>(null);
  const [mode, setMode] = useState<"use" | "manage">("use");
  const [active, setActive] = useState<string | null>(null);   // expanded plugin in use-mode
  const [inputs, setInputs] = useState<Record<string, string>>({});
  const [phrase, setPhrase] = useState<Record<string, string>>({});
  const [results, setResults] = useState<Record<string, string>>({});
  const [busy, setBusy] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    try {
      const r = await fetch("/api/plugins", { cache: "no-store" });
      setData(await r.json());
    } catch { /* keep last */ }
  }, []);

  useEffect(() => { if (open) refresh(); }, [open, refresh]);
  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => { if (e.key === "Escape") onClose(); };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open, onClose]);

  async function toggle(p: Plugin) {
    await fetch(`/api/plugins/${encodeURIComponent(p.id)}/enable`, {
      method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ enabled: !p.enabled }),
    }).catch(() => {});
    refresh();
  }
  async function decide(p: Plugin, cap: Cap, decision: "grant" | "deny") {
    const body: Record<string, unknown> = { decision };
    if (cap.risk === "dangerous") body.phrase = phrase[p.id] ?? "";
    const r = await fetch(`/api/plugins/${encodeURIComponent(p.id)}/permissions/${encodeURIComponent(cap.id)}`, {
      method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body),
    });
    if (!r.ok) {
      const j = await r.json().catch(() => ({}));
      setResults((s) => ({ ...s, [p.id]: typeof j.detail === "string" ? j.detail : (ko ? "승인 문구가 정확해야 합니다." : "Phrase must match.") }));
    }
    refresh();
  }
  async function run(p: Plugin) {
    setBusy(p.id); setResults((s) => ({ ...s, [p.id]: "" }));
    const field = p.composer.field;
    const input: Record<string, unknown> = {};
    if (field) input[field] = inputs[p.id] ?? "";
    try {
      const r = await fetch(`/api/plugins/${encodeURIComponent(p.id)}/run`, {
        method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ input }),
      });
      const j = await r.json();
      if (!r.ok) {
        const cap = j?.detail?.capability || j?.capability;
        setResults((s) => ({ ...s, [p.id]: cap ? (ko ? `권한 필요: ${cap} (관리 탭에서 허용)` : `Needs permission: ${cap}`) : (j?.detail || j?.error || (ko ? "실행 실패" : "Failed")) }));
      } else {
        setResults((s) => ({ ...s, [p.id]: ko
          ? `✓ ${j.unique}문장 수집 · 파이어호스 전송${j.sample?.[0] ? ` · "${j.sample[0].slice(0, 36)}…"` : ""}`
          : `✓ collected ${j.unique} · firehose` }));
      }
    } catch {
      setResults((s) => ({ ...s, [p.id]: ko ? "엔진(:8502) 연결 필요" : "Engine required" }));
    } finally { setBusy(null); refresh(); }
  }

  if (!open) return null;
  const plugins = data?.plugins ?? [];
  const sources = plugins.filter((p) => p.kind === "source");
  const byMarket: Record<string, Plugin[]> = {};
  plugins.forEach((p) => { (byMarket[p.marketplace] ||= []).push(p); });

  return (
    <>
      {/* click-outside backdrop */}
      <div onClick={onClose} style={{ position: "fixed", inset: 0, zIndex: 40, background: "transparent" }} />
      <div role="dialog" aria-label={ko ? "플러그인" : "Plugins"} style={{
        position: "absolute", bottom: "calc(100% + 10px)", left: 0, zIndex: 41,
        width: "min(420px, 92vw)", maxHeight: "min(60vh, 520px)", display: "flex", flexDirection: "column",
        background: "#fff", color: "#1f2937", border: "1px solid #e5e7eb", borderRadius: 14,
        boxShadow: "0 16px 48px rgba(15,23,42,0.18)", overflow: "hidden",
      }}>
        <header style={{ display: "flex", alignItems: "center", gap: 8, padding: "10px 12px", borderBottom: "1px solid #f1f3f5" }}>
          <strong style={{ fontSize: 13.5, flex: 1 }}>{ko ? "플러그인" : "Plugins"}</strong>
          <div style={{ display: "flex", background: "#f1f3f5", borderRadius: 8, padding: 2 }}>
            <button onClick={() => setMode("use")} style={tab(mode === "use")}>{ko ? "사용" : "Use"}</button>
            <button onClick={() => setMode("manage")} style={tab(mode === "manage")}>{ko ? "관리" : "Manage"}</button>
          </div>
          <button onClick={onClose} aria-label="close" style={{ background: "none", border: "none", fontSize: 18, color: "#9ca3af", cursor: "pointer", lineHeight: 1 }}>×</button>
        </header>

        <div style={{ overflowY: "auto", padding: "6px 8px 10px" }}>
          {data?.offline ? <div style={{ fontSize: 11, color: "#d97706", padding: "4px 8px" }}>{ko ? "엔진 오프라인 — 카탈로그만 표시" : "engine offline"}</div> : null}

          {/* USE MODE — quick-pick enabled sources */}
          {mode === "use" && sources.filter((p) => p.enabled).map((p) => {
            const isOpen = active === p.id;
            const result = results[p.id];
            return (
              <div key={p.id} style={{ borderRadius: 10, margin: "2px 0", background: isOpen ? "#f8fafc" : "transparent" }}>
                <button onClick={() => setActive(isOpen ? null : p.id)} style={row}>
                  <span style={{ fontSize: 16 }}>{ICON[p.icon] ?? "🔌"}</span>
                  <span style={{ flex: 1, textAlign: "left", minWidth: 0 }}>
                    <span style={{ fontSize: 13, fontWeight: 600 }}>{p.name}</span>
                    <code style={{ fontSize: 10.5, color: "#9ca3af", marginLeft: 6 }}>{p.composer.slash}</code>
                  </span>
                  {p.max_risk !== "safe" && !p.ready
                    ? <span style={{ fontSize: 10, color: RISK_COLOR[p.max_risk] }}>{ko ? "권한필요" : "perm"}</span>
                    : <span style={{ color: "#cbd5e1", fontSize: 12 }}>{isOpen ? "▾" : "▸"}</span>}
                </button>
                {isOpen ? (
                  <div style={{ padding: "0 10px 9px 38px" }}>
                    <div style={{ fontSize: 11.5, color: "#6b7280", marginBottom: 6 }}>{p.description}</div>
                    <div style={{ display: "flex", gap: 6 }}>
                      {p.composer.field ? (
                        <input value={inputs[p.id] ?? ""} onChange={(e) => setInputs((s) => ({ ...s, [p.id]: e.target.value }))}
                          placeholder={p.composer.placeholder} style={field} disabled={!p.ready}
                          onKeyDown={(e) => { if (e.key === "Enter") run(p); }} />
                      ) : <div style={{ flex: 1, fontSize: 11.5, color: "#9ca3af", alignSelf: "center" }}>{p.composer.placeholder}</div>}
                      <button onClick={() => run(p)} disabled={!p.ready || busy === p.id} style={{ ...runBtn, opacity: p.ready ? 1 : 0.5 }}>
                        {busy === p.id ? "…" : (ko ? "수집" : "Run")}
                      </button>
                    </div>
                    {!p.ready ? <div style={{ fontSize: 11, color: RISK_COLOR[p.max_risk], marginTop: 5 }}>{ko ? "‘관리’ 탭에서 권한을 허용하세요." : "Allow permission in Manage."}</div> : null}
                    {result ? <div style={{ marginTop: 6, fontSize: 11.5, color: result.startsWith("✓") ? "#0d9488" : "#dc2626" }}>{result}</div> : null}
                  </div>
                ) : null}
              </div>
            );
          })}
          {mode === "use" && sources.filter((p) => p.enabled).length === 0 ? (
            <div style={{ fontSize: 12, color: "#9ca3af", padding: "10px 12px" }}>{ko ? "켜진 소스가 없습니다. ‘관리’에서 켜세요." : "No enabled sources — enable in Manage."}</div>
          ) : null}

          {/* MANAGE MODE — enable + permissions */}
          {mode === "manage" && (data?.marketplaces ?? Object.keys(byMarket)).map((mk) => (
            <section key={mk} style={{ marginTop: 8 }}>
              <div style={{ fontSize: 10, letterSpacing: 0.4, color: "#9ca3af", textTransform: "uppercase", margin: "2px 8px 4px" }}>{mk}</div>
              {(byMarket[mk] ?? []).map((p) => (
                <article key={p.id} style={{ border: "1px solid #f1f3f5", borderRadius: 10, padding: "9px 10px", margin: "0 2px 6px" }}>
                  <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                    <span style={{ fontSize: 15 }}>{ICON[p.icon] ?? "🔌"}</span>
                    <div style={{ flex: 1, minWidth: 0 }}>
                      <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
                        <strong style={{ fontSize: 12.5 }}>{p.name}</strong>
                        <span style={{ ...pill, background: `${RISK_COLOR[p.max_risk]}1a`, color: RISK_COLOR[p.max_risk] }}>{ko ? RISK_KO[p.max_risk] : p.max_risk}</span>
                      </div>
                      <div style={{ fontSize: 11, color: "#6b7280", marginTop: 2 }}>{p.description}</div>
                    </div>
                    <button onClick={() => toggle(p)} style={{ ...toggleBtn, background: p.enabled ? "#1f6feb" : "#e5e7eb", color: p.enabled ? "#fff" : "#6b7280" }}>{p.enabled ? "ON" : "OFF"}</button>
                  </div>
                  <div style={{ display: "flex", flexWrap: "wrap", gap: 5, marginTop: 8 }}>
                    {p.capabilities.map((c) => (
                      <span key={c.id} style={{ ...pill, border: "1px solid #e5e7eb", display: "flex", alignItems: "center", gap: 4 }}>
                        <span style={{ width: 6, height: 6, borderRadius: 6, background: RISK_COLOR[c.risk] }} />
                        <span style={{ color: "#4b5563" }}>{ko ? c.label : c.label_en}</span>
                        {c.risk !== "safe" ? (
                          c.state === "granted"
                            ? <button onClick={() => decide(p, c, "deny")} style={{ ...mini, color: "#16a34a" }}>{ko ? "허용됨✓" : "✓"}</button>
                            : <button onClick={() => decide(p, c, "grant")} style={{ ...mini, color: RISK_COLOR[c.risk] }}>{ko ? "허용" : "Allow"}</button>
                        ) : null}
                      </span>
                    ))}
                  </div>
                  {p.capabilities.some((c) => c.risk === "dangerous" && c.state !== "granted") ? (
                    <input value={phrase[p.id] ?? ""} onChange={(e) => setPhrase((s) => ({ ...s, [p.id]: e.target.value }))}
                      placeholder={ko ? `승인 문구: "${data?.pc_control_phrase ?? ""}"` : `Phrase: "${data?.pc_control_phrase ?? ""}"`}
                      style={{ ...field, marginTop: 7 }} />
                  ) : null}
                  {results[p.id] ? <div style={{ marginTop: 6, fontSize: 11, color: "#dc2626" }}>{results[p.id]}</div> : null}
                </article>
              ))}
            </section>
          ))}

          <p style={{ fontSize: 10, color: "#9ca3af", margin: "8px 8px 2px", lineHeight: 1.5 }}>
            {ko ? "수집(발화) ≠ 이해(개념) 분리 · 공개 소스만 · PC 제어는 읽기전용·허용목록·문구승인."
                : "Collected ≠ understood · public sources only · PC control read-only & phrase-gated."}
          </p>
        </div>
      </div>
    </>
  );
}

function tab(activeTab: boolean): React.CSSProperties {
  return { border: "none", borderRadius: 6, padding: "3px 10px", fontSize: 11.5, fontWeight: 700, cursor: "pointer",
    background: activeTab ? "#fff" : "transparent", color: activeTab ? "#1f2937" : "#9ca3af", boxShadow: activeTab ? "0 1px 2px rgba(0,0,0,0.08)" : "none" };
}
const row: React.CSSProperties = { display: "flex", alignItems: "center", gap: 9, width: "100%", background: "none", border: "none", cursor: "pointer", padding: "8px 10px", borderRadius: 10 };
const pill: React.CSSProperties = { fontSize: 9.5, padding: "1px 6px", borderRadius: 999, whiteSpace: "nowrap" };
const toggleBtn: React.CSSProperties = { border: "none", borderRadius: 7, padding: "4px 10px", fontSize: 10.5, fontWeight: 800, cursor: "pointer" };
const mini: React.CSSProperties = { background: "none", border: "none", fontSize: 10, fontWeight: 800, cursor: "pointer", padding: "0 1px" };
const field: React.CSSProperties = { flex: 1, width: "100%", background: "#fff", border: "1px solid #d1d5db", borderRadius: 8, color: "#1f2937", padding: "7px 9px", fontSize: 12, outline: "none" };
const runBtn: React.CSSProperties = { background: "#1f6feb", border: "none", borderRadius: 8, color: "#fff", padding: "7px 13px", fontSize: 12, fontWeight: 700, cursor: "pointer", whiteSpace: "nowrap" };
