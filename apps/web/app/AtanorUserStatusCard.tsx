"use client";

import { FormEvent, useCallback, useEffect, useMemo, useRef, useState } from "react";
import type { CSSProperties } from "react";
import { Mic, Send } from "lucide-react";
import HologramVoiceOrb, { HologramVoiceOrbState, ORB_BENCHMARK_MAX_PARTICLES } from "./HologramVoiceOrb";
import SplatraField, { SplatraHandle } from "./SplatraField";
import { isDemo } from "./lib/profile";
import { parse3DIntent } from "./splatraIntent";
import AnswerExperimentSurface, { AnswerVisual } from "./AnswerExperimentSurface";
import SplatraImaginationField from "./SplatraImaginationField";
import PhaseHolographicFoldScene, { type FoldScene } from "./PhaseHolographicFoldScene";

type Language = "en" | "ko";
type StageLayout = "conversation" | "scene_focus";
type TextAnchor = "auto" | "upper_left" | "lower_left" | "upper_right" | "lower_center";

type AtanorUserStatusCardProps = {
  language: Language;
  onMessageSubmit?: (message: string) => boolean;
};

type ConversationContextTurn = {
  role: "user" | "assistant";
  text: string;
};

type GraftedNode = {
  id?: string;
  label?: string;
  kind?: string;
  source_url?: string;
  definition?: string;
};

type VoiceOutput = {
  audio_available?: boolean;
  audio_url?: string | null;
  audio_mime?: string | null;
  audio_duration_ms?: number | null;
  estimated_duration_ms?: number | null;
  error_reason?: string | null;
  fallback_prosody_applied?: boolean;
  fallback_prosody_source?: string | null;
  local_tts_rate?: number | null;
  local_tts_volume?: number | null;
  neural_emotion_voice_controls?: {
    emotion_hint?: string | null;
    tts_tag?: string | null;
    speed?: number | null;
    energy?: number | null;
    fallback_delivery?: string | null;
    fallback_sentence_gap_ms?: number | null;
  } | null;
  speech_sync_source?: string | null;
  user_message?: string | null;
  text_fallback?: boolean;
};

type VoiceWaveStyle = CSSProperties & {
  "--h": string;
  "--i": number;
};

type RectLike = {
  bottom: number;
  height: number;
  left: number;
  right: number;
  top: number;
  width: number;
};

type TextLayoutEstimate = {
  height: number;
  lineCount: number;
  width: number;
};

type DashboardLayoutMetrics = {
  speechMaxVw: number;
  speechRightVw: number;
  speechBottomVh: number;
  speechUpperLeftTopVh: number;
  speechUpperRightTopVh: number;
  speechLowerLeftBottomVh: number;
  speechLowerCenterBottomVh: number;
  selfNarrationTopVh: number;
  selfNarrationRightVw: number;
  selfNarrationMaxVw: number;
  fieldOpacity: number;
};

type LayoutTelemetry = {
  blockers: number;
  collisionState: string;
  offscreen: number;
  orbOffscreen: number;
  orbOverlap: number;
  overlap: number;
};

type TextPlacementDecision = {
  basis: string;
  blockerCount: number;
  cartridgeFootprintAvoided: boolean;
  interactiveBboxFootprintAvoided: boolean;
  model: string;
  particleText: boolean;
  score: number;
  sceneFootprintAvoided: boolean;
  selfNarrationAnchor: TextAnchor;
  speechAnchor: TextAnchor;
  textRendering: string;
};

type SceneBeatOp = "spawn_object" | "morph" | "move" | "focus_camera" | "label" | "despawn";

type SceneDirective = {
  directive_owner?: string;
  basis?: string;
  narrative_function?: string;
  stage_instruction?: string;
  visual_affordance?: string;
  speech_sync?: string;
  text_rendering?: string;
  particle_text?: boolean;
  topic_scene_templates?: boolean;
};

type SceneEvidence = {
  evidence_owner?: string;
  source_type?: string;
  source_fact_hash?: string;
  prompt_span?: string;
  narration_span?: string;
  semantic_role?: string;
  visual_affordance?: string;
  spatial_relation?: string;
  motion_basis?: string;
  motion_source_prompt?: string;
  motion_target_prompt?: string;
  particle_behavior?: string;
  text_rendering?: string;
  particle_text?: boolean;
  topic_scene_templates?: boolean;
  renderer_may_infer_topic?: boolean;
};

type SceneSelfState = {
  state_owner?: string;
  state_basis?: string;
  self_body_identity?: string;
  particle_field_pressure?: number;
  self_body_pressure?: number;
  text_clearance_pressure?: number;
  composer_clearance_pressure?: number;
  topic_scene_templates?: boolean;
  renderer_may_infer_topic?: boolean;
};

type SceneAvoidanceMap = {
  basis?: string;
  map_owner?: string;
  orb_reserved_lane?: string;
  composer_reserved_lane?: string;
  text_safe_lanes?: string[];
  self_narration_preferred_lane?: string;
  dom_text_only?: boolean;
  particle_text?: boolean;
  topic_scene_templates?: boolean;
  scene_footprint?: {
    min_x?: number;
    max_x?: number;
    min_y?: number;
    max_y?: number;
  };
};

type SceneChoreographyPayload = {
  stage_layout?: "conversation" | "scene_focus";
  orb_anchor?: "center" | "lower_right";
  text_anchor?: TextAnchor;
  layout_intent?: "conversation" | "balanced_scene" | "wide_particle_stage";
  scene_extent?: {
    beat_count?: number;
    motion_count?: number;
    spread_x?: number;
    spread_y?: number;
    min_x?: number;
    max_x?: number;
    min_y?: number;
    max_y?: number;
  };
  scene_self_state?: SceneSelfState;
  dashboard_layout?: {
    planning_basis?: string;
    stage_pressure?: number;
    orb?: {
      anchor?: "center" | "lower_right";
      size_vmin?: number;
      min_px?: number;
      max_px?: number;
      right_vw?: number;
      bottom_vh?: number;
    };
    speech?: {
      anchor?: TextAnchor;
      max_vw?: number;
      right_vw?: number;
      bottom_vh?: number;
      upper_left_top_vh?: number;
      upper_right_top_vh?: number;
      lower_left_bottom_vh?: number;
      lower_center_bottom_vh?: number;
    };
    self_narration?: {
      anchor?: TextAnchor;
      top_vh?: number;
      right_vw?: number;
      max_vw?: number;
    };
    scene?: {
      field_opacity?: number;
      central_scale?: number;
    };
    stage_safe_region?: {
      primary?: string;
      orb_exclusion?: string;
      text_exclusion?: string;
      composer_exclusion?: string;
      scale_strategy?: string;
      footprint?: {
        basis?: string;
        min_x?: number;
        max_x?: number;
        min_y?: number;
        max_y?: number;
        block_text?: boolean;
      };
    };
    avoidance_map?: SceneAvoidanceMap;
    agent_layout_decision?: {
      decision_owner?: string;
      decision_basis?: string;
      scene_geometry_inputs?: Record<string, unknown>;
      topic_scene_templates?: boolean;
      agent_action?: string;
      orb_movement?: string;
      orb_identity?: string;
      layout_autonomy?: string;
      text_strategy?: string;
      text_rendering?: string;
      scene_region?: string;
      particle_stage_strategy?: string;
      particle_space?: string;
      generated_visual_elements?: string;
      line_rendering?: string;
      flow_motion_reference?: string;
      text_exception?: string;
      orb_self_body_yield?: string;
      orb_yield_strength?: number;
      particle_recomposition_mode?: string;
      avoid_regions?: string[];
      content_source?: string;
      renderer_may_infer_topic?: boolean;
      scene_self_state?: SceneSelfState;
      avoidance_map?: SceneAvoidanceMap;
      text_safe_lanes?: string[];
    };
  };
  primary_surface?: string;
  layout_timeline?: Array<{
    t_start?: number;
    duration?: number;
    action?: string;
    decision_owner?: string;
    decision_basis?: string;
    beat_index?: number;
    scene_group_id?: string;
    object_id?: string;
    orb_anchor?: string;
    orb_movement?: string;
    orb_identity?: string;
    text_anchor?: TextAnchor;
    text_anchor_basis?: string;
    text_anchor_points?: number;
    active_layout_pressure?: number;
    active_bbox?: {
      basis?: string;
      min_x?: number;
      max_x?: number;
      min_y?: number;
      max_y?: number;
    };
    active_regions?: string[];
    orb_scale_hint?: string;
    text_safe_region?: TextAnchor;
    self_narration_anchor?: TextAnchor;
    text_rendering?: string;
    text_strategy?: string;
    stage_region?: string;
    particle_stage_strategy?: string;
    particle_space?: string;
    generated_visual_elements?: string;
    line_rendering?: string;
    flow_motion_reference?: string;
    text_exception?: string;
    orb_self_body_yield?: string;
    particle_recomposition_mode?: string;
    layout_autonomy?: string;
    particle_behavior?: string;
  }>;
  speech_timeline?: Array<{
    beat_index?: number;
    object_id?: string;
    scene_group_id?: string;
    scene_group_role?: string;
    text?: string;
    text_source?: string;
    speech_cue_basis?: string;
    t_start?: number;
    duration?: number;
    particle_behavior?: string;
    scene_directive?: SceneDirective;
    scene_evidence?: SceneEvidence;
    physics_hint?: Record<string, any>;
    motion_path?: Record<string, any>;
    semantic_role?: string;
    visual_affordance?: string;
  }>;
  agent_scene_decisions?: Array<Record<string, unknown>>;
  particle_operation_intents?: Array<Record<string, unknown>>;
  beats?: Array<{
    op?: SceneBeatOp;
    archetype?: "orb" | "tower" | "tree" | "creature" | "circuit" | "city_block" | "constellation" | "machine_core" | "abstract_memory_cloud";
    narration?: string;
    prompt?: string;
    object_id?: string;
    semantic_role?: string;
    visual_affordance?: string;
    spatial_relation?: string;
    particle_behavior?: string;
    physics_hint?: Record<string, any>;
    source_fact?: string;
    speech_cue?: boolean;
    speech_cue_basis?: string;
    scene_directive?: SceneDirective;
    scene_evidence?: SceneEvidence;
    scene_group_id?: string;
    scene_group_role?: string;
    t_start?: number;
    duration?: number;
    position?: number[];
    motion_path?: {
      from?: number[];
      to?: number[];
      basis?: string;
      source_prompt?: string;
      target_prompt?: string;
    };
    camera?: Record<string, any>;
  }>;
} | null;

type SceneNarrationBeat = {
  beatIndex: number;
  duration: number;
  tStart: number;
  text: string;
};

type SplatraCommandSequencePayload = {
  scene_actions?: Array<{ op?: string; args?: Record<string, unknown> }>;
  candidate_cartridge_requests?: Array<{
    cartridge_format?: string;
    execution?: {
      execute_now?: boolean;
      raw_buffer_in_agent_context?: boolean;
    };
  }>;
  splatra_contract?: {
    side_channel?: string;
    agent_context_payload?: string;
    raw_buffers_in_agent_context?: boolean;
    topic_scene_templates?: boolean;
    renderer_may_infer_topic?: boolean;
  };
  hot_swap_policy?: {
    mode?: string;
    viewer_side_channel?: string;
    mutation_performed?: boolean;
  };
  particle_motion_policy?: {
    field_model?: string;
    agent_control?: string;
    text_rendering?: string;
  };
} | null;

type SplatraInteractiveSceneAnalysisPayload = {
  interactive_scene?: boolean;
  object_count?: number;
  analyzer_contract?: {
    raw_splat_inference?: boolean;
    object_detection_claim?: string;
    interactive_scene_metadata?: boolean;
    persistent_3d_bounding_boxes?: boolean;
    topic_scene_templates?: boolean;
    renderer_may_infer_topic?: boolean;
    particle_text?: boolean;
    text_rendering?: string;
  };
  objects?: Array<{
    object_id?: string;
    object_track_id?: string;
    label?: string;
    semantic_role?: string;
    visual_affordance?: string;
    raw_splat_inference?: boolean;
    bounding_box?: {
      min?: number[];
      max?: number[];
      center?: number[];
      extent?: number[];
      basis?: string;
    };
    interactions?: Array<Record<string, unknown>>;
    evidence_refs?: Array<Record<string, unknown>>;
  }>;
  spatial_index?: Array<Record<string, unknown>>;
  safety_flags?: Record<string, boolean>;
} | null;

type SplatraCartridgeQueuePayload = {
  status?: string;
  execution_mode?: string;
  job_count?: number;
  side_channel?: string;
  sidecar_status?: string;
  sidecar_configured?: boolean;
  sidecar_dispatch?: {
    status?: string;
    configured?: boolean;
    job_count?: number;
    external_splatra_called?: boolean;
    raw_buffer_in_agent_context?: boolean;
    raw_cartridge_fetched?: boolean;
    mutation_performed?: boolean;
  };
  external_splatra_called?: boolean;
  raw_buffer_in_agent_context?: boolean;
  mutation_performed?: boolean;
  topic_scene_templates?: boolean;
  renderer_may_infer_topic?: boolean;
  particle_text?: boolean;
} | null;

type SplatraScenePolicy = {
  scene_content_source?: string;
  scene_authoring_basis?: string | null;
  visual_affordance_basis?: string | null;
  layout_decision_basis?: string | null;
  topic_scene_templates?: boolean;
  renderer_may_infer_topic?: boolean;
  particle_text?: boolean;
  text_rendering?: string;
  orb_identity?: string;
  verified_evidence_required_for_general_knowledge?: boolean;
};

function stripEmotionTag(text: string) {
  return text.replace(/^\[[^\]]+\]\s*/, "").trim();
}

function firstSpeechBeat(text: string) {
  // A knowledge answer should be readable in full, not clipped to one short
  // clause. Show the whole answer when it is reasonably short; otherwise cut at
  // a sentence boundary near the limit so the user still reads complete thoughts.
  const clean = stripEmotionTag(text);
  if (clean.length <= 260) return clean;
  const boundary = Math.max(clean.lastIndexOf(". ", 260), clean.lastIndexOf("\ub2e4. ", 260));
  if (boundary > 90) return clean.slice(0, boundary + 1);
  return `${clean.slice(0, 256).trim()}\u2026`;
}

function estimatedSpeechDurationMs(text: string, voiceOutput?: VoiceOutput) {
  const fromPayload = Number(voiceOutput?.audio_duration_ms ?? voiceOutput?.estimated_duration_ms ?? 0);
  if (Number.isFinite(fromPayload) && fromPayload > 0) return clampNumber(fromPayload, 900, 48000);
  const compact = stripEmotionTag(text).replace(/\s+/g, "");
  return clampNumber(compact.length * 112 + 520, 900, 48000);
}

function typingStepForSpeech(text: string, durationMs: number) {
  const clean = stripEmotionTag(text);
  const target = durationMs / Math.max(1, clean.length);
  return clampNumber(target, 22, 220);
}

function withAudioTimeout<T>(promise: Promise<T>, timeoutMs = 700): Promise<T> {
  return Promise.race([
    promise,
    new Promise<T>((_, reject) => {
      window.setTimeout(() => reject(new Error("audio_context_timeout")), timeoutMs);
    }),
  ]);
}

function useTypewriterText(text: string, stepMs = 22) {
  const [visible, setVisible] = useState("");

  useEffect(() => {
    if (!text) {
      setVisible("");
      return undefined;
    }
    let index = 0;
    setVisible("");
    const timer = window.setInterval(() => {
      index += 1;
      setVisible(text.slice(0, index));
      if (index >= text.length) {
        window.clearInterval(timer);
      }
    }, stepMs);
    return () => window.clearInterval(timer);
  }, [text, stepMs]);

  return visible;
}

function isAsmConversationPayload(payload: Record<string, any>) {
  const result = payload?.result ?? {};
  const engine = result?.answer_engine ?? {};
  const generationBasis = String(engine.generation_basis ?? "");
  const isAllowedLocalConversation =
    generationBasis === "local_corpus_construction_transition_model"
    || generationBasis === "semantic_grounded_conversation_router_v0"
    || generationBasis === "semantic_cloud_graph_surface_brain_v0"
    || generationBasis === "base_brain_seed_graph_surface_v0";
  return (
    isAllowedLocalConversation
    && engine.external_llm === false
    && engine.external_sllm === false
    && engine.external_llm_used === false
    && engine.external_sllm_used === false
    && engine.rule_based_answer_used === false
    && engine.internal_trace_exposed === false
    && engine.local_brain_write === false
    && engine.production_store_mutated === false
    && engine.candidate_promotion === false
  );
}

function shouldRequestWebGrounding(input: string) {
  const q = input.trim().toLowerCase();
  const compact = q.replace(/[\s!?.,~]+/g, "");
  if (!compact) return false;
  if (["안녕", "안녕하세요", "하이", "hi", "hello", "hey", "thanks", "thankyou"].includes(compact)) {
    return false;
  }
  if (/(splatra|스플라트라|구슬|홀로그램|음성|목소리|fish|selfhood|자기 모델|내적 언어)/i.test(input)) {
    return false;
  }
  // Questions about ATANOR ITSELF are answered from self memory, never the web —
  // but only when there's an explicit 2nd-person reference, so "아인슈타인이 누구야"
  // (3rd-person entity lookup) still searches. The pronoun is mandatory here.
  if (/((너|넌|네|너의|니|니가|네가|당신|당신의)\s*(이름|누구|누군지|뭐|뭐야))|자기소개|소개\s*해|who\s+are\s+you|your\s+name|what'?s\s+your\s+name/i.test(input)) {
    return false;
  }
  // Dashboard control ("창 닫아", "이거 치워") is an instruction to the orb, not a
  // search query.
  if (/(창|탭|페이지|문서|화면|window|tab|page).{0,6}(닫|꺼|치워|없애|close|hide|dismiss)|^\s*(닫아|닫아줘|꺼줘|치워|close|닫기)\s*$/i.test(input)) {
    return false;
  }
  return /검색|찾아|최신|최근|오늘|뉴스|현재|인터넷|웹|누구|무엇|뭐야|왜|어떻게|설명|법칙|원리|정의|근거|확인|search|look up|latest|recent|today|news|current|who|what|why|how|explain|law|principle|definition/i.test(input);
}

function cleanSafeStatusLine(language: Language) {
  return language === "ko"
    ? "\uB85C\uCEEC \uB300\uD654 \uC5D4\uC9C4\uC744 \uD655\uC778\uD558\uB294 \uC911\uC785\uB2C8\uB2E4."
    : "The local conversation engine is being checked.";
}

function cleanVoiceUnavailableLine(language: Language) {
  return language === "ko"
    ? "\uC74C\uC131 \uC5D4\uC9C4\uC740 \uC544\uC9C1 \uC900\uBE44 \uC911\uC785\uB2C8\uB2E4. \uD14D\uC2A4\uD2B8 \uC751\uB2F5\uC740 \uACC4\uC18D \uC0AC\uC6A9\uD560 \uC218 \uC788\uC2B5\uB2C8\uB2E4."
    : "The voice engine is not installed yet. Text replies remain available.";
}

function cleanVoiceFailedLine(language: Language) {
  return language === "ko"
    ? "\uC74C\uC131 \uD569\uC131 \uC911 \uC624\uB958\uAC00 \uBC1C\uC0DD\uD588\uC2B5\uB2C8\uB2E4. \uD14D\uC2A4\uD2B8 \uC751\uB2F5\uC73C\uB85C \uACC4\uC18D\uD569\uB2C8\uB2E4."
    : "Voice synthesis failed. Continuing with text replies.";
}

