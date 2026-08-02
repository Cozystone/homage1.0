import { NextResponse } from "next/server";
import { backendBaseUrl } from "../../_backend";

export async function GET() {
  const baseUrl = backendBaseUrl();
  if (!baseUrl) {
    return NextResponse.json({ folded_state_field: null, render_fold_scene: false, reason: "local_backend_unavailable" }, { status: 503 });
  }
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), 10000);
  try {
    const response = await fetch(`${baseUrl}/api/holographic-fold/local`, { cache: "no-store", signal: controller.signal });
    return new Response(response.body, {
      status: response.status,
      headers: {
        "content-type": response.headers.get("content-type") ?? "application/json",
        "cache-control": "no-store",
      },
    });
  } catch (error) {
    return NextResponse.json({ folded_state_field: null, render_fold_scene: false, error: error instanceof Error ? error.message : "fold request failed" }, { status: 504 });
  } finally {
    clearTimeout(timeout);
  }
}
