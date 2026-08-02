import { backendBaseCandidates } from "../../../_backend";

// SSE passthrough for the answer stream. Unlike the sibling non-stream route this must NOT buffer:
// the whole point is that stage events reach the UI while ATANOR is still working (a first-time
// web-grounded question costs ~17s of real search). So we forward the upstream ReadableStream
// as-is and keep the connection unbuffered.
export const dynamic = "force-dynamic";
export const runtime = "nodejs";

export async function POST(request: Request) {
  const body = await request.text();
  let lastError = "no backend candidate";
  for (const base of backendBaseCandidates()) {
    try {
      const upstream = await fetch(`${base}/api/chat/atanor/stream`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body,
        // @ts-expect-error -- Node fetch needs this to stream a request/response body
        duplex: "half",
      });
      if (!upstream.ok || !upstream.body) {
        lastError = `upstream ${upstream.status}`;
        continue;
      }
      return new Response(upstream.body, {
        status: 200,
        headers: {
          "Content-Type": "text/event-stream; charset=utf-8",
          "Cache-Control": "no-cache, no-transform",
          Connection: "keep-alive",
          "X-Accel-Buffering": "no",
        },
      });
    } catch (error) {
      lastError = error instanceof Error ? error.message : "chat stream proxy failed";
    }
  }
  // Same SSE shape the client already handles, so a dead engine surfaces as an error event
  // rather than an unparseable body.
  return new Response(`data: ${JSON.stringify({ type: "error", detail: lastError })}\n\n`, {
    status: 502,
    headers: { "Content-Type": "text/event-stream; charset=utf-8", "Cache-Control": "no-cache" },
  });
}
