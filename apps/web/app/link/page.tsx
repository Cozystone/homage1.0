"use client";

import { useRef, useState } from "react";

/* Phone Link — this page turns a phone into the paired machine's microphone.
   Enter the pairing code the OS shows, hold the orb, speak. Audio hops through
   OUR relay only (the ATANOR cloud VM), is deleted on pull, and is transcribed
   LOCALLY on the paired machine — this page never sees or stores text. */

const RELAY = "https://136.114.69.152.sslip.io";

type LinkState = "idle" | "recording" | "sending" | "sent" | "error";

export default function PhoneLinkPage() {
  const [code, setCode] = useState("");
  const [st, setSt] = useState<LinkState>("idle");
  const [note, setNote] = useState("");
  const recRef = useRef<MediaRecorder | null>(null);
  const chunksRef = useRef<Blob[]>([]);

  const start = async () => {
    if (code.trim().length < 6) { setNote("OS 화면의 페어링 코드를 먼저 입력하세요"); return; }
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      const rec = new MediaRecorder(stream, { mimeType: "audio/webm" });
      chunksRef.current = [];
      rec.ondataavailable = (e) => { if (e.data.size) chunksRef.current.push(e.data); };
      rec.onstop = async () => {
        stream.getTracks().forEach((t) => t.stop());
        setSt("sending");
        try {
          const blob = new Blob(chunksRef.current, { type: "audio/webm" });
          const buf = await blob.arrayBuffer();
          let bin = "";
          const bytes = new Uint8Array(buf);
          for (let i = 0; i < bytes.length; i += 1) bin += String.fromCharCode(bytes[i]);
          const res = await fetch(`${RELAY}/api/link/${code.trim().toUpperCase()}/utterance`, {
            method: "POST",
            headers: { "content-type": "application/json" },
            body: JSON.stringify({ audio_b64: btoa(bin) }),
          });
          if (res.ok) { setSt("sent"); setNote("전달됨 — 기기가 곧 응답합니다"); }
          else { setSt("error"); setNote(`릴레이 오류 (${res.status})`); }
        } catch { setSt("error"); setNote("릴레이에 연결할 수 없습니다"); }
      };
      recRef.current = rec;
      rec.start();
      setSt("recording"); setNote("듣는 중 — 손을 떼면 전송됩니다");
    } catch { setSt("error"); setNote("마이크 권한이 필요합니다"); }
  };
  const stop = () => { if (st === "recording") recRef.current?.stop(); };

  return (
    <main style={{ position: "fixed", inset: 0, display: "grid", placeItems: "center",
                   background: "radial-gradient(ellipse at 50% 30%, #101318 0%, #05070a 70%)",
                   color: "#f4f6f9", fontFamily: "Pretendard, sans-serif", padding: 24 }}>
      <div style={{ display: "grid", justifyItems: "center", gap: 22, width: "min(360px, 92vw)" }}>
        <svg viewBox="0 0 100 100" style={{ width: 64, height: 64 }}>
          <path d="M 50 15 L 82 78 H 63 L 50 52 L 37 78 H 18 Z" fill="#a0aec0" />
          <rect x="34" y="44" width="32" height="7" fill="#a0aec0" />
          <circle cx="50" cy="66" r="8" fill="#00f0ff" />
        </svg>
        <div style={{ fontSize: 15, opacity: 0.75, textAlign: "center", lineHeight: 1.6 }}>
          이 폰을 ATANOR의 마이크로 씁니다.<br />OS 화면의 페어링 코드를 입력하세요.
        </div>
        <input value={code} onChange={(e) => setCode(e.target.value.toUpperCase())}
               placeholder="페어링 코드" inputMode="text" autoCapitalize="characters"
               style={{ width: "100%", padding: "14px 18px", borderRadius: 14, border: "none",
                        background: "rgba(255,255,255,0.07)", color: "#fff", fontSize: 20,
                        letterSpacing: "0.25em", textAlign: "center", outline: "none" }} />
        <button
          onPointerDown={() => void start()} onPointerUp={stop} onPointerLeave={stop}
          style={{ width: 148, height: 148, borderRadius: "50%", border: "none", cursor: "pointer",
                   background: st === "recording"
                     ? "radial-gradient(circle, rgba(0,240,255,0.35), rgba(0,240,255,0.08))"
                     : "radial-gradient(circle, rgba(255,255,255,0.10), rgba(255,255,255,0.03))",
                   boxShadow: st === "recording" ? "0 0 44px rgba(0,240,255,0.45)" : "0 8px 30px rgba(0,0,0,0.4)",
                   color: "#eaf0f6", fontSize: 15, fontWeight: 700, transition: "all 0.25s ease" }}>
          {st === "recording" ? "말하세요…" : "누르고 말하기"}
        </button>
        <div style={{ fontSize: 13, minHeight: 18, opacity: 0.65 }}>{note}</div>
        <div style={{ fontSize: 11, opacity: 0.35, textAlign: "center", lineHeight: 1.7 }}>
          음성은 ATANOR 자체 릴레이만 거쳐 기기에서 즉시 삭제되며,<br />
          문자 변환은 페어링된 기기 안에서만 일어납니다.
        </div>
      </div>
    </main>
  );
}
