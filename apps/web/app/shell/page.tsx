"use client";

import { useEffect, useRef, useState } from "react";
import HologramVoiceOrb, { HologramVoiceOrbState } from "../HologramVoiceOrb";
import PureField from "../PureField";

// The VM (and any GPU-less machine) renders WebGL through SwiftShader/llvmpipe;
// full particle budgets would crawl. Detect it once and scale down honestly.
function autoDensity(): number {
  try {
    const c = document.createElement("canvas");
    const gl = c.getContext("webgl");
    const ext = gl?.getExtension("WEBGL_debug_renderer_info");
    const r = ext && gl ? String(gl.getParameter(ext.UNMASKED_RENDERER_WEBGL)) : "";
    if (/swiftshader|llvmpipe|software/i.test(r)) return 0.22;
  } catch { /* default below */ }
  return 1;
}

/* ATANOR OS particle shell — the machine boots into this face.
   The orb is the SAME HologramVoiceOrb the main program uses (43k-point
   Three.js hologram: cyan/violet Siri ribbons + glass shell + white core),
   not a lookalike. One codebase, one design language (#d2521f accent,
   Apple restraint × Palantir truth).
   HONESTY CONTRACT: orb motion is driven by the REAL pipeline state, never
   faked. OS actions run only through the trust-tier approval gate. */

type ShellState = "idle" | "listening" | "thinking" | "speaking" | "offline";

