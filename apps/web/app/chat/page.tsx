"use client";

import { useEffect, useRef, useState } from "react";

type Step = {
  step?: number;
  type?: string;
  concept_id?: string;
  label?: string;
  source?: string;
  fact?: string;
  edge?: string;
  from?: string;
  relation?: string;
  to?: string;
};

type Certificate = {
  derivation_kind?: string;
  anchor_concept?: { id?: string; label?: string; match?: string; match_score?: number } | string;
  steps?: Step[];
  evidence_concepts?: string[];
  confidence?: number;
  confidence_basis?: string;
  guarantees?: Record<string, unknown>;
};

type FoldTrace = {
  fold_driver_mode?: string;
  answer_changed?: boolean;
  folded_core?: string[];
  answer_evidence?: string[];
  agreement_overlap?: number;
  agreement_recall?: number;
  folded_global_coherence?: number;
  fold_timing_ms?: number;
};

type AnswerPayload = {
  answer?: string;
  confidence?: number;
  answer_kind?: string;
  reasoning_certificate?: Certificate;
  compact_trace?: { holographic_fold?: FoldTrace };
};

type Turn = {
  id: string;
  role: "user" | "atanor";
  text: string;
  question?: string;
  payload?: AnswerPayload;
  at: string;
};

const T = {
  ko: {
    title: "대화록",
    sub: "텍스트 세션 · 추론 인증서 발급",
    back: "← 대시보드",
    placeholder: "ATANOR에게 질문하기…",
    send: "보내기",
    thinking: "추론 중…",
    cert: "추론 인증서",
    showCert: "추론 인증서 보기",
    hideCert: "접기",
    issue: "PDF로 발급",
    noCert: "이 답변은 추론 인증서를 노출하지 않는 경로입니다.",
    anchor: "기준 개념",
    derivation: "도출 과정",
    evidence: "근거 개념",
    guarantees: "보증",
    fold: "추론핵 일치(홀로그래픽 폴딩)",
    confidence: "신뢰도",
    empty: "질문을 입력하면 답변과 함께 추론 인증서를 발급할 수 있습니다.",
  },
  en: {
    title: "Transcript",
    sub: "Text session · issue reasoning certificate",
    back: "← Dashboard",
    placeholder: "Ask ATANOR…",
    send: "Send",
    thinking: "Reasoning…",
    cert: "Reasoning Certificate",
    showCert: "Show certificate",
    hideCert: "Hide",
    issue: "Export PDF",
    noCert: "This answer came from a path that does not expose a reasoning certificate.",
    anchor: "Anchor concept",
    derivation: "Derivation",
    evidence: "Evidence concepts",
    guarantees: "Guarantees",
    fold: "Reasoning-core agreement (holographic fold)",
    confidence: "Confidence",
    empty: "Ask a question to get an answer with an exportable reasoning certificate.",
  },
};

function anchorLabel(anchor: Certificate["anchor_concept"]): string {
  if (!anchor) return "";
  if (typeof anchor === "string") return anchor;
  return anchor.label || anchor.id || "";
}

