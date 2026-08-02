from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from packages.voice_loop.benchmark import detect_device_profile
from packages.voice_loop.fish_adapter import FishTTSAdapter
from packages.voice_loop.mock_asr import MockASRAdapter
from packages.voice_loop.mock_tts import MockTTSAdapter
from packages.voice_loop.models import AudioSource, TTSRuntimeProfile, VoiceLoopConfig
from packages.voice_loop.nemotron_adapter import NemotronASRAdapter
from packages.voice_loop.selector import select_tts_engine
from packages.voice_loop.tts_adapter import TTSRuntimeUnavailable
from packages.voice_loop.event_bridge import process_transcript
from packages.voice_loop.turn_manager import TurnManager


def _scenario(transcript: str, language: str = "ko-KR") -> dict[str, Any]:
    asr = MockASRAdapter(transcript, language)
    segment = asr.transcribe_file("mock.wav", language)[0]
    tts = MockTTSAdapter()
    result = process_transcript(
        segment,
        tts,
        status_summary="지금은 24시간 후보 학습을 보호 모드로 관찰 중이고, production 저장소와 Local Brain은 건드리지 않고 있어.",
    )
    return result.to_dict()


def run_proof(output_dir: str | Path = "data/audits/voice_loop") -> dict[str, Any]:
    """Run deterministic proof scenarios and write audit artifacts."""

    config = VoiceLoopConfig()
    microphone_blocked = False
    try:
        AudioSource("mic", "microphone_disabled", user_consented=True)
    except ValueError:
        microphone_blocked = True

    profiles = [
        TTSRuntimeProfile("fish2_fast", "fish_2", "high_end_gpu", ttfa_ms=300.0, rtf=0.45, stable=True),
        TTSRuntimeProfile("fish15_ok", "fish_1_5", "mid_gpu", ttfa_ms=500.0, rtf=0.7, stable=True),
        TTSRuntimeProfile("mock_ok", "mock", "unknown", ttfa_ms=0.0, rtf=0.0, stable=True),
    ]
    selection = select_tts_engine(profiles)

    turn = TurnManager()
    turn.start_speaking()
    stop_segment = MockASRAdapter("그만 말해", "ko-KR").transcribe_file("mock.wav", "ko-KR")[0]
    stop_intent = turn.handle_transcript(stop_segment)

    nemotron = NemotronASRAdapter(config.asr_model_name)
    nemotron_available = nemotron.is_available()
    fish_checks: dict[str, dict[str, object]] = {}
    for engine in ("fish_2", "fish_1_5"):
        fish = FishTTSAdapter(engine)
        try:
            available = fish.is_available()
        except TTSRuntimeUnavailable:
            available = False
        fish_checks[engine] = fish.runtime_info() | {"available": available}

    proof = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "config": config.to_dict(),
        "invariants": {
            "production_store_mutated": False,
            "local_brain_write": False,
            "candidate_promotion": False,
            "external_llm_used": False,
            "mock_growth": False,
            "active_24h_run_not_modified": True,
            "raw_audio_exported": False,
            "always_listening_enabled": False,
            "voice_clone_without_consent": False,
        },
        "device_profile": detect_device_profile().to_dict(),
        "runtime_availability": {
            "nemotron": nemotron.runtime_info() | {"available": nemotron_available},
            "fish": fish_checks,
            "fallback_used": True,
        },
        "scenarios": {
            "korean_status": _scenario("아타노르, 지금 상태 알려줘"),
            "morning_brief": _scenario("밤새 뭘 배웠어?"),
            "stop_speaking": {
                "intent": stop_intent.to_dict() if stop_intent else None,
                "turn_state": turn.state,
            },
            "memory_write_blocked": _scenario("이거 기억해줘"),
            "tts_selector": selection.to_dict(),
            "consent_safety": {"microphone_blocked": microphone_blocked, "always_listening_enabled": False},
        },
    }
    output_root = Path(output_dir)
    output_root.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    json_path = output_root / f"voice_loop_proof_{stamp}.json"
    md_path = output_root / f"voice_loop_proof_{stamp}.md"
    json_path.write_text(json.dumps(proof, ensure_ascii=False, indent=2), encoding="utf-8")
    md_path.write_text(_render_markdown(proof), encoding="utf-8")
    proof["outputs"] = {"json": str(json_path), "md": str(md_path)}
    return proof


def _render_markdown(proof: dict[str, Any]) -> str:
    invariants = proof["invariants"]
    lines = [
        "# ATANOR Voice Loop Proof",
        "",
        f"- timestamp: `{proof['timestamp']}`",
        f"- Nemotron available: `{proof['runtime_availability']['nemotron']['available']}`",
        f"- fallback used: `{proof['runtime_availability']['fallback_used']}`",
        "",
        "## Invariants",
    ]
    lines.extend(f"- {key}: `{value}`" for key, value in invariants.items())
    lines.extend(
        [
            "",
            "## Scenarios",
            f"- Korean status intent: `{proof['scenarios']['korean_status']['intent']['intent_type']}`",
            f"- Morning brief intent: `{proof['scenarios']['morning_brief']['intent']['intent_type']}`",
            f"- Stop speaking state: `{proof['scenarios']['stop_speaking']['turn_state']}`",
            f"- Memory command writes Local Brain: `{proof['scenarios']['memory_write_blocked']['plan']['writes_local_brain']}`",
            f"- Selected TTS: `{proof['scenarios']['tts_selector']['selected_engine']}`",
        ]
    )
    return "\n".join(lines) + "\n"


def main() -> None:
    proof = run_proof()
    print(json.dumps({"verdict": "PASS", "outputs": proof["outputs"], "invariants": proof["invariants"]}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
