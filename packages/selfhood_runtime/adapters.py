from __future__ import annotations

import re
from typing import Any

from .models import SelfhoodRuntimeInput


class AutonomyAdapter:
    def build_world_self_snapshot(self, runtime_input: SelfhoodRuntimeInput) -> dict[str, Any]:
        return {
            "adapter": "autonomy_kernel",
            "adapter_status": "local_summary",
            "world": {"input_type": runtime_input.input_type, "observed_text": bool(runtime_input.text)},
            "self": {"mode": "proof_only", "requires_user_approval": True},
        }

    def detect_deficit(self, runtime_input: SelfhoodRuntimeInput) -> dict[str, Any]:
        text = (runtime_input.text or "").lower()
        if runtime_input.input_type == "candidate_run_result" or "promotion" in text or "candidate" in text:
            signal_type = "promotion_candidate"
        elif any(token in text for token in ("private", "email", "phone", "privacy", "개인", "전화", "메일")):
            signal_type = "privacy_risk"
        elif any(token in text for token in ("congress", "deliberate", "토론", "회의", "의회")):
            signal_type = "social_congress_ready"
        elif runtime_input.input_type == "voice_transcript":
            signal_type = "voice_event"
        elif runtime_input.input_type == "morning_wake":
            signal_type = "stale_goal"
        else:
            signal_type = "knowledge_gap"
        return {
            "signal_id": f"signal_{runtime_input.input_id}",
            "signal_type": signal_type,
            "severity": 0.6,
            "source": "selfhood_runtime",
            "evidence": [{"input_id": runtime_input.input_id, "input_type": runtime_input.input_type}],
        }


class DigitalLifeAdapter:
    def convert_deficit_to_life_signal(self, signal: dict[str, Any]) -> dict[str, Any]:
        try:
            from packages.digital_life_kernel.models import LifeSignal

            return LifeSignal(
                signal_id=str(signal["signal_id"]),
                signal_type=signal["signal_type"],
                severity=float(signal.get("severity", 0.5)),
                evidence=list(signal.get("evidence", [])),
                source=str(signal.get("source", "selfhood_runtime")),
            ).to_dict()
        except Exception as exc:  # pragma: no cover - defensive adapter boundary
            return {"adapter_status": "deferred_import", "reason": str(exc), **signal}

    def propose_life_action(self, life_signal: dict[str, Any]) -> dict[str, Any]:
        try:
            from packages.digital_life_kernel.action_policy import proposal_for_signal
            from packages.digital_life_kernel.models import LifeSignal

            signal = LifeSignal(
                life_signal["signal_id"],
                life_signal["signal_type"],
                float(life_signal.get("severity", 0.5)),
                list(life_signal.get("evidence", [])),
                str(life_signal.get("source", "selfhood_runtime")),
            )
            return proposal_for_signal(signal).to_dict()
        except Exception as exc:  # pragma: no cover
            return {"adapter_status": "deferred_import", "reason": str(exc), "action_type": "request_user_approval"}


class MiroFishAdapter:
    def deliberate(self, topic: str, evidence: list[dict[str, Any]],
                   ledger_root: str | None = None) -> dict[str, Any]:
        try:
            # Prefer the REAL multi-step loop grounded in the consensus-evidence
            # ledger whenever one is reachable; the single-pass simulator remains the
            # honest fallback and says so (loop_used=false).
            root = ledger_root or self._default_ledger_root()
            if root:
                from packages.mirofish_deliberation.deliberation_loop import run_deliberation_loop

                payload = run_deliberation_loop(topic, ledger_root=root).to_dict()
                payload["loop_used"] = True
                payload["ledger_root"] = str(root)
                return payload
            from packages.mirofish_deliberation.models import DeliberationInput
            from packages.mirofish_deliberation.simulator import run_deliberation

            refs = [str(item.get("ref") or item.get("input_id") or item) for item in evidence] or ["selfhood_runtime_input"]
            result = run_deliberation(DeliberationInput(topic=topic, evidence_refs=refs))
            payload = result.to_dict()
            payload["loop_used"] = False
            return payload
        except Exception as exc:  # pragma: no cover
            return {"adapter_status": "deferred_import", "reason": str(exc), "requires_manual_approval": True}

    @staticmethod
    def _default_ledger_root() -> str | None:
        """The continuous-learning candidate store's consensus ledger, when present."""
        import os
        from pathlib import Path

        env = os.environ.get("ATANOR_CANDIDATE_STORE_PATH")
        if env:
            candidate = Path(env) / "consensus_ledger"
            if candidate.is_dir():
                return str(candidate)
        return None


