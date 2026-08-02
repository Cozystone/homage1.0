"use client";
// 3D 진화 양식장 — 화학주성 세계에서 살아 꿈틀대는 선충 군집.
// 서버의 단일 백그라운드 스레드가 실제 진화 세계(먹이 그래디언트 항법 + 자연선택)를
// 한 코어에서 돌리고, 이 페이지는 각 선충을 물결치는 3D 몸(파동 이동 = 실제 선충의
// 유영 방식)으로 그린다. 색: 빨강(저적합) → 검정(고적합). Sibernetic 참고.
// 정직: 관찰용 양식장. 어떤 추론 경로에도 연결돼 있지 않다.
import { useEffect, useRef, useState } from "react";
import * as THREE from "three";

type Worm = {
  id: number;
  x: number;
  y: number;
  heading: number;
  fitness: number;
  energy: number;
  alive: boolean;
  color: [number, number, number];
};
type Food = { x: number; y: number; amount: number };
type Snap = {
  generation: number;
  population: number;
  alive: number;
  cap: number;
  difficulty: number;
  best_fitness: number;
  mean_fitness: number;
  world: { w: number; h: number };
  food: Food[];
  worms: Worm[];
  note: string;
};

const ORANGE = "#d2521f";
const SEG = 20; // body segments per worm
const SCALE = 0.16; // world units -> scene units

