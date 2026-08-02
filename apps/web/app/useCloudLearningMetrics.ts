"use client";

import { useEffect, useState } from "react";

/**
 * Shared live cloud-brain learning metrics (난제 P4 — the polling-storm fix).
 *
 * Three panels (LiveLearningPanel, CloudBrainSphereScene, the page dashboard)
 * each independently polled /api/cloud-brain/learning/continuous/metrics every
 * ~2s. This module keeps ONE subscription for the whole app and fans the latest
 * metrics out to every subscriber:
 *   - SSE-first: one EventSource to /api/cloud-brain/status-stream (proxied to the
 *     cloud brain's merged /api/status/stream); the `learning` slice is the metrics.
 *   - graceful fallback: if SSE never opens (or errors), ONE shared poll loop hits
 *     the metrics endpoint. Either way the app makes a single request stream, not N.
 * Nothing here fabricates data — it only deduplicates the transport.
 */

export type LearningMetrics = Record<string, unknown> & {
  running?: boolean;
  concepts_added?: number;
  surface_added?: number;
};

type Listener = (m: LearningMetrics | null) => void;

const POLL_MS = 2000;
const SSE_GRACE_MS = 6000; // if SSE hasn't delivered by now, start the poll fallback

let latest: LearningMetrics | null = null;
const listeners = new Set<Listener>();
let source: EventSource | null = null;
let pollTimer: ReturnType<typeof setInterval> | null = null;
let sseDelivered = false;
let started = false;

function emit() {
  for (const fn of listeners) fn(latest);
}

async function pollOnce() {
  try {
    const res = await fetch("/api/cloud-brain/learning/continuous/metrics", { cache: "no-store" });
    const d = (await res.json()) as LearningMetrics;
    latest = d;
    emit();
  } catch {
    /* keep last value */
  }
}

function startPolling() {
  if (pollTimer !== null) return;
  void pollOnce();
  pollTimer = setInterval(() => void pollOnce(), POLL_MS);
}

function stopPolling() {
  if (pollTimer !== null) {
    clearInterval(pollTimer);
    pollTimer = null;
  }
}

function start() {
  if (started) return;
  started = true;
  sseDelivered = false;
  try {
    source = new EventSource("/api/cloud-brain/status-stream");
    source.onmessage = (e) => {
      try {
        const doc = JSON.parse(e.data) as { learning?: LearningMetrics };
        if (doc && doc.learning && typeof doc.learning === "object") {
          latest = doc.learning;
          sseDelivered = true;
          stopPolling(); // SSE is live — no need for the poll fallback
          emit();
        }
      } catch {
        /* ignore malformed frame */
      }
    };
    source.onerror = () => {
      // EventSource auto-reconnects; ensure data keeps flowing via polling meanwhile.
      if (!sseDelivered) startPolling();
    };
  } catch {
    startPolling();
  }
  // If SSE produced nothing within the grace window, fall back to polling.
  window.setTimeout(() => {
    if (!sseDelivered) startPolling();
  }, SSE_GRACE_MS);
}

function stop() {
  started = false;
  if (source) {
    source.close();
    source = null;
  }
  stopPolling();
}

/** Subscribe a component to the shared metrics; returns the latest value. */
export function useCloudLearningMetrics(): LearningMetrics | null {
  const [value, setValue] = useState<LearningMetrics | null>(latest);
  useEffect(() => {
    const listener: Listener = (m) => setValue(m);
    listeners.add(listener);
    if (latest !== null) setValue(latest);
    start();
    return () => {
      listeners.delete(listener);
      if (listeners.size === 0) stop(); // last subscriber left — release the transport
    };
  }, []);
  return value;
}
