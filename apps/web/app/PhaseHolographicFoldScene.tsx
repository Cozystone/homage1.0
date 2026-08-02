"use client";

import { useEffect, useRef } from "react";
import * as THREE from "three";

export type FoldSceneNode = {
  id: string;
  label: string;
  source_type: string;
  position: [number, number, number] | number[];
  radius: number;
  coherence: number;
  amplitude?: number;
  phase?: number;
  frequency?: number;
};

export type FoldSceneEdge = { i: number; j: number; intf: number; constructive: boolean };

export type FoldScene = {
  render_kind?: string;
  nodes: FoldSceneNode[];
  edges: FoldSceneEdge[];
  core?: string[];
  trajectory?: { r: number; step: number; positions: number[][] }[];
  meta?: Record<string, unknown>;
};

const SOURCE_COLOR: Record<string, number> = {
  cloud_verified: 0x8ad7ff,
  local_brain: 0xb8a6ff,
  inner_voice: 0x9ad8ff,
  user_input: 0xcfe0ff,
  policy: 0x9aa3b6,
  emotion: 0xff8ad0,
  cloud_candidate: 0xf5b362,
  web_candidate: 0xf59e6b,
};

function colorFor(sourceType: string): number {
  return SOURCE_COLOR[sourceType] ?? 0x9aa3b6;
}

function easeInOutCubic(t: number): number {
  return t < 0.5 ? 4 * t * t * t : 1 - Math.pow(-2 * t + 2, 3) / 2;
}

function softTexture(): THREE.CanvasTexture {
  const c = document.createElement("canvas");
  c.width = 64;
  c.height = 64;
  const ctx = c.getContext("2d")!;
  const g = ctx.createRadialGradient(32, 32, 0, 32, 32, 32);
  g.addColorStop(0, "rgba(255,255,255,1)");
  g.addColorStop(0.3, "rgba(255,255,255,0.6)");
  g.addColorStop(1, "rgba(255,255,255,0)");
  ctx.fillStyle = g;
  ctx.fillRect(0, 0, 64, 64);
  return new THREE.CanvasTexture(c);
}

