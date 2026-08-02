"use client";

import { useEffect, useRef } from "react";
import * as THREE from "three";
import { EffectComposer } from "three/examples/jsm/postprocessing/EffectComposer.js";
import { RenderPass } from "three/examples/jsm/postprocessing/RenderPass.js";
import { UnrealBloomPass } from "three/examples/jsm/postprocessing/UnrealBloomPass.js";
import { browserMemorySafeMode, chromeHeapSnapshot, graphRenderFpsCap, resolveGraphPixelRatio, shouldRenderGraphFrame, writeGraphTelemetry } from "./graphRendererGuardrails";
import { computeWebGpuGraphLayout } from "./webgpuLayout";

export type Rag3DNode = {
  id: string;
  label: string;
  type: string;
  x: number;
  y: number;
  z: number;
  confidence?: number;
  source_type?: string;
  sourceType?: string;
  cluster_id?: string;
};

export type Rag3DEdge = {
  source: string;
  target: string;
  relation: string;
  weight?: number;
  confidence?: number;
  source_type?: string;
};

export type Rag3DScaleChunk = {
  chunk_id: string;
  type?: string;
  is_semantic_node?: boolean;
  represents_node_count?: number;
  represents_relation_count?: number;
  lod_level?: number;
  radius_range?: [number, number] | number[];
  theta_range?: [number, number] | number[];
  phi_range?: [number, number] | number[];
  density?: number;
  loaded?: boolean;
};

export type Rag3DGraph = {
  nodes: Rag3DNode[];
  edges: Rag3DEdge[];
  traversal_path?: string[];
  scale_chunks?: Rag3DScaleChunk[];
};

export type Rag3DControl = {
  serial: number;
  action: "zoom-in" | "zoom-out" | "left" | "right" | "up" | "down" | "reset";
};

export type Rag3DVisualState = "loading" | "learning" | "activating" | "completed" | "idle" | "low_memory_viewer";

type Rag3DSceneProps = {
  graph: Rag3DGraph | null;
  activeEdgeKeys?: string[];
  activeNodeIds?: string[];
  newNodeIds?: string[];
  control?: Rag3DControl;
  preserveSourceCoordinates?: boolean;
  onViewportChange?: (viewport: {
    cameraZ: number;
    focus: { x: number; y: number; z: number };
    radius: number;
  }) => void;
  onSelect?: (node: Rag3DNode) => void;
  theme?: "light" | "dark";
  visualState?: Rag3DVisualState;
  fitScale?: number;
  showLabels?: boolean;
  edgeOpacity?: number;
  synapsesPerSecond?: number;
  // When false, the live activity overlay (new-node orange branches, the bloom
  // glow) is hidden and the bloom pass is skipped for power efficiency. The engine
  // keeps running; this is purely a render gate.
  showActivity?: boolean;
  // Synapse trace (owner spec): fly the camera to this node and center it —
  // page-level sequencing walks a reasoning path node by node while the path
  // lights up via activeNodeIds/activeEdgeKeys. serial re-fires the same id.
  focusNode?: { serial: number; id: string } | null;
};

type VisibleEdge = Rag3DEdge & {
  active: boolean;
  index: number;
};

type SignalHalo = {
  bornAt: number;
  id: string;
  newNode: boolean;
  position: THREE.Vector3;
  scale: number;
};

type EdgePulse = {
  phase: number;
  source: string;
  target: string;
};

type SceneState = {
  activeEdgeKeys: Set<string>;
  activeNodeIds: Set<string>;
  activationHops: Map<string, number>;
  activationEdgeIntensity: Map<string, number>;
  camera: THREE.PerspectiveCamera;
  coordinateMutationWarned: boolean;
  dynamicObjects: THREE.Object3D[];
  edgeCapacity: number;
  edgeColorArray: Float32Array | null;
  edgeGeometry: THREE.BufferGeometry | null;
  edgeLines: THREE.LineSegments | null;
  edgePositionArray: Float32Array | null;
  edgePositionBufferDirty: boolean;
  edgePulseCount: number;
  frame: number;
  fitScale: number;
  frozenPositionSnapshot: Float32Array | null;
  graphEdges: Rag3DEdge[];
  graphNodes: Rag3DNode[];
  group: THREE.Group;
  haloCapacity: number;
  haloItems: SignalHalo[];
  haloMesh: THREE.InstancedMesh | null;
  knownNodeIds: Set<string>;
  lastFitDistance: number;
  lastGraphNodeCount: number;
  lastViewportEmitFrame: number;
  layoutDiagnostics: Record<string, number | string | number[]>;
  layoutRequestSerial: number;
  layoutSignature: string;
  newNodeIds: Set<string>;
  nodeBornAt: Map<string, number>;
  nodeCapacity: number;
  nodeColorArray: Float32Array | null;
  nodeGeometry: THREE.BufferGeometry | null;
  nodeIndexById: Map<string, number>;
  nodePoints: THREE.Points | null;
  nodePositionArray: Float32Array | null;
  nodePositionBufferDirty: boolean;
  nodePositionById: Map<string, THREE.Vector3>;
  nodeTargetById: Map<string, THREE.Vector3>;
  pointNodes: Rag3DNode[];
  pulseCapacity: number;
  pulseItems: EdgePulse[];
  pulseMesh: THREE.InstancedMesh | null;
  synapseLines: THREE.LineSegments | null;
  synapseGeometry: THREE.BufferGeometry | null;
  synapsePosArray: Float32Array | null;
  synapseColorArray: Float32Array | null;
  synapseCapacity: number;
  synapseItems: { nodes: number[]; born: number }[];
  synapseSpawnAccum: number;
  synapsesPerSecond: number;
  showActivity: boolean;
  nodeActivation: Float32Array | null;
  nodeActivationCapacity: number;
  activationFireAccum: number;
  renderer: THREE.WebGLRenderer;
  scaleChunks: Rag3DScaleChunk[];
  scene: THREE.Scene;
  shellCapacity: number;
  shellMesh: THREE.InstancedMesh | null;
  startedAt: number;
  userCameraControlUntilFrame: number;
  visibleEdges: VisibleEdge[];
  visualState: Rag3DVisualState;
  preserveSourceCoordinates: boolean;
  edgeOpacity: number;
  onViewportChange?: Rag3DSceneProps["onViewportChange"];
  zoomPulseAt: number;   // elapsed-seconds when last arrival zoom-pulse triggered
  zoomBaseZ: number;     // camera Z at moment of pulse trigger (render-only zoom, not real position)
};

const BASE_EDGE_COLOR = 0xb8c4d2;
const BASE_EDGE_WEAK = 0x667386;
const BASE_EDGE_ACTIVE_NEAR = 0xffffff;
const STRONG_EDGE_COLOR = 0xeaf2ff;
const NEON_ORANGE = 0xff6000;
const COLD_LABEL = "#eef3f8";
const GOLDEN_ANGLE = Math.PI * (3 - Math.sqrt(5));
const NEW_NODE_ANIMATION_SECONDS = 1.0;
// How long a freshly-arrived node keeps its identifiable orange flash after it
// settles into place, and how long the orange connecting edge takes to "grow"
// outward from the existing node to the new one.
const NEW_NODE_GLOW_SECONDS = 2.2;
const NEW_EDGE_GROW_SECONDS = 0.7;
// After the orange glow, the arrival "freezes" — its node and tendrils fade from
// orange to the normal white edge/node colour and stay that way.
const NEW_NODE_FREEZE_SECONDS = 1.8;
const MAX_SHELL_RENDER_CHUNKS = 384;
const DEFAULT_GRAPH_TILT_X = -0.22;
const DEFAULT_GRAPH_TILT_Y = 0.34;

const baseEdgeColor = new THREE.Color(BASE_EDGE_COLOR);
const weakEdgeColor = new THREE.Color(BASE_EDGE_WEAK);
const nearActiveEdgeColor = new THREE.Color(BASE_EDGE_ACTIVE_NEAR);
const strongEdgeColor = new THREE.Color(STRONG_EDGE_COLOR);
const neonOrangeColor = new THREE.Color(NEON_ORANGE);
// Deep red-orange for live arrivals. Low green channel so it stays unmistakably
// orange even when brightened on the additive field (a high-green orange clips to
// yellow-white).
const arrivalGlowColor = new THREE.Color(0xff5a00);
// Sky-blue = complement of the arrival orange. Used for the "synapse firing"
// activation lines that flicker across the graph each second.
const SYNAPSE_COLOR = 0x18b4ff;
const skyBlueColor = new THREE.Color(SYNAPSE_COLOR);
// An activated node momentarily turns deep/vivid pink.
const activationPinkColor = new THREE.Color(0xff1f8f);
const SYNAPSE_LIFE_SECONDS = 0.55;
const SYNAPSE_MAX = 700;
const constructionColor = new THREE.Color(0x22d3ee);
const localMemoryColor = new THREE.Color(0xffffff);
const representativeNodeColor = new THREE.Color(0xa7b7d1);
const cloudBrainColor = new THREE.Color(0x6fb0ff);
const workingMemoryColor = new THREE.Color(0x5eead4);
const contributorFragmentColor = new THREE.Color(0xffa028);
const seedSchemaColor = new THREE.Color(0x9b7cff);
const evidenceSourceColor = new THREE.Color(0x91a4bd);
const depthWhiteColor = new THREE.Color(0xffffff);
const tempColor = new THREE.Color();
const tempMatrix = new THREE.Matrix4();
const tempQuaternion = new THREE.Quaternion();
const tempRingQuaternion = new THREE.Quaternion().setFromEuler(new THREE.Euler(Math.PI / 2, 0, 0));
const tempScale = new THREE.Vector3();
const tempPosition = new THREE.Vector3();
let nodePointTexture: THREE.CanvasTexture | null = null;

function getNodePointTexture() {
  if (nodePointTexture) return nodePointTexture;
  const canvas = document.createElement("canvas");
  canvas.width = 64;
  canvas.height = 64;
  const context = canvas.getContext("2d");
  if (context) {
    // A clean solid dot with a soft glow falloff — NO dark center, so the vertex
    // colour shows as a coloured point (not a black sphere with a halo).
    context.clearRect(0, 0, canvas.width, canvas.height);
    // Solid bright core + a broad soft halo so each node reads as an emitting
    // point of light (a glowing synapse), not a flat dot.
    const dot = context.createRadialGradient(32, 32, 0, 32, 32, 32);
    dot.addColorStop(0, "rgba(255,255,255,1)");
    dot.addColorStop(0.16, "rgba(255,255,255,1)");
    dot.addColorStop(0.34, "rgba(255,255,255,0.78)");
    dot.addColorStop(0.6, "rgba(255,255,255,0.28)");
    dot.addColorStop(0.82, "rgba(255,255,255,0.09)");
    dot.addColorStop(1, "rgba(255,255,255,0)");
    context.fillStyle = dot;
    context.beginPath();
    context.arc(32, 32, 32, 0, Math.PI * 2);
    context.fill();
  }
  nodePointTexture = new THREE.CanvasTexture(canvas);
  nodePointTexture.colorSpace = THREE.SRGBColorSpace;
  nodePointTexture.needsUpdate = true;
  return nodePointTexture;
}

function edgeKey(source: string, target: string) {
  return `${source}:${target}`;
}

// Injected live-learning arrival nodes (concept graph "cloud-arrival-…" and
// surface graph "surface-arrival-…") share the same flash / freeze / grow viz.
function isArrivalId(id: string) {
  return id.startsWith("cloud-arrival") || id.startsWith("surface-arrival");
}

function edgeIsExplicitlyActive(activeEdgeKeys: Set<string>, source: string, target: string) {
  return activeEdgeKeys.has(edgeKey(source, target)) || activeEdgeKeys.has(edgeKey(target, source));
}

function coordinateAnimationAllowed(visualState: Rag3DVisualState) {
  return visualState === "loading" || visualState === "learning";
}

function movingPulseAllowed(visualState: Rag3DVisualState) {
  return visualState === "loading" || visualState === "learning" || visualState === "activating" || visualState === "completed";
}

function resolveVisualState(
  requested: Rag3DVisualState | undefined,
  graph: Rag3DGraph | null,
  activeNodeIds: Set<string>,
  activeEdgeKeys: Set<string>,
  newNodeIds: Set<string>,
): Rag3DVisualState {
  if (requested) return requested;
  if (!graph?.nodes?.length) return "idle";
  if (newNodeIds.size > 0) return "learning";
  if (activeNodeIds.size > 0 || activeEdgeKeys.size > 0) return "completed";
  return "idle";
}

function centroidTuple(position: THREE.Vector3) {
  return [Number(position.x.toFixed(3)), Number(position.y.toFixed(3)), Number(position.z.toFixed(3))];
}

function positionCentroid(positions: THREE.Vector3[], indices?: number[]) {
  const centroid = new THREE.Vector3();
  const selected = indices?.length ? indices.map((index) => positions[index]).filter(Boolean) : positions;
  selected.forEach((position) => centroid.add(position));
  if (selected.length) centroid.divideScalar(selected.length);
  return centroid;
}

