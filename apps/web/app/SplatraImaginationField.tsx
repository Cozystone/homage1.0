"use client";

import { useEffect, useMemo, useRef, useState, type PointerEvent } from "react";

type Archetype =
  | "orb"
  | "tower"
  | "tree"
  | "creature"
  | "circuit"
  | "city_block"
  | "constellation"
  | "machine_core"
  | "abstract_memory_cloud";

type ImaginationMode = "product" | "lab";
type VisualState = "idle" | "listening" | "thinking" | "speaking" | "resting" | "approval_needed" | "blocked";

type Particle = {
  x: number;
  y: number;
  z: number;
  r: number;
  g: number;
  b: number;
  a: number;
  scale: number;
};

type ImaginationObject = {
  archetype?: Archetype;
  particles?: Particle[];
  metadata?: Record<string, any>;
};

type ImaginationFrame = {
  object?: ImaginationObject;
  objects?: ImaginationObject[];
  controls?: Record<string, any>;
  safety_flags?: Record<string, boolean>;
};

type ScenePlanBeat = {
  beat_index?: number;
  op?: "spawn_object" | "morph" | "move" | "focus_camera" | "label" | "despawn";
  archetype?: Archetype;
  prompt?: string;
  narration?: string;
  object_id?: string;
  object_track_id?: string;
  object_track_basis?: string;
  semantic_role?: string;
  visual_affordance?: string;
  spatial_relation?: string;
  pose_hint?: ScenePose;
  surface_features?: string[];
  particle_behavior?: string;
  scene_directive?: {
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
  scene_evidence?: {
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
  physics_hint?: {
    basis?: string;
    field?: string;
    material?: string;
    gravity_bias?: number;
    cohesion?: number;
    trail?: number;
    pose_hint?: ScenePose;
    surface_features?: string[];
  };
  source_fact?: string;
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
};

type SceneBeatOp = "spawn_object" | "morph" | "move" | "focus_camera" | "label" | "despawn";
type SceneMotionRole = "subject" | "source" | "target" | "";
type ScenePose = "standing" | "seated" | "reaching";

type ScenePlan = {
  stage_layout?: "conversation" | "scene_focus";
  orb_anchor?: "center" | "lower_right";
  layout_intent?: "conversation" | "balanced_scene" | "wide_particle_stage";
  primary_surface?: string;
  dashboard_layout?: {
    scene?: {
      central_scale?: number;
      generated_visual_elements?: string;
      line_rendering?: string;
      text_exception?: string;
    };
    stage_safe_region?: {
      scale_strategy?: string;
      primary?: string;
      orb_exclusion?: string;
    };
    agent_layout_decision?: {
      particle_stage_strategy?: string;
      particle_space?: string;
      generated_visual_elements?: string;
      line_rendering?: string;
      flow_motion_reference?: string;
      text_exception?: string;
      orb_self_body_yield?: string;
      particle_recomposition_mode?: string;
      layout_autonomy?: string;
      orb_identity?: string;
    };
  };
  beats?: ScenePlanBeat[];
  speech_timeline?: ScenePlanBeat[];
  layout_timeline?: ScenePlanBeat[];
  agent_scene_decisions?: Array<Record<string, unknown>>;
  particle_operation_intents?: Array<Record<string, unknown>>;
};

type SceneTransform = {
  offsetX: number;
  offsetY: number;
  zoom: number;
};

type CartridgeViewState = {
  yaw: number;
  pitch: number;
  dragging: boolean;
  returning: boolean;
};

type SceneCameraView = {
  targetX: number;
  targetY: number;
  zoom: number;
};

type SceneRenderObject = {
  archetype: Archetype;
  beat: ScenePlanBeat;
  id: string;
  particles: Particle[];
  poseBaseParticles?: Particle[];
};

type ParticleControls = {
  valence: number;
  arousal: number;
  curiosity: number;
  speaking_energy: number;
  resting: boolean;
  fatigue?: number;
  review_pressure?: number;
  novelty_found?: number;
  layout_collision_pressure?: number;
  layout_field_quieting?: number;
  layout_flow_recombine?: number;
  layout_text_avoidance?: string;
};

const PARTICLE_RENDERING_CONTRACT = "all_generated_marks_particle_points_no_canvas_strokes";
const PARTICLE_FLOW_CONTRACT = "flow_lines_are_sparse_particle_marks_not_canvas_paths";
const FLOW_FIELD_BASIS = "magnetic_simplex_inspired_airbend_particles";
const FLOW_MOTION_REFERENCE = "codepen_magnetic_swarm_noise_decay_reference";
const SPLATRA_COMMAND_CONTRACT = "agent_scene_commands_to_particle_cartridges";

type SplatraCommandSequence = {
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
};

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
    jobs?: Array<{
      status?: string;
      viewer_cartridge_url?: string;
      prompt?: string;
      generation_engine?: string | null;
      real_generator_used?: boolean;
      sgf_summary?: {
        num_gaussians?: number;
        raw_bytes?: number;
      };
    }>;
  };
  external_splatra_called?: boolean;
  raw_buffer_in_agent_context?: boolean;
  mutation_performed?: boolean;
};

type SplatraLoadedCartridge = {
  url: string;
  particleCount: number;
  sourceCount: number;
  bbox: {
    minX: number;
    minY: number;
    minZ: number;
    maxX: number;
    maxY: number;
    maxZ: number;
  };
  selectionMode: string;
  materialHint: string;
  reconstructionQualityPath: string;
  realGeneratorUsed: boolean;
  particles: Particle[];
  webgl: {
    positions: Float32Array;
    colors: Float32Array;
    sizes: Float32Array;
  };
};

type WebglCartridgeResources = {
  gl: WebGLRenderingContext | WebGL2RenderingContext;
  program: WebGLProgram;
  positionBuffer: WebGLBuffer;
  colorBuffer: WebGLBuffer;
  sizeBuffer: WebGLBuffer;
  positionLocation: number;
  colorLocation: number;
  sizeLocation: number;
  resolutionLocation: WebGLUniformLocation | null;
  elapsedLocation: WebGLUniformLocation | null;
  zoomLocation: WebGLUniformLocation | null;
  offsetLocation: WebGLUniformLocation | null;
  materialModeLocation: WebGLUniformLocation | null;
  deviceScaleLocation: WebGLUniformLocation | null;
  userYawLocation: WebGLUniformLocation | null;
  userPitchLocation: WebGLUniformLocation | null;
  sourceKey: string;
};

type WebglCartridgeRenderResult = {
  ok: boolean;
  reason: string;
};

const webglCartridgeResources = new WeakMap<HTMLCanvasElement, WebglCartridgeResources>();

type SplatraReadyCartridge = {
  url: string;
  sourceCount: number;
  jobIndex: number;
  generationEngine: string;
  realGeneratorUsed: boolean;
  prompt: string;
};

type Props = {
  mode?: ImaginationMode;
  state?: VisualState;
  particleBudget?: number;
  className?: string;
  interactive?: boolean;
  sceneFocus?: boolean;
  scenePlan?: ScenePlan | null;
  splatraCommandSequence?: SplatraCommandSequence | null;
  splatraCartridgeQueue?: SplatraCartridgeQueuePayload | null;
  activeSpeechBeatIndex?: number;
  controlOverride?: Partial<ParticleControls>;
  onActivate?: () => void;
  onCancel?: () => void;
};

const ARCHETYPES: Archetype[] = [
  "orb",
  "tower",
  "tree",
  "creature",
  "circuit",
  "city_block",
  "constellation",
  "machine_core",
  "abstract_memory_cloud",
];
const PRODUCT_ARCHETYPES: Archetype[] = [
  "constellation",
  "city_block",
  "circuit",
  "tree",
  "machine_core",
  "tower",
  "abstract_memory_cloud",
  "creature",
];
const ARCHETYPE_LABELS: Record<Archetype, string> = {
  orb: "orb",
  tower: "tower",
  tree: "tree",
  creature: "creature",
  circuit: "circuit",
  city_block: "city block",
  constellation: "constellation",
  machine_core: "machine core",
  abstract_memory_cloud: "memory cloud",
};

function normalizeFrame(payload: any): ImaginationFrame {
  const normalizeObject = (item: any): ImaginationObject => ({
    ...item,
    particles: Array.isArray(item?.particles)
      ? item.particles.map((particle: any) => ({
        x: Number(particle.x ?? 0),
        y: Number(particle.y ?? 0),
        z: Number(particle.z ?? 0),
        r: Number(particle.r ?? 0.5),
        g: Number(particle.g ?? 0.8),
        b: Number(particle.b ?? 1),
        a: Number(particle.a ?? 0.5),
        scale: Number(particle.scale ?? Math.max(0.6, Number(particle.radius ?? 0.01) * 120)),
      }))
      : [],
  });
  if (payload?.frame?.objects?.length) {
    return {
      object: normalizeObject(payload.frame.objects[0]),
      objects: payload.frame.objects.map(normalizeObject),
      controls: payload.frame.controls,
      safety_flags: payload.frame.safety_flags ?? payload.safety_flags,
    };
  }
  if (payload?.object) {
    return { ...payload, object: normalizeObject(payload.object) };
  }
  if (payload?.frame?.object) {
    return { ...payload.frame, object: normalizeObject(payload.frame.object) };
  }
  return payload?.frame ?? payload;
}

const STATE_CONTROLS: Record<VisualState, { valence: number; arousal: number; curiosity: number; speaking_energy: number; resting: boolean }> = {
  idle: { valence: 0.58, arousal: 0.34, curiosity: 0.45, speaking_energy: 0.0, resting: false },
  listening: { valence: 0.62, arousal: 0.48, curiosity: 0.7, speaking_energy: 0.08, resting: false },
  thinking: { valence: 0.5, arousal: 0.42, curiosity: 0.86, speaking_energy: 0.0, resting: false },
  speaking: { valence: 0.66, arousal: 0.72, curiosity: 0.56, speaking_energy: 0.88, resting: false },
  resting: { valence: 0.52, arousal: 0.14, curiosity: 0.28, speaking_energy: 0.0, resting: true },
  approval_needed: { valence: 0.48, arousal: 0.64, curiosity: 0.52, speaking_energy: 0.16, resting: false },
  blocked: { valence: 0.25, arousal: 0.55, curiosity: 0.4, speaking_energy: 0.0, resting: false },
};

function clamp(value: number, min: number, max: number) {
  return Math.min(max, Math.max(min, value));
}

function layoutCollisionPressure(controls: ParticleControls) {
  const value = Number(controls.layout_collision_pressure ?? 0);
  return Number.isFinite(value) ? clamp(value, 0, 1) : 0;
}

function layoutFieldQuieting(controls: ParticleControls) {
  const explicit = Number(controls.layout_field_quieting ?? NaN);
  if (Number.isFinite(explicit)) return clamp(explicit, 0, 1);
  return layoutCollisionPressure(controls) * 0.62;
}

function layoutFlowRecombine(controls: ParticleControls) {
  const value = Number(controls.layout_flow_recombine ?? 0);
  return Number.isFinite(value) ? clamp(value, 0, 0.7) : 0;
}

function scenePlanCentralScale(scenePlan: ScenePlan | null | undefined) {
  const value = Number(scenePlan?.dashboard_layout?.scene?.central_scale ?? 1);
  return Number.isFinite(value) ? clamp(value, 0.86, 1.22) : 1;
}

function scenePlanSafeRegionStrategy(scenePlan: ScenePlan | null | undefined) {
  return String(scenePlan?.dashboard_layout?.stage_safe_region?.scale_strategy ?? "ambient_dashboard_fit");
}

function scenePlanParticleStageStrategy(scenePlan: ScenePlan | null | undefined) {
  return String(scenePlan?.dashboard_layout?.agent_layout_decision?.particle_stage_strategy ?? "ambient_self_body");
}

function scenePlanParticleSpace(scenePlan: ScenePlan | null | undefined) {
  return String(scenePlan?.dashboard_layout?.agent_layout_decision?.particle_space ?? "orb_local_field");
}

function scenePlanGeneratedVisualElements(scenePlan: ScenePlan | null | undefined) {
  return String(scenePlan?.dashboard_layout?.agent_layout_decision?.generated_visual_elements ?? scenePlan?.dashboard_layout?.scene?.generated_visual_elements ?? "particle_points_only");
}

function scenePlanLineRendering(scenePlan: ScenePlan | null | undefined) {
  return String(scenePlan?.dashboard_layout?.agent_layout_decision?.line_rendering ?? scenePlan?.dashboard_layout?.scene?.line_rendering ?? "particle_segments_not_canvas_strokes");
}

function scenePlanFlowMotionReference(scenePlan: ScenePlan | null | undefined) {
  return String(scenePlan?.dashboard_layout?.agent_layout_decision?.flow_motion_reference ?? FLOW_MOTION_REFERENCE);
}

function scenePlanTextException(scenePlan: ScenePlan | null | undefined) {
  return String(scenePlan?.dashboard_layout?.agent_layout_decision?.text_exception ?? scenePlan?.dashboard_layout?.scene?.text_exception ?? "dom_text_measured_layout_only");
}

function scenePlanOrbSelfBodyYield(scenePlan: ScenePlan | null | undefined) {
  return String(scenePlan?.dashboard_layout?.agent_layout_decision?.orb_self_body_yield ?? "none");
}

function scenePlanParticleRecompositionMode(scenePlan: ScenePlan | null | undefined) {
  return String(scenePlan?.dashboard_layout?.agent_layout_decision?.particle_recomposition_mode ?? "ambient_orb_particles");
}

function scenePlanLayoutAutonomy(scenePlan: ScenePlan | null | undefined) {
  return String(scenePlan?.dashboard_layout?.agent_layout_decision?.layout_autonomy ?? "conversation_default");
}

function scenePlanOrbIdentity(scenePlan: ScenePlan | null | undefined) {
  return String(scenePlan?.dashboard_layout?.agent_layout_decision?.orb_identity ?? "atanor_primary_self_body");
}

function particleOperationForSceneBeat(beat: ScenePlanBeat | undefined) {
  if (beat?.op === "move" || beat?.motion_path) return "animate_particle_motion_path";
  if (beat?.op === "focus_camera") return "focus_particle_cluster";
  if (beat?.op === "morph") return "recompose_particle_cluster";
  if (beat?.op === "despawn") return "disperse_particle_cluster";
  if (beat?.op) return "assemble_particle_cluster";
  return "none";
}

function sceneBeatParticleDensity(beat: ScenePlanBeat | null | undefined, active = false) {
  if (!beat) return 1;
  const operation = particleOperationForSceneBeat(beat);
  const affordance = String(beat.visual_affordance ?? "");
  const behavior = String(beat.particle_behavior ?? "");
  const cohesion = physicsNumber(beat, "cohesion", 0.56);
  const trail = physicsNumber(beat, "trail", 0.34);
  let density = active ? 1.28 : 1;
  if (operation === "animate_particle_motion_path") density += active ? 0.76 : 0.4;
  if (operation === "focus_particle_cluster") density += active ? 0.44 : 0.24;
  if (operation === "recompose_particle_cluster") density += active ? 0.52 : 0.3;
  if (operation === "disperse_particle_cluster") density += 0.18;
  if (affordance === "small_moving_object") density += 0.22;
  if (affordance === "entity_figure" || affordance === "organic_structure") density += 0.12;
  if (behavior === "gravity_arc") density += active ? 0.52 : 0.3;
  if (behavior === "kinetic_flow" || behavior === "magnetic_field") density += active ? 0.34 : 0.2;
  density += clamp((cohesion - 0.5) * 0.32 + trail * 0.18, -0.12, 0.36);
  return clamp(density, 0.9, active ? 5.05 : 3.55);
}

function sceneParticleIntentForBeat(scenePlan: ScenePlan | null | undefined, beat: ScenePlanBeat | null | undefined, beatIndex = -1) {
  if (!beat || !Array.isArray(scenePlan?.particle_operation_intents)) return null;
  const trackId = sceneObjectTrackId(beat, Math.max(0, beatIndex));
  const objectId = String(beat.object_id ?? "");
  return (scenePlan?.particle_operation_intents ?? []).find((intent) => {
    const intentBeatIndex = Number(intent?.beat_index);
    const intentTrack = String(intent?.object_track_id ?? "");
    const intentObject = String(intent?.object_id ?? "");
    return (
      (Number.isFinite(intentBeatIndex) && beatIndex >= 0 && intentBeatIndex === beatIndex)
      || (trackId && intentTrack && intentTrack === trackId)
      || (objectId && intentObject && intentObject === objectId)
    );
  }) ?? null;
}

function sceneParticleIntentDensity(intent: Record<string, unknown> | null | undefined, beat: ScenePlanBeat | null | undefined, active = false) {
  const base = sceneBeatParticleDensity(beat, active);
  const operation = String(intent?.operation ?? particleOperationForSceneBeat(beat ?? undefined));
  const agentControl = String(intent?.agent_control ?? "");
  const verifiedIntentBoost = agentControl === "airbend_recompose_particles_inside_safe_region" ? 0.18 : 0;
  if (operation === "animate_particle_motion_path") return clamp(base + verifiedIntentBoost + (active ? 0.9 : 0.46), 0.9, active ? 5.25 : 3.65);
  if (operation === "recompose_particle_cluster") return clamp(base + verifiedIntentBoost + 0.24, 0.8, active ? 3.35 : 2.35);
  if (operation === "focus_particle_cluster") return clamp(base + verifiedIntentBoost + 0.18, 0.8, active ? 3.1 : 2.2);
  return clamp(base + verifiedIntentBoost, 0.78, active ? 3.0 : 2.15);
}

function smoothstep(value: number) {
  const t = clamp(value, 0, 1);
  return t * t * (3 - 2 * t);
}

function stableUnit(value: string, salt = 0) {
  let hash = 2166136261 ^ salt;
  for (let index = 0; index < value.length; index += 1) {
    hash ^= value.charCodeAt(index);
    hash = Math.imul(hash, 16777619);
  }
  return (hash >>> 0) / 4294967295;
}

function flowFieldAngle(x: number, y: number, elapsed: number, salt = 0) {
  const low = Math.sin(x * 0.006 + elapsed * 0.36 + salt) + Math.cos(y * 0.005 - elapsed * 0.29);
  const high = Math.sin((x + y) * 0.0028 + elapsed * 0.48 + salt * 1.7);
  return (low * 0.72 + high * 0.46) * Math.PI;
}

function flowFieldDisplacement(x: number, y: number, elapsed: number, strength: number, salt = 0) {
  const angle = flowFieldAngle(x, y, elapsed, salt);
  const cross = flowFieldAngle(y * 0.74 + salt * 13, x * 0.68 - salt * 7, elapsed * 0.82, salt + 11);
  const breath = 0.52 + 0.48 * Math.sin(elapsed * 0.41 + salt * 1.9);
  return {
    x: Math.cos(angle) * strength + Math.cos(cross + Math.PI / 2) * strength * 0.42 * breath,
    y: Math.sin(angle) * strength + Math.sin(cross + Math.PI / 2) * strength * 0.42 * breath,
    angle,
  };
}

function drawParticleStroke(
  ctx: CanvasRenderingContext2D,
  x: number,
  y: number,
  angle: number,
  length: number,
  size: number,
  color: [number, number, number],
  alpha: number,
) {
  const dx = Math.cos(angle) * length;
  const dy = Math.sin(angle) * length;
  const nx = -Math.sin(angle);
  const ny = Math.cos(angle);
  const [r, g, b] = color;
  const steps = Math.max(8, Math.min(24, Math.round(length / Math.max(0.68, size * 0.42))));
  for (let step = 0; step <= steps; step += 1) {
    const t = step / steps;
    const keep = step === 0 || step === steps || seeded(step, x * 0.017 + y * 0.011 + angle) > 0.24;
    if (!keep) continue;
    const taper = Math.sin(t * Math.PI);
    const curl = Math.sin(t * Math.PI * 2.35 + x * 0.004 + y * 0.003) * length * 0.085;
    const shear = Math.cos(t * Math.PI * 3.1 + angle) * length * 0.028;
    const noise = (seeded(step, x * 0.031 + y * 0.019) - 0.5) * length * 0.11;
    const px = x - dx * 0.26 + dx * 1.18 * t + nx * (curl + noise) + Math.cos(angle) * shear;
    const py = y - dy * 0.26 + dy * 1.18 * t + ny * (curl + noise) + Math.sin(angle) * shear;
    const pointAlpha = alpha * (0.055 + taper * 0.34 + t * 0.12);
    const pointSize = size * (0.09 + taper * 0.18 + t * 0.055);
    ctx.fillStyle = `rgba(${r}, ${g}, ${b}, ${pointAlpha})`;
    ctx.beginPath();
    ctx.arc(px, py, pointSize, 0, Math.PI * 2);
    ctx.fill();
  }
}

