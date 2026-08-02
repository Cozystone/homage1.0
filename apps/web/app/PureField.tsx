"use client";

import { useEffect, useRef } from "react";
import * as THREE from "three";

/* PureField v2 — the cognitive plane, orbiting the orb (owner's v1.2 code spec).
   The four absolute rules hold: Points ONLY (no THREE.Line in this file),
   gaussian self-luminous grains, no grids/scaffolds/painted shapes. And now:
   the particles LIVE AROUND THE ORB (radial band, not screen-wide dust) and
   their MOTION IS THE STATE — each mode is a different physics:
     idle       slow orbital drift, loose breathing
     listening  concentric ripples running through the swarm
     thinking   spiral condensation — angular speed up, radius pulls in
     speaking   outward pulses riding the voice
     manual     near-still plane
   Everything animates through refs; renders can never reset the motion. */

export type PureFieldMode = "idle" | "listening" | "thinking" | "speaking" | "manual";

type PureFieldProps = {
  budget?: number;
  mode?: PureFieldMode;
  scale?: number; // ring radius multiplier — tracks the orb's on-screen size
};

function gaussian(): number {
  let u = 0;
  let v = 0;
  while (u === 0) u = Math.random();
  while (v === 0) v = Math.random();
  return Math.sqrt(-2.0 * Math.log(u)) * Math.cos(2.0 * Math.PI * v);
}

function grainTexture(): THREE.Texture {
  const c = document.createElement("canvas");
  c.width = 64;
  c.height = 64;
  const g = c.getContext("2d")!;
  const grad = g.createRadialGradient(32, 32, 0, 32, 32, 32);
  grad.addColorStop(0, "rgba(255,255,255,1)");
  grad.addColorStop(0.3, "rgba(255,255,255,0.6)");
  grad.addColorStop(1, "rgba(255,255,255,0)");
  g.fillStyle = grad;
  g.fillRect(0, 0, 64, 64);
  const tex = new THREE.CanvasTexture(c);
  tex.needsUpdate = true;
  return tex;
}

// plain GRAYS (owner): the field must never be confused with the orb's own
// colored particles — it is quiet context, not a second light show
const PALETTE = [
  new THREE.Color("#8b939e"),
  new THREE.Color("#a8b0ba"),
  new THREE.Color("#c6ccd4"),
];

