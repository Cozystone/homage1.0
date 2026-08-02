from __future__ import annotations

import asyncio
import base64
import hashlib
import hmac
import json
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import asdict, dataclass, field
from typing import Any, Protocol

from app.services.network_config import NetworkConfig


DEFAULT_TIMEOUT_SECONDS = 2.5
DEFAULT_MAX_FRAGMENT_BYTES = 2_000_000
DEFAULT_MAX_NODES = 2_048
DEFAULT_MAX_EDGES = 8_192


def _utc_seconds() -> int:
    return int(time.time())


def canonical_json_bytes(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def query_vector_footprint(query_vector: list[float] | tuple[float, ...], *, buckets: int = 16) -> str:
    if not query_vector:
        return sha256_hex(b"empty-vector")
    clipped = [max(-1.0, min(1.0, float(value))) for value in query_vector[:512]]
    quantized = [int(round(value * buckets)) for value in clipped]
    return sha256_hex(canonical_json_bytes({"dims": len(clipped), "q": quantized}))


def query_text_footprint(query: str) -> str:
    tokens = [token for token in query.lower().replace("_", " ").split() if token]
    return sha256_hex(canonical_json_bytes({"kind": "query-text", "tokens": tokens[:16], "length": len(query)}))


@dataclass(frozen=True)
class QueryIntent:
    """Metadata-safe query signal.

    The raw user query is converted into coarse footprints before it reaches
    any server-side signaling provider.
    """

    text_footprint: str
    vector_footprint: str
    query_vector: list[float]
    created_at: int = field(default_factory=_utc_seconds)

    @classmethod
    def from_query(cls, query: str) -> "QueryIntent":
        query_vector = query_to_vector(query)
        return cls(
            text_footprint=query_text_footprint(query),
            vector_footprint=query_vector_footprint(query_vector),
            query_vector=query_vector,
        )

    @classmethod
    def from_vector(cls, query_vector: list[float]) -> "QueryIntent":
        vector_footprint = query_vector_footprint(query_vector)
        return cls(
            text_footprint=sha256_hex(canonical_json_bytes({"kind": "vector-only", "vector": vector_footprint})),
            vector_footprint=vector_footprint,
            query_vector=list(query_vector),
        )


@dataclass(frozen=True)
class PeerHint:
    peer_id: str
    concept_id: str
    endpoint: str | None = None
    score: float = 0.0
    transport: str = "p2p"
    expires_at: int | None = None
    vector_footprint: str | None = None
    source: str = "unknown"

    @classmethod
    def from_mapping(cls, value: dict[str, Any]) -> "PeerHint":
        concept_id = value.get("concept_id")
        if concept_id is None and isinstance(value.get("concept_ids"), list) and value["concept_ids"]:
            concept_id = value["concept_ids"][0]
        return cls(
            peer_id=str(value.get("peer_id") or ""),
            concept_id=str(concept_id or ""),
            endpoint=str(value["endpoint"]) if value.get("endpoint") else None,
            score=float(value.get("score") or value.get("confidence") or 0.0),
            transport=str(value.get("transport") or "p2p"),
            expires_at=int(value["expires_at"]) if value.get("expires_at") else None,
            vector_footprint=str(value["vector_footprint"]) if value.get("vector_footprint") else None,
            source=str(value.get("source") or "unknown"),
        )

    def is_fresh(self) -> bool:
        return self.expires_at is None or self.expires_at > _utc_seconds()


@dataclass
class GraphFragmentEnvelope:
    fragment_id: str
    source_peer_id: str
    concept_ids: list[str]
    nodes: list[dict[str, Any]]
    edges: list[dict[str, Any]]
    payload_sha256: str
    schema_version: str = "homage.graph-fragment.v1"
    created_at: int = field(default_factory=_utc_seconds)
    expires_at: int | None = None
    signature: str | None = None
    compression: str = "none"

    @property
    def payload(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "fragment_id": self.fragment_id,
            "source_peer_id": self.source_peer_id,
            "concept_ids": self.concept_ids,
            "nodes": self.nodes,
            "edges": self.edges,
            "created_at": self.created_at,
            "expires_at": self.expires_at,
            "compression": self.compression,
        }

    @classmethod
    def create(
        cls,
        *,
        fragment_id: str,
        source_peer_id: str,
        concept_ids: list[str],
        nodes: list[dict[str, Any]],
        edges: list[dict[str, Any]],
        signing_key: str | None = None,
        expires_at: int | None = None,
    ) -> "GraphFragmentEnvelope":
        draft = cls(
            fragment_id=fragment_id,
            source_peer_id=source_peer_id,
            concept_ids=concept_ids,
            nodes=nodes,
            edges=edges,
            payload_sha256="",
            expires_at=expires_at,
        )
        payload = canonical_json_bytes(draft.payload)
        digest = sha256_hex(payload)
        signature = sign_payload(digest, signing_key) if signing_key else None
        draft.payload_sha256 = digest
        draft.signature = signature
        return draft

    @classmethod
    def from_mapping(cls, value: dict[str, Any]) -> "GraphFragmentEnvelope":
        return cls(
            fragment_id=str(value.get("fragment_id") or ""),
            source_peer_id=str(value.get("source_peer_id") or value.get("peer_id") or ""),
            concept_ids=[str(item) for item in value.get("concept_ids") or []],
            nodes=list(value.get("nodes") or []),
            edges=list(value.get("edges") or []),
            payload_sha256=str(value.get("payload_sha256") or ""),
            schema_version=str(value.get("schema_version") or "homage.graph-fragment.v1"),
            created_at=int(value.get("created_at") or _utc_seconds()),
            expires_at=int(value["expires_at"]) if value.get("expires_at") else None,
            signature=str(value["signature"]) if value.get("signature") else None,
            compression=str(value.get("compression") or "none"),
        )

    def validate(
        self,
        *,
        signing_key: str | None = None,
        max_bytes: int = DEFAULT_MAX_FRAGMENT_BYTES,
        max_nodes: int = DEFAULT_MAX_NODES,
        max_edges: int = DEFAULT_MAX_EDGES,
    ) -> None:
        if self.schema_version != "homage.graph-fragment.v1":
            raise ValueError(f"unsupported fragment schema: {self.schema_version}")
        if not self.fragment_id or not self.source_peer_id:
            raise ValueError("fragment_id and source_peer_id are required")
        if self.expires_at is not None and self.expires_at <= _utc_seconds():
            raise ValueError("fragment has expired")
        if self.compression != "none":
            raise ValueError(f"unsupported compression: {self.compression}")
        if len(self.nodes) > max_nodes:
            raise ValueError(f"fragment nodes exceed limit: {len(self.nodes)} > {max_nodes}")
        if len(self.edges) > max_edges:
            raise ValueError(f"fragment edges exceed limit: {len(self.edges)} > {max_edges}")
        payload = canonical_json_bytes(self.payload)
        if len(payload) > max_bytes:
            raise ValueError(f"fragment bytes exceed limit: {len(payload)} > {max_bytes}")
        actual = sha256_hex(payload)
        if not hmac.compare_digest(actual, self.payload_sha256):
            raise ValueError("invalid fragment payload_sha256")
        if signing_key:
            expected = sign_payload(self.payload_sha256, signing_key)
            if not self.signature or not hmac.compare_digest(expected, self.signature):
                raise ValueError("invalid fragment signature")

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def sign_payload(payload_sha256: str, signing_key: str | None) -> str:
    if not signing_key:
        raise ValueError("signing_key is required")
    digest = hmac.new(signing_key.encode("utf-8"), payload_sha256.encode("ascii"), hashlib.sha256).digest()
    return base64.urlsafe_b64encode(digest).decode("ascii").rstrip("=")


class SignalingProvider(Protocol):
    name: str

    async def discover_peers(self, intent: QueryIntent) -> list[PeerHint]:
        ...


class SignalIndex(Protocol):
    async def broadcast_query_intent(self, query_vector: list[float]) -> list[PeerHint]:
        ...


class SupabaseSignalIndex:
    """Metadata-only peer discovery over Supabase.

    The raw query and heavy ontology payload never go to Supabase. Only a
    coarse vector footprint is sent so the central service acts as a lightweight
    signaling/index server.
    """

    name = "supabase_metadata_signal"

    def __init__(
        self,
        *,
        config: NetworkConfig | None = None,
        url: str | None = None,
        key: str | None = None,
        table: str | None = None,
    ) -> None:
        self.config = config or NetworkConfig.from_env()
        self.url = url or self.config.supabase_url
        self.key = key or self.config.supabase_key
        self.table = table or self.config.supabase_peer_table
        self._client: Any | None = None

    @property
    def configured(self) -> bool:
        return bool(self.url and self.key)

    def _client_or_none(self) -> Any | None:
        if self._client is not None:
            return self._client
        if not self.configured:
            return None
        try:
            from supabase import create_client  # type: ignore

            self._client = create_client(str(self.url), str(self.key))
            return self._client
        except Exception:
            return None

    async def discover_peers(self, intent: QueryIntent) -> list[PeerHint]:
        client = self._client_or_none()
        if client is None:
            return []

        def _query() -> list[dict[str, Any]]:
            response = (
                client.table(self.table)
                .select("peer_id,concept_id,endpoint,score,transport,expires_at,vector_footprint")
                .eq("vector_footprint", intent.vector_footprint)
                .order("score", desc=True)
                .limit(8)
                .execute()
            )
            return list(getattr(response, "data", None) or [])

        rows = await asyncio.to_thread(_query)
        hints = []
        for row in rows:
            row["source"] = self.name
            hint = PeerHint.from_mapping(row)
            if hint.peer_id and hint.concept_id and hint.is_fresh():
                hints.append(hint)
        return hints

    async def broadcast_query_intent(self, query_vector: list[float]) -> list[PeerHint]:
        return await self.discover_peers(QueryIntent.from_vector(query_vector))


class LocalPeerDirectorySignal:
    """Local peer discovery that keeps edge payloads independent from servers."""

    name = "local_peer_directory"

    def __init__(self, config: NetworkConfig | None = None) -> None:
        self.config = config or NetworkConfig.from_env()

    async def discover_peers(self, intent: QueryIntent) -> list[PeerHint]:
        path = self.config.peer_directory_path
        if not path.exists():
            return []

        def _read() -> Any:
            return json.loads(path.read_text(encoding="utf-8"))

        try:
            payload = await asyncio.to_thread(_read)
        except (OSError, json.JSONDecodeError):
            return []
        rows = payload.get("peers", payload) if isinstance(payload, dict) else payload
        if not isinstance(rows, list):
            return []

        hints: list[PeerHint] = []
        for row in rows:
            if not isinstance(row, dict):
                continue
            row = {**row, "source": self.name}
            hint = PeerHint.from_mapping(row)
            if not hint.peer_id or not hint.concept_id or not hint.is_fresh():
                continue
            if hint.vector_footprint and hint.vector_footprint != intent.vector_footprint:
                continue
            hints.append(hint)
        return sorted(hints, key=lambda hint: hint.score, reverse=True)[:16]


class StaticSignalIndex:
    name = "static_signal"

    def __init__(self, hints: list[PeerHint] | None = None) -> None:
        self.hints = hints or []

    async def discover_peers(self, intent: QueryIntent) -> list[PeerHint]:
        return [hint for hint in self.hints if hint.is_fresh() and (not hint.vector_footprint or hint.vector_footprint == intent.vector_footprint)]

    async def broadcast_query_intent(self, query_vector: list[float]) -> list[PeerHint]:
        return await self.discover_peers(QueryIntent.from_vector(query_vector))


class PayloadTransport(Protocol):
    name: str

    def can_handle(self, hint: PeerHint) -> bool:
        ...

    async def fetch_fragment(self, hint: PeerHint) -> GraphFragmentEnvelope:
        ...


class P2PTransport(Protocol):
    async def fetch_p2p_subgraph(self, peer_id: str, concept_id: str) -> GraphFragmentEnvelope:
        ...


class Libp2pTransport:
    """P2P-ready payload transport facade.

    The Python libp2p package is optional and not stable enough to make the
    process depend on it at import time. A future Tauri/Rust sidecar can
    implement the same PayloadTransport contract without changing the resolver.
    """

    name = "p2p_payload"

    def __init__(self, config: NetworkConfig | None = None) -> None:
        self.config = config or NetworkConfig.from_env()

    def can_handle(self, hint: PeerHint) -> bool:
        return self.config.enable_p2p_payload and hint.transport in {"p2p", "libp2p", "edge", "webrtc"}

    async def fetch_fragment(self, hint: PeerHint) -> GraphFragmentEnvelope:
        return await self.fetch_p2p_subgraph(hint.peer_id, hint.concept_id)

    async def fetch_p2p_subgraph(self, peer_id: str, concept_id: str) -> GraphFragmentEnvelope:
        try:
            import libp2p  # type: ignore  # noqa: F401
        except Exception as exc:
            raise ConnectionError("python libp2p transport is unavailable") from exc
        raise NotImplementedError("libp2p dial/request protocol is not configured for this peer")


class HttpFallbackTransport:
    """Signed graph-fragment payload transport over peer/server HTTP endpoints."""

    name = "http_fragment_payload"

    def __init__(
        self,
        *,
        config: NetworkConfig | None = None,
        timeout_seconds: float | None = None,
        signing_key: str | None = None,
    ) -> None:
        self.config = config or NetworkConfig.from_env()
        self.timeout_seconds = timeout_seconds if timeout_seconds is not None else self.config.timeout_seconds
        self.signing_key = signing_key if signing_key is not None else self.config.signing_key

    def can_handle(self, hint: PeerHint) -> bool:
        if not self.config.enable_http_payload_fallback or not hint.endpoint:
            return False
        if hint.transport == "server" and not self.config.fallback_to_server_payload:
            return False
        return True

    async def fetch_fragment(self, hint: PeerHint) -> GraphFragmentEnvelope:
        return await self.fetch_from_endpoint(str(hint.endpoint), hint.peer_id, hint.concept_id)

    async def fetch_from_endpoint(self, endpoint: str, peer_id: str, concept_id: str) -> GraphFragmentEnvelope:
        url = self._build_url(endpoint, peer_id, concept_id)

        def _fetch() -> dict[str, Any]:
            request = urllib.request.Request(url, headers={"Accept": "application/json", "User-Agent": "ATANOR/0.1"})
            with urllib.request.urlopen(request, timeout=self.timeout_seconds) as response:
                data = response.read(self.config.max_fragment_bytes + 1)
            if len(data) > self.config.max_fragment_bytes:
                raise ValueError("fallback fragment response exceeded byte limit")
            return json.loads(data.decode("utf-8"))

        try:
            payload = await asyncio.wait_for(asyncio.to_thread(_fetch), timeout=self.timeout_seconds + 0.5)
        except (asyncio.TimeoutError, urllib.error.URLError, OSError, json.JSONDecodeError) as exc:
            raise ConnectionError(f"http fallback failed for peer {peer_id}") from exc
        envelope = GraphFragmentEnvelope.from_mapping(payload)
        envelope.validate(
            signing_key=self.signing_key,
            max_bytes=self.config.max_fragment_bytes,
            max_nodes=self.config.max_nodes,
            max_edges=self.config.max_edges,
        )
        return envelope

    @staticmethod
    def _build_url(endpoint: str, peer_id: str, concept_id: str) -> str:
        base = endpoint.rstrip("/")
        query = urllib.parse.urlencode({"peer_id": peer_id, "concept_id": concept_id})
        return f"{base}/api/cloud-brain/fragment?{query}"


class LegacyP2PPayloadTransport:
    name = "legacy_p2p_payload"

    def __init__(self, transport: P2PTransport) -> None:
        self.transport = transport

    def can_handle(self, hint: PeerHint) -> bool:
        return hint.transport in {"p2p", "libp2p", "edge", "webrtc"}

    async def fetch_fragment(self, hint: PeerHint) -> GraphFragmentEnvelope:
        return await self.transport.fetch_p2p_subgraph(hint.peer_id, hint.concept_id)


class HybridNetworkManager:
    def __init__(
        self,
        *,
        config: NetworkConfig | None = None,
        signal_index: SignalIndex | SignalingProvider | None = None,
        signal_providers: list[SignalingProvider] | None = None,
        p2p_transport: P2PTransport | None = None,
        payload_transports: list[PayloadTransport] | None = None,
        fallback_transport: HttpFallbackTransport | None = None,
        signing_key: str | None = None,
        timeout_seconds: float | None = None,
    ) -> None:
        base_config = config or NetworkConfig.from_env()
        if signing_key is not None or timeout_seconds is not None:
            base_config = NetworkConfig(
                **{
                    **base_config.__dict__,
                    "signing_key": signing_key if signing_key is not None else base_config.signing_key,
                    "timeout_seconds": timeout_seconds if timeout_seconds is not None else base_config.timeout_seconds,
                }
            )
        self.config = base_config
        self.signing_key = self.config.signing_key
        self.timeout_seconds = self.config.timeout_seconds

        providers: list[SignalingProvider] = []
        if signal_providers is not None:
            providers.extend(signal_providers)
        elif signal_index is not None:
            providers.append(signal_index)  # type: ignore[arg-type]
        else:
            if self.config.enable_local_peer_directory:
                providers.append(LocalPeerDirectorySignal(self.config))
            if self.config.enable_server_signaling:
                providers.append(SupabaseSignalIndex(config=self.config))
        self.signal_providers = providers

        transports: list[PayloadTransport] = []
        if payload_transports is not None:
            transports.extend(payload_transports)
        else:
            if p2p_transport is not None:
                transports.append(LegacyP2PPayloadTransport(p2p_transport))
            elif self.config.enable_p2p_payload:
                transports.append(Libp2pTransport(self.config))
            if fallback_transport is not None:
                transports.append(fallback_transport)
            elif self.config.enable_http_payload_fallback:
                transports.append(HttpFallbackTransport(config=self.config))
        self.payload_transports = transports

    async def broadcast_query_intent(self, query_vector: list[float]) -> list[PeerHint]:
        hints, _failures = await self.discover_peer_hints(QueryIntent.from_vector(query_vector))
        return hints

    async def discover_peer_hints(self, intent: QueryIntent) -> tuple[list[PeerHint], list[dict[str, str]]]:
        failures: list[dict[str, str]] = []
        discovered: list[PeerHint] = []
        for provider in self.signal_providers:
            provider_name = getattr(provider, "name", provider.__class__.__name__)
            try:
                hints = await provider.discover_peers(intent)  # type: ignore[attr-defined]
            except AttributeError:
                hints = await provider.broadcast_query_intent(intent.query_vector)  # type: ignore[attr-defined]
            except Exception as exc:
                failures.append({"provider": provider_name, "error": str(exc)})
                continue
            for hint in hints:
                if hint.peer_id and hint.concept_id and hint.is_fresh():
                    discovered.append(hint)
        return self._dedupe_hints(discovered), failures

    async def fetch_p2p_subgraph(self, peer_id: str, concept_id: str) -> GraphFragmentEnvelope:
        hint = PeerHint(peer_id=peer_id, concept_id=concept_id, transport="p2p")
        for transport in self.payload_transports:
            if transport.name.startswith("http") or not transport.can_handle(hint):
                continue
            envelope = await asyncio.wait_for(transport.fetch_fragment(hint), timeout=self.timeout_seconds)
            self._validate_envelope(envelope)
            return envelope
        raise ConnectionError("no p2p payload transport is configured")

    async def resolve_cloud_knowledge(self, query: str) -> dict[str, Any]:
        intent = QueryIntent.from_query(query)
        hints, signaling_failures = await self.discover_peer_hints(intent)
        attempts: list[dict[str, Any]] = []
        fragments: list[dict[str, Any]] = []

        for hint in hints[:8]:
            attempt = {
                "peer_id": hint.peer_id,
                "concept_id": hint.concept_id,
                "hint_transport": hint.transport,
                "hint_source": hint.source,
                "state": "pending",
                "transport_attempts": [],
            }
            for transport in self._ordered_transports(hint):
                transport_attempt = {"transport": transport.name, "state": "pending"}
                try:
                    envelope = await asyncio.wait_for(transport.fetch_fragment(hint), timeout=self.timeout_seconds + 0.75)
                    self._validate_resolved_envelope(envelope, hint)
                    consistency_report = await self._verify_ontological_consistency(envelope)
                    transport_attempt["state"] = "completed"
                    if consistency_report is not None:
                        transport_attempt["consistency"] = consistency_report
                    attempt["state"] = f"{transport.name}_completed"
                    fragments.append(envelope.to_dict())
                    attempt["transport_attempts"].append(transport_attempt)
                    break
                except Exception as exc:
                    transport_attempt["state"] = "failed"
                    transport_attempt["error"] = str(exc)
                    attempt["transport_attempts"].append(transport_attempt)
            else:
                attempt["state"] = "failed"
            attempts.append(attempt)

        return {
            "state": "completed" if fragments else "degraded",
            "query_footprint": intent.text_footprint,
            "vector_footprint": intent.vector_footprint,
            "network_mode": self.config.mode,
            "standalone_localhost_ready": self.config.standalone_localhost_ready,
            "server_dependency": False,
            "metadata_only_signal": True,
            "hint_count": len(hints),
            "fragment_count": len(fragments),
            "fragments": fragments,
            "attempts": attempts,
            "signaling": {
                "providers": [getattr(provider, "name", provider.__class__.__name__) for provider in self.signal_providers],
                "failures": signaling_failures,
                "server_signaling_enabled": self.config.enable_server_signaling,
            },
            "payload": {
                "transports": [transport.name for transport in self.payload_transports],
                "fallback_policy": "try_available_payload_transports_without_requiring_server_signal",
            },
        }

    def status(self) -> dict[str, Any]:
        verifier_configured = bool(self.signing_key)
        return {
            "architecture": "two_track_hybrid_network",
            "evolutionary_architecture": "local_first_cloud_assisted_network",
            "phase": "phase_1_to_phase_2_transition",
            "config": self.config.public_status(),
            "remote_fragment_adoption_enabled": verifier_configured,
            "remote_fragment_adoption_state": (
                "ready" if verifier_configured else "disabled_missing_signature_verifier"
            ),
            "signaling_providers": [getattr(provider, "name", provider.__class__.__name__) for provider in self.signal_providers],
            "payload_transports": [transport.name for transport in self.payload_transports],
            "separation": {
                "metadata_signaling": "server_optional",
                "payload_transfer": "edge_p2p_or_signed_fragment",
                "server_dependency_for_edge_payload": False,
            },
        }

    def _ordered_transports(self, hint: PeerHint) -> list[PayloadTransport]:
        usable = [transport for transport in self.payload_transports if transport.can_handle(hint)]
        if hint.transport in {"http", "server"}:
            return sorted(usable, key=lambda transport: 0 if transport.name.startswith("http") else 1)
        return sorted(usable, key=lambda transport: 1 if transport.name.startswith("http") else 0)

    def _validate_envelope(self, envelope: GraphFragmentEnvelope) -> None:
        envelope.validate(
            signing_key=self.signing_key,
            max_bytes=self.config.max_fragment_bytes,
            max_nodes=self.config.max_nodes,
            max_edges=self.config.max_edges,
        )

    def _validate_resolved_envelope(self, envelope: GraphFragmentEnvelope, hint: PeerHint) -> None:
        """Treat discovery hints as routing proposals, never fragment authority.

        The public resolver may receive hints from remote signaling providers.
        A hint matching a caller-recomputed payload is still self-consistency,
        not evidence.  Resolution therefore fails closed unless a configured
        verifier authenticates the signed envelope, then binds the authenticated
        peer and concept back to the route that was proposed.
        """

        if not self.signing_key:
            raise ValueError("remote fragment signature verifier is not configured")
        self._validate_envelope(envelope)
        if not hmac.compare_digest(envelope.source_peer_id, hint.peer_id):
            raise ValueError("signed fragment source_peer_id does not match peer hint")
        if hint.concept_id not in envelope.concept_ids:
            raise ValueError("signed fragment concept_ids do not include peer hint concept_id")

    async def _verify_ontological_consistency(self, envelope: GraphFragmentEnvelope) -> dict[str, Any] | None:
        try:
            from rag_engine.self_correction import verify_fragment_consistency
        except Exception:
            return None
        report = await verify_fragment_consistency(envelope, config=self.config)
        if not report.accepted:
            raise ValueError(
                f"ontological inconsistency blocked fragment "
                f"{envelope.fragment_id}: score={report.contradiction_score:.3f} "
                f"threshold={report.threshold:.3f}"
            )
        return report.to_dict()

    @staticmethod
    def _dedupe_hints(hints: list[PeerHint]) -> list[PeerHint]:
        best: dict[tuple[str, str], PeerHint] = {}
        for hint in hints:
            key = (hint.peer_id, hint.concept_id)
            if key not in best or hint.score > best[key].score:
                best[key] = hint
        return sorted(best.values(), key=lambda hint: hint.score, reverse=True)

    @staticmethod
    def _query_to_vector(query: str) -> list[float]:
        return query_to_vector(query)


def query_to_vector(query: str) -> list[float]:
    footprint = query_text_footprint(query)
    values: list[float] = []
    for index in range(0, min(len(footprint), 64), 2):
        byte = int(footprint[index : index + 2], 16)
        values.append((byte / 127.5) - 1.0)
    return values


default_hybrid_network_manager = HybridNetworkManager()


async def broadcast_query_intent(query_vector: list[float]) -> list[PeerHint]:
    return await default_hybrid_network_manager.broadcast_query_intent(query_vector)


async def fetch_p2p_subgraph(peer_id: str, concept_id: str) -> GraphFragmentEnvelope:
    return await default_hybrid_network_manager.fetch_p2p_subgraph(peer_id, concept_id)


async def resolve_cloud_knowledge(query: str) -> dict[str, Any]:
    return await default_hybrid_network_manager.resolve_cloud_knowledge(query)
