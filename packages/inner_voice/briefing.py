from __future__ import annotations

from .models import InnerVoiceLog


def build_inner_voice_brief(log: InnerVoiceLog, *, product: bool = False) -> dict:
    if product:
        return log.redact_for_product()
    return log.export_lab_brief(limit=8)
