"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { Activity, Brain, Globe, Play, ShieldCheck, Sparkles, Square } from "lucide-react";

type Language = "en" | "ko";
type AnyRecord = Record<string, any>;

type ActivityEntry = {
  id: string;
  at: string;
  cycle: number;
  thought: string;
  actions: string[];
  candidateDrafts: number;
  splatraFrames: number;
  curiosity: number;
  fatigue: number;
  nextDelay: number;
  ran: boolean;
  reason: string;
};

const copy = {
  en: {
    title: "Autonomous Agent",
    sub: "ATANOR drives itself server-side: bounded public-web reading, candidate drafting, and SPLATRA proof frames — on its own cadence, even with this tab closed. Nothing is promoted or written without your approval.",
    start: "Begin autonomous run",
    stop: "Stop",
    confirmLabel: "I authorize ATANOR to run autonomously (read-only web, candidate-only, no production write).",
    liveWebLabel: "Read the LIVE public web (real bounded GETs, robots-respected, login/payment/download blocked).",
    idle: "Idle — operator confirmation required before any cycle.",
    running: "Running autonomously (server-side)",
    stopped: "Stopped",
    feed: "Live activity",
    empty: "No cycles yet. Authorize and begin to watch ATANOR think on its own.",
    cycle: "cycle",
    drafts: "candidate drafts",
    frames: "SPLATRA frames",
    nextIn: "next in",
    curiosity: "curiosity",
    fatigue: "fatigue",
    locks: "Safety locks",
    serverNote: "Driven by a server-side daemon — closing this tab does not stop it.",
  },
  ko: {
    title: "자율 에이전트",
    sub: "ATANOR가 서버에서 스스로 구동합니다: 공개 웹 읽기·후보 초안·SPLATRA 증명 프레임을 자신의 리듬으로, 이 탭을 닫아도. 승인 없이는 무엇도 승격·기록되지 않습니다.",
    start: "자율 구동 시작",
    stop: "정지",
    confirmLabel: "ATANOR의 자율 구동을 승인합니다 (읽기 전용 웹, 후보 전용, 운영 기록 없음).",
    liveWebLabel: "실시간 공개 웹 읽기 (실제 제한 GET·robots 준수·로그인/결제/다운로드 차단).",
    idle: "대기 — 모든 사이클 전 오퍼레이터 확인이 필요합니다.",
    running: "자율 구동 중 (서버측)",
    stopped: "정지됨",
    feed: "실시간 활동",
    empty: "아직 사이클이 없습니다. 승인 후 시작하면 ATANOR가 스스로 사고하는 과정을 볼 수 있습니다.",
    cycle: "사이클",
    drafts: "후보 초안",
    frames: "SPLATRA 프레임",
    nextIn: "다음까지",
    curiosity: "호기심",
    fatigue: "피로",
    locks: "안전 잠금",
    serverNote: "서버측 데몬이 구동합니다 — 이 탭을 닫아도 멈추지 않습니다.",
  },
} satisfies Record<Language, Record<string, string>>;

const ACTION_LABELS: Record<string, { en: string; ko: string }> = {
  open_web_live_read: { en: "read LIVE public web", ko: "실시간 공개 웹 읽기" },
  web_explorer_fixture_step: { en: "read sample web evidence", ko: "샘플 웹 근거 읽기" },
  review_import: { en: "imported drafts to review queue", ko: "검토 큐에 초안 등록" },
  splatra_frames: { en: "rendered SPLATRA proof frame", ko: "SPLATRA 증명 프레임 생성" },
  host_status_checks: { en: "host status check (read-only)", ko: "호스트 상태 점검 (읽기 전용)" },
  review_queue_pressure_request_review: { en: "paused to request human review", ko: "사람 검토 요청을 위해 일시정지" },
};

function labelAction(raw: string, language: Language): string {
  const key = raw.split(":")[0];
  const found = ACTION_LABELS[key];
  if (!found) return raw;
  const suffix = raw.includes(":") ? ` (${raw.split(":")[1]})` : "";
  return found[language] + suffix;
}

function num(value: unknown, fallback = 0): number {
  const n = typeof value === "number" ? value : Number(value);
  return Number.isFinite(n) ? n : fallback;
}

