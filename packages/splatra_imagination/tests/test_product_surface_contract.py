from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]


def test_product_surface_keeps_orb_input_readable_and_lab_labels_out() -> None:
    status_card = (ROOT / "apps" / "web" / "app" / "AtanorUserStatusCard.tsx").read_text(encoding="utf-8")
    field = (ROOT / "apps" / "web" / "app" / "SplatraImaginationField.tsx").read_text(encoding="utf-8")

    assert 'mode="product"' in status_card
    assert 'interactive={false}' in status_card
    assert 'className="atanor-dashboard-imagination-field"' in status_card
    assert "atanor-hologram-composer" in status_card
    assert "function shouldRequestWebGrounding" in status_card
    assert "web_search: shouldRequestWebGrounding(trimmed)" in status_card
    assert "useTypewriterText" in status_card
    assert "data-stage-layout" in status_card
    assert "requestedSceneChoreography" in status_card
    assert "sceneFocus={stageLayout === \"scene_focus\"}" in status_card
    assert "scenePlan={sceneChoreography}" in status_card
    assert "sceneNarrationBeats" in status_card
    assert "layout_timeline?: Array" in status_card
    assert "activeLayoutState" in status_card
    assert "data-layout-action" in status_card
    assert "data-layout-decision-owner" in status_card
    assert "data-layout-action-basis" in status_card
    assert "data-layout-orb-anchor" in status_card
    assert "data-layout-orb-movement" in status_card
    assert "data-layout-requested-orb-movement" in status_card
    assert "data-layout-orb-identity" in status_card
    assert "data-layout-orb-feedback" in status_card
    assert "data-layout-stage-pressure" in status_card
    assert "data-layout-orb-yield-strength" in status_card
    assert "data-scene-self-owner" in status_card
    assert "data-scene-self-basis" in status_card
    assert "data-scene-self-body" in status_card
    assert "data-scene-self-particle-pressure" in status_card
    assert "data-scene-self-body-pressure" in status_card
    assert "data-scene-self-text-pressure" in status_card
    assert "data-scene-self-composer-pressure" in status_card
    assert "data-layout-pressure-adjusted-orb-movement" in status_card
    assert "data-layout-text-anchor" in status_card
    assert "data-layout-text-anchor-basis" in status_card
    assert "data-layout-text-anchor-points" in status_card
    assert "data-layout-avoidance-map-basis" in status_card
    assert "data-layout-avoidance-text-safe-lanes" in status_card
    assert "data-layout-avoidance-scene-footprint" in status_card
    assert "type TextPlacementDecision" in status_card
    assert "client_dom_scene_and_cartridge_geometry_scorer_no_topic_templates" in status_card
    assert "data-layout-text-decision-model" in status_card
    assert "data-layout-text-decision-basis" in status_card
    assert "data-layout-text-decision-score" in status_card
    assert "data-layout-text-decision-blockers" in status_card
    assert "data-layout-text-decision-speech-anchor" in status_card
    assert "data-layout-text-decision-self-anchor" in status_card
    assert "data-layout-text-decision-scene-footprint-avoided" in status_card
    assert "data-layout-text-decision-cartridge-footprint-avoided" in status_card
    assert "data-layout-text-decision-rendering" in status_card
    assert "data-layout-text-decision-particle-text" in status_card
    assert "data-layout-collision-state" in status_card
    assert "data-layout-measured-blockers" in status_card
    assert "data-layout-overlap-px" in status_card
    assert "data-layout-offscreen-px" in status_card
    assert "layoutCollisionPressureFromTelemetry" in status_card
    assert "splatraControlsForLayout" in status_card
    assert "data-layout-collision-pressure" in status_card
    assert "dashboardRuntimeLayoutVars(sceneChoreography, stageLayout, layoutTelemetry)" in status_card
    assert "client_geometry_css_var_adjustment_no_particle_text" in status_card
    assert "data-runtime-layout-adjustment" in status_card
    assert "data-layout-self-narration-anchor" in status_card
    assert "activeLayout.textAnchor" in status_card
    assert "activeLayout.selfNarrationAnchor" in status_card
    assert "data-layout-stage-region" in status_card
    assert "data-layout-autonomy" in status_card
    assert "data-particle-stage-strategy" in status_card
    assert "data-particle-space" in status_card
    assert "data-generated-visual-elements" in status_card
    assert "data-line-rendering" in status_card
    assert "data-flow-motion-reference" in status_card
    assert "data-text-exception" in status_card
    assert "data-orb-self-body-yield" in status_card
    assert "data-particle-recomposition-mode" in status_card
    assert "data-layout-text-rendering" in status_card
    assert "type SplatraScenePolicy" in status_card
    assert "defaultSplatraScenePolicy" in status_card
    assert "requestedSplatraScenePolicy" in status_card
    assert "setScenePolicy(nextScenePolicy)" in status_card
    assert "splatra_scene_policy: nextScenePolicy" in status_card
    assert "splatraStateForInnerVoice(nextSceneChoreography, nextStageLayout, layoutTelemetry, nextInitialSceneBeatIndex, nextScenePolicy)" in status_card
    assert "data-scene-content-source" in status_card
    assert "data-scene-authoring-basis" in status_card
    assert "data-visual-affordance-basis" in status_card
    assert "data-layout-decision-basis" in status_card
    assert "data-topic-scene-templates" in status_card
    assert "data-renderer-may-infer-topic" in status_card
    assert "data-particle-text" in status_card
    assert "data-scene-policy-text-rendering" in status_card
    assert "data-verified-evidence-required" in status_card
    assert "type SplatraCommandSequencePayload" in status_card
    assert "requestedSplatraCommandSequence" in status_card
    assert "setSplatraCommandSequence(nextSplatraCommandSequence)" in status_card
    assert "splatraCommandSequence={splatraCommandSequence}" in status_card
    assert "data-splatra-command-sequence" in status_card
    assert "data-splatra-command-actions" in status_card
    assert "candidate_cartridge_requests?: Array" in status_card
    assert "data-splatra-candidate-cartridges" in status_card
    assert "data-splatra-candidate-cartridge-format" in status_card
    assert "type SplatraCartridgeQueuePayload" in status_card
    assert "type SplatraInteractiveSceneAnalysisPayload" in status_card
    assert "requestedSplatraInteractiveSceneAnalysis" in status_card
    assert "sceneAnalysisObjectBlockers" in status_card
    assert "splatraInteractiveSceneAnalysis" in status_card
    assert "interactive_scene_object_count" in status_card
    assert "data-splatra-interactive-scene" in status_card
    assert "data-splatra-interactive-objects" in status_card
    assert "data-splatra-interactive-bboxes" in status_card
    assert "data-splatra-interactive-analysis-basis" in status_card
    assert "data-splatra-interactive-raw-inference" in status_card
    assert "data-layout-text-decision-interactive-bbox-avoided" in status_card
    assert "requestedSplatraCartridgeQueue" in status_card
    assert "setSplatraCartridgeQueue(nextSplatraCartridgeQueue)" in status_card
    assert "visualStateCommitted = true" in status_card
    assert "if (!visualStateCommitted)" in status_card
    assert "data-splatra-cartridge-queue" in status_card
    assert "data-splatra-cartridge-jobs" in status_card
    assert "data-splatra-cartridge-execution-mode" in status_card
    assert "data-splatra-cartridge-external-called" in status_card
    assert "data-splatra-cartridge-raw-buffer" in status_card
    assert "data-splatra-cartridge-mutation" in status_card
    assert "data-splatra-sidecar-status" in status_card
    assert "splatraCartridgeQueue={splatraCartridgeQueue}" in status_card
    assert "data-splatra-command-raw-buffers" in status_card
    assert "data-splatra-command-topic-templates" in status_card
    assert "data-splatra-command-renderer-inference" in status_card
    assert 'text_rendering: "dom_text_not_particles"' in status_card
    assert '"conversation_default"' in status_card
    assert "speech_timeline?: Array" in status_card
    assert "scenePlan?.speech_timeline" in status_card
    assert "onPlaybackStart" in status_card
    assert "startVisibleSpeech" in status_card
    assert "setSceneSpeechStartedAt(0)" in status_card
    assert "beat.speech_cue !== false" in status_card
    assert "firstSceneNarration" in status_card
    assert "sceneSpeechBeatIndex" in status_card
    assert "setSceneSpeechBeatIndex(nextSpeechBeat.beatIndex)" in status_card
    assert "data-scene-speech-beat" in status_card
    assert "activeSpeechBeatIndex={sceneSpeechBeatIndex}" in status_card
    assert "speech_cue: bool = True" in (ROOT / "packages" / "splatra_imagination" / "scene_choreography.py").read_text(encoding="utf-8")
    assert "speech_timeline: list[dict[str, Any]]" in (ROOT / "packages" / "splatra_imagination" / "scene_choreography.py").read_text(encoding="utf-8")
    assert "layout_timeline: list[dict[str, Any]]" in (ROOT / "packages" / "splatra_imagination" / "scene_choreography.py").read_text(encoding="utf-8")
    assert "_text_anchor_for_active_beat" in (ROOT / "packages" / "splatra_imagination" / "scene_choreography.py").read_text(encoding="utf-8")
    assert "_text_anchor_basis_for_active_beat" in (ROOT / "packages" / "splatra_imagination" / "scene_choreography.py").read_text(encoding="utf-8")
    assert "\"action\": \"sync_orb_text_with_particle_beat\"" in (ROOT / "packages" / "splatra_imagination" / "scene_choreography.py").read_text(encoding="utf-8")
    assert "\"text_anchor_basis\": _text_anchor_basis_for_active_beat" in (ROOT / "packages" / "splatra_imagination" / "scene_choreography.py").read_text(encoding="utf-8")
    assert "\"text_anchor_points\": len(active_layout_points)" in (ROOT / "packages" / "splatra_imagination" / "scene_choreography.py").read_text(encoding="utf-8")
    assert "\"text_source\": \"verified_beat_narration\"" in (ROOT / "packages" / "splatra_imagination" / "scene_choreography.py").read_text(encoding="utf-8")
    assert "scene_group_id: str = \"\"" in (ROOT / "packages" / "splatra_imagination" / "scene_choreography.py").read_text(encoding="utf-8")
    assert "object_track_id: str = \"\"" in (ROOT / "packages" / "splatra_imagination" / "scene_choreography.py").read_text(encoding="utf-8")
    assert "\"object_track_id\": beat.object_track_id" in (ROOT / "packages" / "splatra_imagination" / "scene_choreography.py").read_text(encoding="utf-8")
    assert "fit_verified_particle_stage_inside_uncovered_dashboard" in (ROOT / "packages" / "splatra_imagination" / "scene_choreography.py").read_text(encoding="utf-8")
    assert "atanor_self_body_not_scene_object" in (ROOT / "packages" / "splatra_imagination" / "scene_choreography.py").read_text(encoding="utf-8")
    assert "airbend_recompose_particles_inside_safe_region" in (ROOT / "packages" / "splatra_imagination" / "scene_choreography.py").read_text(encoding="utf-8")
    assert "uncovered_dashboard_field_minus_sidebar_composer_and_text" in (ROOT / "packages" / "splatra_imagination" / "scene_choreography.py").read_text(encoding="utf-8")
    assert "particle_segments_not_canvas_strokes" in (ROOT / "packages" / "splatra_imagination" / "scene_choreography.py").read_text(encoding="utf-8")
    assert "agent_airbend_recompose_verified_beats" in (ROOT / "packages" / "splatra_imagination" / "scene_choreography.py").read_text(encoding="utf-8")
    assert "orb_moves_and_scales_to_clear_verified_particle_scene" in (ROOT / "packages" / "splatra_imagination" / "scene_choreography.py").read_text(encoding="utf-8")
    assert "agent_authored_from_verified_scene_geometry_and_client_feedback" in (ROOT / "packages" / "splatra_imagination" / "scene_choreography.py").read_text(encoding="utf-8")
    assert "_client_layout_feedback_state" in (ROOT / "packages" / "splatra_imagination" / "scene_choreography.py").read_text(encoding="utf-8")
    assert "\"feedback_basis\": feedback_basis" in (ROOT / "packages" / "splatra_imagination" / "scene_choreography.py").read_text(encoding="utf-8")
    assert "\"content_used_for_scene_generation\": False" in (ROOT / "packages" / "splatra_imagination" / "scene_choreography.py").read_text(encoding="utf-8")
    assert "\"client_layout_feedback\": client_feedback" in (ROOT / "packages" / "splatra_imagination" / "scene_choreography.py").read_text(encoding="utf-8")
    assert "self_body_scene_pressure_scorer_no_topic_templates" in (ROOT / "packages" / "splatra_imagination" / "scene_choreography.py").read_text(encoding="utf-8")
    assert "scene_self_state" in (ROOT / "packages" / "splatra_imagination" / "scene_choreography.py").read_text(encoding="utf-8")
    assert "decision_candidates" in (ROOT / "packages" / "splatra_imagination" / "scene_choreography.py").read_text(encoding="utf-8")
    assert "selected_action_score" in (ROOT / "packages" / "splatra_imagination" / "scene_choreography.py").read_text(encoding="utf-8")
    assert "15.2 - load * 3.7" in (ROOT / "packages" / "splatra_imagination" / "scene_choreography.py").read_text(encoding="utf-8")
    assert "16.0 - load * 3.0" in (ROOT / "packages" / "splatra_imagination" / "scene_choreography.py").read_text(encoding="utf-8")
    assert "splatraStateForInnerVoice" in status_card
    assert "type SceneDirective" in status_card
    assert "type SceneEvidence" in status_card
    assert "sceneDirectiveForInnerVoice" in status_card
    assert "sceneEvidenceForInnerVoice" in status_card
    assert "active_scene_directive" in status_card
    assert "active_scene_narrative_function" in status_card
    assert "active_scene_directive_owner" in status_card
    assert "active_scene_directive_basis" in status_card
    assert "active_scene_text_rendering" in status_card
    assert "active_scene_particle_text" in status_card
    assert "active_scene_topic_templates" in status_card
    assert "scene_directive_source" in status_card
    assert "active_scene_evidence_owner" in status_card
    assert "active_scene_evidence_source" in status_card
    assert "active_scene_evidence_hash" in status_card
    assert "active_scene_renderer_may_infer_topic" in status_card
    assert "scene_evidence_source" in status_card
    assert '"/api/inner-voice/generate-frame"' in status_card
    assert '"/api/inner-voice/emit"' not in status_card
    assert "append_to_log: true" in status_card
    assert "splatra_state: splatraStateForInnerVoice" in status_card
    assert "nextInitialSceneBeatIndex" in status_card
    assert "splatraStateForInnerVoice(nextSceneChoreography, nextStageLayout, layoutTelemetry, nextInitialSceneBeatIndex, nextScenePolicy)" in status_card
    assert "layout_feedback" in status_card
    assert "feedback_basis: \"client_dom_scene_collision_telemetry\"" in status_card
    assert "collision_state: layoutTelemetry.collisionState" in status_card
    assert "orb_overlap_px: layoutTelemetry.orbOverlap" in status_card
    assert "text_rendering: \"dom_text_not_particles\"" in status_card
    assert "particle_text: false" in status_card
    assert "const sceneBlockers = scenePlanBlockers(sceneChoreography, dashboardBox)" in status_card
    assert "nextSpeechRect," in status_card
    assert "splatraOrbLayoutFeedback" in status_card
    assert "nextOrbLayoutFeedback" in status_card
    assert "orb_layout_feedback" in status_card
    assert "effective_orb_movement" in status_card
    assert "requested_orb_movement" in status_card
    assert "client_dom_scene_collision_telemetry" in status_card
    assert "sceneSpeechStartedAt" in status_card
    assert "data-speech-placement" in status_card
    assert "data-self-narration-placement" in status_card
    assert "selfNarrationPlacement" in status_card
    assert "selfNarrationRef" in status_card
    assert "requestedTextAnchor" in status_card
    assert "requestedLayoutIntent" in status_card
    assert "scenePlanBlockers" in status_card
    assert "sceneFootprintToDashboardRect" in status_card
    assert "stage_safe_region?.footprint" in status_card
    assert "rectsOverlap" in status_card
    assert "data-layout-decision" in status_card
    assert "requestedLayoutDecision" in status_card
    assert "requestedLayoutBasis" in status_card
    assert "DashboardLayoutMetrics" in status_card
    assert "LayoutTelemetry" in status_card
    assert "layoutTelemetryForRect" in status_card
    assert "layoutTelemetryForScene" in status_card
    assert "effectiveOrbMovementForTelemetry" in status_card
    assert "orbOverlap" in status_card
    assert "orbOffscreen" in status_card
    assert "orb_overlap_px" in status_card
    assert "orb_offscreen_px" in status_card
    assert "data-layout-orb-overlap-px" in status_card
    assert "data-layout-orb-offscreen-px" in status_card
    assert 'telemetry.collisionState === "orb_clipped"' in status_card
    assert 'telemetry.collisionState === "orb_overlap_risk"' in status_card
    assert "client_dom_collision_feedback" in status_card
    assert "offscreenAmount" in status_card
    assert "dashboardLayoutMetrics" in status_card
    assert "TEXT_LAYOUT_BASIS" in status_card
    assert "pretext_inspired_dom_text_canvas_metrics_preallocated_no_particle_text" in status_card
    assert "pretextInspiredTextLayoutSegments" in status_card
    assert "estimateDomTextLayoutPretextStyle" in status_card
    assert "estimatedTextRectFromDom" in status_card
    assert "stableLayoutMeasurementText" in status_card
    assert "dom_text_canvas_metrics_preallocated_no_particle_text" in status_card
    assert "centerStagePenalty" in status_card
    assert "speechUpperLeftTopVh" in status_card
    assert "selfNarrationMaxVw" in status_card
    assert "wideScene ? 11.5 : 16" in status_card
    assert "wideScene ? 13 : 17" in status_card
    assert "agent_layout_missing_safe_default" in status_card
    assert "agent_layout_missing:dom_text_not_particles" in status_card
    assert "decision_owner?: string" in status_card
    assert "scene_geometry_inputs?: Record<string, unknown>" in status_card
    assert "renderer_may_infer_topic?: boolean" in status_card
    assert "legacySceneChoreographyOwner" in status_card
    assert 'layoutBasis === "scene_geometry_extent"' in status_card
    assert "const planAction = typeof scenePlan?.dashboard_layout?.agent_layout_decision?.agent_action" in status_card
    assert 'stageLayout === "scene_focus" && planAction ? planAction : "keep_orb_primary"' in status_card
    assert "client_scene_geometry_fallback" not in status_card
    assert "beatCount >= 4" not in status_card
    assert "motionCount >= 1" not in status_card
    assert "spreadX >= 0.72" not in status_card
    assert "spreadY >= 0.52" not in status_card
    assert "ParticleText" not in status_card
    assert "scenePlan?: ScenePlan | null" in field
    assert "type SceneTransform" in field
    assert "sceneBeatIndex" in field
    assert "narration?: string" in field
    assert "sceneArchetype" in field
    assert "activeSceneBeatIndex" in field
    assert "activeSpeechBeatIndex?: number" in field
    assert "const syncedBeatIndex = activeSpeechBeatIndex" in field
    assert "data-active-speech-beat" in field
    assert "sceneTransform" in field
    assert "sceneCameraView" in field
    assert "sceneBeatFocusProgress" in field
    assert "start - leadIn" in field
    assert "pathCameraTarget" in field
    assert "sceneMotionPathPoint(beat, elapsedSeconds)" in field
    assert "type SceneCameraView" in field
    assert "SceneRenderObject" in field
    assert "data-safe-region-strategy" in field
    assert "data-particle-stage-strategy" in field
    assert "data-layout-autonomy" in field
    assert "data-orb-identity" in field
    assert "buildSceneRenderObjects" in field
    assert "sceneParticlesForBeat" in field
    assert "scenePoseForBeat" in field
    assert "type ScenePose" in field
    assert "poseBaseParticles" in field
    assert "sceneFigurePoseProgress" in field
    assert "basePoint.x * (1 - poseProgress)" in field
    assert "figureParticles" in field
    assert "organicStructureParticles" in field
    assert "smallObjectParticles" in field
    assert '"seated"' in field
    assert "hasFruit" in field
    assert "sceneRoleStyle" in field
    assert "sceneMotionRole" in field
    assert "semantic_role" in field
    assert "object_track_id" in field
    assert "sceneObjectTrackId" in field
    assert "sceneVisibleTrackObjects" in field
    assert "visibleCandidates" in field
    assert "const maxObjects = Math.min(18" in field
    assert "sceneWide ? 3000 : 1860" in field
    assert "data-active-scene-track" in field
    assert "verified_motion_subject" in field
    assert "verified_motion_source" in field
    assert "verified_motion_target" in field
    assert "visual_affordance" in field
    assert "particle_behavior" in field
    assert "scene_directive?: {" in field
    assert "scene_evidence?: {" in field
    assert "data-active-scene-directive" in field
    assert "data-active-scene-narrative-function" in field
    assert "data-active-scene-directive-owner" in field
    assert "data-active-scene-evidence-source" in field
    assert "data-active-scene-evidence-hash" in field
    assert "data-active-scene-evidence-owner" in field
    assert "activeSceneDirective" in field
    assert "physics_hint" in field
    assert "pose_hint?: ScenePose" in field
    assert "surface_features?: string[]" in field
    assert "physicsNumber" in field
    assert "spatial_relation" in field
    assert "scene_group_id" in field
    assert "sameSceneGroup" in field
    assert "sceneBeatModelPoints" in field
    assert "sceneGroupCameraView" in field
    assert "sceneCameraTransitionBlend" in field
    assert "previousSceneFocusObject" in field
    assert "blendedSceneCameraView" in field
    assert "previous.targetX * (1 - blend)" in field
    assert "sceneMotionFocusBoost" in field
    assert "motionFocusBoost" in field
    assert "zoomCeiling" in field
    assert "sceneRelationRank" in field
    assert "sceneActiveGroupObjects" in field
    assert "drawSceneGroupRelationField" in field
    assert "drawSceneMotionParticipantFlow" in field
    assert "drawSceneFocusSwarm" in field
    assert "sceneObjectCanvasCenter" in field
    assert "drawAmbientAirbendField" in field
    assert "sceneSurfaceFeatures" in field
    assert "PARTICLE_RENDERING_CONTRACT" in field
    assert "all_generated_marks_particle_points_no_canvas_strokes" in field
    assert "PARTICLE_FLOW_CONTRACT" in field
    assert "flow_lines_are_sparse_particle_marks_not_canvas_paths" in field
    assert "FLOW_FIELD_BASIS" in field
    assert "magnetic_simplex_inspired_airbend_particles" in field
    assert "flowFieldDisplacement" in field
    assert "data-particle-rendering-contract" in field
    assert "data-particle-flow-contract" in field
    assert "data-flow-field-basis" in field
    assert "data-particle-space" in field
    assert "data-generated-visual-elements" in field
    assert "data-line-rendering" in field
    assert "data-flow-motion-reference" in field
    assert "data-flow-motion-reference-contract" in field
    assert "data-text-exception" in field
    assert "data-orb-self-body-yield" in field
    assert "data-particle-recomposition-mode" in field
    assert "agent_scene_decisions?: Array<Record<string, unknown>>" in field
    assert "particle_operation_intents?: Array<Record<string, unknown>>" in field
    assert "data-agent-scene-decisions" in field
    assert "data-particle-operation-intents" in field
    assert "data-first-particle-operation-intent" in field
    assert "data-particle-operation-intent-source" in field
    assert "sceneParticleIntentForBeat" in field
    assert "sceneParticleIntentDensity" in field
    assert "sceneBeatParticleDensity" in field
    assert "data-active-particle-operation" in field
    assert "data-active-particle-intent-density" in field
    assert "data-scene-render-density-mode" in field
    assert "operation_intent_weighted_particles" in field
    assert "data-particle-budget" in field
    assert "derived_from_legacy_scene_beats" in field
    assert "sourceSubjectTarget" in field
    assert "small_moving_object" in field
    assert "motion_path" in field
    assert "sceneMotionPathPoint" in field
    assert "sceneMotionSourceHold" in field
    assert "start - 0.72" in field
    assert "drawSceneMotionPathFlow" in field
    assert "streamCount = Math.round(clamp((active ? 18 : 10) * density" in field
    assert "active ? 5.25 : 3.65" in field
    assert "cameraView" in field
    assert "scenePlanCentralScale" in field
    assert "centralSceneScale" in field
    assert "dashboard_layout" in field
    assert "central_scale" in field
    assert "drawSceneFocusParticles" in field
    assert "type ParticleControls" in field
    assert "layoutCollisionPressure" in field
    assert "layoutFieldQuieting" in field
    assert "layoutFlowRecombine" in field
    assert "layoutAwareCentralScale" in field
    assert "data-layout-text-avoidance" in field
    assert "data-scene-objects" in field
    assert "data-active-scene-object" in field
    assert "data-active-scene-role" in field
    assert "data-active-scene-behavior" in field
    assert "data-active-scene-focus-basis" in field
    assert "speech_timeline" in field
    assert "speech_timeline?: ScenePlanBeat[]" in field
    assert "layout_timeline?: ScenePlanBeat[]" in field
    assert "activeSpeechTimelineBeat" in field
    assert "activeLayoutTimelineBeat" in field
    assert "firstEvidenceBearingBeat" in field
    assert "firstEvidenceBearingBeat(scenePlan)" in field
    assert "scene_timer" in field
    assert "ambient_field" in field
    assert "data-active-scene-group" in field
    assert "data-active-scene-group-size" in field
    assert "data-scene-beat" in field
    assert 'mode === "lab" ? (' in field
    assert "splatra-imagination-product-label" in field
    assert "imagination /" in field
    assert "imagination ·" not in field
    assert "flowFieldAngle" in field
    assert "drawParticleStroke" in field
    assert "const keep = step === 0 || step === steps" in field
    assert "drawParticleSegment" in field
    assert "streamCount = distance > unit * 0.42 ? 5 : 3" in field
    assert "codepen_magnetic_swarm_noise_decay_reference" in field
    assert "agent_scene_commands_to_particle_cartridges" in field
    assert "data-flow-motion-reference" in field
    assert "data-splatra-command-contract" in field
    assert "type SplatraCommandSequence" in field
    assert "splatraCommandSequence?: SplatraCommandSequence | null" in field
    assert "type SplatraCartridgeQueuePayload" in field
    assert "splatraCartridgeQueue?: SplatraCartridgeQueuePayload | null" in field
    assert "splatraReadyCartridgeUrl" in field
    assert "parseSpl2Cartridge" in field
    assert "splatraCartridgeFetchUrl" in field
    assert "format\", \"spl3\"" in field
    assert "halfToFloat" in field
    assert "SPL3 cartridge truncated" in field
    assert "bbox_fit_high_density_perspective_material_${reader.format}" in field
    assert "splatraMaterialHint" in field
    assert "const densityMultiplier = realGeneratorUsed ? 20 : 10.75" in field
    assert "adaptiveRealGeneratorCap" in field
    assert "generationEngine.toLowerCase().includes(\"glass_orb\") ? 150000 : 120000" in field
    assert "clamp(Math.floor(budget * densityMultiplier), 22000, 180000)" in field
    assert "const centerX = (minX + maxX) / 2" in field
    assert "candidates.sort((left, right) => right.score - left.score)" in field
    assert "selected.size < outputCount" in field
    assert "data-splatra-cartridge-render-mode" in field
    assert "data-splatra-cartridge-loaded-particles" in field
    assert "data-splatra-cartridge-fill-ratio" in field
    assert "data-splatra-cartridge-selection-mode" in field
    assert "data-splatra-cartridge-reconstruction-path" in field
    assert "real_text_to_image_single_view_2_5d_lift" in field
    assert "procedural_particle_fallback" in field
    assert "data-splatra-cartridge-material" in field
    assert "data-splatra-cartridge-webgl" in field
    assert "data-splatra-cartridge-webgl-status" in field
    assert "data-splatra-cartridge-draggable" in field
    assert "data-splatra-cartridge-view-yaw" in field
    assert "data-splatra-cartridge-view-pitch" in field
    assert "data-splatra-cartridge-dragging" in field
    assert "data-splatra-cartridge-returning" in field
    assert "data-splatra-cartridge-return-policy" in field
    assert "release_returns_to_narration_view" in field
    assert "free_orbit_hold" in field
    assert "webgl_points_active" in field
    assert "data-splatra-cartridge-generation-engine" in field
    assert "data-splatra-cartridge-real-generator" in field
    assert "splatra_sidecar_cartridge_particles" in field
    assert "splatra_sidecar_webgl_points" in field
    assert "drawSplatraCartridgeWebGL" in field
    assert "uUserYaw" in field
    assert "uUserPitch" in field
    assert 'data-render-layer="webgl-cartridge"' in field
    assert "candidate_cartridge_requests?: Array" in field
    assert "data-splatra-candidate-cartridges" in field
    assert "data-splatra-candidate-cartridge-format" in field
    assert "commandSequenceBeats" in field
    assert "scenePlanWithCommandSequence" in field
    assert "const renderScenePlan = useMemo" in field
    assert "buildSceneRenderObjects(renderScenePlan, budget)" in field
    assert "track_id" in field
    assert "data-splatra-command-sequence" in field
    assert "data-splatra-command-side-channel" in field
    assert "data-splatra-command-agent-payload" in field
    assert "data-splatra-command-raw-buffers" in field
    assert "data-splatra-command-topic-templates" in field
    assert "data-splatra-command-renderer-inference" in field
    assert "data-splatra-command-motion-field" in field
    assert "data-splatra-command-agent-control" in field
    assert "agent_scene_decisions?: Array<Record<string, unknown>>" in status_card
    assert "particle_operation_intents?: Array<Record<string, unknown>>" in status_card
    assert "data-agent-scene-decisions" in status_card
    assert "data-particle-operation-intents" in status_card
    assert "data-first-particle-operation-intent" in status_card
    assert "data-particle-operation-intent-source" in status_card
    assert "derived_from_legacy_scene_beats" in status_card
    assert "laneOffset" in field
    assert "curl" in field
    assert "drawParticleEllipse" in field
    assert "ctx.stroke" not in field
    assert "ctx.lineTo" not in field
    assert "centers.forEach" not in field
    assert "sat|sitting|seated|rested|under" not in field
    assert "apple|fruit|berry|seed" not in field
    assert "data-renderer-content-inference" in field
    assert "explicit_scene_plan_hints_only" in field
    assert "SPLATRA Imagination Field" in field
    assert 'mode === "lab"' in field


