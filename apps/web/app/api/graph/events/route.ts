import { NextRequest } from "next/server";
import { backendBaseUrl } from "../../_backend";

const LOCAL_GRAPH_HOSTS = new Set(["127.0.0.1", "localhost", "::1", "[::1]"]);
const LOCAL_COMPANION_ORIGIN = "http://127.0.0.1:8500";

export const dynamic = "force-dynamic";

function viewerOnlyStream(reason: string, status = 200) {
  const body = `event: graph_snapshot\ndata: ${JSON.stringify({
    state: "viewer_only",
    reason,
    nodes: [],
    edges: [],
    stream: "sse_v1",
    cumulative_learning_seconds: 0,
    ghost_shell: {
      system_state: "GHOST SHELL VIEWER",
      logs: [
        "[VIEWER] 배포본 관제 화면이 로컬 FastAPI 연결을 기다립니다.",
        "[VIEWER] 실제 그래프 스트림은 로컬 companion API 연결 시 활성화됩니다.",
      ],
    },
  })}\n\n`;
  return new Response(body, {
    status,
    headers: {
      "Cache-Control": "no-cache, no-transform",
      "Content-Type": "text/event-stream; charset=utf-8",
    },
  });
}

function backendFromRequest(request: NextRequest) {
  const requested = request.nextUrl.searchParams.get("backend") ?? request.nextUrl.searchParams.get("api");
  if (!requested) return backendBaseUrl() || LOCAL_COMPANION_ORIGIN;
  try {
    const url = new URL(requested);
    if (!["http:", "https:"].includes(url.protocol)) return backendBaseUrl() || LOCAL_COMPANION_ORIGIN;
    if (!LOCAL_GRAPH_HOSTS.has(url.hostname)) return backendBaseUrl() || LOCAL_COMPANION_ORIGIN;
    return url.origin;
  } catch {
    return backendBaseUrl() || LOCAL_COMPANION_ORIGIN;
  }
}

export async function GET(request: NextRequest) {
  const backend = backendFromRequest(request);
  if (!backend) {
    return viewerOnlyStream("backend_unconfigured");
  }

  const limit = request.nextUrl.searchParams.get("limit") ?? "5000";
  const eventUrl = `${backend}/api/graph/events?limit=${encodeURIComponent(limit)}`;

  if (process.env.VERCEL === "1" && process.env.VERCEL_ENV === "production") {
    return Response.redirect(eventUrl, 307);
  }

  let response: Response;
  try {
    response = await fetch(eventUrl, {
      cache: "no-store",
      headers: { Accept: "text/event-stream" },
    });
  } catch {
    return viewerOnlyStream("local_backend_unreachable");
  }

  if (!response.ok || !response.body) {
    return viewerOnlyStream(`graph_event_proxy_failed_${response.status}`);
  }

  return new Response(response.body, {
    headers: {
      "Cache-Control": "no-cache, no-transform",
      "Connection": "keep-alive",
      "Content-Type": "text/event-stream; charset=utf-8",
      "X-Accel-Buffering": "no",
    },
  });
}
