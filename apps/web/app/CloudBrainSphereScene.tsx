"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import * as THREE from "three";
import { browserMemorySafeMode, chromeHeapSnapshot, graphRenderFpsCap, resolveGraphPixelRatio, shouldRenderGraphFrame, writeGraphTelemetry } from "./graphRendererGuardrails";
import { useCloudLearningMetrics } from "./useCloudLearningMetrics";

type AnyRecord = Record<string, any>;

export type CloudBrainSphereStats = {
  logicalNodes: string;
  actualMaterializedNodes: number;
  renderedNodes: number;
  activeTiles: number;
  zoomLevel: number;
  renderBudgetNodes: number;
  renderBudgetEdges: number;
  compressionUsed: boolean;
  semanticAggregateNodesUsed: boolean;
  shellMode: boolean;
  actualNodeMode: boolean;
};

type Props = {
  edgeOpacity?: number;
  highEnd?: boolean;
  onStats?: (stats: CloudBrainSphereStats) => void;
};

const MAX_RENDERED_POINTS_BASELINE = 5000;
const MAX_RENDERED_POINTS_HIGH_END = 50000;
const MAX_RENDERED_EDGES_BASELINE = 10000;
const MAX_RENDERED_EDGES_HIGH_END = 100000;

function shellPoint(index: number, total: number, radius: number) {
  const golden = Math.PI * (3 - Math.sqrt(5));
  const y = 1 - (index / Math.max(1, total - 1)) * 2;
  const r = Math.sqrt(Math.max(0, 1 - y * y));
  const theta = golden * index;
  return new THREE.Vector3(Math.cos(theta) * r * radius, y * radius, Math.sin(theta) * r * radius);
}

let _sceneDotTex: THREE.Texture | null = null;
function sceneDotTexture(): THREE.Texture {
  if (_sceneDotTex) return _sceneDotTex;
  const canvas = document.createElement("canvas");
  canvas.width = 64;
  canvas.height = 64;
  const ctx = canvas.getContext("2d");
  if (ctx) {
    const gradient = ctx.createRadialGradient(32, 32, 0, 32, 32, 32);
    gradient.addColorStop(0, "rgba(255,255,255,1)");
    gradient.addColorStop(0.35, "rgba(255,255,255,0.82)");
    gradient.addColorStop(1, "rgba(255,255,255,0)");
    ctx.fillStyle = gradient;
    ctx.fillRect(0, 0, 64, 64);
  }
  _sceneDotTex = new THREE.CanvasTexture(canvas);
  return _sceneDotTex;
}

async function apiJson<T>(path: string): Promise<T> {
  const response = await fetch(path, { cache: "no-store" });
  if (!response.ok) throw new Error(`${path} failed: ${response.status}`);
  return response.json() as Promise<T>;
}

type Spark = { x: number; y: number; z: number; born: number };
// Frontier model: a new node is born flashing on the OUTER shell, settles, then
// slowly sinks inward (toward the dense lower-LOD interior) and dims — so the outer
// surface is always the freshest-learning frontier. Onion-skin: newest = outermost.
const SPARK_LIFETIME_MS = 26000;
const SPARK_MAX = 900; // cap concurrent frontier nodes

function randomSurfacePoint(): { x: number; y: number; z: number } {
  const u = Math.random();
  const v = Math.random();
  const theta = 2 * Math.PI * u;
  const phi = Math.acos(2 * v - 1);
  const r = 1.0;
  return { x: r * Math.sin(phi) * Math.cos(theta), y: r * Math.cos(phi), z: r * Math.sin(phi) * Math.sin(theta) };
}