function nodeBaseColor(node: Rag3DNode) {
  const sourceType = nodeSourceType(node);
  const nodeKind = `${node.type ?? ""} ${sourceType ?? ""}`.toLowerCase();
  if (/construction|surface/.test(nodeKind)) return constructionColor;
  if (/contributor|brain[_-]?link|public[_-]?fragment|fragment/.test(nodeKind)) return contributorFragmentColor;
  if (/working|working[_-]?memory|session|temporary/.test(nodeKind)) return workingMemoryColor;
  if (/seed|schema|root|ontology[_-]?schema/.test(nodeKind)) return seedSchemaColor;
  if (/evidence|source|document|payload|vault/.test(nodeKind)) return evidenceSourceColor;
  if (/cloud|web|external|public/.test(nodeKind)) return cloudBrainColor;
  if (/representative|sample|snapshot/.test(nodeKind) || node.id.startsWith("live-synapse")) return representativeNodeColor;
  return localMemoryColor;
}

function frozenStatusText(visualState: Rag3DVisualState) {
  if (visualState === "completed") return "Graph settled";
  if (visualState === "idle" || visualState === "low_memory_viewer") return "Graph settled";
  return null;
}

function disposeMaterial(material?: THREE.Material | THREE.Material[]) {
  if (Array.isArray(material)) {
    material.forEach((item) => item.dispose());
    return;
  }
  material?.dispose();
}

function disposeObject(object: THREE.Object3D) {
  object.traverse((child) => {
    const mesh = child as THREE.Mesh;
    mesh.geometry?.dispose?.();
    disposeMaterial(mesh.material as THREE.Material | THREE.Material[] | undefined);
  });
}

function removeDynamicObjects(state: SceneState) {
  for (const object of state.dynamicObjects) {
    state.group.remove(object);
    disposeObject(object);
  }
  state.dynamicObjects = [];
}

function addDynamicObject(state: SceneState, object: THREE.Object3D) {
  state.dynamicObjects.push(object);
  state.group.add(object);
}

function nextCapacity(count: number, minimum: number) {
  let capacity = minimum;
  while (capacity < count) capacity *= 2;
  return capacity;
}

function expandedFloatBuffer(previous: Float32Array | null, nextLength: number) {
  const next = new Float32Array(nextLength);
  if (previous) next.set(previous.subarray(0, Math.min(previous.length, next.length)));
  return next;
}

function hashUnit(value: string, salt: number) {
  let hash = 2166136261 ^ salt;
  for (let index = 0; index < value.length; index += 1) {
    hash ^= value.charCodeAt(index);
    hash = Math.imul(hash, 16777619);
  }
  return ((hash >>> 0) / 4294967295) * 2 - 1;
}

function hash01(value: string, salt: number) {
  return (hashUnit(value, salt) + 1) / 2;
}

function stableVolumePoint(id: string, index: number, total: number) {
  const count = Math.max(1, total);
  const y = THREE.MathUtils.clamp(1 - ((index + 0.5) / count) * 2 + hashUnit(id, 13) * 0.035, -0.98, 0.98);
  const theta = index * GOLDEN_ANGLE + hashUnit(id, 29) * 0.82;
  const radial = Math.sqrt(Math.max(0.0001, 1 - y * y));
  const volumeRadius = Math.min(48, 6.6 + Math.cbrt(count) * 1.72);
  const shellNoise = 0.66 + Math.cbrt(hash01(id, 47)) * 0.58;
  const localJitter = 1 + hashUnit(id, 71) * 0.065;
  const radius = volumeRadius * Math.min(1.14, shellNoise * localJitter);
  return new THREE.Vector3(
    Math.cos(theta) * radial * radius,
    y * radius,
    Math.sin(theta) * radial * radius * 1.46,
  );
}

function cameraDistanceForNodeCount(total: number) {
  return Math.min(260, 10 + Math.cbrt(Math.max(1, total)) * 3.8 + Math.sqrt(Math.max(1, total)) * 0.33);
}

function maxZoomDistanceForNodeCount(total: number) {
  const fitDistance = cameraDistanceForNodeCount(total);
  return Math.min(12000, Math.max(420, fitDistance * 28, Math.sqrt(Math.max(1, total)) * 42));
}

function clampCameraZ(camera: THREE.PerspectiveCamera, total: number) {
  camera.position.z = Math.max(3.2, Math.min(maxZoomDistanceForNodeCount(total), camera.position.z));
}

function normalizedSourcePositions(nodes: Rag3DNode[]) {
  const center = new THREE.Vector3();
  const rawPositions = nodes.map((node) => new THREE.Vector3(node.x, node.y, node.z));
  rawPositions.forEach((position) => center.add(position));
  if (rawPositions.length) center.divideScalar(rawPositions.length);
  let radius = 1;
  rawPositions.forEach((position) => {
    radius = Math.max(radius, position.distanceTo(center));
  });
  const sourceLimit = Math.min(18, 4.6 + Math.cbrt(Math.max(1, nodes.length)) * 0.82);
  const scale = radius > sourceLimit ? sourceLimit / radius : 1;
  return rawPositions.map((position) => position.sub(center).multiplyScalar(scale));
}

function initialSpreadPosition(node: Rag3DNode, source: THREE.Vector3, index: number, total: number) {
  if (total <= 14) return source;
  const target = stableVolumePoint(node.id, index, total);
  const sourceWeight = node.id.startsWith("live-synapse") ? 0.18 : total > 800 ? 0.07 : total > 300 ? 0.11 : 0.17;
  return source.multiplyScalar(sourceWeight).add(target.multiplyScalar(1 - sourceWeight));
}

function nodeSourceType(node: Rag3DNode) {
  return String(node.source_type ?? node.sourceType ?? (node.id.includes("cloud") || node.id.includes("web-") ? "cloud_fragment" : "local_memory"));
}

function semanticClusterKey(node: Rag3DNode) {
  return String(node.cluster_id ?? `${nodeSourceType(node)}:${node.type || "concept"}`);
}

function seededClusterCenter(key: string, index: number, total: number) {
  const theta = index * GOLDEN_ANGLE + hashUnit(key, 101) * 0.48;
  const z = hashUnit(key, 131) * 0.72;
  const radial = Math.sqrt(Math.max(0.08, 1 - z * z));
  const radius = 4.2 + Math.cbrt(Math.max(1, total)) * 0.54;
  return new THREE.Vector3(
    Math.cos(theta) * radial * radius,
    Math.sin(theta) * radial * radius,
    z * radius * 1.34,
  );
}

function edgeWeight(edge: Rag3DEdge) {
  return THREE.MathUtils.clamp(Number(edge.weight ?? edge.confidence ?? 0.52), 0.08, 2.4);
}

function computeOrganicGraphLayout(
  nodes: Rag3DNode[],
  edges: Rag3DEdge[],
  options: { activeNodeIds?: Set<string>; maxIterations?: number } = {},
) {
  const sources = normalizedSourcePositions(nodes);
  const nodeIndex = new Map(nodes.map((node, index) => [node.id, index]));
  const degree = new Map<string, number>();
  edges.forEach((edge) => {
    degree.set(edge.source, (degree.get(edge.source) ?? 0) + edgeWeight(edge));
    degree.set(edge.target, (degree.get(edge.target) ?? 0) + edgeWeight(edge));
  });
  const maxDegree = Math.max(1, ...nodes.map((node) => degree.get(node.id) ?? 0));
  const clusterKeys = Array.from(new Set(nodes.map(semanticClusterKey))).sort();
  const clusterCenters = new Map(clusterKeys.map((key, index) => [key, seededClusterCenter(key, index, clusterKeys.length)]));
  const total = Math.max(1, nodes.length);
  const baseRadius = Math.min(70, 7.4 + Math.cbrt(total) * 1.82);
  const activeNodeIds = options.activeNodeIds ?? new Set<string>();
  const positions = nodes.map((node, index) => {
    const source = initialSpreadPosition(node, sources[index].clone(), index, nodes.length);
    const cluster = clusterCenters.get(semanticClusterKey(node)) ?? new THREE.Vector3();
    const degreeRatio = (degree.get(node.id) ?? 0) / maxDegree;
    const isCloud = /cloud|web|external|fragment/i.test(nodeSourceType(node));
    const isPredicate = /predicate|relation|edge/i.test(node.type ?? "");
    const semantic = stableVolumePoint(node.id, index, total).multiplyScalar(isCloud ? 1.12 : 0.76);
    const position = new THREE.Vector3()
      .addScaledVector(semantic, 0.58)
      .addScaledVector(cluster, isPredicate ? 0.18 : 0.34)
      .addScaledVector(source, 0.08);
    const radiusFactor = isCloud ? 1.34 : 1 - degreeRatio * 0.46;
    position.normalize().multiplyScalar(Math.max(1.2, baseRadius * radiusFactor));
    position.x += hashUnit(node.id, 173) * 0.8;
    position.y += hashUnit(node.id, 211) * 0.8;
    position.z += hashUnit(node.id, 241) * 1.15;
    return position;
  });
  if (nodes.length <= 1) return { positions, diagnostics: layoutDiagnostics(nodes, edges, positions, activeNodeIds) };

  const sampledEdges = edges
    .filter((edge) => nodeIndex.has(edge.source) && nodeIndex.has(edge.target))
    .sort((left, right) => edgeWeight(right) - edgeWeight(left))
    .filter((edge, index) => index < 24_000 || activeNodeIds.has(edge.source) || activeNodeIds.has(edge.target) || index % Math.ceil(edges.length / 24_000) === 0);
  const iterations = Math.min(options.maxIterations ?? 60, nodes.length > 5_000 ? 18 : nodes.length > 2_000 ? 28 : nodes.length > 800 ? 42 : 64);
  const minDistance = nodes.length > 5_000 ? 0.52 : nodes.length > 1_400 ? 0.72 : nodes.length > 700 ? 0.9 : 1.05;
  const repulsionStride = nodes.length > 3_000 ? 7 : nodes.length > 1_200 ? 5 : nodes.length > 500 ? 3 : 1;

  for (let pass = 0; pass < iterations; pass += 1) {
    const cooling = 1 - pass / Math.max(1, iterations);
    for (const edge of sampledEdges) {
      const sourceIndex = nodeIndex.get(edge.source);
      const targetIndex = nodeIndex.get(edge.target);
      if (sourceIndex === undefined || targetIndex === undefined) continue;
      const source = positions[sourceIndex];
      const target = positions[targetIndex];
      const delta = target.clone().sub(source);
      const distance = Math.max(0.001, delta.length());
      const desired = THREE.MathUtils.lerp(1.8, 4.8, 1 / Math.sqrt(edgeWeight(edge) + 0.2));
      const spring = (distance - desired) * 0.012 * edgeWeight(edge) * cooling;
      delta.normalize().multiplyScalar(spring);
      source.add(delta);
      target.sub(delta);
    }
    for (let left = 0; left < positions.length; left += repulsionStride) {
      for (let right = left + repulsionStride; right < positions.length; right += repulsionStride) {
        const delta = positions[left].clone().sub(positions[right]);
        let distance = delta.length();
        if (distance >= minDistance) continue;
        if (distance < 0.001) {
          delta.set(hashUnit(nodes[left].id, 307) * 0.03 + 0.02, hashUnit(nodes[right].id, 311) * 0.03 + 0.02, 0.02);
          distance = delta.length();
        }
        const push = (minDistance - distance) * 0.34 * cooling;
        delta.normalize().multiplyScalar(push);
        positions[left].add(delta);
        positions[right].sub(delta);
      }
    }
    positions.forEach((position, index) => {
      const node = nodes[index];
      const cluster = clusterCenters.get(semanticClusterKey(node));
      const degreeRatio = (degree.get(node.id) ?? 0) / maxDegree;
      if (cluster) position.lerp(cluster, (0.004 + degreeRatio * 0.005) * cooling);
    });
  }
  const center = new THREE.Vector3();
  positions.forEach((position) => center.add(position));
  center.divideScalar(positions.length);
  positions.forEach((position) => position.sub(center));
  return { positions, diagnostics: layoutDiagnostics(nodes, edges, positions, activeNodeIds) };
}

function layoutDiagnostics(nodes: Rag3DNode[], edges: Rag3DEdge[], positions: THREE.Vector3[], activeNodeIds: Set<string>) {
  const degree = new Map<string, number>();
  edges.forEach((edge) => {
    degree.set(edge.source, (degree.get(edge.source) ?? 0) + 1);
    degree.set(edge.target, (degree.get(edge.target) ?? 0) + 1);
  });
  const averageDegree = nodes.length ? Array.from(degree.values()).reduce((sum, value) => sum + value, 0) / nodes.length : 0;
  const clusterCount = new Set(nodes.map(semanticClusterKey)).size;
  const activeIndices = nodes
    .map((node, index) => (activeNodeIds.has(node.id) ? index : -1))
    .filter((index) => index >= 0);
  const graphCentroid = positionCentroid(positions);
  const activeCentroid = activeIndices.length ? positionCentroid(positions, activeIndices) : graphCentroid.clone();
  return {
    layout_mode: "organic_semantic_force",
    graph_centroid: centroidTuple(graphCentroid),
    active_centroid: centroidTuple(activeCentroid),
    active_centroid_offset: Number(activeCentroid.distanceTo(graphCentroid).toFixed(3)),
    active_seed_count: activeNodeIds.size,
    active_cluster_count: new Set(nodes.filter((node) => activeNodeIds.has(node.id)).map(semanticClusterKey)).size,
    local_nodes: nodes.filter((node) => !/cloud|web|external|fragment/i.test(nodeSourceType(node))).length,
    cloud_fragment_nodes: nodes.filter((node) => /cloud|web|external|fragment/i.test(nodeSourceType(node))).length,
    average_degree: Number(averageDegree.toFixed(3)),
    visible_edges: edges.length,
    semantic_cluster_count: clusterCount,
    z_axis_ratio: axisDominanceRatio(positions),
  };
}