function requestedStageLayout(payload: Record<string, any>): StageLayout {
  const result = payload?.result ?? {};
  const visualPlan = result?.splatra_scene_plan ?? result?.visual_scene_plan ?? result?.scene_choreography ?? null;
  if (!visualPlan || typeof visualPlan !== "object") return "conversation";
  if (visualPlan.stage_layout === "scene_focus") return "scene_focus";
  if (visualPlan.orb_anchor === "lower_right") return "scene_focus";
  if (visualPlan.primary_surface === "splatra_stage") return "scene_focus";
  return "conversation";
}

function requestedSceneChoreography(payload: Record<string, any>): SceneChoreographyPayload {
  const result = payload?.result ?? {};
  const visualPlan = result?.splatra_scene_plan ?? result?.visual_scene_plan ?? result?.scene_choreography ?? null;
  if (!visualPlan || typeof visualPlan !== "object") return null;
  return visualPlan as SceneChoreographyPayload;
}

function defaultSplatraScenePolicy(): SplatraScenePolicy {
  return {
    scene_content_source: "none",
    scene_authoring_basis: null,
    visual_affordance_basis: null,
    layout_decision_basis: null,
    topic_scene_templates: false,
    renderer_may_infer_topic: false,
    particle_text: false,
    text_rendering: "dom_text_not_particles",
    orb_identity: "atanor_primary_self_body",
    verified_evidence_required_for_general_knowledge: false,
  };
}

function requestedSplatraScenePolicy(payload: Record<string, any>): SplatraScenePolicy {
  const result = payload?.result ?? {};
  const policy = result?.splatra_scene_policy;
  if (!policy || typeof policy !== "object") return defaultSplatraScenePolicy();
  return {
    ...defaultSplatraScenePolicy(),
    scene_content_source: typeof policy.scene_content_source === "string" ? policy.scene_content_source : "none",
    scene_authoring_basis: typeof policy.scene_authoring_basis === "string" ? policy.scene_authoring_basis : null,
    visual_affordance_basis: typeof policy.visual_affordance_basis === "string" ? policy.visual_affordance_basis : null,
    layout_decision_basis: typeof policy.layout_decision_basis === "string" ? policy.layout_decision_basis : null,
    topic_scene_templates: policy.topic_scene_templates === true,
    renderer_may_infer_topic: policy.renderer_may_infer_topic === true,
    particle_text: policy.particle_text === true,
    text_rendering: typeof policy.text_rendering === "string" ? policy.text_rendering : "dom_text_not_particles",
    orb_identity: typeof policy.orb_identity === "string" ? policy.orb_identity : "atanor_primary_self_body",
    verified_evidence_required_for_general_knowledge: policy.verified_evidence_required_for_general_knowledge === true,
  };
}

function requestedSplatraCommandSequence(payload: Record<string, any>): SplatraCommandSequencePayload {
  const result = payload?.result ?? {};
  const sequence = result?.splatra_command_sequence;
  if (!sequence || typeof sequence !== "object") return null;
  return sequence as SplatraCommandSequencePayload;
}

function requestedSplatraInteractiveSceneAnalysis(payload: Record<string, any>): SplatraInteractiveSceneAnalysisPayload {
  const result = payload?.result ?? {};
  const analysis = result?.splatra_interactive_scene_analysis;
  if (!analysis || typeof analysis !== "object") return null;
  return analysis as SplatraInteractiveSceneAnalysisPayload;
}

function requestedSplatraCartridgeQueue(payload: Record<string, any>): SplatraCartridgeQueuePayload {
  const result = payload?.result ?? {};
  const queue = result?.splatra_cartridge_queue;
  if (!queue || typeof queue !== "object") return null;
  return queue as SplatraCartridgeQueuePayload;
}

function particleOperationForSceneBeat(beat: { op?: SceneBeatOp; motion_path?: unknown } | undefined) {
  if (beat?.op === "move" || beat?.motion_path) return "animate_particle_motion_path";
  if (beat?.op === "focus_camera") return "focus_particle_cluster";
  if (beat?.op === "morph") return "recompose_particle_cluster";
  if (beat?.op === "despawn") return "disperse_particle_cluster";
  if (beat?.op) return "assemble_particle_cluster";
  return "none";
}

function requestedTextAnchor(scenePlan: SceneChoreographyPayload): TextAnchor {
  const value = scenePlan?.text_anchor;
  if (value === "upper_left" || value === "lower_left" || value === "upper_right" || value === "lower_center") {
    return value;
  }
  return "auto";
}

function requestedLayoutIntent(scenePlan: SceneChoreographyPayload) {
  const value = scenePlan?.layout_intent;
  if (value === "wide_particle_stage" || value === "balanced_scene") return value;
  // The product renderer does not infer scene ambition from client-side
  // heuristics. Orb yielding/wide-stage decisions must come from the
  // verified scene choreography payload.
  return "balanced_scene";
}

function requestedLayoutBasis(scenePlan: SceneChoreographyPayload, stageLayout: StageLayout) {
  const basis = scenePlan?.dashboard_layout?.planning_basis;
  if (typeof basis === "string" && basis) return basis;
  if (stageLayout === "scene_focus") return "agent_layout_missing_safe_default";
  return "none";
}

function requestedLayoutDecision(scenePlan: SceneChoreographyPayload, stageLayout: StageLayout) {
  const decision = scenePlan?.dashboard_layout?.agent_layout_decision;
  const action = typeof decision?.agent_action === "string" ? decision.agent_action : "";
  const textRendering = typeof decision?.text_rendering === "string" ? decision.text_rendering : "";
  if (action && textRendering) return `${action}:${textRendering}`;
  if (action) return action;
  if (textRendering) return textRendering;
  if (stageLayout === "scene_focus") return "agent_layout_missing:dom_text_not_particles";
  return "none";
}

function activeLayoutState(scenePlan: SceneChoreographyPayload, stageLayout: StageLayout, activeBeatIndex: number) {
  const timeline = Array.isArray(scenePlan?.layout_timeline) ? scenePlan?.layout_timeline ?? [] : [];
  const active = timeline.find((item) => Number(item.beat_index) === activeBeatIndex && typeof item.action === "string");
  const base = timeline.find((item) => item.beat_index === undefined && typeof item.action === "string");
  const planAction = typeof scenePlan?.dashboard_layout?.agent_layout_decision?.agent_action === "string"
    ? scenePlan.dashboard_layout.agent_layout_decision.agent_action
    : "";
  const fallbackAction = stageLayout === "scene_focus" && planAction ? planAction : "keep_orb_primary";
  const item = active ?? base ?? {};
  const layoutBasis = requestedLayoutBasis(scenePlan, stageLayout);
  const legacySceneChoreographyOwner = stageLayout === "scene_focus" && layoutBasis === "scene_geometry_extent"
    ? "cgsr_scene_choreography_agent"
    : stageLayout === "scene_focus" ? "agent_layout_missing_safe_default" : "conversation_default";
  return {
    action: String(item.action ?? fallbackAction),
    owner: String(item.decision_owner ?? scenePlan?.dashboard_layout?.agent_layout_decision?.decision_owner ?? legacySceneChoreographyOwner),
    basis: String(item.decision_basis ?? (stageLayout === "scene_focus" ? layoutBasis : "conversation_default")),
    orbAnchor: String(item.orb_anchor ?? scenePlan?.dashboard_layout?.orb?.anchor ?? (stageLayout === "scene_focus" ? "lower_right" : "center")),
    orbMovement: String(item.orb_movement ?? scenePlan?.dashboard_layout?.agent_layout_decision?.orb_movement ?? (stageLayout === "scene_focus" ? "lower_right_scaled_down" : "center")),
    orbIdentity: String(item.orb_identity ?? scenePlan?.dashboard_layout?.agent_layout_decision?.orb_identity ?? (stageLayout === "scene_focus" ? "atanor_self_body_not_scene_object" : "atanor_primary_self_body")),
    stageRegion: String(item.stage_region ?? scenePlan?.dashboard_layout?.agent_layout_decision?.scene_region ?? (stageLayout === "scene_focus" ? "dashboard_center" : "conversation_center")),
    particleStageStrategy: String(item.particle_stage_strategy ?? scenePlan?.dashboard_layout?.agent_layout_decision?.particle_stage_strategy ?? (stageLayout === "scene_focus" ? "airbend_recompose_particles_inside_safe_region" : "ambient_self_body")),
    particleSpace: String(item.particle_space ?? scenePlan?.dashboard_layout?.agent_layout_decision?.particle_space ?? (stageLayout === "scene_focus" ? "uncovered_dashboard_field_minus_sidebar_composer_and_text" : "orb_local_field")),
    generatedVisualElements: String(item.generated_visual_elements ?? scenePlan?.dashboard_layout?.agent_layout_decision?.generated_visual_elements ?? (stageLayout === "scene_focus" ? "particle_points_only" : "particle_points_only")),
    lineRendering: String(item.line_rendering ?? scenePlan?.dashboard_layout?.agent_layout_decision?.line_rendering ?? "particle_segments_not_canvas_strokes"),
    flowMotionReference: String(item.flow_motion_reference ?? scenePlan?.dashboard_layout?.agent_layout_decision?.flow_motion_reference ?? "codepen_magnetic_swarm_noise_decay_reference"),
    textException: String(item.text_exception ?? scenePlan?.dashboard_layout?.agent_layout_decision?.text_exception ?? "dom_text_measured_layout_only"),
    orbSelfBodyYield: String(item.orb_self_body_yield ?? scenePlan?.dashboard_layout?.agent_layout_decision?.orb_self_body_yield ?? (stageLayout === "scene_focus" ? "orb_moves_and_scales_to_clear_verified_particle_scene" : "none")),
    particleRecompositionMode: String(item.particle_recomposition_mode ?? scenePlan?.dashboard_layout?.agent_layout_decision?.particle_recomposition_mode ?? (stageLayout === "scene_focus" ? "agent_airbend_recompose_verified_beats" : "ambient_orb_particles")),
    layoutAutonomy: String(item.layout_autonomy ?? scenePlan?.dashboard_layout?.agent_layout_decision?.layout_autonomy ?? (stageLayout === "scene_focus" ? "agent_authored_from_verified_scene_geometry_and_client_feedback" : "conversation_default")),
    textAnchor: coerceTextAnchor(item.text_anchor, requestedTextAnchor(scenePlan)),
    textAnchorBasis: String(item.text_anchor_basis ?? scenePlan?.dashboard_layout?.agent_layout_decision?.text_strategy ?? (stageLayout === "scene_focus" ? "verified_scene_geometry" : "conversation_default")),
    textAnchorPoints: Number.isFinite(Number(item.text_anchor_points)) ? Number(item.text_anchor_points) : 0,
    activeLayoutPressure: clampNumber(finiteNumber(item.active_layout_pressure, 0), 0, 1),
    activeBboxBasis: String(item.active_bbox?.basis ?? "none"),
    activeBboxMinX: finiteNumber(item.active_bbox?.min_x, 0),
    activeBboxMaxX: finiteNumber(item.active_bbox?.max_x, 0),
    activeBboxMinY: finiteNumber(item.active_bbox?.min_y, 0),
    activeBboxMaxY: finiteNumber(item.active_bbox?.max_y, 0),
    activeRegions: Array.isArray(item.active_regions) ? item.active_regions.join(",") : "none",
    orbScaleHint: String(item.orb_scale_hint ?? "none"),
    textSafeRegion: coerceTextAnchor(item.text_safe_region, item.text_anchor ?? requestedTextAnchor(scenePlan)),
    selfNarrationAnchor: coerceTextAnchor(item.self_narration_anchor, scenePlan?.dashboard_layout?.self_narration?.anchor ?? "upper_right"),
    textRendering: String(item.text_rendering ?? scenePlan?.dashboard_layout?.agent_layout_decision?.text_rendering ?? "dom_text_not_particles"),
    avoidanceMapBasis: String(scenePlan?.dashboard_layout?.avoidance_map?.basis ?? scenePlan?.dashboard_layout?.agent_layout_decision?.avoidance_map?.basis ?? "none"),
    avoidanceTextSafeLanes: Array.isArray(scenePlan?.dashboard_layout?.avoidance_map?.text_safe_lanes)
      ? scenePlan?.dashboard_layout?.avoidance_map?.text_safe_lanes.join(",")
      : Array.isArray(scenePlan?.dashboard_layout?.agent_layout_decision?.text_safe_lanes)
        ? scenePlan?.dashboard_layout?.agent_layout_decision?.text_safe_lanes.join(",")
        : "none",
    avoidanceSceneFootprint: scenePlan?.dashboard_layout?.avoidance_map?.scene_footprint
      ?? scenePlan?.dashboard_layout?.agent_layout_decision?.avoidance_map?.scene_footprint
      ?? null,
  };
}

function coerceTextAnchor(value: unknown, fallback: unknown): TextAnchor {
  const candidate = String(value || fallback || "lower_left");
  if (candidate === "upper_left" || candidate === "lower_left" || candidate === "upper_right" || candidate === "lower_center") {
    return candidate;
  }
  return "lower_left";
}

function scaleSceneNarrationBeats(beats: SceneNarrationBeat[], targetDurationMs = 0): SceneNarrationBeat[] {
  if (beats.length <= 1 || targetDurationMs <= 0) return beats;
  const rawEnd = beats.reduce((maxEnd, beat) => Math.max(maxEnd, beat.tStart + beat.duration), 0);
  if (rawEnd <= 0) return beats;
  const targetSeconds = targetDurationMs / 1000;
  const scale = clampNumber(targetSeconds / rawEnd, 0.82, 3.4);
  return beats.map((beat, index) => {
    const scaledStart = beat.tStart * scale;
    const nextStart = index < beats.length - 1 ? beats[index + 1].tStart * scale : targetSeconds;
    const visibleWindow = Math.max(beat.duration * scale, nextStart - scaledStart - 0.08);
    return {
      ...beat,
      duration: Math.max(0.55, visibleWindow),
      tStart: scaledStart,
    };
  });
}

function sceneNarrationBeats(scenePlan: SceneChoreographyPayload, targetDurationMs = 0): SceneNarrationBeat[] {
  const beats = Array.isArray(scenePlan?.beats) ? scenePlan?.beats ?? [] : [];
  const timeline = Array.isArray(scenePlan?.speech_timeline) ? scenePlan?.speech_timeline ?? [] : [];
  const timelineBeats = timeline
    .map((item, index) => ({
      beatIndex: Number.isFinite(Number(item.beat_index)) ? Number(item.beat_index) : index,
      duration: Number.isFinite(Number(item.duration)) ? Math.max(0.45, Number(item.duration)) : 1.35,
      tStart: Number.isFinite(Number(item.t_start)) ? Number(item.t_start) : index * 1.35,
      text: stripEmotionTag(String(item.text || "").trim()),
    }))
    .filter((beat) => beat.text.length > 0)
    .filter((beat, index, array) => index === 0 || beat.text !== array[index - 1].text)
    .sort((left, right) => left.tStart - right.tStart);
  if (timelineBeats.length) return scaleSceneNarrationBeats(timelineBeats, targetDurationMs);

  const speechCueBeats = beats.filter((beat) => beat.speech_cue !== false);
  const sourceBeats = speechCueBeats.length ? speechCueBeats : beats;
  return scaleSceneNarrationBeats(sourceBeats
    .map((beat) => {
      const beatIndex = beats.indexOf(beat);
      const index = beatIndex >= 0 ? beatIndex : 0;
      return {
        beatIndex: index,
        duration: Number.isFinite(Number(beat.duration)) ? Math.max(0.45, Number(beat.duration)) : 1.35,
        tStart: Number.isFinite(Number(beat.t_start)) ? Number(beat.t_start) : index * 1.35,
        text: stripEmotionTag(String(beat.narration || beat.prompt || "").trim()),
      };
    })
    .filter((beat) => beat.text.length > 0)
    .filter((beat, index, array) => index === 0 || beat.text !== array[index - 1].text)
    .sort((left, right) => left.tStart - right.tStart), targetDurationMs);
}

function firstSceneNarration(scenePlan: SceneChoreographyPayload) {
  const beats = sceneNarrationBeats(scenePlan);
  return beats[0]?.text ?? "";
}

function splatraLayoutTelemetryOrDefault(stageLayout: StageLayout, layoutTelemetry?: LayoutTelemetry): LayoutTelemetry {
  return layoutTelemetry ?? {
    blockers: 0,
    collisionState: stageLayout === "scene_focus" ? "unmeasured" : "conversation_default",
    offscreen: 0,
    orbOffscreen: 0,
    orbOverlap: 0,
    overlap: 0,
  };
}

function splatraOrbLayoutFeedback(
  scenePlan: SceneChoreographyPayload,
  stageLayout: StageLayout,
  layoutTelemetry?: LayoutTelemetry,
  activeBeatIndex = -1,
) {
  const layoutState = activeLayoutState(scenePlan, stageLayout, activeBeatIndex);
  const telemetry = splatraLayoutTelemetryOrDefault(stageLayout, layoutTelemetry);
  const effectiveMovement = effectiveOrbMovementForTelemetry(stageLayout, layoutState.orbMovement, telemetry);
  return {
    requested_orb_movement: layoutState.orbMovement,
    effective_orb_movement: effectiveMovement,
    orb_feedback: effectiveMovement === layoutState.orbMovement ? "server_scene_geometry" : "client_dom_collision_feedback",
    orb_anchor: layoutState.orbAnchor,
    speech_anchor: layoutState.textAnchor,
    collision_state: telemetry.collisionState,
  };
}

function sceneDirectiveForInnerVoice(scenePlan: SceneChoreographyPayload, activeBeatIndex = -1) {
  const beats = Array.isArray(scenePlan?.beats) ? scenePlan?.beats ?? [] : [];
  const activeBeat = activeBeatIndex >= 0 ? beats[activeBeatIndex] : null;
  const firstDirectiveBeat = beats.find((beat) => beat?.scene_directive);
  const speechDirectiveBeat = Array.isArray(scenePlan?.speech_timeline)
    ? scenePlan?.speech_timeline?.find((beat) => beat?.scene_directive)
    : null;
  const directive = activeBeat?.scene_directive ?? speechDirectiveBeat?.scene_directive ?? firstDirectiveBeat?.scene_directive ?? null;
  return {
    active_scene_directive: String(directive?.stage_instruction ?? "none"),
    active_scene_narrative_function: String(directive?.narrative_function ?? "none"),
    active_scene_directive_owner: String(directive?.directive_owner ?? "none"),
    active_scene_directive_basis: String(directive?.basis ?? "none"),
    active_scene_speech_sync: String(directive?.speech_sync ?? "none"),
    active_scene_text_rendering: String(directive?.text_rendering ?? "dom_text_not_particles"),
    active_scene_particle_text: directive?.particle_text === true,
    active_scene_topic_templates: directive?.topic_scene_templates === true,
    scene_directive_source: activeBeat?.scene_directive
      ? "active_scene_beat"
      : speechDirectiveBeat?.scene_directive
        ? "speech_timeline"
        : firstDirectiveBeat?.scene_directive
          ? "first_scene_beat"
          : "none",
  };
}

