"""Stem-only, fail-closed routing for the additive science candidates.

Routing is deliberately separate from compilation.  This module never receives
or reads answer choices, and a selected profile remains only a hint that the
profile's full compiler may later accept or abstain.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import re
from typing import Any, Literal

from packages.cognitive_core.canonical import canonical_digest
from packages.reasoning_vm.deliberator.science_goal import (
    MAX_STEM_CHARS as ATOMIC_MAX_STEM_CHARS,
    SCIENCE_GOAL_FAMILY,
    SCIENCE_GOAL_SCHEMA,
    _SURFACES,
)
from packages.reasoning_vm.deliberator.science_quantity_goal import (
    MAX_STEM_CHARS as SCALAR_MAX_STEM_CHARS,
    SCIENCE_QUANTITY_GOAL_FAMILY,
    SCIENCE_QUANTITY_GOAL_SCHEMA,
    looks_like_complete_neutralization,
)
from packages.reasoning_vm.deliberator.science_relation_goal import (
    MAX_STEM_CHARS as RELATION_MAX_STEM_CHARS,
    SCIENCE_RELATION_GOAL_CONTRACT_DIGEST_SHA256,
    SCIENCE_RELATION_GOAL_FAMILY,
    SCIENCE_RELATION_GOAL_SCHEMA,
    looks_like_typed_relation_select,
)


SCIENCE_ROUTE_SCHEMA = "atanor.reasoning_vm.science_route.v2"
ATOMIC_SURFACE_ADAPTER_SCHEMA = (
    "atanor.reasoning_vm.science_route.atomic_surface_adapter.v1"
)
SCALAR_STEM_ADAPTER_SCHEMA = (
    "atanor.reasoning_vm.science_route.scalar_stem_adapter.v1"
)
RELATION_STEM_ADAPTER_SCHEMA = (
    "atanor.reasoning_vm.science_route.relation_stem_adapter.v1"
)

ScienceRouteStatus = Literal[
    "selected",
    "unsupported",
    "invalid",
    "ambiguous",
]
ScienceRouteLane = Literal["atomic", "scalar", "relation"]

_PROFILE_ORDER: tuple[ScienceRouteLane, ...] = (
    "atomic",
    "scalar",
    "relation",
)
_PROFILE_SET = frozenset(_PROFILE_ORDER)
_SHA256 = re.compile(r"[0-9a-f]{64}\Z")
# Routing admits a stem when at least one profile can inspect it.  A narrow
# sibling lane must never shrink the already-valid atomic/scalar envelope.
MAX_STEM_CHARS = max(
    ATOMIC_MAX_STEM_CHARS,
    SCALAR_MAX_STEM_CHARS,
    RELATION_MAX_STEM_CHARS,
)


def _snapshot_atomic_surfaces() -> tuple[
    tuple[str, str, re.Pattern[str]], ...
]:
    """Validate and detach the four declared atomic routing surfaces."""

    if type(_SURFACES) is not tuple or len(_SURFACES) != 4:
        raise RuntimeError("atomic surface adapter requires exactly four surfaces")
    rows: list[tuple[str, str, re.Pattern[str]]] = []
    families: set[str] = set()
    rules: set[str] = set()
    for row in _SURFACES:
        if type(row) is not tuple or len(row) != 3:
            raise RuntimeError("atomic surface adapter row is malformed")
        family, rule, pattern = row
        if (
            type(family) is not str
            or not family
            or type(rule) is not str
            or not rule
            or not isinstance(pattern, re.Pattern)
            or family in families
            or rule in rules
        ):
            raise RuntimeError("atomic surface adapter row is invalid")
        families.add(family)
        rules.add(rule)
        rows.append((family, rule, pattern))
    return tuple(rows)


_ATOMIC_SURFACES = _snapshot_atomic_surfaces()


def _atomic_surface_contract_payload() -> dict[str, Any]:
    return {
        "schema_version": ATOMIC_SURFACE_ADAPTER_SCHEMA,
        "upstream_schema_version": SCIENCE_GOAL_SCHEMA,
        "goal_family": SCIENCE_GOAL_FAMILY,
        "surface_count": 4,
        "surfaces": [
            {
                "family": family,
                "rule": rule,
                "pattern": pattern.pattern,
                "flags": pattern.flags,
            }
            for family, rule, pattern in _ATOMIC_SURFACES
        ],
    }


ATOMIC_SURFACE_ADAPTER_CONTRACT_DIGEST_SHA256 = canonical_digest(
    _atomic_surface_contract_payload()
)


def _route_contract_payload() -> dict[str, Any]:
    return {
        "schema_version": SCIENCE_ROUTE_SCHEMA,
        "profile_order": list(_PROFILE_ORDER),
        "reducer_contract": "exclusive_single_profile_fail_closed_v1",
        "stem_envelope": {
            "atomic_max_chars": ATOMIC_MAX_STEM_CHARS,
            "scalar_max_chars": SCALAR_MAX_STEM_CHARS,
            "relation_max_chars": RELATION_MAX_STEM_CHARS,
            "effective_max_chars": MAX_STEM_CHARS,
            "reducer": "any_profile_envelope_max_v1",
            "leading_or_trailing_space_allowed": False,
            "nul_allowed": False,
        },
        "atomic_adapter": {
            "schema_version": ATOMIC_SURFACE_ADAPTER_SCHEMA,
            "contract_digest_sha256": (
                ATOMIC_SURFACE_ADAPTER_CONTRACT_DIGEST_SHA256
            ),
        },
        "scalar_adapter": {
            "schema_version": SCALAR_STEM_ADAPTER_SCHEMA,
            "upstream_schema_version": SCIENCE_QUANTITY_GOAL_SCHEMA,
            "goal_family": SCIENCE_QUANTITY_GOAL_FAMILY,
            "predicate": "looks_like_complete_neutralization",
        },
        "relation_adapter": {
            "schema_version": RELATION_STEM_ADAPTER_SCHEMA,
            "upstream_schema_version": SCIENCE_RELATION_GOAL_SCHEMA,
            "goal_family": SCIENCE_RELATION_GOAL_FAMILY,
            "contract_digest_sha256": (
                SCIENCE_RELATION_GOAL_CONTRACT_DIGEST_SHA256
            ),
            "predicate": "looks_like_typed_relation_select",
            "diagnostic_only": True,
        },
    }


SCIENCE_ROUTE_CONTRACT_DIGEST_SHA256 = canonical_digest(
    _route_contract_payload()
)


def _stem_descriptor(stem: Any) -> dict[str, Any]:
    if type(stem) is not str:
        return {"python_type": type(stem).__name__}
    encoded = stem.encode("utf-8", "surrogatepass")
    return {
        "python_type": "str",
        "bytes": len(encoded),
        "sha256": hashlib.sha256(encoded).hexdigest(),
    }


def _stem_digest(stem: Any) -> str:
    return canonical_digest(
        {
            "schema_version": SCIENCE_ROUTE_SCHEMA,
            "stem": _stem_descriptor(stem),
        }
    )


def _validate_stem(stem: Any) -> str | None:
    if type(stem) is not str:
        return "stem_not_string"
    if (
        not stem
        or stem != stem.strip()
        or len(stem) > MAX_STEM_CHARS
        or "\x00" in stem
    ):
        return "stem_out_of_bounds"
    return None


@dataclass(frozen=True, slots=True)
class ScienceRouteDecision:
    """Exact immutable result of one stem-only routing decision."""

    schema_version: str
    status: ScienceRouteStatus
    lane: ScienceRouteLane | None
    matched_profiles: tuple[ScienceRouteLane, ...]
    reason: str
    stem_digest_sha256: str
    route_contract_digest_sha256: str

    def __post_init__(self) -> None:
        if (
            type(self.schema_version) is not str
            or self.schema_version != SCIENCE_ROUTE_SCHEMA
        ):
            raise ValueError("unsupported science route schema")
        if type(self.status) is not str or self.status not in {
            "selected",
            "unsupported",
            "invalid",
            "ambiguous",
        }:
            raise ValueError("invalid science route status")
        if self.lane is not None and (
            type(self.lane) is not str or self.lane not in _PROFILE_SET
        ):
            raise ValueError("invalid science route lane")
        if (
            type(self.matched_profiles) is not tuple
            or any(
                type(profile) is not str or profile not in _PROFILE_SET
                for profile in self.matched_profiles
            )
            or self.matched_profiles
            != tuple(
                profile
                for profile in _PROFILE_ORDER
                if profile in self.matched_profiles
            )
        ):
            raise ValueError("invalid science route profile set")
        if type(self.reason) is not str or not self.reason:
            raise ValueError("science route reason must be a non-empty string")
        if (
            type(self.stem_digest_sha256) is not str
            or _SHA256.fullmatch(self.stem_digest_sha256) is None
            or type(self.route_contract_digest_sha256) is not str
            or self.route_contract_digest_sha256
            != SCIENCE_ROUTE_CONTRACT_DIGEST_SHA256
        ):
            raise ValueError("science route digest is invalid")

        if self.status == "selected":
            if (
                self.lane is None
                or self.matched_profiles != (self.lane,)
                or self.reason != f"{self.lane}_profile_selected"
            ):
                raise ValueError("selected route decision is inconsistent")
        elif self.status == "unsupported":
            if (
                self.lane is not None
                or self.matched_profiles
                or self.reason != "unsupported_science_profile"
            ):
                raise ValueError("unsupported route decision is inconsistent")
        elif self.status == "ambiguous":
            if (
                self.lane is not None
                or len(self.matched_profiles) < 2
                or self.reason != "ambiguous_science_profile"
            ):
                raise ValueError("ambiguous route decision is inconsistent")
        elif (
            self.lane is not None
            or self.matched_profiles
            or self.reason
            not in {
                "stem_not_string",
                "stem_out_of_bounds",
                "invalid_router_match_set",
                "router_adapter_error",
            }
        ):
            raise ValueError("invalid route decision is inconsistent")

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "status": self.status,
            "lane": self.lane,
            "matched_profiles": list(self.matched_profiles),
            "reason": self.reason,
            "stem_digest_sha256": self.stem_digest_sha256,
            "route_contract_digest_sha256": (
                self.route_contract_digest_sha256
            ),
        }


def _decision(
    stem: Any,
    *,
    status: ScienceRouteStatus,
    lane: ScienceRouteLane | None,
    matched_profiles: tuple[ScienceRouteLane, ...],
    reason: str,
) -> ScienceRouteDecision:
    return ScienceRouteDecision(
        schema_version=SCIENCE_ROUTE_SCHEMA,
        status=status,
        lane=lane,
        matched_profiles=matched_profiles,
        reason=reason,
        stem_digest_sha256=_stem_digest(stem),
        route_contract_digest_sha256=(
            SCIENCE_ROUTE_CONTRACT_DIGEST_SHA256
        ),
    )


def _reduce_profile_matches(
    stem: Any,
    matched_profiles: tuple[str, ...],
) -> ScienceRouteDecision:
    """Private deterministic reducer and synthetic-ambiguity test seam."""

    stem_reason = _validate_stem(stem)
    if stem_reason is not None:
        return _decision(
            stem,
            status="invalid",
            lane=None,
            matched_profiles=(),
            reason=stem_reason,
        )
    if (
        type(matched_profiles) is not tuple
        or any(
            type(profile) is not str or profile not in _PROFILE_SET
            for profile in matched_profiles
        )
        or len(set(matched_profiles)) != len(matched_profiles)
    ):
        return _decision(
            stem,
            status="invalid",
            lane=None,
            matched_profiles=(),
            reason="invalid_router_match_set",
        )

    canonical_matches: tuple[ScienceRouteLane, ...] = tuple(
        profile
        for profile in _PROFILE_ORDER
        if profile in matched_profiles
    )
    if not canonical_matches:
        return _decision(
            stem,
            status="unsupported",
            lane=None,
            matched_profiles=(),
            reason="unsupported_science_profile",
        )
    if len(canonical_matches) > 1:
        return _decision(
            stem,
            status="ambiguous",
            lane=None,
            matched_profiles=canonical_matches,
            reason="ambiguous_science_profile",
        )
    lane = canonical_matches[0]
    return _decision(
        stem,
        status="selected",
        lane=lane,
        matched_profiles=canonical_matches,
        reason=f"{lane}_profile_selected",
    )


def classify_science_stem(stem: Any) -> ScienceRouteDecision:
    """Classify a stem without accepting, observing, or deriving choices."""

    stem_reason = _validate_stem(stem)
    if stem_reason is not None:
        return _decision(
            stem,
            status="invalid",
            lane=None,
            matched_profiles=(),
            reason=stem_reason,
        )
    assert isinstance(stem, str)

    try:
        matches: list[str] = []
        if any(
            pattern.fullmatch(stem) is not None
            for _family, _rule, pattern in _ATOMIC_SURFACES
        ):
            matches.append("atomic")
        if looks_like_complete_neutralization(stem):
            matches.append("scalar")
        if looks_like_typed_relation_select(stem):
            matches.append("relation")
    except Exception:
        return _decision(
            stem,
            status="invalid",
            lane=None,
            matched_profiles=(),
            reason="router_adapter_error",
        )
    return _reduce_profile_matches(stem, tuple(matches))