function axisDominanceRatio(positions: THREE.Vector3[]) {
  if (positions.length < 2) return 0;
  const mean = positions.reduce((acc, position) => acc.add(position), new THREE.Vector3()).divideScalar(positions.length);
  const variance = positions.reduce(
    (acc, position) => {
      acc.x += (position.x - mean.x) ** 2;
      acc.y += (position.y - mean.y) ** 2;
      acc.z += (position.z - mean.z) ** 2;
      return acc;
    },
    new THREE.Vector3(),
  ).divideScalar(positions.length);
  const horizontal = Math.max(0.0001, (variance.x + variance.y) / 2);
  return Number((variance.z / horizontal).toFixed(3));
}

function computeActivationMaps(nodes: Rag3DNode[], edges: Rag3DEdge[], activeNodeIds: Set<string>, activeEdgeKeys: Set<string>) {
  const nodeIds = new Set(nodes.map((node) => node.id));
  const adjacency = new Map<string, string[]>();
  edges.forEach((edge) => {
    if (!nodeIds.has(edge.source) || !nodeIds.has(edge.target)) return;
    if (!adjacency.has(edge.source)) adjacency.set(edge.source, []);
    if (!adjacency.has(edge.target)) adjacency.set(edge.target, []);
    adjacency.get(edge.source)!.push(edge.target);
    adjacency.get(edge.target)!.push(edge.source);
  });
  const hops = new Map<string, number>();
  const queue: Array<{ id: string; hop: number }> = [];
  activeNodeIds.forEach((id) => {
    if (nodeIds.has(id)) {
      hops.set(id, 0);
      queue.push({ id, hop: 0 });
    }
  });
  edges.forEach((edge) => {
    if (edgeIsExplicitlyActive(activeEdgeKeys, edge.source, edge.target)) {
      [edge.source, edge.target].forEach((id) => {
        if (nodeIds.has(id) && !hops.has(id)) {
          hops.set(id, 0);
          queue.push({ id, hop: 0 });
        }
      });
    }
  });
  const maxHopDepth = nodes.length > 5_000 ? 1 : nodes.length > 1_500 ? 2 : 3;
  while (queue.length) {
    const item = queue.shift()!;
    if (item.hop >= maxHopDepth) continue;
    for (const next of adjacency.get(item.id) ?? []) {
      const nextHop = item.hop + 1;
      if ((hops.get(next) ?? Infinity) <= nextHop) continue;
      hops.set(next, nextHop);
      queue.push({ id: next, hop: nextHop });
    }
  }
  const edgeIntensity = new Map<string, number>();
  edges.forEach((edge) => {
    const sourceHop = hops.get(edge.source);
    const targetHop = hops.get(edge.target);
    if (sourceHop === undefined && targetHop === undefined && !edgeIsExplicitlyActive(activeEdgeKeys, edge.source, edge.target)) return;
    const explicit = edgeIsExplicitlyActive(activeEdgeKeys, edge.source, edge.target);
    const hop = Math.min(sourceHop ?? 4, targetHop ?? 4);
    const intensity = explicit ? 1 : Math.exp(-hop * 1.72) * (hop === 0 ? 0.42 : 0.12);
    if (intensity > 0.055) edgeIntensity.set(edgeKey(edge.source, edge.target), intensity);
  });
  return { hops, edgeIntensity };
}

function spreadPositions(nodes: Rag3DNode[], edges: Rag3DEdge[] = [], activeNodeIds = new Set<string>()) {
  return computeOrganicGraphLayout(nodes, edges, { activeNodeIds });
}

function sourceCoordinatePositions(nodes: Rag3DNode[]) {
  const positions = nodes.map((node) => new THREE.Vector3(Number(node.x) || 0, Number(node.y) || 0, Number(node.z) || 0));
  if (positions.length <= 2) return positions;
  const center = positions.reduce((sum, position) => sum.add(position), new THREE.Vector3()).divideScalar(positions.length);
  let radius = 1;
  positions.forEach((position) => {
    radius = Math.max(radius, position.distanceTo(center));
  });
  const scale = radius > 18 ? 18 / radius : 1;
  const jitterScale = Math.min(0.055, Math.max(0.012, radius * 0.004));
  return positions.map((position, index) => {
    const volume = stableVolumePoint(nodes[index].id, index, nodes.length);
    return position.clone().sub(center).multiplyScalar(scale).add(volume.multiplyScalar(jitterScale));
  });
}

function viewportRadiusForCamera(camera: THREE.PerspectiveCamera) {
  const fovRadians = THREE.MathUtils.degToRad(camera.fov);
  return Math.max(8, Math.min(220, camera.position.z * Math.tan(fovRadians / 2) * 1.75));
}

function fitDistanceForPositions(positions: THREE.Vector3[], camera: THREE.PerspectiveCamera, useNodeCountFloor = true) {
  if (!positions.length) return cameraDistanceForNodeCount(0);
  const center = new THREE.Vector3();
  positions.forEach((position) => center.add(position));
  center.divideScalar(positions.length);
  let radius = 1;
  positions.forEach((position) => {
    radius = Math.max(radius, position.distanceTo(center));
  });
  const fovRadians = THREE.MathUtils.degToRad(camera.fov);
  const aspectCompensation = camera.aspect < 1 ? 1 / Math.max(0.62, camera.aspect) : 1;
  const spatialFitDistance = (radius * (useNodeCountFloor ? 1.34 : 0.72) * aspectCompensation) / Math.tan(fovRadians / 2);
  return Math.min(2200, Math.max(useNodeCountFloor ? cameraDistanceForNodeCount(positions.length) : 3.2, spatialFitDistance));
}

function labelSprite(text: string, scale = 1) {
  const canvas = document.createElement("canvas");
  canvas.width = 512;
  canvas.height = 128;
  const context = canvas.getContext("2d");
  if (context) {
    context.clearRect(0, 0, canvas.width, canvas.height);
    context.font = "700 32px Helvetica, Arial, sans-serif";
    context.fillStyle = COLD_LABEL;
    context.strokeStyle = "rgba(0,0,0,0.82)";
    context.lineWidth = 7;
    context.strokeText(text.slice(0, 18), 20, 74);
    context.fillText(text.slice(0, 18), 20, 74);
  }
  const texture = new THREE.CanvasTexture(canvas);
  const material = new THREE.SpriteMaterial({ map: texture, transparent: true, opacity: 0.72 });
  const sprite = new THREE.Sprite(material);
  sprite.scale.set(1.7 * scale, 0.42 * scale, 1);
  return sprite;
}

function shouldShowLabel(node: Rag3DNode, totalNodes: number, isActive: boolean) {
  if (node.id.startsWith("live-synapse")) return false;
  if (isActive) return true;
  const labelContext = `${node.label ?? ""} ${node.type ?? ""} ${nodeSourceType(node)}`.toLowerCase();
  if (/anchor|seed|schema|source|evidence|root|core/.test(labelContext)) return totalNodes <= 500;
  if ((node.confidence ?? 0) >= 0.92) return totalNodes <= 160;
  return totalNodes <= 24;
}

function ensureNodeBuffers(state: SceneState, nodeCount: number) {
  if (state.nodePoints && state.nodeGeometry && state.nodeCapacity >= nodeCount) {
    state.nodeGeometry.setDrawRange(0, nodeCount);
    return;
  }

  const nextNodeCapacity = nextCapacity(nodeCount, 1024);
  state.nodeCapacity = nextNodeCapacity;
  state.nodePositionArray = expandedFloatBuffer(state.nodePositionArray, nextNodeCapacity * 3);
  state.nodeColorArray = expandedFloatBuffer(state.nodeColorArray, nextNodeCapacity * 3);

  if (!state.nodeGeometry) {
    state.nodeGeometry = new THREE.BufferGeometry();
  }
  state.nodeGeometry.setAttribute("position", new THREE.BufferAttribute(state.nodePositionArray, 3).setUsage(THREE.DynamicDrawUsage));
  state.nodeGeometry.setAttribute("color", new THREE.BufferAttribute(state.nodeColorArray, 3).setUsage(THREE.DynamicDrawUsage));
  state.nodeGeometry.setDrawRange(0, nodeCount);
  state.nodePositionBufferDirty = true;

  if (!state.nodePoints) {
    const pointMaterial = new THREE.PointsMaterial({
      alphaTest: 0.04,
      blending: THREE.AdditiveBlending,
      depthTest: false,
      depthWrite: false,
      map: getNodePointTexture(),
      opacity: 1,
      size: nodeCount > 100_000 ? 0.05 : nodeCount > 25_000 ? 0.066 : nodeCount > 5_000 ? 0.095 : nodeCount > 1_000 ? 0.165 : 0.27,
      sizeAttenuation: true,
      transparent: true,
      vertexColors: true,
    });
    state.nodePoints = new THREE.Points(state.nodeGeometry, pointMaterial);
    state.nodePoints.renderOrder = 2;
    state.nodePoints.userData.kind = "node-points";
    state.group.add(state.nodePoints);
  } else {
    state.nodePoints.geometry = state.nodeGeometry;
    const material = state.nodePoints.material as THREE.PointsMaterial;
    material.alphaTest = 0.04;
    material.blending = THREE.AdditiveBlending;
    material.map = getNodePointTexture();
    material.opacity = 1;
    material.size = nodeCount > 100_000 ? 0.05 : nodeCount > 25_000 ? 0.066 : nodeCount > 5_000 ? 0.095 : nodeCount > 1_000 ? 0.165 : 0.27;
    material.needsUpdate = true;
  }
}

function ensureEdgeBuffers(state: SceneState, vertexCount: number) {
  if (state.edgeLines && state.edgeGeometry && state.edgeCapacity >= vertexCount) {
    state.edgeGeometry.setDrawRange(0, vertexCount);
    return;
  }

  const nextEdgeCapacity = nextCapacity(vertexCount, 4096);
  state.edgeCapacity = nextEdgeCapacity;
  state.edgePositionArray = expandedFloatBuffer(state.edgePositionArray, nextEdgeCapacity * 3);
  state.edgeColorArray = expandedFloatBuffer(state.edgeColorArray, nextEdgeCapacity * 3);

  if (!state.edgeGeometry) {
    state.edgeGeometry = new THREE.BufferGeometry();
  }
  state.edgeGeometry.setAttribute("position", new THREE.BufferAttribute(state.edgePositionArray, 3).setUsage(THREE.DynamicDrawUsage));
  state.edgeGeometry.setAttribute("color", new THREE.BufferAttribute(state.edgeColorArray, 3).setUsage(THREE.DynamicDrawUsage));
  state.edgeGeometry.setDrawRange(0, vertexCount);
  state.edgePositionBufferDirty = true;

  if (!state.edgeLines) {
    const edgeMaterial = new THREE.LineBasicMaterial({
      blending: THREE.AdditiveBlending,
      depthTest: false,
      depthWrite: false,
      opacity: state.edgeOpacity,
      transparent: true,
      vertexColors: true,
    });
    state.edgeLines = new THREE.LineSegments(state.edgeGeometry, edgeMaterial);
    state.edgeLines.renderOrder = 1;
    state.group.add(state.edgeLines);
  } else {
    state.edgeLines.geometry = state.edgeGeometry;
    const material = state.edgeLines.material as THREE.LineBasicMaterial;
    material.opacity = state.edgeOpacity;
    material.needsUpdate = true;
  }
}

function ensureHaloMesh(state: SceneState, count: number) {
  if (count <= 0) {
    if (state.haloMesh) state.haloMesh.count = 0;
    return;
  }
  if (state.haloMesh && state.haloCapacity >= count) {
    state.haloMesh.count = count;
    return;
  }

  if (state.haloMesh) {
    state.group.remove(state.haloMesh);
    disposeObject(state.haloMesh);
  }
  state.haloCapacity = nextCapacity(count, 64);
  const geometry = new THREE.TorusGeometry(1, 0.0075, 8, 40);
  const material = new THREE.MeshBasicMaterial({
    blending: THREE.AdditiveBlending,
    color: NEON_ORANGE,
    depthTest: false,
    depthWrite: false,
    opacity: 0.05,
    transparent: true,
  });
  state.haloMesh = new THREE.InstancedMesh(geometry, material, state.haloCapacity);
  state.haloMesh.instanceMatrix.setUsage(THREE.DynamicDrawUsage);
  state.haloMesh.count = count;
  state.haloMesh.renderOrder = 4;
  state.group.add(state.haloMesh);
}

function ensurePulseMesh(state: SceneState, count: number) {
  if (count <= 0) {
    if (state.pulseMesh) state.pulseMesh.count = 0;
    return;
  }
  if (state.pulseMesh && state.pulseCapacity >= count) {
    state.pulseMesh.count = count;
    return;
  }

  if (state.pulseMesh) {
    state.group.remove(state.pulseMesh);
    disposeObject(state.pulseMesh);
  }
  state.pulseCapacity = nextCapacity(count, 128);
  const geometry = new THREE.SphereGeometry(1, 8, 8);
  const material = new THREE.MeshBasicMaterial({
    blending: THREE.AdditiveBlending,
    color: 0xff2fa0,
    depthTest: false,
    depthWrite: false,
    opacity: 0.95,
    transparent: true,
  });
  state.pulseMesh = new THREE.InstancedMesh(geometry, material, state.pulseCapacity);
  state.pulseMesh.instanceMatrix.setUsage(THREE.DynamicDrawUsage);
  state.pulseMesh.count = count;
  state.pulseMesh.renderOrder = 5;
  state.group.add(state.pulseMesh);
}

