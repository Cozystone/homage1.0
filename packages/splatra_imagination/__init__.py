"""Procedural SPLATRA imagination field, separate from verified knowledge."""

from .cartridge_queue import SplatraCandidateCartridgeJob, SplatraCandidateCartridgeQueue, build_candidate_cartridge_queue
from .command_adapter import SplatraCommandPlan, SplatraSceneCommandSequence, compile_scene_choreography_commands, compile_splatra_command
from .generator import ImaginationGenerator, deterministic_seed, select_archetype
from .models import ARCHETYPES, ImaginationFrame, ImaginationObject, ImaginationSeed, default_safety_flags
from .proof import run_imagination_proof
from .scene_analysis import BoundingBox3D, InteractiveSceneAnalysis, InteractiveSceneObject, analyze_scene_choreography
from .scene_choreography import SceneBeat, SceneChoreographyPlan, compile_scene_choreography
from .sidecar import SplatraSidecarDispatchResult, SplatraSidecarJobResult, configured_sidecar_url, dispatch_candidate_queue_to_sidecar

__all__ = [
    "ARCHETYPES",
    "ImaginationFrame",
    "ImaginationGenerator",
    "ImaginationObject",
    "ImaginationSeed",
    "BoundingBox3D",
    "InteractiveSceneAnalysis",
    "InteractiveSceneObject",
    "SceneBeat",
    "SceneChoreographyPlan",
    "SplatraCandidateCartridgeJob",
    "SplatraCandidateCartridgeQueue",
    "SplatraCommandPlan",
    "SplatraSceneCommandSequence",
    "SplatraSidecarDispatchResult",
    "SplatraSidecarJobResult",
    "build_candidate_cartridge_queue",
    "analyze_scene_choreography",
    "compile_scene_choreography",
    "compile_scene_choreography_commands",
    "compile_splatra_command",
    "configured_sidecar_url",
    "default_safety_flags",
    "deterministic_seed",
    "dispatch_candidate_queue_to_sidecar",
    "run_imagination_proof",
    "select_archetype",
]
