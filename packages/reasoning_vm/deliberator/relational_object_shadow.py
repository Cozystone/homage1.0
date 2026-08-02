"""Default-off shadow execution for the relational-object MCQ compiler.

The observer can measure compiler coverage and proof-engine firing without
entering the live answer cascade.  It never executes an action or returns an
authoritative decision.  All compiler/engine failures are contained as bounded
shadow receipts.
"""
from __future__ import annotations

from collections import deque
from collections.abc import Callable, Mapping
from copy import deepcopy
import hashlib
import json
from typing import Any

from packages.reasoning_vm.deliberator.relational_object_compiler import (
    EXPLICIT_RELATIONAL_OBJECT_SCHEMA,
    RelationalObjectCompilation,
    compile_explicit_relational_object_mcq,
)


SHADOW_RECEIPT_SCHEMA = "atanor.deliberator.relational_object_shadow.v1"
MAX_RECEIPT_BYTES = 4_096
FactsAbout = Callable[[str], list[tuple[str, str, str]]]
ReasonerFactory = Callable[[FactsAbout], Any]


def _default_reasoner_factory(facts_about: FactsAbout) -> Any:
    from packages.reasoning_vm.deliberator.reasoner import Deliberator

    return Deliberator(
        facts_about,
        with_kernels=False,
        max_depth=5,
        budget=2_500,
    )


def _digest_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _safe_error_kind(exc: BaseException) -> str:
    name = type(exc).__name__
    return name if name.isidentifier() and len(name) <= 64 else "Exception"


