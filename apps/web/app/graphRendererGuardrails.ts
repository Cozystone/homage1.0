"use client";

export type ChromeHeapSnapshot = {
  jsHeapSizeLimit: number | null;
  totalJSHeapSize: number | null;
  usedJSHeapSize: number | null;
};

export type GraphRendererTelemetry = {
  densityParticles?: number;
  geometriesCount?: number;
  materializedNodes: number;
  materialsCount?: number;
  memorySafeMode: boolean;
  pixelRatio: number;
  renderFpsCap: number;
  renderedEdges: number;
  texturesCount?: number;
  visibilityPaused: boolean;
  visualHints?: number;
  webgpuEnabled?: boolean;
  webgpuFallbackReason?: string;
};

const DEFAULT_PIXEL_RATIO_CAP = 1.5;
const DEFAULT_VISIBLE_FPS = 30;
const MEMORY_SAFE_FPS = 20;
const HIDDEN_FPS = 15;

type PerformanceWithMemory = Performance & {
  memory?: {
    jsHeapSizeLimit: number;
    totalJSHeapSize: number;
    usedJSHeapSize: number;
  };
};

export function graphPixelRatioCap(): number {
  const raw = Number(process.env.NEXT_PUBLIC_ATANOR_GRAPH_PIXEL_RATIO_CAP);
  if (Number.isFinite(raw) && raw >= 1 && raw <= 2) return raw;
  return DEFAULT_PIXEL_RATIO_CAP;
}

export function resolveGraphPixelRatio(devicePixelRatio: number | undefined, cap = graphPixelRatioCap()): number {
  const ratio = Number.isFinite(devicePixelRatio) && devicePixelRatio ? Number(devicePixelRatio) : 1;
  return Math.max(1, Math.min(ratio, cap));
}

export function graphRenderFpsCap(options: { denseGraph?: boolean; memorySafeMode?: boolean; visibilityPaused?: boolean }): number {
  if (options.visibilityPaused) return HIDDEN_FPS;
  if (options.memorySafeMode) return MEMORY_SAFE_FPS;
  return options.denseGraph ? DEFAULT_VISIBLE_FPS : DEFAULT_VISIBLE_FPS;
}

export function shouldRenderGraphFrame(now: number, lastRenderedAt: number, fpsCap: number): boolean {
  if (lastRenderedAt <= 0) return true;
  return now - lastRenderedAt >= 1000 / Math.max(1, fpsCap);
}

export function chromeHeapSnapshot(): ChromeHeapSnapshot {
  const memory = typeof performance !== "undefined" ? (performance as PerformanceWithMemory).memory : undefined;
  if (!memory) return { jsHeapSizeLimit: null, totalJSHeapSize: null, usedJSHeapSize: null };
  return {
    jsHeapSizeLimit: memory.jsHeapSizeLimit,
    totalJSHeapSize: memory.totalJSHeapSize,
    usedJSHeapSize: memory.usedJSHeapSize,
  };
}

export function browserMemorySafeMode(snapshot: ChromeHeapSnapshot = chromeHeapSnapshot()): boolean {
  if (!snapshot.usedJSHeapSize || !snapshot.jsHeapSizeLimit) return false;
  return snapshot.usedJSHeapSize / snapshot.jsHeapSizeLimit >= 0.72;
}

export function writeGraphTelemetry(target: HTMLElement, telemetry: GraphRendererTelemetry): void {
  target.dataset.materializedNodes = String(telemetry.materializedNodes);
  target.dataset.renderedEdges = String(telemetry.renderedEdges);
  target.dataset.pixelRatio = telemetry.pixelRatio.toFixed(2);
  target.dataset.renderFpsCap = String(telemetry.renderFpsCap);
  target.dataset.visibilityPaused = String(telemetry.visibilityPaused);
  target.dataset.memorySafeMode = String(telemetry.memorySafeMode);
  if (telemetry.visualHints !== undefined) target.dataset.visualHints = String(telemetry.visualHints);
  if (telemetry.densityParticles !== undefined) target.dataset.densityParticles = String(telemetry.densityParticles);
  if (telemetry.geometriesCount !== undefined) target.dataset.geometriesCount = String(telemetry.geometriesCount);
  if (telemetry.materialsCount !== undefined) target.dataset.materialsCount = String(telemetry.materialsCount);
  if (telemetry.texturesCount !== undefined) target.dataset.texturesCount = String(telemetry.texturesCount);
  if (telemetry.webgpuEnabled !== undefined) target.dataset.webgpuEnabled = String(telemetry.webgpuEnabled);
  if (telemetry.webgpuFallbackReason !== undefined) target.dataset.webgpuFallbackReason = telemetry.webgpuFallbackReason;
}