function seeded(index: number, salt = 0) {
  const value = Math.sin(index * 12.9898 + salt * 78.233) * 43758.5453123;
  return value - Math.floor(value);
}

function drawGuideParticle(
  ctx: CanvasRenderingContext2D,
  x: number,
  y: number,
  size: number,
  color: [number, number, number],
  alpha: number,
) {
  const [r, g, b] = color;
  ctx.fillStyle = `rgba(${r}, ${g}, ${b}, ${alpha})`;
  ctx.beginPath();
  ctx.arc(x, y, size, 0, Math.PI * 2);
  ctx.fill();
}

function drawParticleSegment(
  ctx: CanvasRenderingContext2D,
  from: [number, number],
  to: [number, number],
  color: [number, number, number],
  alpha: number,
  unit: number,
  salt = 0,
  elapsed = 0,
) {
  const dx = to[0] - from[0];
  const dy = to[1] - from[1];
  const distance = Math.hypot(dx, dy);
  const steps = Math.max(11, Math.ceil(distance / Math.max(12, unit * 0.033)));
  const normalX = distance > 0 ? -dy / distance : 0;
  const normalY = distance > 0 ? dx / distance : 0;
  const tangentX = distance > 0 ? dx / distance : 1;
  const tangentY = distance > 0 ? dy / distance : 0;
  const streamCount = distance > unit * 0.42 ? 5 : 3;
  for (let lane = 0; lane < streamCount; lane += 1) {
    for (let index = 0; index <= steps; index += 1) {
      const rawT = index / steps;
      const t = (rawT + elapsed * (0.018 + lane * 0.011) + seeded(index, salt + lane * 101) * 0.055) % 1;
      if (index > 0 && index < steps && seeded(index, salt + lane * 37 + 41) < 0.48) continue;
      const phase = t * Math.PI * 6 + salt * 0.037 + elapsed * (1.15 + lane * 0.21);
      const laneCenter = (streamCount - 1) / 2;
      const laneOffset = (lane - laneCenter) * unit * 0.032;
      const curl = Math.sin(phase) * unit * (0.036 + seeded(index, salt + 5) * 0.047);
      const shear = Math.cos(phase * 0.63 + salt) * unit * 0.026;
      const baseX = from[0] + dx * t + normalX * (laneOffset + curl) + tangentX * shear;
      const baseY = from[1] + dy * t + normalY * (laneOffset + curl) + tangentY * shear;
      const flow = flowFieldDisplacement(baseX, baseY, elapsed, unit * (0.012 + seeded(index, salt + lane * 29) * 0.024), salt + lane * 3);
      const pulse = 0.46 + 0.54 * Math.sin(t * Math.PI);
      drawGuideParticle(
        ctx,
        baseX + flow.x,
        baseY + flow.y,
        unit * (0.00046 + seeded(index, salt + lane * 53 + 7) * 0.00082) * (0.72 + pulse * 0.3),
        color,
        alpha * (0.018 + pulse * 0.07) * (lane === Math.round(laneCenter) ? 0.62 : 0.36),
      );
    }
  }
}

function drawParticlePolyline(
  ctx: CanvasRenderingContext2D,
  points: Array<[number, number]>,
  color: [number, number, number],
  alpha: number,
  unit: number,
  salt = 0,
  elapsed = 0,
) {
  for (let index = 0; index < points.length - 1; index += 1) {
    drawParticleSegment(ctx, points[index], points[index + 1], color, alpha, unit, salt + index * 17, elapsed);
  }
}

function drawParticleEllipse(
  ctx: CanvasRenderingContext2D,
  cx: number,
  cy: number,
  rx: number,
  ry: number,
  rotation: number,
  color: [number, number, number],
  alpha: number,
  unit: number,
  salt = 0,
  elapsed = 0,
) {
  const steps = Math.max(30, Math.ceil((rx + ry) / Math.max(6, unit * 0.015)));
  for (let index = 0; index < steps; index += 1) {
    const t = (index / steps) * Math.PI * 2;
    const rawX = Math.cos(t) * rx;
    const rawY = Math.sin(t) * ry;
    const jitter = Math.sin(t * 3 + elapsed * 1.1 + salt) * unit * 0.003;
    const x = cx + rawX * Math.cos(rotation) - rawY * Math.sin(rotation) + Math.cos(t) * jitter;
    const y = cy + rawX * Math.sin(rotation) + rawY * Math.cos(rotation) + Math.sin(t) * jitter;
    drawGuideParticle(
      ctx,
      x,
      y,
      unit * (0.0018 + seeded(index, salt + 3) * 0.0018),
      color,
      alpha * (0.22 + seeded(index, salt + 9) * 0.46),
    );
  }
}

function drawParticleRect(
  ctx: CanvasRenderingContext2D,
  x: number,
  y: number,
  w: number,
  h: number,
  color: [number, number, number],
  alpha: number,
  unit: number,
  salt = 0,
  elapsed = 0,
) {
  drawParticlePolyline(ctx, [[x, y], [x + w, y], [x + w, y + h], [x, y + h], [x, y]], color, alpha, unit, salt, elapsed);
}

function drawAmbientAirbendField(
  ctx: CanvasRenderingContext2D,
  width: number,
  height: number,
  elapsed: number,
  controls: ParticleControls,
) {
  const unit = Math.min(width, height);
  const cx = width / 2;
  const cy = height / 2;
  const pressure = layoutCollisionPressure(controls);
  const fieldQuieting = layoutFieldQuieting(controls);
  const flowRecombine = layoutFlowRecombine(controls);
  const count = Math.round(clamp((width * height) / (3600 + fieldQuieting * 1800), 220, 920));
  const attraction = controls.resting
    ? 0.1
    : 0.18 + controls.curiosity * 0.18 + controls.speaking_energy * 0.2 + flowRecombine * 0.18;
  const fieldBreath = (Math.sin(elapsed * 0.22) + 1) * 0.5;

  for (let index = 0; index < count; index += 1) {
    const baseX = seeded(index, 7101) * width;
    const baseY = seeded(index, 7102) * height;
    const orbitAngle = elapsed * (0.035 + seeded(index, 7103) * 0.045) + seeded(index, 7104) * Math.PI * 2;
    const orbitRadiusX = width * (0.14 + seeded(index, 7105) * 0.42);
    const orbitRadiusY = height * (0.1 + seeded(index, 7106) * 0.28);
    const targetX = cx + Math.cos(orbitAngle) * orbitRadiusX;
    const targetY = cy + Math.sin(orbitAngle * 1.27) * orbitRadiusY;
    let x = baseX * (1 - attraction) + targetX * attraction;
    let y = baseY * (1 - attraction) + targetY * attraction;

    const centerDistance = Math.hypot(x - cx, y - cy);
    const bodyClearRadius = unit * (0.25 + pressure * 0.08);
    if (centerDistance < bodyClearRadius) {
      const push = (bodyClearRadius - centerDistance) / Math.max(1, bodyClearRadius);
      const angle = Math.atan2(y - cy, x - cx) || orbitAngle;
      x += Math.cos(angle) * push * unit * 0.22;
      y += Math.sin(angle) * push * unit * 0.22;
    }

    const field = flowFieldDisplacement(x, y, elapsed, unit * (0.006 + flowRecombine * 0.02), index * 0.37);
    x += field.x;
    y += field.y;
    const fieldAngle = field.angle;
    const hueShift = Math.sin(elapsed * 0.18 + index * 0.11);
    const color: [number, number, number] = hueShift > 0.28
      ? [255, 104, 177]
      : hueShift < -0.34
        ? [138, 117, 255]
        : [76, 230, 255];
    const size = unit * (0.00058 + seeded(index, 7110) * 0.00105);
    const length = unit * (0.0038 + controls.curiosity * 0.0058 + fieldBreath * 0.0036 + controls.speaking_energy * 0.006 + flowRecombine * 0.007);
    const alpha = (controls.resting ? 0.026 : 0.038 + controls.arousal * 0.016 + controls.speaking_energy * 0.025)
      * (0.48 + seeded(index, 7111) * 0.82)
      * (1 - fieldQuieting * 0.34)
      * 0.72;
    drawParticleStroke(ctx, x, y, fieldAngle, length, size, color, alpha);
  }
}

function sceneBeatIndex(scenePlan: ScenePlan | null | undefined, elapsedSeconds: number): number {
  const beats = Array.isArray(scenePlan?.beats) ? scenePlan?.beats ?? [] : [];
  if (!beats.length) return -1;
  let activeIndex = 0;
  beats.forEach((beat, index) => {
    const start = Number.isFinite(Number(beat.t_start)) ? Number(beat.t_start) : index * 1.25;
    if (elapsedSeconds >= start) activeIndex = index;
  });
  return activeIndex;
}

function sceneArchetype(scenePlan: ScenePlan | null | undefined, beatIndex = -1): Archetype | null {
  const beats = Array.isArray(scenePlan?.beats) ? scenePlan?.beats ?? [] : [];
  const activeBeat = beatIndex >= 0 ? beats[beatIndex] : null;
  if (activeBeat?.archetype && PRODUCT_ARCHETYPES.includes(activeBeat.archetype)) return activeBeat.archetype;
  const explicit = beats.find((beat) => beat.archetype && PRODUCT_ARCHETYPES.includes(beat.archetype))?.archetype;
  if (explicit) return explicit;
  const prompt = beats.map((beat) => `${beat.prompt ?? ""} ${beat.object_id ?? ""}`).join(" ").trim();
  if (!prompt) return null;
  const hash = Array.from(prompt).reduce((acc, char) => ((acc * 31) + char.charCodeAt(0)) >>> 0, 2166136261);
  return PRODUCT_ARCHETYPES[hash % PRODUCT_ARCHETYPES.length];
}

function sceneTransform(beat: ScenePlanBeat | null | undefined, stageMode: boolean, elapsedSeconds = 0): SceneTransform {
  if (!stageMode || !beat) return { offsetX: 0, offsetY: 0, zoom: 1 };
  const position = Array.isArray(beat.position) ? beat.position : [];
  const camera = beat.camera && typeof beat.camera === "object" ? beat.camera : {};
  const cameraTarget = Array.isArray(camera.target) ? camera.target : [];
  const rawX = Number(position[0] ?? cameraTarget[0] ?? 0);
  const rawY = Number(position[1] ?? cameraTarget[1] ?? 0);
  const rawZoom = Number(camera.zoom ?? camera.distance ?? 1);
  const opBias = beat.op === "focus_camera" ? 1.08 : beat.op === "move" ? 1.16 : beat.op === "despawn" ? 0.82 : 1;
  const motionBias = beat.op === "move" ? 1.45 : 1;
  const beatStart = Number.isFinite(Number(beat.t_start)) ? Number(beat.t_start) : 0;
  const duration = Math.max(0.1, Number.isFinite(Number(beat.duration)) ? Number(beat.duration) : 1.2);
  const progress = smoothstep((elapsedSeconds - beatStart) / duration);
  const flowKey = `${beat.object_id ?? ""}:${beat.prompt ?? ""}:${beat.semantic_role ?? ""}`;
  const moveX = beat.op === "move" ? (stableUnit(flowKey, 11) - 0.5) * 0.18 * Math.sin(progress * Math.PI) : 0;
  const moveY = beat.op === "move" ? (stableUnit(flowKey, 19) - 0.5) * 0.12 * Math.sin(progress * Math.PI) : 0;
  return {
    offsetX: clamp((Number.isFinite(rawX) ? rawX * 0.08 * motionBias : 0) + moveX, -0.34, 0.34),
    offsetY: clamp((Number.isFinite(rawY) ? -rawY * 0.08 * motionBias : 0) + moveY, -0.28, 0.28),
    zoom: clamp((Number.isFinite(rawZoom) ? rawZoom : 1) * opBias * (beat.op === "move" ? 1 + progress * 0.05 : 1), 0.72, 1.42),
  };
}

function sceneBeatFocusProgress(beat: ScenePlanBeat | null | undefined, elapsedSeconds: number) {
  if (!beat) return 0;
  const start = Number.isFinite(Number(beat.t_start)) ? Number(beat.t_start) : 0;
  const duration = Math.max(0.1, Number.isFinite(Number(beat.duration)) ? Number(beat.duration) : 1.2);
  const leadIn = beat.op === "focus_camera" || beat.op === "move" || beat.motion_path ? 0.48 : 0.22;
  const focusWindow = Math.max(0.46, duration * 0.62);
  return smoothstep((elapsedSeconds - (start - leadIn)) / focusWindow);
}

function sceneCameraView(beat: ScenePlanBeat | null | undefined, stageMode: boolean, elapsedSeconds = 0): SceneCameraView {
  if (!stageMode || !beat) return { targetX: 0, targetY: 0, zoom: 1 };
  const position = Array.isArray(beat.position) ? beat.position : [];
  const camera = beat.camera && typeof beat.camera === "object" ? beat.camera : {};
  const cameraTarget = Array.isArray(camera.target) ? camera.target : [];
  const pathCameraTarget = beat.op === "move" && Array.isArray(beat.motion_path?.from) && Array.isArray(beat.motion_path?.to)
    ? sceneMotionPathPoint(beat, elapsedSeconds)
    : null;
  const rawTargetX = Number(pathCameraTarget?.x ?? cameraTarget[0] ?? position[0] ?? 0);
  const rawTargetY = Number(pathCameraTarget?.y ?? cameraTarget[1] ?? position[1] ?? 0);
  const rawZoom = Number(camera.zoom ?? 1);
  const progress = sceneBeatFocusProgress(beat, elapsedSeconds);
  const focusBias = beat.op === "focus_camera" ? 0.16 : beat.op === "move" ? 0.08 : 0;
  return {
    targetX: Number.isFinite(rawTargetX) ? rawTargetX * progress : 0,
    targetY: Number.isFinite(rawTargetY) ? rawTargetY * progress : 0,
    zoom: clamp(1 + ((Number.isFinite(rawZoom) ? rawZoom : 1) + focusBias - 1) * progress, 0.82, 1.56),
  };
}

function sceneObjectPosition(beat: ScenePlanBeat | null | undefined) {
  const position = Array.isArray(beat?.position) ? beat?.position ?? [] : [];
  return {
    x: Number.isFinite(Number(position[0])) ? Number(position[0]) : 0,
    y: Number.isFinite(Number(position[1])) ? Number(position[1]) : 0,
  };
}

function physicsNumber(beat: ScenePlanBeat | null | undefined, key: "gravity_bias" | "cohesion" | "trail", fallback: number) {
  const value = Number(beat?.physics_hint?.[key] ?? fallback);
  return Number.isFinite(value) ? clamp(value, 0, 1.5) : fallback;
}

function sceneMotionPathPoint(beat: ScenePlanBeat | null | undefined, elapsedSeconds: number) {
  const from = Array.isArray(beat?.motion_path?.from) ? beat?.motion_path?.from ?? [] : [];
  const to = Array.isArray(beat?.motion_path?.to) ? beat?.motion_path?.to ?? [] : [];
  if (from.length < 2 || to.length < 2) return sceneObjectPosition(beat);
  const progress = sceneObjectProgress(beat as ScenePlanBeat, elapsedSeconds);
  const arc = Math.sin(progress * Math.PI) * 0.22;
  const fromX = Number.isFinite(Number(from[0])) ? Number(from[0]) : 0;
  const fromY = Number.isFinite(Number(from[1])) ? Number(from[1]) : 0;
  const toX = Number.isFinite(Number(to[0])) ? Number(to[0]) : 0;
  const toY = Number.isFinite(Number(to[1])) ? Number(to[1]) : 0;
  const gravityBias = physicsNumber(beat, "gravity_bias", 0.28);
  const behavior = String(beat?.particle_behavior ?? "");
  const lift = behavior === "gravity_arc" ? 0.17 : 0.22;
  const downwardPull = behavior === "gravity_arc" ? progress * progress * gravityBias * 0.18 : 0;
  return {
    x: fromX * (1 - progress) + toX * progress,
    y: fromY * (1 - progress) + toY * progress + arc * lift / 0.22 - downwardPull,
  };
}

function scenePointToCanvas(
  beat: ScenePlanBeat,
  point: { x: number; y: number },
  width: number,
  height: number,
  sceneElapsed: number,
  swing = { x: 0, y: 0 },
  cameraView: SceneCameraView = { targetX: 0, targetY: 0, zoom: 1 },
) {
  const transform = sceneTransform(beat, true, sceneElapsed);
  const viewX = (point.x - cameraView.targetX) * cameraView.zoom;
  const viewY = (point.y - cameraView.targetY) * cameraView.zoom;
  return {
    x: width / 2 + (viewX * 0.34 + transform.offsetX * 0.38 + swing.x) * width,
    y: height / 2 + (-viewY * 0.28 + transform.offsetY * 0.38 + swing.y) * height,
  };
}

function sceneObjectProgress(beat: ScenePlanBeat, elapsedSeconds: number) {
  const start = Number.isFinite(Number(beat.t_start)) ? Number(beat.t_start) : 0;
  const duration = Math.max(0.1, Number.isFinite(Number(beat.duration)) ? Number(beat.duration) : 1.2);
  return smoothstep((elapsedSeconds - start) / duration);
}

function sceneMotionSourceHold(beat: ScenePlanBeat, elapsedSeconds: number) {
  if (!beat.motion_path && beat.op !== "move") return 0;
  const start = Number.isFinite(Number(beat.t_start)) ? Number(beat.t_start) : 0;
  const leadIn = clamp((elapsedSeconds - (start - 0.72)) / 0.72, 0, 1);
  const beforeMotion = elapsedSeconds < start ? 1 : 0;
  return smoothstep(leadIn) * beforeMotion;
}

function sceneObjectAlpha(beat: ScenePlanBeat, elapsedSeconds: number, active: boolean) {
  const start = Number.isFinite(Number(beat.t_start)) ? Number(beat.t_start) : 0;
  const sourceHold = sceneMotionSourceHold(beat, elapsedSeconds);
  if (elapsedSeconds < start - 0.16 && sourceHold <= 0) return 0;
  const reveal = sceneObjectProgress(beat, elapsedSeconds);
  const sourceHoldBase = sourceHold > 0 ? 0.18 + sourceHold * 0.28 : 0;
  const base = beat.op === "despawn" ? 1 - reveal : Math.max(sourceHoldBase, 0.24, reveal);
  return clamp(base * (active ? 1 : 0.42), 0, 1);
}

function sceneFigurePoseProgress(beat: ScenePlanBeat, elapsedSeconds: number) {
  if (String(beat.visual_affordance ?? "") !== "entity_figure") return 1;
  const pose = scenePoseForBeat(beat);
  if (pose === "standing") return 1;
  const start = Number.isFinite(Number(beat.t_start)) ? Number(beat.t_start) : 0;
  const duration = Math.max(0.24, Number.isFinite(Number(beat.duration)) ? Number(beat.duration) : 1.2);
  return smoothstep((elapsedSeconds - start) / Math.min(1.2, Math.max(0.46, duration * 0.58)));
}

function sceneMotionRole(beat: ScenePlanBeat): SceneMotionRole {
  const role = String(beat.semantic_role ?? "");
  if (role === "verified_motion_subject") return "subject";
  if (role === "verified_motion_source") return "source";
  if (role === "verified_motion_target") return "target";
  return "";
}