export default function ChatPage() {
  const [lang, setLang] = useState<"ko" | "en">("ko");
  const [turns, setTurns] = useState<Turn[]>([]);
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  const [openCert, setOpenCert] = useState<Record<string, boolean>>({});
  const [printTurn, setPrintTurn] = useState<Turn | null>(null);
  const endRef = useRef<HTMLDivElement | null>(null);
  const tr = T[lang];

  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [turns, busy]);

  useEffect(() => {
    if (!printTurn) return;
    const timer = window.setTimeout(() => {
      window.print();
      setPrintTurn(null);
    }, 60);
    return () => window.clearTimeout(timer);
  }, [printTurn]);

  async function send() {
    const question = input.trim();
    if (!question || busy) return;
    const now = new Date();
    const userTurn: Turn = { id: `u${now.getTime()}`, role: "user", text: question, at: now.toISOString() };
    // Send the recent turns so follow-ups ("explain it more simply") resolve
    // against the prior topic instead of abstaining with no context.
    const priorContext = turns.slice(-6).map((t) => ({ role: t.role, text: t.text }));
    setTurns((prev) => [...prev, userTurn]);
    setInput("");
    setBusy(true);
    try {
      const res = await fetch("/api/chat/atanor", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          question,
          language: lang,
          mode: "conversation",
          brain_mode: "conversation",
          web_search: false,
          conversation_context: priorContext,
        }),
      });
      const data = await res.json();
      const payload: AnswerPayload = data.result || data;
      const atanorTurn: Turn = {
        id: `a${Date.now()}`,
        role: "atanor",
        text: payload.answer || (lang === "ko" ? "(답변 없음)" : "(no answer)"),
        question,
        payload,
        at: new Date().toISOString(),
      };
      setTurns((prev) => [...prev, atanorTurn]);
    } catch (error) {
      setTurns((prev) => [
        ...prev,
        { id: `e${Date.now()}`, role: "atanor", text: lang === "ko" ? "연결 오류가 발생했습니다." : "Connection error.", at: new Date().toISOString() },
      ]);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="cx-root">
      <style>{CSS}</style>

      <header className="cx-top">
        <a className="cx-back" href="/?lang=ko&section=home&workspace=lab">{tr.back}</a>
        <div className="cx-title">
          <strong>ATANOR · {tr.title}</strong>
          <span>{tr.sub}</span>
        </div>
        <div className="cx-lang">
          <button data-active={lang === "en"} onClick={() => setLang("en")}>EN</button>
          <button data-active={lang === "ko"} onClick={() => setLang("ko")}>KO</button>
        </div>
      </header>

      <main className="cx-thread">
        {turns.length === 0 ? <p className="cx-empty">{tr.empty}</p> : null}
        {turns.map((turn) => (
          <div key={turn.id} className={`cx-turn cx-${turn.role}`}>
            <div className="cx-bubble">{turn.text}</div>
            {turn.role === "atanor" ? (
              <div className="cx-meta">
                {turn.payload?.reasoning_certificate ? (
                  <>
                    <button
                      className="cx-link"
                      onClick={() => setOpenCert((prev) => ({ ...prev, [turn.id]: !prev[turn.id] }))}
                    >
                      {openCert[turn.id] ? tr.hideCert : tr.showCert}
                    </button>
                    <button className="cx-issue" onClick={() => setPrintTurn(turn)}>{tr.issue}</button>
                    {openCert[turn.id] ? <Cert turn={turn} tr={tr} /> : null}
                  </>
                ) : (
                  <span className="cx-nocert">{tr.noCert}</span>
                )}
              </div>
            ) : null}
          </div>
        ))}
        {busy ? <div className="cx-turn cx-atanor"><div className="cx-bubble cx-thinking">{tr.thinking}</div></div> : null}
        <div ref={endRef} />
      </main>

      <footer className="cx-composer">
        <textarea
          value={input}
          onChange={(event) => setInput(event.target.value)}
          onKeyDown={(event) => {
            if (event.key === "Enter" && !event.shiftKey) {
              event.preventDefault();
              send();
            }
          }}
          placeholder={tr.placeholder}
          rows={1}
        />
        <button onClick={send} disabled={busy || !input.trim()}>{tr.send}</button>
      </footer>

      {printTurn ? <CertPrint turn={printTurn} tr={tr} lang={lang} /> : null}
    </div>
  );
}

function Cert({ turn, tr }: { turn: Turn; tr: typeof T["ko"] }) {
  const cert = turn.payload?.reasoning_certificate;
  const fold = turn.payload?.compact_trace?.holographic_fold;
  if (!cert) return null;
  return (
    <div className="cx-cert">
      <div className="cx-cert-row"><b>{tr.anchor}</b><span>{anchorLabel(cert.anchor_concept)} · {cert.derivation_kind}</span></div>
      <div className="cx-cert-block">
        <b>{tr.derivation}</b>
        <ol>
          {(cert.steps || []).map((step, index) => (
            <li key={index}>
              {step.type === "graph_relation"
                ? <code>{step.from} —{step.relation}→ {step.to}</code>
                : <span>{step.fact || step.label}</span>}
            </li>
          ))}
        </ol>
      </div>
      {cert.evidence_concepts?.length ? (
        <div className="cx-cert-row"><b>{tr.evidence}</b><span>{cert.evidence_concepts.join(", ")}</span></div>
      ) : null}
      <div className="cx-cert-block">
        <b>{tr.guarantees}</b>
        <ul className="cx-guarantees">
          {Object.entries(cert.guarantees || {}).map(([key, value]) => (
            <li key={key}>✓ {key}: {String(value)}</li>
          ))}
        </ul>
      </div>
      {fold ? (
        <div className="cx-cert-row">
          <b>{tr.fold}</b>
          <span>recall {fold.agreement_recall} · overlap {fold.agreement_overlap} · coherence {Number(fold.folded_global_coherence || 0).toFixed(2)} · {fold.fold_timing_ms}ms · answer_changed={String(fold.answer_changed)}</span>
        </div>
      ) : null}
      {typeof cert.confidence === "number" ? (
        <div className="cx-cert-row"><b>{tr.confidence}</b><span>{cert.confidence} — {cert.confidence_basis}</span></div>
      ) : null}
    </div>
  );
}