function sceneEvidenceForInnerVoice(scenePlan: SceneChoreographyPayload, activeBeatIndex = -1) {
  const beats = Array.isArray(scenePlan?.beats) ? scenePlan?.beats ?? [] : [];
  const activeBeat = activeBeatIndex >= 0 ? beats[activeBeatIndex] : null;
  const firstEvidenceBeat = beats.find((beat) => beat?.scene_evidence);
  const speechEvidenceBeat = Array.isArray(scenePlan?.speech_timeline)
    ? scenePlan?.speech_timeline?.find((beat) => beat?.scene_evidence)
    : null;
  const evidence = activeBeat?.scene_evidence ?? speechEvidenceBeat?.scene_evidence ?? firstEvidenceBeat?.scene_evidence ?? null;
  return {
    active_scene_evidence_owner: String(evidence?.evidence_owner ?? "none"),
    active_scene_evidence_source: String(evidence?.source_type ?? "none"),
    active_scene_evidence_hash: String(evidence?.source_fact_hash ?? "none"),
    active_scene_evidence_prompt_span: String(evidence?.prompt_span ?? ""),
    active_scene_evidence_narration_span: String(evidence?.narration_span ?? ""),
    active_scene_motion_basis: String(evidence?.motion_basis ?? ""),
    active_scene_renderer_may_infer_topic: evidence?.renderer_may_infer_topic === true,
    scene_evidence_source: activeBeat?.scene_evidence
      ? "active_scene_beat"
      : speechEvidenceBeat?.scene_evidence
        ? "speech_timeline"
        : firstEvidenceBeat?.scene_evidence
          ? "first_scene_beat"
          : "none",
  };
}

function splatraStateForInnerVoice(
  scenePlan: SceneChoreographyPayload,
  stageLayout: StageLayout,
  layoutTelemetry?: LayoutTelemetry,
  activeBeatIndex = -1,
  scenePolicy: SplatraScenePolicy = defaultSplatraScenePolicy(),
) {
  const beats = Array.isArray(scenePlan?.beats) ? scenePlan?.beats ?? [] : [];
  const firstBeat = beats[0] ?? {};
  const layoutFeedback = splatraLayoutTelemetryOrDefault(stageLayout, layoutTelemetry);
  const orbLayoutFeedback = splatraOrbLayoutFeedback(scenePlan, stageLayout, layoutFeedback, activeBeatIndex);
  const sceneDirective = sceneDirectiveForInnerVoice(scenePlan, activeBeatIndex);
  const sceneEvidence = sceneEvidenceForInnerVoice(scenePlan, activeBeatIndex);
  return {
    stage_layout: stageLayout,
    layout_intent: requestedLayoutIntent(scenePlan),
    layout_decision: requestedLayoutDecision(scenePlan, stageLayout),
    text_rendering: "dom_text_not_particles",
    scene_policy: {
      scene_content_source: scenePolicy.scene_content_source ?? "none",
      scene_authoring_basis: scenePolicy.scene_authoring_basis ?? "none",
      visual_affordance_basis: scenePolicy.visual_affordance_basis ?? "none",
      layout_decision_basis: scenePolicy.layout_decision_basis ?? "none",
      topic_scene_templates: scenePolicy.topic_scene_templates === true,
      renderer_may_infer_topic: scenePolicy.renderer_may_infer_topic === true,
      particle_text: scenePolicy.particle_text === true,
      text_rendering: scenePolicy.text_rendering ?? "dom_text_not_particles",
      verified_evidence_required_for_general_knowledge: scenePolicy.verified_evidence_required_for_general_knowledge === true,
    },
    ...sceneDirective,
    ...sceneEvidence,
    layout_feedback: {
      collision_state: layoutFeedback.collisionState,
      measured_blockers: layoutFeedback.blockers,
      overlap_px: layoutFeedback.overlap,
      offscreen_px: layoutFeedback.offscreen,
      orb_overlap_px: layoutFeedback.orbOverlap,
      orb_offscreen_px: layoutFeedback.orbOffscreen,
      feedback_basis: "client_dom_scene_collision_telemetry",
    },
    orb_layout_feedback: orbLayoutFeedback,
    beat_count: beats.length,
    motion_count: finiteNumber(scenePlan?.scene_extent?.motion_count, beats.filter((beat) => beat.op === "move" || beat.motion_path).length),
    archetype: String(firstBeat.archetype ?? scenePlan?.primary_surface ?? "particle_scene"),
    visual_affordance: String(firstBeat.visual_affordance ?? ""),
    primary_surface: String(scenePlan?.primary_surface ?? ""),
  };
}

function emitNeuralEmotionEvent(eventType: string, payloadSummary: string) {
  fetch("/api/neural-emotion/events/emit", {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({
      source: "voice_loop",
      event_type: eventType,
      intensity: 0.45,
      payload_summary: payloadSummary,
    }),
  }).catch(() => undefined);
}

function rectsOverlap(left: DOMRect, right: DOMRect, padding = 10) {
  return !(
    left.right + padding < right.left
    || left.left - padding > right.right
    || left.bottom + padding < right.top
    || left.top - padding > right.bottom
  );
}

function clampNumber(value: number, min: number, max: number) {
  return Math.min(max, Math.max(min, value));
}

function cssClampPx(min: number, preferred: number, max: number) {
  return clampNumber(preferred, min, max);
}

let textLayoutMeasureCanvas: HTMLCanvasElement | null = null;
const TEXT_LAYOUT_BASIS = "pretext_inspired_dom_text_canvas_metrics_preallocated_no_particle_text";
const TEXT_LAYOUT_REFERENCE = "chenglou_pretext_prepare_layout_pattern_dom_text_only";

function textLayoutContext() {
  if (typeof document === "undefined") return null;
  textLayoutMeasureCanvas ??= document.createElement("canvas");
  return textLayoutMeasureCanvas.getContext("2d");
}

function graphemeSegments(text: string) {
  const cleaned = text.replace(/\s+/g, " ").trim();
  if (!cleaned) return [];
  if (typeof Intl !== "undefined" && "Segmenter" in Intl) {
    const segmenter = new Intl.Segmenter(undefined, { granularity: "grapheme" });
    return Array.from(segmenter.segment(cleaned), (segment) => segment.segment);
  }
  return Array.from(cleaned);
}

function pretextInspiredTextLayoutSegments(text: string) {
  const cleaned = text.replace(/\s+/g, " ").trim();
  if (!cleaned) return [];
  if (typeof Intl !== "undefined" && "Segmenter" in Intl) {
    const segmenter = new Intl.Segmenter(undefined, { granularity: "word" });
    const words = Array.from(segmenter.segment(cleaned), (segment) => segment.segment);
    if (words.length > 1) return words;
  }
  return graphemeSegments(cleaned);
}

function estimateDomTextLayoutPretextStyle(element: HTMLElement, text: string, maxWidth: number): TextLayoutEstimate {
  const fallbackWidth = clampNumber(maxWidth, 180, 620);
  const segments = pretextInspiredTextLayoutSegments(text);
  if (!segments.length) {
    const current = element.getBoundingClientRect();
    return {
      height: Math.max(24, current.height || 24),
      lineCount: 1,
      width: Math.max(120, Math.min(fallbackWidth, current.width || fallbackWidth * 0.68)),
    };
  }
  const context = textLayoutContext();
  const style = window.getComputedStyle(element);
  const fontSize = Number.parseFloat(style.fontSize || "16") || 16;
  const lineHeightRaw = Number.parseFloat(style.lineHeight || "");
  const lineHeight = Number.isFinite(lineHeightRaw) ? lineHeightRaw : fontSize * 1.5;
  const font = `${style.fontWeight || "650"} ${style.fontSize || "16px"} ${style.fontFamily || "Helvetica, Arial, sans-serif"}`;
  const measure = (value: string) => {
    if (!context) return value.length * fontSize * 0.56;
    context.font = font;
    return context.measureText(value).width;
  };

  const maxLineWidth = clampNumber(maxWidth, 180, Math.max(180, window.innerWidth - 48));
  let line = "";
  let lineCount = 1;
  let widest = 0;
  for (const segment of segments) {
    const next = line + segment;
    const nextWidth = measure(next);
    if (line && nextWidth > maxLineWidth) {
      widest = Math.max(widest, measure(line));
      if (measure(segment) > maxLineWidth) {
        const split = graphemeSegments(segment);
        line = "";
        for (const piece of split) {
          const pieceNext = line + piece;
          if (line && measure(pieceNext) > maxLineWidth) {
            widest = Math.max(widest, measure(line));
            line = piece;
            lineCount += 1;
          } else {
            line = pieceNext;
          }
        }
      } else {
        line = segment.trimStart();
      }
      lineCount += 1;
    } else {
      line = next;
    }
  }
  widest = Math.max(widest, measure(line));

  return {
    height: Math.ceil(lineCount * lineHeight),
    lineCount,
    width: Math.ceil(clampNumber(widest, 120, maxLineWidth)),
  };
}

function estimatedTextRectFromDom(element: HTMLElement, text: string, maxWidth: number): RectLike {
  const current = rectFromDom(element.getBoundingClientRect());
  const estimate = estimateDomTextLayoutPretextStyle(element, text, maxWidth);
  return {
    ...current,
    bottom: current.top + estimate.height,
    height: estimate.height,
    right: current.left + estimate.width,
    width: estimate.width,
  };
}

function stableLayoutMeasurementText(fullText: string, typedText: string) {
  // Reserve the final DOM footprint while the typewriter is still catching up.
  return (fullText || typedText || "").trim();
}

function finiteNumber(value: unknown, fallback: number) {
  const number = Number(value);
  return Number.isFinite(number) ? number : fallback;
}

function dashboardLayoutMetrics(scenePlan: SceneChoreographyPayload, stageLayout: StageLayout): DashboardLayoutMetrics {
  const layout = scenePlan?.dashboard_layout ?? {};
  const speech = layout.speech ?? {};
  const selfNarration = layout.self_narration ?? {};
  const scene = layout.scene ?? {};
  const wideScene = stageLayout === "scene_focus" && requestedLayoutIntent(scenePlan) === "wide_particle_stage";
  const speechMaxVw = clampNumber(finiteNumber(speech.max_vw, wideScene ? 36 : 48), 24, 54);
  return {
    speechMaxVw,
    speechRightVw: clampNumber(finiteNumber(speech.right_vw, wideScene ? 24 : 29), 18, 34),
    speechBottomVh: clampNumber(finiteNumber(speech.bottom_vh, wideScene ? 16 : 18), 11, 22),
    speechUpperLeftTopVh: clampNumber(finiteNumber(speech.upper_left_top_vh, wideScene ? 20 : 23), 14, 28),
    speechUpperRightTopVh: clampNumber(finiteNumber(speech.upper_right_top_vh, wideScene ? 21 : 17), 12, 32),
    speechLowerLeftBottomVh: clampNumber(finiteNumber(speech.lower_left_bottom_vh, wideScene ? 11.5 : 16), 11, 28),
    speechLowerCenterBottomVh: clampNumber(finiteNumber(speech.lower_center_bottom_vh, wideScene ? 13 : 17), 12, 30),
    selfNarrationTopVh: clampNumber(finiteNumber(selfNarration.top_vh, wideScene ? 14 : 16), 8, 24),
    selfNarrationRightVw: clampNumber(finiteNumber(selfNarration.right_vw, wideScene ? 6.8 : 8), 4.8, 14),
    selfNarrationMaxVw: clampNumber(finiteNumber(selfNarration.max_vw, wideScene ? 24 : 28), 18, 34),
    fieldOpacity: clampNumber(finiteNumber(scene.field_opacity, wideScene ? 0.96 : 0.9), 0.64, 1),
  };
}

function dashboardLayoutVars(scenePlan: SceneChoreographyPayload, stageLayout: StageLayout): CSSProperties {
  if (stageLayout !== "scene_focus") return {};
  const layout = scenePlan?.dashboard_layout ?? {};
  const orb = layout.orb ?? {};
  const metrics = dashboardLayoutMetrics(scenePlan, stageLayout);
  const orbSizeVmin = clampNumber(finiteNumber(orb.size_vmin, requestedLayoutIntent(scenePlan) === "wide_particle_stage" ? 18.0 : 23.0), 12, 28);
  const orbMinPx = clampNumber(finiteNumber(orb.min_px, requestedLayoutIntent(scenePlan) === "wide_particle_stage" ? 132 : 168), 104, 230);
  const orbMaxPx = clampNumber(finiteNumber(orb.max_px, requestedLayoutIntent(scenePlan) === "wide_particle_stage" ? 218 : 260), 140, 310);
  const orbRightVw = clampNumber(finiteNumber(orb.right_vw, requestedLayoutIntent(scenePlan) === "wide_particle_stage" ? 10 : 12), 5.5, 16);
  const orbBottomVh = clampNumber(finiteNumber(orb.bottom_vh, requestedLayoutIntent(scenePlan) === "wide_particle_stage" ? 16 : 19), 9, 23);
  return {
    ["--atanor-scene-orb-size" as string]: `clamp(${orbMinPx}px, ${orbSizeVmin}vmin, ${orbMaxPx}px)`,
    ["--atanor-scene-orb-right" as string]: `clamp(86px, ${orbRightVw}vw, 168px)`,
    ["--atanor-scene-orb-bottom" as string]: `clamp(188px, ${orbBottomVh}vh, 224px)`,
    ["--atanor-scene-speech-max" as string]: `${metrics.speechMaxVw}vw`,
    ["--atanor-scene-speech-right" as string]: `${metrics.speechRightVw}vw`,
    ["--atanor-scene-speech-bottom" as string]: `${metrics.speechBottomVh}vh`,
    ["--atanor-scene-speech-upper-left-top" as string]: `${metrics.speechUpperLeftTopVh}vh`,
    ["--atanor-scene-speech-upper-right-top" as string]: `${metrics.speechUpperRightTopVh}vh`,
    ["--atanor-scene-speech-lower-left-bottom" as string]: `${metrics.speechLowerLeftBottomVh}vh`,
    ["--atanor-scene-speech-lower-center-bottom" as string]: `${metrics.speechLowerCenterBottomVh}vh`,
    ["--atanor-scene-self-top" as string]: `${metrics.selfNarrationTopVh}vh`,
    ["--atanor-scene-self-right" as string]: `${metrics.selfNarrationRightVw}vw`,
    ["--atanor-scene-self-max" as string]: `${metrics.selfNarrationMaxVw}vw`,
    ["--atanor-scene-field-opacity" as string]: String(metrics.fieldOpacity),
  };
}

function dashboardRuntimeLayoutVars(
  scenePlan: SceneChoreographyPayload,
  stageLayout: StageLayout,
  telemetry: LayoutTelemetry,
): CSSProperties {
  const base = dashboardLayoutVars(scenePlan, stageLayout);
  if (stageLayout !== "scene_focus") return base;
  const pressure = layoutCollisionPressureFromTelemetry(telemetry);
  if (pressure <= 0.02) return base;
  const metrics = dashboardLayoutMetrics(scenePlan, stageLayout);
  const wideScene = requestedLayoutIntent(scenePlan) === "wide_particle_stage";
  const severe = telemetry.collisionState === "dom_text_clipped"
    || telemetry.collisionState === "orb_clipped"
    || telemetry.collisionState === "orb_overlap_risk";
  const speechMax = clampNumber(metrics.speechMaxVw - pressure * (wideScene ? 9 : 7), wideScene ? 21 : 24, metrics.speechMaxVw);
  const selfMax = clampNumber(metrics.selfNarrationMaxVw - pressure * 4.5, 17, metrics.selfNarrationMaxVw);
  const baseOrbSize = String((base as Record<string, string | number | undefined>)["--atanor-scene-orb-size"] ?? "clamp(132px, 19vmin, 218px)");
  return {
    ...base,
    ["--atanor-scene-speech-max" as string]: `${speechMax.toFixed(2)}vw`,
    ["--atanor-scene-self-max" as string]: `${selfMax.toFixed(2)}vw`,
    ["--atanor-scene-field-opacity" as string]: String(clampNumber(metrics.fieldOpacity + pressure * 0.04, metrics.fieldOpacity, 1)),
    ["--atanor-scene-orb-size" as string]: severe
      ? "clamp(96px, 13vmin, 156px)"
      : pressure > 0.42 ? "clamp(112px, 15vmin, 182px)" : baseOrbSize,
  };
}

function overlapArea(left: RectLike, right: RectLike, padding = 0) {
  const x = Math.max(0, Math.min(left.right + padding, right.right) - Math.max(left.left - padding, right.left));
  const y = Math.max(0, Math.min(left.bottom + padding, right.bottom) - Math.max(left.top - padding, right.top));
  return x * y;
}

function offscreenAmount(rect: RectLike, inset = 12) {
  const viewportWidth = window.innerWidth;
  const viewportHeight = window.innerHeight;
  return (
    Math.max(0, inset - rect.left)
    + Math.max(0, rect.right - (viewportWidth - inset))
    + Math.max(0, inset - rect.top)
    + Math.max(0, rect.bottom - (viewportHeight - inset))
  );
}

function rectFromDom(rect: DOMRect): RectLike {
  return {
    bottom: rect.bottom,
    height: rect.height,
    left: rect.left,
    right: rect.right,
    top: rect.top,
    width: rect.width,
  };
}

function candidateSpeechRect(anchor: TextAnchor, speechSize: RectLike, dashboard: RectLike, metrics: DashboardLayoutMetrics): RectLike {
  const viewportWidth = window.innerWidth;
  const viewportHeight = window.innerHeight;
  const leftInset = cssClampPx(28, viewportWidth * 0.06, 92);
  const rightInset = cssClampPx(42, viewportWidth * 0.08, 126);
  const upperLeftTop = cssClampPx(112, viewportHeight * (metrics.speechUpperLeftTopVh / 100), 252);
  const upperRightTop = cssClampPx(96, viewportHeight * (metrics.speechUpperRightTopVh / 100), 276);
  const lowerLeftBottom = cssClampPx(104, viewportHeight * (metrics.speechLowerLeftBottomVh / 100), 260);
  const lowerCenterBottom = cssClampPx(112, viewportHeight * (metrics.speechLowerCenterBottomVh / 100), 278);
  const width = speechSize.width;
  const height = speechSize.height;
  let left = dashboard.left + leftInset;
  let top = dashboard.top + upperLeftTop;

  if (anchor === "lower_left") {
    top = dashboard.bottom - lowerLeftBottom - height;
  } else if (anchor === "upper_right") {
    left = dashboard.right - rightInset - width;
    top = dashboard.top + upperRightTop;
  } else if (anchor === "lower_center") {
    left = dashboard.left + dashboard.width / 2 - width / 2;
    top = dashboard.bottom - lowerCenterBottom - height;
  }

  return {
    bottom: top + height,
    height,
    left,
    right: left + width,
    top,
    width,
  };
}

function scenePointToDashboardRect(point: number[], dashboard: RectLike, size = 138): RectLike | null {
  if (!Array.isArray(point) || point.length < 2) return null;
  const rawX = Number(point[0]);
  const rawY = Number(point[1]);
  if (!Number.isFinite(rawX) || !Number.isFinite(rawY)) return null;
  const x = dashboard.left + dashboard.width * (0.5 + clampNumber(rawX / 2.4, -0.42, 0.42));
  const y = dashboard.top + dashboard.height * (0.5 - clampNumber(rawY / 2.0, -0.38, 0.38));
  return {
    bottom: y + size / 2,
    height: size,
    left: x - size / 2,
    right: x + size / 2,
    top: y - size / 2,
    width: size,
  };
}