export default function CloudBrainSphereScene({ edgeOpacity = 0.2, highEnd = false, onStats }: Props) {
  const containerRef = useRef<HTMLDivElement | null>(null);
  const sceneRef = useRef<{
    renderer: THREE.WebGLRenderer;
    scene: THREE.Scene;
    camera: THREE.PerspectiveCamera;
    shell: THREE.Points;
    nodes: THREE.Points;
    edges: THREE.LineSegments;
    fresh: THREE.Points;
    sparks: Spark[];
    animation: number;
    rotation: number;
  } | null>(null);
  const [zoomLevel, setZoomLevel] = useState(0);
  const [manifest, setManifest] = useState<AnyRecord | null>(null);
  const [materialized, setMaterialized] = useState<AnyRecord | null>(null);
  const [memorySafeMode, setMemorySafeMode] = useState(false);
  const budgets = useMemo(() => ({
    nodes: highEnd && !memorySafeMode ? MAX_RENDERED_POINTS_HIGH_END : MAX_RENDERED_POINTS_BASELINE,
    edges: highEnd && !memorySafeMode ? MAX_RENDERED_EDGES_HIGH_END : MAX_RENDERED_EDGES_BASELINE,
  }), [highEnd, memorySafeMode]);

  useEffect(() => {
    let cancelled = false;
    async function load() {
      let nextManifest = await apiJson<AnyRecord>("/api/cloud-brain/sphere/manifest").catch(() => null);
      let nextMaterialized = await apiJson<AnyRecord>(
        `/api/cloud-brain/sphere/materialize?tile_id=sphere_l0_x0000_y0000_r0&zoom=${zoomLevel}&budget_nodes=${budgets.nodes}&budget_edges=${budgets.edges}`,
      ).catch(() => null);
      // Fallback: the sphere's logical store can be empty while the surfaced CANDIDATE store
      // holds the real learned graph (status/candidate report tens of thousands). Render THAT
      // instead of a blank sphere — honestly styled as candidate (unverified), consistent with
      // what /status already reports. Positions are synthesized on the sphere (fibonacci).
      const sphereNodes = Array.isArray(nextMaterialized?.materialized_nodes) ? nextMaterialized.materialized_nodes : [];
      if (sphereNodes.length === 0) {
        const cand = await apiJson<AnyRecord>(
          `/api/cloud-brain/candidate/graph?max_nodes=${Math.min(budgets.nodes, 1200)}&max_edges=${Math.min(budgets.edges, 2400)}`,
        ).catch(() => null);
        const candNodes = Array.isArray(cand?.nodes) ? cand.nodes : [];
        if (candNodes.length > 0) {
          const posMap = new Map<string, { x: number; y: number; z: number }>();
          const materialized_nodes = candNodes.map((node: AnyRecord, index: number) => {
            const p = shellPoint(index, candNodes.length, 1.0);
            const xyz = { x: p.x, y: p.y, z: p.z };
            if (node?.id) posMap.set(String(node.id), xyz);
            return xyz;
          });
          const candEdges = Array.isArray(cand?.edges) ? cand.edges : [];
          const materialized_edges = candEdges
            .map((edge: AnyRecord) => {
              const s = posMap.get(String(edge?.source));
              const t = posMap.get(String(edge?.target));
              return s && t ? { source: s, target: t } : null;
            })
            .filter(Boolean);
          const status = await apiJson<AnyRecord>("/api/cloud-brain/candidate/status").catch(() => null);
          const logical = Number(status?.candidate_concepts ?? candNodes.length);
          nextManifest = { ...(nextManifest ?? {}), logical_total_nodes: String(logical), graph_source: "candidate_store_fallback" };
          nextMaterialized = { materialized_nodes, materialized_edges, logical_nodes_addressable: String(logical) };
        }
      }
      if (cancelled) return;
      setManifest(nextManifest);
      setMaterialized(nextMaterialized);
    }
    load();
    return () => {
      cancelled = true;
    };
  }, [budgets.edges, budgets.nodes, zoomLevel]);

  useEffect(() => {
    const container = containerRef.current;
    if (!container) return;
    const renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true });
    const pixelRatio = resolveGraphPixelRatio(window.devicePixelRatio);
    renderer.setPixelRatio(pixelRatio);
    renderer.setSize(container.clientWidth, container.clientHeight);
    container.appendChild(renderer.domElement);

    const scene = new THREE.Scene();
    const camera = new THREE.PerspectiveCamera(42, Math.max(1, container.clientWidth) / Math.max(1, container.clientHeight), 0.1, 100);
    camera.position.set(0, 0, 3.1);

    const shellGeometry = new THREE.BufferGeometry();
    const shellCount = 1800;
    const shellPositions = new Float32Array(shellCount * 3);
    for (let index = 0; index < shellCount; index += 1) {
      const point = shellPoint(index, shellCount, 1.08);
      shellPositions[index * 3] = point.x;
      shellPositions[index * 3 + 1] = point.y;
      shellPositions[index * 3 + 2] = point.z;
    }
    shellGeometry.setAttribute("position", new THREE.BufferAttribute(shellPositions, 3));
    const shell = new THREE.Points(
      shellGeometry,
      new THREE.PointsMaterial({
        color: new THREE.Color("#55708f"),
        opacity: 0.18,
        transparent: true,
        size: 0.008,
        blending: THREE.AdditiveBlending,
        depthWrite: false,
      }),
    );
    scene.add(shell);

    const nodes = new THREE.Points(
      new THREE.BufferGeometry(),
      new THREE.PointsMaterial({
        color: new THREE.Color("#ffb43d"),
        map: sceneDotTexture(),
        alphaTest: 0.01,
        opacity: 0.95,
        transparent: true,
        size: 0.03,
        blending: THREE.AdditiveBlending,
        depthWrite: false,
      }),
    );
    scene.add(nodes);

    const edges = new THREE.LineSegments(
      new THREE.BufferGeometry(),
      new THREE.LineBasicMaterial({
        color: new THREE.Color("#f8fbff"),
        opacity: Math.max(0.04, Math.min(0.72, edgeOpacity)),
        transparent: true,
        blending: THREE.AdditiveBlending,
      }),
    );
    scene.add(edges);

    // Live "fresh node" layer — newly learned nodes pop in from outside the shell
    // and flash green, then fade. Driven by the real cumulative-learning rate.
    const fresh = new THREE.Points(
      new THREE.BufferGeometry(),
      new THREE.PointsMaterial({
        vertexColors: true,
        size: 0.055,
        transparent: true,
        blending: THREE.AdditiveBlending,
        depthWrite: false,
      }),
    );
    scene.add(fresh);

    const state = { renderer, scene, camera, shell, nodes, edges, fresh, sparks: [] as Spark[], animation: 0, rotation: 0 };
    sceneRef.current = state;

    const resize = () => {
      const width = Math.max(1, container.clientWidth);
      const height = Math.max(1, container.clientHeight);
      renderer.setSize(width, height);
      camera.aspect = width / height;
      camera.updateProjectionMatrix();
    };
    let visibilityPaused = typeof document !== "undefined" ? document.hidden : false;
    let lastMemoryProbeAt = 0;
    let lastRenderedAt = 0;
    let currentMemorySafeMode = false;
    const onVisibilityChange = () => {
      visibilityPaused = document.hidden;
      lastRenderedAt = 0;
      container.dataset.visibilityPaused = String(visibilityPaused);
    };
    const animate = (now = performance.now()) => {
      const nodeCount = (state.nodes.geometry.getAttribute("position")?.count ?? 0) as number;
      const edgeCount = Math.floor(((state.edges.geometry.getAttribute("position")?.count ?? 0) as number) / 2);
      if (now - lastMemoryProbeAt > 1000) {
        lastMemoryProbeAt = now;
        const nextSafeMode = browserMemorySafeMode(chromeHeapSnapshot());
        if (nextSafeMode !== currentMemorySafeMode) {
          currentMemorySafeMode = nextSafeMode;
          setMemorySafeMode(nextSafeMode);
        }
      }
      const fpsCap = graphRenderFpsCap({ denseGraph: nodeCount > MAX_RENDERED_POINTS_BASELINE || edgeCount > MAX_RENDERED_EDGES_BASELINE, memorySafeMode: currentMemorySafeMode, visibilityPaused });
      writeGraphTelemetry(container, {
        densityParticles: shellCount,
        geometriesCount: 3,
        materializedNodes: nodeCount,
        materialsCount: 3,
        memorySafeMode: currentMemorySafeMode,
        pixelRatio,
        renderFpsCap: fpsCap,
        renderedEdges: edgeCount,
        visibilityPaused,
      });
      state.animation = window.requestAnimationFrame(animate);
      if (visibilityPaused || !shouldRenderGraphFrame(now, lastRenderedAt, fpsCap)) return;
      lastRenderedAt = now;
      state.rotation += 0.0018;
      shell.rotation.y = state.rotation;
      nodes.rotation.y = state.rotation;
      edges.rotation.y = state.rotation;
      // Fresh-node sparks: each newly learned node flies in from outside the shell,
      // flashes green, then fades (additive → black = invisible).
      const sparks = state.sparks;
      if (sparks.length) {
        const pos = new Float32Array(sparks.length * 3);
        const col = new Float32Array(sparks.length * 3);
        const alive: Spark[] = [];
        let n = 0;
        for (const s of sparks) {
          const age = now - s.born;
          if (age > SPARK_LIFETIME_MS) continue;
          const t = age / SPARK_LIFETIME_MS; // 0..1 over the node's frontier lifetime
          // radius: spawn just OUTSIDE the shell (1.22), settle to the shell (1.0)
          // in the first ~5%, then sink inward to the dense interior (~0.34).
          let rad: number;
          if (t < 0.05) {
            const s2 = t / 0.05;
            rad = 1.22 - 0.22 * (s2 * (2 - s2)); // ease-out to 1.0
          } else {
            rad = 1.0 - 0.66 * ((t - 0.05) / 0.95); // sink 1.0 → 0.34
          }
          pos[n * 3] = s.x * rad;
          pos[n * 3 + 1] = s.y * rad;
          pos[n * 3 + 2] = s.z * rad;
          // color: bright green flash while fresh → orange as it settles → dim as it
          // sinks (additive blending: darker = fades into the interior).
          const fresh = Math.max(0, 1 - t / 0.08);
          const bright = Math.max(0, 1 - t * 0.82);
          col[n * 3] = (0.28 + 0.62 * (1 - fresh)) * bright; // red rises as it ages
          col[n * 3 + 1] = (0.55 + 0.45 * fresh) * bright;   // green strong when fresh
          col[n * 3 + 2] = 0.28 * fresh * bright;
          alive.push(s);
          n += 1;
        }
        state.sparks = alive;
        const fg = new THREE.BufferGeometry();
        fg.setAttribute("position", new THREE.BufferAttribute(pos.subarray(0, n * 3), 3));
        fg.setAttribute("color", new THREE.BufferAttribute(col.subarray(0, n * 3), 3));
        state.fresh.geometry.dispose();
        state.fresh.geometry = fg;
      }
      state.fresh.rotation.y = state.rotation;
      renderer.render(scene, camera);
    };
    resize();
    animate();
    window.addEventListener("resize", resize);
    document.addEventListener("visibilitychange", onVisibilityChange);
    return () => {
      window.removeEventListener("resize", resize);
      document.removeEventListener("visibilitychange", onVisibilityChange);
      window.cancelAnimationFrame(state.animation);
      renderer.dispose();
      shellGeometry.dispose();
      (shell.material as THREE.Material).dispose();
      (nodes.geometry as THREE.BufferGeometry).dispose();
      (nodes.material as THREE.Material).dispose();
      (edges.geometry as THREE.BufferGeometry).dispose();
      (edges.material as THREE.Material).dispose();
      (fresh.geometry as THREE.BufferGeometry).dispose();
      (fresh.material as THREE.Material).dispose();
      renderer.domElement.remove();
      sceneRef.current = null;
    };
  }, []);

  useEffect(() => {
    const state = sceneRef.current;
    if (!state) return;
    const nodeRows = Array.isArray(materialized?.materialized_nodes) ? materialized.materialized_nodes : [];
    const positions = new Float32Array(nodeRows.length * 3);
    nodeRows.forEach((node: AnyRecord, index: number) => {
      positions[index * 3] = Number(node.x ?? 0);
      positions[index * 3 + 1] = Number(node.y ?? 0);
      positions[index * 3 + 2] = Number(node.z ?? 0);
    });
    const nodeGeometry = new THREE.BufferGeometry();
    nodeGeometry.setAttribute("position", new THREE.BufferAttribute(positions, 3));
    state.nodes.geometry.dispose();
    state.nodes.geometry = nodeGeometry;

    const nodeById = new Map(nodeRows.map((node: AnyRecord) => [String(node.cloud_node_id), node]));
    const edgeRows = Array.isArray(materialized?.materialized_edges) ? materialized.materialized_edges : [];
    const edgePositions: number[] = [];
    for (const edge of edgeRows) {
      const source = nodeById.get(String(edge.source));
      const target = nodeById.get(String(edge.target));
      if (!source || !target) continue;
      edgePositions.push(Number(source.x ?? 0), Number(source.y ?? 0), Number(source.z ?? 0));
      edgePositions.push(Number(target.x ?? 0), Number(target.y ?? 0), Number(target.z ?? 0));
    }
    const edgeGeometry = new THREE.BufferGeometry();
    edgeGeometry.setAttribute("position", new THREE.Float32BufferAttribute(edgePositions, 3));
    state.edges.geometry.dispose();
    state.edges.geometry = edgeGeometry;
    const edgeMaterial = state.edges.material as THREE.LineBasicMaterial;
    edgeMaterial.opacity = Math.max(0.04, Math.min(0.72, edgeOpacity));

    onStats?.({
      logicalNodes: String(manifest?.logical_total_nodes ?? materialized?.logical_nodes_addressable ?? "0"),
      actualMaterializedNodes: Number(manifest?.actual_materialized_nodes ?? 0),
      renderedNodes: Number(materialized?.rendered_nodes ?? nodeRows.length),
      activeTiles: Math.max(1, Number(Array.isArray(materialized?.child_tiles) ? materialized.child_tiles.length : 1)),
      zoomLevel,
      renderBudgetNodes: Number(materialized?.render_budget_nodes ?? budgets.nodes),
      renderBudgetEdges: Number(materialized?.render_budget_edges ?? budgets.edges),
      compressionUsed: Boolean(materialized?.compression_used || manifest?.compression_used),
      semanticAggregateNodesUsed: Boolean(materialized?.semantic_aggregate_nodes_used || manifest?.semantic_aggregate_nodes_used),
      shellMode: String(materialized?.render_mode ?? "shell") === "shell",
      actualNodeMode: String(materialized?.render_mode ?? "") === "actual_nodes",
    });
  }, [budgets.edges, budgets.nodes, edgeOpacity, manifest, materialized, onStats, zoomLevel]);

  // Spawn a fresh-node spark for every newly learned concept/relation so growth is
  // visible on the sphere per second. Reads the SHARED cloud-learning metrics
  // (one app-wide subscription — 난제 P4) instead of its own 2s poll.
  const learnMetrics = useCloudLearningMetrics();
  const lastTotalRef = useRef<number>(-1);
  useEffect(() => {
    if (!learnMetrics) return;
    const total = Number(learnMetrics.concepts_added ?? 0) + Number(learnMetrics.relations_added ?? 0);
    if (lastTotalRef.current >= 0) {
      const delta = Math.max(0, Math.min(120, total - lastTotalRef.current));
      const state = sceneRef.current;
      if (state && delta > 0) {
        const now = performance.now();
        for (let i = 0; i < delta; i += 1) {
          const p = randomSurfacePoint();
          state.sparks.push({ ...p, born: now + i * 60 }); // slight stagger
        }
        if (state.sparks.length > SPARK_MAX) state.sparks.splice(0, state.sparks.length - SPARK_MAX);
      }
    }
    lastTotalRef.current = total;
  }, [learnMetrics]);

  return (
    <div
      className="atanor-cloud-sphere-scene"
      ref={containerRef}
      onWheel={(event) => {
        event.preventDefault();
        setZoomLevel((current) => Math.max(0, Math.min(6, current + (event.deltaY > 0 ? -1 : 1))));
      }}
    >
      <div className="atanor-cloud-sphere-overlay">
        <span>Cloud Brain Shell</span>
        <strong>{materialized?.render_mode ?? "shell"}</strong>
      </div>
    </div>
  );
}