function sceneRoleStyle(beat: ScenePlanBeat, active: boolean) {
  const role = String(beat.semantic_role ?? "");
  const affordance = String(beat.visual_affordance ?? "");
  const motionRole = sceneMotionRole(beat);
  const moving = beat.op === "move" || role.includes("motion");
  const relation = role.includes("relation");
  const anchor = role.includes("anchor");
  const smallObject = affordance === "small_object" || affordance === "small_moving_object";
  const figure = affordance === "entity_figure";
  const organic = affordance === "organic_structure";
  const behavior = String(beat.particle_behavior ?? "");
  const cohesion = physicsNumber(beat, "cohesion", 0.56);
  const trailHint = physicsNumber(beat, "trail", 0.34);
  const physicsTrailBoost = behavior === "gravity_arc" ? 0.34 : behavior === "kinetic_flow" ? 0.22 : behavior === "magnetic_field" ? 0.16 : 0;
  const physicsScaleBoost = (cohesion - 0.5) * 0.18;
  if (motionRole === "subject") {
    return {
      alpha: active ? 1.46 : 1.24,
      scale: (smallObject ? 0.5 : 0.72) + physicsScaleBoost,
      trail: (active ? 1.38 : 0.94) + trailHint * 0.16 + physicsTrailBoost,
      focus: active ? 1.08 : 0.9,
    };
  }
  if (motionRole === "source") {
    return {
      alpha: active ? 1.08 : 0.86,
      scale: (organic ? 1.28 : 1.02) + physicsScaleBoost,
      trail: (active ? 0.34 : 0.18) + trailHint * 0.08,
      focus: active ? 0.92 : 0.62,
    };
  }
  if (motionRole === "target") {
    return {
      alpha: active ? 1.18 : 0.92,
      scale: (figure ? 1.12 : 1.04) + physicsScaleBoost,
      trail: (active ? 0.48 : 0.26) + trailHint * 0.1,
      focus: active ? 1 : 0.72,
    };
  }
  return {
    alpha: smallObject ? 1.32 : moving ? 1.16 : relation ? 1.02 : anchor ? 0.86 : 0.94,
    scale: (smallObject ? 0.56 : organic ? 1.22 : figure ? 1.06 : moving ? 1.2 : relation ? 1.08 : anchor ? 0.92 : 1) + physicsScaleBoost,
    trail: (smallObject && moving ? (active ? 1.18 : 0.78) : moving ? (active ? 1 : 0.62) : relation ? 0.34 : 0.16) + trailHint * 0.12 + physicsTrailBoost,
    focus: active ? 1 : smallObject ? 0.82 : moving ? 0.72 : 0.48,
  };
}

function sceneObjectId(beat: ScenePlanBeat, index: number) {
  return `${beat.object_id || beat.prompt || "scene"}:${index}`;
}

function sceneObjectTrackId(beat: ScenePlanBeat, index = 0) {
  return String(beat.object_track_id || beat.object_id || beat.prompt || `scene-track-${index}`);
}

function sceneBeatStart(beat: ScenePlanBeat | null | undefined) {
  const value = Number(beat?.t_start ?? 0);
  return Number.isFinite(value) ? value : 0;
}

function sameSceneGroup(left: ScenePlanBeat | null | undefined, right: ScenePlanBeat | null | undefined) {
  const leftGroup = String(left?.scene_group_id ?? "");
  const rightGroup = String(right?.scene_group_id ?? "");
  return Boolean(leftGroup && rightGroup && leftGroup === rightGroup);
}

function firstEvidenceBearingBeat(scenePlan: ScenePlan | null | undefined) {
  const sources = [
    ...(Array.isArray(scenePlan?.speech_timeline) ? scenePlan?.speech_timeline ?? [] : []),
    ...(Array.isArray(scenePlan?.layout_timeline) ? scenePlan?.layout_timeline ?? [] : []),
    ...(Array.isArray(scenePlan?.beats) ? scenePlan?.beats ?? [] : []),
  ];
  return sources.find((beat) => beat?.scene_evidence || beat?.scene_directive) ?? null;
}

function sceneBeatModelPoints(beat: ScenePlanBeat, sceneElapsed: number) {
  const points = [sceneObjectPosition(beat), sceneMotionPathPoint(beat, sceneElapsed)];
  const from = Array.isArray(beat.motion_path?.from) ? beat.motion_path?.from ?? [] : [];
  const to = Array.isArray(beat.motion_path?.to) ? beat.motion_path?.to ?? [] : [];
  if (from.length >= 2) {
    points.push({
      x: Number.isFinite(Number(from[0])) ? Number(from[0]) : 0,
      y: Number.isFinite(Number(from[1])) ? Number(from[1]) : 0,
    });
  }
  if (to.length >= 2) {
    points.push({
      x: Number.isFinite(Number(to[0])) ? Number(to[0]) : 0,
      y: Number.isFinite(Number(to[1])) ? Number(to[1]) : 0,
    });
  }
  return points;
}

function sceneGroupCameraView(activeObject: SceneRenderObject | null, visibleObjects: SceneRenderObject[], sceneElapsed: number): SceneCameraView {
  const baseView = sceneCameraView(activeObject?.beat, true, sceneElapsed);
  if (!activeObject) return baseView;
  const groupObjects = visibleObjects.filter((object) => sameSceneGroup(object.beat, activeObject.beat));
  if (groupObjects.length < 2) return baseView;
  const points = groupObjects.flatMap((object) => sceneBeatModelPoints(object.beat, sceneElapsed));
  if (points.length < 2) return baseView;
  const xs = points.map((point) => point.x);
  const ys = points.map((point) => point.y);
  const minX = Math.min(...xs);
  const maxX = Math.max(...xs);
  const minY = Math.min(...ys);
  const maxY = Math.max(...ys);
  const spread = Math.max(maxX - minX, maxY - minY);
  const groupTargetX = (minX + maxX) / 2;
  const groupTargetY = (minY + maxY) / 2;
  const groupZoom = clamp(1.48 - spread * 0.34 + groupObjects.length * 0.018, 0.9, 1.46);
  const motionFocusBoost = sceneMotionFocusBoost(activeObject.beat);
  const zoomCeiling = groupZoom + motionFocusBoost * 0.72;
  return {
    targetX: baseView.targetX * 0.38 + groupTargetX * 0.62,
    targetY: baseView.targetY * 0.38 + groupTargetY * 0.62,
    zoom: clamp(Math.min(baseView.zoom + motionFocusBoost, zoomCeiling), 0.82, 1.68),
  };
}

function sceneCameraTransitionBlend(beat: ScenePlanBeat | null | undefined, sceneElapsed: number) {
  if (!beat) return 1;
  const start = Number.isFinite(Number(beat.t_start)) ? Number(beat.t_start) : 0;
  const transition = beat.op === "focus_camera" || beat.op === "move" || beat.motion_path ? 0.56 : 0.36;
  return smoothstep((sceneElapsed - start) / transition);
}

function previousSceneFocusObject(activeObject: SceneRenderObject | null, visibleObjects: SceneRenderObject[]) {
  if (!activeObject) return null;
  const activeStart = Number.isFinite(Number(activeObject.beat.t_start)) ? Number(activeObject.beat.t_start) : 0;
  return visibleObjects
    .filter((object) => object.id !== activeObject.id)
    .filter((object) => {
      const start = Number.isFinite(Number(object.beat.t_start)) ? Number(object.beat.t_start) : 0;
      return start < activeStart;
    })
    .sort((left, right) => Number(right.beat.t_start ?? 0) - Number(left.beat.t_start ?? 0))[0] ?? null;
}

function blendedSceneCameraView(activeObject: SceneRenderObject | null, visibleObjects: SceneRenderObject[], sceneElapsed: number): SceneCameraView {
  const current = sceneGroupCameraView(activeObject, visibleObjects, sceneElapsed);
  const previousObject = previousSceneFocusObject(activeObject, visibleObjects);
  if (!activeObject || !previousObject) return current;
  const blend = sceneCameraTransitionBlend(activeObject.beat, sceneElapsed);
  if (blend >= 0.995) return current;
  const previous = sceneGroupCameraView(previousObject, visibleObjects, sceneElapsed);
  return {
    targetX: previous.targetX * (1 - blend) + current.targetX * blend,
    targetY: previous.targetY * (1 - blend) + current.targetY * blend,
    zoom: clamp(previous.zoom * (1 - blend) + current.zoom * blend, 0.82, 1.72),
  };
}

function sceneMotionFocusBoost(beat: ScenePlanBeat | null | undefined) {
  if (!beat?.motion_path && beat?.op !== "move") return 0;
  const behavior = String(beat?.particle_behavior ?? "");
  const gravityBias = physicsNumber(beat, "gravity_bias", 0.28);
  if (behavior === "gravity_arc") return clamp(0.16 + gravityBias * 0.12, 0.16, 0.32);
  if (behavior === "kinetic_flow") return 0.14;
  return 0.08;
}

function sceneRelationRank(object: SceneRenderObject) {
  const affordance = String(object.beat.visual_affordance ?? "");
  const role = String(object.beat.semantic_role ?? "");
  const motionRole = sceneMotionRole(object.beat);
  if (motionRole === "subject") return 0;
  if (motionRole === "source") return 1;
  if (motionRole === "target") return 2;
  if (object.beat.op === "move" || object.beat.motion_path) return 0;
  if (affordance === "small_moving_object" || affordance === "small_object") return 1;
  if (affordance === "entity_figure") return 2;
  if (affordance === "organic_structure") return 3;
  if (role.includes("relation")) return 4;
  return 5;
}

function sceneActiveGroupObjects(activeObject: SceneRenderObject | null, visibleObjects: SceneRenderObject[]) {
  if (!activeObject) return [];
  return visibleObjects
    .filter((object) => sameSceneGroup(object.beat, activeObject.beat))
    .sort((left, right) => sceneRelationRank(left) - sceneRelationRank(right))
    .slice(0, 6);
}

function sceneObjectCanvasCenter(
  object: SceneRenderObject,
  width: number,
  height: number,
  sceneElapsed: number,
  cameraView: SceneCameraView,
) {
  const modelPoint = sceneMotionPathPoint(object.beat, sceneElapsed);
  return scenePointToCanvas(object.beat, modelPoint, width, height, sceneElapsed, { x: 0, y: 0 }, cameraView);
}

function sceneVisibleTrackObjects(objects: SceneRenderObject[], activeObjectId: string | null, sceneElapsed: number) {
  const byTrack = new Map<string, { object: SceneRenderObject; score: number; order: number }>();
  objects.forEach((object, order) => {
    const trackId = sceneObjectTrackId(object.beat, order);
    const activeScore = object.id === activeObjectId ? 1_000_000 : 0;
    const start = sceneBeatStart(object.beat);
    const startedScore = start <= sceneElapsed ? 10_000 + start : start;
    const preCoherenceScore = sceneMotionSourceHold(object.beat, sceneElapsed) > 0 ? 9_000 + start : 0;
    const score = activeScore + Math.max(startedScore, preCoherenceScore);
    const current = byTrack.get(trackId);
    if (!current || score > current.score || (score === current.score && order > current.order)) {
      byTrack.set(trackId, { object, score, order });
    }
  });
  return Array.from(byTrack.values())
    .sort((left, right) => left.order - right.order)
    .map((entry) => entry.object);
}

function commandSequenceBeats(sequence: SplatraCommandSequence | null | undefined): ScenePlanBeat[] {
  const actions = Array.isArray(sequence?.scene_actions) ? sequence?.scene_actions ?? [] : [];
  return actions
    .map((action, index) => {
      const args = action?.args && typeof action.args === "object" ? action.args : {};
      return {
        ...(args as ScenePlanBeat),
        op: coerceSceneBeatOp(action?.op),
        object_id: String(args.id ?? `splatra_action_${index}`),
        object_track_id: typeof args.track_id === "string" ? args.track_id : "",
        object_track_basis: typeof args.track_basis === "string" ? args.track_basis : "",
        prompt: typeof args.prompt === "string" ? args.prompt : "",
        narration: typeof args.narration === "string" ? args.narration : "",
        particle_behavior: typeof args.particle_behavior === "string" ? args.particle_behavior : "",
        visual_affordance: typeof args.visual_affordance === "string" ? args.visual_affordance : "",
        semantic_role: typeof args.semantic_role === "string" ? args.semantic_role : "",
        spatial_relation: typeof args.spatial_relation === "string" ? args.spatial_relation : "",
      };
    })
    .filter((beat) => Boolean(beat.prompt || beat.object_id));
}

function coerceSceneBeatOp(value: unknown): SceneBeatOp {
  const candidate = String(value || "spawn_object");
  if (
    candidate === "spawn_object"
    || candidate === "morph"
    || candidate === "move"
    || candidate === "focus_camera"
    || candidate === "label"
    || candidate === "despawn"
  ) {
    return candidate;
  }
  return "spawn_object";
}

function scenePlanWithCommandSequence(scenePlan: ScenePlan | null | undefined, sequence: SplatraCommandSequence | null | undefined): ScenePlan | null | undefined {
  const commandBeats = commandSequenceBeats(sequence);
  if (!commandBeats.length) return scenePlan;
  return {
    ...(scenePlan ?? {}),
    beats: commandBeats,
  };
}

function splatraReadyCartridge(queue: SplatraCartridgeQueuePayload | null | undefined): SplatraReadyCartridge | null {
  const jobs = Array.isArray(queue?.sidecar_dispatch?.jobs) ? queue?.sidecar_dispatch?.jobs ?? [] : [];
  const ready = jobs
    .map((job, index) => ({
      job,
      index,
      sourceCount: Number(job?.sgf_summary?.num_gaussians ?? 0) || 0,
      generationEngine: String(job?.generation_engine ?? "unknown"),
      realGeneratorUsed: job?.real_generator_used === true,
      prompt: String(job?.prompt ?? ""),
    }))
    .filter((item) => item.job?.status === "swap_ready" && typeof item.job?.viewer_cartridge_url === "string")
    .sort((left, right) => {
      if (right.sourceCount !== left.sourceCount) return right.sourceCount - left.sourceCount;
      return left.index - right.index;
    })[0];
  if (!ready?.job?.viewer_cartridge_url) return null;
  return {
    url: ready.job.viewer_cartridge_url,
    sourceCount: ready.sourceCount,
    jobIndex: ready.index,
    generationEngine: ready.generationEngine,
    realGeneratorUsed: ready.realGeneratorUsed,
    prompt: ready.prompt,
  };
}

function splatraReadyCartridgeUrl(queue: SplatraCartridgeQueuePayload | null | undefined): string {
  return splatraReadyCartridge(queue)?.url ?? "";
}

function splatraMaterialHint(prompt: string, realGeneratorUsed: boolean): string {
  const lowered = prompt.toLowerCase();
  if (lowered.includes("glass") || lowered.includes("transparent") || lowered.includes("translucent") || lowered.includes("유리")) return "glass";
  if (lowered.includes("metal") || lowered.includes("금속")) return "metal";
  if (lowered.includes("water") || lowered.includes("물")) return "water";
  return realGeneratorUsed ? "learned_surface" : "procedural";
}

function splatraCartridgeFetchUrl(url: string, budget: number): string {
  const next = new URL(url, window.location.href);
  next.searchParams.set("format", "spl3");
  next.searchParams.set("budget", String(Math.max(1, Math.floor(budget))));
  next.searchParams.set("_", String(Date.now()));
  return next.toString();
}

function halfToFloat(value: number): number {
  const sign = value & 0x8000 ? -1 : 1;
  const exponent = (value >> 10) & 0x1f;
  const fraction = value & 0x03ff;
  if (exponent === 0) return sign * Math.pow(2, -14) * (fraction / 1024);
  if (exponent === 31) return fraction ? Number.NaN : sign * Number.POSITIVE_INFINITY;
  return sign * Math.pow(2, exponent - 15) * (1 + fraction / 1024);
}

type SplatraSampleReader = {
  sourceCount: number;
  format: "spl2" | "spl3";
  readPosition: (index: number) => [number, number, number];
  readColor: (index: number) => [number, number, number];
  readScaleSignal: (index: number) => number;
  readOpacity: (index: number) => number;
  bbox?: {
    minX: number;
    minY: number;
    minZ: number;
    maxX: number;
    maxY: number;
    maxZ: number;
  };
};

function buildLoadedSplatraCartridge(
  reader: SplatraSampleReader,
  budget: number,
  url: string,
  prompt = "",
  realGeneratorUsed = false,
  generationEngine = "",
): SplatraLoadedCartridge {
  const sourceCount = reader.sourceCount;
  const densityMultiplier = realGeneratorUsed ? 20 : 10.75;
  // Keep the rendered model high-density, but avoid expanding every generated
  // Gaussian into a JS object on the browser main thread. The original source
  // count remains exposed as telemetry; the visible cartridge uses an adaptive
  // sample that is dense enough for the product surface and stable enough for
  // lower-end machines or browser automation.
  const adaptiveRealGeneratorCap = generationEngine.toLowerCase().includes("glass_orb") ? 150000 : 120000;
  const maxParticles = realGeneratorUsed
    ? clamp(Math.floor(budget * densityMultiplier), 48000, adaptiveRealGeneratorCap)
    : clamp(Math.floor(budget * densityMultiplier), 22000, 180000);
  const outputCount = Math.min(sourceCount, maxParticles);
  const salt = Math.floor(stableUnit(url, 909) * 10000);
  const particles: Particle[] = [];
  let minX = reader.bbox?.minX ?? Number.POSITIVE_INFINITY;
  let minY = reader.bbox?.minY ?? Number.POSITIVE_INFINITY;
  let minZ = reader.bbox?.minZ ?? Number.POSITIVE_INFINITY;
  let maxX = reader.bbox?.maxX ?? Number.NEGATIVE_INFINITY;
  let maxY = reader.bbox?.maxY ?? Number.NEGATIVE_INFINITY;
  let maxZ = reader.bbox?.maxZ ?? Number.NEGATIVE_INFINITY;
  if (!reader.bbox) {
    const stride = Math.max(1, Math.floor(sourceCount / 180000));
    for (let index = 0; index < sourceCount; index += stride) {
      const [x, y, z] = reader.readPosition(index);
      if (!Number.isFinite(x) || !Number.isFinite(y) || !Number.isFinite(z)) continue;
      minX = Math.min(minX, x);
      minY = Math.min(minY, y);
      minZ = Math.min(minZ, z);
      maxX = Math.max(maxX, x);
      maxY = Math.max(maxY, y);
      maxZ = Math.max(maxZ, z);
    }
  }
  if (!Number.isFinite(minX)) {
    minX = minY = minZ = -1;
    maxX = maxY = maxZ = 1;
  }
  const centerX = (minX + maxX) / 2;
  const centerY = (minY + maxY) / 2;
  const centerZ = (minZ + maxZ) / 2;
  const spanX = Math.max(1e-6, maxX - minX);
  const spanY = Math.max(1e-6, maxY - minY);
  const spanZ = Math.max(1e-6, maxZ - minZ);
  const fitScale = Math.max(spanX, spanY, spanZ) / 1.9;
  const candidates: Array<{ index: number; score: number }> = [];
  const candidateStride = Math.max(1, Math.floor(sourceCount / Math.max(outputCount * 2, 1)));
  for (let index = 0; index < sourceCount; index += candidateStride) {
    const jittered = (index + Math.floor(seeded(index, salt) * candidateStride)) % sourceCount;
    const scaleSignal = reader.readScaleSignal(jittered);
    const opacity = Math.max(0, reader.readOpacity(jittered));
    const surfaceJitter = seeded(jittered, salt + 31) * 0.08;
    candidates.push({ index: jittered, score: opacity * (0.58 + scaleSignal * 5.2) + surfaceJitter });
  }
  candidates.sort((left, right) => right.score - left.score);
  const selected = new Set<number>();
  const salienceCount = Math.min(outputCount, Math.floor(outputCount * 0.62));
  for (const item of candidates) {
    if (selected.size >= salienceCount) break;
    selected.add(item.index);
  }
  const uniformStep = Math.max(1, Math.floor(sourceCount / Math.max(outputCount - selected.size, 1)));
  for (let index = 0; index < sourceCount && selected.size < outputCount; index += uniformStep) {
    selected.add((index + Math.floor(seeded(index, salt + 53) * uniformStep)) % sourceCount);
  }
  if (selected.size < outputCount) {
    for (let index = 0; index < sourceCount && selected.size < outputCount; index += 1) {
      selected.add((index + Math.floor(seeded(index, salt + 79) * sourceCount)) % sourceCount);
    }
  }
  if (selected.size < outputCount) {
    for (let index = 0; index < sourceCount && selected.size < outputCount; index += 1) {
      selected.add(index);
    }
  }
  for (const jittered of selected) {
    if (particles.length >= outputCount) break;
    const [rawX, rawY, rawZ] = reader.readPosition(jittered);
    if (!Number.isFinite(rawX) || !Number.isFinite(rawY) || !Number.isFinite(rawZ)) continue;
    const [rawR, rawG, rawB] = reader.readColor(jittered);
    const x = (rawX - centerX) / fitScale;
    const y = (rawY - centerY) / fitScale;
    const z = (rawZ - centerZ) / fitScale;
    const r = clamp(rawR, 0.04, 1);
    const g = clamp(rawG, 0.04, 1);
    const b = clamp(rawB, 0.04, 1);
    const scaleSignal = clamp(reader.readScaleSignal(jittered), 0.004, 0.18);
    const opacity = clamp(reader.readOpacity(jittered), 0.08, 3.8);
    particles.push({
      x,
      y: -y,
      z,
      r,
      g,
      b,
      a: clamp(0.2 + opacity * 0.28, 0.16, 0.92),
      scale: clamp(0.58 + scaleSignal * 14 + seeded(jittered, salt + 17) * 0.44, 0.58, 2.7),
    });
  }
  const webglPositions = new Float32Array(particles.length * 3);
  const webglColors = new Float32Array(particles.length * 4);
  const webglSizes = new Float32Array(particles.length);
  particles.forEach((particle, index) => {
    const p3 = index * 3;
    const p4 = index * 4;
    webglPositions[p3] = particle.x;
    webglPositions[p3 + 1] = particle.y;
    webglPositions[p3 + 2] = particle.z;
    webglColors[p4] = particle.r;
    webglColors[p4 + 1] = particle.g;
    webglColors[p4 + 2] = particle.b;
    webglColors[p4 + 3] = particle.a;
    webglSizes[index] = particle.scale;
  });
  return {
    url,
    particleCount: particles.length,
    sourceCount,
    bbox: { minX, minY, minZ, maxX, maxY, maxZ },
    selectionMode: `bbox_fit_high_density_perspective_material_${reader.format}`,
    materialHint: splatraMaterialHint(prompt, realGeneratorUsed),
    reconstructionQualityPath: generationEngine.toLowerCase().includes("glass_orb")
      ? "particle_material_generator_glass_orb"
      : realGeneratorUsed
        ? "real_text_to_image_single_view_2_5d_lift"
        : "procedural_particle_fallback",
    realGeneratorUsed,
    particles,
    webgl: {
      positions: webglPositions,
      colors: webglColors,
      sizes: webglSizes,
    },
  };
}

