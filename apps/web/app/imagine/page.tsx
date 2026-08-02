"use client";
// 생성형 상상 필드 — 아무 개념이나 입력하면 그 개념의 "형상"을 파티클로 실시간 생성.
// 9개 아키타입 선택이 아니라, 개념의 그래프 시그니처에서 3D 초형상(supershape)을
// 합성한다. 무제한·결정론적·No-LLM/No-이미지모델. 형상은 회전하며 숨쉰다(애니메이션).
import { useEffect, useRef, useState } from "react";
import * as THREE from "three";

type Particle = { x: number; y: number; z: number; vx: number; vy: number; vz: number; r: number; g: number; b: number; a: number };
type Descriptor = { primary_lobes: number; secondary_lobes: number; complexity: number; grounded: boolean; note: string };

const ORANGE = "#d2521f";
const PRESETS = ["물", "쿠버네티스", "사랑", "블랙홀", "나무", "양자역학", "도시", "음악"];

export default function ImaginePage() {
  const mountRef = useRef<HTMLDivElement | null>(null);
  const partsRef = useRef<Particle[]>([]);
  const [concept, setConcept] = useState("");
  const [desc, setDesc] = useState<Descriptor | null>(null);
  const [loading, setLoading] = useState(false);
  const [count, setCount] = useState(0);

  const imagine = async (c: string) => {
    const q = c.trim();
    if (!q) return;
    setConcept(q);
    setLoading(true);
    try {
      const r = await fetch("/api/imagine", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ concept: q, count: 2600 }),
      });
      const j = await r.json();
      partsRef.current = j.particles ?? [];
      setDesc(j.descriptor ?? null);
      setCount(j.particle_count ?? 0);
    } catch {
      partsRef.current = [];
      setDesc(null);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    const mount = mountRef.current;
    if (!mount) return;
    const W = mount.clientWidth || 900;
    const H = mount.clientHeight || 560;
    const scene = new THREE.Scene();
    scene.background = new THREE.Color("#08090d");
    const camera = new THREE.PerspectiveCamera(50, W / H, 0.1, 100);
    camera.position.set(0, 0, 5.2);
    const renderer = new THREE.WebGLRenderer({ antialias: true, preserveDrawingBuffer: true });
    renderer.setPixelRatio(Math.min(2, window.devicePixelRatio || 1));
    renderer.setSize(W, H);
    mount.appendChild(renderer.domElement);

    const MAX = 6000;
    const positions = new Float32Array(MAX * 3);
    const colors = new Float32Array(MAX * 3);
    const geo = new THREE.BufferGeometry();
    geo.setAttribute("position", new THREE.BufferAttribute(positions, 3));
    geo.setAttribute("color", new THREE.BufferAttribute(colors, 3));
    geo.setDrawRange(0, 0);
    const mat = new THREE.PointsMaterial({ size: 0.035, vertexColors: true, transparent: true, opacity: 0.92, depthWrite: false, blending: THREE.AdditiveBlending });
    const points = new THREE.Points(geo, mat);
    scene.add(points);

    let raf = 0;
    const posAttr = geo.getAttribute("position") as THREE.BufferAttribute;
    const colAttr = geo.getAttribute("color") as THREE.BufferAttribute;
    // live copy of positions we integrate for the breathing motion
    let live: Particle[] = [];
    let syncedLen = -1;

    const render = () => {
      const parts = partsRef.current;
      if (parts !== live && parts.length !== syncedLen) {
        live = parts;
        syncedLen = parts.length;
        const n = Math.min(MAX, parts.length);
        for (let i = 0; i < n; i++) {
          const p = parts[i];
          positions[i * 3] = p.x; positions[i * 3 + 1] = p.y; positions[i * 3 + 2] = p.z;
          colors[i * 3] = p.r; colors[i * 3 + 1] = p.g; colors[i * 3 + 2] = p.b;
        }
        geo.setDrawRange(0, n);
        posAttr.needsUpdate = true;
        colAttr.needsUpdate = true;
      }
      // breathing: nudge positions along velocity, mean-reverting so it pulses
      const n = Math.min(MAX, live.length);
      const t = performance.now() / 1000;
      const puls = 0.5 + 0.5 * Math.sin(t * 1.4);
      for (let i = 0; i < n; i++) {
        const p = live[i];
        positions[i * 3] = p.x + p.vx * 6 * puls;
        positions[i * 3 + 1] = p.y + p.vy * 6 * puls;
        positions[i * 3 + 2] = p.z + p.vz * 6 * puls;
      }
      if (n > 0) posAttr.needsUpdate = true;
      points.rotation.y = t * 0.35;
      points.rotation.x = Math.sin(t * 0.2) * 0.15;
      renderer.render(scene, camera);
      raf = requestAnimationFrame(render);
    };
    raf = requestAnimationFrame(render);
    const fallback = setInterval(() => { if (document.hidden) render(); }, 140);
    const onResize = () => {
      const nw = mount.clientWidth || 900, nh = mount.clientHeight || 560;
      camera.aspect = nw / nh; camera.updateProjectionMatrix(); renderer.setSize(nw, nh);
    };
    window.addEventListener("resize", onResize);
    return () => {
      cancelAnimationFrame(raf); clearInterval(fallback); window.removeEventListener("resize", onResize);
      renderer.dispose(); geo.dispose();
      if (renderer.domElement.parentNode === mount) mount.removeChild(renderer.domElement);
    };
  }, []);

  return (
    <main style={{ position: "relative", minHeight: "100vh", background: "#08090d", color: "#e8e8ea", overflow: "hidden", fontFamily: "-apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif" }}>
      <div ref={mountRef} style={{ position: "absolute", inset: 0 }} />

      <div style={{ position: "relative", zIndex: 2, padding: "22px 26px", pointerEvents: "none" }}>
        <div style={{ display: "flex", alignItems: "baseline", gap: 12 }}>
          <h1 style={{ fontSize: 21, fontWeight: 600, margin: 0, letterSpacing: -0.3 }}>생성형 상상 필드</h1>
          <span style={{ fontSize: 11, color: ORANGE, border: `1px solid ${ORANGE}`, borderRadius: 999, padding: "2px 9px" }}>
            개념 → 파티클 형상 실시간 합성
          </span>
        </div>
        <p style={{ fontSize: 12, color: "#9aa2a8", margin: "8px 0 0", maxWidth: 640, lineHeight: 1.6 }}>
          아무 개념이나 입력하세요. ATANOR가 그 개념의 <b style={{ color: "#c7c7cd" }}>그래프 시그니처</b>(관계 다양성·복잡도·계층)에서
          3D 초형상을 <b style={{ color: "#c7c7cd" }}>합성</b>합니다 — 고정 아키타입 선택이 아니라 무제한 생성.
          형상은 회전하며 숨쉽니다. <b style={{ color: "#c7c7cd" }}>No-LLM · No-이미지모델 · 결정론적.</b>
        </p>
      </div>

      {/* composer */}
      <div style={{ position: "absolute", bottom: 26, left: "50%", transform: "translateX(-50%)", zIndex: 3, width: "min(680px, 92vw)", pointerEvents: "auto" }}>
        <div style={{ display: "flex", gap: 8, marginBottom: 10, flexWrap: "wrap", justifyContent: "center" }}>
          {PRESETS.map((p) => (
            <button key={p} onClick={() => imagine(p)} style={{ background: "rgba(255,255,255,0.06)", color: "#c7c7cd", border: "1px solid #23262e", borderRadius: 999, padding: "5px 12px", fontSize: 12.5, cursor: "pointer", backdropFilter: "blur(6px)" }}>{p}</button>
          ))}
        </div>
        <div style={{ display: "flex", gap: 8 }}>
          <input
            value={concept}
            onChange={(e) => setConcept(e.target.value)}
            onKeyDown={(e) => { if (e.key === "Enter") imagine(concept); }}
            placeholder="아무 개념이나 입력…  (예: 심장, 우주, 관료제)"
            style={{ flex: 1, background: "rgba(14,16,20,0.7)", color: "#e8e8ea", border: "1px solid #23262e", borderRadius: 12, padding: "12px 16px", fontSize: 14, outline: "none", backdropFilter: "blur(8px)" }}
          />
          <button onClick={() => imagine(concept)} disabled={loading} style={{ background: ORANGE, color: "#fff", border: "none", borderRadius: 12, padding: "12px 22px", fontSize: 14, fontWeight: 600, cursor: "pointer", opacity: loading ? 0.6 : 1 }}>
            {loading ? "합성 중…" : "생성"}
          </button>
        </div>
      </div>

      {/* descriptor */}
      {desc && (
        <div style={{ position: "absolute", top: 22, right: 26, zIndex: 2, background: "rgba(14,16,20,0.6)", border: "1px solid #1c242c", borderRadius: 12, padding: "12px 16px", minWidth: 190, backdropFilter: "blur(6px)", fontSize: 12 }}>
          <div style={{ fontSize: 13, fontWeight: 600, marginBottom: 8 }}>{concept}</div>
          <Row k="파티클" v={String(count)} />
          <Row k="1차 로브" v={String(desc.primary_lobes)} />
          <Row k="2차 로브" v={String(desc.secondary_lobes)} />
          <Row k="복잡도" v={desc.complexity.toFixed(3)} accent />
          <Row k="그래프 근거" v={desc.grounded ? "예" : "해시만"} />
        </div>
      )}
    </main>
  );
}

function Row({ k, v, accent }: { k: string; v: string; accent?: boolean }) {
  return (
    <div style={{ display: "flex", justifyContent: "space-between", gap: 16, padding: "2px 0" }}>
      <span style={{ color: "#8a929a" }}>{k}</span>
      <span style={{ color: accent ? ORANGE : "#e8e8ea", fontWeight: 500 }}>{v}</span>
    </div>
  );
}
