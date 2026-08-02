from __future__ import annotations

from dataclasses import dataclass, field

from .patch_manifest import make_patch_proposal
from .virtual_fs import validate_cell_path
from packages.splatra_turbovec.emotion_mapping import map_emotion_to_splatra_controls
from packages.splatra_turbovec.proof import run_city_proof, run_orb_proof
from packages.splatra_imagination import ImaginationGenerator, ImaginationSeed, run_imagination_proof
from packages.splatra_imagination.turbovec_bridge import compress_imagination_object


ALLOWED_SPLATRA_PATHS = [
    "apps/web/app/HologramVoiceOrb.tsx",
    "apps/web/app/AtanorUserStatusCard.tsx",
    "packages/splatra_turbovec",
    "docs/ATANOR_splatra_",
    "docs/ATANOR_agentic_micro_os.md",
    "data/sandbox/splatra_cell",
]


@dataclass
class SplatraCosmosCell:
    max_cycles: int = 5
    max_runtime_sec: int = 300
    max_files_changed: int = 8
    max_diff_lines: int = 600
    max_generated_particles_proof: int = 200_000
    proposals: list[object] = field(default_factory=list)

    def path_allowed(self, path: str) -> bool:
        return validate_cell_path(path, ALLOWED_SPLATRA_PATHS)

    def run_particle_compression_eval(self) -> dict[str, object]:
        return {"orb": run_orb_proof(), "city": run_city_proof()}

    def map_emotion_to_visual_controls(self, valence: float, arousal: float, audio_energy: float = 0.0) -> dict[str, float]:
        return map_emotion_to_splatra_controls(valence, arousal, audio_energy)

    def generate_imagination_frame(self, seed: ImaginationSeed) -> dict[str, object]:
        frame = ImaginationGenerator(max_particle_budget=self.max_generated_particles_proof).generate_frame(seed)
        return frame.to_dict(include_particles=True)

    def evaluate_imagination_frame(self, particle_budget: int = 900) -> dict[str, object]:
        return run_imagination_proof(particle_budget=particle_budget)

    def compress_imagination_object(self, seed: ImaginationSeed) -> dict[str, object]:
        item = ImaginationGenerator(max_particle_budget=self.max_generated_particles_proof).generate_object(seed, compress=False)
        return compress_imagination_object(item).to_dict()

    def propose_imagination_patch(self, diff_summary: str):
        proposal = make_patch_proposal(
            "splatra_imagination_patch_0",
            "splatra_cosmos_cell",
            ["apps/web/app/SplatraImaginationField.tsx", "packages/splatra_imagination"],
            diff_summary,
        )
        self.proposals.append(proposal)
        return proposal

    def propose_orb_patch(self, diff_summary: str):
        proposal = make_patch_proposal(
            "splatra_orb_patch_0",
            "splatra_cosmos_cell",
            ["apps/web/app/HologramVoiceOrb.tsx", "packages/splatra_turbovec"],
            diff_summary,
        )
        self.proposals.append(proposal)
        return proposal
