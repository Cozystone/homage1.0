"use client";
// SPLATRA imagination — a THOUGHT (not one concept) as a scene. Type a word and ATANOR imagines
// it: the matching concept at the center, its graph neighborhood around it, playing the compiled
// motion script as particles. The scene is grounded (/api/imagination/scene-for-query over the
// real graph), never invented. Sibling of /imagine, which draws a single concept's *shape*.
import { useEffect, useRef, useState } from "react";

type SceneObject = {
  id: string; label: string; archetype: string; pos: [number, number, number];
  scale: number; hue: number; role: string;
};
type Motion = { t: number; action: string; target?: string; from?: string; to?: string;
                around?: string; toward?: string; source?: string;
                accel?: number; radius?: number; period?: number };
type Scene = { objects: SceneObject[]; links: unknown[]; motion: Motion[]; duration: number;
               meta: { empty?: boolean; subject?: string } };
type Particle = { x: number; y: number; ph: number; a: number };

const PRESETS = ["물", "별", "나무", "사랑", "도시", "음악"];

export default function ImaginationPage() {
  const canvasRef = useRef<HTMLCanvasElement | null>(null);
  const sceneRef = useRef<Scene | null>(null);
  const partsRef = useRef<Map<string, Particle[]>>(new Map());
  const [query, setQuery] = useState("");
  const [loading, setLoading] = useState(false);
  const [meta, setMeta] = useState<{ n: number; subject: string } | null>(null);
  const [live, setLive] = useState(false);

  // LIVE: follow ATANOR's mind — poll the current thought (what it just answered) and render it.
  useEffect(() => {
    if (!live) return;
    let alive = true;
    const poll = async () => {
      try {
        const r = await fetch("/api/imagination/current?duration=7", { cache: "no-store" });
        const s: Scene = await r.json();
        if (!alive) return;
        sceneRef.current = s.objects?.length ? s : null;
        const subj = s.objects?.find((o) => o.role === "subject")?.label
          || (s.meta as { live_query?: string })?.live_query || "";
        setMeta(s.objects?.length
          ? { n: s.objects.length, subject: subj }
          : { n: 0, subject: (s.meta as { idle?: boolean })?.idle ? "지금은 생각을 쉬고 있어요" : "" });
      } catch { /* engine offline → keep the last frame */ }
    };
    poll();
    const id = setInterval(poll, 2500);
    return () => { alive = false; clearInterval(id); };
  }, [live]);

  async function imagine(q: string) {
    const t = q.trim();
    if (!t) return;
    setQuery(t);
    setLoading(true);
    try {
      const r = await fetch("/api/imagination/scene-for-query", {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ query: t, duration: 7 }),
      });
      const s: Scene = await r.json();
      sceneRef.current = s.objects?.length ? s : null;
      partsRef.current = new Map();
      const subjLabel = s.objects?.find((o) => o.role === "subject")?.label || t;
      setMeta({ n: s.objects?.length || 0, subject: subjLabel });
    } catch {
      sceneRef.current = null; setMeta({ n: 0, subject: t });
    } finally { setLoading(false); }
  }

  // spatial replay: /imagination?replay=1 rebuilds the last remembered space as particles
  useEffect(() => {
    if (typeof window === "undefined") return;
    if (new URLSearchParams(window.location.search).get("replay") !== "1") return;
    let alive = true;
    const load = async () => {
      try {
        const r = await fetch("/api/imagination/replay?duration=8", { cache: "no-store" });
        const s: Scene = await r.json();
        if (!alive) return;
        sceneRef.current = s.objects?.length ? s : null;
        partsRef.current = new Map();
        const place = (s.meta as { place?: string })?.place;
        setMeta(s.objects?.length
          ? { n: s.objects.length, subject: place ? `기억한 공간 · ${place}` : "기억한 공간" }
          : { n: 0, subject: "아직 기억한 공간이 없어요" });
      } catch { /* engine offline */ }
    };
    load();
    const id = setInterval(load, 5000);          // pick up newly-recorded spaces
    return () => { alive = false; clearInterval(id); };
  }, []);

  function particlesFor(o: SceneObject): Particle[] {
    const cached = partsRef.current.get(o.id);
    if (cached) return cached;
    const n = o.role === "subject" ? 64 : 40;
    const ps: Particle[] = [];
    for (let i = 0; i < n; i++) {
      const a = Math.random() * Math.PI * 2;
      const r = Math.sqrt(Math.random());
      ps.push({ x: Math.cos(a) * r, y: Math.sin(a) * r, ph: Math.random() * 6.28, a: 0.4 + Math.random() * 0.6 });
    }
    partsRef.current.set(o.id, ps);
    return ps;
  }

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext("2d");
    if (!ctx) return;
    const dpr = Math.min(2, window.devicePixelRatio || 1);
    let raf = 0;
    const start = performance.now();

    const resize = () => { canvas.width = canvas.clientWidth * dpr; canvas.height = canvas.clientHeight * dpr; };
    resize();
    window.addEventListener("resize", resize);

    const project = (p: [number, number, number], rot: number, W: number, H: number) => {
      const x = p[0] * Math.cos(rot) - p[2] * Math.sin(rot);
      const z = p[0] * Math.sin(rot) + p[2] * Math.cos(rot);
      const scale = 0.34 * Math.min(W, H);
      const depth = 1 / (1.7 - z * 0.4);
      return { sx: W / 2 + x * scale * depth, sy: H / 2 + p[1] * scale * depth, depth };
    };

    const frame = (now: number) => {
      const s = sceneRef.current;
      const W = canvas.width, H = canvas.height;
      ctx.clearRect(0, 0, W, H);
      if (s && s.objects.length) {
        const dur = s.duration || 6;
        const tt = ((now - start) / 1000) % (dur + 2.4);
        const rot = (now - start) / 7000;
        // physics mirror (same as the main aquarium): a relation that names a motion moves the
        // object — fall accelerates down, orbit circles its anchor, attract drifts toward it.
        const base = new Map(s.objects.map((o) => [o.id, project(o.pos, rot, W, H)]));
        const physOffset = (o: SceneObject) => {
          const b = base.get(o.id)!;
          let ox = 0, oy = 0, sc = 1;
          for (const m of s.motion) {
            if (m.action === "appear" || tt < m.t) continue;
            const dt = tt - m.t;
            if (m.action === "fall" && m.target === o.id) oy += Math.min(H * 0.33, 0.5 * (m.accel ?? 1) * dt * dt * 46 * dpr);
            else if (m.action === "rise" && m.target === o.id) oy -= Math.min(H * 0.3, 0.5 * Math.abs(m.accel ?? 0.6) * dt * dt * 46 * dpr);
            else if (m.action === "attract" && m.target === o.id) { const a = base.get(m.toward as string); if (a) { const k = Math.min(0.85, dt * 0.35); ox += (a.sx - b.sx) * k; oy += (a.sy - b.sy) * k; } }
            else if (m.action === "orbit" && m.target === o.id) { const a = base.get(m.around as string); if (a) { const ang = (dt / (m.period ?? 3)) * Math.PI * 2; const rad = (m.radius ?? 0.55) * 0.32 * Math.min(W, H); ox += a.sx + Math.cos(ang) * rad - b.sx; oy += a.sy + Math.sin(ang) * rad * 0.5 - b.sy; } }
            else if (m.action === "emit" && m.source === o.id) sc = 1 + Math.min(1.3, dt * 0.5);
          }
          return { sx: b.sx + ox, sy: b.sy + oy, depth: b.depth, sc };
        };

        for (const m of s.motion) {
          if (m.action === "appear" || tt < m.t) continue;
          const a = s.objects.find((o) => o.id === m.from);
          const b = s.objects.find((o) => o.id === m.to);
          if (!a || !b) continue;
          const pa = project(a.pos, rot, W, H), pb = project(b.pos, rot, W, H);
          const k = m.action === "flow" ? 14 : 9;
          for (let i = 0; i < k; i++) {
            const f = (tt * 0.55 + i / k) % 1;
            const x = pa.sx + (pb.sx - pa.sx) * f, y = pa.sy + (pb.sy - pa.sy) * f;
            const fade = 1 - Math.abs(0.5 - f) * 2;
            ctx.fillStyle = `hsla(${a.hue}, 80%, 66%, ${0.45 * fade})`;
            ctx.beginPath(); ctx.arc(x, y, 2 * dpr, 0, 7); ctx.fill();
          }
        }

        const ordered = [...s.objects].sort((o1, o2) =>
          project(o1.pos, rot, W, H).depth - project(o2.pos, rot, W, H).depth);
        for (const o of ordered) {
          const appearT = s.motion.find((m) => m.action === "appear" && m.target === o.id)?.t ?? 0;
          const alpha = Math.max(0, Math.min(1, (tt - appearT) / 0.6));
          if (alpha <= 0) continue;
          const p = physOffset(o);
          const R = 30 * dpr * o.scale * p.depth * p.sc;
          for (const pt of particlesFor(o)) {
            let jx = pt.x, jy = pt.y;
            const wob = Math.sin(now / 520 + pt.ph);
            if (o.archetype === "swirl") {
              const ang = Math.atan2(pt.y, pt.x) + now / 1100; const rr = Math.hypot(pt.x, pt.y);
              jx = Math.cos(ang) * rr; jy = Math.sin(ang) * rr;
            } else if (o.archetype === "blob") {
              jx = pt.x * (1 + 0.18 * wob); jy = pt.y * (1 - 0.18 * wob);
            } else if (o.archetype === "field") {
              jy = pt.y * 0.4; jx = pt.x * (1 + 0.05 * wob);
            }
            ctx.fillStyle = `hsla(${o.hue}, 85%, ${o.role === "subject" ? 70 : 60}%, ${alpha * pt.a})`;
            ctx.beginPath();
            ctx.arc(p.sx + jx * R, p.sy + jy * R, (o.role === "subject" ? 2.3 : 1.7) * dpr, 0, 7);
            ctx.fill();
          }
          ctx.fillStyle = `hsla(${o.hue}, 70%, 86%, ${alpha})`;
          ctx.font = `${(o.role === "subject" ? 15 : 12.5) * dpr}px ui-sans-serif, sans-serif`;
          ctx.textAlign = "center";
          ctx.fillText(o.label, p.sx, p.sy + R + 15 * dpr);
        }
      }
      raf = requestAnimationFrame(frame);
    };
    raf = requestAnimationFrame(frame);
    return () => { cancelAnimationFrame(raf); window.removeEventListener("resize", resize); };
  }, []);

  return (
    <div style={{ position: "fixed", inset: 0, background: "radial-gradient(circle at 50% 40%, #0b1020, #05070c 72%)", overflow: "hidden" }}>
      <canvas ref={canvasRef} style={{ position: "absolute", inset: 0, width: "100%", height: "100%" }} />

      <div style={{ position: "absolute", top: 22, left: 24, color: "#9aa3b6", fontSize: 12.5,
        fontFamily: "ui-monospace, monospace", letterSpacing: "0.04em", maxWidth: 340 }}>
        <span style={{ color: "#ff8a00", fontWeight: 700, letterSpacing: "0.2em" }}>SPLATRA · 생각의 장면</span>
        <div style={{ marginTop: 6, opacity: 0.7, lineHeight: 1.5 }}>
          단어를 던지면 그 생각을 그래프에서 떠올려, 중심 개념과 이웃을 입자로 그리고 관계를 따라 움직입니다. 지어내지 않고, 아는 것만.
        </div>
        <button onClick={() => setLive((v) => !v)}
          style={{ marginTop: 10, display: "inline-flex", alignItems: "center", gap: 7,
            background: live ? "rgba(255,138,0,0.16)" : "rgba(255,255,255,0.05)",
            color: live ? "#ff8a00" : "#9aa3b6", border: `1px solid ${live ? "rgba(255,138,0,0.45)" : "rgba(255,255,255,0.14)"}`,
            borderRadius: 999, padding: "6px 13px", fontSize: 12, cursor: "pointer", fontFamily: "inherit" }}>
          <span style={{ width: 7, height: 7, borderRadius: 999, background: live ? "#ff8a00" : "#586074",
            boxShadow: live ? "0 0 8px #ff8a00" : "none" }} />
          {live ? "라이브 — ATANOR의 생각을 따라가는 중" : "라이브 켜기 (대화 따라가기)"}
        </button>
        {meta && (
          <div style={{ marginTop: 8, opacity: 0.6 }}>
            {meta.n > 0
              ? `중심: ${meta.subject} · 개념 ${meta.n}`
              : `"${meta.subject}" — 아직 그릴 만큼 알지 못해요. 정직하게 비워둡니다.`}
          </div>
        )}
      </div>

      <div style={{ position: "absolute", bottom: 30, left: "50%", transform: "translateX(-50%)",
        width: "min(560px, 90vw)" }}>
        <div style={{ display: "flex", gap: 7, marginBottom: 9, flexWrap: "wrap", justifyContent: "center" }}>
          {PRESETS.map((p) => (
            <button key={p} onClick={() => imagine(p)}
              style={{ background: "rgba(255,255,255,0.06)", color: "#c7cbd4", border: "1px solid rgba(255,255,255,0.12)",
                borderRadius: 999, padding: "5px 12px", fontSize: 12.5, cursor: "pointer", backdropFilter: "blur(6px)" }}>
              {p}
            </button>
          ))}
        </div>
        <form onSubmit={(e) => { e.preventDefault(); imagine(query); }} style={{ display: "flex", gap: 8 }}>
          <input
            value={query} onChange={(e) => setQuery(e.target.value)}
            placeholder="무엇을 상상해볼까요?  예: 물, 별, 사랑"
            style={{ flex: 1, background: "rgba(255,255,255,0.06)", border: "1px solid rgba(255,255,255,0.14)",
              borderRadius: 12, padding: "13px 16px", color: "#f2f4f8", fontSize: 14, outline: "none",
              backdropFilter: "blur(10px)" }} />
          <button type="submit" disabled={loading}
            style={{ background: loading ? "rgba(255,138,0,0.3)" : "#ff8a00", color: "#0b0d12", border: "none",
              borderRadius: 12, padding: "0 20px", fontSize: 14, fontWeight: 700, cursor: "pointer" }}>
            {loading ? "떠올리는 중…" : "상상"}
          </button>
        </form>
      </div>
    </div>
  );
}