function ensureShellMesh(state: SceneState, count: number) {
  if (count <= 0) {
    if (state.shellMesh) state.shellMesh.count = 0;
    return;
  }
  if (state.shellMesh && state.shellCapacity >= count) {
    state.shellMesh.count = count;
    return;
  }

  if (state.shellMesh) {
    state.group.remove(state.shellMesh);
    disposeObject(state.shellMesh);
  }
  state.shellCapacity = nextCapacity(count, 64);
  const geometry = new THREE.SphereGeometry(1, 10, 10);
  const material = new THREE.MeshBasicMaterial({
    blending: THREE.AdditiveBlending,
    color: 0x4ea3ff,
    depthWrite: false,
    opacity: 0.105,
    transparent: true,
  });
  state.shellMesh = new THREE.InstancedMesh(geometry, material, state.shellCapacity);
  state.shellMesh.instanceMatrix.setUsage(THREE.DynamicDrawUsage);
  state.shellMesh.count = count;
  state.shellMesh.renderOrder = 0;
  state.group.add(state.shellMesh);
}

function findSpawnPositionForNode(nodeId: string, edges: Rag3DEdge[], positions: Map<string, THREE.Vector3>, fallback: THREE.Vector3) {
  for (const edge of edges) {
    if (edge.source === nodeId) {
      const source = positions.get(edge.target);
      if (source) return source.clone();
    }
    if (edge.target === nodeId) {
      const source = positions.get(edge.source);
      if (source) return source.clone();
    }
  }
  return fallback.clone().multiplyScalar(0.54);
}

function syncGraph(
  state: SceneState,
  graph: Rag3DGraph | null,
  activeNodeIds: Set<string>,
  activeEdgeKeys: Set<string>,
  newNodeIds: Set<string>,
  requestedVisualState?: Rag3DVisualState,
  showLabels = true,
) {
  const nextVisualState = resolveVisualState(requestedVisualState, graph, activeNodeIds, activeEdgeKeys, newNodeIds);
  if (state.visualState !== nextVisualState) {
    state.frozenPositionSnapshot = null;
    state.coordinateMutationWarned = false;
  }
  state.visualState = nextVisualState;
  state.activeNodeIds = new Set(activeNodeIds);
  state.activeEdgeKeys = new Set(activeEdgeKeys);
  state.newNodeIds = new Set(newNodeIds);
  state.graphNodes = graph?.nodes ?? [];
  state.graphEdges = graph?.edges ?? [];
  state.scaleChunks = (graph?.scale_chunks ?? []).filter((chunk) => chunk?.is_semantic_node !== true);

  if (!graph?.nodes?.length) {
    state.nodePoints?.geometry.setDrawRange(0, 0);
    state.edgeLines?.geometry.setDrawRange(0, 0);
    ensureShellMesh(state, state.scaleChunks.length);
    if (state.haloMesh) state.haloMesh.count = 0;
    if (state.pulseMesh) state.pulseMesh.count = 0;
    removeDynamicObjects(state);
    return;
  }

  const elapsed = (performance.now() - state.startedAt) / 1000;
  const activation = computeActivationMaps(graph.nodes, graph.edges, activeNodeIds, activeEdgeKeys);
  state.activationHops = activation.hops;
  state.activationEdgeIntensity = activation.edgeIntensity;
  const organicLayout = spreadPositions(graph.nodes, graph.edges, activeNodeIds);
  state.layoutDiagnostics = {
    ...organicLayout.diagnostics,
    hop1_count: Array.from(activation.hops.values()).filter((hop) => hop === 1).length,
    hop2_count: Array.from(activation.hops.values()).filter((hop) => hop === 2).length,
    hop3_count: Array.from(activation.hops.values()).filter((hop) => hop === 3).length,
    visual_state: nextVisualState,
  };
  const targets = state.preserveSourceCoordinates ? sourceCoordinatePositions(graph.nodes) : organicLayout.positions;
  scheduleWebGpuLayout(state, graph, activeNodeIds);
  const nextKnownNodeIds = new Set<string>();
  const nextNodeIndexById = new Map<string, number>();
  const stillPresent = new Set<string>();
  const targetMap = new Map<string, THREE.Vector3>();

  const freshlyAdded: string[] = [];
  graph.nodes.forEach((node, index) => {
    const target = targets[index];
    nextKnownNodeIds.add(node.id);
    nextNodeIndexById.set(node.id, index);
    targetMap.set(node.id, target);
    stillPresent.add(node.id);

    if (!state.nodePositionById.has(node.id)) {
      const spawn = coordinateAnimationAllowed(nextVisualState)
        ? findSpawnPositionForNode(node.id, graph.edges, state.nodePositionById, target)
        : target.clone();
      state.nodePositionById.set(node.id, spawn);
      freshlyAdded.push(node.id);
    }
  });

  // Only treat new ids as flashing "arrivals" when a modest number appear. The
  // first population, or a bulk re-sample where most ids changed, is a reload —
  // flashing the whole field orange would be noise, so we backdate those.
  const bulkReload = state.knownNodeIds.size === 0
    || freshlyAdded.length > Math.max(48, graph.nodes.length * 0.4);
  freshlyAdded.forEach((id) => state.nodeBornAt.set(id, bulkReload ? -999 : elapsed));

  // Zoom-in pulse on real arrival: brief zoom-in (5%), then ease back over 3s.
  // Only fires for real incremental arrivals (not bulk reload/first population).
  if (!bulkReload && state.frame >= state.userCameraControlUntilFrame) {
    const realArrivals = freshlyAdded.filter(id => isArrivalId(id));
    const sinceLastPulse = elapsed - state.zoomPulseAt;
    if (realArrivals.length > 0 && sinceLastPulse > 3.5) {
      state.zoomPulseAt = elapsed;
      state.zoomBaseZ = state.camera.position.z;
    }
  }

  for (const id of Array.from(state.nodePositionById.keys())) {
    if (!stillPresent.has(id)) {
      state.nodePositionById.delete(id);
      state.nodeTargetById.delete(id);
      state.nodeBornAt.delete(id);
    }
  }

  state.nodeTargetById = targetMap;
  state.nodeIndexById = nextNodeIndexById;
  state.pointNodes = graph.nodes;
  state.nodePositionBufferDirty = true;
  state.edgePositionBufferDirty = true;
  state.frozenPositionSnapshot = null;
  state.coordinateMutationWarned = false;

  // Exclude transient arrival nodes from the camera fit so spawning/expiring
  // outer nodes never jitter or re-zoom the view.
  const fitTargets = targets.filter((_, index) => !isArrivalId(graph.nodes[index].id));
  const fitDistance = fitDistanceForPositions(fitTargets.length ? fitTargets : targets, state.camera, !state.preserveSourceCoordinates) * state.fitScale;
  // Ignore small node-count wobble (live arrivals spawning/expiring) so the
  // camera doesn't re-fit and jitter every couple of seconds.
  const graphExpanded = graph.nodes.length > state.lastGraphNodeCount + 40;
  const userControllingCamera = state.frame < state.userCameraControlUntilFrame;
  if (!userControllingCamera && (graphExpanded || fitDistance > state.lastFitDistance || fitDistance > state.camera.position.z)) {
    state.camera.position.z = Math.max(state.camera.position.z, fitDistance);
    state.lastFitDistance = fitDistance;
  } else if (!userControllingCamera && state.camera.position.z > fitDistance * 1.32) {
    state.camera.position.z = fitDistance * 1.12;
    state.lastFitDistance = fitDistance;
  }
  state.lastGraphNodeCount = graph.nodes.length;
  if (!state.preserveSourceCoordinates) {
    clampCameraZ(state.camera, graph.nodes.length);
  }

  const traversalPairs = new Set<string>();
  for (let index = 0; index < (graph.traversal_path?.length ?? 0) - 1; index += 1) {
    traversalPairs.add(`${graph.traversal_path?.[index]}:${graph.traversal_path?.[index + 1]}`);
  }

  const maxEdges = graph.nodes.length > 100_000 ? 80_000 : graph.nodes.length > 25_000 ? 70_000 : graph.nodes.length > 5_000 ? 60_000 : Number.POSITIVE_INFINITY;
  const edgeStride = Number.isFinite(maxEdges) && graph.edges.length > maxEdges ? Math.ceil(graph.edges.length / maxEdges) : 1;
  state.visibleEdges = [];
  for (const [index, edge] of graph.edges.entries()) {
    if (!state.nodeIndexById.has(edge.source) || !state.nodeIndexById.has(edge.target)) continue;
    const explicitActive = edgeIsExplicitlyActive(activeEdgeKeys, edge.source, edge.target);
    const directActive = activeNodeIds.has(edge.source) || activeNodeIds.has(edge.target);
    const hopActive = (state.activationEdgeIntensity.get(edgeKey(edge.source, edge.target)) ?? 0) > 0;
    const traversalActive = traversalPairs.has(`${edge.source}:${edge.target}`);
    if (!explicitActive && !directActive && !hopActive && !traversalActive && index % edgeStride !== 0) continue;
    state.visibleEdges.push({ ...edge, active: explicitActive || directActive || hopActive || traversalActive, index });
  }

  ensureNodeBuffers(state, graph.nodes.length);
  ensureEdgeBuffers(state, state.visibleEdges.length * 4);

  state.haloItems = [];
  ensureHaloMesh(state, state.haloItems.length);

  state.pulseItems = movingPulseAllowed(nextVisualState)
    ? state.visibleEdges
      .filter((edge) => edge.active)
      .slice(0, 980)
      .flatMap((edge) => [0, 1, 2].map((pulse) => ({ source: edge.source, target: edge.target, phase: pulse / 3 })))
    : [];
  ensurePulseMesh(state, state.pulseItems.length);
  state.edgePulseCount = state.pulseItems.length;
  ensureShellMesh(state, state.scaleChunks.length);

  removeDynamicObjects(state);
  if (showLabels) {
    const labelScale = graph.nodes.length > 18 ? 0.72 : graph.nodes.length > 12 ? 0.84 : 1;
    graph.nodes.forEach((node) => {
      const isActive = activeNodeIds.has(node.id);
      if (!shouldShowLabel(node, graph.nodes.length, isActive)) return;
      const position = state.nodePositionById.get(node.id);
      if (!position) return;
      const sprite = labelSprite(node.label, labelScale);
      sprite.position.set(position.x + 0.32, position.y + 0.18, position.z);
      addDynamicObject(state, sprite);
    });
  }

  state.knownNodeIds = nextKnownNodeIds;
}

function graphLayoutSignature(graph: Rag3DGraph, activeNodeIds: Set<string>) {
  const first = graph.nodes[0]?.id ?? "";
  const last = graph.nodes[graph.nodes.length - 1]?.id ?? "";
  const active = Array.from(activeNodeIds).sort().slice(0, 32).join(",");
  return `${graph.nodes.length}:${graph.edges.length}:${first}:${last}:${active}`;
}

function scheduleWebGpuLayout(state: SceneState, graph: Rag3DGraph, activeNodeIds: Set<string>) {
  if (state.preserveSourceCoordinates || typeof navigator === "undefined") return;
  const signature = graphLayoutSignature(graph, activeNodeIds);
  if (signature === state.layoutSignature) return;
  state.layoutSignature = signature;
  const serial = state.layoutRequestSerial + 1;
  state.layoutRequestSerial = serial;
  const graphNodes = graph.nodes.map((node) => ({ ...node }));
  const graphEdges = graph.edges.map((edge) => ({ ...edge }));
  const activeSnapshot = new Set(activeNodeIds);
  computeWebGpuGraphLayout(graphNodes, graphEdges, activeSnapshot)
    .then((result) => {
      if (!result || sceneStateIsStale(state, serial, signature)) return;
      const targetMap = new Map<string, THREE.Vector3>();
      graphNodes.forEach((node, index) => {
        const position = result.positions[index];
        if (!position) return;
        targetMap.set(node.id, new THREE.Vector3(position[0], position[1], position[2]));
      });
      if (targetMap.size !== graphNodes.length) return;
      state.nodeTargetById = targetMap;
      state.layoutDiagnostics = {
        ...state.layoutDiagnostics,
        ...result.diagnostics,
      };
      state.nodePositionBufferDirty = true;
      state.edgePositionBufferDirty = true;
      const fitDistance = fitDistanceForPositions(Array.from(targetMap.values()), state.camera, true) * state.fitScale;
      if (state.frame >= state.userCameraControlUntilFrame && fitDistance > state.camera.position.z) {
        state.camera.position.z = fitDistance;
        state.lastFitDistance = fitDistance;
      }
    })
    .catch((error) => {
      state.layoutDiagnostics = {
        ...state.layoutDiagnostics,
        layout_accelerator: "cpu",
        webgpu_disabled_reason: error instanceof Error ? error.name || "layout_failed" : "layout_failed",
      };
      if (process.env.NODE_ENV !== "production") {
        console.warn("ATANOR WebGPU layout unavailable; using CPU layout", error);
      }
    });
}

