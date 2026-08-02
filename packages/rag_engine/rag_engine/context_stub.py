from __future__ import annotations

import abc
import hashlib
from dataclasses import asdict, dataclass
from typing import Any, Iterable


class NoSequenceBackendConfigured(RuntimeError):
    """Raised when context routing is ready but no local sequence backend is loaded."""


@dataclass(frozen=True)
class ContextChunk:
    chunk_id: str
    document_id: str
    ordinal: int
    text: str
    token_count: int

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class ContextRoute:
    backend: str
    complexity: str
    chunks: list[ContextChunk]
    total_tokens: int
    max_window_tokens: int
    hardware_tier: str
    max_depth: int

    def to_dict(self) -> dict[str, Any]:
        value = asdict(self)
        value["chunks"] = [chunk.to_dict() for chunk in self.chunks]
        return value


def _tokens(text: str) -> list[str]:
    return [token for token in text.replace("\n", " ").split(" ") if token]


def _fingerprint(*parts: str) -> str:
    digest = hashlib.sha256("\0".join(parts).encode("utf-8", errors="ignore")).hexdigest()
    return digest[:24]


def _runtime_defaults(config: Any | None) -> tuple[int, int, str]:
    max_depth = int(getattr(config, "ssm_max_depth", 3) if config is not None else 3)
    max_window = int(getattr(config, "ssm_ingest_chunk_tokens", 512) if config is not None else 512)
    tier = str(getattr(config, "mode", "local_first") if config is not None else "local_first")
    try:
        from neuro_efficiency import get_runtime_config  # type: ignore

        runtime = get_runtime_config()
        max_depth = min(max_depth, int(getattr(runtime, "lazy_subgraph_depth", max_depth)))
        max_window = min(max_window, max(64, int(getattr(runtime, "utterance_max_tokens", max_window)) * 8))
        tier = str(getattr(runtime, "tier", tier))
    except Exception:
        pass
    return max(1, max_window), max(1, max_depth), tier


class SsmContextRouter(abc.ABC):
    """Abstract linear-time context router for future local sequence ingestion.

    This class does not load a neural model. It provides the deterministic
    streaming envelope that lets ATANOR replace a quadratic attention path with
    an O(N) locally authored sequence backend when such a backend is configured.
    """

    def __init__(self, *, config: Any | None = None, backend_name: str = "unconfigured_ssm") -> None:
        self.config = config
        self.backend_name = backend_name
        self.max_window_tokens, self.max_depth, self.hardware_tier = _runtime_defaults(config)

    def build_route(self, documents: Iterable[str | dict[str, Any]], *, max_window_tokens: int | None = None) -> ContextRoute:
        window = max(1, int(max_window_tokens or self.max_window_tokens))
        chunks: list[ContextChunk] = []
        for doc_index, document in enumerate(documents):
            if isinstance(document, dict):
                document_id = str(document.get("doc_id") or document.get("id") or f"doc-{doc_index}")
                text = str(document.get("text") or document.get("content") or "")
            else:
                document_id = f"doc-{doc_index}"
                text = str(document)
            tokens = _tokens(text)
            if not tokens:
                continue
            ordinal = 0
            for start in range(0, len(tokens), window):
                piece_tokens = tokens[start : start + window]
                piece = " ".join(piece_tokens)
                chunks.append(
                    ContextChunk(
                        chunk_id=f"ctx-{_fingerprint(document_id, str(ordinal), piece[:128])}",
                        document_id=document_id,
                        ordinal=ordinal,
                        text=piece,
                        token_count=len(piece_tokens),
                    )
                )
                ordinal += 1
        total_tokens = sum(chunk.token_count for chunk in chunks)
        return ContextRoute(
            backend=self.backend_name,
            complexity="O(N)",
            chunks=chunks,
            total_tokens=total_tokens,
            max_window_tokens=window,
            hardware_tier=self.hardware_tier,
            max_depth=self.max_depth,
        )

    @abc.abstractmethod
    async def infer_stream(self, route: ContextRoute) -> dict[str, Any]:
        """Run the configured sequence backend over a prepared route."""


class ConfiguredSsmContextRouter(SsmContextRouter):
    """Runtime adapter around a caller-supplied async sequence function."""

    def __init__(self, sequence_backend: Any, *, config: Any | None = None, backend_name: str = "configured_ssm") -> None:
        super().__init__(config=config, backend_name=backend_name)
        self.sequence_backend = sequence_backend

    async def infer_stream(self, route: ContextRoute) -> dict[str, Any]:
        result = self.sequence_backend(route)
        if hasattr(result, "__await__"):
            result = await result
        if not isinstance(result, dict):
            raise TypeError("SSM sequence backend must return a dict")
        return {
            "state": "completed",
            "backend": self.backend_name,
            "route": route.to_dict(),
            "result": result,
        }


class UnconfiguredSsmContextRouter(SsmContextRouter):
    async def infer_stream(self, route: ContextRoute) -> dict[str, Any]:
        raise NoSequenceBackendConfigured(
            f"{self.backend_name} is not configured; route prepared {len(route.chunks)} chunks without loading a model"
        )
