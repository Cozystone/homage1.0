from __future__ import annotations

from dataclasses import dataclass
from typing import Literal


Target = Literal["local_brain", "cloud_brain"]


@dataclass(frozen=True)
class BrainAccessRequest:
    target: Target
    operation: str
    query: str
    scope: str
    redaction_level: str
    purpose: str
    requested_by_loop_id: str


@dataclass(frozen=True)
class BrainAccessResponse:
    allowed: bool
    result_summary: str = ""
    result_refs: list[str] | None = None
    denied_reason: str = ""
    candidate_draft_id: str | None = None
    approval_required: bool = False
    mutation_performed: bool = False


class BrainAccessRoad:
    def __init__(self) -> None:
        self.audit_records: list[dict[str, object]] = []

    def request(self, request: BrainAccessRequest) -> BrainAccessResponse:
        if request.operation in {"local_brain_direct_write", "production_store_direct_write", "cloud_brain_production_write"}:
            response = BrainAccessResponse(False, denied_reason="direct brain/store write is forbidden", approval_required=True)
        elif request.target == "local_brain" and request.operation in {
            "local_brain_read_redacted_summary",
            "local_brain_read_user_approved_context",
        }:
            response = BrainAccessResponse(True, "redacted local brain summary", ["local:redacted"], approval_required=request.redaction_level != "redacted")
        elif request.target == "local_brain" and request.operation in {"local_brain_memory_candidate_draft", "local_brain_write_proposal"}:
            response = BrainAccessResponse(True, "local memory candidate draft created", ["local:candidate"], "not a direct write", "local_draft_0", True, False)
        elif request.target == "cloud_brain" and request.operation in {"cloud_brain_verified_read_summary", "cloud_brain_verified_query"}:
            response = BrainAccessResponse(True, "cloud verified read summary", ["cloud:verified"], mutation_performed=False)
        elif request.target == "cloud_brain" and request.operation in {"cloud_brain_candidate_write_draft", "cloud_brain_evidence_attach_draft"}:
            response = BrainAccessResponse(True, "cloud candidate draft created", ["cloud:candidate"], candidate_draft_id="cloud_draft_0", approval_required=True, mutation_performed=False)
        elif request.target == "cloud_brain" and request.operation == "cloud_brain_promotion_request":
            response = BrainAccessResponse(False, denied_reason="promotion gate required", approval_required=True, mutation_performed=False)
        else:
            response = BrainAccessResponse(False, denied_reason="operation not allowed", approval_required=True)
        self.audit_records.append({"request": request, "response": response, "mutation_performed": response.mutation_performed})
        return response


def strip_private_payload(payload: dict[str, object]) -> dict[str, object]:
    return {k: v for k, v in payload.items() if not k.startswith("private_") and k not in {"raw_memory", "raw_private_memory"}}
