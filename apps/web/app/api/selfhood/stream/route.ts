import { backendBaseCandidates } from "../../_backend";

// SSE proxy for the continuously-alive self. The self runs on the LOCAL companion
// (:8502), so this streams from the local backend (NOT the cloud brain). The upstream
// SSE body is piped straight through so the "living mind" UI receives every heartbeat.
export const dynamic = "force-dynamic";
export const runtime = "nodejs";

export async function GET(): Promise<Response> {
  for (const base of backendBaseCandidates()) {
    if (!base) continue;
    try {
      const upstream = await fetch(`${base}/api/selfhood/stream`, {
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
      /* try the next candidate */
    }
  }
  return new Response("event: offline\ndata: {}\n\n", {
    status: 200,
    headers: { "Content-Type": "text/event-stream", "Cache-Control": "no-cache" },
  });
}
