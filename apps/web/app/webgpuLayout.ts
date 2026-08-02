"use client";

import type { Rag3DEdge, Rag3DNode } from "./Rag3DScene";

type WebGpuNavigator = Navigator & {
  gpu?: {
    requestAdapter(options?: unknown): Promise<any>;
    getPreferredCanvasFormat?: () => string;
  };
};

export type WebGpuLayoutResult = {
  diagnostics: Record<string, number | string | number[]>;
  positions: Array<[number, number, number]>;
};

const MAX_WEBGPU_LAYOUT_NODES = 4096;
const MAX_WEBGPU_LAYOUT_EDGES = 24000;
const WORKGROUP_SIZE = 64;
const GPU_BUFFER_USAGE = {
  MAP_READ: 1,
  COPY_SRC: 4,
  COPY_DST: 8,
  UNIFORM: 64,
  STORAGE: 128,
} as const;
const GPU_MAP_MODE_READ = 1;

const layoutShader = `
struct Node {
  pos: vec4f,
  vel: vec4f,
  meta: vec4f,
};

struct Edge {
  source: f32,
  target: f32,
  weight: f32,
  pad: f32,
};

struct Params {
  nodeCount: f32,
  edgeCount: f32,
  cooling: f32,
  iteration: f32,
  repulsionStride: f32,
  edgeStride: f32,
  activeBias: f32,
  pad0: f32,
};

@group(0) @binding(0) var<storage, read> inNodes: array<Node>;
@group(0) @binding(1) var<storage, read_write> outNodes: array<Node>;
@group(0) @binding(2) var<storage, read> edges: array<Edge>;
@group(0) @binding(3) var<uniform> params: Params;

@compute @workgroup_size(64)
fn main(@builtin(global_invocation_id) id: vec3u) {
  let i = id.x;
  if (i >= u32(params.nodeCount)) {
    return;
  }

  var node = inNodes[i];
  var force = -node.pos.xyz * 0.018;
  let stride = max(1u, u32(params.repulsionStride));

  for (var j: u32 = 0u; j < u32(params.nodeCount); j = j + stride) {
    if (i == j) {
      continue;
    }
    let other = inNodes[j];
    let delta = node.pos.xyz - other.pos.xyz;
    let dist2 = max(dot(delta, delta), 0.01);
    let strength = 0.018 / dist2;
    force = force + normalize(delta + vec3f(0.0003, 0.0007, 0.0005)) * strength;
  }

  let edgeStride = max(1u, u32(params.edgeStride));
  for (var edgeIndex: u32 = 0u; edgeIndex < u32(params.edgeCount); edgeIndex = edgeIndex + edgeStride) {
    let edge = edges[edgeIndex];
    let source = u32(edge.source);
    let target = u32(edge.target);
    if (source == i || target == i) {
      let otherIndex = select(source, target, source == i);
      let other = inNodes[otherIndex];
      let delta = other.pos.xyz - node.pos.xyz;
      let distance = max(length(delta), 0.001);
      let desired = 1.8 + (1.0 / sqrt(edge.weight + 0.2)) * 2.7;
      force = force + normalize(delta) * (distance - desired) * 0.022 * edge.weight;
    }
  }

  let activePull = node.meta.y * params.activeBias;
  force = force + normalize(node.meta.xyz + vec3f(0.001, 0.002, 0.003)) * activePull * 0.012;
  let orbit = vec3f(
    sin(params.iteration * 0.37 + node.meta.x * 6.2831),
    cos(params.iteration * 0.31 + node.meta.y * 5.112),
    sin(params.iteration * 0.19 + node.meta.z * 4.173)
  ) * 0.006;

  node.vel = vec4f((node.vel.xyz + (force + orbit) * params.cooling) * 0.86, 0.0);
  node.pos = vec4f(clamp(node.pos.xyz + node.vel.xyz, vec3f(-76.0, -76.0, -68.0), vec3f(76.0, 76.0, 68.0)), 1.0);
  outNodes[i] = node;
}
`;

