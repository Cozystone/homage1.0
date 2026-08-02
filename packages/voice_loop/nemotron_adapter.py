from __future__ import annotations

from typing import Iterable

from packages.voice_loop.asr_adapter import ASRAdapter, ModelRuntimeUnavailable
from packages.voice_loop.models import TranscriptSegment


class NemotronASRAdapter(ASRAdapter):
    """Lazy local adapter for NVIDIA Nemotron ASR.

    This proof adapter never downloads weights, never opens a microphone, and
    does not call external inference services. If NeMo or the model runtime is
    unavailable, callers should fall back to deterministic mock ASR.
    """

    def __init__(self, model_name: str = "nvidia/nemotron-3.5-asr-streaming-0.6b") -> None:
        self.model_name = model_name
        self._model: object | None = None
        self._unavailable_reason: str | None = None

    def load(self) -> None:
        try:
            import nemo.collections.asr as nemo_asr  # type: ignore[import-not-found]
        except Exception as exc:  # pragma: no cover - depends on optional runtime
            self._unavailable_reason = f"NeMo ASR runtime unavailable: {exc}"
            raise ModelRuntimeUnavailable(self._unavailable_reason) from exc
        try:
            self._model = nemo_asr.models.ASRModel.from_pretrained(model_name=self.model_name)
        except Exception as exc:  # pragma: no cover - depends on optional model/cache
            self._unavailable_reason = f"Nemotron model unavailable locally: {exc}"
            raise ModelRuntimeUnavailable(self._unavailable_reason) from exc

    def is_available(self) -> bool:
        if self._model is not None:
            return True
        try:
            self.load()
        except ModelRuntimeUnavailable:
            return False
        return True

    def runtime_info(self) -> dict[str, object]:
        return {
            "adapter": "nemotron_asr",
            "model_name": self.model_name,
            "available": self._model is not None,
            "unavailable_reason": self._unavailable_reason,
            "microphone_enabled": False,
            "external_service": False,
        }

    def transcribe_file(self, path: str, target_lang: str) -> list[TranscriptSegment]:
        if self._model is None:
            self.load()
        model = self._model
        if model is None:
            raise ModelRuntimeUnavailable("Nemotron ASR model is not loaded")
        try:
            result = model.transcribe([path])  # type: ignore[attr-defined]
        except Exception as exc:  # pragma: no cover - optional runtime behavior
            raise ModelRuntimeUnavailable(f"Nemotron transcription failed: {exc}") from exc
        text = str(result[0] if isinstance(result, list) and result else result)
        return [
            TranscriptSegment(
                segment_id="nemotron_file_0",
                source_id=path,
                text=text,
                language=target_lang,
                confidence=None,
                final=True,
                metadata={"adapter": "nemotron_asr", "transcript_persisted": False},
            )
        ]

    def transcribe_stream(self, chunks: Iterable[bytes], target_lang: str) -> list[TranscriptSegment]:
        raise ModelRuntimeUnavailable("Nemotron streaming is scaffolded only in proof mode")