function CertPrint({ turn, tr, lang }: { turn: Turn; tr: typeof T["ko"]; lang: "ko" | "en" }) {
  const cert = turn.payload?.reasoning_certificate;
  const fold = turn.payload?.compact_trace?.holographic_fold;
  return (
    <div className="cx-print">
      <div className="cx-print-head">
        <h1>ATANOR {lang === "ko" ? "추론 인증서" : "Reasoning Certificate"}</h1>
        <p>{new Date(turn.at).toLocaleString(lang === "ko" ? "ko-KR" : "en-US")} · v0.1.2</p>
      </div>
      {turn.question ? (
        <section>
          <h2>{lang === "ko" ? "질문" : "Question"}</h2>
          <p className="cx-print-answer">{turn.question}</p>
        </section>
      ) : null}
      <section>
        <h2>{lang === "ko" ? "답변" : "Answer"}</h2>
        <p className="cx-print-answer">{turn.text}</p>
      </section>
      {cert ? (
        <>
          <section>
            <h2>{tr.anchor}</h2>
            <p>{anchorLabel(cert.anchor_concept)} · {cert.derivation_kind}</p>
          </section>
          <section>
            <h2>{tr.derivation}</h2>
            <ol>
              {(cert.steps || []).map((step, index) => (
                <li key={index}>
                  {step.type === "graph_relation" ? `${step.from} —${step.relation}→ ${step.to}` : (step.fact || step.label)}
                </li>
              ))}
            </ol>
          </section>
          {cert.evidence_concepts?.length ? (
            <section><h2>{tr.evidence}</h2><p>{cert.evidence_concepts.join(", ")}</p></section>
          ) : null}
          <section>
            <h2>{tr.guarantees}</h2>
            <ul>
              {Object.entries(cert.guarantees || {}).map(([key, value]) => (
                <li key={key}>{value ? "✓" : "✗"} {key}</li>
              ))}
            </ul>
          </section>
          {fold ? (
            <section>
              <h2>{tr.fold}</h2>
              <p>recall {fold.agreement_recall} · overlap {fold.agreement_overlap} · coherence {Number(fold.folded_global_coherence || 0).toFixed(2)} · {fold.fold_timing_ms}ms · answer_changed={String(fold.answer_changed)}</p>
            </section>
          ) : null}
        </>
      ) : null}
      <footer className="cx-print-foot">
        {lang === "ko"
          ? "이 답변은 외부 LLM 없이 ATANOR의 온톨로지 그래프에서 도출되었으며, 모든 단계가 그래프 노드/엣지로 추적 가능합니다."
          : "Derived from ATANOR's ontology graph with no external LLM; every step is traceable to graph nodes/edges."}
      </footer>
    </div>
  );
}

