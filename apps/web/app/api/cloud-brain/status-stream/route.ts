import { cloudBrainBase, backendBaseCandidates } from "../../_backend";

// SSE proxy (난제 P4): the dashboard's cloud-brain panels each used to poll
// /api/cloud-brain/learning/continuous/metrics every ~2s (3 duplicate loops). They
// now share ONE EventSource to the cloud brain's merged /api/status/stream, proxied
// here so the browser talks to a same-origin URL. The upstream body (a real SSE
// byte stream) is piped straight through — no buffering, no re-encoding.

export const dynamic = "force-dynamic";
export const runtime = "nodejs";

export async function GET(): Promise<Response> {
  const cloud = cloudBrainBase();
  const bases = [cloud, ...backendBaseCandidates()].filter(
    (b): b is string => Boolean(b),
  );
  for (const base of bases) {
    try {
      const upstream = await fetch(`${base}/api/status/stream`, {
        headers: { Accept: "text/event-stream" },
        cache: "no-store",
      });
      if (!upstream.ok || !upstream.body) continue;
      return new Response(upstream.body, {
        status: 200,
        headers: {
          "Content-Type": "text/event-stream",
          "Cache-Control": "no-cache, no-transform",
          Connection: "keep-alive",
          "X-Accel-Buffering": "no",
        },
      });
    } catch {
      // try the next candidate base
    }
  }
  // No upstream reachable: return a terminating stream so the client falls back to
  // polling rather than hanging on an open connection.
  return new Response("event: unavailable\ndata: {}\n\n", {
    status: 200,
    headers: { "Content-Type": "text/event-stream", "Cache-Control": "no-cache" },
  });
}