function parseSpl2Cartridge(buffer: ArrayBuffer, budget: number, url: string, prompt = "", realGeneratorUsed = false, generationEngine = ""): SplatraLoadedCartridge {
  const view = new DataView(buffer);
  if (buffer.byteLength < 8) throw new Error("SPL2 cartridge too small");
  const magic = String.fromCharCode(view.getUint8(0), view.getUint8(1), view.getUint8(2), view.getUint8(3));
  if (magic === "SPL3") {
    const sourceCount = view.getUint32(4, true);
    const headerBytes = 32;
    const posOffset = headerBytes;
    const colorOffset = posOffset + sourceCount * 6;
    const scaleOffset = colorOffset + sourceCount * 3;
    const quatOffset = scaleOffset + sourceCount * 6;
    const opacityOffset = quatOffset + sourceCount * 4;
    const expectedBytes = opacityOffset + sourceCount;
    if (buffer.byteLength < expectedBytes) throw new Error("SPL3 cartridge truncated");
    const minX = view.getFloat32(8, true);
    const minY = view.getFloat32(12, true);
    const minZ = view.getFloat32(16, true);
    const maxX = view.getFloat32(20, true);
    const maxY = view.getFloat32(24, true);
    const maxZ = view.getFloat32(28, true);
    const spanX = Math.max(1e-8, maxX - minX);
    const spanY = Math.max(1e-8, maxY - minY);
    const spanZ = Math.max(1e-8, maxZ - minZ);
    return buildLoadedSplatraCartridge({
      sourceCount,
      format: "spl3",
      bbox: { minX, minY, minZ, maxX, maxY, maxZ },
      readPosition: (index) => {
        const offset = posOffset + index * 6;
        const xq = view.getInt16(offset, true);
        const yq = view.getInt16(offset + 2, true);
        const zq = view.getInt16(offset + 4, true);
        return [
          minX + ((xq + 32768) / 65535) * spanX,
          minY + ((yq + 32768) / 65535) * spanY,
          minZ + ((zq + 32768) / 65535) * spanZ,
        ];
      },
      readColor: (index) => {
        const offset = colorOffset + index * 3;
        return [
          view.getUint8(offset) / 255,
          view.getUint8(offset + 1) / 255,
          view.getUint8(offset + 2) / 255,
        ];
      },
      readScaleSignal: (index) => {
        const offset = scaleOffset + index * 6;
        const sx = Math.abs(halfToFloat(view.getUint16(offset, true)) || 0);
        const sy = Math.abs(halfToFloat(view.getUint16(offset + 2, true)) || 0);
        const sz = Math.abs(halfToFloat(view.getUint16(offset + 4, true)) || 0);
        return (sx + sy + sz) / 3;
      },
      readOpacity: (index) => view.getUint8(opacityOffset + index) / 255,
    }, budget, url, prompt, realGeneratorUsed, generationEngine);
  }
  if (magic !== "SPL2") throw new Error(`unsupported cartridge ${magic}`);
  const sourceCount = view.getUint32(4, true);
  const strideFloats = 14;
  const expectedBytes = 8 + sourceCount * strideFloats * 4;
  if (buffer.byteLength < expectedBytes) throw new Error("SPL2 cartridge truncated");
  const floats = new Float32Array(buffer, 8);
  const posOffset = 0;
  const colorOffset = sourceCount * 3;
  const scaleOffset = sourceCount * 6;
  const opacityOffset = sourceCount * 13;
  return buildLoadedSplatraCartridge({
    sourceCount,
    format: "spl2",
    readPosition: (index) => [
      floats[posOffset + index * 3],
      floats[posOffset + index * 3 + 1],
      floats[posOffset + index * 3 + 2],
    ],
    readColor: (index) => [
      floats[colorOffset + index * 3],
      floats[colorOffset + index * 3 + 1],
      floats[colorOffset + index * 3 + 2],
    ],
    readScaleSignal: (index) => {
      const sx = Math.abs(floats[scaleOffset + index * 3] || 0);
      const sy = Math.abs(floats[scaleOffset + index * 3 + 1] || 0);
      const sz = Math.abs(floats[scaleOffset + index * 3 + 2] || 0);
      return (sx + sy + sz) / 3;
    },
    readOpacity: (index) => floats[opacityOffset + index],
  }, budget, url, prompt, realGeneratorUsed, generationEngine);
}

function buildSceneRenderObjects(scenePlan: ScenePlan | null | undefined, budget: number): SceneRenderObject[] {
  const beats = Array.isArray(scenePlan?.beats) ? scenePlan?.beats ?? [] : [];
  const seen = new Set<string>();
  const maxObjects = Math.min(18, Math.max(1, beats.length));
  const sceneWide = scenePlan?.layout_intent === "wide_particle_stage";
  const densityBudget = budget * (sceneWide ? 8.4 : 5.8);
  const perObjectBudget = clamp(Math.floor(Math.max(1400, densityBudget) / maxObjects), 520, sceneWide ? 3000 : 1860);
  return beats
    .slice(0, maxObjects)
    .map((beat, index) => {
      const archetype = beat.archetype && PRODUCT_ARCHETYPES.includes(beat.archetype) ? beat.archetype : sceneArchetype(scenePlan, index) ?? "abstract_memory_cloud";
      const id = sceneObjectId(beat, index);
      const seed = `${sceneObjectTrackId(beat, index)}:${beat.prompt ?? ""}`;
      const pose = scenePoseForBeat(beat);
      const isFigure = String(beat.visual_affordance ?? "") === "entity_figure";
      const intent = sceneParticleIntentForBeat(scenePlan, beat, index);
      const objectBudget = Math.round(perObjectBudget * sceneParticleIntentDensity(intent, beat, false));
      return {
        archetype,
        beat,
        id,
        particles: sceneParticlesForBeat(beat, archetype, objectBudget),
        poseBaseParticles: isFigure && pose !== "standing" ? figureParticles(objectBudget, seed, "standing") : undefined,
      };
    })
    .filter((object) => {
      if (seen.has(object.id)) return false;
      seen.add(object.id);
      return true;
    });
}

function sceneParticlesForBeat(beat: ScenePlanBeat, archetype: Archetype, count: number): Particle[] {
  const affordance = String(beat.visual_affordance ?? "");
  const seed = `${sceneObjectTrackId(beat)}:${beat.prompt ?? ""}`;
  if (affordance === "entity_figure") return figureParticles(count, seed, scenePoseForBeat(beat));
  if (affordance === "organic_structure") {
    return organicStructureParticles(count, seed, beat);
  }
  if (affordance === "small_object" || affordance === "small_moving_object") {
    return smallObjectParticles(count, seed, affordance === "small_moving_object");
  }
  return fallbackParticles(archetype, count);
}

function scenePoseForBeat(beat: ScenePlanBeat): ScenePose {
  const explicitPose = String(beat.pose_hint ?? beat.physics_hint?.pose_hint ?? "");
  if (explicitPose === "seated" || explicitPose === "reaching" || explicitPose === "standing") return explicitPose;
  const relation = String(beat.spatial_relation ?? "");
  const motionRole = sceneMotionRole(beat);
  if (relation === "under_target") return "seated";
  if (relation === "motion_target") return "reaching";
  if (motionRole === "target" && beat.visual_affordance === "entity_figure") return "reaching";
  return "standing";
}

function sceneSurfaceFeatures(beat: ScenePlanBeat) {
  const rawFeatures = [
    ...(Array.isArray(beat.surface_features) ? beat.surface_features : []),
    ...(Array.isArray(beat.physics_hint?.surface_features) ? beat.physics_hint.surface_features : []),
  ];
  return new Set(rawFeatures.map((feature) => String(feature).toLowerCase()).filter(Boolean));
}

function semanticParticleColor(index: number, salt: number, warm = 0.32) {
  return {
    r: 0.1 + warm * 0.74 + seeded(index, salt + 3) * 0.14,
    g: 0.68 + seeded(index, salt + 5) * 0.24,
    b: 0.92 + seeded(index, salt + 7) * 0.08,
    a: 0.5 + seeded(index, salt + 11) * 0.42,
    scale: 0.76 + seeded(index, salt + 13) * 1.18,
  };
}

function segmentParticle(
  index: number,
  start: [number, number, number],
  end: [number, number, number],
  thickness: number,
  salt: number,
) {
  const t = seeded(index, salt);
  const angle = seeded(index, salt + 1) * Math.PI * 2;
  const radius = Math.sqrt(seeded(index, salt + 2)) * thickness;
  return {
    x: start[0] * (1 - t) + end[0] * t + Math.cos(angle) * radius,
    y: start[1] * (1 - t) + end[1] * t + (seeded(index, salt + 3) - 0.5) * thickness,
    z: start[2] * (1 - t) + end[2] * t + Math.sin(angle) * radius * 0.7,
  };
}

function figureParticles(count: number, seed: string, pose: ScenePose = "standing"): Particle[] {
  const salt = Math.floor(stableUnit(seed, 221) * 10000);
  const seated = pose === "seated";
  const reaching = pose === "reaching";
  const limbs: Array<{ start: [number, number, number]; end: [number, number, number]; thickness: number; warm: number }> = [
    { start: [0, 0.42, 0], end: [0, -0.35, 0], thickness: 0.13, warm: 0.26 },
    { start: [-0.05, 0.28, 0], end: [reaching ? -0.58 : -0.42, reaching ? 0.22 : -0.02, 0], thickness: 0.06, warm: 0.38 },
    { start: [0.05, 0.28, 0], end: [reaching ? 0.58 : 0.42, reaching ? 0.22 : -0.02, 0], thickness: 0.06, warm: 0.38 },
    { start: [-0.05, -0.34, 0], end: [seated ? -0.5 : -0.27, seated ? -0.48 : -0.88, 0], thickness: 0.07, warm: 0.3 },
    { start: [0.05, -0.34, 0], end: [seated ? 0.5 : 0.27, seated ? -0.48 : -0.88, 0], thickness: 0.07, warm: 0.3 },
  ];
  return Array.from({ length: count }, (_, index) => {
    const headCutoff = Math.floor(count * 0.22);
    let x = 0;
    let y = 0;
    let z = 0;
    let warm = 0.34;
    let scaleBoost = 1;
    if (index < headCutoff) {
      const local = index / Math.max(1, headCutoff);
      const theta = index * Math.PI * (3 - Math.sqrt(5));
      const yy = 1 - 2 * local;
      const ring = Math.sqrt(Math.max(0, 1 - yy * yy));
      const radius = 0.17 + (seeded(index, salt + 31) - 0.5) * 0.025;
      x = Math.cos(theta) * ring * radius;
      y = 0.66 + yy * radius;
      z = Math.sin(theta) * ring * radius * 0.72;
      warm = 0.46;
      scaleBoost = 1.22;
    } else {
      const limb = limbs[(index - headCutoff) % limbs.length];
      const point = segmentParticle(index, limb.start, limb.end, limb.thickness, salt + (index % limbs.length) * 19);
      x = point.x;
      y = point.y;
      z = point.z;
      warm = limb.warm;
      scaleBoost = limb.thickness > 0.1 ? 1.08 : 0.82;
    }
    const color = semanticParticleColor(index, salt, warm);
    return { x, y, z, ...color, scale: color.scale * scaleBoost };
  });
}

function organicStructureParticles(count: number, seed: string, beat: ScenePlanBeat): Particle[] {
  const particles = fallbackParticles("tree", count);
  const features = sceneSurfaceFeatures(beat);
  const hasFruit = features.has("fruit_cluster") || features.has("fruit") || features.has("seed_cluster");
  if (!hasFruit) return particles;
  const salt = Math.floor(stableUnit(seed, 419) * 10000);
  const fruitCount = Math.max(8, Math.floor(count * 0.1));
  for (let index = 0; index < fruitCount && index < particles.length; index += 1) {
    const target = particles.length - 1 - index;
    const theta = index * Math.PI * (3 - Math.sqrt(5)) + seeded(index, salt) * 0.4;
    const r = 0.24 + seeded(index, salt + 3) * 0.56;
    particles[target] = {
      x: Math.cos(theta) * r * 0.78,
      y: 0.24 + seeded(index, salt + 5) * 0.88,
      z: Math.sin(theta) * r * 0.5,
      r: 0.9 + seeded(index, salt + 7) * 0.08,
      g: 0.28 + seeded(index, salt + 11) * 0.16,
      b: 0.38 + seeded(index, salt + 13) * 0.12,
      a: 0.74,
      scale: 1.42 + seeded(index, salt + 17) * 0.74,
    };
  }
  return particles;
}

function smallObjectParticles(count: number, seed: string, moving: boolean): Particle[] {
  const salt = Math.floor(stableUnit(seed, 337) * 10000);
  return Array.from({ length: count }, (_, index) => {
    const t = (index + 0.5) / count;
    const theta = index * Math.PI * (3 - Math.sqrt(5));
    const yy = 1 - 2 * t;
    const ring = Math.sqrt(Math.max(0, 1 - yy * yy));
    const radius = 0.26 + Math.sin(index * 0.29 + salt) * 0.018;
    const tail = moving && index > count * 0.72;
    const tailT = tail ? (index - count * 0.72) / Math.max(1, count * 0.28) : 0;
    const color = semanticParticleColor(index, salt, tail ? 0.62 : 0.78);
    return {
      x: Math.cos(theta) * ring * radius - tailT * (0.32 + seeded(index, salt + 17) * 0.18),
      y: yy * radius + Math.sin(tailT * Math.PI) * 0.05,
      z: Math.sin(theta) * ring * radius * 0.72,
      ...color,
      a: tail ? color.a * (1 - tailT * 0.62) : color.a,
      scale: color.scale * (tail ? 0.58 : 1.28),
    };
  });
}

function fallbackParticles(archetype: Archetype, count: number): Particle[] {
  const palette = (index: number, warm = 0.32) => ({
    r: 0.1 + warm * 0.75 + seeded(index, 3) * 0.16,
    g: 0.66 + seeded(index, 2) * 0.28,
    b: 0.92 + seeded(index, 4) * 0.08,
    a: 0.45 + seeded(index, 5) * 0.5,
    scale: 0.72 + seeded(index, 8) * 1.35,
  });
  return Array.from({ length: count }, (_, index) => {
    const t = (index + 0.5) / count;
    let x = 0;
    let y = 0;
    let z = 0;
    let warm = 0.28;
    let scaleBoost = 1;
    if (archetype === "city_block") {
      const cols = 9;
      const col = index % cols;
      const row = Math.floor(index / cols);
      const height = 0.38 + seeded(col, 71) * 1.12;
      x = -1.35 + (col / (cols - 1)) * 2.7 + (seeded(index, 17) - 0.5) * 0.08;
      y = -1.15 + seeded(row, col) * height * 1.75;
      z = -0.55 + seeded(col, 19) * 1.1;
      warm = seeded(index, 28) > 0.74 ? 0.8 : 0.24;
      scaleBoost = index % 17 === 0 ? 1.5 : 0.82;
    } else if (archetype === "circuit") {
      const lane = index % 12;
      const step = Math.floor(index / 12);
      const horizontal = lane % 2 === 0;
      const coord = -1.38 + (lane / 11) * 2.76;
      const progress = (step % 90) / 89;
      x = horizontal ? -1.55 + progress * 3.1 : coord;
      y = horizontal ? coord : -1.35 + progress * 2.7;
      z = Math.sin(progress * Math.PI * 2 + lane) * 0.15;
      warm = index % 37 === 0 ? 0.8 : 0.18;
      scaleBoost = index % 37 === 0 ? 2.3 : 0.62;
    } else if (archetype === "tree") {
      if (index < count * 0.22) {
        const trunkT = index / Math.max(1, count * 0.22);
        x = (seeded(index, 31) - 0.5) * (0.12 + trunkT * 0.08);
        y = -1.35 + trunkT * 1.35;
        z = (seeded(index, 32) - 0.5) * 0.24;
        warm = 0.1;
        scaleBoost = 1.0;
      } else {
        const canopyT = (index - count * 0.22) / Math.max(1, count * 0.78);
        const theta = index * Math.PI * (3 - Math.sqrt(5));
        const radius = (0.15 + seeded(index, 33) * 1.05) * (1 - canopyT * 0.22);
        x = Math.cos(theta) * radius * 0.78;
        y = -0.05 + seeded(index, 34) * 1.38;
        z = Math.sin(theta) * radius * 0.58;
        warm = 0.2 + seeded(index, 35) * 0.28;
        scaleBoost = 1.18;
      }
    } else if (archetype === "tower") {
      const floors = 26;
      const floor = index % floors;
      const side = Math.floor(index / floors) % 4;
      const floorT = floor / (floors - 1);
      const width = 0.23 + floorT * 0.22;
      y = -1.45 + floorT * 2.9;
      x = side === 0 ? -width : side === 1 ? width : (seeded(index, 41) - 0.5) * width * 2;
      z = side === 2 ? -width : side === 3 ? width : (seeded(index, 42) - 0.5) * width * 2;
      warm = floor % 5 === 0 ? 0.72 : 0.24;
      scaleBoost = 0.82;
    } else if (archetype === "machine_core") {
      const ring = index % 6;
      const theta = t * Math.PI * 2 * (9 + ring * 0.6);
      const radius = 0.28 + ring * 0.18 + Math.sin(theta * 2.4) * 0.025;
      x = Math.cos(theta) * radius;
      y = Math.sin(theta * (1.0 + ring * 0.08)) * 0.24;
      z = Math.sin(theta) * radius;
      warm = ring % 2 ? 0.72 : 0.22;
      scaleBoost = ring === 0 ? 1.55 : 0.96;
    } else if (archetype === "constellation") {
      const anchor = index % 18;
      const theta = anchor * 2.399963 + seeded(anchor, 51);
      const baseR = 0.35 + seeded(anchor, 52) * 1.45;
      const star = index % 13 === 0;
      const drift = seeded(index, 53) * 0.18;
      x = Math.cos(theta) * baseR + (seeded(index, 54) - 0.5) * drift;
      y = Math.sin(theta * 0.72) * (0.35 + seeded(anchor, 55) * 0.9) + (seeded(index, 56) - 0.5) * drift;
      z = Math.sin(theta) * baseR * 0.42;
      warm = star ? 0.72 : 0.24;
      scaleBoost = star ? 2.8 : 0.46;
    } else if (archetype === "creature") {
      const centers = [[-0.24, 0.05, 0], [0.26, 0.02, 0], [0, 0.58, 0], [-0.58, -0.38, 0], [0.58, -0.38, 0]];
      const center = centers[index % centers.length];
      const spread = index % centers.length === 2 ? 0.16 : 0.22;
      const theta = seeded(index, 61) * Math.PI * 2;
      const dist = Math.sqrt(seeded(index, 62)) * spread;
      x = center[0] + Math.cos(theta) * dist;
      y = center[1] + (seeded(index, 63) - 0.5) * spread;
      z = center[2] + Math.sin(theta) * dist * 0.68;
      warm = 0.36 + seeded(index, 64) * 0.34;
      scaleBoost = 1.2;
    } else if (archetype === "abstract_memory_cloud") {
      const cluster = index % 8;
      const theta = cluster * 0.91 + seeded(cluster, 81);
      const cx = Math.cos(theta) * (0.22 + seeded(cluster, 82) * 0.88);
      const cy = Math.sin(theta * 1.7) * 0.7;
      const cz = Math.sin(theta) * 0.48;
      const spread = 0.12 + seeded(index, 83) * 0.46;
      x = cx + (seeded(index, 84) - 0.5) * spread;
      y = cy + (seeded(index, 85) - 0.5) * spread;
      z = cz + (seeded(index, 86) - 0.5) * spread;
      warm = 0.24 + seeded(index, 87) * 0.5;
      scaleBoost = 1.28;
    } else {
      const theta = index * Math.PI * (3 - Math.sqrt(5));
      const yy = 1 - 2 * t;
      const ring = Math.sqrt(Math.max(0, 1 - yy * yy));
      x = Math.cos(theta) * ring * 1.08;
      y = yy;
      z = Math.sin(theta) * ring * 1.08;
      warm = 0.36;
    }
    const color = palette(index, warm);
    return { x, y, z, ...color, scale: color.scale * scaleBoost };
  });
}