def test_scene_focus_layout_moves_orb_without_hiding_input() -> None:
    css = (ROOT / "apps" / "web" / "app" / "globals.css").read_text(encoding="utf-8")

    assert '[data-stage-layout="scene_focus"] .hologram-voice-orb' in css
    assert '[data-layout-orb-anchor="lower_right"] .hologram-voice-orb' in css
    assert '[data-layout-action="yield_center_to_particle_scene"] .hologram-voice-orb' in css
    assert '[data-layout-action="sync_orb_text_with_particle_beat"][data-layout-orb-anchor="lower_right"] .hologram-voice-orb' in css
    assert '[data-layout-orb-movement="lower_right_lifted_compact"] .hologram-voice-orb' in css
    assert '[data-layout-orb-movement="lower_right_tucked_compact"] .hologram-voice-orb' in css
    assert '[data-layout-orb-movement="lower_right_micro_stage_guard"] .hologram-voice-orb' in css
    assert '[data-layout-orb-movement="lower_right_lifted_micro"] .hologram-voice-orb' in css
    assert '[data-stage-layout="scene_focus"] .atanor-hologram-speech' in css
    assert '[data-speech-placement="lower_left"] .atanor-hologram-speech' in css
    assert '[data-speech-placement="upper_left"] .atanor-hologram-speech' in css
    assert '[data-speech-placement="upper_right"] .atanor-hologram-speech' in css
    assert '[data-layout-collision-state="dom_text_overlap_risk"] .atanor-hologram-speech' in css
    assert '[data-layout-collision-state="dom_text_clipped"] .atanor-hologram-speech' in css
    assert '[data-layout-collision-state="dom_text_overlap_risk"] .atanor-hologram-self-narration' in css
    assert '[data-self-narration-placement="upper_left"] .atanor-hologram-self-narration' in css
    assert '[data-self-narration-placement="lower_left"] .atanor-hologram-self-narration' in css
    assert '[data-self-narration-placement="upper_right"] .atanor-hologram-self-narration' in css
    assert '[data-scene-intent="wide_particle_stage"] .hologram-voice-orb' in css
    assert '[data-layout-action="yield_center_to_particle_scene"] .atanor-dashboard-imagination-field' in css
    assert '[data-layout-action="sync_orb_text_with_particle_beat"] .atanor-dashboard-imagination-field' in css
    assert "--atanor-scene-orb-size" in css
    assert "--atanor-scene-field-opacity" in css
    assert "--atanor-scene-speech-upper-left-top" in css
    assert "--atanor-scene-speech-upper-right-top" in css
    assert "--atanor-scene-speech-lower-center-bottom" in css
    assert "--atanor-scene-self-max" in css
    assert "atanor-hologram-composer" in css
    assert "overflow-wrap: anywhere" in css
    status_card = (ROOT / "apps" / "web" / "app" / "AtanorUserStatusCard.tsx").read_text(encoding="utf-8")
    assert "chenglou_pretext_prepare_layout_pattern_dom_text_only" in status_card
    assert "data-text-layout-reference" in status_card
    assert "data-dashboard-particle-budget" in status_card
    assert "data-speech-sync-mode" in status_card
    assert "data-voice-emotion-hint" in status_card
    assert "data-voice-prosody-applied" in status_card
    assert "data-voice-local-tts-rate" in status_card
    assert "dashboardParticleBudget" in status_card
    assert "data-voice-playback-error" in status_card
    assert "data-voice-playback-unlocked" in status_card
    assert "particleBudget={dashboardParticleBudget}" in status_card
    assert "? 24000 : 9800" in status_card
    assert "microRequested" in status_card
    assert 'requestedLayoutIntent(scenePlan) === "wide_particle_stage"' in status_card
    assert "it still reserves visual space" in status_card
    assert "avoid the generated scene" in status_card
    assert "lower_right_lifted_micro" in status_card
    assert "pressureAdjustedOrbMovement" in status_card
    assert "client_stage_pressure_feedback" in status_card
    field = (ROOT / "apps" / "web" / "app" / "SplatraImaginationField.tsx").read_text(encoding="utf-8")
    assert "densityBudget = budget * (sceneWide ? 8.4 : 5.8)" in field
    assert "drawSplatraCartridgeParticles" in field
    assert "handleCartridgePointerDown" in field
    assert "handleCartridgePointerMove" in field
    assert "handleCartridgePointerUp" in field
    assert "splatraReadyCartridge(queue)" in field
    assert "sort((left, right)" in field
    assert "data-splatra-cartridge-selected-job" in field
    assert "data-splatra-cartridge-real-generator" in field
    assert "data-splatra-cartridge-webgl" in field


def test_product_archetype_cycle_excludes_central_orb_body() -> None:
    field = (ROOT / "apps" / "web" / "app" / "SplatraImaginationField.tsx").read_text(encoding="utf-8")
    product_block = field.split("const PRODUCT_ARCHETYPES", 1)[1].split("];", 1)[0]

    assert '"orb"' not in product_block
    assert '"constellation"' in product_block
    assert '"city_block"' in product_block
    assert '"circuit"' in product_block
