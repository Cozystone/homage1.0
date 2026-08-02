export function backendBaseUrl() {
  return backendBaseCandidates()[0] ?? "";
}

export function backendBaseCandidates() {
  const explicit = [
    process.env.ATANOR_GATEWAY_API,
    process.env.HOMAGE_GATEWAY_API,
    process.env.API_BASE_URL,
  ].filter((value): value is string => Boolean(value));
  if (process.env.VERCEL) return explicit;
  // Only the live companion (:8502) runs locally. The legacy alternates :8504/:8500 are
  // not up, so every endpoint that 404s on :8502 fell through to two ECONNREFUSED probes,
  // adding latency + log noise on each dashboard poll. Set ATANOR_GATEWAY_API to add a
  // real alternate; otherwise probe only what actually exists.
  return Array.from(new Set([
    ...explicit,
    "http://127.0.0.1:8502",
  ]));
}

// The shared Cloud Brain runs always-on in the cloud (Oracle VM, HTTPS). The
// exe / web app fetches the Cloud Brain tab live from there, while Local Brain
// and chat stay on the local companion. Set CLOUD_BRAIN_BASE (baked into the exe
// build) to route only `/api/cloud-brain/*` to the cloud endpoint.
export function cloudBrainBase(): string | null {
  return process.env.CLOUD_BRAIN_BASE || process.env.NEXT_PUBLIC_CLOUD_BRAIN_BASE || null;
}

export async function proxyJson(path: string, init?: RequestInit) {
  // Cloud-Brain calls prefer the always-on cloud endpoint (when configured),
  // then fall back to local companions for resilience. Everything else stays local.
  const cloud = cloudBrainBase();
  const bases =
    cloud && path.startsWith("/api/cloud-brain/")
      ? [cloud, ...backendBaseCandidates()]
      : backendBaseCandidates();

  // Per-candidate budget. This must accommodate the SLOWEST legitimate endpoint —
  // /api/chat/atanor does graph routing + holographic fold + realization (~3-7s, and
  // up to ~30s+ with live web search). The previous 3.5s budget aborted every chat
  // request ("fetch failed" -> 502) while fast status endpoints (<0.1s) were unaffected,
  // which read as "응답없음". A wedged backend now takes longer to fail over, but the
  // client carries its own timeout and the alternate companions are usually absent.
  const PER_TRY_MS = Number(process.env.ATANOR_PROXY_TIMEOUT_MS ?? 45000);

  // Restart resilience: the engine watchdog may be mid-restart (memory-ceiling
  // recycle takes ~5-15s). A connection REFUSED during that window used to
  // surface as "엔진이 응답을 만들지 못했어요" — for the person, a dead product.
  // So refused/reset connections get a short wait-and-retry before giving up:
  // the restart window becomes a slower answer, not a failure.
  const RETRY_ROUNDS = 3;
  const RETRY_WAIT_MS = 4000;

  let lastError: unknown = null;
  for (let round = 0; round < RETRY_ROUNDS; round++) {
    for (const baseUrl of bases) {
      if (!baseUrl) continue;
      const ctrl = new AbortController();
      const timer = setTimeout(() => ctrl.abort(), PER_TRY_MS);
      try {
        const response = await fetch(`${baseUrl}${path}`, {
          ...init,
          cache: "no-store",
          signal: ctrl.signal,
        });
        if (response.status === 404 || response.status === 405) {
          continue;
        }
        return {
          body: await response.json(),
          status: response.status,
        };
      } catch (error) {
        lastError = error;
      } finally {
        clearTimeout(timer);
      }
    }
    const msg = String((lastError as Error)?.message ?? lastError ?? "");
    const cause = String((lastError as { cause?: unknown })?.cause ?? "");
    const transient = /ECONNREFUSED|ECONNRESET|fetch failed|socket hang up|UND_ERR/i;
    if (!(transient.test(msg) || transient.test(cause)) || round === RETRY_ROUNDS - 1) {
      break;
    }
    await new Promise((r) => setTimeout(r, RETRY_WAIT_MS));
  }
  if (lastError) {
    throw lastError;
  }
  return null;
}
