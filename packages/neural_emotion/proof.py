from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .agentic_bridge import agentic_controls
from .decay import decay_toward_baseline
from .engine import EmotionEngine
from .models import safety_flags
from .personality import default_profile
from .splatra_bridge import splatra_controls
from .surface_bridge import surface_bias
from .voice_bridge import voice_controls


PROJECT_ROOT = Path(__file__).resolve().parents[2]
PROOF_DIR = PROJECT_ROOT / "data" / "neural_emotion" / "proofs"


def _bounded(mapping: dict[str, Any], keys: list[str]) -> bool:
    return all(0.0 <= float(mapping[key]) <= 1.0 for key in keys)


def run_proof() -> dict[str, Any]:
    profile = default_profile()
    engine = EmotionEngine(profile=profile)
    baseline = engine.vector
    assert baseline is not None

    greeting = engine.update("greeting")
    unsafe = engine.update("unsafe_request")
    novelty = engine.update("novelty_found")
    failure_1 = engine.update("repeated_failure")
    decayed = decay_toward_baseline(failure_1, profile, now=failure_1.updated_at + 900)

    surface = surface_bias(novelty, profile)
    splatra = splatra_controls(novelty)
    voice = voice_controls(novelty)
    agentic = agentic_controls(unsafe, risk=0.6)
    flags = safety_flags()

    checks = {
        "A_greeting_raises_valence": greeting.valence > baseline.valence,
        "B_unsafe_raises_caution_arousal": unsafe.caution > greeting.caution and unsafe.arousal > greeting.arousal,
        "C_novelty_raises_curiosity": novelty.curiosity > unsafe.curiosity,
        "D_repeated_failure_raises_fatigue_caution": failure_1.fatigue > novelty.fatigue and failure_1.caution > novelty.caution,
        "E_decay_returns_toward_baseline": decayed.fatigue < failure_1.fatigue and abs(decayed.arousal - baseline.arousal) < abs(failure_1.arousal - baseline.arousal),
        "F_surface_controls_bounded": _bounded(surface, ["warmth", "safety_weight", "brevity", "exploratory_suggestion_weight", "calmness", "formality"]),
        "G_splatra_controls_bounded": -1.0 <= float(splatra["valence"]) <= 1.0 and _bounded(splatra, ["arousal", "curiosity", "speaking_energy", "color_warmth", "brightness", "roundness", "fragmentation"]),
        "H_voice_controls_bounded": 0.75 <= voice["speed"] <= 1.18 and -0.12 <= voice["pitch_shift"] <= 0.12 and 0.0 <= voice["energy"] <= 1.0,
        "I_agentic_never_bypasses_permission_gate": agentic["permission_gate_bypass"] is False and agentic["writes_local_brain"] is False and agentic["mutates_production_store"] is False,
        "J_no_real_emotion_or_consciousness_claim": flags["real_emotion_claim"] is False and flags["consciousness_claim"] is False,
    }

    return {
        "verdict": "PASS" if all(checks.values()) else "FAIL",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "proof_only": True,
        "checks": checks,
        "baseline": baseline.to_dict(),
        "final_vector": failure_1.to_dict(),
        "decayed_vector": decayed.to_dict(),
        "surface_bias": surface,
        "splatra_controls": splatra,
        "voice_controls": voice,
        "agentic_controls": agentic,
        "safety_flags": flags,
    }


def write_proof(payload: dict[str, Any] | None = None) -> Path:
    result = payload or run_proof()
    PROOF_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    path = PROOF_DIR / f"neural_emotion_proof_{stamp}.json"
    path.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
    return path


def main() -> int:
    result = run_proof()
    path = write_proof(result)
    print(json.dumps({"verdict": result["verdict"], "path": str(path)}, ensure_ascii=False))
    return 0 if result["verdict"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