function sceneStateIsStale(state: SceneState, serial: number, signature: string) {
  return state.layoutRequestSerial !== serial || state.layoutSignature !== signature || state.preserveSourceCoordinates;
}

function nodeSignalStrength(state: SceneState, node: Rag3DNode, elapsed: number) {
  const active = state.activeNodeIds.has(node.id);
  const hop = state.activationHops.get(node.id);
  const bornAt = state.nodeBornAt.get(node.id);
  const newAge = typeof bornAt === "number" ? elapsed - bornAt : Number.POSITIVE_INFINITY;
  // Injected "arrival" nodes are highlighted the entire (short) time they exist
  // — they're removed after a few seconds upstream, so this IS the "glows for a
  // while" window. Keyed by id so it never depends on frame-timing math.
  if (isArrivalId(node.id) && state.visualState !== "low_memory_viewer") {
    // Flash bright on arrival, then settle to a faint orange node that STAYS on
    // the surface (it doesn't vanish) until the upstream cap rotates it out.
    const arrivalBornAt = state.nodeBornAt.get(node.id);
    const arrivalAge = typeof arrivalBornAt === "number" ? elapsed - arrivalBornAt : 0;
    const decay = THREE.MathUtils.clamp(1 - arrivalAge / NEW_NODE_GLOW_SECONDS, 0, 1);
    const twinkle = 0.6 + 0.4 * Math.abs(Math.sin(elapsed * 7.5 + hash01(node.id, 53) * Math.PI * 2));
    return THREE.MathUtils.clamp(0.16 + decay * 0.84 * twinkle, 0, 1);
  }
  // Arrivals flash even when the overall graph has "settled" (idle) — a new node
  // landing on a calm field is exactly when the flash matters most.
  const fresh = state.visualState !== "low_memory_viewer" && (state.newNodeIds.has(node.id) || newAge < NEW_NODE_GLOW_SECONDS);
  // A brand-new node twinkles bright orange for a few seconds so it is easy to
  // spot, then decays back into the field — this wins over the active/hop glow
  // below so arrivals always read as arrivals.
  if (fresh) {
    const decay = THREE.MathUtils.clamp(1 - newAge / NEW_NODE_GLOW_SECONDS, 0, 1);
    const twinkle = 0.58 + 0.42 * Math.abs(Math.sin(elapsed * 7.5 + hash01(node.id, 53) * Math.PI * 2));
    return THREE.MathUtils.clamp(0.35 + decay * twinkle, 0, 1);
  }
  if (state.visualState === "low_memory_viewer") return active ? 0.42 : 0;
  if (active) {
    const amplitude = state.visualState === "completed" ? 0.012 : 0.12;
    const base = state.visualState === "completed" ? 0.26 : 0.58;
    return base + Math.sin(elapsed * 10 + hash01(node.id, 31) * Math.PI * 2) * amplitude;
  }
  if (hop !== undefined && hop <= 3) {
    const base = Math.exp(-hop * 1.42);
    const pulseAmplitude = state.visualState === "completed" ? 0.004 : 0.04;
    const pulseBase = state.visualState === "completed" ? 0.08 : 0.28;
    return THREE.MathUtils.clamp(base * (pulseBase + Math.sin(elapsed * 8 + hash01(node.id, 37) * Math.PI * 2) * pulseAmplitude), 0.004, 0.16);
  }
  return 0;
}

function edgeSignalStrength(state: SceneState, edge: VisibleEdge, elapsed: number) {
  if (!edge.active) return 0;
  const hopIntensity = state.activationEdgeIntensity.get(edgeKey(edge.source, edge.target))
    ?? state.activationEdgeIntensity.get(edgeKey(edge.target, edge.source))
    ?? 0;
  const phase = hash01(edge.source + edge.target, 19) * Math.PI * 2;
  const pulse = state.visualState === "completed"
    ? 0.34 + Math.sin(elapsed * 8 + phase) * 0.045
    : 0.52 + Math.sin(elapsed * 10 + phase) * 0.12;
  const explicitBoost = edgeIsExplicitlyActive(state.activeEdgeKeys, edge.source, edge.target) ? pulse : 0;
  return THREE.MathUtils.clamp(Math.max(hopIntensity * pulse, explicitBoost), 0, 0.82);
}

function assertCompletedCoordinatesStable(state: SceneState) {
  if (state.visualState !== "completed" || !state.nodePositionArray) return;
  const length = state.graphNodes.length * 3;
  const current = state.nodePositionArray.subarray(0, length);
  if (!state.frozenPositionSnapshot || state.frozenPositionSnapshot.length !== length) {
    state.frozenPositionSnapshot = new Float32Array(current);
    return;
  }
  if (state.coordinateMutationWarned) return;
  for (let index = 0; index < length; index += 1) {
    if (Math.abs(current[index] - state.frozenPositionSnapshot[index]) > 0.00001) {
      console.warn("Unexpected coordinate mutation in completed graph state");
      state.coordinateMutationWarned = true;
      state.frozenPositionSnapshot = new Float32Array(current);
      return;
    }
  }
}

function updateNodeBuffers(state: SceneState, elapsed: number) {
  if (!state.nodePositionArray || !state.nodeColorArray || !state.nodeGeometry) return;
  const positionAttribute = state.nodeGeometry.getAttribute("position") as THREE.BufferAttribute;
  const colorAttribute = state.nodeGeometry.getAttribute("color") as THREE.BufferAttribute;
  const allowPositionMutation = coordinateAnimationAllowed(state.visualState);
  let positionBufferChanged = state.nodePositionBufferDirty;

  state.graphNodes.forEach((node, index) => {
    const position = state.nodePositionById.get(node.id) ?? new THREE.Vector3();
    const target = state.nodeTargetById.get(node.id) ?? position;
    const bornAt = state.nodeBornAt.get(node.id);
    const age = typeof bornAt === "number" ? elapsed - bornAt : 99;
    if (allowPositionMutation) {
      const beforeX = position.x;
      const beforeY = position.y;
      const beforeZ = position.z;
      const expansionRate = age < NEW_NODE_ANIMATION_SECONDS ? 0.115 : 0.045;
      position.lerp(target, expansionRate);
      if (Math.abs(position.x - beforeX) > 0.00001 || Math.abs(position.y - beforeY) > 0.00001 || Math.abs(position.z - beforeZ) > 0.00001) {
        positionBufferChanged = true;
      }
    }

    state.nodePositionArray![index * 3] = position.x;
    state.nodePositionArray![index * 3 + 1] = position.y;
    state.nodePositionArray![index * 3 + 2] = position.z;

    const signal = nodeSignalStrength(state, node, elapsed);
    const isArrival = isArrivalId(node.id);
    const depthCue = THREE.MathUtils.clamp(0.5 + position.z / Math.max(10, state.camera.position.z * 0.28), 0.18, 1);
    if (isArrival) {
      // Flash orange, then FREEZE to a normal white node and stay that way.
      const bornAt = state.nodeBornAt.get(node.id);
      const age = typeof bornAt === "number" ? elapsed - bornAt : 0;
      const freeze = THREE.MathUtils.clamp((age - NEW_NODE_GLOW_SECONDS) / NEW_NODE_FREEZE_SECONDS, 0, 1);
      tempColor.copy(arrivalGlowColor).lerp(localMemoryColor, freeze);
      const freshBright = 1.15 + signal * 0.5;
      const normalBright = 0.66 + depthCue * 0.42;
      tempColor.multiplyScalar(THREE.MathUtils.lerp(freshBright, normalBright, freeze));
    } else {
      tempColor.copy(nodeBaseColor(node)).lerp(neonOrangeColor, signal);
      tempColor.multiplyScalar(0.98 + depthCue * 0.5);
      tempColor.lerp(depthWhiteColor, depthCue * 0.12);
    }
    // Activation pop: a firing node momentarily turns deep pink, then decays.
    const activation = state.nodeActivation ? state.nodeActivation[index] : 0;
    if (activation > 0.01) {
      tempColor.lerp(activationPinkColor, Math.min(1, activation * 1.3));
      tempColor.multiplyScalar(1 + activation * 2.6);
    }
    state.nodeColorArray![index * 3] = tempColor.r;
    state.nodeColorArray![index * 3 + 1] = tempColor.g;
    state.nodeColorArray![index * 3 + 2] = tempColor.b;
  });

  if (positionBufferChanged) {
    positionAttribute.needsUpdate = true;
    state.nodeGeometry.computeBoundingSphere();
    state.nodePositionBufferDirty = false;
  }
  colorAttribute.needsUpdate = true;
  assertCompletedCoordinatesStable(state);
}

