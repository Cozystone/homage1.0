"use client";
// 살아있는 꼬마선충 배양소 (observatory only). 서버의 단일 백그라운드 스레드가
// 실제 LIF(leaky integrate-and-fire) 스파이킹 군집을 한 코어에서 배양한다. 이 페이지는
// 그 스냅샷을 폴링해 각 선충을 뉴런 전압으로 맥동하는 입자장으로 그린다.
// 정직: 이것은 추론기가 아니다. 어떤 답변 경로에도 연결돼 있지 않다. 관찰용이다.
import { useEffect, useRef, useState } from "react";

type Worm = {
  id: number;
  gen: number;
  energy: number;
  activity: number;
  voltages: number[];
};
type Snap = {
  generation: number;
  population: number;
  alive: number;
  cap: number;
  worms: Worm[];
  note: string;
};

const ORANGE = "#d2521f";

export default function CulturePage() {
  const [snap, setSnap] = useState<Snap | null>(null);
  const [live, setLive] = useState(false);
  const canvasRef = useRef<HTMLCanvasElement | null>(null);
  const snapRef = useRef<Snap | null>(null);

  // poll the living colony ~3 Hz
  useEffect(() => {
    let stop = false;
    const pull = async () => {
      try {
        const r = await fetch("/api/culture/state", { cache: "no-store" });
        if (!r.ok) throw new Error(String(r.status));
        const j = (await r.json()) as Snap;
        if (!stop) {
          setSnap(j);
          snapRef.current = j;
          setLive(true);
        }
      } catch {
        if (!stop) setLive(false);
      }
    };
    pull();
    const t = setInterval(pull, 330);
    return () => {
      stop = true;
      clearInterval(t);
    };
  }, []);

  // render: each worm = a cluster of neuron points, brightness = voltage.
  // Driven by BOTH requestAnimationFrame (smooth 60fps when the tab is visible)
  // AND a setInterval (background tabs throttle/pause rAF, but timers still fire,
  // so the colony keeps painting even when the window is not focused).
  useEffect(() => {
    let raf = 0;
    const paint = () => {
      const cv = canvasRef.current;
      const s = snapRef.current;
      if (!cv || !s) return;
      const ctx = cv.getContext("2d");
      if (!ctx) return;
      const W = (cv.width = cv.clientWidth * devicePixelRatio);
      const H = (cv.height = cv.clientHeight * devicePixelRatio);
      ctx.clearRect(0, 0, W, H);
      const worms = s.worms.filter((w) => w.energy > 0);
      const n = Math.max(1, worms.length);
      const cols = Math.ceil(Math.sqrt(n));
      const cw = W / cols;
      const ch = H / Math.ceil(n / cols);
      const now = performance.now() / 1000;
      worms.forEach((w, k) => {
        const cx = (k % cols) * cw + cw / 2;
        const cy = Math.floor(k / cols) * ch + ch / 2;
        const rad = Math.min(cw, ch) * 0.36;
        const nn = w.voltages.length || 1;
        const alive = w.energy > 0;
        // worm body halo — brightness by activity, size by energy
        ctx.beginPath();
        ctx.arc(cx, cy, rad * (0.55 + Math.min(1, w.energy) * 0.5), 0, Math.PI * 2);
        ctx.fillStyle = alive
          ? `rgba(210,82,31,${0.05 + 0.05 * Math.min(1, w.activity * 3)})`
          : "rgba(120,120,130,0.03)";
        ctx.fill();
        // neurons as pulsing points around a ring
        w.voltages.forEach((v, i) => {
          const ang = (i / nn) * Math.PI * 2 + now * 0.2;
          const rr = rad * (0.35 + (0.6 * ((i * 37) % nn)) / nn);
          const px = cx + Math.cos(ang) * rr;
          const py = cy + Math.sin(ang) * rr;
          const b = Math.max(0, Math.min(1, v));
          const size = (1.2 + b * 3.2) * devicePixelRatio;
          ctx.beginPath();
          ctx.arc(px, py, size, 0, Math.PI * 2);
          if (!alive) ctx.fillStyle = "rgba(120,120,130,0.25)";
          else if (b > 0.6) ctx.fillStyle = `rgba(255,180,120,${0.55 + b * 0.45})`; // firing
          else ctx.fillStyle = `rgba(210,82,31,${0.2 + b * 0.5})`;
          ctx.fill();
        });
      });
    };
    const loop = () => {
      paint();
      raf = requestAnimationFrame(loop);
    };
    raf = requestAnimationFrame(loop);
    const fallback = setInterval(paint, 200); // survives hidden/throttled tabs
    return () => {
      cancelAnimationFrame(raf);
      clearInterval(fallback);
    };
  }, []);

  const feed = async () => {
    try {
      await fetch("/api/culture/feed", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ ticks: 60 }),
      });
    } catch {
      /* ignore */
    }
  };

  return (
    <main
      style={{
        minHeight: "100vh",
        background: "#0a0a0c",
        color: "#e8e8ea",
        fontFamily: "-apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif",
        padding: "28px 24px 40px",
      }}
    >
      <div style={{ maxWidth: 980, margin: "0 auto" }}>
        <header style={{ marginBottom: 18 }}>
          <div style={{ display: "flex", alignItems: "baseline", gap: 12 }}>
            <h1 style={{ fontSize: 22, fontWeight: 600, margin: 0, letterSpacing: -0.3 }}>
              선충 배양소
            </h1>
            <span
              style={{
                fontSize: 11,
                color: live ? ORANGE : "#8a8a90",
                border: `1px solid ${live ? ORANGE : "#333"}`,
                borderRadius: 999,
                padding: "2px 9px",
              }}
            >
              {live ? "LIVE · 한 코어에서 배양 중" : "엔진 연결 대기"}
            </span>
          </div>
          <p style={{ fontSize: 12.5, color: "#9a9aa2", margin: "8px 0 0", lineHeight: 1.6 }}>
            실제 LIF 스파이킹 뉴런 군집이 서버 백그라운드 스레드 한 개에서 살아 움직입니다. 두
            마리에서 시작해 세대마다 생존자가 번식하며 개체수가 거듭제곱으로 늘고(2→4→8…), 상한에서
            멈춥니다. <b style={{ color: "#c7c7cd" }}>관찰용입니다 — 어떤 추론 경로에도 연결돼 있지
            않습니다.</b>
          </p>
        </header>

        <div style={{ display: "flex", gap: 14, flexWrap: "wrap", marginBottom: 16 }}>
          <Stat label="세대" value={snap ? String(snap.generation) : "—"} />
          <Stat label="개체수" value={snap ? `${snap.population} / ${snap.cap}` : "—"} />
          <Stat label="생존" value={snap ? String(snap.alive) : "—"} accent />
          <button
            onClick={feed}
            style={{
              marginLeft: "auto",
              alignSelf: "center",
              background: "transparent",
              color: ORANGE,
              border: `1px solid ${ORANGE}`,
              borderRadius: 10,
              padding: "8px 16px",
              fontSize: 13,
              cursor: "pointer",
            }}
          >
            먹이 주기 (리듬 자극)
          </button>
        </div>

        <div
          style={{
            position: "relative",
            border: "1px solid #1c1c22",
            borderRadius: 16,
            overflow: "hidden",
            background: "radial-gradient(circle at 50% 40%, #141418 0%, #0a0a0c 70%)",
          }}
        >
          <canvas
            ref={canvasRef}
            style={{ width: "100%", height: "min(62vh, 560px)", display: "block" }}
          />
          {!live && (
            <div
              style={{
                position: "absolute",
                inset: 0,
                display: "grid",
                placeItems: "center",
                color: "#7a7a82",
                fontSize: 13,
              }}
            >
              배양 엔진(:8502)에 연결되면 살아있는 군집이 나타납니다.
            </div>
          )}
        </div>

        <p style={{ fontSize: 11.5, color: "#6f6f77", marginTop: 14, lineHeight: 1.6 }}>
          각 원반은 한 마리의 선충입니다. 점 하나하나가 그 선충의 뉴런이고, 밝게 터지는 점은 지금
          발화(spike)하는 뉴런입니다. 조용하거나(죽어감) 발작적으로(폭주) 발화하는 개체는 에너지를
          잃고 사라지며, 건강한 리듬(발화율 8–45%)을 유지한 개체만 다음 세대를 남깁니다. 멸종하면
          새 창시 쌍 두 마리로 다시 시작합니다.
        </p>
      </div>
    </main>
  );
}

function Stat({ label, value, accent }: { label: string; value: string; accent?: boolean }) {
  return (
    <div
      style={{
        border: "1px solid #1c1c22",
        borderRadius: 12,
        padding: "10px 16px",
        minWidth: 96,
        background: "#0e0e12",
      }}
    >
      <div style={{ fontSize: 11, color: "#8a8a90", marginBottom: 4 }}>{label}</div>
      <div style={{ fontSize: 20, fontWeight: 600, color: accent ? ORANGE : "#e8e8ea" }}>
        {value}
      </div>
    </div>
  );
}