const CSS = `
.cx-root{position:fixed;inset:0;display:flex;flex-direction:column;background:#07080c;color:#e8eaf0;font-family:ui-sans-serif,system-ui,'Segoe UI',sans-serif;}
.cx-top{display:flex;align-items:center;gap:16px;padding:14px 22px;border-bottom:1px solid #1b1f2a;}
.cx-back{color:#8ab4ff;text-decoration:none;font-size:13px;}
.cx-title{display:flex;flex-direction:column;flex:1;}
.cx-title strong{font-size:15px;letter-spacing:.04em;}
.cx-title span{font-size:11px;color:#7d869b;}
.cx-lang button{background:transparent;border:1px solid #2a2f3d;color:#9aa3b6;border-radius:6px;padding:4px 9px;margin-left:6px;cursor:pointer;font-size:12px;}
.cx-lang button[data-active="true"]{background:#1b2540;color:#cfe0ff;border-color:#3a4a78;}
.cx-thread{flex:1;overflow-y:auto;padding:22px;display:flex;flex-direction:column;gap:16px;max-width:860px;width:100%;margin:0 auto;}
.cx-empty{color:#6b7488;text-align:center;margin-top:18vh;font-size:13px;}
.cx-turn{display:flex;flex-direction:column;}
.cx-turn.cx-user{align-items:flex-end;}
.cx-bubble{max-width:80%;padding:11px 15px;border-radius:14px;line-height:1.6;font-size:14px;white-space:pre-wrap;}
.cx-user .cx-bubble{background:#1b2540;color:#eaf1ff;border-bottom-right-radius:4px;}
.cx-atanor .cx-bubble{background:#11141d;border:1px solid #1e2330;border-bottom-left-radius:4px;}
.cx-thinking{color:#7d869b;font-style:italic;}
.cx-meta{display:flex;flex-wrap:wrap;align-items:center;gap:10px;margin-top:7px;}
.cx-link{background:transparent;border:none;color:#8ab4ff;cursor:pointer;font-size:12px;padding:0;}
.cx-issue{background:#16203a;border:1px solid #2f3f6b;color:#cfe0ff;border-radius:7px;padding:5px 11px;cursor:pointer;font-size:12px;}
.cx-issue:hover{background:#1c2a4d;}
.cx-nocert{color:#6b7488;font-size:12px;}
.cx-cert{margin-top:10px;width:100%;background:#0c0f17;border:1px solid #1c2230;border-radius:10px;padding:14px 16px;font-size:13px;}
.cx-cert-row{display:flex;gap:10px;padding:5px 0;border-bottom:1px solid #161b27;}
.cx-cert-row b{color:#8a93a8;min-width:140px;font-weight:600;}
.cx-cert-row span{color:#d4dbe9;}
.cx-cert-block{padding:7px 0;}
.cx-cert-block b{color:#8a93a8;display:block;margin-bottom:6px;}
.cx-cert-block ol{margin:0;padding-left:20px;}
.cx-cert-block li{padding:3px 0;color:#d4dbe9;}
.cx-cert-block code{color:#9cc7ff;font-size:12.5px;}
.cx-guarantees{list-style:none;padding:0;margin:0;display:flex;flex-wrap:wrap;gap:6px 16px;}
.cx-guarantees li{color:#7fd8a6;font-size:12px;}
.cx-composer{display:flex;gap:10px;padding:14px 22px;border-top:1px solid #1b1f2a;max-width:860px;width:100%;margin:0 auto;}
.cx-composer textarea{flex:1;resize:none;background:#11141d;border:1px solid #232838;color:#e8eaf0;border-radius:10px;padding:12px 14px;font-size:14px;font-family:inherit;line-height:1.5;}
.cx-composer button{background:#1b2540;border:1px solid #3a4a78;color:#cfe0ff;border-radius:10px;padding:0 20px;cursor:pointer;font-size:14px;}
.cx-composer button:disabled{opacity:.45;cursor:default;}
.cx-print{display:none;}
@media print{
  body *{visibility:hidden;}
  .cx-print,.cx-print *{visibility:visible;}
  .cx-print{display:block;position:absolute;inset:0;background:#fff;color:#111;padding:40px 48px;font-family:'Times New Roman',serif;}
  .cx-print h1{font-size:22px;margin:0;}
  .cx-print-head{border-bottom:2px solid #111;padding-bottom:10px;margin-bottom:18px;}
  .cx-print-head p{color:#555;font-size:12px;margin:4px 0 0;}
  .cx-print h2{font-size:13px;text-transform:uppercase;letter-spacing:.06em;color:#444;margin:18px 0 6px;}
  .cx-print-answer{font-size:14px;line-height:1.7;}
  .cx-print ol,.cx-print ul{margin:0;padding-left:22px;font-size:13px;line-height:1.6;}
  .cx-print-foot{margin-top:26px;padding-top:12px;border-top:1px solid #999;font-size:11px;color:#555;font-style:italic;}
}
`;