async function callJson(path: string, init?: RequestInit): Promise<AnyRecord | null> {
  try {
    const res = await fetch(path, { cache: "no-store", ...init });
    return (await res.json()) as AnyRecord;
  } catch {
    return null;
  }
}

const SCHED = "/api/agentic-os/policy-scheduler";
const POLL_MS = 3500;
const MAX_FEED = 24;

// Build a feed entry from a server-side activity_log record (_summarize_tick).
function toEntry(rec: AnyRecord, language: Language): ActivityEntry {
  const actions: string[] = Array.isArray(rec.actions) ? rec.actions : [];
  const ran = Boolean(rec.ran);
  const reason = String(rec.reason ?? "");
  const curiosity = num(rec.curiosity);
  const actionPhrase = actions.length
    ? actions.map((a) => labelAction(a, language)).join(", ")
    : language === "ko" ? "관찰만 수행" : "observed only";
  const driver = rec.policy_reason ? `${rec.policy_reason} · ` : "";
  const thought = ran
    ? `${driver}${language === "ko" ? `호기심 ${curiosity.toFixed(2)} — ${actionPhrase}` : `curiosity ${curiosity.toFixed(2)} — ${actionPhrase}`}`
    : `${language === "ko" ? "쉼" : "rest"}: ${reason}`;
  return {
    id: `${rec.at ?? ""}-${rec.cycle ?? Math.random()}`,
    at: rec.at ? new Date(rec.at).toLocaleTimeString() : "",
    cycle: num(rec.cycle),
    thought,
    actions,
    candidateDrafts: num(rec.candidate_drafts),
    splatraFrames: num(rec.splatra_frames),
    curiosity,
    fatigue: num(rec.fatigue),
    nextDelay: num(rec.next_delay_sec, 5),
    ran,
    reason,
  };
}