export default function PhaseHolographicFoldScene({ scene }: { scene: FoldScene }) {
  const mountRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    const mount = mountRef.current;
    if (!mount || !scene?.nodes?.length) return;

    const width = mount.clientWidth || 800;
    const height = mount.clientHeight || 600;
    const renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true });
    renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 2));
    renderer.setSize(width, height);
    renderer.domElement.style.touchAction = "none";
    mount.appendChild(renderer.domElement);

    const SCALE = 2.3;
    const cam = new THREE.PerspectiveCamera(52, width / height, 0.1, 100);
    cam.position.set(0, 0.5, 7.8);
    const scene3 = new THREE.Scene();
    const group = new THREE.Group();
    scene3.add(group);

    const nodes = scene.nodes;
    const n = nodes.length;
    const coreSet = new Set(scene.core || []);
    const frames = scene.trajectory || [];
    const hasTrajectory = frames.length >= 2 && frames.every((f) => f.positions.length === n);
    const finalPos = nodes.map((nd) => new THREE.Vector3(nd.position[0] * SCALE, nd.position[1] * SCALE, nd.position[2] * SCALE));
    const centers = nodes.map((_, i) => finalPos[i].clone());
    const sprite = softTexture();

    // --- REAL wave parameters per node (from the engine) ---
    // Ψ(r,t) = Σ_i (A_i / (d0 + d_i)) · e^{i (k_i·d_i − ω_i·t + φ_i)}
    const A = new Float64Array(n);
    const K = new Float64Array(n); // spatial wavenumber
    const W = new Float64Array(n); // temporal angular frequency
    const PH = new Float64Array(n);
    nodes.forEach((nd, i) => {
      const freq = Math.max(0, Math.min(1023, nd.frequency ?? 0)) / 1023;
      A[i] = Math.max(0.05, nd.amplitude ?? 0.4);
      K[i] = 1.6 + freq * 5.0;       // wavelength ≈ 2π/K spans the scene
      W[i] = 0.6 + freq * 1.6;       // different ω → real beats between nodes
      PH[i] = nd.phase ?? 0;
    });

    // --- field probes: sample the real interference field in the volume ---
    const PROBES = Math.max(300, Math.min(1500, Math.floor(48000 / Math.max(1, n))));
    const probePos = new Float32Array(PROBES * 3);
    const probeColor = new Float32Array(PROBES * 3);
    let seed = 9173;
    const rnd = () => { seed = (seed * 1103515245 + 12345) & 0x7fffffff; return seed / 0x7fffffff; };
    const PROBE_R = 2.7;
    for (let p = 0; p < PROBES; p++) {
      // uniform-ish point in a ball
      const u = rnd() * 2 - 1;
      const th = rnd() * Math.PI * 2;
      const rr = PROBE_R * Math.cbrt(rnd());
      const rxy = Math.sqrt(Math.max(0, 1 - u * u));
      probePos[p * 3] = rr * rxy * Math.cos(th);
      probePos[p * 3 + 1] = rr * rxy * Math.sin(th) * 0.8;
      probePos[p * 3 + 2] = rr * u;
    }
    const fieldGeo = new THREE.BufferGeometry();
    fieldGeo.setAttribute("position", new THREE.BufferAttribute(probePos, 3));
    fieldGeo.setAttribute("color", new THREE.BufferAttribute(probeColor, 3));
    const fieldMat = new THREE.PointsMaterial({ size: 0.11, map: sprite, vertexColors: true, transparent: true, opacity: 1.0, depthWrite: false, blending: THREE.AdditiveBlending, sizeAttenuation: true });
    group.add(new THREE.Points(fieldGeo, fieldMat));

    // --- every node emits an expanding spherical wavefront (phase velocity ω/k) ---
    const shells = nodes.map((_, i) => {
      const geo = new THREE.SphereGeometry(1, 14, 9);
      const mat = new THREE.MeshBasicMaterial({ color: colorFor(nodes[i].source_type), wireframe: true, transparent: true, opacity: 0, depthWrite: false, blending: THREE.AdditiveBlending });
      const mesh = new THREE.Mesh(geo, mat);
      group.add(mesh);
      return { mesh, node: i, v: W[i] / K[i], offset: (PH[i] / (2 * Math.PI)) % 1 };
    });
    const SHELL_MAX = 2.6;

    // bright core dot per node (real positions)
    const coreGeo = new THREE.BufferGeometry();
    const corePos = new Float32Array(n * 3);
    const coreCol = new Float32Array(n * 3);
    nodes.forEach((nd, i) => {
      const col = new THREE.Color(colorFor(nd.source_type));
      coreCol[i * 3] = col.r; coreCol[i * 3 + 1] = col.g; coreCol[i * 3 + 2] = col.b;
    });
    coreGeo.setAttribute("position", new THREE.BufferAttribute(corePos, 3));
    coreGeo.setAttribute("color", new THREE.BufferAttribute(coreCol, 3));
    const coreMat = new THREE.PointsMaterial({ size: 0.22, map: sprite, vertexColors: true, transparent: true, opacity: 0.95, depthWrite: false, blending: THREE.AdditiveBlending, sizeAttenuation: true });
    group.add(new THREE.Points(coreGeo, coreMat));

    // edges (real constructive/destructive)
    const edgeGeo = new THREE.BufferGeometry();
    const edgePositions = new Float32Array(scene.edges.length * 6);
    const edgeColors = new Float32Array(scene.edges.length * 6);
    const cCon = new THREE.Color(0x6fe9ff);
    const cDes = new THREE.Color(0xff6fc2);
    scene.edges.forEach((e, k) => {
      const c = e.constructive ? cCon : cDes;
      for (let s = 0; s < 2; s++) { edgeColors[k * 6 + s * 3] = c.r; edgeColors[k * 6 + s * 3 + 1] = c.g; edgeColors[k * 6 + s * 3 + 2] = c.b; }
    });
    edgeGeo.setAttribute("position", new THREE.BufferAttribute(edgePositions, 3));
    edgeGeo.setAttribute("color", new THREE.BufferAttribute(edgeColors, 3));
    const edgeMat = new THREE.LineBasicMaterial({ vertexColors: true, transparent: true, opacity: 0.3, blending: THREE.AdditiveBlending });
    group.add(new THREE.LineSegments(edgeGeo, edgeMat));

    // labels
    const labelSet = new Set([...(scene.core || []).slice(0, 2), "concept:atanor"]);
    const labelSprites: THREE.Sprite[] = [];
    nodes.forEach((nd, i) => {
      if (!labelSet.has(nd.id)) return;
      const canvas = document.createElement("canvas");
      canvas.width = 256; canvas.height = 64;
      const ctx = canvas.getContext("2d");
      if (!ctx) return;
      ctx.font = "600 30px ui-sans-serif, system-ui, sans-serif";
      ctx.fillStyle = "#eaf2ff"; ctx.textAlign = "center"; ctx.textBaseline = "middle";
      ctx.fillText(nd.label.slice(0, 18), 128, 32);
      const tex = new THREE.CanvasTexture(canvas);
      const s = new THREE.Sprite(new THREE.SpriteMaterial({ map: tex, transparent: true, opacity: 0, depthWrite: false }));
      s.scale.set(0.95, 0.24, 1);
      (s as unknown as { _node: number })._node = i;
      group.add(s);
      labelSprites.push(s);
    });

    function trajCentersAt(t: number) {
      if (!hasTrajectory) { centers.forEach((c, i) => c.copy(finalPos[i])); return; }
      const f = t * (frames.length - 1);
      const fi = Math.min(frames.length - 2, Math.floor(f));
      const frac = f - fi;
      const a = frames[fi].positions;
      const b = frames[fi + 1].positions;
      centers.forEach((c, i) => {
        c.set((a[i][0] + (b[i][0] - a[i][0]) * frac) * SCALE, (a[i][1] + (b[i][1] - a[i][1]) * frac) * SCALE, (a[i][2] + (b[i][2] - a[i][2]) * frac) * SCALE);
      });
    }

    // drag-to-rotate
    let yaw = 0, pitch = 0.05, dragging = false, lastX = 0, lastY = 0;
    const dom = renderer.domElement;
    const onDown = (e: PointerEvent) => { dragging = true; lastX = e.clientX; lastY = e.clientY; dom.style.cursor = "grabbing"; };
    const onMove = (e: PointerEvent) => { if (!dragging) return; yaw += (e.clientX - lastX) * 0.006; pitch += (e.clientY - lastY) * 0.006; pitch = Math.max(-1.3, Math.min(1.3, pitch)); lastX = e.clientX; lastY = e.clientY; };
    const onUp = () => { dragging = false; dom.style.cursor = "grab"; };
    dom.addEventListener("pointerdown", onDown);
    window.addEventListener("pointermove", onMove);
    window.addEventListener("pointerup", onUp);

    const start = performance.now();
    const FOLD_MS = 5200;
    const BURST_MS = 900; // central diffusion happens before the orb slides aside (~820ms)
    const frameInterval = 1000 / 60;
    let raf = 0, lastDraw = 0;
    const coreArr = coreGeo.getAttribute("position") as THREE.BufferAttribute;
    const edgeArr = edgeGeo.getAttribute("position") as THREE.BufferAttribute;
    const colArr = fieldGeo.getAttribute("color") as THREE.BufferAttribute;
    const GAIN = 0.42;

    function loop(now: number) {
      raf = requestAnimationFrame(loop);
      if (now - lastDraw < frameInterval) return;
      lastDraw = now;
      const elapsed = now - start;
      const tSec = elapsed / 1000;
      const foldT = easeInOutCubic(Math.min(1, elapsed / FOLD_MS));

      // central diffusion burst: nodes emerge from the centred orb (origin) and
      // spread out BEFORE the orb slides aside, then settle into the fold.
      const bt = Math.min(1, elapsed / BURST_MS);
      const birth = bt * bt * (3 - 2 * bt); // smoothstep
      trajCentersAt(foldT);
      for (let i = 0; i < n; i++) centers[i].multiplyScalar(birth);
      for (let i = 0; i < n; i++) coreArr.setXYZ(i, centers[i].x, centers[i].y, centers[i].z);
      coreArr.needsUpdate = true;

      // --- compute the REAL superposed interference field at each probe ---
      const fieldVis = foldT; // field fades in as the structure forms
      for (let p = 0; p < PROBES; p++) {
        const px = probePos[p * 3], py = probePos[p * 3 + 1], pz = probePos[p * 3 + 2];
        let re = 0, im = 0;
        for (let i = 0; i < n; i++) {
          const dx = px - centers[i].x, dy = py - centers[i].y, dz = pz - centers[i].z;
          const d = Math.sqrt(dx * dx + dy * dy + dz * dz);
          const amp = A[i] / (0.35 + d);              // spherical 1/r falloff
          const arg = K[i] * d - W[i] * tSec + PH[i];
          re += amp * Math.cos(arg);
          im += amp * Math.sin(arg);
        }
        // |Ψ| amplitude (sqrt of intensity) → less extreme dynamic range so the
        // constructive fringes are visible; still the real superposed field.
        const mag = Math.sqrt(re * re + im * im) * GAIN;
        let b = mag > 1 ? 1 : mag;
        b = b * b * (3 - 2 * b);                       // smooth contrast
        const bb = b * fieldVis;
        // destructive ≈ deep blue/dark, constructive ≈ bright cyan-white
        colArr.setXYZ(p, bb * bb * 0.7, bb * 0.78, (0.18 + 0.82 * bb) * bb);
      }
      colArr.needsUpdate = true;

      // every node's wavefront expands at its phase velocity, fades, repeats
      shells.forEach((sh) => {
        const ph = ((sh.v * tSec * 0.5 + sh.offset) % 1 + 1) % 1;
        const rad = 0.1 + ph * SHELL_MAX;
        sh.mesh.position.copy(centers[sh.node]);
        sh.mesh.scale.setScalar(rad);
        (sh.mesh.material as THREE.MeshBasicMaterial).opacity = (1 - ph) * 0.085 * fieldVis;
      });

      scene.edges.forEach((e, k) => {
        const a = centers[e.i], b = centers[e.j];
        edgeArr.setXYZ(k * 2, a.x, a.y, a.z);
        edgeArr.setXYZ(k * 2 + 1, b.x, b.y, b.z);
      });
      edgeArr.needsUpdate = true;
      edgeMat.opacity = 0.28 * foldT;

      labelSprites.forEach((s) => {
        const idx = (s as unknown as { _node: number })._node;
        const c = centers[idx];
        s.position.set(c.x, c.y + 0.34, c.z);
        (s.material as THREE.SpriteMaterial).opacity = 0.92 * foldT;
      });

      if (!dragging) yaw += 0.0012;
      group.rotation.set(pitch, yaw, 0);
      renderer.render(scene3, cam);
    }
    raf = requestAnimationFrame(loop);

    function onResize() {
      // mount is verified non-null by the early-return guard above; TS loses this in nested fns
      const w = mount!.clientWidth || width, h = mount!.clientHeight || height;
      cam.aspect = w / h; cam.updateProjectionMatrix(); renderer.setSize(w, h);
    }
    window.addEventListener("resize", onResize);

    return () => {
      cancelAnimationFrame(raf);
      window.removeEventListener("resize", onResize);
      dom.removeEventListener("pointerdown", onDown);
      window.removeEventListener("pointermove", onMove);
      window.removeEventListener("pointerup", onUp);
      renderer.dispose();
      fieldGeo.dispose(); coreGeo.dispose(); edgeGeo.dispose();
      fieldMat.dispose(); coreMat.dispose(); sprite.dispose();
      shells.forEach((sh) => { sh.mesh.geometry.dispose(); (sh.mesh.material as THREE.Material).dispose(); });
      labelSprites.forEach((s) => (s.material as THREE.SpriteMaterial).map?.dispose());
      if (renderer.domElement.parentNode === mount) mount.removeChild(renderer.domElement);
    };
  }, [scene]);

  return <div ref={mountRef} style={{ position: "absolute", inset: 0 }} />;
}
