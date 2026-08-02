"""Default-off canonical cycle observation for the live chat boundary.

The disabled path returns before touching the request or filesystem.  The
enabled path records hashes and bounded structural metadata, never raw prompts
or answers.  It observes already-produced behavior and has no route, truth,
permission, safety, action, or promotion authority.
"""
from __future__ import annotations

import contextvars
import hashlib
import math
import os
from pathlib import Path
from typing import Any
import uuid

from packages.cognitive_core.canonical import FrozenMap
from packages.cognitive_core.cycle import (
    CanonicalEntityRef,
    CycleEvent,
    CyclePhase,
    CycleReceipt,
    CycleStatus,
    EntityKind,
    RequestCycle,
)
from packages.cognitive_core.cycle_ledger import CycleLedger


SHADOW_ENV = "ATANOR_COGNITIVE_SHADOW"
SHADOW_LEDGER_RELATIVE = Path("reports") / "cognitive-shadow" / "chat_cycles.jsonl"
_CURRENT_CYCLE_ID: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "atanor_canonical_cycle_id",
    default=None,
)


def _sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _bounded_text(value: Any, *, max_chars: int = 96) -> str:
    normalized = " ".join(str(value or "").split())
    return normalized[:max_chars]


def _safe_number(value: Any) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    number = float(value)
    return number if math.isfinite(number) else None


def _affect_snapshot() -> dict[str, Any]:
    """Read the already-live neural-emotion namespace without starting an organ."""

    try:
        from packages.neural_emotion.event_bus import EVENT_BUS

        snapshot = EVENT_BUS.engine.snapshot()
        raw = snapshot.to_dict() if hasattr(snapshot, "to_dict") else {}
        vector = raw.get("vector") if isinstance(raw, dict) else {}
        if not isinstance(vector, dict):
            vector = {}
        bounded: dict[str, float] = {}
        for key in sorted(vector)[:16]:
            number = _safe_number(vector[key])
            if number is not None:
                bounded[_bounded_text(key, max_chars=48)] = number
        return {
            "namespace": "neural_emotion",
            "state": "observed_existing_state",
            "signals": bounded,
        }
    except Exception:
        return {
            "namespace": "neural_emotion",
            "state": "unavailable",
            "signals": {},
        }


def shadow_enabled() -> bool:
    """Only an exact server-side ``1`` enables observation."""

    return os.environ.get(SHADOW_ENV, "0") == "1"


class DisabledChatCycleSpan:
    """No-op span whose methods deliberately ignore every argument."""

    enabled = False
    cycle_id = None
    fault_count = 0

    def complete(self, _response: Any) -> bool:
        return False

    def fail(self, _error: BaseException) -> bool:
        return False


_DISABLED_SPAN = DisabledChatCycleSpan()