function updateEdgeBuffers(state: SceneState, elapsed: number) {
  if (!state.edgePositionArray || !state.edgeColorArray || !state.edgeGeometry) return;
  const positionAttribute = state.edgeGeometry.getAttribute("position") as THREE.BufferAttribute;
  const colorAttribute = state.edgeGeometry.getAttribute("color") as THREE.BufferAttribute;
  let positionBufferChanged = state.edgePositionBufferDirty || coordinateAnimationAllowed(state.visualState);

  state.visibleEdges.forEach((edge, edgeIndex) => {
    const source = state.nodePositionById.get(edge.source);
    const target = state.nodePositionById.get(edge.target);
    if (!source || !target) return;

    // Fresh-edge "growing tendril": when one endpoint is a newly-arrived node,
    // draw the line as if it sprouts from the older (existing) node and reaches
    // out to the new one, flashing orange while it is young.
    let sx = source.x, sy = source.y, sz = source.z;
    let tx = target.x, ty = target.y, tz = target.z;
    let freshGlow = 0;
    if (state.visualState !== "low_memory_viewer") {
      const sourceArrival = isArrivalId(edge.source);
      const targetArrival = isArrivalId(edge.target);
      const sourceBorn = state.nodeBornAt.get(edge.source);
      const targetBorn = state.nodeBornAt.get(edge.target);
      const sourceAge = typeof sourceBorn === "number" ? elapsed - sourceBorn : Number.POSITIVE_INFINITY;
      const targetAge = typeof targetBorn === "number" ? elapsed - targetBorn : Number.POSITIVE_INFINITY;
      // An edge touching an arrival node is always a fresh tendril (keyed by id);
      // otherwise fall back to the age window for ordinary new nodes.
      const newEndpointAge = targetArrival ? targetAge : sourceArrival ? sourceAge : Math.min(sourceAge, targetAge);
      const isArrivalEdge = sourceArrival || targetArrival;
      if (state.showActivity && (isArrivalEdge || newEndpointAge < NEW_NODE_GLOW_SECONDS)) {
        // While any tendril is still growing/glowing we must keep re-uploading
        // edge positions even on an otherwise-static (idle) graph.
        positionBufferChanged = true;
        const grow = THREE.MathUtils.clamp(newEndpointAge / NEW_EDGE_GROW_SECONDS, 0, 1);
        if (grow < 1) {
          // For an arrival edge the new node stays put and the OTHER end grows out
          // from it (tendrils originate AT the new node and reach its neighbours).
          if (sourceArrival) {
            tx = source.x + (target.x - source.x) * grow;
            ty = source.y + (target.y - source.y) * grow;
            tz = source.z + (target.z - source.z) * grow;
          } else if (targetArrival) {
            sx = target.x + (source.x - target.x) * grow;
            sy = target.y + (source.y - target.y) * grow;
            sz = target.z + (source.z - target.z) * grow;
          } else if (sourceAge <= targetAge) {
            sx = target.x + (source.x - target.x) * grow;
            sy = target.y + (source.y - target.y) * grow;
            sz = target.z + (source.z - target.z) * grow;
          } else {
            tx = source.x + (target.x - source.x) * grow;
            ty = source.y + (target.y - source.y) * grow;
            tz = source.z + (target.z - source.z) * grow;
          }
        }
        const twinkle = 0.64 + 0.36 * Math.abs(Math.sin(elapsed * 8 + hash01(edge.source + edge.target, 23) * Math.PI * 2));
        const decayEdge = THREE.MathUtils.clamp(1 - newEndpointAge / NEW_NODE_GLOW_SECONDS, 0, 1);
        // Arrival tendril stays as a faint orange link after the flash settles.
        freshGlow = isArrivalEdge ? (0.24 + 0.76 * decayEdge) * twinkle : decayEdge * twinkle;
      }
    }

    // Two sub-segments (A→mid, mid→B) so the sky-blue activation can be U-shaped:
    // bright at both ends (near the nodes), dimmer in the middle.
    const mx = (sx + tx) * 0.5, my = (sy + ty) * 0.5, mz = (sz + tz) * 0.5;
    const vertexIndex = edgeIndex * 12;
    const p = state.edgePositionArray!;
    p[vertexIndex] = sx; p[vertexIndex + 1] = sy; p[vertexIndex + 2] = sz;
    p[vertexIndex + 3] = mx; p[vertexIndex + 4] = my; p[vertexIndex + 5] = mz;
    p[vertexIndex + 6] = mx; p[vertexIndex + 7] = my; p[vertexIndex + 8] = mz;
    p[vertexIndex + 9] = tx; p[vertexIndex + 10] = ty; p[vertexIndex + 11] = tz;

    const signal = edgeSignalStrength(state, edge, elapsed);
    const weight = edgeWeight(edge);
    if (state.showActivity && (isArrivalId(edge.source) || isArrivalId(edge.target))) {
      // Orange tendril on arrival, then FREEZE to a normal white edge and stay.
      const arrivalBorn = isArrivalId(edge.source)
        ? state.nodeBornAt.get(edge.source)
        : state.nodeBornAt.get(edge.target);
      const arrivalAge = typeof arrivalBorn === "number" ? elapsed - arrivalBorn : 0;
      const freeze = THREE.MathUtils.clamp((arrivalAge - NEW_NODE_GLOW_SECONDS) / NEW_NODE_FREEZE_SECONDS, 0, 1);
      // Stay vivid orange: only fade toward the base edge near the very end, and
      // keep a low base-edge mix so the colour reads saturated, not washed.
      // Deepened: brighter peak + slower wash so the active tendril reads dense.
      const lit = THREE.MathUtils.lerp(3.7 + freshGlow * 2.3, 1.0, freeze);
      tempColor.copy(arrivalGlowColor).lerp(baseEdgeColor, freeze * 0.5).multiplyScalar(lit);
    } else {
      const base = edge.active || weight >= 0.82
        ? nearActiveEdgeColor
        : weight < 0.34
          ? weakEdgeColor
          : baseEdgeColor;
      tempColor.copy(base);
      if (weight > 0.62) {
        tempColor.lerp(strongEdgeColor, THREE.MathUtils.clamp((weight - 0.62) * 0.48, 0, 0.28));
      }
      // NO orange tint on activation: an active established edge flashes SKY-BLUE
      // (added below). Orange is reserved for NEW-node branch edges (arrival branch).
      const edgeDepthCue = THREE.MathUtils.clamp(0.5 + ((sz + tz) * 0.5) / Math.max(10, state.camera.position.z * 0.28), 0.2, 1);
      // Clear brightness CONTRAST by activation: a resting edge sits dim (~50%),
      // an active one rises so active lines visibly stand out.
      const activeness = Math.min(1, Math.max(signal, edge.active ? 0.55 : 0));
      // Full graph stays visible; active edges go overbright so the bloom pass
      // (post-processing) makes ONLY the active ones glow/bleed at scale.
      tempColor.multiplyScalar((0.5 + 2.5 * activeness) * (0.92 + edgeDepthCue * 0.3));
      tempColor.lerp(depthWhiteColor, edgeDepthCue * 0.03);
      if (freshGlow > 0) tempColor.multiplyScalar(1 + freshGlow * 3.1);
    }
    // Sky-blue activation gradient: bright at each end by that node's activation,
    // dimmer at the midpoint — so the line glows toward the nodes (synapse look).
    const act = state.nodeActivation;
    let sa = 0, ta = 0;
    if (act) {
      const si = state.nodeIndexById.get(edge.source);
      const ti = state.nodeIndexById.get(edge.target);
      if (si !== undefined) sa = act[si];
      if (ti !== undefined) ta = act[ti];
    }
    const K = 7.5; // deep, saturated, BRIGHT sky-blue when active
    const baseR = tempColor.r, baseG = tempColor.g, baseB = tempColor.b;
    // Flash sky-blue whenever the edge is active: drive by the stronger of node
    // activation and the edge's own signal, so every activation reads sky-blue.
    const sFlash = Math.min(1, Math.max(sa, signal));
    const tFlash = Math.min(1, Math.max(ta, signal));
    const midAct = (sFlash + tFlash) * 0.5 * 0.55; // fuller middle, still U-shaped
    const ca = state.edgeColorArray!;
    // A (near source node)
    ca[vertexIndex] = baseR + skyBlueColor.r * sFlash * K;
    ca[vertexIndex + 1] = baseG + skyBlueColor.g * sFlash * K;
    ca[vertexIndex + 2] = baseB + skyBlueColor.b * sFlash * K;
    // mid (duplicated vertex for the two sub-segments)
    const mR = baseR + skyBlueColor.r * midAct * K;
    const mG = baseG + skyBlueColor.g * midAct * K;
    const mB = baseB + skyBlueColor.b * midAct * K;
    ca[vertexIndex + 3] = mR; ca[vertexIndex + 4] = mG; ca[vertexIndex + 5] = mB;
    ca[vertexIndex + 6] = mR; ca[vertexIndex + 7] = mG; ca[vertexIndex + 8] = mB;
    // B (near target node)
    ca[vertexIndex + 9] = baseR + skyBlueColor.r * tFlash * K;
    ca[vertexIndex + 10] = baseG + skyBlueColor.g * tFlash * K;
    ca[vertexIndex + 11] = baseB + skyBlueColor.b * tFlash * K;
  });

  if (positionBufferChanged) {
    positionAttribute.needsUpdate = true;
    state.edgePositionBufferDirty = false;
  }
  colorAttribute.needsUpdate = true;
}

function updateHaloMesh(state: SceneState, elapsed: number) {
  if (!state.haloMesh) return;
  state.haloMesh.count = state.haloItems.length;
  state.haloItems.forEach((halo, index) => {
    const position = state.nodePositionById.get(halo.id) ?? halo.position;
    const age = elapsed - halo.bornAt;
    const t = THREE.MathUtils.clamp(age / NEW_NODE_ANIMATION_SECONDS, 0, 1);
    const signal = halo.newNode
      ? 1 - t
      : 0.55 + Math.sin(elapsed * 10 + hash01(halo.id, 43) * Math.PI * 2) * 0.18;
    const ringScale = halo.scale * (halo.newNode ? THREE.MathUtils.lerp(0.76, 0.18, t) : THREE.MathUtils.lerp(0.28, 0.36, signal));
    tempScale.setScalar(Math.max(0.001, ringScale));
    tempMatrix.compose(position, tempRingQuaternion, tempScale);
    state.haloMesh!.setMatrixAt(index, tempMatrix);
  });
  const material = state.haloMesh.material as THREE.MeshBasicMaterial;
  material.opacity = state.haloItems.some((halo) => halo.newNode) ? 0.045 : 0.015;
  material.needsUpdate = true;
  state.haloMesh.instanceMatrix.needsUpdate = true;
}

function updatePulseMesh(state: SceneState, elapsed: number) {
  if (!state.pulseMesh) return;
  if (!state.showActivity || !movingPulseAllowed(state.visualState)) {
    state.pulseMesh.count = 0;
    return;
  }
  state.pulseMesh.count = state.pulseItems.length;
  state.pulseItems.forEach((pulse, index) => {
    const source = state.nodePositionById.get(pulse.source);
    const target = state.nodePositionById.get(pulse.target);
    if (!source || !target) return;
    const t = (elapsed * 3.1 + pulse.phase) % 1;
    tempPosition.copy(source).lerp(target, t);
    // Fat travelling pulse: the line visibly THICKENS where the signal passes.
    tempScale.setScalar(0.045 + Math.sin(t * Math.PI) * 0.11);
    tempMatrix.compose(tempPosition, tempQuaternion, tempScale);
    state.pulseMesh!.setMatrixAt(index, tempMatrix);
  });
  state.pulseMesh.instanceMatrix.needsUpdate = true;
}

function chunkMidpoint(value: number[] | undefined, fallback: number) {
  if (!Array.isArray(value) || value.length < 2) return fallback;
  return (Number(value[0]) + Number(value[1])) / 2;
}

function updateShellMesh(state: SceneState, elapsed: number) {
  if (!state.shellMesh) return;
  const chunks = state.scaleChunks.filter((chunk) => chunk?.is_semantic_node !== true).slice(0, MAX_SHELL_RENDER_CHUNKS);
  const cameraZ = state.camera.position.z;
  const shellVisibility = THREE.MathUtils.clamp((cameraZ - 8.0) / 22.0, 0, 1);
  if (shellVisibility <= 0.015) {
    state.shellMesh.count = 0;
    return;
  }
  state.shellMesh.count = chunks.length;
  chunks.forEach((chunk, index) => {
    const radiusRange = Array.isArray(chunk.radius_range) ? chunk.radius_range : [0.64, 0.78];
    const normalizedRadius = (Number(radiusRange[0]) + Number(radiusRange[1])) / 2;
    const explicitX = Number((chunk as { x?: unknown }).x);
    const explicitY = Number((chunk as { y?: unknown }).y);
    const explicitZ = Number((chunk as { z?: unknown }).z);
    const hasExplicitCenter = Number.isFinite(explicitX) && Number.isFinite(explicitY) && Number.isFinite(explicitZ);
    const shellRadius = 4.2 + normalizedRadius * 5.8 + (1 - shellVisibility) * 0.65;
    const density = THREE.MathUtils.clamp(Number(chunk.density ?? 0.45), 0.12, 1);
    const shimmer = 0.82 + Math.sin(elapsed * 0.7 + index * 1.37) * 0.06;
    if (hasExplicitCenter) {
      tempPosition.set(explicitX, explicitY, explicitZ);
      if (tempPosition.lengthSq() < 0.0001) {
        tempPosition.set(0, 1, 0);
      }
      tempPosition.normalize().multiplyScalar(shellRadius);
    } else {
      const theta = THREE.MathUtils.degToRad(chunkMidpoint(chunk.theta_range, index * 37) % 360);
      const phi = THREE.MathUtils.degToRad(THREE.MathUtils.clamp(chunkMidpoint(chunk.phi_range, 72), 3, 177));
      tempPosition.set(
        Math.sin(phi) * Math.cos(theta) * shellRadius,
        Math.cos(phi) * shellRadius,
        Math.sin(phi) * Math.sin(theta) * shellRadius,
      );
    }
    tempScale.setScalar((0.042 + density * 0.145) * shimmer);
    tempMatrix.compose(tempPosition, tempQuaternion, tempScale);
    state.shellMesh!.setMatrixAt(index, tempMatrix);
  });
  const material = state.shellMesh.material as THREE.MeshBasicMaterial;
  material.opacity = chunks.length ? 0.095 * shellVisibility : 0;
  material.needsUpdate = true;
  state.shellMesh.instanceMatrix.needsUpdate = true;
}

function ensureSynapseBuffers(state: SceneState, segmentCount: number) {
  const vertexCount = Math.max(1, segmentCount) * 2;
  if (state.synapseLines && state.synapseGeometry && state.synapseCapacity >= vertexCount) {
    state.synapseGeometry.setDrawRange(0, segmentCount * 2);
    return;
  }
  const nextCap = nextCapacity(vertexCount, 1024);
  state.synapseCapacity = nextCap;
  state.synapsePosArray = expandedFloatBuffer(state.synapsePosArray, nextCap * 3);
  state.synapseColorArray = expandedFloatBuffer(state.synapseColorArray, nextCap * 3);
  if (!state.synapseGeometry) state.synapseGeometry = new THREE.BufferGeometry();
  state.synapseGeometry.setAttribute("position", new THREE.BufferAttribute(state.synapsePosArray, 3).setUsage(THREE.DynamicDrawUsage));
  state.synapseGeometry.setAttribute("color", new THREE.BufferAttribute(state.synapseColorArray, 3).setUsage(THREE.DynamicDrawUsage));
  state.synapseGeometry.setDrawRange(0, segmentCount * 2);
  if (!state.synapseLines) {
    const material = new THREE.LineBasicMaterial({
      blending: THREE.AdditiveBlending,
      depthTest: false,
      depthWrite: false,
      opacity: 0.68,
      transparent: true,
      vertexColors: true,
    });
    state.synapseLines = new THREE.LineSegments(state.synapseGeometry, material);
    state.synapseLines.renderOrder = 3;
    state.synapseLines.frustumCulled = false;
    state.group.add(state.synapseLines);
  } else {
    state.synapseLines.geometry = state.synapseGeometry;
  }
}

// Build a short signal PATH: start at a random node, then hop to the nearest of a
// small random candidate set each step, so the path snakes coherently through the
// graph (like a signal travelling a route) rather than one straight chord.
function buildSynapsePath(np: Float32Array, nodeCount: number, hops: number): number[] {
  const path: number[] = [(Math.random() * nodeCount) | 0];
  for (let h = 0; h < hops; h += 1) {
    const cur = path[path.length - 1];
    const cx = np[cur * 3], cy = np[cur * 3 + 1], cz = np[cur * 3 + 2];
    let best = -1;
    let bestD = Infinity;
    for (let s = 0; s < 12; s += 1) {
      const cand = (Math.random() * nodeCount) | 0;
      if (path.includes(cand)) continue;
      const dx = np[cand * 3] - cx, dy = np[cand * 3 + 1] - cy, dz = np[cand * 3 + 2] - cz;
      const d = dx * dx + dy * dy + dz * dz;
      if (d < bestD) { bestD = d; best = cand; }
    }
    if (best < 0) break;
    path.push(best);
  }
  return path;
}

