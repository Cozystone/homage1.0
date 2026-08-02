"use client";
// 시각 기억 재현 (Phase 4-2) — "영상 재생"이 아니라 "상상": 실측 시그니처(색 밴드/
// 팔레트/질감)에서 파티클 필드를 역산해 그린다. 저장된 것은 몇 개의 숫자뿐이고,
// 장면은 매번 그 숫자들로부터 다시 태어난다 (영상 블랙홀 방지 원칙).
import { Suspense, useEffect, useRef, useState } from "react";
import { useSearchParams } from "next/navigation";

type Scene = {
  kind: string;
  concept: string;
  known?: boolean;
  bands?: number[][];
  palette?: number[][];
  particle_density?: number;
  drift?: number;
  luminance?: number;
  sources?: string[];
  measured_from?: number;
  honest_scope?: string;
};

function RecallView() {
  const params = useSearchParams();
  const concept = params.get("concept") || "";
  const mountRef = useRef<HTMLDivElement | null>(null);
  const [scene, setScene] = useState<Scene | null>(null);
  const [phase, setPhase] = useState<"loading" | "learning" | "ready" | "unknown">("loading");

  useEffect(() => {
    if (!concept) { setPhase("unknown"); return; }
    let cancelled = false;
    (async () => {
      const get = async (learn: boolean): Promise<Scene | null> => {
        try {
          const r = await fetch(`/api/base-brain/visual-memory/${encodeURIComponent(concept)}${learn ? "?learn=1" : ""}`);
          return (await r.json()) as Scene;
        } catch { return null; }
      };
      let s = await get(false);
      if (!cancelled && (!s || s.known === false)) {
        setPhase("learning"); // on-miss: fetch + measure real photos (bounded)
        s = await get(true);
      }
      if (cancelled) return;
      if (s && s.known !== false && s.bands) { setScene(s); setPhase("ready"); }
      else setPhase("unknown");
    })();
    return () => { cancelled = true; };
  }, [concept]);

  useEffect(() => {
    if (!scene || !mountRef.current) return;
    const root = mountRef.current;
    root.querySelector("canvas")?.remove();
    const cv = document.createElement("canvas");
    cv.width = root.clientWidth; cv.height = root.clientHeight;
    cv.style.position = "absolute"; cv.style.inset = "0";
    root.appendChild(cv);
    const cx = cv.getContext("2d")!;
    const W = cv.width, H = cv.height;

    const bands = scene.bands!;
    const palette = scene.palette || [];
    const density = scene.particle_density ?? 0.5;
    const drift = scene.drift ?? 0.3;
    const lum = scene.luminance ?? 0.5;
    const N = Math.floor(400 + density * 1400);

    type P = { x: number; y: number; vx: number; vy: number; c: number[]; r: number; tw: number };
    const parts: P[] = [];
    for (let i = 0; i < N; i++) {
      const y = Math.random() * H;
      const band = bands[Math.min(2, Math.floor((y / H) * 3))];
      // 대부분은 밴드색(구도), 일부는 팔레트 강세색
      const c = Math.random() < 0.22 && palette.length
        ? palette[Math.floor(Math.random() * palette.length)]
        : band;
      parts.push({
        x: Math.random() * W, y,
        vx: (Math.random() - 0.5) * drift * 1.2,
        vy: (Math.random() - 0.5) * drift * 0.5,
        c, r: 0.8 + Math.random() * 1.8, tw: Math.random() * Math.PI * 2,
      });
    }

    let raf = 0;
    const animate = (now: number) => {
      raf = requestAnimationFrame(animate);
      cx.fillStyle = "rgba(5,7,10,0.28)";
      cx.fillRect(0, 0, W, H);
      for (const p of parts) {
        p.x += p.vx; p.y += p.vy;
        if (p.x < 0) p.x = W; if (p.x > W) p.x = 0;
        if (p.y < 0) p.y = H; if (p.y > H) p.y = 0;
        const twinkle = 0.55 + 0.45 * Math.sin(now / 900 + p.tw);
        const a = (0.25 + lum * 0.5) * twinkle;
        const [r, g, b] = p.c.map((v) => Math.round(v * 255));
        cx.beginPath();
        cx.arc(p.x, p.y, p.r, 0, Math.PI * 2);
        cx.fillStyle = `rgba(${r},${g},${b},${a})`;
        cx.fill();
      }
    };
    raf = requestAnimationFrame(animate);
    return () => { cancelAnimationFrame(raf); cv.remove(); };
  }, [scene]);

  return (
    <div style={{ position: "fixed", inset: 0, background: "#05070A", overflow: "hidden" }}>
      <div ref={mountRef} style={{ position: "absolute", inset: 0 }} />
      <div style={{
        position: "absolute", top: 20, left: 22, color: "#e2e8f0", pointerEvents: "none",
        background: "rgba(10,15,25,0.78)", padding: "14px 18px", borderRadius: 8,
        border: "1px solid rgba(56,189,248,0.25)", backdropFilter: "blur(10px)",
        fontFamily: "ui-monospace, monospace", fontSize: 13, maxWidth: 340,
      }}>
        <div style={{ letterSpacing: "0.2em", color: "#38bdf8", fontWeight: 700, marginBottom: 8 }}>
          시각 기억 재현
        </div>
        <div style={{ fontSize: 15, fontWeight: 600, marginBottom: 6 }}>{concept || "—"}</div>
        {phase === "loading" && <div style={{ opacity: 0.6 }}>기억을 찾는 중…</div>}
        {phase === "learning" && <div style={{ opacity: 0.6 }}>처음 보는 개념 — 실제 사진을 측정하는 중…</div>}
        {phase === "unknown" && (
          <div style={{ opacity: 0.6 }}>
            이 개념의 시각 기억이 아직 없어요. 측정에 실패했거나 이미지 검색이 닿지 않았습니다 —
            지어내지 않고 비워둡니다.
          </div>
        )}
        {phase === "ready" && scene && (
          <>
            <div style={{ opacity: 0.75, marginBottom: 4 }}>
              실측 — 사진 {scene.measured_from ?? "?"}장에서 잰 색·구도·질감으로 재구성
            </div>
            <div style={{ opacity: 0.5, fontSize: 11 }}>
              저장된 건 영상이 아니라 시그니처 몇 바이트입니다. 장면은 지금 그 숫자에서
              다시 태어난 것 — 재생이 아니라 상상입니다.
            </div>
          </>
        )}
      </div>
    </div>
  );
}

export default function RecallPage() {
  return (
    <Suspense fallback={null}>
      <RecallView />
    </Suspense>
  );
}