function drawArchetypeGuides(
  ctx: CanvasRenderingContext2D,
  archetype: Archetype,
  width: number,
  height: number,
  elapsed: number,
  controls: ParticleControls,
) {
  const cx = width / 2;
  const cy = height / 2;
  const unit = Math.min(width, height);
  const alpha = controls.resting ? 0.08 : 0.16 + controls.arousal * 0.08 + controls.speaking_energy * 0.08;
  ctx.save();
  ctx.translate(cx, cy);
  ctx.rotate(Math.sin(elapsed * 0.08) * 0.08);
  const guideColor: [number, number, number] = [76, 230, 255];
  const accentColor: [number, number, number] = [255, 104, 177];

  if (archetype === "constellation") {
    const stars = Array.from({ length: 14 }, (_, index) => {
      const angle = index * 2.399963 + 0.3;
      const radius = unit * (0.18 + seeded(index, 101) * 0.34);
      return [Math.cos(angle) * radius, Math.sin(angle * 0.72) * radius * 0.72] as const;
    });
    stars.forEach(([x, y], index) => {
      const next = stars[(index * 5 + 3) % stars.length];
      drawParticleSegment(ctx, [x, y], [next[0], next[1]], guideColor, alpha * 0.72, unit, index + 101, elapsed);
      drawGuideParticle(ctx, x, y, index % 3 === 0 ? unit * 0.006 : unit * 0.0032, accentColor, alpha * 0.9);
    });
  } else if (archetype === "city_block") {
    for (let i = 0; i < 10; i += 1) {
      const w = unit * (0.028 + seeded(i, 111) * 0.025);
      const h = unit * (0.13 + seeded(i, 112) * 0.3);
      const x = -unit * 0.43 + i * unit * 0.095;
      const y = unit * 0.31 - h;
      drawParticleRect(ctx, x, y, w, h, guideColor, alpha * 0.72, unit, i + 111, elapsed);
      for (let row = 0; row < 5; row += 1) {
        const yy = y + h * (0.2 + row * 0.15);
        drawParticleSegment(ctx, [x + w * 0.18, yy], [x + w * 0.82, yy], accentColor, alpha * 0.45, unit, i * 19 + row, elapsed);
      }
    }
  } else if (archetype === "circuit") {
    for (let i = 0; i < 8; i += 1) {
      const y = -unit * 0.34 + i * unit * 0.095;
      drawParticlePolyline(ctx, [
        [-unit * 0.45, y],
        [-unit * 0.16, y],
        [-unit * 0.06, y + (i % 2 ? -unit * 0.045 : unit * 0.045)],
        [unit * 0.44, y + (i % 2 ? -unit * 0.045 : unit * 0.045)],
      ], guideColor, alpha * 0.8, unit, i + 211, elapsed);
      drawGuideParticle(ctx, -unit * 0.16, y, unit * 0.0048, accentColor, alpha * 0.76);
    }
  } else if (archetype === "tree") {
    drawParticleSegment(ctx, [0, unit * 0.32], [0, -unit * 0.12], guideColor, alpha * 0.86, unit, 311, elapsed);
    for (let i = 0; i < 9; i += 1) {
      const y = unit * (0.17 - i * 0.045);
      const side = i % 2 ? -1 : 1;
      const mid: [number, number] = [side * unit * 0.14, y - unit * 0.08];
      const end: [number, number] = [side * unit * (0.23 + seeded(i, 121) * 0.12), y - unit * 0.13];
      drawParticlePolyline(ctx, [[0, y], mid, end], guideColor, alpha * 0.72, unit, i + 321, elapsed);
    }
    drawParticleEllipse(ctx, 0, -unit * 0.16, unit * 0.28, unit * 0.18, 0, guideColor, alpha * 0.72, unit, 331, elapsed);
  } else if (archetype === "machine_core") {
    for (let i = 0; i < 5; i += 1) {
      drawParticleEllipse(ctx, 0, 0, unit * (0.09 + i * 0.055), unit * (0.05 + i * 0.034), elapsed * 0.18 + i * 0.42, guideColor, alpha * 0.72, unit, i + 411, elapsed);
    }
  } else if (archetype === "tower") {
    drawParticlePolyline(ctx, [
      [-unit * 0.12, unit * 0.36],
      [-unit * 0.22, -unit * 0.28],
      [0, -unit * 0.42],
      [unit * 0.22, -unit * 0.28],
      [unit * 0.12, unit * 0.36],
      [-unit * 0.12, unit * 0.36],
    ], guideColor, alpha * 0.78, unit, 501, elapsed);
    for (let i = 0; i < 10; i += 1) {
      const y = -unit * 0.24 + i * unit * 0.055;
      drawParticleSegment(ctx, [-unit * (0.18 - i * 0.006), y], [unit * (0.18 - i * 0.006), y], accentColor, alpha * 0.52, unit, i + 521, elapsed);
    }
  } else if (archetype === "abstract_memory_cloud") {
    for (let i = 0; i < 7; i += 1) {
      const angle = i * 0.9;
      const x = Math.cos(angle) * unit * (0.08 + seeded(i, 131) * 0.18);
      const y = Math.sin(angle * 1.7) * unit * 0.16;
      drawParticleEllipse(ctx, x, y, unit * (0.08 + seeded(i, 132) * 0.08), unit * (0.045 + seeded(i, 133) * 0.05), angle, guideColor, alpha * 0.62, unit, i + 611, elapsed);
    }
  } else if (archetype === "creature") {
    drawParticleEllipse(ctx, 0, unit * 0.04, unit * 0.18, unit * 0.12, 0, guideColor, alpha * 0.78, unit, 701, elapsed);
    drawParticleEllipse(ctx, 0, -unit * 0.16, unit * 0.1, unit * 0.1, 0, guideColor, alpha * 0.78, unit, 711, elapsed);
    [[-0.28, 0.18], [0.28, 0.18], [-0.24, -0.05], [0.24, -0.05]].forEach(([x, y]) => {
      drawParticleSegment(ctx, [0, unit * 0.02], [x * unit, y * unit], guideColor, alpha * 0.72, unit, Math.round((x + y) * 1000), elapsed);
    });
  }
  ctx.restore();
}

function drawParticles(
  ctx: CanvasRenderingContext2D,
  particles: Particle[],
  archetype: Archetype,
  width: number,
  height: number,
  elapsed: number,
  controls: ParticleControls,
  ambient = false,
  guides = false,
  transform: SceneTransform = { offsetX: 0, offsetY: 0, zoom: 1 },
) {
  ctx.clearRect(0, 0, width, height);
  const pressure = layoutCollisionPressure(controls);
  const fieldQuieting = layoutFieldQuieting(controls);
  const flowRecombine = layoutFlowRecombine(controls);
  const cx = width / 2 + transform.offsetX * width;
  const cy = height / 2 + transform.offsetY * height;
  const scale = Math.min(width, height) * (ambient ? 0.18 : 0.26) * transform.zoom * (1 - pressure * 0.08);
  const rotation = elapsed * (controls.resting ? 0.08 : 0.18 + controls.arousal * 0.16);
  const tilt = Math.sin(elapsed * 0.21) * 0.18;
  const pulse = 1 + Math.sin(elapsed * 3.6) * controls.speaking_energy * 0.045;
  const cosY = Math.cos(rotation);
  const sinY = Math.sin(rotation);
  const cosX = Math.cos(tilt);
  const sinX = Math.sin(tilt);

  if (!ambient && guides) {
    drawArchetypeGuides(ctx, archetype, width, height, elapsed, controls);
  }

  if (ambient) {
    ctx.globalCompositeOperation = "lighter";
    drawAmbientAirbendField(ctx, width, height, elapsed, controls);
  }

  for (const point of particles) {
    let x = point.x;
    let y = point.y;
    let z = point.z;
    const rx = x * cosY - z * sinY;
    const rz = x * sinY + z * cosY;
    x = rx;
    z = rz;
    const ry = y * cosX - z * sinX;
    z = y * sinX + z * cosX;
    y = ry;
    const depth = clamp((z + 2.4) / 4.8, 0.08, 1);
    let px = cx + x * scale * pulse;
    let py = cy + y * scale * pulse;
    let size = clamp(point.scale * (0.82 + depth * 1.35), 0.8, 4.8);
    let alpha = clamp(point.a * (0.22 + depth * 0.82), 0.08, 0.86);

    if (ambient) {
      const homeX = seeded(point.x * 1000 + point.y * 911, 22) * width;
      const homeY = seeded(point.z * 1000 + point.x * 677, 23) * height;
      const edgeBias = Math.abs(homeX - cx) / Math.max(1, width / 2);
      const verticalBias = Math.abs(homeY - cy) / Math.max(1, height / 2);
      const recombineWave = (Math.sin(elapsed * 0.18) + 1) * 0.5;
      const recombine = controls.resting
        ? 0.08
        : 0.14 + controls.curiosity * 0.16 + controls.speaking_energy * 0.16 + recombineWave * 0.08 + flowRecombine * 0.22;
      const orbitX = cx + x * scale * 2.6;
      const orbitY = cy + y * scale * 1.9;
      const flow = flowFieldDisplacement(homeX, homeY, elapsed, Math.min(width, height) * (0.007 + flowRecombine * 0.028), point.x * 1.31 + point.z * 0.71);
      const drift = Math.sin(elapsed * 0.23 + homeX * 0.002 + homeY * 0.003) * 18;
      px = homeX * (1 - recombine) + orbitX * recombine + drift + flow.x;
      py = homeY * (1 - recombine) + orbitY * recombine + Math.cos(elapsed * 0.17 + homeX * 0.002) * 12 + flow.y;
      size = clamp(point.scale * (0.42 + depth * 0.74 + controls.speaking_energy * 0.24), 0.45, 2.2);
      alpha = clamp(point.a * (0.14 + depth * 0.44) * (0.74 + edgeBias * 0.22 + verticalBias * 0.12) * (1 - fieldQuieting * 0.28), 0.03, 0.48);
      const centerDistance = Math.hypot(px - cx, py - cy);
      const bodyClearRadius = Math.min(width, height) * (0.34 + pressure * 0.08);
      const bodyFeather = Math.min(width, height) * (0.16 + pressure * 0.04);
      const clearance = clamp((centerDistance - bodyClearRadius) / bodyFeather, 0.05, 1);
      alpha *= clearance;
      if (clearance < 0.08) size *= 0.62;
    }

    const color: [number, number, number] = [
      Math.floor(point.r * 255),
      Math.floor(point.g * 255),
      Math.floor(point.b * 255),
    ];
    if (ambient) {
      const angle = flowFieldAngle(px, py, elapsed, point.x * 1.7 + point.z * 0.9);
      const trailLength = clamp(size * (3.6 + controls.curiosity * 3.8 + controls.speaking_energy * 2.4 + flowRecombine * 2.2), 1.8, 13);
      drawParticleStroke(ctx, px, py, angle, trailLength, size, color, alpha);
    } else {
      ctx.fillStyle = `rgba(${color[0]}, ${color[1]}, ${color[2]}, ${alpha})`;
      ctx.beginPath();
      ctx.arc(px, py, size, 0, Math.PI * 2);
      ctx.fill();
    }
  }

  if (ambient) {
    ctx.globalCompositeOperation = "source-over";
  }

  if (ambient) {
    const fieldGlow = ctx.createRadialGradient(cx, cy, 0, cx, cy, Math.max(width, height) * 0.68);
    fieldGlow.addColorStop(0, "rgba(255,255,255,0.012)");
    fieldGlow.addColorStop(0.42, "rgba(30,228,255,0.022)");
    fieldGlow.addColorStop(1, "rgba(0,0,0,0)");
    ctx.fillStyle = fieldGlow;
    ctx.fillRect(0, 0, width, height);
    return;
  }

  const shellRadius = Math.min(width, height) * (0.215 + controls.speaking_energy * 0.012) * (1 - pressure * 0.04);
  const glow = ctx.createRadialGradient(cx, cy, shellRadius * 0.2, cx, cy, shellRadius * 1.35);
  glow.addColorStop(0, "rgba(255,255,255,0.18)");
  glow.addColorStop(0.42, "rgba(44,231,255,0.055)");
  glow.addColorStop(1, "rgba(0,0,0,0)");
  ctx.fillStyle = glow;
  ctx.beginPath();
  ctx.arc(cx, cy, shellRadius * 1.35, 0, Math.PI * 2);
  ctx.fill();
  drawParticleEllipse(ctx, cx, cy, shellRadius, shellRadius, 0, [128, 226, 255], 0.22, Math.min(width, height), 901, elapsed);
}

function drawSplatraCartridgeParticles(
  ctx: CanvasRenderingContext2D,
  cartridge: SplatraLoadedCartridge,
  width: number,
  height: number,
  elapsed: number,
  controls: ParticleControls,
  transform: SceneTransform,
  view: CartridgeViewState,
) {
  ctx.clearRect(0, 0, width, height);
  const pressure = layoutCollisionPressure(controls);
  const fieldQuieting = layoutFieldQuieting(controls);
  const cx = width / 2 + transform.offsetX * width;
  const cy = height / 2 + transform.offsetY * height;
  const unit = Math.min(width, height);
  const scale = unit * 0.37 * transform.zoom * (1 - pressure * 0.1);
  const rotation = elapsed * (0.16 + controls.curiosity * 0.06) + view.yaw;
  const tilt = Math.sin(elapsed * 0.18) * 0.14 + view.pitch;
  const cosY = Math.cos(rotation);
  const sinY = Math.sin(rotation);
  const cosX = Math.cos(tilt);
  const sinX = Math.sin(tilt);

  ctx.globalCompositeOperation = "lighter";
  const fieldGlow = ctx.createRadialGradient(cx, cy, 0, cx, cy, unit * 0.44);
  fieldGlow.addColorStop(0, `rgba(255,255,255,${0.038 * (1 - fieldQuieting * 0.28)})`);
  fieldGlow.addColorStop(0.48, `rgba(54,228,255,${0.028 * (1 - fieldQuieting * 0.28)})`);
  fieldGlow.addColorStop(1, "rgba(0,0,0,0)");
  ctx.fillStyle = fieldGlow;
  ctx.fillRect(0, 0, width, height);

  for (const point of cartridge.particles) {
    let x = point.x;
    let y = point.y;
    let z = point.z;
    const rx = x * cosY - z * sinY;
    const rz = x * sinY + z * cosY;
    x = rx;
    z = rz;
    const ry = y * cosX - z * sinX;
    z = y * sinX + z * cosX;
    y = ry;
    const viewDepth = clamp(2.55 - z, 0.85, 4.65);
    const perspective = clamp(2.35 / viewDepth, 0.62, 1.95);
    const depth = clamp((z + 1.65) / 3.3, 0.06, 1);
    const radius = Math.sqrt(point.x * point.x + point.y * point.y + point.z * point.z);
    const surfaceRim = clamp((radius - 0.56) / 0.72, 0, 1);
    const glassLike = cartridge.materialHint === "glass" || cartridge.materialHint === "water";
    const realSurfaceBoost = cartridge.realGeneratorUsed ? 1.12 : 1;
    const flow = flowFieldDisplacement(
      cx + x * scale * perspective,
      cy + y * scale * perspective,
      elapsed,
      unit * (0.0013 + controls.speaking_energy * 0.0011),
      point.x * 1.37 + point.z * 0.73,
    );
    const px = cx + x * scale * perspective + flow.x;
    const py = cy + y * scale * perspective + flow.y;
    const gloss = glassLike ? clamp(surfaceRim * 0.42 + depth * 0.16, 0, 0.58) : 0;
    const colorLift = cartridge.realGeneratorUsed ? 0.045 : 0;
    const color: [number, number, number] = [
      Math.floor(clamp(point.r + gloss + colorLift, 0, 1) * 255),
      Math.floor(clamp(point.g + gloss * 0.82 + colorLift, 0, 1) * 255),
      Math.floor(clamp(point.b + gloss * 1.05 + colorLift, 0, 1) * 255),
    ];
    const size = clamp(point.scale * (0.18 + depth * 0.42) * perspective * transform.zoom * realSurfaceBoost, 0.14, glassLike ? 1.82 : 2.18);
    const alpha = clamp(
      point.a * (0.16 + depth * 0.42 + surfaceRim * (glassLike ? 0.18 : 0.07)) * (1 - fieldQuieting * 0.22) * realSurfaceBoost,
      0.018,
      glassLike ? 0.62 : 0.58,
    );
    ctx.fillStyle = `rgba(${color[0]}, ${color[1]}, ${color[2]}, ${alpha})`;
    ctx.beginPath();
    ctx.arc(px, py, size, 0, Math.PI * 2);
    ctx.fill();
    if (glassLike && surfaceRim > 0.7 && seeded(point.x * 911, point.z * 613 + elapsed) > 0.82) {
      ctx.fillStyle = `rgba(210, 248, 255, ${alpha * 0.32})`;
      ctx.beginPath();
      ctx.arc(px, py, clamp(size * 1.65, 0.42, 3.8), 0, Math.PI * 2);
      ctx.fill();
    }
    if (controls.speaking_energy > 0.2 && seeded(px, py + elapsed) > 0.86) {
      drawParticleStroke(ctx, px, py, flow.angle, size * (2.4 + controls.speaking_energy * 2.2), size * 0.78, color, alpha * 0.28);
    }
  }
  ctx.globalCompositeOperation = "source-over";
}

