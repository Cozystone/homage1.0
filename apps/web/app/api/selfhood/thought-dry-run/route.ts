import { NextResponse } from "next/server";
import { proxyJson } from "../../_backend";

const safeThoughtInvariants = {
  proof_only: true,
  external_llm_used: false,
  external_sllm_used: false,
  fish_s2_called: false,
  audio_generated: false,
  generated_audio_persisted: false,
  inner_speech_exposed_to_user: false,
  inner_speech_sent_to_fish: false,
  internal_trace_exposed: false,
  production_store_mutated: false,
  local_brain_write: false,
  candidate_promotion: false,
  real_p2p_used: false,
  real_cloud_upload: false,
  always_listening_enabled: false,
  rule_based_answer_used: false,
  template_free_surface: true,
  generation_basis: "local_corpus_construction_transition_model",
};

function unavailableThoughtDryRun(language: string) {
  const ko = language.startsWith("ko");
  return {
    state: "unavailable",
    result_id: `thought_dashboard_unavailable_${Date.now()}`,
    input_id: "dashboard_text",
    intent: "conversation_engine_unavailable",
    emotion_tag: "",
    final_tagged_text: "",
    message: ko
      ? "로컬 대화 엔진 연결을 확인하는 중입니다. 텍스트 입력은 유지되며, 기억이나 지식은 변경되지 않습니다."
      : "The local conversation engine is being checked. Text input remains available, and no memory or knowledge is changed.",
    orb_state: "blocked",
    safety: safeThoughtInvariants,
    fish_request: {
      speaker: "fish_s2",
      mode: "not_requested",
      text: "",
      language: ko ? "ko-KR" : "en-US",
      fish_s2_called: false,
      audio_generated: false,
      generated_audio_persisted: false,
      requires_user_review: false,
    },
  };
}

export async function POST(request: Request) {
  const body = await request.text();
  try {
    const proxied = await proxyJson("/api/selfhood/thought-dry-run", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body,
    });
    if (proxied) return NextResponse.json(proxied.body, { status: proxied.status });
  } catch {
    // The product surface must not invent a fallback answer when the API companion is absent.
  }

  try {
    const parsed = JSON.parse(body || "{}");
    const text = String(parsed.text ?? "");
    const language = String(parsed.language ?? "ko");
    if (!text.trim()) {
      return NextResponse.json({ error: "text is required" }, { status: 400 });
    }
    return NextResponse.json(unavailableThoughtDryRun(language), { status: 503 });
  } catch {
    return NextResponse.json({ error: "invalid request" }, { status: 400 });
  }
}