function sceneFootprintToDashboardRect(scenePlan: SceneChoreographyPayload, dashboard: RectLike): RectLike | null {
  const footprint = scenePlan?.dashboard_layout?.stage_safe_region?.footprint;
  if (!footprint?.block_text) return null;
  const minX = finiteNumber(footprint.min_x, -0.72);
  const maxX = finiteNumber(footprint.max_x, 0.72);
  const minY = finiteNumber(footprint.min_y, -0.48);
  const maxY = finiteNumber(footprint.max_y, 0.48);
  const topLeft = scenePointToDashboardRect([minX, maxY], dashboard, 0);
  const bottomRight = scenePointToDashboardRect([maxX, minY], dashboard, 0);
  if (!topLeft || !bottomRight) return null;
  const horizontalPad = Math.min(72, dashboard.width * 0.04);
  const verticalPad = Math.min(58, dashboard.height * 0.045);
  return {
    bottom: Math.min(dashboard.bottom, bottomRight.top + verticalPad),
    height: Math.max(0, bottomRight.top - topLeft.top + verticalPad * 2),
    left: Math.max(dashboard.left, topLeft.left - horizontalPad),
    right: Math.min(dashboard.right, bottomRight.left + horizontalPad),
    top: Math.max(dashboard.top, topLeft.top - verticalPad),
    width: Math.max(0, bottomRight.left - topLeft.left + horizontalPad * 2),
  };
}

function sceneAnalysisObjectBlockers(analysis: SplatraInteractiveSceneAnalysisPayload, dashboard: RectLike): RectLike[] {
  if (!analysis?.interactive_scene || analysis?.analyzer_contract?.raw_splat_inference === true) return [];
  const objects = Array.isArray(analysis.objects) ? analysis.objects : [];
  return objects
    .slice(0, 24)
    .map((object) => {
      const bbox = object.bounding_box;
      const min = bbox?.min;
      const max = bbox?.max;
      if (!Array.isArray(min) || !Array.isArray(max) || min.length < 2 || max.length < 2) return null;
      const topLeft = scenePointToDashboardRect([Number(min[0]), Number(max[1]), Number(max[2] ?? 0)], dashboard, 0);
      const bottomRight = scenePointToDashboardRect([Number(max[0]), Number(min[1]), Number(min[2] ?? 0)], dashboard, 0);
      if (!topLeft || !bottomRight) return null;
      const extent = Array.isArray(bbox?.extent) ? bbox?.extent : [];
      const extentX = Math.abs(Number(extent[0] ?? 0));
      const extentY = Math.abs(Number(extent[1] ?? 0));
      const affordance = String(object.visual_affordance ?? "");
      const interactiveBoost = Array.isArray(object.interactions) && object.interactions.length > 3 ? 1.16 : 1;
      const structureBoost = affordance.includes("structure") || affordance.includes("field") ? 1.18 : 1;
      const horizontalPad = clampNumber((dashboard.width * Math.max(0.018, extentX * 0.032)) * interactiveBoost * structureBoost, 18, 96);
      const verticalPad = clampNumber((dashboard.height * Math.max(0.018, extentY * 0.038)) * interactiveBoost * structureBoost, 16, 86);
      const left = Math.min(topLeft.left, bottomRight.left) - horizontalPad;
      const right = Math.max(topLeft.left, bottomRight.left) + horizontalPad;
      const top = Math.min(topLeft.top, bottomRight.top) - verticalPad;
      const bottom = Math.max(topLeft.top, bottomRight.top) + verticalPad;
      return {
        bottom: Math.min(dashboard.bottom, bottom),
        height: Math.max(0, bottom - top),
        left: Math.max(dashboard.left, left),
        right: Math.min(dashboard.right, right),
        top: Math.max(dashboard.top, top),
        width: Math.max(0, right - left),
      };
    })
    .filter((rect): rect is RectLike => Boolean(rect && rect.width > 0 && rect.height > 0));
}

function scenePlanBlockers(scenePlan: SceneChoreographyPayload, dashboard: RectLike): RectLike[] {
  const beats = Array.isArray(scenePlan?.beats) ? scenePlan?.beats ?? [] : [];
  const footprint = sceneFootprintToDashboardRect(scenePlan, dashboard);
  const wideStage = requestedLayoutIntent(scenePlan) === "wide_particle_stage";
  const beatBlockers = beats
    .flatMap((beat) => {
      const points: number[][] = [];
      if (Array.isArray(beat.position)) points.push(beat.position);
      if (Array.isArray(beat.motion_path?.from)) points.push(beat.motion_path.from);
      if (Array.isArray(beat.motion_path?.to)) points.push(beat.motion_path.to);
      const size = beat.op === "move" || beat.motion_path ? 168 : 124;
      return points.map((point) => scenePointToDashboardRect(point, dashboard, size));
    })
    .filter((rect): rect is RectLike => Boolean(rect));
  if (wideStage) {
    // The center particle stage is not DOM text and never becomes particle
    // text, but it still reserves visual space. Text/orb placement should
    // avoid the generated scene instead of crossing through it.
    return footprint ? [footprint, ...beatBlockers] : beatBlockers;
  }
  return footprint ? [footprint, ...beatBlockers] : beatBlockers;
}

function splatraCartridgeFootprintToDashboardRect(dashboardElement: HTMLElement, dashboard: RectLike): RectLike | null {
  const field = dashboardElement.querySelector(".atanor-dashboard-imagination-field") as HTMLElement | null;
  if (!field) return null;
  const loadedParticles = Number(field.dataset.splatraCartridgeLoadedParticles ?? 0) || 0;
  const sourceParticles = Number(field.dataset.splatraCartridgeSourceParticles ?? 0) || 0;
  const realGenerator = field.dataset.splatraCartridgeRealGenerator === "true";
  const hasCartridge = loadedParticles > 0 || sourceParticles > 0;
  if (!hasCartridge) return null;
  const fieldRect = rectFromDom(field.getBoundingClientRect());
  const centerX = (fieldRect.left + fieldRect.right) / 2;
  const centerY = (fieldRect.top + fieldRect.bottom) / 2;
  const loadRatio = clampNumber(loadedParticles / Math.max(1, sourceParticles || loadedParticles), 0.18, 1);
  const denseScale = realGenerator ? 1.0 : 0.82;
  const width = Math.min(fieldRect.width * (0.68 + loadRatio * 0.13) * denseScale, dashboard.width * 0.78);
  const height = Math.min(fieldRect.height * (0.58 + loadRatio * 0.16) * denseScale, dashboard.height * 0.72);
  return {
    bottom: Math.min(dashboard.bottom, centerY + height / 2),
    height,
    left: Math.max(dashboard.left, centerX - width / 2),
    right: Math.min(dashboard.right, centerX + width / 2),
    top: Math.max(dashboard.top, centerY - height / 2),
    width,
  };
}

function scoreSpeechAnchor(
  anchor: TextAnchor,
  speechSize: RectLike,
  dashboard: RectLike,
  blockers: RectLike[],
  preferred: TextAnchor,
  metrics: DashboardLayoutMetrics,
) {
  const rect = candidateSpeechRect(anchor, speechSize, dashboard, metrics);
  const offscreen = offscreenAmount(rect);
  const blockerPenalty = blockers.reduce((total, blocker) => total + overlapArea(rect, blocker, 18), 0);
  const stagePenalty = blockers.reduce((total, blocker) => total + overlapArea(rect, blocker, 0) * 0.22, 0);
  const centerStagePenalty = blockers.reduce((total, blocker) => {
    const largeVisualStage = blocker.width > dashboard.width * 0.42 && blocker.height > dashboard.height * 0.34;
    return total + (largeVisualStage ? overlapArea(rect, blocker, 42) * 0.18 : 0);
  }, 0);
  const preferencePenalty = anchor === preferred ? 0 : anchor === "lower_left" ? 42 : 84;
  return offscreen * 1000 + blockerPenalty * 9 + stagePenalty + centerStagePenalty + preferencePenalty;
}

function scoreTextPlacementPair(
  speechAnchor: TextAnchor,
  selfAnchor: TextAnchor,
  speechSize: RectLike,
  selfSize: RectLike,
  dashboard: RectLike,
  blockers: RectLike[],
  preferredSpeech: TextAnchor,
  preferredSelf: TextAnchor,
  metrics: DashboardLayoutMetrics,
) {
  const speechRect = candidateSpeechRect(speechAnchor, speechSize, dashboard, metrics);
  const selfRect = candidateSpeechRect(selfAnchor, selfSize, dashboard, metrics);
  const speechBlockerScore = scoreSpeechAnchor(speechAnchor, speechSize, dashboard, blockers, preferredSpeech, metrics);
  const selfBlockerScore = scoreSpeechAnchor(selfAnchor, selfSize, dashboard, blockers, preferredSelf, metrics);
  const textOverlapPenalty = overlapArea(speechRect, selfRect, 24) * 9;
  const sameCornerPenalty = speechAnchor === selfAnchor ? 420 : 0;
  const lowerCenterCrowdingPenalty = speechAnchor === "lower_center" || selfAnchor === "lower_center" ? 36 : 0;
  return {
    score: speechBlockerScore + selfBlockerScore + textOverlapPenalty + sameCornerPenalty + lowerCenterCrowdingPenalty,
    selfRect,
    speechRect,
  };
}

function layoutTelemetryForRect(rect: RectLike | null, blockers: RectLike[]): LayoutTelemetry {
  if (!rect) {
    return { blockers: blockers.length, collisionState: "no_dom_text", offscreen: 0, orbOffscreen: 0, orbOverlap: 0, overlap: 0 };
  }
  const overlap = Math.round(blockers.reduce((total, blocker) => total + overlapArea(rect, blocker, 0), 0));
  const offscreen = Math.round(offscreenAmount(rect));
  let collisionState = "dom_text_clear";
  if (offscreen > 0) {
    collisionState = "dom_text_clipped";
  } else if (overlap > 360) {
    collisionState = "dom_text_overlap_risk";
  } else if (overlap > 0) {
    collisionState = "dom_text_minimized_overlap";
  }
  return { blockers: blockers.length, collisionState, offscreen, orbOffscreen: 0, orbOverlap: 0, overlap };
}

function layoutTelemetryForScene(
  textRect: RectLike | null,
  textBlockers: RectLike[],
  orbRect: RectLike | null,
  orbBlockers: RectLike[],
): LayoutTelemetry {
  const textTelemetry = layoutTelemetryForRect(textRect, textBlockers);
  const orbOverlap = orbRect
    ? Math.round(orbBlockers.reduce((total, blocker) => total + overlapArea(orbRect, blocker, 6), 0))
    : 0;
  const orbOffscreen = orbRect ? Math.round(offscreenAmount(orbRect, 8)) : 0;
  let collisionState = textTelemetry.collisionState;
  if (orbOffscreen > 0) {
    collisionState = "orb_clipped";
  } else if (orbOverlap > 220) {
    collisionState = "orb_overlap_risk";
  }
  return {
    ...textTelemetry,
    blockers: textBlockers.length + orbBlockers.length,
    collisionState,
    orbOffscreen,
    orbOverlap,
  };
}

function effectiveOrbMovementForTelemetry(stageLayout: StageLayout, requestedMovement: string, telemetry: LayoutTelemetry) {
  if (stageLayout !== "scene_focus") return requestedMovement;
  const microRequested = requestedMovement === "lower_right_micro_stage_guard" || requestedMovement === "lower_right_lifted_micro";
  if (telemetry.collisionState === "orb_clipped" || telemetry.collisionState === "orb_overlap_risk") {
    return microRequested ? "lower_right_lifted_micro" : "lower_right_lifted_compact";
  }
  if (telemetry.collisionState === "dom_text_clipped") return microRequested ? "lower_right_lifted_micro" : "lower_right_lifted_compact";
  if (telemetry.collisionState === "dom_text_overlap_risk") {
    if (microRequested) return "lower_right_lifted_micro";
    return requestedMovement === "lower_right_lifted" || requestedMovement === "lower_right_lifted_compact"
      ? "lower_right_tucked_compact"
      : "lower_right_lifted_compact";
  }
  if (telemetry.collisionState === "dom_text_minimized_overlap" && telemetry.overlap > 0) {
    return requestedMovement === "lower_right_scaled_down" ? "lower_right_tucked_compact" : requestedMovement;
  }
  return requestedMovement;
}

function layoutCollisionPressureFromTelemetry(telemetry: LayoutTelemetry) {
  const statePressure =
    telemetry.collisionState === "dom_text_clipped" ? 1
      : telemetry.collisionState === "orb_clipped" ? 1
        : telemetry.collisionState === "orb_overlap_risk" ? 0.82
      : telemetry.collisionState === "dom_text_overlap_risk" ? 0.76
        : telemetry.collisionState === "dom_text_minimized_overlap" ? 0.32
          : 0;
  const measuredPressure = Math.max(
    clampNumber(telemetry.offscreen / 180, 0, 1),
    clampNumber(telemetry.orbOffscreen / 160, 0, 1),
    clampNumber(telemetry.overlap / 1600, 0, 0.86),
    clampNumber(telemetry.orbOverlap / 1400, 0, 0.86),
  );
  const blockerPressure = clampNumber(Math.max(0, telemetry.blockers - 2) / 7, 0, 0.24);
  return clampNumber(Math.max(statePressure, measuredPressure) + blockerPressure, 0, 1);
}

function splatraControlsForLayout(emotionControls: Record<string, any> | null, telemetry: LayoutTelemetry) {
  const collisionPressure = layoutCollisionPressureFromTelemetry(telemetry);
  const base = emotionControls ?? {};
  const quieting = collisionPressure * 0.62;
  return {
    ...base,
    layout_collision_pressure: collisionPressure,
    layout_field_quieting: quieting,
    layout_text_avoidance: collisionPressure > 0 ? "dom_text_canvas_feedback" : "clear",
    layout_flow_recombine: 0.12 + collisionPressure * 0.42,
    curiosity: clampNumber(Number(base.curiosity ?? 0.45) * (1 - quieting * 0.22), 0.16, 1),
    speaking_energy: clampNumber(Number(base.speaking_energy ?? 0) * (1 - quieting * 0.16), 0, 1),
  };
}

// Stage labels for the answer stream. These name REAL engine transitions (the SSE contract:
// stage → evidence → answer), so the wait is legible instead of a frozen screen.
const STAGE_LABEL: Record<"ko" | "en", Record<string, string>> = {
  ko: {
    analyzing: "질문을 뜯어보는 중…",
    reasoning: "아는 것에서 찾는 중…",
    composing: "답을 엮는 중…",
    web_grounding: "웹에서 근거를 찾는 중…",
  },
  en: {
    analyzing: "Reading the question…",
    reasoning: "Searching what I know…",
    composing: "Composing the answer…",
    web_grounding: "Grounding on the web…",
  },
};

/** Consume the /api/chat/atanor/stream SSE and return the SAME envelope the non-stream endpoint
 *  gives ({state, result:{…}}), reporting stage transitions along the way. Throws on {type:"error"}
 *  so the caller's existing catch path is unchanged. */
async function consumeAtanorStream(
  response: Response,
  onStage: (stage: string) => void,
): Promise<any> {
  if (!response.body) throw new Error("conversation stream: no body");
  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  let envelope: any = null;
  for (;;) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    const chunks = buffer.split("\n\n");
    buffer = chunks.pop() ?? "";
    for (const chunk of chunks) {
      const line = chunk.split("\n").find((l) => l.startsWith("data: "));
      if (!line) continue;                       // ": keepalive" and blanks
      let event: any;
      try {
        event = JSON.parse(line.slice(6));
      } catch {
        continue;
      }
      if (event?.type === "stage" && typeof event.stage === "string") onStage(event.stage);
      else if (event?.type === "error") throw new Error(String(event.detail ?? "conversation stream error"));
      else if (event?.type === "answer") envelope = event.result;
    }
  }
  if (!envelope) throw new Error("conversation stream ended without an answer");
  return envelope;
}

