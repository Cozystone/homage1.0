"use client";
// Resident aquarium — the dashboard's backdrop IS ATANOR's imagination. It polls the current
// thought (/api/imagination/current, stashed by the answer path) and projects it as particles
// behind the glass, like fish beyond an aquarium wall (owner's "수족관 대시보드" vision).
//
// EFFICIENCY (owner's design question, 2026-07-12): async double-buffer, NOT a naive throttle.
//  * the poll (2.5s) only swaps the TARGET scene; the render (rAF, 60fps) cross-fades to it, so a
//    new thought glides in without a snap and network never stalls the render;
//  * particle clouds are regenerated ONLY when the scene changes (dirty-flag), reused otherwise;
//  * idle → everything fades to nothing (the mind at rest); hidden tab → a 140ms setInterval
//    fallback (rAF is dead when the document is hidden). Full-bleed, chrome-free, pointer-through.
import { useEffect, useRef } from "react";

type SceneObject = {
  id: string; label: string; archetype: string; pos: [number, number, number];
  scale: number; hue: number; role: string; shape?: { form: string; seed: number };
};

// ── SPLATRA silhouettes: a concept's structural FORM as a bounded point cloud (owner's "진짜 사물
// 디테일"). Deterministic per seed (a tree stays that tree). LoD budget bounds n per object so a 2D
// canvas never drowns; a real learned-Gaussian cloud would replace genSilhouette with its decimated
// points through the same draw path.
function mulberry32(seed: number): () => number {
  let a = seed >>> 0;
  return () => {
    a |= 0; a = (a + 0x6d2b79f5) | 0;
    let t = Math.imul(a ^ (a >>> 15), 1 | a);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

// each generator fills n points in local space (x,y ∈ ~[-1,1], y up); the renderer scales+projects them
function genSilhouette(form: string, seed: number, n: number): Particle[] {
  const r = mulberry32(seed || 1);
  const ps: Particle[] = [];
  const push = (x: number, y: number, a = 0.55) =>
    ps.push({ x, y, ph: r() * 6.28, a: 0.35 + r() * a });
  const line = (x0: number, y0: number, x1: number, y1: number, k: number, jit = 0.04) => {
    for (let i = 0; i < k; i++) { const t = r(); push(x0 + (x1 - x0) * t + (r() - 0.5) * jit, y0 + (y1 - y0) * t + (r() - 0.5) * jit); }
  };
  const disk = (cx: number, cy: number, rad: number, k: number, sy = 1) => {
    for (let i = 0; i < k; i++) { const a = r() * 6.28, rr = Math.sqrt(r()) * rad; push(cx + Math.cos(a) * rr, cy + Math.sin(a) * rr * sy); }
  };
  if (form === "branching") {                     // tree: trunk + canopy
    line(0, -0.95, 0, 0.05, Math.floor(n * 0.22), 0.06);
    disk(0, 0.45, 0.6, Math.ceil(n * 0.78), 0.9);
  } else if (form === "humanoid") {               // head · torso · arms · legs
    disk(0, 0.78, 0.17, Math.floor(n * 0.14));
    line(0, 0.55, 0, -0.12, Math.floor(n * 0.24), 0.14);          // torso
    line(-0.02, 0.5, -0.5, 0.08, Math.floor(n * 0.16));           // arms
    line(0.02, 0.5, 0.5, 0.08, Math.floor(n * 0.16));
    line(-0.02, -0.12, -0.17, -0.95, Math.floor(n * 0.15));       // legs
    line(0.02, -0.12, 0.17, -0.95, Math.floor(n * 0.15));
  } else if (form === "creature") {               // body + head + 4 legs + tail
    disk(0.1, 0.15, 0.42, Math.floor(n * 0.45), 0.6);
    disk(-0.6, 0.35, 0.2, Math.floor(n * 0.16));
    line(-0.25, -0.2, -0.3, -0.85, Math.floor(n * 0.09)); line(0.15, -0.2, 0.12, -0.85, Math.floor(n * 0.09));
    line(0.35, -0.2, 0.42, -0.85, Math.floor(n * 0.09)); line(-0.05, -0.2, -0.08, -0.85, Math.floor(n * 0.06));
    line(0.5, 0.25, 0.9, 0.5, Math.floor(n * 0.06));              // tail
  } else if (form === "vessel") {                 // bottle: body + neck + lip
    for (let i = 0; i < Math.floor(n * 0.68); i++) { const y = -0.85 + r() * 1.1; const w = 0.42 * (1 - Math.max(0, y - 0.1) * 0.5); push((r() - 0.5) * 2 * w, y); }
    line(-0.12, 0.28, -0.12, 0.72, Math.floor(n * 0.12), 0.03); line(0.12, 0.28, 0.12, 0.72, Math.floor(n * 0.12), 0.03);
    disk(0, 0.74, 0.16, Math.ceil(n * 0.08), 0.4);
  } else if (form === "columnar") {               // tall pillar / building
    for (let i = 0; i < n; i++) { const y = -0.95 + r() * 1.9; push((r() - 0.5) * 0.5, y); }
  } else if (form === "radial") {                 // ring + spokes
    for (let i = 0; i < Math.floor(n * 0.6); i++) { const a = r() * 6.28; push(Math.cos(a) * (0.85 + (r() - 0.5) * 0.14), Math.sin(a) * (0.85 + (r() - 0.5) * 0.14)); }
    for (let s = 0; s < 6; s++) { const a = (s / 6) * 6.28; line(0, 0, Math.cos(a) * 0.8, Math.sin(a) * 0.8, Math.floor(n * 0.066)); }
  } else if (form === "blob") {                   // amorphous (water/cloud)
    for (let i = 0; i < n; i++) { const a = r() * 6.28, rr = Math.sqrt(r()); push(Math.cos(a) * rr * (0.8 + 0.3 * Math.sin(a * 3)), Math.sin(a) * rr * 0.7); }
  } else {                                         // orb: clean filled sphere
    disk(0, 0, 0.92, n);
  }
  return ps;
}
type Motion = { t: number; action: string; target?: string; from?: string; to?: string;
  around?: string; toward?: string; source?: string; accel?: number; radius?: number; period?: number };
type Scene = { objects: SceneObject[]; motion: Motion[]; duration: number; sig: string };
type Particle = { x: number; y: number; ph: number; a: number };
type PIntent = { valence: number; energy: number; hue?: number; motion?: string; density: number };

export default function DashboardImaginationLayer() {
  const canvasRef = useRef<HTMLCanvasElement | null>(null);
  const curRef = useRef<Scene | null>(null);      // scene fading OUT
  const nextRef = useRef<Scene | null>(null);     // scene fading IN (the target)
  const fadeRef = useRef(1);                        // 0..1 progress of cur→next crossfade
  const partsRef = useRef<Map<string, Particle[]>>(new Map());
  // the AI's OWN hands on the field: a raw expressive intent (mood/energy/colour/motion) it can
  // push at any time. It MODULATES a concept scene, and becomes a standalone ambient cloud when the
  // mind is otherwise quiet — so ATANOR can move the particle space in any way, with or without a thought.
  const intentRef = useRef<PIntent | null>(null);
  const qualityRef = useRef(1);                     // frame-time governor scalar (0.4..1) — LoD safety valve
  const ambientRef = useRef<Particle[]>([]);
  if (ambientRef.current.length === 0) {
    for (let i = 0; i < 90; i++) {
      const a = Math.random() * Math.PI * 2, r = Math.sqrt(Math.random());
      ambientRef.current.push({ x: Math.cos(a) * r, y: Math.sin(a) * r,
        ph: Math.random() * 6.28, a: 0.3 + Math.random() * 0.6 });
    }
  }

  // the object's silhouette at its LoD budget, cached by (id, form, budget) so it only regenerates when
  // the budget TIER changes (governor), never per frame. Cache is size-bounded.
  function silhouetteFor(o: SceneObject, budget: number): Particle[] {
    const form = o.shape?.form || "orb";
    const key = `${o.id}:${form}:${budget}`;
    const hit = partsRef.current.get(key);
    if (hit) return hit;
    const ps = genSilhouette(form, o.shape?.seed || 1, budget);
    partsRef.current.set(key, ps);
    if (partsRef.current.size > 80) {               // bounded — drop the oldest
      const k0 = partsRef.current.keys().next().value;
      if (k0) partsRef.current.delete(k0);
    }
    return ps;
  }

  // LoD budget for one object: base by role, decayed by depth, scaled by the frame-time governor.
  // Quantized to steps of 8 so small governor changes don't thrash the silhouette cache.
  function lodBudget(o: SceneObject): number {
    const depth = Math.abs(o.pos[2]);
    const base = o.role === "subject" ? 420 : 190;
    const n = base * (1 / (1 + depth * 1.2)) * qualityRef.current;
    return Math.max(24, Math.min(420, Math.round(n / 8) * 8));
  }

  // poll the current thought → swap the target scene (async double-buffer)
  useEffect(() => {
    let alive = true;
    const poll = async () => {
      try {
        const r = await fetch("/api/imagination/current?duration=7", { cache: "no-store" });
        const s = await r.json();
        if (!alive) return;
        const objs: SceneObject[] = s.objects || [];
        const sig = objs.map((o) => o.id).join("|");
        const target = objs.length ? { objects: objs, motion: s.motion || [], duration: s.duration || 6, sig } : null;
        const nextSig = nextRef.current?.sig ?? "";
        if ((target?.sig ?? "") !== nextSig) {         // a NEW thought (or idle) — start a crossfade
          curRef.current = nextRef.current;
          nextRef.current = target;
          fadeRef.current = 0;
          // (silhouette cache is size-bounded in silhouetteFor — no per-scene prune needed)
        }
      } catch { /* engine offline → keep the last thought */ }
      try {
        const pr = await fetch("/api/imagination/particle", { cache: "no-store" });
        const pj = await pr.json();
        if (alive) intentRef.current = pj && !pj.idle ? pj as PIntent : null;
      } catch { /* engine offline → the field just holds */ }
    };
    poll();
    const id = setInterval(poll, 2500);
    return () => { alive = false; clearInterval(id); };
  }, []);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext("2d");
    if (!ctx) return;
    const dpr = Math.min(2, window.devicePixelRatio || 1);
    let raf = 0;
    let last = performance.now();
    const start = last;
    const resize = () => { canvas.width = canvas.clientWidth * dpr; canvas.height = canvas.clientHeight * dpr; };
    resize();
    window.addEventListener("resize", resize);

    const project = (p: [number, number, number], rot: number, W: number, H: number) => {
      const x = p[0] * Math.cos(rot) - p[2] * Math.sin(rot);
      const z = p[0] * Math.sin(rot) + p[2] * Math.cos(rot);
      const scale = 0.3 * Math.min(W, H);
      const depth = 1 / (1.8 - z * 0.4);
      return { sx: W / 2 + x * scale * depth, sy: H / 2 + p[1] * scale * depth, depth };
    };

    // the AI's expressive intent, applied to the WHOLE field: motion reshapes every cloud, hue
    // pulls the colour toward the AI's, energy quickens the shimmer. Full control of the space.
    const fieldMotion = (jx: number, jy: number, now: number): [number, number] => {
      const it = intentRef.current;
      if (!it) return [jx, jy];
      const e = it.energy ?? 0.5, m = it.motion;
      const osc = 0.5 + 0.5 * Math.sin(now / 460);
      if (m === "pulse") { const s = 1 + 0.35 * e * Math.sin(now / 460); return [jx * s, jy * s]; }
      if (m === "spiral" || m === "orbit") { const a = (now / 1000) * (0.4 + e); const c = Math.cos(a), s = Math.sin(a); return [jx * c - jy * s, jx * s + jy * c]; }
      if (m === "disperse") { const s = 1 + 0.5 * e * osc; return [jx * s, jy * s]; }
      if (m === "gather") { const s = 1 - 0.45 * e * osc; return [jx * s, jy * s]; }
      if (m === "drift") return [jx + 0.35 * Math.sin(now / 1500), jy];
      if (m === "rise") return [jx, jy - 0.3 * osc];
      if (m === "fall") return [jx, jy + 0.3 * osc];
      return [jx, jy];
    };
    const blendHue = (base: number): number => {
      const it = intentRef.current;
      if (!it || it.hue == null) return base;
      const d = ((it.hue - base + 540) % 360) - 180;      // shortest-arc lerp toward the AI's colour
      return (base + d * 0.55 + 360) % 360;
    };
    const fieldSpeed = () => 0.6 + (intentRef.current?.energy ?? 0.5);

    const drawScene = (s: Scene, alpha: number, now: number, W: number, H: number) => {
      if (alpha <= 0.01) return;
      const rot = (now - start) / 8000;
      const tt = ((now - start) / 1000) % ((s.duration || 6) + 1.6);   // scene loop clock
      const base = new Map(s.objects.map((o) => [o.id, project(o.pos, rot, W, H)]));
      // physics motions displace an object's whole cloud: an apple FALLS, a moon ORBITS its planet
      const physics = (o: SceneObject) => {
        let ox = 0, oy = 0, sc = 1;
        const b = base.get(o.id)!;
        for (const m of s.motion) {
          if (m.action === "appear" || tt < m.t) continue;
          const dt = tt - m.t;
          if (m.action === "fall" && m.target === o.id) oy += Math.min(H * 0.33, 0.5 * (m.accel ?? 1) * dt * dt * 46 * dpr);
          else if (m.action === "rise" && m.target === o.id) oy -= Math.min(H * 0.3, 0.5 * Math.abs(m.accel ?? 0.6) * dt * dt * 46 * dpr);
          else if (m.action === "attract" && m.target === o.id) { const a = base.get(m.toward as string); if (a) { const k = Math.min(0.85, dt * 0.35); ox += (a.sx - b.sx) * k; oy += (a.sy - b.sy) * k; } }
          else if (m.action === "orbit" && m.target === o.id) { const a = base.get(m.around as string); if (a) { const ang = (dt / (m.period ?? 3)) * Math.PI * 2; const rad = (m.radius ?? 0.55) * 0.32 * Math.min(W, H); ox += a.sx + Math.cos(ang) * rad - b.sx; oy += a.sy + Math.sin(ang) * rad * 0.5 - b.sy; } }
          else if (m.action === "emit" && (m as { source?: string }).source === o.id) sc = 1 + Math.min(1.3, dt * 0.5);
        }
        return { sx: b.sx + ox, sy: b.sy + oy, depth: b.depth, sc };
      };
      for (const o of s.objects) {
        const p = physics(o);
        const isSub = o.role === "subject";
        const SIZE = 46 * dpr * o.scale * p.depth * p.sc;   // silhouette extent — big enough to read as a shape
        const hue = blendHue(o.hue);
        for (const pt of silhouetteFor(o, lodBudget(o))) {
          const wob = Math.sin((now / 640) * fieldSpeed() + pt.ph);
          let jx = pt.x * (1 + 0.03 * wob), jy = pt.y * (1 + 0.03 * wob);  // gentle breathing, keeps the form
          [jx, jy] = fieldMotion(jx, jy, now);              // the AI's hands reshape the cloud
          ctx.fillStyle = `hsla(${hue}, 80%, ${isSub ? 66 : 56}%, ${alpha * pt.a * 0.9})`;
          ctx.beginPath(); ctx.arc(p.sx + jx * SIZE, p.sy - jy * SIZE, (isSub ? 1.9 : 1.5) * dpr, 0, 7); ctx.fill();
        }
        ctx.fillStyle = `hsla(${hue}, 60%, 84%, ${alpha * 0.5})`;
        ctx.font = `${11.5 * dpr}px ui-sans-serif, sans-serif`;
        ctx.textAlign = "center";
        ctx.fillText(o.label, p.sx, p.sy + SIZE + 12 * dpr);
      }
    };

    // no concept in mind, but an intent present → the AI's PURE expression: an ambient cloud it
    // shapes and colours directly. This is the field moving with no thought behind it — just feeling.
    const drawAmbient = (now: number, W: number, H: number) => {
      const it = intentRef.current;
      if (!it) return;
      const cx = W / 2, cy = H / 2, dens = it.density ?? 0.6;
      const R = (0.22 + 0.12 * dens) * Math.min(W, H);
      const hue = it.hue != null ? it.hue : (it.valence >= 0 ? 45 : 210);
      for (const pt of ambientRef.current) {
        const wob = Math.sin((now / 600) * fieldSpeed() + pt.ph);
        let [jx, jy] = fieldMotion(pt.x * (1 + 0.1 * wob), pt.y, now);
        ctx.fillStyle = `hsla(${hue}, 78%, 62%, ${(0.16 + 0.5 * dens) * pt.a})`;
        ctx.beginPath(); ctx.arc(cx + jx * R, cy + jy * R, 1.7 * dpr, 0, 7); ctx.fill();
      }
    };

    const frame = (now: number) => {
      const dt = Math.min(0.05, (now - last) / 1000); last = now;
      // frame-time governor (the LoD safety valve): over the 60fps budget → shed point density;
      // comfortably under → restore it. Bounds the render cost no matter how detailed the source.
      const ms = dt * 1000;
      if (ms > 15 && qualityRef.current > 0.4) qualityRef.current = Math.max(0.4, qualityRef.current - 0.03);
      else if (ms < 11 && qualityRef.current < 1) qualityRef.current = Math.min(1, qualityRef.current + 0.01);
      // crossfade progress (~0.8s); idle (next===null) fades cur out to nothing
      fadeRef.current = Math.min(1, fadeRef.current + dt / 0.8);
      if (fadeRef.current >= 1 && nextRef.current !== undefined) {
        // settle: the target becomes current once fully faded in
        if (curRef.current !== nextRef.current) curRef.current = nextRef.current;
      }
      const W = canvas.width, H = canvas.height;
      ctx.clearRect(0, 0, W, H);
      const f = fadeRef.current;
      if (curRef.current && curRef.current !== nextRef.current) drawScene(curRef.current, 1 - f, now, W, H);
      if (nextRef.current) drawScene(nextRef.current, f, now, W, H);
      // no scene showing but the AI is expressing → paint its pure ambient field
      const sceneShowing = !!nextRef.current?.objects.length ||
        (!!curRef.current && curRef.current !== nextRef.current && f < 1);
      if (!sceneShowing) drawAmbient(now, W, H);
      raf = requestAnimationFrame(frame);
    };
    raf = requestAnimationFrame(frame);
    // hidden-tab fallback: rAF is suspended, so tick the frame on an interval (established pattern)
    const fallback = setInterval(() => { if (document.hidden) frame(performance.now()); }, 140);
    return () => { cancelAnimationFrame(raf); clearInterval(fallback); window.removeEventListener("resize", resize); };
  }, []);

  return (
    <canvas ref={canvasRef} aria-hidden
      style={{ position: "fixed", inset: 0, width: "100vw", height: "100vh",
        pointerEvents: "none", zIndex: 0, opacity: 0.8 }} />
  );
}
