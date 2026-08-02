"use client";

import { useEffect, useRef } from "react";
import * as THREE from "three";

export type HologramVoiceOrbState =
  | "idle"
  | "listening"
  | "thinking"
  | "speaking"
  | "resting"
  | "approval_needed"
  | "blocked";

type HologramVoiceOrbProps = {
  state: HologramVoiceOrbState;
  onActivate: () => void;
  onCancel: () => void;
  /** Particle density 0..1. 1 = full benchmark count (~43.2k pts). Lower = lighter render. */
  density?: number;
};

// Benchmark-run maximum: the orb was profiled smooth at this full count on the
// reference machine, so it is the slider's ceiling. Density scales down from here.
const RIBBON_PARTICLES = 24000;
const SHELL_PARTICLES = 14000;
const AURA_PARTICLES = 5200;
export const ORB_BENCHMARK_MAX_PARTICLES = RIBBON_PARTICLES + SHELL_PARTICLES + AURA_PARTICLES;
const SHAPE_COUNT = 7;
const GOLDEN_ANGLE = Math.PI * (3 - Math.sqrt(5));
const PALETTE = [
  new THREE.Color("#20f4ff"),
  new THREE.Color("#3aa8ff"),
  new THREE.Color("#bd6dff"),
  new THREE.Color("#ff4f9d"),
];

function fract(value: number) {
  return value - Math.floor(value);
}

function seeded(index: number, salt = 0) {
  return fract(Math.sin(index * 12.9898 + salt * 78.233) * 43758.5453123);
}

function siriRibbonPoint(shape: number, t: number, seed: number): THREE.Vector3 {
  const band = Math.floor(seed * 4);
  const local = fract(seed * 4);
  const phase = shape * 0.58 + band * 1.72 + local * 0.8;
  const angle = t * Math.PI * (2.2 + band * 0.18) + phase;
  const ribbonWidth = (local - 0.5) * (0.26 + Math.sin(angle + shape) * 0.045);
  const radius = 1.04 + Math.sin(angle * 1.7 + phase) * 0.2 + Math.cos(angle * 0.67 + shape) * 0.05;
  const squash = 0.48 + band * 0.06;
  const x = Math.cos(angle + Math.sin(angle * 0.73 + phase) * 0.32) * radius;
  const z = Math.sin(angle + Math.cos(angle * 0.82 + phase) * 0.22) * radius * squash;
  const y = Math.sin(angle * 1.05 + phase) * (0.48 - band * 0.035) + ribbonWidth;
  const point = new THREE.Vector3(x, y, z);
  point.applyAxisAngle(new THREE.Vector3(0, 0, 1), -0.58 + band * 0.34 + Math.sin(shape * 0.9) * 0.1);
  point.applyAxisAngle(new THREE.Vector3(1, 0, 0), 0.38 + Math.cos(shape * 0.7) * 0.18);
  point.multiplyScalar(1.08);
  return point;
}

function buildRibbonGeometry(ribbonCount: number) {
  const positions = new Float32Array(ribbonCount * 3);
  const colors = new Float32Array(ribbonCount * 3);
  const morphs = Array.from({ length: SHAPE_COUNT }, () => new Float32Array(ribbonCount * 3));

  for (let i = 0; i < ribbonCount; i += 1) {
    const t = i / ribbonCount;
    const seed = seeded(i);
    const band = Math.min(2, Math.floor(seed * 3));
    const color = PALETTE[band].clone().lerp(PALETTE[band + 1], 0.18 + seeded(i, 4) * 0.32);
    colors[i * 3] = color.r;
    colors[i * 3 + 1] = color.g;
    colors[i * 3 + 2] = color.b;

    for (let shape = 0; shape < SHAPE_COUNT; shape += 1) {
      const point = siriRibbonPoint(shape, t, seed);
      morphs[shape][i * 3] = point.x;
      morphs[shape][i * 3 + 1] = point.y;
      morphs[shape][i * 3 + 2] = point.z;
    }

    positions[i * 3] = morphs[0][i * 3];
    positions[i * 3 + 1] = morphs[0][i * 3 + 1];
    positions[i * 3 + 2] = morphs[0][i * 3 + 2];
  }

  const geometry = new THREE.BufferGeometry();
  geometry.setAttribute("position", new THREE.BufferAttribute(positions, 3));
  geometry.setAttribute("color", new THREE.BufferAttribute(colors, 3));
  return { geometry, morphs };
}