export default function ShellPage() {
  // overlay mode (?overlay=1): transparent background so the orb floats over the
  // real desktop as an always-on-top layer (the GNOME extension pins the window).
  // wallpaper mode (?wallpaper=1): this surface BECOMES the desktop background —
  // orb-wallpaper.sh retypes the window to _NET_WM_WINDOW_TYPE_DESKTOP, so the
  // SPLATRA field runs as the wallpaper layer with every app window above it.
  const params = typeof window !== "undefined" ? new URLSearchParams(window.location.search) : null;
  const overlay = params?.get("overlay") === "1";
  const wallpaper = params?.get("wallpaper") === "1";
  const [density, setDensity] = useState(1);
  useEffect(() => {
    setDensity(autoDensity());
    // distinct title so the desktop-layer script and the GNOME extension can
    // tell the wallpaper surface from a normal ATANOR app window
    if (wallpaper) document.title = "ATANOR WALLPAPER";
  }, [wallpaper]);
  const stateRef = useRef<ShellState>("idle");
  const [shellState, setShellState] = useState<ShellState>("idle");
  const [question, setQuestion] = useState("");
  const [answer, setAnswer] = useState("");
  const recRef = useRef<MediaRecorder | null>(null);
  const chunksRef = useRef<Blob[]>([]);
  type Pending = { token: string; text: string; kind?: string };
  const [pending, setPendingState] = useState<Pending | null>(null);
  const pendingRef = useRef<Pending | null>(null);
  const setPending = (p: Pending | null) => { pendingRef.current = p; setPendingState(p); };
  const [tier, setTier] = useState<number>(1);
  const TIER_NAMES = ["관찰", "승인", "가드", "자율"];

  const setState = (s: ShellState) => { stateRef.current = s; setShellState(s); };

  // real state → the orb's own vocabulary (approval hold and engine-down included)
  const orbState: HologramVoiceOrbState = pending
    ? "approval_needed"
    : shellState === "offline"
      ? "blocked"
      : shellState;

  // engine liveness is BUILT IN: the engine takes minutes to wake on boot, and
  // that is a normal state, not a failure. Poll until it answers, auto-recover.
  const [engineUp, setEngineUp] = useState<boolean | null>(null);
  useEffect(() => {
    let stop = false;
    const poll = async () => {
      try {
        const r = await fetch("/api/os-action/status", { signal: AbortSignal.timeout(4000) });
        const ok = r.ok;
        if (stop) return;
        setEngineUp(ok);
        if (ok) {
          try { const s = await r.json(); if (typeof s?.tier === "number") setTier(s.tier); } catch { /* body optional */ }
          if (stateRef.current === "offline") setState("idle");
        }
      } catch { if (!stop) setEngineUp(false); }
    };
    void poll();
    const iv = setInterval(poll, 5000);
    return () => { stop = true; clearInterval(iv); };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const changeTier = async (t: number) => {
    setTier(t);
    // picking a tier by hand exits manual mode — two active pills at once was a lie
    if (t !== 0) setManual(false);
    await fetch("/api/os-action/tier", { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify({ tier: t }) }).catch(() => {});
  };

  const approveNow = async () => {
    if (!pendingRef.current) return;
    const r = await fetch("/api/os-action/approve", { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify({ token: pendingRef.current.token }) }).then((x) => x.json()).catch(() => null);
    setPending(null);
    if (r) { setAnswer(`${r.detail || "실행했습니다."} ${r.stdout ? "— " + String(r.stdout).slice(0, 160) : ""}`.trim()); speak(r.detail || "실행했습니다."); }
  };
  const rejectNow = async () => {
    if (!pendingRef.current) return;
    await fetch("/api/os-action/reject", { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify({ token: pendingRef.current.token }) }).catch(() => {});
    setPending(null); setAnswer("취소했습니다.");
  };

  const speak = (text: string) => {
    try {
      const u = new SpeechSynthesisUtterance(text);
      u.lang = /[가-힣]/.test(text) ? "ko-KR" : "en-US";
      u.onend = () => setState("idle");
      setState("speaking");
      speechSynthesis.speak(u);
    } catch { setState("idle"); }
  };

  // Ultimate-style: while an action holds the stage, the orb docks small to the
  // bottom-right; it returns to center when the action's moment passes.
  const [docked, setDocked] = useState(false);
  const dockTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const dockFor = (ms: number) => {
    setDocked(true);
    if (dockTimer.current) clearTimeout(dockTimer.current);
    dockTimer.current = setTimeout(() => setDocked(false), ms);
  };

  const runOsResult = (r: any) => {
    if (r?.outcome === 0 && r?.executed) {              // EXECUTE — done
      const msg = `${r.detail || "실행했습니다."} ${r.stdout ? "— " + String(r.stdout).slice(0, 160) : ""}`.trim();
      dockFor(9000);
      setAnswer(msg); setPending(null); speak(r.detail || "실행했습니다.");
    } else if (r?.approval_token) {                      // NEEDS_APPROVAL — hold
      dockFor(60000);
      setPending({ token: r.approval_token, text: r.detail || "이 작업을 실행할까요?", kind: r.action?.kind });
      setAnswer(r.detail || "승인이 필요한 작업입니다."); speak(r.detail || "승인이 필요합니다. 실행할까요?");
      setState("idle");
    } else {                                             // BLOCKED
      setAnswer(r?.detail || "실행할 수 없습니다."); setPending(null); setState("idle");
      setDocked(false);
    }
  };

  const ask = async (q: string) => {
    setQuestion(q);
    setAnswer("");
    setState("thinking");
    // voice approval: while an action is held, '응/네/그래/실행/yes' approves, '아니/취소/no' rejects.
    if (pendingRef.current) {
      if (/^(응|네|그래|좋아|실행|해줘|yes|ok|okay|approve)/i.test(q.trim())) {
        const r = await fetch("/api/os-action/approve", { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify({ token: pendingRef.current.token }) }).then(x => x.json()).catch(() => null);
        setPending(null); if (r) runOsResult({ ...r, approval_token: undefined }); else setState("idle");
        return;
      }
      if (/^(아니|아뇨|취소|하지마|no|cancel|stop)/i.test(q.trim())) {
        await fetch("/api/os-action/reject", { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify({ token: pendingRef.current.token }) }).catch(() => {});
        setPending(null); setAnswer("취소했습니다."); speak("취소했습니다."); setState("idle");
        return;
      }
    }
    // OS command first — the orb drives the desktop; a plain question falls through.
    try {
      const os = await fetch("/api/os-action/propose", { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify({ text: q }) }).then(x => x.json()).catch(() => null);
      if (os && os.is_os_action) { runOsResult(os); return; }
    } catch { /* fall through to knowledge answer */ }
    try {
      const res = await fetch("/api/chat/atanor", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ question: q, language: /[가-힣]/.test(q) ? "ko" : "en",
                               audience_level: "beginner", mode: "default", brain_mode: "unified" }),
      });
      const body = await res.json();
      const text = String(body?.result?.answer ?? body?.answer ?? "").trim();
      if (text) { setAnswer(text); speak(text); }
      else { setAnswer("…"); setState("idle"); }
    } catch {
      // a failed call while the engine wakes is expected — the poller recovers us
      setAnswer("엔진이 깨어나는 중입니다 — 연결되면 바로 응답합니다.");
      setState("offline");
    }
  };

  const toggleTalk = async () => {
    if (stateRef.current === "listening") { recRef.current?.stop(); return; }
    if (stateRef.current !== "idle" && stateRef.current !== "offline") return;
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      const rec = new MediaRecorder(stream, { mimeType: "audio/webm" });
      chunksRef.current = [];
      rec.ondataavailable = (e) => { if (e.data.size) chunksRef.current.push(e.data); };
      rec.onstop = async () => {
        stream.getTracks().forEach((tr) => tr.stop());
        setState("thinking");
        try {
          const fd = new FormData();
          fd.append("file", new Blob(chunksRef.current, { type: "audio/webm" }), "mic.webm");
          const res = await fetch("/api/voice/transcribe", { method: "POST", body: fd });
          const body = await res.json().catch(() => ({}));
          const text = String(body?.text ?? "").trim();
          if (res.ok && text) void ask(text);
          else setState(res.ok ? "idle" : "offline");
        } catch { setState("offline"); }
      };
      recRef.current = rec;
      rec.start();
      setState("listening");
    } catch {
      // no microphone (VMs, headless) is not an engine failure — say so and
      // point at the composer instead of scaring with an offline banner
      setAnswer("마이크를 찾을 수 없습니다 — 아래 입력줄로 말을 걸어주세요.");
      setState("idle");
    }
  };

  const composerRef = useRef<HTMLInputElement | null>(null);
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      // Space = push-to-talk — but NEVER while typing (the composer's spaces
      // were triggering the mic on every word; measured on the OS build)
      const t = e.target as HTMLElement | null;
      if (t && (t.tagName === "INPUT" || t.tagName === "TEXTAREA" || t.isContentEditable)) return;
      // omni-prompt summon: '/' (Ctrl+Space belongs to the Korean IME toggle)
      if (e.key === "/") {
        e.preventDefault();
        composerRef.current?.focus();
        return;
      }
      if (e.code === "Space") { e.preventDefault(); void toggleTalk(); }
    };
    addEventListener("keydown", onKey);
    return () => removeEventListener("keydown", onKey);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const statusLine: Record<ShellState, string> = {
    idle: engineUp === false ? "엔진 기동 중 — 준비되면 자동으로 연결됩니다" : "말하거나, 아래에 입력하세요",
    listening: "듣는 중… (다시 눌러 끝내기)",
    thinking: "그래프에서 근거를 찾는 중…",
    speaking: "답하는 중",
    offline: "엔진 기동 중 — 준비되면 자동으로 연결됩니다",
  };

  // typed commands: same lane as voice — a machine without a microphone (VMs,
  // headless boxes) still gets the full AI desktop
  const [draft, setDraft] = useState("");

  // PHONE LINK: any phone becomes this machine's microphone via the pairing
  // code — auto-enabled once the engine is up (relay is OUR cloud VM only)
  const [linkInfo, setLinkInfo] = useState<{ code?: string; last_text?: string; last_answer?: string; last_at?: string } | null>(null);
  const lastLinkAtRef = useRef("");
  useEffect(() => {
    if (engineUp !== true || !wallpaper) return;
    let stop = false;
    fetch("/api/phone-link/enable", { method: "POST" }).catch(() => {});
    const iv = setInterval(async () => {
      try {
        const s = await fetch("/api/phone-link/status", { signal: AbortSignal.timeout(4000) }).then((r) => r.json());
        if (stop) return;
        setLinkInfo(s);
        // a fresh phone utterance surfaces on the desktop like a spoken one
        if (s?.last_at && s.last_at !== lastLinkAtRef.current && s.last_text) {
          lastLinkAtRef.current = s.last_at;
          setQuestion(s.last_text);
          if (s.last_answer) { setAnswer(s.last_answer); speak(s.last_answer); }
        }
      } catch { /* engine poller covers liveness */ }
    }, 4000);
    return () => { stop = true; clearInterval(iv); };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [engineUp, wallpaper]);

  // MANUAL mode (패닉룸): the field flattens to a quiet plane and the AI's
  // autonomy drops to 관찰(OBSERVE) — "never intervenes first" as a REAL gate,
  // not a promise. Leaving manual restores the previous tier.
  const [manual, setManual] = useState(false);
  const prevTierRef = useRef(1);
  const toggleManual = async () => {
    if (!manual) {
      prevTierRef.current = tier;
      setManual(true);
      await changeTier(0);
    } else {
      setManual(false);
      await changeTier(prevTierRef.current);
    }
  };

  return (
    <main className="atanor-os-shell" data-overlay={overlay ? "1" : "0"} data-wallpaper={wallpaper ? "1" : "0"}
      style={{ background: overlay ? "transparent" : undefined }}>

      {/* wallpaper mode: the PURE cognitive plane — points only, gaussian
          grains, fluid drift (the four absolute rules; no lines, no scaffolds,
          no painted shapes ANYWHERE in that component). energy is a primitive
          driven by REAL state, and all motion lives in refs — typing can
          never reset the field. */}
      {wallpaper ? (
        <div className="atanor-os-shell-field" aria-hidden data-mode={manual ? "manual" : shellState}>
          <PureField
            budget={Math.round(6500 * density)}
            scale={1.0} /* halo tracks the orb: gap ≈ orb radius, 1080p-measured */
            mode={manual ? "manual"
              : shellState === "thinking" ? "thinking"
              : shellState === "listening" ? "listening"
              : shellState === "speaking" ? "speaking"
              : "idle"}
          />
        </div>
      ) : null}

      {/* wallpaper mode: desktop icons, Windows-like — but every launch goes
          THROUGH the AI action lane (proposed, gated by trust tier, audited).
          The desktop surface is ours, so the icons are ours too. */}
      {wallpaper ? (
        <div className="atanor-os-shell-icons" onClick={(e) => e.stopPropagation()}>
          {[
            { name: "파일", cmd: "파일 관리자 열어줘", d: "M3 6a2 2 0 0 1 2-2h4l2 2h8a2 2 0 0 1 2 2v9a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V6z" },
            { name: "터미널", cmd: "터미널 열어줘", d: "M4 5h16v14H4V5zm3 4 3 3-3 3m5 0h5" },
            { name: "브라우저", cmd: "브라우저 열어줘", d: "M12 3a9 9 0 1 0 0 18 9 9 0 0 0 0-18zm-9 9h18M12 3c-2.5 2.5-4 5.5-4 9s1.5 6.5 4 9c2.5-2.5 4-5.5 4-9s-1.5-6.5-4-9z" },
          ].map((ic) => (
            <button key={ic.name} className="atanor-os-shell-icon" onClick={() => void ask(ic.cmd)} title={ic.cmd}>
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5"
                   strokeLinecap="round" strokeLinejoin="round"><path d={ic.d} /></svg>
              <span>{ic.name}</span>
            </button>
          ))}
          {/* the Omni-Node mark (owner-designed) — THE ATANOR glyph */}
          <button className="atanor-os-shell-icon" onClick={() => void ask("대시보드 열어줘")} title="대시보드 열어줘">
            <svg viewBox="0 0 100 100" className="atanor-omni-mark">
              <path d="M 50 15 L 82 78 H 63 L 50 52 L 37 78 H 18 Z" fill="currentColor" />
              <rect x="34" y="44" width="32" height="7" fill="currentColor" />
              <circle cx="50" cy="66" r="8" className="atanor-omni-core" />
            </svg>
            <span>ATANOR</span>
          </button>
          {/* phone pairing — the phone IS the microphone */}
          {linkInfo?.code ? (
            <div className="atanor-os-shell-pairing" title="폰에서 atanor-liard.vercel.app/link 를 열고 이 코드를 입력하세요">
              <span>폰 마이크</span>
              <strong>{linkInfo.code}</strong>
              <em>atanor-liard.vercel.app/link</em>
            </div>
          ) : null}
        </div>
      ) : null}

      {/* the real orb, front and center — docks bottom-right while acting */}
      <div className="atanor-os-shell-orb" data-docked={docked}>
        <HologramVoiceOrb state={orbState} density={density}
          onActivate={() => void toggleTalk()} onCancel={() => void toggleTalk()} />
      </div>

      {/* trust tier — the ONE dial for autonomy (관찰 → 승인 → 가드 → 자율) */}
      <div className="atanor-os-shell-tier" onClick={(e) => e.stopPropagation()}>
        {TIER_NAMES.map((name, i) => (
          <button key={i} onClick={() => void changeTier(i)} data-active={tier === i} data-danger={i >= 3}
            title={["관찰: 실행 안 함", "승인: 매 작업 확인", "가드: 되돌릴 수 있는 건 자동, 위험한 건 확인", "자율: 위험도 실행(전체 시스템만 재확인)"][i]}>
            {name}
          </button>
        ))}
        <button className="atanor-os-shell-manual" onClick={() => void toggleManual()} data-active={manual}
          title="수동: 필드가 잠잠해지고 AI는 절대 먼저 개입하지 않습니다(관찰 티어). 창과 마우스는 평소처럼.">
          수동
        </button>
      </div>

      <div className="atanor-os-shell-readout">
        <div className="atanor-os-shell-status" data-state={shellState}>{statusLine[shellState]}</div>
        {question ? <div className="atanor-os-shell-question">“{question}”</div> : null}
        {answer ? <div className="atanor-os-shell-answer">{answer}</div> : null}

        {/* held action — approve by click OR by saying '응' */}
        {pending ? (
          <div className="atanor-os-shell-approval" onClick={(e) => e.stopPropagation()}>
            <div className="atanor-os-shell-approval-text">{pending.text}</div>
            <div className="atanor-os-shell-approval-actions">
              <button className="atanor-os-shell-approve" onClick={() => void approveNow()}>실행 (또는 &quot;응&quot;)</button>
              <button className="atanor-os-shell-reject" onClick={() => void rejectNow()}>취소</button>
            </div>
          </div>
        ) : null}

        <form className="atanor-os-shell-composer" onClick={(e) => e.stopPropagation()}
          onSubmit={(e) => { e.preventDefault(); const q = draft.trim(); if (q) { setDraft(""); void ask(q); } }}>
          <input ref={composerRef} value={draft} onChange={(e) => setDraft(e.target.value)}
                 placeholder="무엇이든 — 질문하거나, 명령하세요 ( / )"
                 aria-label="ATANOR에게 말하기" />
        </form>

        <div className="atanor-os-shell-honesty">
          모든 처리는 이 기기 안에서 · 근거 없으면 정직하게 기권 · 모든 조작은 감사 기록에 남고 즉시 정지 가능
        </div>
      </div>
    </main>
  );
}