export default function AtanorUserStatusCard({ language, onMessageSubmit }: AtanorUserStatusCardProps) {
  const [message, setMessage] = useState("");
  const [orbState, setOrbState] = useState<HologramVoiceOrbState>("idle");
  // 3D 파티클 필드 (Ultimate): 3D 의도가 잡히면 홈 위로 떠오른다.
  // avatar 모드는 오브 자리(중앙)에 — 아토를 부르면 오브가 아토로 바뀌는 경험.
  const [splatraOpen, setSplatraOpen] = useState(false);
  const [splatraMode, setSplatraMode] = useState<"avatar" | "object">("object");
  const splatraRef = useRef<SplatraHandle>(null);
  // Particle render budget. Draft = live slider thumb; applied = what the orb
  // actually rebuilds at (committed on release, since a rebuild is heavy).
  // Default to HALF density (owner 2026-07-16 "너무 버벅거려"): 7.8k full particles taxed the GPU;
  // 0.5 (~3.9k) reads the same but runs smooth. Users who want the full field raise the slider.
  const [orbDensityDraft, setOrbDensityDraft] = useState(0.5);
  const [orbDensityApplied, setOrbDensityApplied] = useState(0.5);
  useEffect(() => {
    try {
      const saved = Number(window.localStorage.getItem("atanor.orbDensity"));
      if (Number.isFinite(saved) && saved >= 0.18 && saved <= 1) {
        setOrbDensityDraft(saved);
        setOrbDensityApplied(saved);
      }
    } catch {
      /* localStorage unavailable — keep full density */
    }
  }, []);
  const commitOrbDensity = useCallback((value: number) => {
    const clamped = Math.min(1, Math.max(0.18, value));
    setOrbDensityApplied(clamped);
    try {
      window.localStorage.setItem("atanor.orbDensity", String(clamped));
    } catch {
      /* ignore persistence failure */
    }
  }, []);
  const [voiceMode, setVoiceMode] = useState(false);
  const [speechLine, setSpeechLine] = useState("");
  const [voiceNotice, setVoiceNotice] = useState("");
  const [selfNarration, setSelfNarration] = useState("");
  // ATANOR no-rule-based-surface principle: the orange self-narration ("…질문의 초점을
  // 먼저 붙잡고…") is a hand-authored inner-voice template, i.e. a rule-based canned
  // surface. Keep it out of the user-facing dashboard. (Inner-voice still runs for the
  // internal Live Selfhood lab panels; this only suppresses the user-facing narration.)
  const SHOW_RULE_BASED_SELF_NARRATION = false;
  const [foldScene, setFoldScene] = useState<FoldScene | null>(null);
  // Experimental answer-interface surface: a GeoGebra-like figure or formula card
  // the engine attaches to math/geometry answers (data-driven; see AnswerExperimentSurface).
  const [answerVisual, setAnswerVisual] = useState<AnswerVisual | null>(null);
  // Self-layout: ATANOR reads the rendered dashboard and, if the answer card would
  // cover the orb, slides the orb down just enough to clear it. Deterministic seam
  // for "the AI sees its own screen and re-arranges so nothing overlaps."
  const answerCardRef = useRef<HTMLDivElement | null>(null);
  const [orbDodgeY, setOrbDodgeY] = useState(0);
  const orbDodgeYRef = useRef(0);
  // Iframe content stage: ATANOR can surface a search box or a document/page in a
  // sandboxed iframe; the orb slides to the lower-right (scene_focus) to make room.
  const [iframeStage, setIframeStage] = useState<{ url: string; title: string } | null>(null);
  // Browser-style tabs: the orb can open the answer's source plus related pages.
  const [iframeTabs, setIframeTabs] = useState<{ url: string; title: string }[]>([]);
  const [iframeQuery, setIframeQuery] = useState("");
  // Floating-window position/size: like a free Google tab inside the dashboard.
  // null = use the default docked CSS box; once dragged/resized it becomes pinned.
  const [iframeBox, setIframeBox] = useState<{ x: number; y: number; w: number; h: number } | null>(null);
  const [iframeBusy, setIframeBusy] = useState(false); // true while drag/resize: shield the iframe from swallowing pointer events
  const iframeWinRef = useRef<HTMLDivElement | null>(null);
  const iframeDragRef = useRef<{ mode: "move" | "resize"; px: number; py: number; box: { x: number; y: number; w: number; h: number } } | null>(null);

  const beginIframeGesture = useCallback(
    (mode: "move" | "resize") => (e: React.MouseEvent) => {
      if (e.button !== 0) return;
      if (mode === "move") {
        // Don't hijack clicks on the search box, tabs, links, or close button.
        const t = e.target as HTMLElement;
        if (t.closest("input, button, a, textarea, select")) return;
      }
      const el = iframeWinRef.current;
      if (!el) return;
      const r = el.getBoundingClientRect();
      // Convert to coordinates relative to the offset parent (the dashboard stage).
      const parent = el.offsetParent as HTMLElement | null;
      const pr = parent?.getBoundingClientRect() ?? { left: 0, top: 0 } as DOMRect;
      const start = { x: r.left - pr.left, y: r.top - pr.top, w: r.width, h: r.height };
      iframeDragRef.current = { mode, px: e.clientX, py: e.clientY, box: start };
      setIframeBox(start);
      setIframeBusy(true);
      e.preventDefault();
      e.stopPropagation();
    },
    [],
  );

  useEffect(() => {
    if (!iframeBusy) return;
    const onMove = (e: MouseEvent) => {
      const d = iframeDragRef.current;
      if (!d) return;
      const dx = e.clientX - d.px;
      const dy = e.clientY - d.py;
      if (d.mode === "move") {
        setIframeBox({ ...d.box, x: Math.max(0, d.box.x + dx), y: Math.max(0, d.box.y + dy) });
      } else {
        setIframeBox({ ...d.box, w: Math.max(320, d.box.w + dx), h: Math.max(220, d.box.h + dy) });
      }
    };
    const onUp = () => {
      iframeDragRef.current = null;
      setIframeBusy(false);
    };
    window.addEventListener("mousemove", onMove);
    window.addEventListener("mouseup", onUp);
    return () => {
      window.removeEventListener("mousemove", onMove);
      window.removeEventListener("mouseup", onUp);
    };
  }, [iframeBusy]);

  // Dev/preview-only automation hook: drives the REAL submit path (same as the
  // quick-reply buttons) so harness verification doesn't fight React's controlled
  // input. Never exposed in production. window.__atanorAsk("질문") submits;
  // window.__atanorPeek() reports what surfaced (read from the DOM) for assertions.
  useEffect(() => {
    if (process.env.NODE_ENV === "production") return undefined;
    const w = window as unknown as Record<string, unknown>;
    w.__atanorAsk = (q: string) => {
      setMessage(String(q ?? ""));
      window.setTimeout(() => composerRef.current?.requestSubmit?.(), 120);
      return `submitting: ${q}`;
    };
    w.__atanorPeek = () => ({
      answerCardKind: document.querySelector(".atanor-answer-experiment")?.getAttribute("data-kind") ?? null,
      answerCardFormula: document.querySelector(".atanor-answer-experiment-formula")?.textContent ?? null,
      orbDodgeY: orbDodgeYRef.current,
      dashboardAnswerCard: document.querySelector(".atanor-ai-dashboard")?.getAttribute("data-answer-card") ?? null,
    });
    return () => {
      delete w.__atanorAsk;
      delete w.__atanorPeek;
    };
  }, []);

  // Overlap guard: when an answer card is shown, read the card's box and the orb's
  // box; if they intersect, slide the orb down just enough to clear the card.
  useEffect(() => {
    if (!answerVisual) {
      orbDodgeYRef.current = 0;
      setOrbDodgeY(0);
      return;
    }
    let raf = 0;
    const measure = () => {
      const card = answerCardRef.current?.getBoundingClientRect();
      const orbEl = dashboardRef.current?.querySelector(".hologram-voice-orb") as HTMLElement | null;
      const orb = orbEl?.getBoundingClientRect();
      if (!card || !orb) return;
      // Work from the orb's natural (un-dodged) position to avoid feedback.
      const naturalTop = orb.top - orbDodgeYRef.current;
      const hOverlap = Math.min(card.right, orb.right) - Math.max(card.left, orb.left);
      const vGap = naturalTop - card.bottom; // >0 means orb already below the card
      let dodge = 0;
      if (hOverlap > 0 && vGap < 24) {
        dodge = Math.max(0, Math.min(Math.round(card.bottom + 24 - naturalTop), 240));
      }
      orbDodgeYRef.current = dodge;
      setOrbDodgeY(dodge);
    };
    raf = window.requestAnimationFrame(() => window.requestAnimationFrame(measure));
    window.addEventListener("resize", measure);
    return () => {
      window.cancelAnimationFrame(raf);
      window.removeEventListener("resize", measure);
    };
  }, [answerVisual]);

  // Reset to the docked default whenever a fresh stage opens (new question → new window).
  useEffect(() => {
    if (!iframeStage) setIframeBox(null);
  }, [iframeStage]);
  // Nodes the agent just fetched from the web, added to the Cloud Brain, and
  // grafted onto the Local Brain to answer. Rendered glowing as they emerge.
  const [graftedNodes, setGraftedNodes] = useState<GraftedNode[]>([]);
  const [graftBatchId, setGraftBatchId] = useState(0);
  const [audioPlaying, setAudioPlaying] = useState(false);
  const [speechTypingStepMs, setSpeechTypingStepMs] = useState(24);
  const [speechSyncMode, setSpeechSyncMode] = useState<"idle" | "audio_onplaying" | "estimated_text_clock">("idle");
  const [speechSyncDurationMs, setSpeechSyncDurationMs] = useState(0);
  const [voiceEmotionHint, setVoiceEmotionHint] = useState("none");
  const [voiceTtsTag, setVoiceTtsTag] = useState("none");
  const [voiceProsodyState, setVoiceProsodyState] = useState({
    applied: false,
    delivery: "none",
    gapMs: 0,
    rate: 0,
    source: "none",
    volume: 0,
  });
  const [voicePlaybackState, setVoicePlaybackState] = useState({
    error: "none",
    unlocked: false,
  });
  const [emotionControls, setEmotionControls] = useState<Record<string, any> | null>(null);
  const [stageLayout, setStageLayout] = useState<StageLayout>("conversation");
  const [sceneChoreography, setSceneChoreography] = useState<SceneChoreographyPayload>(null);
  const [splatraCommandSequence, setSplatraCommandSequence] = useState<SplatraCommandSequencePayload>(null);
  const [splatraInteractiveSceneAnalysis, setSplatraInteractiveSceneAnalysis] = useState<SplatraInteractiveSceneAnalysisPayload>(null);
  const [splatraCartridgeQueue, setSplatraCartridgeQueue] = useState<SplatraCartridgeQueuePayload>(null);
  const [scenePolicy, setScenePolicy] = useState<SplatraScenePolicy>(() => defaultSplatraScenePolicy());
  const [conversationContext, setConversationContext] = useState<ConversationContextTurn[]>([]);
  const [sceneSpeechStartedAt, setSceneSpeechStartedAt] = useState(0);
  const [sceneSpeechBeatIndex, setSceneSpeechBeatIndex] = useState(-1);
  const [speechPlacement, setSpeechPlacement] = useState<TextAnchor>("lower_center");
  const [selfNarrationPlacement, setSelfNarrationPlacement] = useState<TextAnchor>("upper_right");
  const [layoutTelemetry, setLayoutTelemetry] = useState<LayoutTelemetry>({
    blockers: 0,
    collisionState: "conversation_default",
    offscreen: 0,
    orbOffscreen: 0,
    orbOverlap: 0,
    overlap: 0,
  });
  const [textPlacementDecision, setTextPlacementDecision] = useState<TextPlacementDecision>({
    basis: "conversation_default",
    blockerCount: 0,
    cartridgeFootprintAvoided: false,
    interactiveBboxFootprintAvoided: false,
    model: "client_dom_scene_and_cartridge_geometry_scorer_no_topic_templates",
    particleText: false,
    score: 0,
    sceneFootprintAvoided: false,
    selfNarrationAnchor: "upper_right",
    speechAnchor: "lower_center",
    textRendering: "dom_text_not_particles",
  });
  const dashboardRef = useRef<HTMLElement | null>(null);
  const speechRef = useRef<HTMLParagraphElement | null>(null);
  const selfNarrationRef = useRef<HTMLParagraphElement | null>(null);
  const composerRef = useRef<HTMLFormElement | null>(null);
  const audioRef = useRef<HTMLAudioElement | null>(null);
  const audioContextRef = useRef<AudioContext | null>(null);
  const audioSourceRef = useRef<AudioBufferSourceNode | null>(null);
  const selfNarrationHoldUntilRef = useRef(0);
  // When the holographic fold is showing, let the particle diffusion burst from
  // the CENTRED orb first, then smoothly slide the orb to the lower-right (the
  // CSS transition animates the move) and give the centre stage to the fold.
  useEffect(() => {
    if (!foldScene) return;
    const timer = window.setTimeout(() => setStageLayout("scene_focus"), 820);
    return () => window.clearTimeout(timer);
  }, [foldScene]);
  const speakingVisual = orbState === "speaking" || audioPlaying;
  const cleanPlaceholder = voiceMode
    ? language === "ko" ? "\uC74C\uC131 \uBAA8\uB4DC - \uD14D\uC2A4\uD2B8\uB3C4 \uC785\uB825\uD560 \uC218 \uC788\uC5B4\uC694" : "Voice mode - text still works"
    : language === "ko" ? "ATANOR\uC5D0\uAC8C \uB9D0\uD558\uAE30" : "Message ATANOR";
  const typedSpeechLine = useTypewriterText(speechLine, speechTypingStepMs);
  const typedSelfNarration = useTypewriterText(selfNarration, 28);
  const splatraDashboardControls = useMemo(
    () => splatraControlsForLayout(emotionControls, layoutTelemetry),
    [emotionControls, layoutTelemetry],
  );

  useEffect(() => {
    if (orbState !== "listening") return;
    const thinkingTimer = window.setTimeout(() => setOrbState("thinking"), 1500);
    const speakingTimer = window.setTimeout(() => setOrbState("speaking"), 3200);
    return () => {
      window.clearTimeout(thinkingTimer);
      window.clearTimeout(speakingTimer);
    };
  }, [orbState]);

  useEffect(() => {
    if (stageLayout !== "scene_focus") setSceneSpeechBeatIndex(-1);
  }, [stageLayout]);

  useEffect(() => {
    if (!speechLine) return;
    if (stageLayout === "scene_focus") return undefined;
    setSceneSpeechBeatIndex(-1);
    // Keep the answer on screen long enough to finish typing AND be read: scale
    // by the estimated speech duration with a generous floor (the old fixed 5.6s
    // clipped longer answers before they finished).
    const holdMs = Math.max(11000, (speechSyncDurationMs || 0) + 4000);
    const clearTimer = window.setTimeout(() => setSpeechLine(""), holdMs);
    return () => window.clearTimeout(clearTimer);
  }, [speechLine, stageLayout, speechSyncDurationMs]);

  useEffect(() => {
    if (!voiceNotice) return;
    const clearTimer = window.setTimeout(() => setVoiceNotice(""), 5200);
    return () => window.clearTimeout(clearTimer);
  }, [voiceNotice]);

  useEffect(() => {
    if (stageLayout !== "scene_focus") return undefined;
    const beats = sceneNarrationBeats(sceneChoreography, speechSyncDurationMs);
    if (!beats.length || !sceneSpeechStartedAt) {
      setSceneSpeechBeatIndex(-1);
      return undefined;
    }
    let activeIndex = -1;
    const update = () => {
      const elapsedSeconds = Math.max(0, (performance.now() - sceneSpeechStartedAt) / 1000);
      let nextIndex = 0;
      beats.forEach((beat, index) => {
        if (elapsedSeconds >= beat.tStart) nextIndex = index;
      });
      if (nextIndex !== activeIndex) {
        activeIndex = nextIndex;
        const nextSpeechBeat = beats[nextIndex];
        setSceneSpeechBeatIndex(nextSpeechBeat.beatIndex);
        setSpeechTypingStepMs(typingStepForSpeech(nextSpeechBeat.text, nextSpeechBeat.duration * 1000));
        setSpeechLine(nextSpeechBeat.text);
      }
    };
    update();
    const timer = window.setInterval(update, 180);
    return () => window.clearInterval(timer);
  }, [sceneChoreography, sceneSpeechStartedAt, speechSyncDurationMs, stageLayout]);

  useEffect(() => {
    if (stageLayout !== "scene_focus") {
      setSpeechPlacement("lower_center");
      setSelfNarrationPlacement("upper_right");
      setTextPlacementDecision((current) => (
        current.basis === "conversation_default"
          && current.speechAnchor === "lower_center"
          && current.selfNarrationAnchor === "upper_right"
          && current.score === 0
          ? current
          : {
            basis: "conversation_default",
            blockerCount: 0,
            cartridgeFootprintAvoided: false,
            interactiveBboxFootprintAvoided: false,
            model: "client_dom_scene_and_cartridge_geometry_scorer_no_topic_templates",
            particleText: false,
            score: 0,
            sceneFootprintAvoided: false,
            selfNarrationAnchor: "upper_right",
            speechAnchor: "lower_center",
            textRendering: "dom_text_not_particles",
          }
      ));
      setLayoutTelemetry((current) => (
        current.collisionState === "conversation_default" && current.blockers === 0 && current.overlap === 0 && current.offscreen === 0
          && current.orbOffscreen === 0 && current.orbOverlap === 0
          ? current
          : { blockers: 0, collisionState: "conversation_default", offscreen: 0, orbOffscreen: 0, orbOverlap: 0, overlap: 0 }
      ));
      return undefined;
    }
    const activeLayout = activeLayoutState(sceneChoreography, stageLayout, sceneSpeechBeatIndex);
    const requested = activeLayout.textAnchor ?? requestedTextAnchor(sceneChoreography);
    const preferred: TextAnchor = requested === "auto" ? "lower_left" : requested;
    const preferredSelfNarration: TextAnchor = activeLayout.selfNarrationAnchor ?? (requestedLayoutIntent(sceneChoreography) === "wide_particle_stage" ? "upper_right" : "upper_left");
    let frameId = 0;
    let timer = 0;

    const updatePlacement = () => {
      const dashboard = dashboardRef.current;
      const speech = speechRef.current;
      const selfNarrationElement = selfNarrationRef.current;
      if (!dashboard || (!speech && !selfNarrationElement)) {
        setSpeechPlacement(preferred);
        setSelfNarrationPlacement(preferredSelfNarration);
        return;
      }
      const dashboardBox = rectFromDom(dashboard.getBoundingClientRect());
      const layoutMetrics = dashboardLayoutMetrics(sceneChoreography, stageLayout);
      const orbRect = dashboard.querySelector(".hologram-voice-orb")?.getBoundingClientRect();
      const composerRect = composerRef.current?.getBoundingClientRect();
      const baseBlockers = [
        orbRect,
        composerRect,
      ]
        .filter((rect): rect is DOMRect => Boolean(rect))
        .map(rectFromDom);
      const candidates: TextAnchor[] = ["lower_left", "upper_left", "upper_right", "lower_center"];
      const sceneBlockers = scenePlanBlockers(sceneChoreography, dashboardBox);
      const interactiveObjectBlockers = sceneAnalysisObjectBlockers(splatraInteractiveSceneAnalysis, dashboardBox);
      const cartridgeBlocker = splatraCartridgeFootprintToDashboardRect(dashboard, dashboardBox);
      const cartridgeBlockers = cartridgeBlocker ? [cartridgeBlocker] : [];
      const blockers = [...baseBlockers, ...sceneBlockers, ...interactiveObjectBlockers, ...cartridgeBlockers];
      const sceneFootprintAvoided = [...sceneBlockers, ...interactiveObjectBlockers].some((blocker) => blocker.width > dashboardBox.width * 0.42 && blocker.height > dashboardBox.height * 0.34);
      const interactiveBboxFootprintAvoided = interactiveObjectBlockers.some((blocker) => blocker.width > dashboardBox.width * 0.2 && blocker.height > dashboardBox.height * 0.16);
      const cartridgeFootprintAvoided = cartridgeBlockers.some((blocker) => blocker.width > dashboardBox.width * 0.42 && blocker.height > dashboardBox.height * 0.34);
      let nextSpeechRect: RectLike | null = null;
      let nextSelfRect: RectLike | null = null;
      let nextSpeechBlockers = blockers;

      if (speech && selfNarrationElement) {
        const speechMaxWidth = Math.min(540, window.innerWidth * (layoutMetrics.speechMaxVw / 100));
        const selfMaxWidth = Math.min(360, window.innerWidth * (layoutMetrics.selfNarrationMaxVw / 100));
        const speechBox = estimatedTextRectFromDom(speech, stableLayoutMeasurementText(speechLine, typedSpeechLine), speechMaxWidth);
        const selfBox = estimatedTextRectFromDom(selfNarrationElement, stableLayoutMeasurementText(selfNarration, typedSelfNarration), selfMaxWidth);
        const selfCandidates: TextAnchor[] = ["upper_right", "upper_left", "lower_left"];
        const bestPair = candidates
          .flatMap((speechAnchor) => selfCandidates.map((selfAnchor) => ({
            speechAnchor,
            selfAnchor,
            ...scoreTextPlacementPair(
              speechAnchor,
              selfAnchor,
              speechBox,
              selfBox,
              dashboardBox,
              blockers,
              preferred,
              preferredSelfNarration,
              layoutMetrics,
            ),
          })))
          .sort((left, right) => left.score - right.score)[0];
        const nextSpeech = bestPair?.speechAnchor ?? preferred;
        const nextSelf = bestPair?.selfAnchor ?? preferredSelfNarration;
        nextSpeechRect = bestPair?.speechRect ?? candidateSpeechRect(nextSpeech, speechBox, dashboardBox, layoutMetrics);
        nextSelfRect = bestPair?.selfRect ?? candidateSpeechRect(nextSelf, selfBox, dashboardBox, layoutMetrics);
        nextSpeechBlockers = [...blockers, nextSelfRect];
        setSpeechPlacement((current) => (current === nextSpeech ? current : nextSpeech));
        setSelfNarrationPlacement((current) => (current === nextSelf ? current : nextSelf));
        setTextPlacementDecision({
          basis: TEXT_LAYOUT_BASIS,
          blockerCount: blockers.length,
          cartridgeFootprintAvoided,
          interactiveBboxFootprintAvoided,
          model: "client_dom_scene_and_cartridge_geometry_scorer_no_topic_templates",
          particleText: false,
          score: Math.round(bestPair?.score ?? 0),
          sceneFootprintAvoided,
          selfNarrationAnchor: nextSelf,
          speechAnchor: nextSpeech,
          textRendering: "dom_text_not_particles",
        });
      } else if (speech) {
        const speechMaxWidth = Math.min(540, window.innerWidth * (layoutMetrics.speechMaxVw / 100));
        const speechBox = estimatedTextRectFromDom(speech, stableLayoutMeasurementText(speechLine, typedSpeechLine), speechMaxWidth);
        const best = candidates
          .map((anchor) => ({
            anchor,
            score: scoreSpeechAnchor(anchor, speechBox, dashboardBox, blockers, preferred, layoutMetrics),
          }))
          .sort((left, right) => left.score - right.score)[0];
        const next = best?.anchor ?? preferred;
        nextSpeechRect = candidateSpeechRect(next, speechBox, dashboardBox, layoutMetrics);
        setSpeechPlacement((current) => (current === next ? current : next));
        setTextPlacementDecision({
          basis: TEXT_LAYOUT_BASIS,
          blockerCount: blockers.length,
          cartridgeFootprintAvoided,
          interactiveBboxFootprintAvoided,
          model: "client_dom_scene_and_cartridge_geometry_scorer_no_topic_templates",
          particleText: false,
          score: Math.round(best?.score ?? 0),
          sceneFootprintAvoided,
          selfNarrationAnchor: selfNarrationPlacement,
          speechAnchor: next,
          textRendering: "dom_text_not_particles",
        });
      } else if (selfNarrationElement) {
        const selfMaxWidth = Math.min(360, window.innerWidth * (layoutMetrics.selfNarrationMaxVw / 100));
        const selfBox = estimatedTextRectFromDom(selfNarrationElement, stableLayoutMeasurementText(selfNarration, typedSelfNarration), selfMaxWidth);
        const selfCandidates: TextAnchor[] = ["upper_right", "upper_left", "lower_left"];
        const bestSelf = selfCandidates
          .map((anchor) => ({
            anchor,
            score: scoreSpeechAnchor(anchor, selfBox, dashboardBox, blockers, preferredSelfNarration, layoutMetrics),
          }))
          .sort((left, right) => left.score - right.score)[0];
        const nextSelf = bestSelf?.anchor ?? preferredSelfNarration;
        nextSelfRect = candidateSpeechRect(nextSelf, selfBox, dashboardBox, layoutMetrics);
        setSelfNarrationPlacement((current) => (current === nextSelf ? current : nextSelf));
        setTextPlacementDecision({
          basis: TEXT_LAYOUT_BASIS,
          blockerCount: blockers.length,
          cartridgeFootprintAvoided,
          interactiveBboxFootprintAvoided,
          model: "client_dom_scene_and_cartridge_geometry_scorer_no_topic_templates",
          particleText: false,
          score: Math.round(bestSelf?.score ?? 0),
          sceneFootprintAvoided,
          selfNarrationAnchor: nextSelf,
          speechAnchor: speechPlacement,
          textRendering: "dom_text_not_particles",
        });
      }
      const orbBlockers = [
        composerRect ? rectFromDom(composerRect) : null,
        nextSpeechRect,
        nextSelfRect,
        ...sceneBlockers,
        ...interactiveObjectBlockers,
        ...cartridgeBlockers,
      ].filter((rect): rect is RectLike => Boolean(rect));
      const telemetry = layoutTelemetryForScene(
        nextSpeechRect,
        nextSpeechBlockers,
        orbRect ? rectFromDom(orbRect) : null,
        orbBlockers,
      );
      setLayoutTelemetry((current) => (
        current.collisionState === telemetry.collisionState
          && current.blockers === telemetry.blockers
          && current.overlap === telemetry.overlap
          && current.offscreen === telemetry.offscreen
          && current.orbOverlap === telemetry.orbOverlap
          && current.orbOffscreen === telemetry.orbOffscreen
          ? current
          : telemetry
      ));
    };

    frameId = window.requestAnimationFrame(updatePlacement);
    timer = window.setInterval(updatePlacement, 420);
    window.addEventListener("resize", updatePlacement);
    return () => {
      window.cancelAnimationFrame(frameId);
      window.clearInterval(timer);
      window.removeEventListener("resize", updatePlacement);
    };
  }, [sceneChoreography, sceneSpeechBeatIndex, splatraInteractiveSceneAnalysis, stageLayout, typedSelfNarration, typedSpeechLine]);

  useEffect(() => {
    let cancelled = false;
    async function refreshEmotionControls() {
      const payload = await fetch("/api/neural-emotion/snapshot", { cache: "no-store" })
        .then((response) => response.json())
        .catch(() => null);
      if (!cancelled) {
        setEmotionControls(payload?.snapshot?.splatra_controls ?? payload?.splatra_controls ?? null);
      }
    }
    refreshEmotionControls().catch(() => undefined);
    const timer = window.setInterval(() => refreshEmotionControls().catch(() => undefined), 12000);
    return () => {
      cancelled = true;
      window.clearInterval(timer);
    };
  }, []);

  useEffect(() => {
    if (!SHOW_RULE_BASED_SELF_NARRATION) return;
    let cancelled = false;
    async function refreshSelfNarration() {
      const payload = await fetch("/api/inner-voice/status?workspace=product", { cache: "no-store" })
        .then((response) => response.json())
        .catch(() => null);
      const next = String(
        payload?.product_summary?.visible_self_narration
          ?? payload?.visible_self_narration
          ?? payload?.product_summary?.summary
          ?? "",
      ).trim();
      if (!cancelled && next && Date.now() > selfNarrationHoldUntilRef.current) {
        setSelfNarration(next);
      }
    }
    refreshSelfNarration().catch(() => undefined);
    const timer = window.setInterval(() => refreshSelfNarration().catch(() => undefined), 2600);
    return () => {
      cancelled = true;
      window.clearInterval(timer);
    };
  }, []);

  function stopAudio() {
    const source = audioSourceRef.current;
    if (source) {
      try {
        source.stop();
      } catch {
        // Source may already be stopped; ignore so UI state can still reset.
      }
      source.disconnect();
    }
    audioSourceRef.current = null;
    const audio = audioRef.current;
    if (audio) {
      audio.pause();
      audio.src = "";
    }
    audioRef.current = null;
    setAudioPlaying(false);
    setVoicePlaybackState((current) => ({ ...current, error: "none" }));
  }

  function startVoiceMode() {
    setVoiceMode(true);
    setOrbState("listening");
    setVoiceNotice("");
    setSpeechLine(language === "ko" ? "\uB4E3\uACE0 \uC788\uC5B4." : "I'm listening.");
  }

  function cancelVoiceMode() {
    stopAudio();
    setVoiceMode(false);
    setOrbState("resting");
    setSpeechLine("");
    setVoiceNotice("");
  }

  function primeVoiceAudioElement() {
    try {
      const AudioContextCtor = window.AudioContext
        ?? (window as unknown as { webkitAudioContext?: typeof AudioContext }).webkitAudioContext;
      if (AudioContextCtor) {
        const context = audioContextRef.current ?? new AudioContextCtor();
        audioContextRef.current = context;
        void withAudioTimeout(context.resume(), 700).then(() => {
          if (context.state === "running") {
            setVoicePlaybackState({ error: "none", unlocked: true });
          }
        }).catch((error) => {
          setVoicePlaybackState({
            error: error instanceof Error ? `context_${error.name || "failed"}` : "context_failed",
            unlocked: false,
          });
        });
      }
      const audio = audioRef.current ?? new Audio();
      audio.muted = false;
      audio.loop = true;
      audio.preload = "auto";
      audio.volume = 0;
      audio.src = "data:audio/wav;base64,UklGRigAAABXQVZFZm10IBAAAAABAAEAESsAACJWAAACABAAZGF0YQQAAAAAAA==";
      audioRef.current = audio;
      void audio.play().then(() => {
        audio.currentTime = 0;
        setVoicePlaybackState({ error: "none", unlocked: true });
      }).catch((error) => {
        setVoicePlaybackState({
          error: error instanceof Error ? `prime_${error.name || "failed"}` : "prime_failed",
          unlocked: false,
        });
      });
    } catch {
      audioRef.current = null;
      setVoicePlaybackState({ error: "prime_failed", unlocked: false });
    }
  }

  async function playVoiceOutputWithAudioContext(
    voiceOutput: VoiceOutput,
    onPlaybackStart?: () => void,
  ): Promise<boolean> {
    const AudioContextCtor = window.AudioContext
      ?? (window as unknown as { webkitAudioContext?: typeof AudioContext }).webkitAudioContext;
    if (!AudioContextCtor || !voiceOutput.audio_url) return false;
    const context = audioContextRef.current ?? new AudioContextCtor();
    audioContextRef.current = context;
    if (context.state !== "running") {
      await withAudioTimeout(context.resume(), 700);
    }
    if (context.state !== "running") return false;
    const response = await fetch(voiceOutput.audio_url, { cache: "no-store" });
    if (!response.ok) return false;
    const bytes = await response.arrayBuffer();
    const buffer = await context.decodeAudioData(bytes.slice(0));
    const source = context.createBufferSource();
    const gain = context.createGain();
    gain.gain.value = 1;
    source.buffer = buffer;
    source.connect(gain);
    gain.connect(context.destination);
    audioSourceRef.current?.disconnect();
    audioSourceRef.current = source;
    source.onended = () => {
      if (audioSourceRef.current === source) {
        audioSourceRef.current = null;
      }
      setAudioPlaying(false);
      setOrbState(voiceMode ? "listening" : "resting");
      emitNeuralEmotionEvent("speaking_end", "web audio playback ended");
    };
    onPlaybackStart?.();
    setAudioPlaying(true);
    setOrbState("speaking");
    setVoicePlaybackState({ error: "none", unlocked: true });
    emitNeuralEmotionEvent("speaking_start", "web audio playback started");
    source.start(0);
    return true;
  }

  async function playVoiceOutput(voiceOutput: VoiceOutput | undefined, onPlaybackStart?: () => void): Promise<boolean> {
    if (!voiceOutput?.audio_available || !voiceOutput.audio_url) {
      stopAudio();
      setVoiceNotice(voiceOutput?.user_message || cleanVoiceUnavailableLine(language));
      return false;
    }
    try {
      if (await playVoiceOutputWithAudioContext(voiceOutput, onPlaybackStart)) {
        return true;
      }
    } catch {
      audioSourceRef.current = null;
    }
    try {
      const audio = audioRef.current ?? new Audio();
      let playbackStarted = false;
      audio.muted = false;
      audio.loop = false;
      audio.volume = 1;
      audio.src = voiceOutput.audio_url;
      audio.preload = "auto";
      audio.crossOrigin = "anonymous";
      audio.onplaying = () => {
        if (!playbackStarted) {
          playbackStarted = true;
          onPlaybackStart?.();
        }
        setAudioPlaying(true);
        setOrbState("speaking");
        emitNeuralEmotionEvent("speaking_start", "audio playback started");
      };
      audio.onended = () => {
        setAudioPlaying(false);
        setOrbState(voiceMode ? "listening" : "resting");
        emitNeuralEmotionEvent("speaking_end", "audio playback ended");
      };
      audio.onerror = () => {
        setAudioPlaying(false);
        setVoiceNotice(cleanVoiceFailedLine(language));
        setOrbState(voiceMode ? "listening" : "resting");
        setVoicePlaybackState({ error: "audio_element_error", unlocked: voicePlaybackState.unlocked });
        emitNeuralEmotionEvent("voice_unavailable", "audio playback error");
      };
      audioRef.current = audio;
      audio.load();
      await audio.play();
      setVoicePlaybackState({ error: "none", unlocked: true });
      return true;
    } catch (error) {
      setAudioPlaying(false);
      const errorName = error instanceof Error ? error.name || "play_failed" : "play_failed";
      setVoiceNotice(errorName === "NotAllowedError" ? "" : cleanVoiceFailedLine(language));
      setOrbState(voiceMode ? "listening" : "resting");
      setVoicePlaybackState({
        error: errorName,
        unlocked: voicePlaybackState.unlocked,
      });
      emitNeuralEmotionEvent("voice_unavailable", "audio playback unavailable");
      return false;
    }
  }

  async function submitMessage(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const trimmed = message.trim();
    if (!trimmed) return;
    // 3D 공간 제어 (Ultimate 전용): 명백한 3D 의도는 파티클 필드로 — 아토 소환,
    // 생성, 몸짓, 재질. 일반 질문은 아래 언어 엔진 경로 그대로.
    const splatraCmd = isDemo ? null : parse3DIntent(trimmed);
    if (splatraCmd && (splatraCmd.kind !== "gesture" || splatraOpen)) {
      setMessage("");
      if (splatraCmd.kind === "gesture") {           // 인사는 팔만 — 재생성 없음
        splatraRef.current?.gesture(splatraCmd.name);
        return;
      }
      if (splatraCmd.kind === "avatar") setSplatraMode("avatar");   // 오브 자리에
      else if (!splatraOpen) setSplatraMode("object");
      setSplatraOpen(true);
      void (async () => {
        try {
          if (splatraCmd.kind === "avatar") {
            await fetch("/api/splatra/v1/avatar", { method: "POST",
              headers: { "Content-Type": "application/json" }, body: "{}" });
            splatraRef.current?.reload();
          } else if (splatraCmd.kind === "generate") {
            splatraRef.current?.disassemble();
            await fetch("/api/splatra/v1/chat", { method: "POST",
              headers: { "Content-Type": "application/json" },
              body: JSON.stringify({ message: splatraCmd.prompt }) });
            splatraRef.current?.reload();
          } else if (splatraCmd.kind === "anim") splatraRef.current?.animate(splatraCmd.style);
          else if (splatraCmd.kind === "stop") splatraRef.current?.animate("stop");
          else if (splatraCmd.kind === "reset") splatraRef.current?.animate("flow");
        } catch { /* particle engine offline: panel stays empty */ }
      })();
      return;
    }
    setFoldScene(null); // clear any prior fold; a fold request re-attaches it
    setAnswerVisual(null); // clear any prior figure/formula; re-attached if present

    if (onMessageSubmit?.(trimmed)) {
      setMessage("");
      setSpeechLine("");
      setVoiceNotice("");
      setSpeechSyncMode("idle");
      return;
    }

    setVoiceMode(true);
    setOrbState("thinking");
    setVoiceNotice("");
    setSpeechLine("");   // owner 2026-07-16: no "Let me think." filler \u2014 go straight to the answer
    setSpeechSyncMode("estimated_text_clock");
    setSpeechSyncDurationMs(0);
    setVoiceEmotionHint("none");
    setVoiceTtsTag("none");
    setVoiceProsodyState({ applied: false, delivery: "none", gapMs: 0, rate: 0, source: "none", volume: 0 });
    setVoicePlaybackState({ error: "none", unlocked: false });
    primeVoiceAudioElement();
    let visualStateCommitted = false;
    try {
      // STREAM the answer (owner 2026-07-17 "반응속도 늦음"): a first-time web-grounded question
      // costs ~17s of real multi-round search. The work can't be wished away, but the UI must not
      // look frozen while ATANOR thinks — /stream emits true stage transitions (analyzing →
      // reasoning → composing → web_grounding) and finally {type:"answer", result} carrying the
      // SAME envelope the non-stream endpoint returned, so everything downstream is unchanged.
      const response = await fetch("/api/chat/atanor/stream", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          question: trimmed,
          language,
          mode: "conversation",
          brain_mode: "conversation",
          web_search: shouldRequestWebGrounding(trimmed),
          include_trace: false,
          conversation_context: conversationContext.slice(-6),
          layout_feedback: {
            feedback_basis: "client_dom_scene_collision_telemetry",
            collision_state: layoutTelemetry.collisionState,
            blockers: layoutTelemetry.blockers,
            overlap_px: layoutTelemetry.overlap,
            offscreen_px: layoutTelemetry.offscreen,
            orb_overlap_px: layoutTelemetry.orbOverlap,
            orb_offscreen_px: layoutTelemetry.orbOffscreen,
            interactive_scene_object_count: Number(splatraInteractiveSceneAnalysis?.object_count ?? splatraInteractiveSceneAnalysis?.objects?.length ?? 0) || 0,
            interactive_scene_bbox_count: Array.isArray(splatraInteractiveSceneAnalysis?.objects)
              ? splatraInteractiveSceneAnalysis.objects.filter((object) => Boolean(object?.bounding_box)).length
              : 0,
            interactive_scene_analysis_basis: String(
              splatraInteractiveSceneAnalysis?.analyzer_contract?.object_detection_claim ?? "none",
            ),
            speech_anchor: speechPlacement,
            self_narration_anchor: selfNarrationPlacement,
            stage_layout: stageLayout,
            text_rendering: "dom_text_not_particles",
            particle_text: false,
          },
        }),
      });
      if (!response.ok) throw new Error(`conversation surface failed: ${response.status}`);
      const payload = await consumeAtanorStream(response, (stage) => {
        // Live, truthful progress — real state transitions from the engine, not a fake spinner.
        // Goes to the status notice, NOT the orb's speech line (that stays filler-free).
        const label = STAGE_LABEL[language === "ko" ? "ko" : "en"][stage];
        if (label) setVoiceNotice(label);
      });
      setVoiceNotice("");
      if (payload?.result?.render_fold_scene && payload?.result?.folded_state_field) {
        setFoldScene(payload.result.folded_state_field as FoldScene);
      }
      // The agent decided to surface a document/search — open the iframe stage on
      // its own (orb slides to the lower-right). No button needed.
      // Dashboard control directive: the orb obeys layout commands ("창 닫아").
      const directive = payload?.result?.dashboard_directive as { action?: string } | undefined;
      if (directive?.action === "close_window") {
        setIframeStage(null);
        setIframeTabs([]);
        setStageLayout("conversation");
      }
      const renderIframe = payload?.result?.render_iframe as { url?: string; title?: string } | undefined;
      const renderIframeTabs = payload?.result?.render_iframe_tabs as { url?: string; title?: string }[] | undefined;
      if (renderIframe?.url) {
        const tabs = Array.isArray(renderIframeTabs) && renderIframeTabs.length > 1
          ? renderIframeTabs
              .filter((tab) => tab?.url)
              .map((tab) => ({ url: String(tab.url), title: String(tab.title || "") }))
          : [{ url: String(renderIframe.url), title: String(renderIframe.title || "") }];
        setIframeTabs(tabs);
        setIframeStage(tabs[0]);
        setIframeQuery("");
        setStageLayout("scene_focus");
      }
      const answer = String(payload?.result?.answer ?? "");
      if (!answer || !isAsmConversationPayload(payload)) {
        throw new Error("conversation surface unavailable");
      }
      setAnswerVisual((payload?.result?.answer_visual as AnswerVisual | undefined) ?? null);
      // New web→Cloud Brain→Local Brain nodes for this answer: light them up.
      const newGrafted = (payload?.result?.web_grafted_nodes as GraftedNode[] | undefined) ?? [];
      if (Array.isArray(newGrafted) && newGrafted.length > 0) {
        setGraftedNodes(newGrafted);
        setGraftBatchId((previous) => previous + 1);
      } else {
        setGraftedNodes([]);
      }
      const voiceOutput = payload?.result?.voice_output as VoiceOutput | undefined;
      const nextSpeechDurationMs = estimatedSpeechDurationMs(answer, voiceOutput);
      const nextTypingStepMs = typingStepForSpeech(answer, nextSpeechDurationMs);
      const nextVoiceControls = voiceOutput?.neural_emotion_voice_controls ?? null;
      setSpeechTypingStepMs(nextTypingStepMs);
      setSpeechSyncDurationMs(nextSpeechDurationMs);
      setVoiceEmotionHint(String(nextVoiceControls?.emotion_hint ?? "none"));
      setVoiceTtsTag(String(nextVoiceControls?.tts_tag || "none"));
      setVoiceProsodyState({
        applied: voiceOutput?.fallback_prosody_applied === true,
        delivery: String(nextVoiceControls?.fallback_delivery ?? "none"),
        gapMs: Number(nextVoiceControls?.fallback_sentence_gap_ms ?? 0) || 0,
        rate: Number(voiceOutput?.local_tts_rate ?? 0) || 0,
        source: String(voiceOutput?.fallback_prosody_source ?? "none"),
        volume: Number(voiceOutput?.local_tts_volume ?? 0) || 0,
      });
      // An open document keeps the stage in scene_focus so the orb tucks aside.
      const nextStageLayout = renderIframe?.url ? "scene_focus" : requestedStageLayout(payload);
      const nextSceneChoreography = requestedSceneChoreography(payload);
      const nextScenePolicy = requestedSplatraScenePolicy(payload);
      const nextSplatraCommandSequence = requestedSplatraCommandSequence(payload);
      const nextSplatraInteractiveSceneAnalysis = requestedSplatraInteractiveSceneAnalysis(payload);
      const nextSplatraCartridgeQueue = requestedSplatraCartridgeQueue(payload);
      const nextInitialSceneBeatIndex = sceneNarrationBeats(nextSceneChoreography, nextSpeechDurationMs)[0]?.beatIndex ?? -1;
      const startVisibleSpeech = (syncMode: "audio_onplaying" | "estimated_text_clock") => {
        const firstNarration = sceneNarrationBeats(nextSceneChoreography, nextSpeechDurationMs)[0]?.text ?? firstSceneNarration(nextSceneChoreography);
        const visibleLine = firstNarration || firstSpeechBeat(answer);
        const firstBeat = sceneNarrationBeats(nextSceneChoreography, nextSpeechDurationMs)[0];
        const visibleDuration = firstBeat?.duration ? firstBeat.duration * 1000 : nextSpeechDurationMs;
        setSpeechTypingStepMs(typingStepForSpeech(visibleLine, visibleDuration));
        if (nextSceneChoreography) setSceneSpeechStartedAt(performance.now());
        setSpeechSyncMode(syncMode);
        setSpeechLine(visibleLine);
      };
      const nextOrbLayoutFeedback = splatraOrbLayoutFeedback(nextSceneChoreography, nextStageLayout, layoutTelemetry, nextInitialSceneBeatIndex);
      setStageLayout(nextStageLayout);
      setSceneChoreography(nextSceneChoreography);
      setSplatraCommandSequence(nextSplatraCommandSequence);
      setSplatraInteractiveSceneAnalysis(nextSplatraInteractiveSceneAnalysis);
      setSplatraCartridgeQueue(nextSplatraCartridgeQueue);
      setScenePolicy(nextScenePolicy);
      setSceneSpeechStartedAt(0);
      const nextConversationTurns: ConversationContextTurn[] = [
        { role: "user", text: trimmed },
        { role: "assistant", text: answer },
      ];
      setConversationContext((previous) => [...previous, ...nextConversationTurns].slice(-8));
      visualStateCommitted = true;
      setOrbState("speaking");
      void fetch("/api/inner-voice/generate-frame", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({
          source_event_id: "product_hologram_conversation",
          mode: "product_summary",
          append_to_log: true,
          latest_user_input: trimmed,
          latest_action_result: {
            speech_act: payload?.result?.answer_kind ?? "conversation",
            answered: true,
            scene_focus: nextStageLayout === "scene_focus",
            layout_decision: requestedLayoutDecision(nextSceneChoreography, nextStageLayout),
            visual_scene_beats: Array.isArray(nextSceneChoreography?.beats) ? nextSceneChoreography?.beats?.length ?? 0 : 0,
            layout_feedback: {
              collision_state: layoutTelemetry.collisionState,
              measured_blockers: layoutTelemetry.blockers,
              overlap_px: layoutTelemetry.overlap,
              offscreen_px: layoutTelemetry.offscreen,
              orb_overlap_px: layoutTelemetry.orbOverlap,
              orb_offscreen_px: layoutTelemetry.orbOffscreen,
            },
            orb_layout_feedback: nextOrbLayoutFeedback,
            splatra_scene_policy: nextScenePolicy,
          },
          splatra_state: splatraStateForInnerVoice(nextSceneChoreography, nextStageLayout, layoutTelemetry, nextInitialSceneBeatIndex, nextScenePolicy),
          review_queue_pressure: 0,
          permission_tier: "OBSERVE_ONLY",
        }),
      })
        .then((response) => response.json())
        .then((innerVoicePayload) => {
          const next = String(
            innerVoicePayload?.product_summary?.visible_self_narration
              ?? innerVoicePayload?.product_summary?.summary
              ?? "",
          ).trim();
          if (next && SHOW_RULE_BASED_SELF_NARRATION) {
            selfNarrationHoldUntilRef.current = Date.now() + 30000;
            setSelfNarration(next);
          }
      })
        .catch(() => undefined);
      emitNeuralEmotionEvent("speaking_start", "text conversation visible speech");
      setMessage("");
      const audioStarted = await playVoiceOutput(voiceOutput, () => startVisibleSpeech("audio_onplaying"));
      if (!audioStarted) {
        startVisibleSpeech("estimated_text_clock");
        window.setTimeout(() => {
          setOrbState("listening");
          emitNeuralEmotionEvent("speaking_end", "text fallback speech ended");
        }, clampNumber(nextSpeechDurationMs + 360, 1800, 48000));
      }
    } catch {
      setOrbState("blocked");
      if (!visualStateCommitted) {
        setStageLayout("conversation");
        setSceneChoreography(null);
        setSplatraCommandSequence(null);
        setSplatraInteractiveSceneAnalysis(null);
        setSplatraCartridgeQueue(null);
        setScenePolicy(defaultSplatraScenePolicy());
        setSceneSpeechStartedAt(0);
        setSceneSpeechBeatIndex(-1);
      }
      setSpeechSyncMode("idle");
      setSpeechLine(visualStateCommitted ? speechLine || cleanSafeStatusLine(language) : cleanSafeStatusLine(language));
      setVoiceNotice(cleanVoiceFailedLine(language));
      window.setTimeout(() => setOrbState(voiceMode ? "listening" : "resting"), 2600);
    }
  }

  const currentLayoutState = activeLayoutState(sceneChoreography, stageLayout, sceneSpeechBeatIndex);
  const splatraCommandActionCount = Array.isArray(splatraCommandSequence?.scene_actions)
    ? splatraCommandSequence?.scene_actions?.length ?? 0
    : 0;
  const splatraCandidateCartridgeCount = Array.isArray(splatraCommandSequence?.candidate_cartridge_requests)
    ? splatraCommandSequence?.candidate_cartridge_requests?.length ?? 0
    : 0;
  const splatraCandidateCartridgeFormat = String(splatraCommandSequence?.candidate_cartridge_requests?.[0]?.cartridge_format ?? "none");
  const splatraCartridgeQueueStatus = String(splatraCartridgeQueue?.status ?? "none");
  const splatraCartridgeQueueMode = String(splatraCartridgeQueue?.execution_mode ?? "none");
  const splatraCartridgeQueueJobs = Number(splatraCartridgeQueue?.job_count ?? 0) || 0;
  const splatraSidecarStatus = String(splatraCartridgeQueue?.sidecar_dispatch?.status ?? splatraCartridgeQueue?.sidecar_status ?? "none");
  const splatraSidecarConfigured = splatraCartridgeQueue?.sidecar_dispatch?.configured === true || splatraCartridgeQueue?.sidecar_configured === true;
  const splatraSidecarJobs = Number(splatraCartridgeQueue?.sidecar_dispatch?.job_count ?? 0) || 0;
  const splatraSidecarRawCartridgeFetched = splatraCartridgeQueue?.sidecar_dispatch?.raw_cartridge_fetched === true;
  const splatraInteractiveObjectCount = Number(splatraInteractiveSceneAnalysis?.object_count ?? splatraInteractiveSceneAnalysis?.objects?.length ?? 0) || 0;
  const splatraInteractiveBboxCount = Array.isArray(splatraInteractiveSceneAnalysis?.objects)
    ? splatraInteractiveSceneAnalysis.objects.filter((object) => Boolean(object?.bounding_box)).length
    : 0;
  const splatraInteractiveAnalysisBasis = String(splatraInteractiveSceneAnalysis?.analyzer_contract?.object_detection_claim ?? "none");
  const splatraInteractiveRawInference = splatraInteractiveSceneAnalysis?.analyzer_contract?.raw_splat_inference === true
    || splatraInteractiveSceneAnalysis?.safety_flags?.raw_buffer_in_agent_context === true;
  const stagePressure = Number(sceneChoreography?.dashboard_layout?.stage_pressure ?? 0) || 0;
  const orbYieldStrength = Number(sceneChoreography?.dashboard_layout?.agent_layout_decision?.orb_yield_strength ?? stagePressure) || 0;
  const sceneSelfState = sceneChoreography?.scene_self_state
    ?? sceneChoreography?.dashboard_layout?.agent_layout_decision?.scene_self_state
    ?? {};
  const sceneSelfParticlePressure = finiteNumber(sceneSelfState.particle_field_pressure, 0);
  const sceneSelfBodyPressure = finiteNumber(sceneSelfState.self_body_pressure, 0);
  const sceneSelfTextPressure = finiteNumber(sceneSelfState.text_clearance_pressure, 0);
  const sceneSelfComposerPressure = finiteNumber(sceneSelfState.composer_clearance_pressure, 0);
  const explicitAgentSceneDecisionCount = Array.isArray(sceneChoreography?.agent_scene_decisions)
    ? sceneChoreography?.agent_scene_decisions?.length ?? 0
    : 0;
  const explicitParticleOperationIntentCount = Array.isArray(sceneChoreography?.particle_operation_intents)
    ? sceneChoreography?.particle_operation_intents?.length ?? 0
    : 0;
  const legacyLayoutDecisionCount = Array.isArray(sceneChoreography?.layout_timeline)
    ? sceneChoreography?.layout_timeline?.length ?? 0
    : 0;
  const legacyBeatCount = Array.isArray(sceneChoreography?.beats) ? sceneChoreography?.beats?.length ?? 0 : 0;
  const agentSceneDecisionCount = explicitAgentSceneDecisionCount || (stageLayout === "scene_focus" ? legacyLayoutDecisionCount : 0);
  const particleOperationIntentCount = explicitParticleOperationIntentCount || (stageLayout === "scene_focus" ? legacyBeatCount : 0);
  const avoidanceFootprint = currentLayoutState.avoidanceSceneFootprint && typeof currentLayoutState.avoidanceSceneFootprint === "object"
    ? currentLayoutState.avoidanceSceneFootprint as Record<string, unknown>
    : null;
  const avoidanceFootprintLabel = avoidanceFootprint
    ? `${finiteNumber(avoidanceFootprint.min_x, 0).toFixed(3)},${finiteNumber(avoidanceFootprint.max_x, 0).toFixed(3)},${finiteNumber(avoidanceFootprint.min_y, 0).toFixed(3)},${finiteNumber(avoidanceFootprint.max_y, 0).toFixed(3)}`
    : "none";
  const firstParticleOperationIntent = String(
    sceneChoreography?.particle_operation_intents?.[0]?.operation
      ?? particleOperationForSceneBeat(sceneChoreography?.beats?.[0])
      ?? "none",
  );
  const particleOperationIntentSource = explicitParticleOperationIntentCount > 0
    ? "explicit_particle_operation_intents"
    : particleOperationIntentCount > 0 ? "derived_from_legacy_scene_beats" : "none";
  const pressureAdjustedOrbMovement = stageLayout === "scene_focus"
    && stagePressure >= 0.82
    && currentLayoutState.orbMovement === "lower_right_scaled_down"
    ? "lower_right_micro_stage_guard"
    : currentLayoutState.orbMovement;
  const effectiveOrbMovement = effectiveOrbMovementForTelemetry(stageLayout, pressureAdjustedOrbMovement, layoutTelemetry);
  const orbMovementFeedback = effectiveOrbMovement === currentLayoutState.orbMovement
    ? "server_scene_geometry"
    : pressureAdjustedOrbMovement !== currentLayoutState.orbMovement ? "client_stage_pressure_feedback" : "client_dom_collision_feedback";
  const runtimeLayoutAdjustment = stageLayout === "scene_focus" && layoutCollisionPressureFromTelemetry(layoutTelemetry) > 0.02
    ? "client_geometry_css_var_adjustment_no_particle_text"
    : "none";
  const dashboardParticleBudget = stageLayout === "scene_focus"
    ? requestedLayoutIntent(sceneChoreography) === "wide_particle_stage" ? 24000 : 9800
    : 3600;

  return (
    <section
      ref={dashboardRef}
      data-splatra-open={splatraOpen ? "true" : "false"}
      className="atanor-ai-dashboard"
      data-answer-card={answerVisual && !foldScene && !iframeStage ? "true" : "false"}
      aria-label={language === "ko" ? "ATANOR \uC785\uC790 \uBCF8\uCCB4" : "ATANOR particle body"}
      data-voice-mode={voiceMode ? "true" : "false"}
      data-speaking={speakingVisual ? "true" : "false"}
      data-speech-sync-mode={speechSyncMode}
      data-speech-sync-duration-ms={Math.round(speechSyncDurationMs)}
      data-speech-typing-step-ms={Math.round(speechTypingStepMs)}
      data-voice-emotion-hint={voiceEmotionHint}
      data-voice-tts-tag={voiceTtsTag}
      data-voice-prosody-applied={voiceProsodyState.applied ? "true" : "false"}
      data-voice-prosody-source={voiceProsodyState.source}
      data-voice-prosody-delivery={voiceProsodyState.delivery}
      data-voice-prosody-gap-ms={voiceProsodyState.gapMs}
      data-voice-local-tts-rate={voiceProsodyState.rate}
      data-voice-local-tts-volume={voiceProsodyState.volume}
      data-voice-playback-error={voicePlaybackState.error}
      data-voice-playback-unlocked={voicePlaybackState.unlocked ? "true" : "false"}
      data-stage-layout={stageLayout}
      data-iframe-stage={iframeStage ? "open" : "closed"}
      data-scene-speech-beat={sceneSpeechBeatIndex >= 0 ? String(sceneSpeechBeatIndex) : "none"}
      data-speech-placement={speechPlacement}
      data-self-narration-placement={selfNarrationPlacement}
      data-scene-intent={stageLayout === "scene_focus" ? requestedLayoutIntent(sceneChoreography) : "conversation"}
      data-layout-basis={requestedLayoutBasis(sceneChoreography, stageLayout)}
      data-layout-decision={requestedLayoutDecision(sceneChoreography, stageLayout)}
      data-layout-action={currentLayoutState.action}
      data-layout-decision-owner={currentLayoutState.owner}
      data-layout-action-basis={currentLayoutState.basis}
      data-layout-orb-anchor={currentLayoutState.orbAnchor}
      data-layout-orb-movement={effectiveOrbMovement}
      data-layout-requested-orb-movement={currentLayoutState.orbMovement}
      data-layout-pressure-adjusted-orb-movement={pressureAdjustedOrbMovement}
      data-layout-orb-identity={currentLayoutState.orbIdentity}
      data-layout-orb-feedback={orbMovementFeedback}
      data-runtime-layout-adjustment={runtimeLayoutAdjustment}
      data-layout-stage-pressure={stagePressure.toFixed(3)}
      data-layout-orb-yield-strength={orbYieldStrength.toFixed(3)}
      data-scene-self-owner={sceneSelfState.state_owner ?? "none"}
      data-scene-self-basis={sceneSelfState.state_basis ?? "none"}
      data-scene-self-body={sceneSelfState.self_body_identity ?? "none"}
      data-scene-self-particle-pressure={sceneSelfParticlePressure.toFixed(3)}
      data-scene-self-body-pressure={sceneSelfBodyPressure.toFixed(3)}
      data-scene-self-text-pressure={sceneSelfTextPressure.toFixed(3)}
      data-scene-self-composer-pressure={sceneSelfComposerPressure.toFixed(3)}
      data-scene-self-topic-templates={sceneSelfState.topic_scene_templates === true ? "true" : "false"}
      data-scene-self-renderer-inference={sceneSelfState.renderer_may_infer_topic === true ? "true" : "false"}
      data-layout-stage-region={currentLayoutState.stageRegion}
      data-layout-autonomy={currentLayoutState.layoutAutonomy}
      data-particle-stage-strategy={currentLayoutState.particleStageStrategy}
      data-particle-space={currentLayoutState.particleSpace}
      data-generated-visual-elements={currentLayoutState.generatedVisualElements}
      data-line-rendering={currentLayoutState.lineRendering}
      data-flow-motion-reference={currentLayoutState.flowMotionReference}
      data-text-exception={currentLayoutState.textException}
      data-orb-self-body-yield={currentLayoutState.orbSelfBodyYield}
      data-particle-recomposition-mode={currentLayoutState.particleRecompositionMode}
      data-agent-scene-decisions={agentSceneDecisionCount}
      data-particle-operation-intents={particleOperationIntentCount}
      data-first-particle-operation-intent={firstParticleOperationIntent}
      data-particle-operation-intent-source={particleOperationIntentSource}
      data-dashboard-particle-budget={dashboardParticleBudget}
      data-layout-text-anchor={currentLayoutState.textAnchor}
      data-layout-text-anchor-basis={currentLayoutState.textAnchorBasis}
      data-layout-text-anchor-points={currentLayoutState.textAnchorPoints}
      data-layout-active-pressure={currentLayoutState.activeLayoutPressure.toFixed(3)}
      data-layout-active-bbox-basis={currentLayoutState.activeBboxBasis}
      data-layout-active-bbox={`${currentLayoutState.activeBboxMinX.toFixed(3)},${currentLayoutState.activeBboxMaxX.toFixed(3)},${currentLayoutState.activeBboxMinY.toFixed(3)},${currentLayoutState.activeBboxMaxY.toFixed(3)}`}
      data-layout-active-regions={currentLayoutState.activeRegions}
      data-layout-orb-scale-hint={currentLayoutState.orbScaleHint}
      data-layout-text-safe-region={currentLayoutState.textSafeRegion}
      data-layout-avoidance-map-basis={currentLayoutState.avoidanceMapBasis}
      data-layout-avoidance-text-safe-lanes={currentLayoutState.avoidanceTextSafeLanes}
      data-layout-avoidance-scene-footprint={avoidanceFootprintLabel}
      data-layout-text-decision-model={textPlacementDecision.model}
      data-layout-text-decision-basis={textPlacementDecision.basis}
      data-layout-text-decision-score={textPlacementDecision.score}
      data-layout-text-decision-blockers={textPlacementDecision.blockerCount}
      data-layout-text-decision-speech-anchor={textPlacementDecision.speechAnchor}
      data-layout-text-decision-self-anchor={textPlacementDecision.selfNarrationAnchor}
      data-layout-text-decision-scene-footprint-avoided={textPlacementDecision.sceneFootprintAvoided ? "true" : "false"}
      data-layout-text-decision-interactive-bbox-avoided={textPlacementDecision.interactiveBboxFootprintAvoided ? "true" : "false"}
      data-layout-text-decision-cartridge-footprint-avoided={textPlacementDecision.cartridgeFootprintAvoided ? "true" : "false"}
      data-layout-text-decision-rendering={textPlacementDecision.textRendering}
      data-layout-text-decision-particle-text={textPlacementDecision.particleText ? "true" : "false"}
      data-layout-collision-state={layoutTelemetry.collisionState}
      data-layout-measured-blockers={layoutTelemetry.blockers}
      data-layout-overlap-px={layoutTelemetry.overlap}
      data-layout-offscreen-px={layoutTelemetry.offscreen}
      data-layout-orb-overlap-px={layoutTelemetry.orbOverlap}
      data-layout-orb-offscreen-px={layoutTelemetry.orbOffscreen}
      data-layout-collision-pressure={splatraDashboardControls.layout_collision_pressure}
      data-layout-self-narration-anchor={currentLayoutState.selfNarrationAnchor}
      data-layout-text-rendering={currentLayoutState.textRendering}
      data-scene-content-source={scenePolicy.scene_content_source ?? "none"}
      data-scene-authoring-basis={scenePolicy.scene_authoring_basis ?? "none"}
      data-visual-affordance-basis={scenePolicy.visual_affordance_basis ?? "none"}
      data-layout-decision-basis={scenePolicy.layout_decision_basis ?? "none"}
      data-topic-scene-templates={scenePolicy.topic_scene_templates === true ? "true" : "false"}
      data-renderer-may-infer-topic={scenePolicy.renderer_may_infer_topic === true ? "true" : "false"}
      data-particle-text={scenePolicy.particle_text === true ? "true" : "false"}
      data-scene-policy-text-rendering={scenePolicy.text_rendering ?? "dom_text_not_particles"}
      data-verified-evidence-required={scenePolicy.verified_evidence_required_for_general_knowledge === true ? "true" : "false"}
      data-splatra-command-sequence={splatraCommandActionCount > 0 ? "available" : "none"}
      data-splatra-command-actions={splatraCommandActionCount}
      data-splatra-candidate-cartridges={splatraCandidateCartridgeCount}
      data-splatra-candidate-cartridge-format={splatraCandidateCartridgeFormat}
      data-splatra-interactive-scene={splatraInteractiveObjectCount > 0 ? "available" : "none"}
      data-splatra-interactive-objects={splatraInteractiveObjectCount}
      data-splatra-interactive-bboxes={splatraInteractiveBboxCount}
      data-splatra-interactive-analysis-basis={splatraInteractiveAnalysisBasis}
      data-splatra-interactive-raw-inference={splatraInteractiveRawInference ? "true" : "false"}
      data-splatra-cartridge-queue={splatraCartridgeQueueStatus}
      data-splatra-cartridge-jobs={splatraCartridgeQueueJobs}
      data-splatra-cartridge-execution-mode={splatraCartridgeQueueMode}
      data-splatra-cartridge-side-channel={String(splatraCartridgeQueue?.side_channel ?? "none")}
      data-splatra-cartridge-external-called={splatraCartridgeQueue?.external_splatra_called === true ? "true" : "false"}
      data-splatra-cartridge-raw-buffer={splatraCartridgeQueue?.raw_buffer_in_agent_context === true ? "true" : "false"}
      data-splatra-cartridge-mutation={splatraCartridgeQueue?.mutation_performed === true ? "true" : "false"}
      data-splatra-sidecar-status={splatraSidecarStatus}
      data-splatra-sidecar-configured={splatraSidecarConfigured ? "true" : "false"}
      data-splatra-sidecar-jobs={splatraSidecarJobs}
      data-splatra-sidecar-raw-cartridge-fetched={splatraSidecarRawCartridgeFetched ? "true" : "false"}
      data-splatra-command-raw-buffers={splatraCommandSequence?.splatra_contract?.raw_buffers_in_agent_context === true ? "true" : "false"}
      data-splatra-command-topic-templates={splatraCommandSequence?.splatra_contract?.topic_scene_templates === true ? "true" : "false"}
      data-splatra-command-renderer-inference={splatraCommandSequence?.splatra_contract?.renderer_may_infer_topic === true ? "true" : "false"}
      data-text-layout-basis={TEXT_LAYOUT_BASIS}
      data-text-layout-reference={TEXT_LAYOUT_REFERENCE}
      style={{ ...dashboardRuntimeLayoutVars(sceneChoreography, stageLayout, layoutTelemetry), ["--orb-dodge-y" as string]: `${orbDodgeY}px` } as CSSProperties}
    >
      {splatraOpen && (
        // AQUARIUM (owner directive): not a floating window — the orb's screen
        // area ITSELF is the particle field. A full-bleed transparent layer over
        // the dashboard (glass in front, 3D behind it), stopping above the
        // composer like the fold scene does. No frame, no shadow, no chrome —
        // the generated model simply exists in the room with the orb.
        <div style={{ position: "absolute", top: 0, left: 0, right: 0, bottom: 84,
                      zIndex: 6, overflow: "hidden", background: "transparent" }}>
          <SplatraField ref={splatraRef} />
          <button type="button" onClick={() => setSplatraOpen(false)} aria-label="dissolve particles"
            style={{ position: "absolute", top: 10, right: 14, background: "transparent",
                     border: "none", color: "#8a8a92", cursor: "pointer", padding: 6, fontSize: 13 }}>
            ✕
          </button>
        </div>
      )}
      <div style={(foldScene || iframeStage)
        ? { opacity: 0, pointerEvents: "none" }
        // aquarium visibility (owner): while a generated model lives on the
        // screen the orb YIELDS THE STAGE — it docks small to the bottom-right
        // corner (cognitively stepping aside), not a ghost fade in place.
        : splatraOpen ? { transform: "translate(36%, 30%) scale(0.32)", opacity: 0.85,
                          transformOrigin: "center", transition: "transform .8s ease, opacity .8s ease",
                          pointerEvents: "none" } : { transition: "transform .8s ease, opacity .8s ease" }}>
        <SplatraImaginationField
          state={orbState}
          mode="product"
          particleBudget={dashboardParticleBudget}
          interactive={false}
          controlOverride={splatraDashboardControls}
          sceneFocus={stageLayout === "scene_focus"}
          scenePlan={sceneChoreography}
          splatraCommandSequence={splatraCommandSequence}
          splatraCartridgeQueue={splatraCartridgeQueue}
          activeSpeechBeatIndex={sceneSpeechBeatIndex}
          className="atanor-dashboard-imagination-field"
        />
      </div>
      {foldScene ? (
        <div style={{ position: "absolute", top: 0, left: 0, right: 0, bottom: 84, zIndex: 5, pointerEvents: "auto", cursor: "grab" }}>
          <PhaseHolographicFoldScene scene={foldScene} />
        </div>
      ) : null}
      {foldScene ? (
        <>
          <div style={{ position: "absolute", left: "calc(var(--atanor-sidebar-w, 240px) + 28px)", top: 78, maxWidth: "34vw", zIndex: 40, pointerEvents: "none" }}>
            <strong style={{ display: "block", color: "#dbe6ff", fontSize: 13.5, letterSpacing: "0.02em" }}>
              {foldScene.render_kind === "local_graph_wave"
                ? (language === "ko" ? "실시간 로컬 그래프 · 파동 간섭장" : "Live local graph · wave interference field")
                : (language === "ko" ? "ATANOR 사고 구조 · 위상 홀로그래픽 폴딩" : "ATANOR thought structure · phase holographic fold")}
            </strong>
            <span style={{ color: "#7d869b", fontSize: 11 }}>
              {foldScene.render_kind === "local_graph_wave"
                ? (language === "ko" ? `노드 ${foldScene.nodes.length} · 각 노드의 파동이 퍼져 겹친 실제 간섭장` : `${foldScene.nodes.length} nodes · real superposed field of each node's wave`)
                : (language === "ko" ? "검증(밝음·중심) · 후보(주황·외곽) · 감정" : "verified (bright, center) · candidate (amber, outer) · emotion")}
            </span>
          </div>
          <button
            onClick={() => { setFoldScene(null); setStageLayout("conversation"); }}
            aria-label={language === "ko" ? "닫기" : "Close"}
            style={{ position: "absolute", top: 18, right: 22, zIndex: 41, width: 34, height: 34, borderRadius: 17, border: "1px solid #2a2f3d", background: "rgba(15,18,26,0.85)", color: "#cfe0ff", cursor: "pointer", fontSize: 18, lineHeight: "32px" }}
          >
            ×
          </button>
        </>
      ) : null}
      {iframeStage ? (
        <>
        <div className="atanor-iframe-backdrop" onClick={() => { setIframeStage(null); setIframeTabs([]); setStageLayout("conversation"); }} aria-hidden="true" />
        <div
          key={iframeTabs[0]?.url ?? iframeStage.url}
          ref={iframeWinRef}
          className={`atanor-iframe-window${iframeBox ? " is-floating" : ""}${iframeBusy ? " is-dragging" : ""}`}
          style={iframeBox ? { left: iframeBox.x, top: iframeBox.y, width: iframeBox.w, height: iframeBox.h, right: "auto", bottom: "auto" } : undefined}
        >
          <div
            onMouseDown={beginIframeGesture("move")}
            style={{ display: "flex", alignItems: "center", gap: 10, padding: "9px 12px", borderBottom: "1px solid #1c2230", background: "rgba(14,18,28,0.95)", cursor: "move", userSelect: "none" }}
          >
            <span aria-hidden="true" style={{ color: "#46506a", fontSize: 13, letterSpacing: 1, marginRight: -2 }}>⠿</span>
            {iframeTabs.length > 1 ? (
              <div className="atanor-iframe-tabs">
                {iframeTabs.map((tab) => (
                  <button
                    key={tab.url}
                    type="button"
                    className={`atanor-iframe-tab${tab.url === iframeStage.url ? " is-active" : ""}`}
                    onClick={() => setIframeStage(tab)}
                    title={tab.title || tab.url}
                  >
                    <span className="atanor-iframe-tab-dot" />
                    <span className="atanor-iframe-tab-label">{tab.title || "page"}</span>
                  </button>
                ))}
              </div>
            ) : (
              <span style={{ color: "#9bb4ff", fontSize: 12.5, whiteSpace: "nowrap" }}>{iframeStage.title}</span>
            )}
            <form
              style={{ flex: 1, display: "flex", gap: 6 }}
              onSubmit={(e) => {
                e.preventDefault();
                const q = iframeQuery.trim();
                if (!q) return;
                const host = /[가-힣]/.test(q) ? "ko.wikipedia.org" : "en.wikipedia.org";
                const newTab = { url: `https://${host}/wiki/Special:Search?search=${encodeURIComponent(q)}`, title: q };
                setIframeTabs((prev) => (prev.length ? [...prev, newTab] : [iframeStage as { url: string; title: string }, newTab]));
                setIframeStage(newTab);
                setIframeQuery("");
              }}
            >
              <input
                value={iframeQuery}
                onChange={(e) => setIframeQuery(e.target.value)}
                placeholder={language === "ko" ? "검색어 입력 후 Enter…" : "Type to search, then Enter…"}
                style={{ flex: 1, minWidth: 0, fontSize: 12.5, padding: "6px 10px", borderRadius: 8, border: "1px solid #2a3550", background: "#0c111c", color: "#dbe6ff" }}
              />
            </form>
            <a href={iframeStage.url} target="_blank" rel="noreferrer" style={{ color: "#7d869b", fontSize: 11, textDecoration: "none", whiteSpace: "nowrap" }}>
              {language === "ko" ? "새 탭 ↗" : "open ↗"}
            </a>
            <button
              onClick={() => { setIframeStage(null); setStageLayout("conversation"); }}
              aria-label={language === "ko" ? "닫기" : "Close"}
              style={{ width: 28, height: 28, borderRadius: 14, border: "1px solid #2a2f3d", background: "rgba(15,18,26,0.85)", color: "#cfe0ff", cursor: "pointer", fontSize: 16, lineHeight: "26px" }}
            >
              ×
            </button>
          </div>
          {(typeof navigator !== "undefined" && navigator.onLine === false) ? (
            <div style={{ flex: 1, display: "flex", alignItems: "center", justifyContent: "center", textAlign: "center", padding: 24, color: "#9aa4bd", fontSize: 13, lineHeight: 1.6 }}>
              {language === "ko"
                ? "오프라인이에요 — 인터넷에 연결되면 검색·문서를 띄울 수 있어요. 그동안에도 로컬 지식으로는 답할 수 있어요."
                : "You're offline — search and documents need an internet connection. I can still answer from local knowledge in the meantime."}
            </div>
          ) : (
            <iframe
              key={iframeStage.url}
              src={iframeStage.url}
              title={iframeStage.title}
              sandbox="allow-scripts allow-same-origin allow-popups allow-forms"
              referrerPolicy="no-referrer"
              style={{ flex: 1, width: "100%", border: 0, background: "#fff" }}
            />
          )}
          <div style={{ padding: "5px 12px", borderTop: "1px solid #1c2230", color: "#5a6478", fontSize: 10.5 }}>
            {language === "ko" ? "일부 사이트는 임베드를 차단합니다 — 그럴 땐 ‘새 탭 ↗’을 누르세요. (표시 전용 · 입력 정보 없음)" : "Some sites block embedding — use ‘open ↗’ then. (display-only · no data entered)"}
          </div>
          {/* Transparent shield: while dragging/resizing the iframe must not eat mouse moves. */}
          {iframeBusy ? <div style={{ position: "absolute", inset: 0, zIndex: 5, cursor: iframeDragRef.current?.mode === "resize" ? "nwse-resize" : "move" }} /> : null}
          {/* Bottom-right resize grip — larger hit area so it's easy to grab. */}
          <div
            onMouseDown={beginIframeGesture("resize")}
            aria-hidden="true"
            title={language === "ko" ? "크기 조절" : "Resize"}
            style={{
              position: "absolute",
              right: 0,
              bottom: 0,
              width: 26,
              height: 26,
              cursor: "nwse-resize",
              zIndex: 7,
              color: "#9bb4ff",
              fontSize: 13,
              lineHeight: "30px",
              textAlign: "center",
              borderTopLeftRadius: 10,
              background: "linear-gradient(135deg, transparent 46%, rgba(120,160,255,0.32) 46%)",
            }}
          >
            <span style={{ position: "absolute", right: 3, bottom: 1 }}>◢</span>
          </div>
        </div>
        </>
      ) : null}
      {graftedNodes.length > 0 ? (
        <div key={graftBatchId} className="atanor-graft-stage" aria-live="polite">
          <div className="atanor-graft-head">
            <span className="atanor-graft-spark" />
            <span>{language === "ko" ? "웹에서 찾아 붙인 새 노드" : "New nodes grafted from the web"}</span>
            <button
              className="atanor-graft-close"
              onClick={() => setGraftedNodes([])}
              aria-label={language === "ko" ? "닫기" : "Close"}
            >
              ×
            </button>
          </div>
          <div className="atanor-graft-nodes">
            {graftedNodes.map((node, index) => (
              <a
                key={node.id ?? node.source_url ?? index}
                className="atanor-graft-node"
                href={node.source_url || undefined}
                target="_blank"
                rel="noreferrer"
                style={{ animationDelay: `${index * 0.16}s` }}
                title={node.definition || node.label || ""}
              >
                <span className="atanor-graft-node-dot" />
                <span className="atanor-graft-node-label">{node.label || "node"}</span>
              </a>
            ))}
          </div>
          <div className="atanor-graft-foot">
            {language === "ko"
              ? "클라우드 브레인에 추가 → 로컬 브레인에 연결 (후보 · 검증 전)"
              : "added to Cloud Brain → linked into Local Brain (candidate · pre-verified)"}
          </div>
        </div>
      ) : null}
      <div className="atanor-hologram-stage">
        <HologramVoiceOrb state={orbState} onActivate={startVoiceMode} onCancel={cancelVoiceMode} density={orbDensityApplied} />
        {typedSelfNarration ? (
          <p ref={selfNarrationRef} className="atanor-hologram-self-narration" aria-live="polite">
            {typedSelfNarration}
          </p>
        ) : null}
        {typedSpeechLine ? (
          <p ref={speechRef} className="atanor-hologram-speech" aria-live="polite">
            {typedSpeechLine}
          </p>
        ) : null}
        {voiceNotice ? (
          <p className="atanor-hologram-voice-status" aria-live="polite">
            {voiceNotice}
          </p>
        ) : null}
      </div>
      {/* Experimental answer interface: GeoGebra-like figure / formula card. */}
      {answerVisual && !foldScene && !iframeStage ? (
        <div className="atanor-answer-experiment-stage" aria-live="polite" ref={answerCardRef}>
          <AnswerExperimentSurface visual={answerVisual} />
        </div>
      ) : null}
      {/* Particle render budget — bottom-left. Max = benchmark-run full count. */}
      <div className="atanor-orb-density" data-iframe-hidden={iframeStage ? "true" : "false"}>
        <span className="atanor-orb-density-label">
          {language === "ko" ? "파티클 렌더링" : "Particle render"}
        </span>
        <input
          type="range"
          min={18}
          max={100}
          step={1}
          value={Math.round(orbDensityDraft * 100)}
          onChange={(e) => setOrbDensityDraft(Number(e.target.value) / 100)}
          onPointerUp={() => commitOrbDensity(orbDensityDraft)}
          onMouseUp={() => commitOrbDensity(orbDensityDraft)}
          onTouchEnd={() => commitOrbDensity(orbDensityDraft)}
          onKeyUp={() => commitOrbDensity(orbDensityDraft)}
          aria-label={language === "ko" ? "파티클 렌더링 밀도" : "Particle render density"}
        />
        <span className="atanor-orb-density-count">
          {(Math.round(ORB_BENCHMARK_MAX_PARTICLES * orbDensityDraft / 100) / 10).toFixed(1)}k
          {orbDensityDraft >= 0.999 ? (language === "ko" ? " · 최대" : " · max") : ""}
        </span>
      </div>
      {/* Composer suggestion chips removed (owner: 밑에 이것들도 없애자) — a clean
          ChatGPT-style composer, no demo phrases competing for attention. */}
      <form ref={composerRef} className="atanor-hologram-composer" data-voice-mode={voiceMode ? "true" : "false"} onSubmit={submitMessage}>
        <button type="button" aria-label={language === "ko" ? "\uC74C\uC131 \uB300\uD654 \uBAA8\uB4DC" : "Voice conversation mode"} onClick={voiceMode ? cancelVoiceMode : startVoiceMode}>
          <Mic size={18} strokeWidth={1.8} />
        </button>
        <div className="atanor-voice-wave" aria-hidden="true">
          {Array.from({ length: 17 }, (_, index) => (
            <span key={index} style={{ "--h": `${8 + (index % 6) * 3}px`, "--i": index } as VoiceWaveStyle} />
          ))}
        </div>
        <input
          aria-label={cleanPlaceholder}
          value={message}
          onChange={(event) => setMessage(event.target.value)}
          placeholder={cleanPlaceholder}
        />
        <button type="submit" aria-label={language === "ko" ? "\uBCF4\uB0B4\uAE30" : "Send"}>
          <Send size={18} strokeWidth={1.8} />
        </button>
      </form>
    </section>
  );
}