class ChatCycleSpan:
    """One enabled, exception-contained observer span."""

    enabled = True

    def __init__(
        self,
        *,
        project_root: Path,
        question: str,
        language: str | None,
        context_turn_count: int,
    ) -> None:
        self._closed = False
        self.fault_count = 0
        self._project_root = project_root.resolve(strict=False)
        request_nonce = uuid.uuid4().hex
        self.request_id = f"request_{request_nonce}"
        self.cycle_id = f"cycle_{uuid.uuid4().hex}"
        self.parent_cycle_id = _CURRENT_CYCLE_ID.get()
        self._context_token = _CURRENT_CYCLE_ID.set(self.cycle_id)
        self._question_hash = _sha256_text(question)
        self._seed = int(hashlib.sha256(self.request_id.encode("ascii")).hexdigest()[:16], 16)
        self._initial_affect = _affect_snapshot()

        self._input_observation = CanonicalEntityRef(
            kind=EntityKind.OBSERVATION,
            cycle_id=self.cycle_id,
            ordinal=0,
            payload=FrozenMap(
                {
                    "channel": "chat",
                    "content_present": bool(question),
                    "content_sha256": self._question_hash,
                    "content_utf8_bytes": len(question.encode("utf-8")),
                    "language_requested": _bounded_text(language or "unspecified", max_chars=24),
                    "raw_content_stored": False,
                }
            ),
            legacy_ref="apps.api.dual_brain.AtanorChatRequest",
        )
        self._goal = CanonicalEntityRef(
            kind=EntityKind.GOAL,
            cycle_id=self.cycle_id,
            ordinal=1,
            payload=FrozenMap(
                {
                    "origin": "explicit_user",
                    "statement_sha256": self._question_hash,
                    "statement_stored": False,
                    "can_override_safety": False,
                }
            ),
        )
        self._episode = CanonicalEntityRef(
            kind=EntityKind.EPISODE,
            cycle_id=self.cycle_id,
            ordinal=2,
            payload=FrozenMap(
                {
                    "channel": "chat",
                    "context_turn_count": max(0, int(context_turn_count)),
                    "session_binding": "unavailable",
                }
            ),
        )
        self._request_cycle = RequestCycle(
            request_id=self.request_id,
            cycle_id=self.cycle_id,
            session_id="session_unbound",
            parent_cycle_id=self.parent_cycle_id,
            seed=self._seed,
            input_observation_id=self._input_observation.occurrence_id,
        )
        initial = FrozenMap(
            {
                "observer_projection": "m1",
                "status": "created",
            }
        )
        ingress, after_ingress = CycleEvent.transition(
            cycle_id=self.cycle_id,
            sequence=0,
            phase=CyclePhase.INGRESS,
            parent_event_id=None,
            entity_occurrence_ids=(
                self._input_observation.occurrence_id,
                self._goal.occurrence_id,
                self._episode.occurrence_id,
            ),
            state_before=initial,
            state_patch={
                "set": {
                    "affect": self._initial_affect,
                    "episode_occurrence_id": self._episode.occurrence_id,
                    "goal_occurrence_id": self._goal.occurrence_id,
                    "input_observation_occurrence_id": self._input_observation.occurrence_id,
                    "status": "running",
                },
                "delete": [],
            },
            metadata={
                "observer_only": True,
                "raw_prompt_stored": False,
            },
        )
        self._initial_state = initial
        self._ingress_event = ingress
        self._state_after_ingress = after_ingress

    def _reset_context(self) -> None:
        try:
            _CURRENT_CYCLE_ID.reset(self._context_token)
        except Exception:
            pass

    def _write_terminal(
        self,
        *,
        status: CycleStatus,
        output_hash: str | None,
        selected_route: str | None,
        terminal_entities: tuple[CanonicalEntityRef, ...],
        terminal_payload: dict[str, Any],
    ) -> bool:
        if self._closed:
            return False
        self._closed = True
        try:
            terminal, terminal_state = CycleEvent.transition(
                cycle_id=self.cycle_id,
                sequence=1,
                phase=CyclePhase.TERMINAL,
                parent_event_id=self._ingress_event.event_id,
                entity_occurrence_ids=tuple(
                    entity.occurrence_id for entity in terminal_entities
                ),
                state_before=self._state_after_ingress,
                state_patch={
                    "set": {
                        "affect_terminal": _affect_snapshot(),
                        "route": selected_route or "unavailable",
                        "status": status.value,
                        "terminal": terminal_payload,
                    },
                    "delete": [],
                },
                metadata={
                    "action_authorized": False,
                    "authoritative": False,
                    "observer_only": True,
                    "permission_mutated": False,
                    "promotion_mutated": False,
                    "truth_mutated": False,
                },
            )
            receipt = CycleReceipt(
                request_cycle=self._request_cycle,
                status=status,
                entities=(
                    self._input_observation,
                    self._goal,
                    self._episode,
                    *terminal_entities,
                ),
                events=(self._ingress_event, terminal),
                initial_state=self._initial_state,
                terminal_state_hash=terminal.state_after_hash,
                input_hash=self._question_hash,
                output_hash=output_hash,
                selected_route=selected_route,
                declared_effects=(),
                limitations=(
                    "hash_only_content_no_lossless_payload_vault",
                    "no_external_evaluator",
                    "no_session_identifier_at_ingress",
                    "observer_projection_not_shared_state_authority",
                ),
            )
            CycleLedger(self._project_root / SHADOW_LEDGER_RELATIVE).append(receipt)
            return True
        except Exception:
            self.fault_count += 1
            return False
        finally:
            self._reset_context()

    def complete(self, response: Any) -> bool:
        try:
            outer = response if isinstance(response, dict) else {}
            inner = outer.get("result") if isinstance(outer.get("result"), dict) else outer
            answer = str(inner.get("answer") or "") if isinstance(inner, dict) else ""
            output_hash = _sha256_text(answer)
            route = _bounded_text(
                inner.get("answer_kind")
                or (inner.get("reasoning_certificate") or {}).get("derivation_kind")
                or outer.get("state")
                or "unknown",
                max_chars=96,
            )
            confidence = _safe_number(inner.get("confidence")) if isinstance(inner, dict) else None
            proposition = CanonicalEntityRef(
                kind=EntityKind.PROPOSITION,
                cycle_id=self.cycle_id,
                ordinal=3,
                payload=FrozenMap(
                    {
                        "content_present": bool(answer),
                        "content_sha256": output_hash,
                        "content_utf8_bytes": len(answer.encode("utf-8")),
                        "epistemic_status": "response_output_unscored",
                        "raw_content_stored": False,
                        "route": route,
                    }
                ),
                legacy_ref="apps.api.dual_brain.chat_atanor.result",
            )
            evaluation = CanonicalEntityRef(
                kind=EntityKind.EVALUATION,
                cycle_id=self.cycle_id,
                ordinal=4,
                payload=FrozenMap(
                    {
                        "confidence_reported": confidence,
                        "external_evaluator": False,
                        "result": "not_scored",
                    }
                ),
            )
            terminal_entities: list[CanonicalEntityRef] = [proposition, evaluation]
            action_present = False
            if isinstance(inner, dict) and isinstance(inner.get("browser_action"), dict):
                action = inner["browser_action"]
                action_kind = _bounded_text(action.get("kind") or "unknown", max_chars=48)
                action_hash = hashlib.sha256(
                    repr(sorted((str(key), repr(value)) for key, value in action.items())).encode(
                        "utf-8"
                    )
                ).hexdigest()
                terminal_entities.append(
                    CanonicalEntityRef(
                        kind=EntityKind.ACTION,
                        cycle_id=self.cycle_id,
                        ordinal=5,
                        payload=FrozenMap(
                            {
                                "action_kind": action_kind,
                                "proposal_sha256": action_hash,
                                "status": "proposed_unverified",
                                "authorized_by_receipt": False,
                                "executed_by_receipt": False,
                            }
                        ),
                    )
                )
                action_present = True
            return self._write_terminal(
                status=CycleStatus.COMPLETED,
                output_hash=output_hash,
                selected_route=route,
                terminal_entities=tuple(terminal_entities),
                terminal_payload={
                    "action_proposal_observed": action_present,
                    "answer_present": bool(answer),
                    "response_state": _bounded_text(outer.get("state") or "unknown", max_chars=32),
                },
            )
        except Exception:
            self.fault_count += 1
            self._closed = True
            self._reset_context()
            return False

    def fail(self, error: BaseException) -> bool:
        try:
            error_type = type(error).__name__
            failure_hash = _sha256_text(error_type)
            failure = CanonicalEntityRef(
                kind=EntityKind.EVALUATION,
                cycle_id=self.cycle_id,
                ordinal=3,
                payload=FrozenMap(
                    {
                        "error_message_stored": False,
                        "error_type": _bounded_text(error_type, max_chars=96),
                        "external_evaluator": False,
                        "result": "pipeline_exception_observed",
                    }
                ),
            )
            return self._write_terminal(
                status=CycleStatus.FAILED,
                output_hash=failure_hash,
                selected_route=f"exception:{_bounded_text(error_type, max_chars=80)}",
                terminal_entities=(failure,),
                terminal_payload={
                    "error_message_stored": False,
                    "error_type": _bounded_text(error_type, max_chars=96),
                },
            )
        except Exception:
            # Observation must remain exception-contained even if construction
            # fails before _write_terminal() can run its cleanup.
            self.fault_count += 1
            self._closed = True
            self._reset_context()
            return False


def begin_chat_cycle_shadow(
    request: Any,
    *,
    project_root: str | os.PathLike[str] | Path,
) -> DisabledChatCycleSpan | ChatCycleSpan:
    """Begin only when the exact server-side flag is enabled.

    The first branch is intentionally before every request attribute access.
    """

    if not shadow_enabled():
        return _DISABLED_SPAN
    try:
        question_method = getattr(request, "question_text", None)
        if callable(question_method):
            question = str(question_method())
        else:
            question = str(
                getattr(request, "question", None)
                or getattr(request, "query", None)
                or getattr(request, "message", None)
                or ""
            )
        language = getattr(request, "language", None)
        context = getattr(request, "conversation_context", ())
        context_count = len(context) if isinstance(context, (list, tuple)) else 0
        return ChatCycleSpan(
            project_root=Path(project_root),
            question=question,
            language=language,
            context_turn_count=context_count,
        )
    except Exception:
        return _DISABLED_SPAN