const WEBGL_CARTRIDGE_VERTEX_SHADER = `
precision highp float;
precision mediump int;
attribute vec3 aPosition;
attribute vec4 aColor;
attribute float aSize;
uniform vec2 uResolution;
uniform float uElapsed;
uniform float uZoom;
uniform vec2 uOffset;
uniform int uMaterialMode;
uniform float uDeviceScale;
uniform float uUserYaw;
uniform float uUserPitch;
varying vec4 vColor;
varying float vRim;
varying float vFront;

vec3 rotateY(vec3 p, float angle) {
  float c = cos(angle);
  float s = sin(angle);
  return vec3(p.x * c - p.z * s, p.y, p.x * s + p.z * c);
}

vec3 rotateX(vec3 p, float angle) {
  float c = cos(angle);
  float s = sin(angle);
  return vec3(p.x, p.y * c - p.z * s, p.y * s + p.z * c);
}

void main() {
  vec3 p = rotateY(aPosition, uElapsed * 0.24 + uUserYaw);
  p = rotateX(p, sin(uElapsed * 0.17) * 0.13 + uUserPitch);
  float radius = length(aPosition);
  float perspective = clamp(1.0 / (1.0 + p.z * 0.28), 0.62, 1.92);
  vec2 projected = (p.xy + uOffset) * uZoom * perspective;
  projected.x *= 0.74;
  projected.y *= 0.74 * (uResolution.x / max(uResolution.y, 1.0));
  gl_Position = vec4(projected, 0.0, 1.0);
  float materialScale = uMaterialMode == 1 ? 1.28 : 1.0;
  gl_PointSize = clamp(aSize * uDeviceScale * perspective * materialScale, 1.0, 7.0);
  vRim = smoothstep(0.52, 1.18, radius);
  vFront = 1.0 - smoothstep(-0.16, 0.92, p.z);
  vColor = aColor;
}
`;

const WEBGL_CARTRIDGE_FRAGMENT_SHADER = `
precision highp float;
precision mediump int;
varying vec4 vColor;
varying float vRim;
varying float vFront;
uniform int uMaterialMode;

void main() {
  vec2 uv = gl_PointCoord - vec2(0.5);
  float d = dot(uv, uv);
  if (d > 0.25) {
    discard;
  }
  float core = smoothstep(0.25, 0.0, d);
  float edge = smoothstep(0.05, 0.24, d);
  vec3 color = vColor.rgb;
  float alpha = vColor.a * (0.18 + core * 0.66);
  alpha *= mix(0.18, 1.0, vFront);
  if (uMaterialMode == 1) {
    color = mix(color, vec3(0.78, 0.97, 1.0), edge * (0.18 + vRim * 0.42));
    alpha *= 0.82 + vRim * 0.58;
  } else if (uMaterialMode == 2) {
    color = mix(color, vec3(1.0, 0.88, 0.64), edge * 0.22);
  } else if (uMaterialMode == 3) {
    color = mix(color, vec3(0.43, 0.92, 1.0), edge * 0.3);
  }
  gl_FragColor = vec4(color, alpha);
}
`;

function createWebglShader(gl: WebGLRenderingContext | WebGL2RenderingContext, type: number, source: string) {
  const shader = gl.createShader(type);
  if (!shader) return null;
  gl.shaderSource(shader, source);
  gl.compileShader(shader);
  if (!gl.getShaderParameter(shader, gl.COMPILE_STATUS)) {
    gl.deleteShader(shader);
    return null;
  }
  return shader;
}

function createWebglCartridgeResources(canvas: HTMLCanvasElement): { resources: WebglCartridgeResources | null; reason: string } {
  const gl = canvas.getContext("webgl", {
    alpha: true,
    antialias: false,
    depth: false,
    premultipliedAlpha: false,
    preserveDrawingBuffer: false,
  }) ?? canvas.getContext("webgl2", {
    alpha: true,
    antialias: false,
    depth: false,
    premultipliedAlpha: false,
    preserveDrawingBuffer: false,
  });
  if (!gl) return { resources: null, reason: "no_webgl_context" };
  const vertex = createWebglShader(gl, gl.VERTEX_SHADER, WEBGL_CARTRIDGE_VERTEX_SHADER);
  const fragment = createWebglShader(gl, gl.FRAGMENT_SHADER, WEBGL_CARTRIDGE_FRAGMENT_SHADER);
  if (!vertex || !fragment) return { resources: null, reason: "shader_compile_failed" };
  const program = gl.createProgram();
  if (!program) return { resources: null, reason: "program_create_failed" };
  gl.attachShader(program, vertex);
  gl.attachShader(program, fragment);
  gl.linkProgram(program);
  gl.deleteShader(vertex);
  gl.deleteShader(fragment);
  if (!gl.getProgramParameter(program, gl.LINK_STATUS)) {
    const linkLog = String(gl.getProgramInfoLog(program) || "unknown").replace(/[^0-9A-Za-z가-힣_.:-]+/g, "_").slice(0, 120);
    gl.deleteProgram(program);
    return { resources: null, reason: `program_link_failed:${linkLog}` };
  }
  const positionBuffer = gl.createBuffer();
  const colorBuffer = gl.createBuffer();
  const sizeBuffer = gl.createBuffer();
  if (!positionBuffer || !colorBuffer || !sizeBuffer) return { resources: null, reason: "buffer_create_failed" };
  const resources: WebglCartridgeResources = {
    gl,
    program,
    positionBuffer,
    colorBuffer,
    sizeBuffer,
    positionLocation: gl.getAttribLocation(program, "aPosition"),
    colorLocation: gl.getAttribLocation(program, "aColor"),
    sizeLocation: gl.getAttribLocation(program, "aSize"),
    resolutionLocation: gl.getUniformLocation(program, "uResolution"),
    elapsedLocation: gl.getUniformLocation(program, "uElapsed"),
    zoomLocation: gl.getUniformLocation(program, "uZoom"),
    offsetLocation: gl.getUniformLocation(program, "uOffset"),
    materialModeLocation: gl.getUniformLocation(program, "uMaterialMode"),
    deviceScaleLocation: gl.getUniformLocation(program, "uDeviceScale"),
    userYawLocation: gl.getUniformLocation(program, "uUserYaw"),
    userPitchLocation: gl.getUniformLocation(program, "uUserPitch"),
    sourceKey: "",
  };
  if (resources.positionLocation < 0 || resources.colorLocation < 0 || resources.sizeLocation < 0) {
    return { resources: null, reason: "attribute_location_missing" };
  }
  webglCartridgeResources.set(canvas, resources);
  return { resources, reason: "ready" };
}

function splatraMaterialMode(materialHint: string) {
  if (materialHint === "glass") return 1;
  if (materialHint === "metal") return 2;
  if (materialHint === "water") return 3;
  return 0;
}

function drawSplatraCartridgeWebGL(
  canvas: HTMLCanvasElement,
  cartridge: SplatraLoadedCartridge,
  width: number,
  height: number,
  elapsed: number,
  controls: ParticleControls,
  transform: SceneTransform,
  view: CartridgeViewState,
): WebglCartridgeRenderResult {
  let resources = webglCartridgeResources.get(canvas) ?? null;
  if (!resources) {
    const created = createWebglCartridgeResources(canvas);
    resources = created.resources;
    if (!resources) return { ok: false, reason: created.reason };
  }
  const { gl } = resources;
  try {
    if (canvas.width !== width || canvas.height !== height) {
      canvas.width = width;
      canvas.height = height;
    }
    gl.viewport(0, 0, width, height);
    gl.clearColor(0, 0, 0, 0);
    gl.clear(gl.COLOR_BUFFER_BIT);
    gl.useProgram(resources.program);
    const sourceKey = `${cartridge.url}:${cartridge.particleCount}:${cartridge.materialHint}`;
    if (resources.sourceKey !== sourceKey) {
      gl.bindBuffer(gl.ARRAY_BUFFER, resources.positionBuffer);
      gl.bufferData(gl.ARRAY_BUFFER, cartridge.webgl.positions, gl.STATIC_DRAW);
      gl.bindBuffer(gl.ARRAY_BUFFER, resources.colorBuffer);
      gl.bufferData(gl.ARRAY_BUFFER, cartridge.webgl.colors, gl.STATIC_DRAW);
      gl.bindBuffer(gl.ARRAY_BUFFER, resources.sizeBuffer);
      gl.bufferData(gl.ARRAY_BUFFER, cartridge.webgl.sizes, gl.STATIC_DRAW);
      resources.sourceKey = sourceKey;
    }
    gl.bindBuffer(gl.ARRAY_BUFFER, resources.positionBuffer);
    gl.enableVertexAttribArray(resources.positionLocation);
    gl.vertexAttribPointer(resources.positionLocation, 3, gl.FLOAT, false, 0, 0);
    gl.bindBuffer(gl.ARRAY_BUFFER, resources.colorBuffer);
    gl.enableVertexAttribArray(resources.colorLocation);
    gl.vertexAttribPointer(resources.colorLocation, 4, gl.FLOAT, false, 0, 0);
    gl.bindBuffer(gl.ARRAY_BUFFER, resources.sizeBuffer);
    gl.enableVertexAttribArray(resources.sizeLocation);
    gl.vertexAttribPointer(resources.sizeLocation, 1, gl.FLOAT, false, 0, 0);
    const pressure = layoutCollisionPressure(controls);
    const materialBoost = cartridge.realGeneratorUsed ? 0.62 : 1;
    const zoom = transform.zoom * (1 - pressure * 0.08) * materialBoost;
    if (resources.resolutionLocation) gl.uniform2f(resources.resolutionLocation, width, height);
    if (resources.elapsedLocation) gl.uniform1f(resources.elapsedLocation, elapsed);
    if (resources.zoomLocation) gl.uniform1f(resources.zoomLocation, zoom);
    if (resources.offsetLocation) gl.uniform2f(resources.offsetLocation, transform.offsetX, -transform.offsetY);
    if (resources.materialModeLocation) gl.uniform1i(resources.materialModeLocation, splatraMaterialMode(cartridge.materialHint));
    if (resources.userYawLocation) gl.uniform1f(resources.userYawLocation, view.yaw);
    if (resources.userPitchLocation) gl.uniform1f(resources.userPitchLocation, view.pitch);
    if (resources.deviceScaleLocation) {
      gl.uniform1f(resources.deviceScaleLocation, Math.max(1.4, Math.min(window.devicePixelRatio || 1, 2.2)) * (cartridge.realGeneratorUsed ? 1.9 : 1.2));
    }
    gl.disable(gl.DEPTH_TEST);
    gl.enable(gl.BLEND);
    if (cartridge.realGeneratorUsed) {
      gl.blendFunc(gl.SRC_ALPHA, gl.ONE_MINUS_SRC_ALPHA);
    } else {
      gl.blendFunc(gl.SRC_ALPHA, gl.ONE);
    }
    gl.drawArrays(gl.POINTS, 0, cartridge.particleCount);
    const error = gl.getError();
    if (error !== gl.NO_ERROR) return { ok: false, reason: `webgl_error_${error}` };
    return { ok: true, reason: "webgl_points_active" };
  } catch {
    return { ok: false, reason: "draw_exception" };
  }
}

function drawSceneObjectCloud(
  ctx: CanvasRenderingContext2D,
  object: SceneRenderObject,
  width: number,
  height: number,
  elapsed: number,
  sceneElapsed: number,
  active: boolean,
  controls: ParticleControls,
  cameraView: SceneCameraView,
  centralScale = 1,
) {
  const alphaMultiplier = sceneObjectAlpha(object.beat, sceneElapsed, active);
  if (alphaMultiplier <= 0.02) return;
  const roleStyle = sceneRoleStyle(object.beat, active);
  const density = sceneBeatParticleDensity(object.beat, active);
  const position = sceneMotionPathPoint(object.beat, sceneElapsed);
  const beatProgress = sceneObjectProgress(object.beat, sceneElapsed);
  const sourceHold = sceneMotionSourceHold(object.beat, sceneElapsed);
  const motionSwing = object.beat.op === "move" ? Math.sin(beatProgress * Math.PI) : 0;
  const flowSalt = stableUnit(object.id, 43);
  const center = scenePointToCanvas(
    object.beat,
    position,
    width,
    height,
    sceneElapsed,
    {
      x: motionSwing * (flowSalt - 0.5) * 0.11,
      y: motionSwing * (stableUnit(object.id, 47) - 0.5) * 0.08,
    },
    cameraView,
  );
  const cx = center.x;
  const cy = center.y;
  const transform = sceneTransform(object.beat, true, sceneElapsed);
  const scaleBias = (active ? 1.12 : 0.78) * roleStyle.scale * (sourceHold > 0 ? 0.84 : 1) * clamp(0.92 + density * 0.08, 0.94, 1.16);
  const pressure = layoutCollisionPressure(controls);
  const scale = Math.min(width, height) * 0.11 * transform.zoom * centralScale * scaleBias * (1 - pressure * 0.08);
  const rotation = elapsed * (0.12 + controls.arousal * 0.11) + stableUnit(object.id, 5) * Math.PI * 2;
  const tilt = Math.sin(elapsed * 0.16 + stableUnit(object.id, 9) * 4) * 0.18;
  const pulse = 1 + Math.sin(elapsed * (2.1 + roleStyle.trail) + stableUnit(object.id, 17) * 4) * (active ? 0.035 : 0.018) * roleStyle.focus;
  const cosY = Math.cos(rotation);
  const sinY = Math.sin(rotation);
  const cosX = Math.cos(tilt);
  const sinX = Math.sin(tilt);

  if (roleStyle.trail > 0.4) {
    const wakeLength = Math.min(width, height) * (0.06 + roleStyle.trail * 0.035);
    const wakeAngle = flowFieldAngle(cx, cy, elapsed, flowSalt * 11);
    for (let index = 0; index < 9; index += 1) {
      const t = index / 8;
      const wakeX = cx - Math.cos(wakeAngle) * wakeLength * t;
      const wakeY = cy - Math.sin(wakeAngle) * wakeLength * t;
      drawGuideParticle(ctx, wakeX, wakeY, Math.min(width, height) * (0.002 + (1 - t) * 0.003), [76, 230, 255], alphaMultiplier * roleStyle.trail * (0.12 + (1 - t) * 0.26));
    }
  }

  const poseProgress = sceneFigurePoseProgress(object.beat, sceneElapsed);
  object.particles.forEach((point, index) => {
    const basePoint = object.poseBaseParticles?.[index];
    let x = basePoint ? basePoint.x * (1 - poseProgress) + point.x * poseProgress : point.x;
    let y = basePoint ? basePoint.y * (1 - poseProgress) + point.y * poseProgress : point.y;
    let z = basePoint ? basePoint.z * (1 - poseProgress) + point.z * poseProgress : point.z;
    const rx = x * cosY - z * sinY;
    const rz = x * sinY + z * cosY;
    x = rx;
    z = rz;
    const ry = y * cosX - z * sinX;
    z = y * sinX + z * cosX;
    y = ry;
    const depth = clamp((z + 2.4) / 4.8, 0.08, 1);
    const px = cx + x * scale * pulse;
    const py = cy + y * scale * pulse;
    const color: [number, number, number] = [
      Math.floor(point.r * 255),
      Math.floor(point.g * 255),
      Math.floor(point.b * 255),
    ];
    const size = clamp(point.scale * (0.42 + depth * 0.72) * scaleBias, 0.32, active ? 2.75 : 1.95);
    const alpha = clamp(point.a * (0.13 + depth * 0.56) * alphaMultiplier * roleStyle.alpha * clamp(0.82 + density * 0.11, 0.84, 1.2) * (1 - layoutFieldQuieting(controls) * 0.18), 0.02, active ? 0.78 : 0.5);
    const angle = flowFieldAngle(px, py, elapsed, point.x * 1.7 + point.z * 0.9 + stableUnit(object.id, 31));
    drawParticleStroke(ctx, px, py, angle, clamp(size * (2.15 + controls.curiosity * 2.1 + roleStyle.trail * 1.55 + density * 0.34), 1.2, 9.8), size, color, alpha);
  });
}

function drawSceneMotionPathFlow(
  ctx: CanvasRenderingContext2D,
  object: SceneRenderObject,
  width: number,
  height: number,
  elapsed: number,
  sceneElapsed: number,
  active: boolean,
  cameraView: SceneCameraView,
  centralScale = 1,
  density = 1,
) {
  const from = Array.isArray(object.beat.motion_path?.from) ? object.beat.motion_path?.from ?? [] : [];
  const to = Array.isArray(object.beat.motion_path?.to) ? object.beat.motion_path?.to ?? [] : [];
  if (from.length < 2 || to.length < 2) return;

  const fromPoint = {
    x: Number.isFinite(Number(from[0])) ? Number(from[0]) : 0,
    y: Number.isFinite(Number(from[1])) ? Number(from[1]) : 0,
  };
  const toPoint = {
    x: Number.isFinite(Number(to[0])) ? Number(to[0]) : 0,
    y: Number.isFinite(Number(to[1])) ? Number(to[1]) : 0,
  };
  const progress = sceneObjectProgress(object.beat, sceneElapsed);
  const unit = Math.min(width, height);
  const steps = Math.round(clamp(24 * density, 24, 62));
  const points: Array<[number, number]> = [];
  for (let index = 0; index <= steps; index += 1) {
    const t = index / steps;
    const arc = Math.sin(t * Math.PI) * 0.22;
    const modelPoint = {
      x: fromPoint.x * (1 - t) + toPoint.x * t,
      y: fromPoint.y * (1 - t) + toPoint.y * t + arc,
    };
    const canvasPoint = scenePointToCanvas(object.beat, modelPoint, width, height, sceneElapsed, { x: 0, y: 0 }, cameraView);
    points.push([canvasPoint.x, canvasPoint.y]);
  }
  const baseAlpha = (active ? 0.036 : 0.016) * centralScale * clamp(0.86 + density * 0.14, 0.88, 1.26);
  drawParticlePolyline(ctx, points, [76, 230, 255], baseAlpha, unit, Math.floor(stableUnit(object.id, 73) * 1000), elapsed);

  const streamCount = Math.round(clamp((active ? 18 : 10) * density, active ? 18 : 10, active ? 46 : 28));
  for (let index = 0; index < streamCount; index += 1) {
    const local = clamp(progress - index * (0.034 / clamp(density, 1, 2.8)) + Math.sin(elapsed * 0.9 + index) * 0.01, 0, 1);
    const arc = Math.sin(local * Math.PI) * 0.22;
    const modelPoint = {
      x: fromPoint.x * (1 - local) + toPoint.x * local,
      y: fromPoint.y * (1 - local) + toPoint.y * local + arc,
    };
    const canvasPoint = scenePointToCanvas(object.beat, modelPoint, width, height, sceneElapsed, { x: 0, y: 0 }, cameraView);
    const fade = 1 - index / Math.max(1, streamCount);
    drawGuideParticle(
      ctx,
      canvasPoint.x,
      canvasPoint.y,
        unit * (0.0012 + fade * 0.0024) * centralScale,
        index % 3 === 0 ? [255, 104, 177] : [76, 230, 255],
        (active ? 0.3 : 0.14) * fade * clamp(0.82 + density * 0.1, 0.88, 1.18),
      );
  }
}

function drawSceneMotionParticipantFlow(
  ctx: CanvasRenderingContext2D,
  points: Array<{ object: SceneRenderObject; x: number; y: number }>,
  unit: number,
  elapsed: number,
  centralScale: number,
  groupSalt: number,
) {
  const subject = points.find((point) => sceneMotionRole(point.object.beat) === "subject");
  const source = points.find((point) => sceneMotionRole(point.object.beat) === "source");
  const target = points.find((point) => sceneMotionRole(point.object.beat) === "target");
  if (!subject || !source || !target) return false;

  const sourceSubjectTarget: Array<[number, number]> = [
    [source.x, source.y],
    [
      (source.x + subject.x) / 2 + Math.sin(elapsed * 0.27 + groupSalt) * unit * 0.018,
      (source.y + subject.y) / 2 - unit * 0.075,
    ],
    [subject.x, subject.y],
    [
      (subject.x + target.x) / 2 + Math.cos(elapsed * 0.31 + groupSalt) * unit * 0.02,
      (subject.y + target.y) / 2 - unit * 0.052,
    ],
    [target.x, target.y],
  ];

  drawParticlePolyline(ctx, sourceSubjectTarget, [76, 230, 255], 0.026 * centralScale, unit, groupSalt + 401, elapsed);

  for (let index = 0; index < 34; index += 1) {
    const leg = index < 10 ? 0 : 1;
    const localIndex = leg === 0 ? index : index - 10;
    const steps = leg === 0 ? 10 : 12;
    const from = leg === 0 ? source : subject;
    const to = leg === 0 ? subject : target;
    const t = (localIndex / steps + elapsed * (0.045 + leg * 0.018) + seeded(index, groupSalt + 503) * 0.08) % 1;
    const lift = Math.sin(t * Math.PI) * unit * (leg === 0 ? -0.07 : -0.052);
    const curl = Math.sin(t * Math.PI * 5 + elapsed * 1.4 + groupSalt) * unit * 0.018;
    const x = from.x * (1 - t) + to.x * t + curl;
    const y = from.y * (1 - t) + to.y * t + lift;
    const fade = 0.38 + Math.sin(t * Math.PI) * 0.62;
    drawGuideParticle(
      ctx,
      x,
      y,
      unit * (0.0014 + fade * 0.0021) * centralScale,
      leg === 0 ? [76, 230, 255] : [255, 104, 177],
      0.18 * fade * centralScale,
    );
  }

  drawParticleEllipse(ctx, subject.x, subject.y, unit * 0.026, unit * 0.017, elapsed * 0.32, [255, 255, 255], 0.085 * centralScale, unit, groupSalt + 607, elapsed);
  return true;
}

