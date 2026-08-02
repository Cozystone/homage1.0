"use client";
// 위상 홀로그래모픽 간섭 — 3D 엔진 (Three.js + OrbitControls).
// Gemini의 3D 씬 구조(HUD/파동 구체/간섭 계측/Replay)를 채택하되, 노드와 결착·
// 소독은 랜덤이 아니라 ATANOR가 실제로 훈련한 위상공간의 개념·공명 쌍이다:
// /api/base-brain/interference-scene 이 실데이터를 공급한다. 파동 구체가 서로
// 겹치는 순간이 '간섭 지점'으로 계측되어 HUD에 오른다.
import { useEffect, useRef, useState } from "react";

type SceneNode = { id: number; label: string };
type ScenePair = { a: number; b: number; resonance: number };
type Scene = { nodes: SceneNode[]; links: ScenePair[]; prunes: ScenePair[]; source?: string };

export default function InterferencePage() {
  const mountRef = useRef<HTMLDivElement | null>(null);
  const [scene, setScene] = useState<Scene | null>(null);
  const [hud, setHud] = useState({ nodes: 0, interference: 0 });
  const actionsRef = useRef<{ emit?: () => void; link?: () => void; prune?: () => void; replay?: () => void }>({});
  const bootedRef = useRef(false);

  useEffect(() => {
    fetch("/api/base-brain/interference-scene")
      .then((r) => r.json())
      .then((s: Scene) => setScene(s && s.nodes && s.nodes.length ? s : demoScene()))
      .catch(() => setScene(demoScene()));
  }, []);

  useEffect(() => {
    if (!scene || !mountRef.current) return;
    // SINGLE-OWNER boot: under StrictMode double-mount the drawing runner and
    // the live React instance split (measured: canvas animating while the live
    // probe saw waves:0). The ref survives remounts, so exactly one runner owns
    // scene+HUD; cleanup releases ownership for the next legitimate mount.
    if (bootedRef.current) return;
    bootedRef.current = true;
    let disposed = false;
    let cleanup: (() => void) | undefined;
    (async () => {
      const THREE = await import("three");
      const { OrbitControls } = await import("three/examples/jsm/controls/OrbitControls.js");
      if (disposed || !mountRef.current) return;

      const root = mountRef.current;
      root.querySelector("canvas")?.remove(); // clear any zombie canvas
      const three = new THREE.Scene();
      three.fog = new THREE.FogExp2(0x05070a, 0.015);
      const camera = new THREE.PerspectiveCamera(60, root.clientWidth / root.clientHeight, 0.1, 1000);
      camera.position.set(0, 22, 48);
      const renderer = new THREE.WebGLRenderer({ antialias: true });
      renderer.setSize(root.clientWidth, root.clientHeight);
      renderer.setClearColor(0x05070a);
      root.appendChild(renderer.domElement);
      const controls = new OrbitControls(camera, renderer.domElement);
      controls.enableDamping = true;
      controls.dampingFactor = 0.05;

      // ── nodes: REAL concepts, deterministic spherical layout ──
      const N = scene.nodes.length;
      const pruneNodeIds = new Set<number>();
      scene.prunes.forEach((p) => { pruneNodeIds.add(p.a); pruneNodeIds.add(p.b); });
      const nodeGeo = new THREE.SphereGeometry(0.55, 16, 16);
      const cyanMat = new THREE.MeshBasicMaterial({ color: 0x22d3ee });
      const warnMat = new THREE.MeshBasicMaterial({ color: 0xd2521f });
      const nodeMeshes: import("three").Mesh[] = [];
      const labelSprites: import("three").Sprite[] = [];
      const pos: import("three").Vector3[] = [];
      for (let i = 0; i < N; i++) {
        const phi = Math.acos(1 - (2 * (i + 0.5)) / N);
        const theta = Math.PI * (1 + Math.sqrt(5)) * i;
        const r = 17 + 5 * Math.sin(i * 2.399);
        const p = new THREE.Vector3(
          r * Math.sin(phi) * Math.cos(theta),
          r * Math.cos(phi) * 0.7,
          r * Math.sin(phi) * Math.sin(theta),
        );
        pos.push(p);
        const mesh = new THREE.Mesh(nodeGeo, pruneNodeIds.has(i) ? warnMat : cyanMat);
        mesh.position.copy(p);
        three.add(mesh);
        nodeMeshes.push(mesh);
        // label sprite (canvas texture)
        const cv = document.createElement("canvas");
        cv.width = 256; cv.height = 64;
        const cx = cv.getContext("2d")!;
        cx.font = "28px system-ui, sans-serif";
        cx.fillStyle = "rgba(226,232,240,0.9)";
        cx.fillText(scene.nodes[i].label, 8, 40);
        const tex = new THREE.CanvasTexture(cv);
        const spr = new THREE.Sprite(new THREE.SpriteMaterial({ map: tex, transparent: true }));
        spr.scale.set(7, 1.75, 1);
        spr.position.copy(p).add(new THREE.Vector3(0, 1.6, 0));
        three.add(spr);
        labelSprites.push(spr);
      }
      setHud({ nodes: N, interference: 0 });

      // ── persistent constructive links (REAL resonance, opacity = strength) ──
      const linkLines: import("three").Line[] = [];
      for (const l of scene.links) {
        const g = new THREE.BufferGeometry().setFromPoints([pos[l.a], pos[l.b]]);
        const m = new THREE.LineBasicMaterial({
          color: 0x22d3ee, transparent: true,
          opacity: 0.08 + 0.25 * Math.max(0, l.resonance),
        });
        const line = new THREE.Line(g, m);
        three.add(line);
        linkLines.push(line);
      }

      // ── waves + flashes state ──
      type Wave = { id: number; mesh: import("three").Mesh; radius: number; center: import("three").Vector3; hit: Set<number> };
      let waves: Wave[] = [];
      let flashes: { line: import("three").Line; life: number }[] = [];
      let interference = 0;
      let waveSeq = 0;
      const waveMat = new THREE.MeshBasicMaterial({
        color: 0x22d3ee, transparent: true, opacity: 0.35,
        blending: THREE.AdditiveBlending, depthWrite: false, wireframe: true,
      });

      const emit = () => {
        for (let k = 0; k < 2; k++) {
          const i = Math.floor(Math.random() * N);
          const mesh = new THREE.Mesh(new THREE.SphereGeometry(1, 20, 20), waveMat.clone());
          mesh.position.copy(pos[i]);
          three.add(mesh);
          waves.push({ id: waveSeq++, mesh, radius: 1, center: pos[i].clone(), hit: new Set() });
        }
      };
      const flashPairs = (pairs: ScenePair[], color: number, dashed: boolean) => {
        for (const l of pairs.slice(0, 6)) {
          const g = new THREE.BufferGeometry().setFromPoints([pos[l.a], pos[l.b]]);
          const m = dashed
            ? new THREE.LineDashedMaterial({ color, transparent: true, opacity: 0.9, dashSize: 1.2, gapSize: 0.8 })
            : new THREE.LineBasicMaterial({ color, transparent: true, opacity: 0.9 });
          const line = new THREE.Line(g, m);
          if (dashed) line.computeLineDistances();
          three.add(line);
          flashes.push({ line, life: 1 });
        }
      };
      const link = () => flashPairs(scene.links, 0x22d3ee, false);
      const prune = () => flashPairs(scene.prunes, 0xd2521f, true);
      const replay = () => {
        waves.forEach((w) => three.remove(w.mesh));
        flashes.forEach((f) => three.remove(f.line));
        waves = []; flashes = []; interference = 0;
        setHud({ nodes: N, interference: 0 });
      };
      actionsRef.current = { emit, link, prune, replay };
      (window as unknown as Record<string, unknown>).__atanorProbe = () => ({
        waves: waves.length, interference,
        radii: waves.map((w) => +w.radius.toFixed(1)),
        d01: waves.length >= 2 ? +waves[0].center.distanceTo(waves[1].center).toFixed(1) : null,
      });

      // ONE rAF loop owns everything (autopilot, HUD sync, physics) — separate
      // intervals under StrictMode double-mount left a zombie instance whose
      // intervals ran while its rAF was dead (measured: waves accumulated at
      // radius 1.0 forever and the counter never moved)
      let raf = 0;
      let lastEmit = 0;
      let lastHud = 0;
      const animate = (now: number) => {
        raf = requestAnimationFrame(animate);
        controls.update();
        if (now - lastEmit > 2200) {
          lastEmit = now;
          emit();
          if (Math.random() < 0.3) link();
          if (Math.random() < 0.15) prune();
        }
        if (now - lastHud > 400) {
          lastHud = now;
          setHud({ nodes: N, interference });
        }
        for (let i = waves.length - 1; i >= 0; i--) {
          const w = waves[i];
          w.radius += 0.22;
          w.mesh.scale.setScalar(w.radius);
          (w.mesh.material as import("three").MeshBasicMaterial).opacity = Math.max(0, (1 - w.radius / 34) * 0.35);
          if (w.radius >= 34) { three.remove(w.mesh); waves.splice(i, 1); continue; }
          // interference detection: expanding shells meeting = 간섭 지점.
          // pair identity by wave ID (indices shift on splice) and count each
          // meeting once, on the lower-id side
          for (const other of waves) {
            if (other.id >= w.id || w.hit.has(other.id)) continue;
            const d = w.center.distanceTo(other.center);
            if (d > 0.01 && d < w.radius + other.radius) {
              w.hit.add(other.id);
              interference++;
            }
          }
        }
        for (let i = flashes.length - 1; i >= 0; i--) {
          const f = flashes[i];
          f.life -= 0.012;
          (f.line.material as import("three").LineBasicMaterial).opacity = Math.max(0, f.life * 0.9);
          if (f.life <= 0) { three.remove(f.line); flashes.splice(i, 1); }
        }
        renderer.render(three, camera);
      };
      raf = requestAnimationFrame(animate);

      const onResize = () => {
        if (!mountRef.current) return;
        camera.aspect = mountRef.current.clientWidth / mountRef.current.clientHeight;
        camera.updateProjectionMatrix();
        renderer.setSize(mountRef.current.clientWidth, mountRef.current.clientHeight);
      };
      window.addEventListener("resize", onResize);
      cleanup = () => {
        cancelAnimationFrame(raf);
        window.removeEventListener("resize", onResize);
        renderer.dispose();
        root.removeChild(renderer.domElement);
      };
    })();
    return () => { disposed = true; cleanup?.(); bootedRef.current = false; };
  }, [scene]);

  const call = (name: "emit" | "link" | "prune" | "replay") => actionsRef.current[name]?.();

  return (
    <div style={{ position: "fixed", inset: 0, background: "#05070A", overflow: "hidden" }}>
      <div ref={mountRef} style={{ position: "absolute", inset: 0 }} />
      <div style={{
        position: "absolute", top: 20, left: 22, color: "#e2e8f0", pointerEvents: "none",
        background: "rgba(10,15,25,0.78)", padding: "14px 18px", borderRadius: 8,
        border: "1px solid rgba(56,189,248,0.25)", backdropFilter: "blur(10px)",
        fontFamily: "ui-monospace, monospace", fontSize: 13, minWidth: 210,
      }}>
        <div style={{ letterSpacing: "0.2em", color: "#38bdf8", fontWeight: 700, marginBottom: 8 }}>
          위상 홀로그래모픽 간섭
        </div>
        <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 5 }}>
          <span style={{ opacity: 0.7 }}>활성 노드</span><strong style={{ color: "#38bdf8" }}>{hud.nodes}</strong>
        </div>
        <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 5 }}>
          <span style={{ opacity: 0.7 }}>간섭 지점</span><strong style={{ color: "#38bdf8" }}>{hud.interference}</strong>
        </div>
        <div style={{ opacity: 0.55, fontSize: 11, marginTop: 8 }}>
          {scene?.source === "trained_phase_space" ? "실데이터 — 훈련된 위상공간" : "데모 데이터"}
        </div>
      </div>
      <div style={{
        position: "absolute", bottom: 26, left: "50%", transform: "translateX(-50%)",
        display: "flex", gap: 10, background: "rgba(10,15,25,0.78)",
        padding: "12px 18px", borderRadius: 10, backdropFilter: "blur(10px)",
        border: "1px solid rgba(56,189,248,0.2)",
      }}>
        {([["replay", "Replay"], ["emit", "주파수 발산"], ["link", "논리 결착"], ["prune", "오류 소독"]] as const).map(([fn, label]) => (
          <button key={fn} onClick={() => call(fn)} style={{
            background: "transparent",
            color: fn === "replay" ? "#a78bfa" : "#38bdf8",
            border: `1px solid ${fn === "replay" ? "rgba(167,139,250,0.6)" : "rgba(56,189,248,0.55)"}`,
            padding: "9px 16px", borderRadius: 6, cursor: "pointer", fontSize: 12.5,
            letterSpacing: "0.08em", fontWeight: 600,
          }}>{label}</button>
        ))}
      </div>
    </div>
  );
}

function demoScene(): Scene {
  const labels = ["개념", "그래프", "위상", "공명", "지식", "추론", "근거", "질문",
    "언어", "기억", "학습", "검증"];
  return {
    nodes: labels.map((label, id) => ({ id, label })),
    links: [{ a: 0, b: 1, resonance: 0.8 }, { a: 2, b: 3, resonance: 0.7 },
            { a: 4, b: 6, resonance: 0.6 }, { a: 5, b: 7, resonance: 0.5 }],
    prunes: [{ a: 0, b: 11, resonance: -0.5 }, { a: 3, b: 9, resonance: -0.4 }],
  };
}