export default function AutonomousAgentPanel({ language }: { language: Language }) {
  const t = copy[language];
  const [running, setRunning] = useState(false);
  const [confirmed, setConfirmed] = useState(false);
  const [liveWeb, setLiveWeb] = useState(false);
  const [status, setStatus] = useState<AnyRecord | null>(null);
  const [feed, setFeed] = useState<ActivityEntry[]>([]);
  const [busy, setBusy] = useState(false);

  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const pollingRef = useRef(false);

  const clearTimer = useCallback(() => {
    if (timerRef.current) {
      clearTimeout(timerRef.current);
      timerRef.current = null;
    }
  }, []);

  const applyStatus = useCallback((payload: AnyRecord, language2: Language) => {
    setStatus(payload);
    setRunning(Boolean(payload.daemon_running));
    const log: AnyRecord[] = Array.isArray(payload.activity_log) ? payload.activity_log : [];
    if (log.length) {
      const entries = log.map((rec) => toEntry(rec, language2)).reverse().slice(0, MAX_FEED);
      setFeed(entries);
    }
  }, []);

  // Poll the SERVER daemon's status — the loop runs server-side; we only observe.
  const poll = useCallback(async () => {
    if (!pollingRef.current) return;
    const payload = await callJson(`${SCHED}/daemon/status`);
    if (payload) applyStatus(payload, language);
    if (!pollingRef.current) return;
    if (payload && payload.daemon_running === false) {
      pollingRef.current = false;
      clearTimer();
      return;
    }
    timerRef.current = setTimeout(poll, POLL_MS);
  }, [applyStatus, clearTimer, language]);

  const start = useCallback(async () => {
    if (!confirmed || busy) return;
    setBusy(true);
    const payload = await callJson(`${SCHED}/daemon/start`, {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({
        operator_confirmed: true,
        live_web: liveWeb,
        max_cycles: 2000,
        max_runtime_sec: 3600,
        min_interval_sec: 2,
        max_interval_sec: 30,
        allow_web_explorer: true,
        allow_review_import: true,
        allow_splatra_generation: true,
        allow_host_executor_status_only: true,
      }),
    });
    setBusy(false);
    if (!payload || payload.allowed === false || payload.daemon_running === false) {
      setStatus(payload);
      return;
    }
    setRunning(true);
    pollingRef.current = true;
    clearTimer();
    timerRef.current = setTimeout(poll, 700);
  }, [confirmed, busy, liveWeb, poll, clearTimer]);

  const stop = useCallback(async () => {
    pollingRef.current = false;
    clearTimer();
    const payload = await callJson(`${SCHED}/daemon/stop`, { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify({ reason: "operator_stop" }) });
    if (payload) applyStatus(payload, language);
    setRunning(false);
  }, [applyStatus, clearTimer, language]);

  // On mount: read current daemon status (it may already be running server-side).
  useEffect(() => {
    callJson(`${SCHED}/daemon/status`).then((s) => {
      if (!s) return;
      applyStatus(s, language);
      if (s.daemon_running) {
        pollingRef.current = true;
        timerRef.current = setTimeout(poll, POLL_MS);
      }
    });
    return () => {
      pollingRef.current = false;
      clearTimer();
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const flags = (status?.safety_flags as AnyRecord) ?? (status?.scheduler_state as AnyRecord)?.safety_flags ?? {};
  const locks = [
    ["production_store_mutated", flags.production_store_mutated],
    ["local_brain_write", flags.local_brain_write],
    ["candidate_promotion", flags.candidate_promotion],
    ["human_approval_required", flags.human_approval_required],
    ["scheduler_opt_in", flags.scheduler_opt_in],
    ["no_daemon_autostart", flags.no_daemon_autostart],
  ].filter(([, v]) => v !== undefined);

  const schedReason = (status?.scheduler_state as AnyRecord)?.stopped_reason || status?.stopped_reason;
  const stateLabel = running ? t.running : schedReason && schedReason !== "disabled" ? `${t.stopped} · ${schedReason}` : t.idle;

  return (
    <section className="autonomous-agent" aria-label={t.title} style={{ display: "grid", gap: 16, color: "#dbe6ff" }}>
      <header style={{ display: "grid", gap: 8 }}>
        <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
          <Brain size={20} color="#6fa8ff" />
          <h2 style={{ margin: 0, fontSize: 22, color: "#eaf1ff" }}>{t.title}</h2>
          <span style={{ marginLeft: "auto", display: "inline-flex", alignItems: "center", gap: 7, fontSize: 12.5, color: running ? "#7fd8a6" : "#8a93a8" }}>
            <span style={{ width: 9, height: 9, borderRadius: "50%", background: running ? "#48d18a" : "#56607a", boxShadow: running ? "0 0 10px #48d18a" : "none", animation: running ? "aa-pulse 1.4s ease-in-out infinite" : "none" }} />
            {stateLabel}
          </span>
        </div>
        <p style={{ margin: 0, color: "#9aa4bd", fontSize: 13, lineHeight: 1.55, maxWidth: 720 }}>{t.sub}</p>
      </header>

      <div style={{ display: "grid", gap: 12, border: "1px solid #1d2636", borderRadius: 14, padding: "14px 16px", background: "rgba(13,18,30,0.5)" }}>
        <label style={{ display: "flex", alignItems: "flex-start", gap: 9, fontSize: 12.5, color: "#b6c1da", cursor: running ? "default" : "pointer" }}>
          <input type="checkbox" checked={confirmed} disabled={running} onChange={(e) => setConfirmed(e.target.checked)} style={{ marginTop: 2 }} />
          <span>{t.confirmLabel}</span>
        </label>
        <label style={{ display: "flex", alignItems: "flex-start", gap: 9, fontSize: 12.5, color: "#b6c1da", cursor: running ? "default" : "pointer" }}>
          <input type="checkbox" checked={liveWeb} disabled={running} onChange={(e) => setLiveWeb(e.target.checked)} style={{ marginTop: 2 }} />
          <span style={{ display: "inline-flex", alignItems: "center", gap: 5 }}><Globe size={12} color="#6fa8ff" /> {t.liveWebLabel}</span>
        </label>
        <div style={{ display: "flex", gap: 10, flexWrap: "wrap", alignItems: "center" }}>
          {!running ? (
            <button type="button" onClick={start} disabled={!confirmed || busy}
              style={{ display: "inline-flex", alignItems: "center", gap: 7, padding: "9px 16px", borderRadius: 10, border: "1px solid #2f6df0", background: confirmed && !busy ? "#2f6df0" : "#1b2740", color: confirmed && !busy ? "#fff" : "#6b7488", fontSize: 13.5, cursor: confirmed && !busy ? "pointer" : "not-allowed" }}>
              <Play size={15} /> {t.start}
            </button>
          ) : (
            <button type="button" onClick={stop}
              style={{ display: "inline-flex", alignItems: "center", gap: 7, padding: "9px 16px", borderRadius: 10, border: "1px solid #4a3a4a", background: "#2a1e2a", color: "#f0c0c8", fontSize: 13.5, cursor: "pointer" }}>
              <Square size={14} /> {t.stop}
            </button>
          )}
          <span style={{ fontSize: 11, color: "#6b7488" }}>{t.serverNote}</span>
        </div>
        {locks.length ? (
          <div style={{ display: "flex", flexWrap: "wrap", gap: 6, alignItems: "center" }}>
            <ShieldCheck size={13} color="#7fd8a6" />
            {locks.map(([name, value]) => (
              <em key={String(name)} style={{ fontStyle: "normal", fontSize: 11, color: value ? "#f5b362" : "#7fd8a6", border: `1px solid ${value ? "#4a3a23" : "#244a36"}`, borderRadius: 10, padding: "2px 8px" }}>
                {String(name)}={String(value)}
              </em>
            ))}
          </div>
        ) : null}
      </div>

      <section aria-label={t.feed} style={{ display: "grid", gap: 8 }}>
        <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
          <Activity size={16} color="#6fa8ff" />
          <strong style={{ fontSize: 14, color: "#dbe6ff" }}>{t.feed}</strong>
        </div>
        {feed.length === 0 ? (
          <p style={{ color: "#6b7488", fontSize: 12.5, margin: "4px 0 0" }}>{t.empty}</p>
        ) : (
          <ol style={{ listStyle: "none", margin: 0, padding: 0, display: "grid", gap: 8 }}>
            {feed.map((e) => (
              <li key={e.id} style={{ border: "1px solid #1b2436", borderRadius: 12, padding: "10px 13px", background: e.ran ? "rgba(15,22,38,0.55)" : "rgba(38,28,20,0.4)", display: "grid", gap: 6 }}>
                <div style={{ display: "flex", alignItems: "center", gap: 8, fontSize: 11.5, color: "#7d869b" }}>
                  <span style={{ color: "#6fa8ff" }}>{t.cycle} {e.cycle}</span>
                  <span>· {e.at}</span>
                  <span style={{ marginLeft: "auto" }}>{t.nextIn} {e.nextDelay.toFixed(1)}s</span>
                </div>
                <p style={{ margin: 0, fontSize: 13, color: "#e2e9fb", lineHeight: 1.5 }}>
                  {e.actions.some((a) => a.startsWith("open_web") || a.startsWith("web_explorer")) ? <Globe size={12} style={{ verticalAlign: "-1px", marginRight: 5, color: "#6fa8ff" }} /> : <Sparkles size={12} style={{ verticalAlign: "-1px", marginRight: 5, color: "#c08af0" }} />}
                  {e.thought}
                </p>
                <div style={{ display: "flex", flexWrap: "wrap", gap: 6, fontSize: 10.5, color: "#9aa4bd" }}>
                  <span style={{ border: "1px solid #243049", borderRadius: 8, padding: "1px 7px" }}>{t.drafts} {e.candidateDrafts}</span>
                  <span style={{ border: "1px solid #243049", borderRadius: 8, padding: "1px 7px" }}>{t.frames} {e.splatraFrames}</span>
                  <span style={{ border: "1px solid #243049", borderRadius: 8, padding: "1px 7px" }}>{t.curiosity} {e.curiosity.toFixed(2)}</span>
                  <span style={{ border: "1px solid #243049", borderRadius: 8, padding: "1px 7px" }}>{t.fatigue} {e.fatigue.toFixed(2)}</span>
                </div>
              </li>
            ))}
          </ol>
        )}
      </section>

      <style>{`@keyframes aa-pulse { 0%,100% { opacity: 1; } 50% { opacity: 0.35; } }`}</style>
    </section>
  );
}
