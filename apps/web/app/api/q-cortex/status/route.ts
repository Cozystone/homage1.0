import { NextResponse } from "next/server";
import { proxyJson } from "../../_backend";

export async function GET() {
  const proxied = await proxyJson("/api/q-cortex/status");
  return NextResponse.json(
    proxied?.body ?? {
      state: "unavailable",
      architecture: "Q-Cortex Optimizer",
      label: "Quantum-inspired Cortex Routing",
      quantum_inspired_only: true,
      real_quantum_hardware_used: false,
      external_llm_used: false,
      external_sllm_used: false,
      local_brain_write: false,
      final_answer_generation_claimed: false,
    },
    { status: proxied?.status ?? 503 },
  );
}
