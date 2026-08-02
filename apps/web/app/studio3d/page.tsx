"use client";

import { useCallback, useRef, useState } from "react";
import SplatraField, { SplatraHandle } from "../SplatraField";

// SPLATRA 3D — 스튜디오 화면 없이, 파티클 엔진이 ATANOR 안에서 직접 산다.
// 생성은 /api/splatra 프록시로 엔진에, 몸짓·재질은 네이티브 렌더러에 바로.
// 감정 구동은 기계 자신의 캐릭터(avatar)일 때만.
type Cmd =
  | { kind: "generate"; prompt: string }
  | { kind: "anim"; style: string }
  | { kind: "stop" }
  | { kind: "reset" };

function parseIntent(raw: string): Cmd {
  const t = raw.trim().toLowerCase();
  if (/멈춰|정지|그만|stop/.test(t)) return { kind: "stop" };
  if (/원래대로|되돌려|리셋|reset|얼려|굳혀/.test(t)) return { kind: "reset" };
  if (/물처럼|녹여|녹아|액체|melt|water/.test(t)) return { kind: "anim", style: "water" };
  if (/흙처럼|모래|부서|가루|crumble|soil|sand/.test(t)) return { kind: "anim", style: "soil" };
  if (/흔들|움직여|춤|살아|animate|wiggle|dance/.test(t)) return { kind: "anim", style: "rig" };
  if (/걸어|걷게|walk/.test(t)) return { kind: "anim", style: "walk" };
  if (/돌려|회전|spin/.test(t)) return { kind: "anim", style: "spin" };
  if (/숨( )?쉬|breathe/.test(t)) return { kind: "anim", style: "breathe" };
  return { kind: "generate", prompt: raw.trim() };
}

export default function Studio3D() {
  const field = useRef<SplatraHandle>(null);
  const [busy, setBusy] = useState(false);
  const [log, setLog] = useState<string[]>([]);
  const [text, setText] = useState("");

  const say = (m: string) => setLog((l) => [...l.slice(-6), m]);

  const run = useCallback(async () => {
    const raw = text.trim();
    if (!raw || busy) return;
    setText("");
    const cmd = parseIntent(raw);
    if (cmd.kind === "stop") { field.current?.animate("stop"); say("⏸ 정지"); return; }
    if (cmd.kind === "reset") { field.current?.animate("flow"); say("↺ 복원"); return; }
    if (cmd.kind === "anim") { field.current?.animate(cmd.style); say(`▶ ${cmd.style}`); return; }
    setBusy(true);
    say(`⚒ 생성 중: ${cmd.prompt}`);
    field.current?.disassemble();
    try {
      const res = await fetch("/api/splatra/v1/chat", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ message: cmd.prompt }),
      });
      const d = await res.json();
      if (res.ok) {
        say(`✓ ${d.narration || d.reply || "완료"}`.slice(0, 120));
        field.current?.reload();
      } else say(`✕ ${d.error || d.detail || res.status}`);
    } catch { say("✕ 엔진 연결 실패 (:8010)"); }
    setBusy(false);
  }, [text, busy]);

  return (
    <div style={{ display: "flex", flexDirection: "column", height: "100vh",
                  background: "radial-gradient(ellipse at 50% 35%, #101318 0%, #07080b 70%)" }}>
      <div style={{ flex: 1, position: "relative" }}>
        <SplatraField ref={field} />
        <div style={{ position: "absolute", top: 14, left: 18, color: "#6e6e76",
                      fontSize: 12, letterSpacing: 1.5, pointerEvents: "none" }}>
          ATANOR · PARTICLE FIELD
        </div>
      </div>
      <div style={{ padding: "10px 14px", borderTop: "1px solid #1d1d22", display: "flex", gap: 10 }}>
        <input value={text} onChange={(e) => setText(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && run()}
          placeholder='말하듯 입력 — "파란 토러스 만들어줘", "흔들어봐", "물처럼 녹여", "원래대로"'
          style={{ flex: 1, background: "#101014", color: "#eee", border: "1px solid #26262c",
                   borderRadius: 8, padding: "10px 12px", fontSize: 14, outline: "none" }} />
        <button onClick={run} disabled={busy}
          style={{ background: "#d2521f", color: "#fff", border: "none", borderRadius: 8,
                   padding: "10px 18px", fontSize: 14, cursor: "pointer", opacity: busy ? 0.5 : 1 }}>
          실행
        </button>
      </div>
      <div style={{ padding: "4px 14px 10px", color: "#9a9aa0", fontSize: 12, minHeight: 20 }}>
        {log.join("  ·  ")}
      </div>
    </div>
  );
}
