from __future__ import annotations

from dataclasses import asdict, dataclass


FULL_HOST_CONFIRMATION_PHRASE = "ENABLE FULL HOST AUTHORITY FOR ATANOR"


@dataclass(frozen=True)
class OperatorConfirmation:
    operator_id: str
    typed_phrase: str
    requested_tier: str

    @property
    def phrase_matches_full_host(self) -> bool:
        return self.typed_phrase == FULL_HOST_CONFIRMATION_PHRASE

    def to_dict(self) -> dict[str, str | bool]:
        return {**asdict(self), "phrase_matches_full_host": self.phrase_matches_full_host}


def verify_full_host_phrase(typed_phrase: str) -> bool:
    return typed_phrase == FULL_HOST_CONFIRMATION_PHRASE