class PromotionGateAdapter:
    def dry_run_candidate_review(self, candidate_summary: dict[str, Any]) -> dict[str, Any]:
        return {
            "adapter": "promotion_gate",
            "adapter_status": "summary_only",
            "dry_run_only": True,
            "actual_promotion_performed": False,
            "candidate_promotion": False,
            "requires_user_approval": True,
            "candidate_summary": dict(candidate_summary),
            "estimated_delta": {
                "concepts": int(candidate_summary.get("candidate_concepts") or candidate_summary.get("concepts") or 0),
                "relations": int(candidate_summary.get("candidate_relations") or candidate_summary.get("relations") or 0),
                "evidence": int(candidate_summary.get("candidate_evidence") or candidate_summary.get("evidence") or 0),
                "case_frames": int(candidate_summary.get("candidate_case_frames") or candidate_summary.get("case_frames") or 0),
            },
        }


class TabularisAdapter:
    _PHONE_FIELD_HINTS = ("phone", "tel", "mobile", "전화", "휴대")
    _PHONE_WITH_SEPARATORS = re.compile(r"\b(?:\+?\d{1,3}[- ]?)?(?:\d{2,4}[- ]){1,3}\d{3,4}\b")

    def privacy_check(self, payload: dict[str, Any]) -> dict[str, Any]:
        direct = []
        for key, value in payload.items():
            text = str(value)
            if re.search(r"[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}", text) and "email" not in direct:
                direct.append("email")
            key_text = str(key).lower()
            phone_hint = any(hint in key_text for hint in self._PHONE_FIELD_HINTS)
            digit_count = len(re.sub(r"\D", "", text))
            phone_like = self._PHONE_WITH_SEPARATORS.search(text) is not None
            if phone_hint and digit_count >= 7 and "phone" not in direct:
                direct.append("phone")
            elif phone_like and not text.strip().isdigit() and "phone" not in direct:
                direct.append("phone")
        return {
            "adapter": "tabularis_privacy",
            "adapter_status": "deterministic_detector",
            "private_data_present": bool(direct),
            "direct_identifier_fields": direct,
            "raw_private_data_exported": False,
            "requires_privacy_review": bool(direct),
            "safe_for_cloud_brain": not direct,
        }


class AtlasRouterAdapter:
    def route_public_fragment_dry_run(self, payload: dict[str, Any]) -> dict[str, Any]:
        wants_real = bool(payload.get("real_p2p") or payload.get("connect_peer"))
        return {
            "adapter": "atlas_router",
            "adapter_status": "dry_run_only",
            "route_allowed": not wants_real,
            "real_p2p_used": False,
            "real_cloud_upload": False,
            "blocked_reason": "real_p2p_requires_future_gate" if wants_real else None,
        }


class VoiceLoopAdapter:
    def accept_text_or_voice_transcript(self, runtime_input: SelfhoodRuntimeInput) -> dict[str, Any]:
        return {
            "adapter": "voice_loop",
            "text_input_supported": True,
            "voice_optional": True,
            "input_type": runtime_input.input_type,
            "transcript_accepted": runtime_input.input_type == "voice_transcript",
            "always_listening_enabled": False,
        }

    def produce_optional_voice_output(self, text: str, enabled: bool) -> dict[str, Any] | None:
        if not enabled:
            return None
        try:
            from packages.voice_loop.mock_tts import MockTTSAdapter

            return MockTTSAdapter().synthesize(text, "ko-KR", "calm").to_dict()
        except Exception as exc:  # pragma: no cover
            return {
                "event_id": "voice_output_deferred",
                "text": text,
                "language": "ko-KR",
                "tts_engine": "mock",
                "requires_user_review": True,
                "generated_audio_persisted": False,
                "metadata": {"adapter_status": "deferred_import", "reason": str(exc)},
            }


class LogicalSphereAdapter:
    def read_verified_candidate_rendered_summary(self) -> dict[str, Any]:
        try:
            from packages.cloud_brain.logical_sphere_summary import build_logical_sphere_summary

            return build_logical_sphere_summary().to_dict()
        except Exception as exc:  # pragma: no cover
            return {"adapter": "logical_sphere", "adapter_status": "deferred_import", "reason": str(exc)}
