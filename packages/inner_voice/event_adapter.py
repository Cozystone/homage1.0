from __future__ import annotations

from typing import Any

from .generator import InnerVoiceInput, generate_inner_voice_frame
from .models import InnerVoiceFrame
from .proof import GLOBAL_INNER_VOICE_LOG


def emit_inner_voice_from_state(**payload: Any) -> InnerVoiceFrame:
    frame = generate_inner_voice_frame(InnerVoiceInput(**payload))
    GLOBAL_INNER_VOICE_LOG.append(frame)
    return frame