// Node activation "팟팟": random nodes fire (at the real relation-check rate) and
// glow sky-blue, decaying quickly. The node pops, and (in the edge pass) the edges
// touching it brighten at THAT end — light radiates from the firing node into its
// connections. Calmer and more node-anchored than full-graph chord lines.
function updateNodeActivation(state: SceneState, dt: number) {
  const count = state.graphNodes.length;
  if (count <= 0) return;
  if (!state.nodeActivation || state.nodeActivationCapacity < count) {
    const next = new Float32Array(nextCapacity(count, 1024));
    if (state.nodeActivation) next.set(state.nodeActivation.subarray(0, Math.min(state.nodeActivation.length, next.length)));
    state.nodeActivation = next;
    state.nodeActivationCapacity = next.length;
  }
  const act = state.nodeActivation;
  const decay = Math.exp(-Math.min(0.1, dt) / 0.26);
  for (let i = 0; i < count; i += 1) act[i] *= decay;
  const rate = state.synapsesPerSecond;
  if (rate > 0) {
    state.activationFireAccum += rate * Math.min(0.1, dt);
    let toFire = Math.floor(state.activationFireAccum);
    state.activationFireAccum -= toFire;
    for (let i = 0; i < toFire; i += 1) act[(Math.random() * count) | 0] = 1;
  }
}

// (legacy traveling-path synapse layer — kept for reference, no longer rendered)
function updateSynapses(state: SceneState, elapsed: number, dt: number) {
  const nodeCount = state.nodePositionById.size > 0 ? state.graphNodes.length : 0;
  state.synapseItems = state.synapseItems.filter((s) => elapsed - s.born < SYNAPSE_LIFE_SECONDS);
  const rate = state.synapsesPerSecond;
  if (rate > 0 && nodeCount > 4 && state.nodePositionArray) {
    // Each spawned "synapse" is a multi-hop path, so divide the pair-rate down.
    state.synapseSpawnAccum += rate * 0.42 * Math.min(0.1, dt);
    let toSpawn = Math.floor(state.synapseSpawnAccum);
    state.synapseSpawnAccum -= toSpawn;
    toSpawn = Math.min(toSpawn, SYNAPSE_MAX - state.synapseItems.length);
    for (let i = 0; i < toSpawn; i += 1) {
      const hops = 3 + ((Math.random() * 4) | 0); // 3..6 hops => 4..7 nodes
      state.synapseItems.push({ nodes: buildSynapsePath(state.nodePositionArray, nodeCount, hops), born: elapsed });
    }
  }
  const items = state.synapseItems;
  let totalSegments = 0;
  for (let i = 0; i < items.length; i += 1) totalSegments += Math.max(0, items[i].nodes.length - 1);
  ensureSynapseBuffers(state, totalSegments);
  if (!state.synapseLines || !state.synapsePosArray || !state.synapseColorArray || !state.nodePositionArray || !state.synapseGeometry) return;
  const pos = state.synapsePosArray;
  const col = state.synapseColorArray;
  const np = state.nodePositionArray;
  let seg = 0;
  for (let i = 0; i < items.length; i += 1) {
    const s = items[i];
    const t = THREE.MathUtils.clamp((elapsed - s.born) / SYNAPSE_LIFE_SECONDS, 0, 1);
    const envelope = Math.sin(t * Math.PI); // 0 -> 1 -> 0 overall fade
    const segCount = s.nodes.length - 1;
    // A bright pulse travels along the path over its life.
    const head = t * segCount;
    for (let j = 0; j < segCount; j += 1) {
      const a = s.nodes[j] * 3;
      const b = s.nodes[j + 1] * 3;
      const v = seg * 6;
      pos[v] = np[a]; pos[v + 1] = np[a + 1]; pos[v + 2] = np[a + 2];
      pos[v + 3] = np[b]; pos[v + 4] = np[b + 1]; pos[v + 5] = np[b + 2];
      const pulse = Math.max(0, 1 - Math.abs(j + 0.5 - head) * 0.85);
      const bright = (0.32 + 0.68 * pulse) * envelope * 1.05; // softer
      const r = skyBlueColor.r * bright;
      const g = skyBlueColor.g * bright;
      const bch = skyBlueColor.b * bright;
      col[v] = r; col[v + 1] = g; col[v + 2] = bch;
      col[v + 3] = r; col[v + 4] = g; col[v + 5] = bch;
      seg += 1;
    }
  }
  state.synapseGeometry.setDrawRange(0, seg * 2);
  (state.synapseGeometry.getAttribute("position") as THREE.BufferAttribute).needsUpdate = true;
  (state.synapseGeometry.getAttribute("color") as THREE.BufferAttribute).needsUpdate = true;
}