function drawSceneGroupRelationField(
  ctx: CanvasRenderingContext2D,
  activeObject: SceneRenderObject | null,
  visibleObjects: SceneRenderObject[],
  width: number,
  height: number,
  elapsed: number,
  sceneElapsed: number,
  cameraView: SceneCameraView,
  centralScale = 1,
) {
  const groupObjects = sceneActiveGroupObjects(activeObject, visibleObjects);
  if (groupObjects.length < 2) return;
  const unit = Math.min(width, height);
  const points = groupObjects.map((object) => {
    const modelPoint = sceneMotionPathPoint(object.beat, sceneElapsed);
    const canvasPoint = scenePointToCanvas(object.beat, modelPoint, width, height, sceneElapsed, { x: 0, y: 0 }, cameraView);
    return {
      object,
      x: canvasPoint.x,
      y: canvasPoint.y,
    };
  });
  const primary = points.find((point) => sceneMotionRole(point.object.beat) === "subject") ?? points[0];
  const xs = points.map((point) => point.x);
  const ys = points.map((point) => point.y);
  const centerX = xs.reduce((total, value) => total + value, 0) / points.length;
  const centerY = ys.reduce((total, value) => total + value, 0) / points.length;
  const radiusX = clamp((Math.max(...xs) - Math.min(...xs)) * 0.56 + unit * 0.055, unit * 0.055, unit * 0.22);
  const radiusY = clamp((Math.max(...ys) - Math.min(...ys)) * 0.56 + unit * 0.042, unit * 0.042, unit * 0.18);
  const groupSalt = Math.floor(stableUnit(String(activeObject?.beat.scene_group_id ?? activeObject?.id ?? "group"), 89) * 1000);
  drawParticleEllipse(ctx, centerX, centerY, radiusX, radiusY, elapsed * 0.07, [76, 230, 255], 0.01 * centralScale, unit, groupSalt, elapsed);
  const renderedMotionFlow = drawSceneMotionParticipantFlow(ctx, points, unit, elapsed, centralScale, groupSalt);

  points.slice(1).forEach((target, index) => {
    if (target.object.id === primary.object.id) return;
    if (renderedMotionFlow && sceneMotionRole(target.object.beat)) return;
    const relationLift = target.object.beat.visual_affordance === "organic_structure" || primary.object.beat.visual_affordance === "organic_structure"
      ? -unit * 0.055
      : unit * 0.028 * Math.sin(elapsed * 0.31 + index);
    const midX = (primary.x + target.x) / 2 + Math.sin(elapsed * 0.23 + index * 1.7) * unit * 0.012;
    const midY = (primary.y + target.y) / 2 + relationLift;
    const alpha = (target.object.beat.op === "move" || target.object.beat.motion_path ? 0.034 : 0.018) * centralScale;
    drawParticlePolyline(
      ctx,
      [[primary.x, primary.y], [midX, midY], [target.x, target.y]],
      index % 2 === 0 ? [76, 230, 255] : [255, 104, 177],
      alpha,
      unit,
      groupSalt + index * 31,
      elapsed,
    );
  });
}

function drawSceneFocusSwarm(
  ctx: CanvasRenderingContext2D,
  activeObject: SceneRenderObject | null,
  visibleObjects: SceneRenderObject[],
  width: number,
  height: number,
  elapsed: number,
  sceneElapsed: number,
  controls: ParticleControls,
  cameraView: SceneCameraView,
  centralScale = 1,
) {
  if (!activeObject) return;
  const unit = Math.min(width, height);
  const pressure = layoutCollisionPressure(controls);
  const fieldQuieting = layoutFieldQuieting(controls);
  const flowRecombine = layoutFlowRecombine(controls);
  const center = sceneObjectCanvasCenter(activeObject, width, height, sceneElapsed, cameraView);
  const groupObjects = sceneActiveGroupObjects(activeObject, visibleObjects);
  const attractors = (groupObjects.length ? groupObjects : [activeObject])
    .map((object) => sceneObjectCanvasCenter(object, width, height, sceneElapsed, cameraView));
  const behavior = String(activeObject.beat.particle_behavior ?? "");
  const moving = activeObject.beat.op === "move" || Boolean(activeObject.beat.motion_path);
  const roleStyle = sceneRoleStyle(activeObject.beat, true);
  const density = sceneBeatParticleDensity(activeObject.beat, true);
  const count = Math.round(clamp(unit * (moving ? 0.36 : 0.26) * density * centralScale * (1 - fieldQuieting * 0.22), 160, 780));
  const fieldRadius = unit * clamp(0.1 + roleStyle.focus * 0.045 + controls.curiosity * 0.025 + flowRecombine * 0.025, 0.1, 0.22) * centralScale;
  const salt = Math.floor(stableUnit(activeObject.id, 991) * 10000);
  const pulse = 0.55 + Math.sin(elapsed * 1.1 + salt) * 0.18 + controls.speaking_energy * 0.18;
  ctx.globalCompositeOperation = "lighter";
  for (let index = 0; index < count; index += 1) {
    const local = (index + 0.5) / Math.max(1, count);
    const attractor = attractors[index % attractors.length] ?? center;
    const orbit = elapsed * (0.18 + seeded(index, salt + 3) * 0.18) + seeded(index, salt + 5) * Math.PI * 2;
    const ring = Math.sqrt(seeded(index, salt + 7)) * fieldRadius * (0.46 + seeded(index, salt + 11) * 0.82);
    const tide = Math.sin(elapsed * 0.47 + local * Math.PI * 4 + salt) * unit * 0.022 * centralScale;
    const rawX = attractor.x + Math.cos(orbit) * ring + Math.sin(orbit * 1.7) * tide;
    const rawY = attractor.y + Math.sin(orbit * 0.78) * ring * 0.62 + Math.cos(orbit * 1.3) * tide;
    const pull = 0.42 + pulse * 0.16 - pressure * 0.08;
    const px = rawX * (1 - pull) + center.x * pull;
    const py = rawY * (1 - pull) + center.y * pull;
    const fieldAngle = flowFieldAngle(px, py, elapsed, salt * 0.001 + index * 0.13);
    const color: [number, number, number] = behavior === "gravity_arc"
      ? (index % 4 === 0 ? [255, 255, 255] : [76, 230, 255])
      : index % 5 === 0 ? [255, 104, 177] : [76, 230, 255];
    const size = unit * (0.00078 + seeded(index, salt + 13) * 0.00145) * centralScale;
    const length = unit * (0.006 + controls.curiosity * 0.006 + (moving ? 0.005 : 0.002) + flowRecombine * 0.005 + density * 0.002) * centralScale;
    const alpha = (0.026 + roleStyle.focus * 0.03 + controls.speaking_energy * 0.02)
      * (0.35 + seeded(index, salt + 17) * 0.65)
      * centralScale
      * (1 - fieldQuieting * 0.28);
    drawParticleStroke(ctx, px, py, fieldAngle, length, size, color, alpha);
  }
  ctx.globalCompositeOperation = "source-over";
}

function drawSceneFocusParticles(
  ctx: CanvasRenderingContext2D,
  sceneObjects: SceneRenderObject[],
  activeObjectId: string | null,
  width: number,
  height: number,
  elapsed: number,
  sceneElapsed: number,
  controls: ParticleControls,
  centralScale = 1,
) {
  ctx.clearRect(0, 0, width, height);
  const pressure = layoutCollisionPressure(controls);
  const fieldQuieting = layoutFieldQuieting(controls);
  const layoutAwareCentralScale = centralScale * (1 - pressure * 0.12);
  const centerGlow = ctx.createRadialGradient(width / 2, height / 2, 0, width / 2, height / 2, Math.max(width, height) * 0.48);
  centerGlow.addColorStop(0, `rgba(255,255,255,${0.035 * (1 - fieldQuieting * 0.36)})`);
  centerGlow.addColorStop(0.38, `rgba(43,223,255,${0.03 * (1 - fieldQuieting * 0.34)})`);
  centerGlow.addColorStop(1, "rgba(0,0,0,0)");
  ctx.fillStyle = centerGlow;
  ctx.fillRect(0, 0, width, height);

  const visibleCandidates = sceneObjects.filter((object) => sceneObjectAlpha(object.beat, sceneElapsed, object.id === activeObjectId) > 0.02);
  const visibleObjects = sceneVisibleTrackObjects(visibleCandidates, activeObjectId, sceneElapsed);
  const activeObject = visibleObjects.find((object) => object.id === activeObjectId) ?? visibleObjects[0] ?? null;
  const cameraView = blendedSceneCameraView(activeObject, visibleObjects, sceneElapsed);
  cameraView.zoom = clamp(cameraView.zoom * layoutAwareCentralScale, 0.82, 1.82);
  drawSceneGroupRelationField(ctx, activeObject, visibleObjects, width, height, elapsed, sceneElapsed, cameraView, layoutAwareCentralScale);
  drawSceneFocusSwarm(ctx, activeObject, visibleObjects, width, height, elapsed, sceneElapsed, controls, cameraView, layoutAwareCentralScale);
  visibleObjects.forEach((object) => {
    const sameGroup = sameSceneGroup(object.beat, activeObject?.beat);
    drawSceneMotionPathFlow(ctx, object, width, height, elapsed, sceneElapsed, object.id === activeObjectId || sameGroup, cameraView, layoutAwareCentralScale, sceneBeatParticleDensity(object.beat, object.id === activeObjectId || sameGroup));
  });

  visibleObjects.forEach((object) => {
    const sameGroup = sameSceneGroup(object.beat, activeObject?.beat);
    drawSceneObjectCloud(ctx, object, width, height, elapsed, sceneElapsed, object.id === activeObjectId || sameGroup, controls, cameraView, layoutAwareCentralScale);
  });
}

