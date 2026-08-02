import { NextResponse } from "next/server";
import { demoOntologyRun } from "../../_alphaDemo";
import { proxyJson } from "../../_backend";

export async function POST() {
  try {
    const proxied = await proxyJson("/api/ontology/run", { method: "POST" });
    if (proxied) return NextResponse.json(proxied.body, { status: proxied.status });
    return NextResponse.json(demoOntologyRun());
  } catch {
    return NextResponse.json(demoOntologyRun());
  }
}