export async function computeWebGpuGraphLayout(
  nodes: Rag3DNode[],
  edges: Rag3DEdge[],
  activeNodeIds: Set<string>,
): Promise<WebGpuLayoutResult | null> {
  if (typeof navigator === "undefined") return null;
  const gpu = (navigator as WebGpuNavigator).gpu;
  if (!gpu || nodes.length < 16 || nodes.length > MAX_WEBGPU_LAYOUT_NODES) return null;

  const adapter = await gpu.requestAdapter({ powerPreference: "high-performance" });
  if (!adapter) return null;
  const device = await adapter.requestDevice();
  const validEdges = buildIndexedEdges(nodes, edges).slice(0, MAX_WEBGPU_LAYOUT_EDGES);
  const nodeData = buildNodeData(nodes, activeNodeIds);
  const edgeData = new Float32Array(Math.max(1, validEdges.length) * 4);
  validEdges.forEach((edge, index) => {
    const offset = index * 4;
    edgeData[offset] = edge.source;
    edgeData[offset + 1] = edge.target;
    edgeData[offset + 2] = edge.weight;
  });

  const usage = GPU_BUFFER_USAGE.STORAGE | GPU_BUFFER_USAGE.COPY_DST | GPU_BUFFER_USAGE.COPY_SRC;
  let readBuffer: any | null = null;
  let writeBuffer: any | null = null;
  let edgeBuffer: any | null = null;
  let paramsBuffer: any | null = null;
  let resultBuffer: any | null = null;
  let resultMapped = false;
  try {
    readBuffer = createMappedBuffer(device, nodeData, usage);
    writeBuffer = createMappedBuffer(device, nodeData, usage);
    edgeBuffer = createMappedBuffer(device, edgeData, GPU_BUFFER_USAGE.STORAGE | GPU_BUFFER_USAGE.COPY_DST);
    paramsBuffer = device.createBuffer({
      size: 32,
      usage: GPU_BUFFER_USAGE.UNIFORM | GPU_BUFFER_USAGE.COPY_DST,
    });
    resultBuffer = device.createBuffer({
      size: nodeData.byteLength,
      usage: GPU_BUFFER_USAGE.MAP_READ | GPU_BUFFER_USAGE.COPY_DST,
    });

    const module = device.createShaderModule({ code: layoutShader });
    const pipeline = device.createComputePipeline({
      layout: "auto",
      compute: { module, entryPoint: "main" },
    });
    const bindGroups = [
      device.createBindGroup({
        layout: pipeline.getBindGroupLayout(0),
        entries: [
          { binding: 0, resource: { buffer: readBuffer } },
          { binding: 1, resource: { buffer: writeBuffer } },
          { binding: 2, resource: { buffer: edgeBuffer } },
          { binding: 3, resource: { buffer: paramsBuffer } },
        ],
      }),
      device.createBindGroup({
        layout: pipeline.getBindGroupLayout(0),
        entries: [
          { binding: 0, resource: { buffer: writeBuffer } },
          { binding: 1, resource: { buffer: readBuffer } },
          { binding: 2, resource: { buffer: edgeBuffer } },
          { binding: 3, resource: { buffer: paramsBuffer } },
        ],
      }),
    ];

    const iterations = nodes.length > 3000 ? 18 : nodes.length > 1200 ? 24 : 36;
    const repulsionStride = nodes.length > 2200 ? 5 : nodes.length > 900 ? 3 : 1;
    const edgeStride = validEdges.length > 12000 ? Math.ceil(validEdges.length / 12000) : 1;
    for (let iteration = 0; iteration < iterations; iteration += 1) {
      const params = new Float32Array([
        nodes.length,
        validEdges.length,
        1 - iteration / Math.max(1, iterations),
        iteration,
        repulsionStride,
        edgeStride,
        activeNodeIds.size > 0 ? 1 : 0,
        0,
      ]);
      device.queue.writeBuffer(paramsBuffer, 0, params);
      const encoder = device.createCommandEncoder();
      const pass = encoder.beginComputePass();
      pass.setPipeline(pipeline);
      pass.setBindGroup(0, bindGroups[iteration % 2]);
      pass.dispatchWorkgroups(Math.ceil(nodes.length / WORKGROUP_SIZE));
      pass.end();
      device.queue.submit([encoder.finish()]);
    }

    const finalBuffer = iterations % 2 === 0 ? readBuffer : writeBuffer;
    const encoder = device.createCommandEncoder();
    encoder.copyBufferToBuffer(finalBuffer, 0, resultBuffer, 0, nodeData.byteLength);
    device.queue.submit([encoder.finish()]);
    await device.queue.onSubmittedWorkDone();
    await resultBuffer.mapAsync(GPU_MAP_MODE_READ);
    resultMapped = true;
    const result = new Float32Array(resultBuffer.getMappedRange());
    const positions = normalizeResultPositions(result, nodes.length);
    resultBuffer.unmap();
    resultMapped = false;

    return {
      positions,
      diagnostics: {
        layout_mode: "browser_webgpu_force",
        layout_accelerator: "webgpu",
        webgpu_nodes: nodes.length,
        webgpu_edges: validEdges.length,
        webgpu_iterations: iterations,
        webgpu_repulsion_stride: repulsionStride,
        webgpu_edge_stride: edgeStride,
      },
    };
  } finally {
    if (resultMapped) {
      try {
        resultBuffer?.unmap();
      } catch {
        // Ignore cleanup errors; the caller falls back to CPU layout on the original failure.
      }
    }
    readBuffer?.destroy?.();
    writeBuffer?.destroy?.();
    edgeBuffer?.destroy?.();
    paramsBuffer?.destroy?.();
    resultBuffer?.destroy?.();
    device.destroy?.();
  }
}