function buildShellGeometry(count: number, radius: number, opacityBias = 0) {
  const positions = new Float32Array(count * 3);
  const colors = new Float32Array(count * 3);
  const rim = new THREE.Color("#5ee7ff");
  const glass = new THREE.Color("#dcecff");
  const violet = new THREE.Color("#6557ff");

  for (let i = 0; i < count; i += 1) {
    const t = (i + 0.5) / count;
    const theta = i * GOLDEN_ANGLE;
    const y = 1 - 2 * t;
    const ring = Math.sqrt(Math.max(0, 1 - y * y));
    const wobble = Math.sin(theta * 1.7 + i * 0.003) * 0.01;
    const r = radius + wobble;
    const x = Math.cos(theta) * ring * r;
    const z = Math.sin(theta) * ring * r;
    positions[i * 3] = x;
    positions[i * 3 + 1] = y * r;
    positions[i * 3 + 2] = z;

    const rimWeight = Math.min(1, Math.pow(Math.abs(x) / r, 2.2) + Math.pow(Math.abs(y) / r, 3) * 0.35 + opacityBias);
    const color = glass.clone().lerp(rim, rimWeight * 0.65).lerp(violet, Math.max(0, z / r) * 0.22);
    colors[i * 3] = color.r;
    colors[i * 3 + 1] = color.g;
    colors[i * 3 + 2] = color.b;
  }

  const geometry = new THREE.BufferGeometry();
  geometry.setAttribute("position", new THREE.BufferAttribute(positions, 3));
  geometry.setAttribute("color", new THREE.BufferAttribute(colors, 3));
  return geometry;
}

function buildAuraGeometry(auraCount: number) {
  const positions = new Float32Array(auraCount * 3);
  const colors = new Float32Array(auraCount * 3);
  const cyan = new THREE.Color("#18e8ff");
  const rose = new THREE.Color("#ff3d85");

  for (let i = 0; i < auraCount; i += 1) {
    const u = seeded(i, 2);
    const v = seeded(i, 3);
    const theta = Math.PI * 2 * u;
    const phi = Math.acos(2 * v - 1);
    const r = 1.96 + seeded(i, 8) * 0.5;
    positions[i * 3] = Math.sin(phi) * Math.cos(theta) * r;
    positions[i * 3 + 1] = Math.cos(phi) * r;
    positions[i * 3 + 2] = Math.sin(phi) * Math.sin(theta) * r;
    const color = cyan.clone().lerp(rose, seeded(i, 5) * 0.35);
    colors[i * 3] = color.r;
    colors[i * 3 + 1] = color.g;
    colors[i * 3 + 2] = color.b;
  }

  const geometry = new THREE.BufferGeometry();
  geometry.setAttribute("position", new THREE.BufferAttribute(positions, 3));
  geometry.setAttribute("color", new THREE.BufferAttribute(colors, 3));
  return geometry;
}