export default function SplatraImaginationField({
  mode = "product",
  state = "idle",
  particleBudget,
  className,
  interactive = true,
  controlOverride,
  onActivate,
  onCancel,
  sceneFocus = false,
  scenePlan = null,
  splatraCommandSequence = null,
  splatraCartridgeQueue = null,
  activeSpeechBeatIndex = -1,
}: Props) {
  const canvasRef = useRef<HTMLCanvasElement | null>(null);
  const webglCanvasRef = useRef<HTMLCanvasElement | null>(null);
  const webglCartridgeActiveRef = useRef(false);
  const webglCartridgeStatusRef = useRef("not_requested");
  const cartridgeViewRef = useRef<CartridgeViewState>({ yaw: 0, pitch: 0, dragging: false, returning: false });
  const cartridgeDragRef = useRef({ active: false, pointerId: -1, lastX: 0, lastY: 0 });
  const [archetype, setArchetype] = useState<Archetype>(() => (mode === "product" ? "constellation" : "orb"));
  const [seedNonce, setSeedNonce] = useState(0);
  const [frame, setFrame] = useState<ImaginationFrame | null>(null);
  const [status, setStatus] = useState<Record<string, any> | null>(null);
  const [error, setError] = useState("");
  const [reducedMotion, setReducedMotion] = useState(false);
  const [sceneStartedAt, setSceneStartedAt] = useState(0);
  const [activeSceneBeatIndex, setActiveSceneBeatIndex] = useState(-1);
  const [loadedCartridge, setLoadedCartridge] = useState<SplatraLoadedCartridge | null>(null);
  const [webglCartridgeActive, setWebglCartridgeActive] = useState(false);
  const [webglCartridgeStatus, setWebglCartridgeStatus] = useState("not_requested");
  const [cartridgeViewState, setCartridgeViewState] = useState<CartridgeViewState>(() => cartridgeViewRef.current);
  const budget = particleBudget ?? (mode === "lab" ? 1400 : 520);
  const controls = useMemo<ParticleControls>(() => {
    const base = STATE_CONTROLS[state] ?? STATE_CONTROLS.idle;
    if (!controlOverride) return base;
    return {
      ...base,
      ...Object.fromEntries(
        Object.entries(controlOverride).filter(([, value]) => value !== undefined && value !== null),
      ),
    };
  }, [controlOverride, state]);
  const particles = frame?.object?.particles?.length ? frame.object.particles : fallbackParticles(archetype, budget);
  const activeArchetype = frame?.object?.archetype ?? archetype;
  const stageMode = sceneFocus || scenePlan?.stage_layout === "scene_focus";
  const centralSceneScale = scenePlanCentralScale(scenePlan);
  const syncedBeatIndex = activeSpeechBeatIndex >= 0 ? activeSpeechBeatIndex : activeSceneBeatIndex;
  const activeSpeechTimelineBeat = activeSpeechBeatIndex >= 0 && Array.isArray(scenePlan?.speech_timeline)
    ? scenePlan?.speech_timeline?.find((beat) => beat?.beat_index === activeSpeechBeatIndex)
    : null;
  const activeLayoutTimelineBeat = syncedBeatIndex >= 0 && Array.isArray(scenePlan?.layout_timeline)
    ? scenePlan?.layout_timeline?.find((beat) => beat?.beat_index === syncedBeatIndex)
    : null;
  const activeSceneBeat = (
    syncedBeatIndex >= 0 && Array.isArray(scenePlan?.beats) ? scenePlan?.beats?.[syncedBeatIndex] : null
  ) ?? activeSpeechTimelineBeat ?? activeLayoutTimelineBeat ?? firstEvidenceBearingBeat(scenePlan);
  const renderScenePlan = useMemo(
    () => scenePlanWithCommandSequence(scenePlan, splatraCommandSequence),
    [scenePlan, splatraCommandSequence],
  );
  const sceneObjects = useMemo(() => buildSceneRenderObjects(renderScenePlan, budget), [budget, renderScenePlan]);
  const activeSceneObjectId = activeSceneBeat ? sceneObjectId(activeSceneBeat, Math.max(0, syncedBeatIndex)) : null;
  const activeSceneGroupId = activeSceneBeat?.scene_group_id ?? "";
  const activeSceneGroupSize = activeSceneGroupId ? sceneObjects.filter((object) => sameSceneGroup(object.beat, activeSceneBeat)).length : 0;
  const activeSceneFocusBasis = activeSpeechBeatIndex >= 0 ? "speech_timeline" : activeSceneBeat ? "scene_timer" : "ambient_field";
  const activeSceneRole = activeSceneBeat?.semantic_role ?? "none";
  const activeSceneBehavior = activeSceneBeat?.particle_behavior ?? "none";
  const activeSceneDirective = activeSceneBeat?.scene_directive?.stage_instruction ?? "none";
  const activeSceneNarrativeFunction = activeSceneBeat?.scene_directive?.narrative_function ?? "none";
  const activeSceneDirectiveOwner = activeSceneBeat?.scene_directive?.directive_owner ?? "none";
  const activeSceneEvidenceSource = activeSceneBeat?.scene_evidence?.source_type ?? "none";
  const activeSceneEvidenceHash = activeSceneBeat?.scene_evidence?.source_fact_hash ?? "none";
  const activeSceneEvidenceOwner = activeSceneBeat?.scene_evidence?.evidence_owner ?? "none";
  const activeSceneTrackId = activeSceneBeat ? sceneObjectTrackId(activeSceneBeat, Math.max(0, syncedBeatIndex)) : "";
  const activeParticleOperationIntent = sceneParticleIntentForBeat(scenePlan, activeSceneBeat, syncedBeatIndex);
  const activeParticleOperation = String(activeParticleOperationIntent?.operation ?? particleOperationForSceneBeat(activeSceneBeat ?? undefined));
  const activeParticleIntentDensity = sceneParticleIntentDensity(activeParticleOperationIntent, activeSceneBeat, true);
  const safeRegionStrategy = scenePlanSafeRegionStrategy(scenePlan);
  const particleStageStrategy = scenePlanParticleStageStrategy(scenePlan);
  const particleSpace = scenePlanParticleSpace(scenePlan);
  const generatedVisualElements = scenePlanGeneratedVisualElements(scenePlan);
  const lineRendering = scenePlanLineRendering(scenePlan);
  const flowMotionReference = scenePlanFlowMotionReference(scenePlan);
  const textException = scenePlanTextException(scenePlan);
  const orbSelfBodyYield = scenePlanOrbSelfBodyYield(scenePlan);
  const particleRecompositionMode = scenePlanParticleRecompositionMode(scenePlan);
  const layoutAutonomy = scenePlanLayoutAutonomy(scenePlan);
  const orbIdentity = scenePlanOrbIdentity(scenePlan);
  const agentSceneDecisions = Array.isArray(scenePlan?.agent_scene_decisions) ? scenePlan?.agent_scene_decisions ?? [] : [];
  const particleOperationIntents = Array.isArray(scenePlan?.particle_operation_intents) ? scenePlan?.particle_operation_intents ?? [] : [];
  const derivedAgentSceneDecisionCount = Array.isArray(scenePlan?.layout_timeline) ? scenePlan?.layout_timeline?.length ?? 0 : 0;
  const derivedParticleOperationIntentCount = Array.isArray(scenePlan?.beats) ? scenePlan?.beats?.length ?? 0 : 0;
  const agentSceneDecisionCount = agentSceneDecisions.length || (stageMode ? derivedAgentSceneDecisionCount : 0);
  const particleOperationIntentCount = particleOperationIntents.length || (stageMode ? derivedParticleOperationIntentCount : 0);
  const firstParticleOperationIntent = String(particleOperationIntents[0]?.operation ?? particleOperationForSceneBeat(scenePlan?.beats?.[0]) ?? "none");
  const particleOperationIntentSource = particleOperationIntents.length > 0
    ? "explicit_particle_operation_intents"
    : particleOperationIntentCount > 0 ? "derived_from_legacy_scene_beats" : "none";
  const splatraSceneActions = Array.isArray(splatraCommandSequence?.scene_actions) ? splatraCommandSequence?.scene_actions ?? [] : [];
  const splatraCartridgeRequests = Array.isArray(splatraCommandSequence?.candidate_cartridge_requests)
    ? splatraCommandSequence?.candidate_cartridge_requests ?? []
    : [];
  const firstCartridgeFormat = String(splatraCartridgeRequests[0]?.cartridge_format ?? "none");
  const splatraContract = splatraCommandSequence?.splatra_contract ?? {};
  const splatraHotSwap = splatraCommandSequence?.hot_swap_policy ?? {};
  const splatraMotionPolicy = splatraCommandSequence?.particle_motion_policy ?? {};
  const readyCartridge = splatraReadyCartridge(splatraCartridgeQueue);
  const readyCartridgeUrl = readyCartridge?.url ?? "";
  const cartridgeRenderMode = loadedCartridge?.particles.length
    ? webglCartridgeActive
      ? "splatra_sidecar_webgl_points"
      : "splatra_sidecar_cartridge_particles"
    : "procedural_fallback_particles";
  const cartridgeFillRatio = loadedCartridge?.sourceCount
    ? loadedCartridge.particleCount / Math.max(1, loadedCartridge.sourceCount)
    : 0;
  const shouldReturnCartridgeView = stageMode || state === "speaking" || activeSpeechBeatIndex >= 0;
  const publishCartridgeView = (next: CartridgeViewState) => {
    cartridgeViewRef.current = next;
    setCartridgeViewState((current) => (
      Math.abs(current.yaw - next.yaw) > 0.001
      || Math.abs(current.pitch - next.pitch) > 0.001
      || current.dragging !== next.dragging
      || current.returning !== next.returning
        ? next
        : current
    ));
  };
  useEffect(() => {
    const media = window.matchMedia("(prefers-reduced-motion: reduce)");
    const update = () => setReducedMotion(media.matches);
    update();
    media.addEventListener("change", update);
    return () => media.removeEventListener("change", update);
  }, []);

  useEffect(() => {
    fetch("/api/agentic-os/splatra/imagination/status", { cache: "no-store" })
      .then((response) => response.json())
      .then(setStatus)
      .catch(() => setStatus({ available: false }));
  }, []);

  useEffect(() => {
    let cancelled = false;
    async function load(nextArchetype: Archetype) {
      try {
        const response = await fetch("/api/agentic-os/splatra/imagination/generate", {
          method: "POST",
          headers: { "content-type": "application/json" },
          body: JSON.stringify({
            archetype: nextArchetype,
            state,
            particle_budget: budget,
            reduced_motion: reducedMotion,
            include_particles: true,
            seed_id: `dashboard_${nextArchetype}_${seedNonce}`,
            ...controls,
          }),
        });
        if (!response.ok) throw new Error(`HTTP ${response.status}`);
        const payload = await response.json();
        if (!cancelled) {
          setFrame(normalizeFrame(payload));
          setError("");
        }
      } catch (loadError) {
        if (!cancelled) setError(String(loadError));
      }
    }
    load(archetype);
    return () => {
      cancelled = true;
    };
  }, [archetype, budget, controls, reducedMotion, seedNonce, state]);

  useEffect(() => {
    if (!readyCartridgeUrl) {
      setLoadedCartridge(null);
      return undefined;
    }
    let cancelled = false;
    async function loadCartridge() {
      try {
        const cartridgeBudget = Math.min(
          260000,
          Math.max(budget, readyCartridge?.realGeneratorUsed === true ? 180000 : 90000),
        );
        const cartridgeUrl = splatraCartridgeFetchUrl(readyCartridgeUrl, cartridgeBudget);
        const response = await fetch(cartridgeUrl, { cache: "no-store" });
        if (!response.ok) throw new Error(`cartridge HTTP ${response.status}`);
        const buffer = await response.arrayBuffer();
        const parsed = parseSpl2Cartridge(
          buffer,
          cartridgeBudget,
          cartridgeUrl,
          readyCartridge?.prompt ?? "",
          readyCartridge?.realGeneratorUsed === true,
          readyCartridge?.generationEngine ?? "",
        );
        if (!cancelled) {
          setLoadedCartridge(parsed);
          setError("");
        }
      } catch (loadError) {
        if (!cancelled) {
          setLoadedCartridge(null);
          setError(String(loadError));
        }
      }
    }
    loadCartridge();
    return () => {
      cancelled = true;
    };
  }, [budget, readyCartridge?.generationEngine, readyCartridge?.prompt, readyCartridge?.realGeneratorUsed, readyCartridgeUrl]);

  useEffect(() => {
    const beats = Array.isArray(scenePlan?.beats) ? scenePlan?.beats ?? [] : [];
    if (!beats.length) {
      setActiveSceneBeatIndex(-1);
      return;
    }
    setSceneStartedAt(performance.now());
    setActiveSceneBeatIndex(0);
    const nextSceneArchetype = sceneArchetype(scenePlan, 0);
    if (!nextSceneArchetype) return;
    setArchetype(nextSceneArchetype);
    setSeedNonce((value) => value + 1);
  }, [scenePlan]);

  useEffect(() => {
    const beats = Array.isArray(scenePlan?.beats) ? scenePlan?.beats ?? [] : [];
    if (!stageMode || !beats.length || reducedMotion) return undefined;
    const timer = window.setInterval(() => {
      const elapsedSeconds = Math.max(0, (performance.now() - sceneStartedAt) / 1000);
      const nextIndex = sceneBeatIndex(scenePlan, elapsedSeconds);
      setActiveSceneBeatIndex((current) => {
        if (nextIndex === current) return current;
        const nextSceneArchetype = sceneArchetype(scenePlan, nextIndex);
        if (nextSceneArchetype) {
          setArchetype(nextSceneArchetype);
          setSeedNonce((value) => value + 1);
        }
        return nextIndex;
      });
    }, 180);
    return () => window.clearInterval(timer);
  }, [reducedMotion, scenePlan, sceneStartedAt, stageMode]);

  useEffect(() => {
    if (mode !== "product" || reducedMotion) return undefined;
    if (stageMode) return undefined;
    const switchMs = clamp(15000 - Number(controls.curiosity ?? 0.45) * 6400 - Number(controls.speaking_energy ?? 0) * 1800, 7800, 17000);
    const timer = window.setInterval(() => {
      setArchetype((current) => {
        const pressure = Number((controls as any).review_pressure ?? 0);
        const novelty = Number((controls as any).novelty_found ?? controls.curiosity ?? 0);
        const sequence = pressure > 0.58
          ? ["machine_core", "circuit", "city_block", "constellation"] as Archetype[]
          : novelty > 0.62
            ? ["constellation", "circuit", "city_block", "abstract_memory_cloud"] as Archetype[]
            : PRODUCT_ARCHETYPES;
        const index = sequence.indexOf(current);
        return sequence[(index + 1) % sequence.length];
      });
    }, switchMs);
    return () => window.clearInterval(timer);
  }, [controls, mode, reducedMotion, stageMode]);

  useEffect(() => {
    const canvas = canvasRef.current;
    const webglCanvas = webglCanvasRef.current;
    if (!canvas) return undefined;
    const ctx = canvas.getContext("2d");
    if (!ctx) return undefined;
    let animationId = 0;
    const startedAt = performance.now();
    const setWebglActive = (active: boolean) => {
      if (webglCartridgeActiveRef.current === active) return;
      webglCartridgeActiveRef.current = active;
      setWebglCartridgeActive(active);
    };
    const setWebglStatus = (status: string) => {
      if (webglCartridgeStatusRef.current === status) return;
      webglCartridgeStatusRef.current = status;
      setWebglCartridgeStatus(status);
    };
    const render = () => {
      const rect = canvas.getBoundingClientRect();
      const ratio = Math.min(window.devicePixelRatio || 1, mode === "lab" ? 1.6 : 1.45);
      const width = Math.max(280, Math.floor(rect.width * ratio));
      const height = Math.max(260, Math.floor(rect.height * ratio));
      if (canvas.width !== width || canvas.height !== height) {
        canvas.width = width;
        canvas.height = height;
      }
      const elapsed = reducedMotion ? 0.5 : (performance.now() - startedAt) / 1000;
      const sceneElapsed = sceneStartedAt ? Math.max(0, (performance.now() - sceneStartedAt) / 1000) : elapsed;
      const activeTransform = sceneTransform(activeSceneBeat, stageMode, sceneElapsed);
      const currentView = cartridgeViewRef.current;
      if (currentView.returning && !currentView.dragging) {
        const nextYaw = currentView.yaw * 0.86;
        const nextPitch = currentView.pitch * 0.86;
        publishCartridgeView({
          yaw: Math.abs(nextYaw) < 0.002 ? 0 : nextYaw,
          pitch: Math.abs(nextPitch) < 0.002 ? 0 : nextPitch,
          dragging: false,
          returning: Math.abs(nextYaw) >= 0.002 || Math.abs(nextPitch) >= 0.002,
        });
      }
      const cartridgeView = cartridgeViewRef.current;
      if (loadedCartridge?.particles.length) {
        const cartridgeTransform = stageMode
          ? { offsetX: -0.04, offsetY: -0.02, zoom: Math.max(1.12, centralSceneScale * 1.18) }
          : activeTransform;
        const webglResult = webglCanvas
          ? drawSplatraCartridgeWebGL(webglCanvas, loadedCartridge, width, height, elapsed, controls, cartridgeTransform, cartridgeView)
          : { ok: false, reason: "missing_webgl_canvas" };
        setWebglActive(webglResult.ok);
        setWebglStatus(webglResult.reason);
        if (webglResult.ok) {
          ctx.clearRect(0, 0, width, height);
        } else {
          if (webglCanvas) {
            const gl = webglCartridgeResources.get(webglCanvas)?.gl ?? null;
            gl?.clear(gl.COLOR_BUFFER_BIT);
          }
          drawSplatraCartridgeParticles(
            ctx,
            loadedCartridge,
            width,
            height,
            elapsed,
            controls,
            cartridgeTransform,
            cartridgeView,
          );
        }
      } else if (stageMode && sceneObjects.length) {
        setWebglActive(false);
        setWebglStatus("no_cartridge_scene_focus");
        drawSceneFocusParticles(ctx, sceneObjects, activeSceneObjectId, width, height, elapsed, sceneElapsed, controls, centralSceneScale);
      } else {
        setWebglActive(false);
        setWebglStatus("no_cartridge_procedural");
        drawParticles(
          ctx,
          particles,
          activeArchetype,
          width,
          height,
          elapsed,
          controls,
          !stageMode && !interactive && mode === "product",
          mode === "lab",
          activeTransform,
        );
      }
      if (!reducedMotion) animationId = window.requestAnimationFrame(render);
    };
    render();
    return () => window.cancelAnimationFrame(animationId);
  }, [activeArchetype, activeSceneBeat, activeSceneObjectId, activeSpeechBeatIndex, centralSceneScale, controls, interactive, loadedCartridge, mode, particles, reducedMotion, sceneObjects, sceneStartedAt, stageMode, state]);

  function handleCartridgePointerDown(event: PointerEvent<HTMLElement>) {
    if (!loadedCartridge?.particles.length) return;
    cartridgeDragRef.current = {
      active: true,
      pointerId: event.pointerId,
      lastX: event.clientX,
      lastY: event.clientY,
    };
    publishCartridgeView({ ...cartridgeViewRef.current, dragging: true, returning: false });
    event.currentTarget.setPointerCapture?.(event.pointerId);
    event.preventDefault();
  }

  function handleCartridgePointerMove(event: PointerEvent<HTMLElement>) {
    const drag = cartridgeDragRef.current;
    if (!drag.active || drag.pointerId !== event.pointerId) return;
    const dx = event.clientX - drag.lastX;
    const dy = event.clientY - drag.lastY;
    drag.lastX = event.clientX;
    drag.lastY = event.clientY;
    const current = cartridgeViewRef.current;
    publishCartridgeView({
      yaw: current.yaw + dx * 0.008,
      pitch: clamp(current.pitch + dy * 0.006, -0.72, 0.72),
      dragging: true,
      returning: false,
    });
    event.preventDefault();
  }

  function handleCartridgePointerUp(event: PointerEvent<HTMLElement>) {
    const drag = cartridgeDragRef.current;
    if (drag.pointerId === event.pointerId) {
      cartridgeDragRef.current = { active: false, pointerId: -1, lastX: 0, lastY: 0 };
      publishCartridgeView({
        ...cartridgeViewRef.current,
        dragging: false,
        returning: shouldReturnCartridgeView,
      });
      event.currentTarget.releasePointerCapture?.(event.pointerId);
      event.preventDefault();
    }
  }

  function handleClick() {
    if (state === "listening") {
      onCancel?.();
    } else {
      onActivate?.();
    }
  }

  const canvas = (
    <>
      <canvas ref={canvasRef} data-render-layer="canvas-2d" />
      <canvas ref={webglCanvasRef} data-render-layer="webgl-cartridge" aria-hidden="true" />
    </>
  );

  return (
    <section
      className={`splatra-imagination-field ${className ?? ""}`}
      data-mode={mode}
      data-state={state}
      data-particle-budget={budget}
      data-scene-objects={sceneObjects.length}
      data-active-speech-beat={activeSpeechBeatIndex >= 0 ? activeSpeechBeatIndex : "none"}
      data-active-scene-object={activeSceneObjectId || "none"}
      data-active-scene-role={activeSceneRole}
      data-active-scene-behavior={activeSceneBehavior}
      data-active-scene-directive={activeSceneDirective}
      data-active-scene-narrative-function={activeSceneNarrativeFunction}
      data-active-scene-directive-owner={activeSceneDirectiveOwner}
      data-active-scene-evidence-source={activeSceneEvidenceSource}
      data-active-scene-evidence-hash={activeSceneEvidenceHash}
      data-active-scene-evidence-owner={activeSceneEvidenceOwner}
      data-active-scene-track={activeSceneTrackId || "none"}
      data-active-scene-focus-basis={activeSceneFocusBasis}
      data-safe-region-strategy={safeRegionStrategy}
      data-particle-stage-strategy={particleStageStrategy}
      data-particle-space={particleSpace}
      data-generated-visual-elements={generatedVisualElements}
      data-line-rendering={lineRendering}
      data-flow-motion-reference={flowMotionReference}
      data-text-exception={textException}
      data-orb-self-body-yield={orbSelfBodyYield}
      data-particle-recomposition-mode={particleRecompositionMode}
      data-agent-scene-decisions={agentSceneDecisionCount}
      data-particle-operation-intents={particleOperationIntentCount}
      data-first-particle-operation-intent={firstParticleOperationIntent}
      data-particle-operation-intent-source={particleOperationIntentSource}
      data-active-particle-operation={activeParticleOperation}
      data-active-particle-intent-density={activeParticleIntentDensity.toFixed(2)}
      data-scene-render-density-mode="operation_intent_weighted_particles"
      data-layout-autonomy={layoutAutonomy}
      data-orb-identity={orbIdentity}
      data-layout-collision-pressure={layoutCollisionPressure(controls)}
      data-layout-text-avoidance={String(controls.layout_text_avoidance ?? "clear")}
      data-particle-rendering-contract={PARTICLE_RENDERING_CONTRACT}
      data-particle-flow-contract={PARTICLE_FLOW_CONTRACT}
      data-flow-field-basis={FLOW_FIELD_BASIS}
      data-flow-motion-reference-contract={FLOW_MOTION_REFERENCE}
      data-splatra-command-contract={SPLATRA_COMMAND_CONTRACT}
      data-splatra-command-sequence={splatraSceneActions.length > 0 ? "available" : "none"}
      data-splatra-command-actions={splatraSceneActions.length}
      data-splatra-candidate-cartridges={splatraCartridgeRequests.length}
      data-splatra-candidate-cartridge-format={firstCartridgeFormat}
      data-splatra-command-side-channel={String(splatraHotSwap.viewer_side_channel ?? splatraContract.side_channel ?? "none")}
      data-splatra-command-agent-payload={String(splatraContract.agent_context_payload ?? "none")}
      data-splatra-command-hot-swap-mode={String(splatraHotSwap.mode ?? "none")}
      data-splatra-command-raw-buffers={splatraContract.raw_buffers_in_agent_context === true ? "true" : "false"}
      data-splatra-command-topic-templates={splatraContract.topic_scene_templates === true ? "true" : "false"}
      data-splatra-command-renderer-inference={splatraContract.renderer_may_infer_topic === true ? "true" : "false"}
      data-splatra-command-motion-field={String(splatraMotionPolicy.field_model ?? "none")}
      data-splatra-command-agent-control={String(splatraMotionPolicy.agent_control ?? "none")}
      data-splatra-cartridge-render-mode={cartridgeRenderMode}
      data-splatra-cartridge-url={readyCartridgeUrl ? "available" : "none"}
      data-splatra-cartridge-selected-job={readyCartridge?.jobIndex ?? "none"}
      data-splatra-cartridge-selected-source-particles={readyCartridge?.sourceCount ?? 0}
      data-splatra-cartridge-generation-engine={readyCartridge?.generationEngine ?? "none"}
      data-splatra-cartridge-real-generator={readyCartridge?.realGeneratorUsed === true ? "true" : "false"}
      data-splatra-cartridge-loaded-particles={loadedCartridge?.particleCount ?? 0}
      data-splatra-cartridge-source-particles={loadedCartridge?.sourceCount ?? 0}
      data-splatra-cartridge-fill-ratio={cartridgeFillRatio.toFixed(4)}
      data-splatra-cartridge-selection-mode={loadedCartridge?.selectionMode ?? "none"}
      data-splatra-cartridge-reconstruction-path={loadedCartridge?.reconstructionQualityPath ?? "none"}
      data-splatra-cartridge-material={loadedCartridge?.materialHint ?? "none"}
      data-splatra-cartridge-webgl={webglCartridgeActive ? "true" : "false"}
      data-splatra-cartridge-webgl-status={webglCartridgeStatus}
      data-splatra-cartridge-draggable={loadedCartridge?.particles.length ? "true" : "false"}
      data-splatra-cartridge-view-yaw={cartridgeViewState.yaw.toFixed(3)}
      data-splatra-cartridge-view-pitch={cartridgeViewState.pitch.toFixed(3)}
      data-splatra-cartridge-dragging={cartridgeViewState.dragging ? "true" : "false"}
      data-splatra-cartridge-returning={cartridgeViewState.returning ? "true" : "false"}
      data-splatra-cartridge-return-policy={shouldReturnCartridgeView ? "release_returns_to_narration_view" : "free_orbit_hold"}
      data-renderer-content-inference="explicit_scene_plan_hints_only"
      data-active-scene-group={activeSceneGroupId || "none"}
      data-active-scene-group-size={activeSceneGroupSize}
    >
      {interactive ? (
        <button
          type="button"
          className="splatra-imagination-canvas-button"
          aria-label="SPLATRA procedural imagination field"
          onClick={handleClick}
          onPointerDown={handleCartridgePointerDown}
          onPointerMove={handleCartridgePointerMove}
          onPointerUp={handleCartridgePointerUp}
          onPointerCancel={handleCartridgePointerUp}
        >
          {canvas}
        </button>
      ) : (
        <div
          className="splatra-imagination-canvas-button"
          aria-hidden="true"
          onPointerDown={handleCartridgePointerDown}
          onPointerMove={handleCartridgePointerMove}
          onPointerUp={handleCartridgePointerUp}
          onPointerCancel={handleCartridgePointerUp}
        >
          {canvas}
        </div>
      )}
      {mode === "lab" ? (
        <span className="splatra-imagination-product-label" data-scene-beat={activeSceneBeat?.op ?? "ambient"} aria-hidden="true">
          imagination / {ARCHETYPE_LABELS[activeArchetype]}
        </span>
      ) : null}
      {mode === "lab" ? (
        <div className="splatra-imagination-lab">
          <div>
            <small>SPLATRA Imagination Field</small>
            <strong>{ARCHETYPE_LABELS[activeArchetype]}</strong>
            <span>{status?.proof_only === false ? "blocked" : "proof-only"} / product visible={String(status?.product_visible ?? true)}</span>
          </div>
          <label>
            <span>archetype</span>
            <select value={archetype} onChange={(event) => setArchetype(event.target.value as Archetype)}>
              {ARCHETYPES.map((name) => <option key={name} value={name}>{ARCHETYPE_LABELS[name]}</option>)}
            </select>
          </label>
          <div className="splatra-imagination-actions">
            <button
              type="button"
              onClick={() => setArchetype((current) => {
                const index = ARCHETYPES.indexOf(current);
                return ARCHETYPES[(index + 1) % ARCHETYPES.length];
              })}
            >
              switch
            </button>
            <button
              type="button"
              onClick={() => {
                const next = PRODUCT_ARCHETYPES[Math.floor(Math.random() * PRODUCT_ARCHETYPES.length)];
                setArchetype(next);
                setSeedNonce((value) => value + 1);
              }}
            >
              random
            </button>
          </div>
          <div className="splatra-imagination-flags">
            <span>particles={particles.length}</span>
            <span>compression={frame?.object?.metadata?.turbovec?.compressed_ref?.compression_ratio?.toFixed?.(2) ?? "-"}</span>
            <span>lod={frame?.object?.metadata?.turbovec?.lod_summary?.levels?.join?.("/") ?? "-"}</span>
            <span>intensity={Number(frame?.object?.metadata?.visual_intensity ?? status?.visual_intensity ?? 0).toFixed(2)}</span>
            <span>clear radius={frame?.object?.metadata?.clear_radius ?? status?.clear_radius ?? "0.34"}</span>
            <span>{Number(frame?.object?.metadata?.visual_intensity ?? status?.visual_intensity ?? 1) < 0.42 ? "too subtle" : "visible object"}</span>
            <span>error={error ? "fallback" : "none"}</span>
          </div>
        </div>
      ) : null}
    </section>
  );
}