function createMappedBuffer(device: any, data: Float32Array, usage: number) {
  const buffer = device.createBuffer({
    size: data.byteLength,
    usage,
    mappedAtCreation: true,
  });
  new Float32Array(buffer.getMappedRange()).set(data);
  buffer.unmap();
  return buffer;
}

function buildIndexedEdges(nodes: Rag3DNode[], edges: Rag3DEdge[]) {
  const indexById = new Map(nodes.map((node, index) => [node.id, index]));
  return edges
    .map((edge) => {
      const source = indexById.get(edge.source);
      const target = indexById.get(edge.target);
      if (source === undefined || target === undefined) return null;
      return {
        source,
        target,
        weight: Math.max(0.08, Math.min(2.4, Number(edge.weight ?? edge.confidence ?? 0.52))),
      };
    })
    .filter((edge): edge is { source: number; target: number; weight: number } => Boolean(edge));
}

function buildNodeData(nodes: Rag3DNode[], activeNodeIds: Set<string>) {
  const data = new Float32Array(nodes.length * 12);
  const count = Math.max(1, nodes.length);
  nodes.forEach((node, index) => {
    const offset = index * 12;
    const y = 1 - ((index + 0.5) / count) * 2;
    const theta = index * Math.PI * (3 - Math.sqrt(5)) + hashUnit(node.id, 29) * 0.82;
    const radial = Math.sqrt(Math.max(0.0001, 1 - y * y));
    const radius = Math.min(44, 6.2 + Math.cbrt(count) * 1.56) * (0.78 + hash01(node.id, 47) * 0.34);
    data[offset] = Number.isFinite(node.x) ? node.x : Math.cos(theta) * radial * radius;
    data[offset + 1] = Number.isFinite(node.y) ? node.y : y * radius;
    data[offset + 2] = Number.isFinite(node.z) ? node.z : Math.sin(theta) * radial * radius * 1.18;
    data[offset + 3] = 1;
    data[offset + 8] = hash01(node.id, 101);
    data[offset + 9] = activeNodeIds.has(node.id) ? 1 : 0;
    data[offset + 10] = hash01(`${node.type}:${node.id}`, 131);
  });
  return data;
}

function normalizeResultPositions(result: Float32Array, nodeCount: number): Array<[number, number, number]> {
  const center = [0, 0, 0];
  for (let index = 0; index < nodeCount; index += 1) {
    center[0] += result[index * 12];
    center[1] += result[index * 12 + 1];
    center[2] += result[index * 12 + 2];
  }
  center[0] /= nodeCount;
  center[1] /= nodeCount;
  center[2] /= nodeCount;
  let radius = 1;
  for (let index = 0; index < nodeCount; index += 1) {
    const dx = result[index * 12] - center[0];
    const dy = result[index * 12 + 1] - center[1];
    const dz = result[index * 12 + 2] - center[2];
    radius = Math.max(radius, Math.sqrt(dx * dx + dy * dy + dz * dz));
  }
  const targetRadius = Math.min(74, 8.4 + Math.cbrt(nodeCount) * 2.2);
  const scale = targetRadius / radius;
  const positions: Array<[number, number, number]> = [];
  for (let index = 0; index < nodeCount; index += 1) {
    positions.push([
      (result[index * 12] - center[0]) * scale,
      (result[index * 12 + 1] - center[1]) * scale,
      (result[index * 12 + 2] - center[2]) * scale * 1.16,
    ]);
  }
  return positions;
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