export default function HologramVoiceOrb({ state, onActivate, onCancel, density = 1 }: HologramVoiceOrbProps) {
  const hostRef = useRef<HTMLButtonElement | null>(null);
  const clickGuardRef = useRef({ dragged: false, x: 0, y: 0 });
  const stateRef = useRef(state);

  useEffect(() => {
    stateRef.current = state;
  }, [state]);

  useEffect(() => {
    const host = hostRef.current;
    if (!host) return undefined;
    const activeHost = host;

    // Density scales every cloud down from the benchmark ceiling. Floors keep the
    // orb legible even at the lowest setting.
    const d = Math.min(1, Math.max(0.18, density));
    const ribbonCount = Math.max(4200, Math.round(RIBBON_PARTICLES * d));
    const shellCount = Math.max(2600, Math.round(SHELL_PARTICLES * d));
    const auraCount = Math.max(1100, Math.round(AURA_PARTICLES * d));
    const coreCount = Math.max(600, Math.round(1800 * d));

    const scene = new THREE.Scene();
    const camera = new THREE.PerspectiveCamera(38, 1, 0.1, 100);
    camera.position.set(0, 0, 7.2);

    // antialias is off: it has no visible effect on additively-blended point
    // sprites (no polygon edges) but costs real GPU fill — pure waste here.
    const renderer = new THREE.WebGLRenderer({ alpha: true, antialias: false, powerPreference: "high-performance" });
    renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 2));
    renderer.setClearColor(0x000000, 0);
    activeHost.appendChild(renderer.domElement);

    const root = new THREE.Group();
    scene.add(root);

    const auraGeometry = buildAuraGeometry(auraCount);
    const auraMaterial = new THREE.PointsMaterial({
      blending: THREE.AdditiveBlending,
      depthWrite: false,
      opacity: 0.11,
      size: 0.024,
      sizeAttenuation: true,
      transparent: true,
      vertexColors: true,
    });
    const aura = new THREE.Points(auraGeometry, auraMaterial);
    root.add(aura);

    const shellGeometry = buildShellGeometry(shellCount, 1.72, 0.06);
    const shellMaterial = new THREE.PointsMaterial({
      blending: THREE.AdditiveBlending,
      depthWrite: false,
      opacity: 0.24,
      size: 0.01,
      sizeAttenuation: true,
      transparent: true,
      vertexColors: true,
    });
    const shell = new THREE.Points(shellGeometry, shellMaterial);
    root.add(shell);

    const rimGeometry = buildShellGeometry(Math.floor(shellCount * 0.38), 1.76, 0.15);
    const rimMaterial = new THREE.PointsMaterial({
      blending: THREE.AdditiveBlending,
      depthWrite: false,
      opacity: 0.3,
      size: 0.014,
      sizeAttenuation: true,
      transparent: true,
      vertexColors: true,
    });
    const rim = new THREE.Points(rimGeometry, rimMaterial);
    root.add(rim);

    const { geometry: ribbonGeometry, morphs } = buildRibbonGeometry(ribbonCount);
    const ribbonMaterial = new THREE.PointsMaterial({
      blending: THREE.AdditiveBlending,
      depthWrite: false,
      opacity: 0.92,
      size: 0.027,
      sizeAttenuation: true,
      transparent: true,
      vertexColors: true,
    });
    const ribbons = new THREE.Points(ribbonGeometry, ribbonMaterial);
    root.add(ribbons);

    const coreGeometry = buildShellGeometry(coreCount, 0.16, 0.5);
    const coreMaterial = new THREE.PointsMaterial({
      blending: THREE.AdditiveBlending,
      depthWrite: false,
      opacity: 0.72,
      size: 0.042,
      sizeAttenuation: true,
      transparent: true,
      vertexColors: true,
    });
    const core = new THREE.Points(coreGeometry, coreMaterial);
    root.add(core);

    const clock = new THREE.Clock();
    const targetRotation = { x: -0.08, y: 0.22 };
    const currentRotation = { x: -0.08, y: 0.22 };
    const pointer = { active: false, x: 0, y: 0, moved: false };
    let animationId = 0;
    let activeShape = 0;
    let nextShape = 1;
    let morphStart = 0;
    // The 24k-particle ribbon morph (a CPU loop + full GPU buffer re-upload) is
    // the orb's heaviest per-frame cost. The morph is a slow ~4.4s transition, so
    // recomputing it every OTHER frame is visually identical but halves that work.
    // NOTE: this used to be a time-based ~33fps throttle — on a 60Hz display that
    // beats against rAF in a 2-1-2-1 frame pattern, so the ribbon cloud advanced on
    // an uneven cadence while rotation ran at 60fps. That mixed cadence is visible
    // as crackling micro-judder (owner: 파티클 렌더링이 지직거려). A frame-parity
    // throttle gives a perfectly even 30Hz (or 45Hz at 90Hz) update — same cost,
    // no beat pattern.
    let frameParity = 0;

    function resize() {
      const rect = activeHost.getBoundingClientRect();
      const width = Math.max(320, rect.width || 900);
      const height = Math.max(320, rect.height || 700);
      renderer.setSize(width, height, false);
      camera.aspect = width / height;
      camera.position.z = width > height ? 6.4 : 7.2;
      camera.updateProjectionMatrix();
    }

    function updateRibbonMorph(elapsed: number) {
      if (elapsed - morphStart > 4.4) {
        activeShape = nextShape;
        nextShape = (nextShape + 1 + Math.floor(elapsed) % (SHAPE_COUNT - 1)) % SHAPE_COUNT;
        if (nextShape === activeShape) nextShape = (nextShape + 1) % SHAPE_COUNT;
        morphStart = elapsed;
      }

      const morphT = Math.min(1, Math.max(0, (elapsed - morphStart) / 1.85));
      const ease = morphT * morphT * (3 - 2 * morphT);
      const positions = ribbonGeometry.getAttribute("position") as THREE.BufferAttribute;
      const from = morphs[activeShape];
      const to = morphs[nextShape];
      const state = stateRef.current;
      const pulse = state === "listening" ? 1.08 : state === "speaking" ? 1.12 : state === "thinking" ? 1.055 : 1;
      const fluid = Math.sin(elapsed * 1.6) * 0.028;

      for (let i = 0; i < ribbonCount * 3; i += 3) {
        const wave = Math.sin(elapsed * 1.35 + i * 0.0009) * fluid;
        positions.array[i] = (from[i] + (to[i] - from[i]) * ease) * pulse;
        positions.array[i + 1] = (from[i + 1] + (to[i + 1] - from[i + 1]) * ease + wave) * pulse;
        positions.array[i + 2] = (from[i + 2] + (to[i + 2] - from[i + 2]) * ease) * pulse;
      }
      positions.needsUpdate = true;
    }

    function renderFrame() {
      const elapsed = clock.getElapsedTime();
      frameParity = (frameParity + 1) & 1;
      if (frameParity === 0) {
        updateRibbonMorph(elapsed);
      }

      targetRotation.y += 0.0018;
      currentRotation.x += (targetRotation.x - currentRotation.x) * 0.055;
      currentRotation.y += (targetRotation.y - currentRotation.y) * 0.055;
      root.rotation.x = currentRotation.x + Math.sin(elapsed * 0.23) * 0.025;
      root.rotation.y = currentRotation.y;
      root.rotation.z = Math.sin(elapsed * 0.31) * 0.05;

      const breath = 1 + Math.sin(elapsed * 1.04) * 0.018;
      root.scale.setScalar(breath);
      ribbons.rotation.y = elapsed * 0.12;
      shell.rotation.y = -elapsed * 0.035;
      rim.rotation.y = elapsed * 0.052;
      aura.rotation.y = -elapsed * 0.018;
      core.rotation.y = elapsed * 0.4;

      const state = stateRef.current;
      ribbonMaterial.opacity = state === "resting" ? 0.62 : state === "blocked" ? 0.7 : 0.9;
      shellMaterial.opacity = state === "thinking" ? 0.3 : 0.22;
      auraMaterial.opacity = state === "listening" || state === "speaking" ? 0.17 : 0.1;

      renderer.render(scene, camera);
      animationId = window.requestAnimationFrame(renderFrame);
    }

    function handlePointerDown(event: PointerEvent) {
      pointer.active = true;
      pointer.moved = false;
      pointer.x = event.clientX;
      pointer.y = event.clientY;
      activeHost.setPointerCapture(event.pointerId);
    }

    function handlePointerMove(event: PointerEvent) {
      if (!pointer.active) return;
      const dx = event.clientX - pointer.x;
      const dy = event.clientY - pointer.y;
      if (Math.abs(dx) + Math.abs(dy) > 4) pointer.moved = true;
      targetRotation.y += dx * 0.006;
      targetRotation.x += dy * 0.004;
      targetRotation.x = Math.max(-0.72, Math.min(0.72, targetRotation.x));
      pointer.x = event.clientX;
      pointer.y = event.clientY;
    }

    function handlePointerUp(event: PointerEvent) {
      pointer.active = false;
      try {
        activeHost.releasePointerCapture(event.pointerId);
      } catch {
        // Pointer capture can already be released by the browser.
      }
    }

    activeHost.addEventListener("pointerdown", handlePointerDown);
    activeHost.addEventListener("pointermove", handlePointerMove);
    activeHost.addEventListener("pointerup", handlePointerUp);
    activeHost.addEventListener("pointercancel", handlePointerUp);

    resize();
    renderFrame();
    const resizeObserver = new ResizeObserver(resize);
    resizeObserver.observe(activeHost);

    return () => {
      window.cancelAnimationFrame(animationId);
      resizeObserver.disconnect();
      activeHost.removeEventListener("pointerdown", handlePointerDown);
      activeHost.removeEventListener("pointermove", handlePointerMove);
      activeHost.removeEventListener("pointerup", handlePointerUp);
      activeHost.removeEventListener("pointercancel", handlePointerUp);
      ribbonGeometry.dispose();
      ribbonMaterial.dispose();
      shellGeometry.dispose();
      shellMaterial.dispose();
      rimGeometry.dispose();
      rimMaterial.dispose();
      auraGeometry.dispose();
      auraMaterial.dispose();
      coreGeometry.dispose();
      coreMaterial.dispose();
      renderer.dispose();
      renderer.domElement.remove();
    };
    // density change tears down + rebuilds the scene at the new particle count.
  }, [density]);

  return (
    <button
      ref={hostRef}
      type="button"
      className="hologram-voice-orb"
      data-state={state}
      aria-label="ATANOR particle hologram"
      aria-pressed={state === "listening"}
      onPointerDown={(event) => {
        clickGuardRef.current = { dragged: false, x: event.clientX, y: event.clientY };
      }}
      onPointerMove={(event) => {
        const dx = event.clientX - clickGuardRef.current.x;
        const dy = event.clientY - clickGuardRef.current.y;
        if (Math.hypot(dx, dy) > 8) {
          clickGuardRef.current.dragged = true;
        }
      }}
      onClick={(event) => {
        if (clickGuardRef.current.dragged) {
          event.preventDefault();
          clickGuardRef.current.dragged = false;
          return;
        }
        if (state === "listening") {
          onCancel();
        } else {
          onActivate();
        }
      }}
    />
  );
}