export default function Rag3DScene({
  graph,
  activeEdgeKeys = [],
  activeNodeIds = [],
  newNodeIds = [],
  control,
  preserveSourceCoordinates = false,
  onViewportChange,
  onSelect,
  theme = "light",
  visualState,
  fitScale = 1,
  showLabels = true,
  edgeOpacity = 0.34,
  synapsesPerSecond = 0,
  showActivity = true,
  focusNode = null,
}: Rag3DSceneProps) {
  const hostRef = useRef<HTMLDivElement | null>(null);
  const selectRef = useRef(onSelect);
  const viewportChangeRef = useRef(onViewportChange);
  const sceneStateRef = useRef<SceneState | null>(null);
  const showActivityRef = useRef(showActivity);
  const synapseRateRef = useRef(synapsesPerSecond);
  const activeEdgeRef = useRef(new Set(activeEdgeKeys));
  const activeNodeRef = useRef(new Set(activeNodeIds));
  const newNodeRef = useRef(new Set(newNodeIds));
  const graphRef = useRef<Rag3DGraph | null>(graph);
  const showLabelsRef = useRef(showLabels);
  const edgeOpacityRef = useRef(edgeOpacity);

  useEffect(() => {
    selectRef.current = onSelect;
  }, [onSelect]);

  useEffect(() => {
    viewportChangeRef.current = onViewportChange;
    const state = sceneStateRef.current;
    if (state) state.onViewportChange = onViewportChange;
  }, [onViewportChange]);

  useEffect(() => {
    graphRef.current = graph;
    const state = sceneStateRef.current;
    if (state) syncGraph(state, graph, activeNodeRef.current, activeEdgeRef.current, newNodeRef.current, visualState, showLabelsRef.current);
  }, [graph, visualState]);

  useEffect(() => {
    showLabelsRef.current = showLabels;
    const state = sceneStateRef.current;
    if (state) syncGraph(state, graphRef.current, activeNodeRef.current, activeEdgeRef.current, newNodeRef.current, visualState, showLabels);
  }, [showLabels, visualState]);

  useEffect(() => {
    edgeOpacityRef.current = edgeOpacity;
    const state = sceneStateRef.current;
    if (!state) return;
    state.edgeOpacity = THREE.MathUtils.clamp(edgeOpacity, 0.04, 0.86);
    if (state.edgeLines) {
      const material = state.edgeLines.material as THREE.LineBasicMaterial;
      material.opacity = state.edgeOpacity;
      material.needsUpdate = true;
    }
  }, [edgeOpacity]);

  useEffect(() => {
    showActivityRef.current = showActivity;
    const state = sceneStateRef.current;
    if (state) state.showActivity = showActivity;
  }, [showActivity]);

  useEffect(() => {
    synapseRateRef.current = synapsesPerSecond;
    const state = sceneStateRef.current;
    if (state) state.synapsesPerSecond = synapsesPerSecond;
  }, [synapsesPerSecond]);

  useEffect(() => {
    const state = sceneStateRef.current;
    if (!state) return;
    state.preserveSourceCoordinates = preserveSourceCoordinates;
    state.fitScale = fitScale;
    syncGraph(state, graphRef.current, activeNodeRef.current, activeEdgeRef.current, newNodeRef.current, visualState, showLabelsRef.current);
  }, [preserveSourceCoordinates, visualState, fitScale]);

  useEffect(() => {
    activeNodeRef.current = new Set(activeNodeIds);
    activeEdgeRef.current = new Set(activeEdgeKeys);
    const state = sceneStateRef.current;
    if (state) syncGraph(state, graphRef.current, activeNodeRef.current, activeEdgeRef.current, newNodeRef.current, visualState, showLabelsRef.current);
  }, [activeEdgeKeys, activeNodeIds, visualState]);

  useEffect(() => {
    newNodeRef.current = new Set(newNodeIds);
    const state = sceneStateRef.current;
    if (state) syncGraph(state, graphRef.current, activeNodeRef.current, activeEdgeRef.current, newNodeRef.current, visualState, showLabelsRef.current);
  }, [newNodeIds, visualState]);

  useEffect(() => {
    if (!control) return;
    const state = sceneStateRef.current;
    if (!state) return;
    const { camera, group } = state;
    state.preserveSourceCoordinates = preserveSourceCoordinates;

    const totalNodes = graphRef.current?.nodes?.length ?? 0;
    state.userCameraControlUntilFrame = state.frame + 420;
    if (control.action === "zoom-in") camera.position.z = Math.max(3.2, camera.position.z - Math.max(2.4, camera.position.z * 0.18));
    if (control.action === "zoom-out") camera.position.z = Math.min(maxZoomDistanceForNodeCount(totalNodes), camera.position.z + Math.max(1.8, camera.position.z * 0.18));
    if (control.action === "left") group.rotation.y -= 0.22;
    if (control.action === "right") group.rotation.y += 0.22;
    if (control.action === "up") group.rotation.x -= 0.18;
    if (control.action === "down") group.rotation.x += 0.18;
    if (control.action === "reset") {
      camera.position.set(0, 0, Math.max(cameraDistanceForNodeCount(totalNodes), state.lastFitDistance));
      group.rotation.set(DEFAULT_GRAPH_TILT_X, DEFAULT_GRAPH_TILT_Y, 0);
    }
    camera.updateProjectionMatrix();
    clampCameraZ(camera, totalNodes);
    const host = hostRef.current;
    if (host) {
      host.dataset.cameraZ = camera.position.z.toFixed(1);
      host.dataset.lastControlAction = control.action;
      host.dataset.lastControlSerial = String(control.serial);
      host.dataset.maxZoom = maxZoomDistanceForNodeCount(totalNodes).toFixed(1);
    }
    viewportChangeRef.current?.({
      cameraZ: camera.position.z,
      focus: { x: 0, y: 0, z: 0 },
      radius: viewportRadiusForCamera(camera),
    });
  }, [control]);

  useEffect(() => {
    if (!focusNode) return;
    const state = sceneStateRef.current;
    if (!state || !state.nodePositionArray) return;
    const index = state.nodeIndexById.get(focusNode.id);
    if (index === undefined) return;
    const { camera, group } = state;
    // Synapse zoom: park the camera on the ray THROUGH the node, looking at it,
    // so the node centers on screen with no group-rotation math. Suspend the
    // auto-camera while the trace plays (page sequencing re-fires per hop).
    state.userCameraControlUntilFrame = state.frame + 1200;
    const local = new THREE.Vector3(
      state.nodePositionArray[index * 3],
      state.nodePositionArray[index * 3 + 1],
      state.nodePositionArray[index * 3 + 2],
    );
    group.updateMatrixWorld(true);
    const world = local.applyMatrix4(group.matrixWorld);
    const length = world.length();
    if (length > 0.01) {
      camera.position.copy(world.clone().multiplyScalar((length + 8.5) / length));
    } else {
      camera.position.set(world.x, world.y, world.z + 8.5);
    }
    camera.lookAt(world);
    camera.updateProjectionMatrix();
  }, [focusNode]);

  useEffect(() => {
    const host = hostRef.current;
    if (!host) return;
    const container = host;

    const scene = new THREE.Scene();
    const darkMode = theme === "dark";
    scene.background = darkMode ? null : new THREE.Color(0xf8faf8);
    const camera = new THREE.PerspectiveCamera(48, container.clientWidth / Math.max(1, container.clientHeight), 0.1, 16000);
    camera.position.set(0, 0, 13);

    const renderer = new THREE.WebGLRenderer({ antialias: true, alpha: darkMode });
    const pixelRatio = resolveGraphPixelRatio(window.devicePixelRatio);
    renderer.outputColorSpace = THREE.SRGBColorSpace;
    // Overall scene ~2x brighter than the prior baseline. Linear tone mapping with
    // 2.0 exposure scales output uniformly (headroom so what looked ~50% reaches
    // full), while keeping color (no NoToneMapping no-op).
    renderer.toneMapping = THREE.LinearToneMapping;
    renderer.toneMappingExposure = 2.0;
    renderer.setClearColor(new THREE.Color(darkMode ? 0x000000 : 0xf8faf8), darkMode ? 0 : 1);
    renderer.setPixelRatio(pixelRatio);
    renderer.setSize(container.clientWidth, container.clientHeight);
    container.replaceChildren(renderer.domElement);

    // Bloom post-processing (dark mode only): the whole graph stays visible, but
    // pixels brighter than the threshold (the OVERBRIGHT active edges/nodes) glow
    // and bleed, so activation pops at scale without dimming the dormant graph.
    let composer: EffectComposer | null = null;
    let bloomPass: UnrealBloomPass | null = null;
    if (darkMode) {
      composer = new EffectComposer(renderer);
      composer.setPixelRatio(pixelRatio);
      composer.setSize(container.clientWidth, container.clientHeight);
      composer.addPass(new RenderPass(scene, camera));
      // (resolution, strength, radius, threshold) — threshold 0.85 keeps the
      // dormant graph (dim) out of the glow; only active overbright lines bloom.
      bloomPass = new UnrealBloomPass(
        new THREE.Vector2(container.clientWidth, container.clientHeight),
        1.1,
        0.6,
        0.85,
      );
      composer.addPass(bloomPass);
    }

    const group = new THREE.Group();
    group.rotation.set(DEFAULT_GRAPH_TILT_X, DEFAULT_GRAPH_TILT_Y, 0);
    scene.add(group);
    scene.add(new THREE.AmbientLight(0xffffff, darkMode ? 0.78 : 1.25));
    const light = new THREE.DirectionalLight(0xffffff, darkMode ? 0.8 : 1.3);
    light.position.set(4, 7, 8);
    scene.add(light);

    const grid = new THREE.GridHelper(18, 18, darkMode ? 0x303640 : 0xcdd3cf, darkMode ? 0x171b22 : 0xe3e6e3);
    const gridMaterials = Array.isArray(grid.material) ? grid.material : [grid.material];
    gridMaterials.forEach((material) => {
      material.transparent = true;
      material.opacity = darkMode ? 0.055 : 0.14;
      material.depthWrite = false;
    });
    grid.rotation.x = Math.PI / 2;
    grid.position.z = -2.2;
    group.add(grid);

    const state: SceneState = {
      activeEdgeKeys: new Set(),
      activeNodeIds: new Set(),
      activationHops: new Map(),
      activationEdgeIntensity: new Map(),
      camera,
      coordinateMutationWarned: false,
      dynamicObjects: [],
      edgeCapacity: 0,
      edgeColorArray: null,
      edgeGeometry: null,
      edgeLines: null,
      edgePositionBufferDirty: true,
      edgePositionArray: null,
      edgePulseCount: 0,
      fitScale,
      frame: 0,
      frozenPositionSnapshot: null,
      graphEdges: [],
      graphNodes: [],
      group,
      haloCapacity: 0,
      haloItems: [],
      haloMesh: null,
      knownNodeIds: new Set(),
      lastFitDistance: 0,
      lastGraphNodeCount: 0,
      lastViewportEmitFrame: -999,
      layoutDiagnostics: { layout_mode: "organic_semantic_force" },
      layoutRequestSerial: 0,
      layoutSignature: "",
      newNodeIds: new Set(),
      nodeBornAt: new Map(),
      nodeCapacity: 0,
      nodeColorArray: null,
      nodeGeometry: null,
      nodeIndexById: new Map(),
      nodePoints: null,
      nodePositionArray: null,
      nodePositionBufferDirty: true,
      nodePositionById: new Map(),
      nodeTargetById: new Map(),
      pointNodes: [],
      pulseCapacity: 0,
      pulseItems: [],
      pulseMesh: null,
      synapseLines: null,
      synapseGeometry: null,
      synapsePosArray: null,
      synapseColorArray: null,
      synapseCapacity: 0,
      synapseItems: [],
      synapseSpawnAccum: 0,
      synapsesPerSecond: synapseRateRef.current,
      showActivity: showActivityRef.current,
      nodeActivation: null,
      nodeActivationCapacity: 0,
      activationFireAccum: 0,
      renderer,
      scaleChunks: [],
      scene,
      shellCapacity: 0,
      shellMesh: null,
      startedAt: performance.now(),
      userCameraControlUntilFrame: 0,
      visibleEdges: [],
      visualState: resolveVisualState(visualState, graphRef.current, activeNodeRef.current, activeEdgeRef.current, newNodeRef.current),
      preserveSourceCoordinates,
      edgeOpacity: THREE.MathUtils.clamp(edgeOpacityRef.current, 0.04, 0.86),
      onViewportChange: viewportChangeRef.current,
      zoomPulseAt: -999,
      zoomBaseZ: 0,
    };
    sceneStateRef.current = state;
    syncGraph(state, graphRef.current, activeNodeRef.current, activeEdgeRef.current, newNodeRef.current, visualState, showLabelsRef.current);

    const raycaster = new THREE.Raycaster();
    const pointer = new THREE.Vector2();
    const drag = { active: false, moved: false, x: 0, y: 0 };

    function pointerEventToNdc(event: PointerEvent) {
      const rect = renderer.domElement.getBoundingClientRect();
      pointer.x = ((event.clientX - rect.left) / rect.width) * 2 - 1;
      pointer.y = -((event.clientY - rect.top) / rect.height) * 2 + 1;
    }

    function handlePointerDown(event: PointerEvent) {
      state.userCameraControlUntilFrame = state.frame + 420;
      drag.active = true;
      drag.x = event.clientX;
      drag.y = event.clientY;
      drag.moved = false;
      renderer.domElement.setPointerCapture(event.pointerId);
    }

    function handlePointerMove(event: PointerEvent) {
      if (!drag.active) return;
      state.userCameraControlUntilFrame = state.frame + 420;
      const dx = event.clientX - drag.x;
      const dy = event.clientY - drag.y;
      if (Math.abs(dx) + Math.abs(dy) > 2) drag.moved = true;
      group.rotation.y += dx * 0.006;
      group.rotation.x += dy * 0.004;
      drag.x = event.clientX;
      drag.y = event.clientY;
    }

    function handlePointerUp(event: PointerEvent) {
      renderer.domElement.releasePointerCapture(event.pointerId);
      drag.active = false;
      if (drag.moved) return;
      pointerEventToNdc(event);
      raycaster.setFromCamera(pointer, camera);
      raycaster.params.Points.threshold = Math.max(0.22, camera.position.z * 0.006);
      const hit = state.nodePoints ? raycaster.intersectObject(state.nodePoints)[0] : null;
      if (hit && typeof hit.index === "number") {
        const node = state.pointNodes[hit.index];
        if (node) selectRef.current?.(node);
      }
    }

    function handleWheel(event: WheelEvent) {
      event.preventDefault();
      const totalNodes = graphRef.current?.nodes?.length ?? 0;
      state.userCameraControlUntilFrame = state.frame + 420;
      camera.position.z = Math.max(3.2, Math.min(maxZoomDistanceForNodeCount(totalNodes), camera.position.z + event.deltaY * Math.max(0.016, camera.position.z * 0.0018)));
    }

    function handleResize() {
      camera.aspect = container.clientWidth / Math.max(1, container.clientHeight);
      camera.updateProjectionMatrix();
      renderer.setSize(container.clientWidth, container.clientHeight);
      composer?.setSize(container.clientWidth, container.clientHeight);
      bloomPass?.setSize(container.clientWidth, container.clientHeight);
    }

    let visibilityPaused = typeof document !== "undefined" ? document.hidden : false;
    let memorySafeMode = false;
    let lastMemoryProbeAt = 0;
    let lastRenderedAt = 0;
    let lastSynapseElapsed = 0;
    function handleVisibilityChange() {
      visibilityPaused = document.hidden;
      lastRenderedAt = 0;
      container.dataset.visibilityPaused = String(visibilityPaused);
    }

    renderer.domElement.addEventListener("pointerdown", handlePointerDown);
    renderer.domElement.addEventListener("pointermove", handlePointerMove);
    renderer.domElement.addEventListener("pointerup", handlePointerUp);
    renderer.domElement.addEventListener("wheel", handleWheel, { passive: false });
    window.addEventListener("resize", handleResize);
    document.addEventListener("visibilitychange", handleVisibilityChange);

    let animation = 0;
    function animate(now = performance.now()) {
      animation = requestAnimationFrame(animate);
      if (now - lastMemoryProbeAt > 1000) {
        lastMemoryProbeAt = now;
        memorySafeMode = browserMemorySafeMode(chromeHeapSnapshot());
      }
      const totalNodes = graphRef.current?.nodes?.length ?? 0;
      const denseGraph = totalNodes > 1200 || state.visibleEdges.length > 1800;
      const fpsCap = graphRenderFpsCap({ denseGraph, memorySafeMode, visibilityPaused });
      writeGraphTelemetry(container, {
        densityParticles: state.shellCapacity,
        geometriesCount: 4 + state.dynamicObjects.length,
        materializedNodes: totalNodes,
        memorySafeMode,
        pixelRatio,
        renderFpsCap: fpsCap,
        renderedEdges: state.visibleEdges.length,
        visibilityPaused,
        visualHints: state.shellCapacity + state.haloItems.length + state.pulseItems.length,
        webgpuEnabled: String(state.layoutDiagnostics.layout_accelerator ?? "") === "webgpu",
        webgpuFallbackReason: String(state.layoutDiagnostics.webgpu_disabled_reason ?? ""),
      });
      if (visibilityPaused || !shouldRenderGraphFrame(now, lastRenderedAt, fpsCap)) return;
      lastRenderedAt = now;
      state.frame += 1;
      const elapsed = (performance.now() - state.startedAt) / 1000;
      const synapseDt = lastSynapseElapsed > 0 ? elapsed - lastSynapseElapsed : 0;
      lastSynapseElapsed = elapsed;
      if (!drag.active && coordinateAnimationAllowed(state.visualState)) group.rotation.y += 0.00125;

      updateNodeActivation(state, synapseDt);
      updateNodeBuffers(state, elapsed);
      updateEdgeBuffers(state, elapsed);
      updateShellMesh(state, elapsed);
      updateHaloMesh(state, elapsed);
      updatePulseMesh(state, elapsed);

      container.dataset.cameraZ = camera.position.z.toFixed(1);
      container.dataset.maxZoom = maxZoomDistanceForNodeCount(totalNodes).toFixed(1);
      container.dataset.nodeCount = String(totalNodes);
      container.dataset.activeEdgeCount = String(state.activeEdgeKeys.size);
      container.dataset.edgePulseCount = String(state.edgePulseCount);
      container.dataset.bufferMode = "persistent-append";
      container.dataset.visualState = state.visualState;
      container.dataset.layoutMode = String(state.layoutDiagnostics.layout_mode ?? "organic_semantic_force");
      container.dataset.activeClusterCount = String(state.layoutDiagnostics.active_cluster_count ?? 0);
      container.dataset.averageDegree = String(state.layoutDiagnostics.average_degree ?? 0);
      container.dataset.zAxisRatio = String(state.layoutDiagnostics.z_axis_ratio ?? 0);
      container.dataset.activeCentroidOffset = String(state.layoutDiagnostics.active_centroid_offset ?? 0);
      container.dataset.hop1Count = String(state.layoutDiagnostics.hop1_count ?? 0);
      container.dataset.hop2Count = String(state.layoutDiagnostics.hop2_count ?? 0);
      if (state.onViewportChange && state.frame - state.lastViewportEmitFrame >= 12) {
        state.lastViewportEmitFrame = state.frame;
        state.onViewportChange({
          cameraZ: camera.position.z,
          focus: { x: 0, y: 0, z: 0 },
          radius: viewportRadiusForCamera(camera),
        });
      }
      // Arrival zoom-pulse: cosmetic 5% zoom-in that eases back over 3s.
      // Applied only to the render snapshot — the real camera.position.z is
      // unchanged so the fit/clamp/user-control logic is never disrupted.
      let zoomSavedZ = 0;
      if (state.zoomBaseZ > 0 && state.frame >= state.userCameraControlUntilFrame) {
        const sinceP = elapsed - state.zoomPulseAt;
        if (sinceP < 3.0) {
          const t = Math.min(1, sinceP / 3.0);
          const smooth = t * t * (3 - 2 * t); // smoothstep easing
          // zoom factor: 0.95 at t=0, 1.0 at t=1 (ease back)
          const zoomF = 0.95 + 0.05 * smooth;
          zoomSavedZ = camera.position.z;
          camera.position.z = state.zoomBaseZ * zoomF;
        } else {
          state.zoomBaseZ = 0; // pulse complete
        }
      }
      // Skip the bloom pass when activity is hidden — saves GPU/power.
      if (composer && state.showActivity) composer.render();
      else renderer.render(scene, camera);
      if (zoomSavedZ > 0) camera.position.z = zoomSavedZ;
    }
    animate();

    return () => {
      cancelAnimationFrame(animation);
      window.removeEventListener("resize", handleResize);
      document.removeEventListener("visibilitychange", handleVisibilityChange);
      renderer.domElement.removeEventListener("pointerdown", handlePointerDown);
      renderer.domElement.removeEventListener("pointermove", handlePointerMove);
      renderer.domElement.removeEventListener("pointerup", handlePointerUp);
      renderer.domElement.removeEventListener("wheel", handleWheel);
      removeDynamicObjects(state);
      if (state.nodePoints) {
        state.group.remove(state.nodePoints);
        disposeObject(state.nodePoints);
      }
      if (state.edgeLines) {
        state.group.remove(state.edgeLines);
        disposeObject(state.edgeLines);
      }
      if (state.haloMesh) {
        state.group.remove(state.haloMesh);
        disposeObject(state.haloMesh);
      }
      if (state.shellMesh) {
        state.group.remove(state.shellMesh);
        disposeObject(state.shellMesh);
      }
      if (state.pulseMesh) {
        state.group.remove(state.pulseMesh);
        disposeObject(state.pulseMesh);
      }
      if (state.synapseLines) {
        state.group.remove(state.synapseLines);
        disposeObject(state.synapseLines);
      }
      disposeObject(grid);
      renderer.dispose();
      container.replaceChildren();
      sceneStateRef.current = null;
    };
  }, [theme]);

  const displayVisualState = resolveVisualState(
    visualState,
    graph,
    new Set(activeNodeIds),
    new Set(activeEdgeKeys),
    new Set(newNodeIds),
  );
  const settledText = frozenStatusText(displayVisualState);

  return (
    <div className="rag3d-shell">
      <div className="rag3d-host" ref={hostRef} aria-label="3D RAG traversal graph" />
      {settledText ? <span className="rag3d-settled-label">{settledText}</span> : null}
    </div>
  );
}
