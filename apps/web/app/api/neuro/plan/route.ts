import { NextResponse } from "next/server";
import { demoNeuroPlan } from "../../_alphaDemo";
import { proxyJson } from "../../_backend";

export async function GET() {
  try {
    const proxied = await proxyJson("/api/neuro/plan");
    if (proxied) {
      return NextResponse.json(proxied.body, { status: proxied.status });
    }
    return NextResponse.json(demoNeuroPlan());
  } catch (error) {
    return NextResponse.json(demoNeuroPlan());
  }
}

export async function POST(request: Request) {
  const body = await request.json().catch(() => ({}));
  try {
    const proxied = await proxyJson("/api/neuro/plan", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    if (proxied) {
      return NextResponse.json(proxied.body, { status: proxied.status });
    }
    return NextResponse.json(demoNeuroPlan(body));
  } catch (error) {
    return NextResponse.json(demoNeuroPlan(body));
  }
}