export default function PureField({ budget = 5200, mode = "idle", scale = 1 }: PureFieldProps) {
  const hostRef = useRef<HTMLDivElement | null>(null);
  const modeRef = useRef<PureFieldMode>(mode);
  useEffect(() => {
    modeRef.current = mode;
  }, [mode]);

  useEffect(() => {
    const host = hostRef.current;
    if (!host) return undefined;

    const scene = new THREE.Scene();
    const camera = new THREE.PerspectiveCamera(46, 1, 0.1, 100);
    camera.position.set(0, 0, 10);
    const renderer = new THREE.WebGLRenderer({ alpha: true, antialias: false, powerPreference: "high-performance" });
    renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 1.5));
    renderer.setClearColor(0x000000, 0);
    host.appendChild(renderer.domElement);

    const n = Math.max(900, budget);
    // spherical home coordinates AROUND the orb: dense band near it, thin halo
    const radius = new Float32Array(n);
    const theta = new Float32Array(n);
    const phi = new Float32Array(n);
    const phase = new Float32Array(n);
    const pos = new Float32Array(n * 3);
    const col = new Float32Array(n * 3);
    for (let i = 0; i < n; i += 1) {
      radius[i] = (2.5 + Math.min(0.95, Math.abs(gaussian()) * 0.7)) * scale; // tight halo band
      theta[i] = Math.random() * Math.PI * 2;
      phi[i] = Math.acos(2 * Math.random() - 1);
      phase[i] = Math.random() * Math.PI * 2;
      const c = PALETTE[Math.floor(Math.random() * PALETTE.length)];
      const glow = 0.55 + Math.random() * 0.45; // photons, not dust
      col[i * 3] = c.r * glow;
      col[i * 3 + 1] = c.g * glow;
      col[i * 3 + 2] = c.b * glow;
    }

    const geo = new THREE.BufferGeometry();
    geo.setAttribute("position", new THREE.BufferAttribute(pos, 3));
    geo.setAttribute("color", new THREE.BufferAttribute(col, 3));
    const mat = new THREE.PointsMaterial({
      map: grainTexture(),
      blending: THREE.NormalBlending, // no additive glow — grays stay gray
      depthWrite: false,
      transparent: true,
      opacity: 0.8,
      size: 0.11,
      sizeAttenuation: true,
      vertexColors: true,
    });
    const points = new THREE.Points(geo, mat);
    scene.add(points);

    const clock = new THREE.Clock();
    let raf = 0;
    let last = 0;
    let spin = 0; // accumulated orbit angle — continuous across mode changes
    let lastT = 0;
    const STEP = 1 / 30;

    function resize() {
      const r = host!.getBoundingClientRect();
      const w = Math.max(320, r.width || 1280);
      const h = Math.max(240, r.height || 800);
      renderer.setSize(w, h, false);
      camera.aspect = w / h;
      camera.updateProjectionMatrix();
    }

    function frame() {
      const t = clock.getElapsedTime();
      const dt = Math.min(0.1, t - lastT);
      lastT = t;
      const m = modeRef.current;
      // angular velocity is the mode's tempo — integrated, so transitions GLIDE
      const w =
        m === "thinking" ? 0.34 : m === "listening" ? 0.14 : m === "speaking" ? 0.18 : m === "manual" ? 0.004 : 0.05;
      spin += w * dt;

      if (t - last >= STEP) {
        last = t;
        const attr = geo.getAttribute("position") as THREE.BufferAttribute;
        for (let i = 0; i < n; i += 1) {
          const p = phase[i];
          let r = radius[i];
          const th = theta[i] + spin * (0.65 + 0.35 * Math.sin(p)); // shear, not lockstep
          const ph = phi[i] + Math.sin(t * 0.05 + p) * 0.06;

          if (m === "thinking") {
            // spiral condensation: the swarm pulls toward the core and churns
            r = 2.45 * scale + (r - 2.45 * scale) * (0.45 + 0.1 * Math.sin(t * 0.9 + p));
          } else if (m === "listening") {
            // concentric ripple travelling outward through the band
            r += Math.sin(t * 3.2 - radius[i] * 2.4 + p * 0.2) * 0.22;
          } else if (m === "speaking") {
            // voice pulses pushing outward
            r += Math.max(0, Math.sin(t * 2.2 - radius[i] * 1.1)) * 0.34;
          } else if (m === "manual") {
            r = radius[i];
          } else {
            // idle: loose breathing drift
            r += Math.sin(t * 0.35 + p) * 0.12;
          }

          r = Math.max(2.35 * scale, r); // the gap is inviolable — nothing enters the orb's space
          const sr = Math.sin(ph) * r;
          attr.array[i * 3] = Math.cos(th) * sr + Math.sin(t * 0.07 + p * 1.7) * 0.08;
          attr.array[i * 3 + 1] = Math.cos(ph) * r * 0.78 + Math.cos(t * 0.06 + p) * 0.08;
          attr.array[i * 3 + 2] = Math.sin(th) * sr * 0.6;
        }
        attr.needsUpdate = true;
        mat.opacity = m === "manual" ? 0.3 : 0.8;
      }
      renderer.render(scene, camera);
      raf = window.requestAnimationFrame(frame);
    }

    resize();
    frame();
    const ro = new ResizeObserver(resize);
    ro.observe(host);
    return () => {
      window.cancelAnimationFrame(raf);
      ro.disconnect();
      geo.dispose();
      mat.map?.dispose();
      mat.dispose();
      renderer.dispose();
      renderer.domElement.remove();
    };
  }, [budget, scale]);

  return <div ref={hostRef} style={{ position: "absolute", inset: 0 }} />;
}