export default function EvolvePage() {
  const mountRef = useRef<HTMLDivElement | null>(null);
  const snapRef = useRef<Snap | null>(null);
  const [hud, setHud] = useState<Snap | null>(null);
  const [live, setLive] = useState(false);

  // poll the living world ~3 Hz
  useEffect(() => {
    let stop = false;
    const pull = async () => {
      try {
        const r = await fetch("/api/evolve/state", { cache: "no-store" });
        if (!r.ok) throw new Error(String(r.status));
        const j = (await r.json()) as Snap;
        if (!stop) {
          snapRef.current = j;
          setHud(j);
          setLive(true);
        }
      } catch {
        if (!stop) setLive(false);
      }
    };
    pull();
    const t = setInterval(pull, 320);
    return () => {
      stop = true;
      clearInterval(t);
    };
  }, []);

  // three.js scene
  useEffect(() => {
    const mount = mountRef.current;
    if (!mount) return;
    const W = mount.clientWidth || 960;
    const H = mount.clientHeight || 560;

    const scene = new THREE.Scene();
    scene.background = new THREE.Color("#0a0f16");
    scene.fog = new THREE.FogExp2("#0a0f16", 0.012);

    const camera = new THREE.PerspectiveCamera(50, W / H, 0.1, 500);
    camera.position.set(0, 18, 26);
    camera.lookAt(0, 0, 0);

    const renderer = new THREE.WebGLRenderer({ antialias: true, alpha: false, preserveDrawingBuffer: true });
    renderer.setPixelRatio(Math.min(2, window.devicePixelRatio || 1));
    renderer.setSize(W, H);
    mount.appendChild(renderer.domElement);

    // --- fluid haze (the tank's "liquid particles", like the reference) ---
    const HAZE = 1600;
    const hz = new Float32Array(HAZE * 3);
    for (let i = 0; i < HAZE; i++) {
      hz[i * 3] = (Math.random() - 0.5) * 44;
      hz[i * 3 + 1] = Math.random() * 10 - 1;
      hz[i * 3 + 2] = (Math.random() - 0.5) * 30;
    }
    const hazeGeo = new THREE.BufferGeometry();
    hazeGeo.setAttribute("position", new THREE.BufferAttribute(hz, 3));
    const hazeMat = new THREE.PointsMaterial({
      color: new THREE.Color("#3f6f5a"),
      size: 0.28,
      transparent: true,
      opacity: 0.5,
      depthWrite: false,
    });
    const haze = new THREE.Points(hazeGeo, hazeMat);
    scene.add(haze);

    // --- food (bright warm points) ---
    const foodGeo = new THREE.SphereGeometry(0.42, 8, 8);
    const foodMat = new THREE.MeshBasicMaterial({ color: new THREE.Color("#ffd68a") });
    const FOOD_CAP = 80;
    const food = new THREE.InstancedMesh(foodGeo, foodMat, FOOD_CAP);
    food.instanceMatrix.setUsage(THREE.DynamicDrawUsage);
    scene.add(food);

    // --- worms: one InstancedMesh of segment spheres for the whole colony ---
    const CAP = 48;
    const segGeo = new THREE.SphereGeometry(1, 8, 8); // scaled per-instance
    const segMat = new THREE.MeshBasicMaterial({});
    const body = new THREE.InstancedMesh(segGeo, segMat, CAP * SEG);
    body.instanceMatrix.setUsage(THREE.DynamicDrawUsage);
    body.instanceColor = new THREE.InstancedBufferAttribute(new Float32Array(CAP * SEG * 3), 3);
    scene.add(body);

    // arena floor ring for depth reference
    const floorGeo = new THREE.RingGeometry(0.1, 24, 48);
    const floorMat = new THREE.MeshBasicMaterial({
      color: new THREE.Color("#14202a"),
      transparent: true,
      opacity: 0.35,
      side: THREE.DoubleSide,
    });
    const floor = new THREE.Mesh(floorGeo, floorMat);
    floor.rotation.x = -Math.PI / 2;
    floor.position.y = -1.2;
    scene.add(floor);

    const dummy = new THREE.Object3D();
    const col = new THREE.Color();
    // smoothing state per worm id
    const disp = new Map<number, { x: number; z: number; h: number }>();

    const worldToScene = (x: number, y: number, w: number, h: number) => ({
      x: (x - w / 2) * SCALE,
      z: (y - h / 2) * SCALE,
    });

    let t0 = performance.now();
    const renderFrame = () => {
      const s = snapRef.current;
      const now = performance.now();
      const t = (now - t0) / 1000;
      // slow auto-orbit so the wriggle reads as 3D
      const ang = t * 0.12;
      camera.position.set(Math.sin(ang) * 27, 17 + Math.sin(t * 0.2) * 2, Math.cos(ang) * 27);
      camera.lookAt(0, -0.5, 0);
      haze.rotation.y = t * 0.02;

      if (s) {
        const w = s.world.w;
        const h = s.world.h;
        // food
        for (let i = 0; i < FOOD_CAP; i++) {
          if (i < s.food.length && s.food[i].amount > 0.05) {
            const p = worldToScene(s.food[i].x, s.food[i].y, w, h);
            const sc = 0.4 + Math.min(1, s.food[i].amount) * 0.5;
            dummy.position.set(p.x, -0.9, p.z);
            dummy.scale.setScalar(sc);
            dummy.rotation.set(0, 0, 0);
            dummy.updateMatrix();
          } else {
            dummy.position.set(0, -999, 0);
            dummy.scale.setScalar(0.0001);
            dummy.updateMatrix();
          }
          food.setMatrixAt(i, dummy.matrix);
        }
        food.instanceMatrix.needsUpdate = true;

        // worms
        const worms = s.worms;
        let inst = 0;
        for (let wi = 0; wi < CAP; wi++) {
          const wm = wi < worms.length ? worms[wi] : null;
          if (!wm || !wm.alive) {
            for (let si = 0; si < SEG; si++) {
              dummy.position.set(0, -999, 0);
              dummy.scale.setScalar(0.0001);
              dummy.rotation.set(0, 0, 0);
              dummy.updateMatrix();
              body.setMatrixAt(inst, dummy.matrix);
              inst++;
            }
            continue;
          }
          const target = worldToScene(wm.x, wm.y, w, h);
          let d = disp.get(wm.id);
          if (!d) {
            d = { x: target.x, z: target.z, h: wm.heading };
            disp.set(wm.id, d);
          }
          // glide toward the polled position; snap heading toward target
          d.x += (target.x - d.x) * 0.14;
          d.z += (target.z - d.z) * 0.14;
          let dh = wm.heading - d.h;
          while (dh > Math.PI) dh -= 2 * Math.PI;
          while (dh < -Math.PI) dh += 2 * Math.PI;
          d.h += dh * 0.18;

          // body frame: head at (d.x,d.z), heading d.h in the x-z plane
          const dirx = Math.cos(d.h);
          const dirz = Math.sin(d.h);
          const perpx = -dirz;
          const perpz = dirx;
          const amp = 0.7 + Math.min(1.4, wm.energy) * 0.5; // livelier when energetic
          const wormPhase = (wm.id % 32) * 0.6;
          const [cr, cg, cb] = wm.color;
          const segLen = 0.34;
          for (let si = 0; si < SEG; si++) {
            const along = si * segLen;
            const phase = 0.55 * si - t * 4.2 + wormPhase; // traveling wave
            const wave = amp * Math.sin(phase) * (0.4 + 0.6 * (si / SEG)); // tail swings more
            const bob = 0.35 * Math.sin(phase + 1.1);
            const px = d.x - dirx * along + perpx * wave;
            const pz = d.z - dirz * along + perpz * wave;
            const py = -0.6 + bob;
            const taper = 0.34 - 0.2 * (si / SEG); // head thick, tail thin
            dummy.position.set(px, py, pz);
            dummy.scale.setScalar(Math.max(0.08, taper));
            dummy.rotation.set(0, 0, 0);
            dummy.updateMatrix();
            body.setMatrixAt(inst, dummy.matrix);
            // color: fitness red->black, tail a touch dimmer
            const dim = 1 - 0.35 * (si / SEG);
            col.setRGB((cr / 255) * dim, (cg / 255) * dim, (cb / 255) * dim);
            body.setColorAt(inst, col);
            inst++;
          }
        }
        body.instanceMatrix.needsUpdate = true;
        if (body.instanceColor) body.instanceColor.needsUpdate = true;
      }
      renderer.render(scene, camera);
    };

    let raf = 0;
    const loop = () => {
      renderFrame();
      raf = requestAnimationFrame(loop);
    };
    raf = requestAnimationFrame(loop);
    // fallback: paint even when the tab is hidden/throttled (rAF pauses there)
    const fallback = setInterval(() => {
      if (document.hidden) renderFrame();
    }, 140);

    const onResize = () => {
      const nw = mount.clientWidth || 960;
      const nh = mount.clientHeight || 560;
      camera.aspect = nw / nh;
      camera.updateProjectionMatrix();
      renderer.setSize(nw, nh);
    };
    window.addEventListener("resize", onResize);

    return () => {
      cancelAnimationFrame(raf);
      clearInterval(fallback);
      window.removeEventListener("resize", onResize);
      renderer.dispose();
      segGeo.dispose();
      foodGeo.dispose();
      hazeGeo.dispose();
      floorGeo.dispose();
      if (renderer.domElement.parentNode === mount) mount.removeChild(renderer.domElement);
    };
  }, []);

  const post = async (path: string, body: Record<string, unknown> = {}) => {
    try {
      await fetch(path, {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify(body),
      });
    } catch {
      /* ignore */
    }
  };

  return (
    <main style={{ position: "relative", minHeight: "100vh", background: "#0a0f16", color: "#e8e8ea", overflow: "hidden", fontFamily: "-apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif" }}>
      <div ref={mountRef} style={{ position: "absolute", inset: 0 }} />

      {/* HUD */}
      <div style={{ position: "relative", zIndex: 2, padding: "22px 26px", pointerEvents: "none" }}>
        <div style={{ display: "flex", alignItems: "baseline", gap: 12 }}>
          <h1 style={{ fontSize: 21, fontWeight: 600, margin: 0, letterSpacing: -0.3 }}>3D 진화 양식장</h1>
          <span style={{ fontSize: 11, color: live ? ORANGE : "#8a8a90", border: `1px solid ${live ? ORANGE : "#333"}`, borderRadius: 999, padding: "2px 9px" }}>
            {live ? "LIVE · 한 코어에서 진화 중" : "엔진 연결 대기"}
          </span>
        </div>
        <p style={{ fontSize: 12, color: "#9aa2a8", margin: "8px 0 0", maxWidth: 620, lineHeight: 1.6 }}>
          선충은 <b style={{ color: "#c7c7cd" }}>먹이의 화학 그래디언트를 따라 항법</b>해야만 삽니다. 항법을
          못 하면 굶어 도태되고, 잘하는 소수가 교배해 다음 세대를 남깁니다. 색은 적합도 —
          <span style={{ color: "#e0604a" }}> 빨강(낮음)</span> → <span style={{ color: "#c7c7cd" }}>검정(높음)</span>.
          몸의 물결은 실제 선충의 유영(파동 이동)입니다. <b style={{ color: "#c7c7cd" }}>관찰용 — 추론에 연결 안 됨.</b>
        </p>
      </div>

      {/* stats */}
      <div style={{ position: "absolute", top: 22, right: 26, zIndex: 2, display: "flex", flexDirection: "column", gap: 8, textAlign: "right" }}>
        <Stat label="세대" v={hud ? String(hud.generation) : "—"} />
        <Stat label="개체수" v={hud ? `${hud.population} / ${hud.cap}` : "—"} />
        <Stat label="최고 적합도" v={hud ? hud.best_fitness.toFixed(2) : "—"} accent />
        <Stat label="난이도(결승선)" v={hud ? hud.difficulty.toFixed(2) : "—"} />
      </div>

      {/* controls */}
      <div style={{ position: "absolute", bottom: 24, left: 26, zIndex: 2, display: "flex", gap: 10 }}>
        <button onClick={() => post("/api/evolve/feed", { count: 10 })} style={btn}>먹이 투하</button>
        <button onClick={() => post("/api/evolve/crispr", { edits: 3, targets: 4 })} style={btn}>CRISPR 편집</button>
      </div>
    </main>
  );
}

const btn: React.CSSProperties = {
  background: "rgba(210,82,31,0.12)",
  color: ORANGE,
  border: `1px solid ${ORANGE}`,
  borderRadius: 10,
  padding: "9px 16px",
  fontSize: 13,
  cursor: "pointer",
  backdropFilter: "blur(6px)",
};

function Stat({ label, v, accent }: { label: string; v: string; accent?: boolean }) {
  return (
    <div style={{ background: "rgba(14,18,24,0.6)", border: "1px solid #1c242c", borderRadius: 10, padding: "8px 14px", minWidth: 120, backdropFilter: "blur(6px)" }}>
      <div style={{ fontSize: 10.5, color: "#8a929a", marginBottom: 3 }}>{label}</div>
      <div style={{ fontSize: 18, fontWeight: 600, color: accent ? ORANGE : "#e8e8ea" }}>{v}</div>
    </div>
  );
}