def _bounded_receipt(receipt: dict[str, Any]) -> dict[str, Any]:
    encoded = json.dumps(
        receipt,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    if len(encoded) <= MAX_RECEIPT_BYTES:
        return receipt
    return {
        "schema_version": SHADOW_RECEIPT_SCHEMA,
        "mode": "shadow",
        "status": "receipt_truncated",
        "authoritative": False,
        "choice_influenced": False,
        "action_executed": False,
        "receipt_truncated": True,
        "receipt_digest": hashlib.sha256(encoded).hexdigest(),
    }


class RelationalObjectShadowObserver:
    """Observe proof firings in memory; disabled is an immediate no-access return."""

    def __init__(
        self,
        *,
        enabled: bool = False,
        max_receipts: int = 128,
        reasoner_factory: ReasonerFactory | None = None,
    ) -> None:
        if type(enabled) is not bool:
            raise TypeError("enabled must be a literal boolean")
        if isinstance(max_receipts, bool) or not isinstance(max_receipts, int):
            raise TypeError("max_receipts must be an integer")
        if max_receipts <= 0 or max_receipts > 10_000:
            raise ValueError("max_receipts must be in [1, 10000]")
        self.enabled = enabled
        self._reasoner_factory = reasoner_factory or _default_reasoner_factory
        self._receipts: deque[dict[str, Any]] = deque(maxlen=max_receipts)
        self._coverage_attempts = 0
        self._coverage_compiled = 0
        self._coverage_abstained = 0
        self._compiler_errors = 0
        self._firing_eligible = 0
        self._engine_calls = 0
        self._grounded_firings = 0
        self._multistep_firings = 0
        self._engine_abstentions = 0
        self._engine_errors = 0

    @property
    def receipts(self) -> tuple[dict[str, Any], ...]:
        return tuple(deepcopy(receipt) for receipt in self._receipts)

    @property
    def coverage_telemetry(self) -> dict[str, Any]:
        """Compiler coverage only; no correctness or capability assertion."""

        return {
            "schema_version": EXPLICIT_RELATIONAL_OBJECT_SCHEMA,
            "attempted": self._coverage_attempts,
            "compiled": self._coverage_compiled,
            "abstained": self._coverage_abstained,
            "compiler_errors": self._compiler_errors,
            "coverage_rate": (
                self._coverage_compiled / self._coverage_attempts
                if self._coverage_attempts
                else 0.0
            ),
        }

    @property
    def firing_telemetry(self) -> dict[str, Any]:
        """Proof-engine firing only; firing is not accuracy."""

        return {
            "schema_version": SHADOW_RECEIPT_SCHEMA,
            "eligible_compilations": self._firing_eligible,
            "engine_calls": self._engine_calls,
            "grounded_firings": self._grounded_firings,
            "multistep_firings": self._multistep_firings,
            "engine_abstentions": self._engine_abstentions,
            "engine_errors": self._engine_errors,
            "firing_rate": (
                self._grounded_firings / self._engine_calls
                if self._engine_calls
                else 0.0
            ),
        }

    def _record(self, receipt: dict[str, Any]) -> dict[str, Any]:
        bounded = _bounded_receipt(receipt)
        self._receipts.append(deepcopy(bounded))
        return deepcopy(bounded)

    def _base_receipt(
        self,
        *,
        status: str,
        compilation: RelationalObjectCompilation | None,
    ) -> dict[str, Any]:
        return {
            "schema_version": SHADOW_RECEIPT_SCHEMA,
            "mode": "shadow",
            "status": status,
            "authoritative": False,
            "choice_influenced": False,
            "action_executed": False,
            "compilation": compilation.to_dict() if compilation is not None else None,
            "coverage_event": {
                "compiled": compilation.compiled if compilation is not None else False,
                "reason": compilation.reason if compilation is not None else "compiler_error",
            },
            "firing_event": {
                "engine_called": False,
                "grounded": False,
                "multistep": False,
            },
        }

    def observe(
        self,
        stem: Any,
        choices: Any,
        facts_about: FactsAbout,
    ) -> dict[str, Any] | None:
        """Run a shadow compile/proof attempt, isolated from every live decision."""

        if not self.enabled:
            return None

        self._coverage_attempts += 1
        try:
            # One detached snapshot is compiled and proved.  A caller mutating a
            # custom mapping between those phases cannot change the object
            # candidates after the provenance fingerprint was computed.
            choice_snapshot = dict(choices) if isinstance(choices, Mapping) else choices
            compilation = compile_explicit_relational_object_mcq(stem, choice_snapshot)
        except Exception as exc:
            self._compiler_errors += 1
            receipt = self._base_receipt(status="compiler_error", compilation=None)
            receipt["error_kind"] = _safe_error_kind(exc)
            return self._record(receipt)

        if not compilation.compiled:
            self._coverage_abstained += 1
            return self._record(
                self._base_receipt(
                    status="compiler_abstained",
                    compilation=compilation,
                )
            )

        self._coverage_compiled += 1
        self._firing_eligible += 1
        self._engine_calls += 1
        receipt = self._base_receipt(
            status="engine_abstained",
            compilation=compilation,
        )
        receipt["firing_event"]["engine_called"] = True
        try:
            reasoner = self._reasoner_factory(facts_about)
            goal = compilation.goal
            if goal is None:  # defensive: dataclass invariant already excludes this
                raise RuntimeError("compiled receipt lost its typed goal")
            output = reasoner.answer_mcq_object(
                goal.subject,
                goal.relation,
                dict(choice_snapshot),
            )
            if not isinstance(output, Mapping):
                raise TypeError("reasoner output must be a mapping")
            choice_key = output.get("choice_key")
            hops = output.get("hops")
            trail = output.get("trail")
            grounded = (
                output.get("mode") == "grounded"
                and type(choice_key) is str
                and choice_key in choice_snapshot
                and isinstance(hops, int)
                and not isinstance(hops, bool)
                and hops >= 1
                and type(trail) is str
                and bool(trail)
            )
            if grounded:
                self._grounded_firings += 1
                multistep = hops >= 2
                if multistep:
                    self._multistep_firings += 1
                receipt["status"] = "shadow_grounded"
                receipt["firing_event"] = {
                    "engine_called": True,
                    "grounded": True,
                    "multistep": multistep,
                    "choice_key": choice_key,
                    "hops": hops,
                    "proof_digest": _digest_text(trail),
                }
            else:
                self._engine_abstentions += 1
        except Exception as exc:
            self._engine_errors += 1
            receipt["status"] = "engine_error"
            receipt["error_kind"] = _safe_error_kind(exc)

        return self._record(receipt)
