from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Literal


NetworkMode = Literal["local_first", "server_assisted", "p2p_dominant"]


def _env_bool(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _env_alias(primary: str, legacy: str, default: str | None = None) -> str | None:
    return os.getenv(primary, os.getenv(legacy, default))


def _env_bool_alias(primary: str, legacy: str, default: bool) -> bool:
    value = _env_alias(primary, legacy)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, str(default)))
    except ValueError:
        return default


def _env_float(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, str(default)))
    except ValueError:
        return default


def _env_int_alias(primary: str, legacy: str, default: int) -> int:
    try:
        return int(_env_alias(primary, legacy, str(default)) or default)
    except ValueError:
        return default


def _env_float_alias(primary: str, legacy: str, default: float) -> float:
    try:
        return float(_env_alias(primary, legacy, str(default)) or default)
    except ValueError:
        return default


@dataclass(frozen=True)
class NetworkConfig:
    """Central config for local-first, cloud-assisted networking.

    No URL, API key, or server dependency is baked into the networking core.
    A default instance runs fully offline on localhost and simply returns no
    remote peers until the user supplies signaling or local peer-directory
    configuration.
    """

    mode: NetworkMode = "local_first"
    local_peer_id: str = "homage-local-peer"
    homage_gateway_api: str = "http://127.0.0.1:8500"
    local_payload_endpoint: str | None = "http://127.0.0.1:8500"
    peer_directory_path: Path = Path("data/network/peers.json")
    enable_server_signaling: bool = False
    enable_local_peer_directory: bool = True
    enable_p2p_payload: bool = True
    enable_http_payload_fallback: bool = True
    fallback_to_server_payload: bool = True
    supabase_url: str | None = None
    supabase_key: str | None = None
    supabase_peer_table: str = "homage_peer_index"
    timeout_seconds: float = 2.5
    max_fragment_bytes: int = 2_000_000
    max_nodes: int = 2_048
    max_edges: int = 8_192
    contradiction_threshold: float = 0.72
    trust_penalty_on_contradiction: float = 0.1
    trust_store_path: Path = Path("data/network/peer_trust.json")
    replay_interval_seconds: float = 300.0
    replay_top_percent: float = 0.05
    replay_max_edges_per_cycle: int = 8_192
    replay_min_confidence: float = 0.62
    ssm_ingest_chunk_tokens: int = 512
    ssm_max_depth: int = 3
    signing_key: str | None = None

    @classmethod
    def from_env(cls) -> "NetworkConfig":
        raw_mode = (_env_alias("ATANOR_NETWORK_MODE", "HOMAGE_NETWORK_MODE", "local_first") or "local_first").strip().lower()
        mode: NetworkMode = raw_mode if raw_mode in {"local_first", "server_assisted", "p2p_dominant"} else "local_first"  # type: ignore[assignment]
        supabase_url = os.getenv("SUPABASE_URL")
        supabase_key = os.getenv("SUPABASE_SERVICE_ROLE_KEY") or os.getenv("SUPABASE_ANON_KEY")
        server_signaling_default = mode == "server_assisted" and bool(supabase_url and supabase_key)
        return cls(
            mode=mode,
            local_peer_id=_env_alias("ATANOR_LOCAL_PEER_ID", "HOMAGE_LOCAL_PEER_ID", "atanor-local-peer") or "atanor-local-peer",
            homage_gateway_api=_env_alias(
                "ATANOR_GATEWAY_API",
                "HOMAGE_GATEWAY_API",
                _env_alias("ATANOR_LOCAL_PAYLOAD_ENDPOINT", "HOMAGE_LOCAL_PAYLOAD_ENDPOINT", "http://127.0.0.1:8500"),
            )
            or "http://127.0.0.1:8500",
            local_payload_endpoint=_env_alias(
                "ATANOR_LOCAL_PAYLOAD_ENDPOINT",
                "HOMAGE_LOCAL_PAYLOAD_ENDPOINT",
                _env_alias("ATANOR_GATEWAY_API", "HOMAGE_GATEWAY_API", "http://127.0.0.1:8500"),
            ),
            peer_directory_path=Path(_env_alias("ATANOR_PEER_DIRECTORY", "HOMAGE_PEER_DIRECTORY", "data/network/peers.json") or "data/network/peers.json"),
            enable_server_signaling=_env_bool_alias("ATANOR_ENABLE_SERVER_SIGNALING", "HOMAGE_ENABLE_SERVER_SIGNALING", server_signaling_default),
            enable_local_peer_directory=_env_bool_alias("ATANOR_ENABLE_LOCAL_PEER_DIRECTORY", "HOMAGE_ENABLE_LOCAL_PEER_DIRECTORY", True),
            enable_p2p_payload=_env_bool_alias("ATANOR_ENABLE_P2P_PAYLOAD", "HOMAGE_ENABLE_P2P_PAYLOAD", True),
            enable_http_payload_fallback=_env_bool_alias("ATANOR_ENABLE_HTTP_PAYLOAD_FALLBACK", "HOMAGE_ENABLE_HTTP_PAYLOAD_FALLBACK", True),
            fallback_to_server_payload=_env_bool_alias("ATANOR_FALLBACK_TO_SERVER_PAYLOAD", "HOMAGE_FALLBACK_TO_SERVER_PAYLOAD", True),
            supabase_url=supabase_url,
            supabase_key=supabase_key,
            supabase_peer_table=_env_alias("ATANOR_SUPABASE_PEER_TABLE", "HOMAGE_SUPABASE_PEER_TABLE", "atanor_peer_index") or "atanor_peer_index",
            timeout_seconds=_env_float_alias("ATANOR_NETWORK_TIMEOUT_SECONDS", "HOMAGE_NETWORK_TIMEOUT_SECONDS", 2.5),
            max_fragment_bytes=_env_int_alias("ATANOR_MAX_FRAGMENT_BYTES", "HOMAGE_MAX_FRAGMENT_BYTES", 2_000_000),
            max_nodes=_env_int_alias("ATANOR_MAX_FRAGMENT_NODES", "HOMAGE_MAX_FRAGMENT_NODES", 2_048),
            max_edges=_env_int_alias("ATANOR_MAX_FRAGMENT_EDGES", "HOMAGE_MAX_FRAGMENT_EDGES", 8_192),
            contradiction_threshold=_env_float_alias("ATANOR_CONTRADICTION_THRESHOLD", "HOMAGE_CONTRADICTION_THRESHOLD", 0.72),
            trust_penalty_on_contradiction=_env_float_alias("ATANOR_TRUST_PENALTY_ON_CONTRADICTION", "HOMAGE_TRUST_PENALTY_ON_CONTRADICTION", 0.1),
            trust_store_path=Path(_env_alias("ATANOR_TRUST_STORE", "HOMAGE_TRUST_STORE", "data/network/peer_trust.json") or "data/network/peer_trust.json"),
            replay_interval_seconds=_env_float_alias("ATANOR_REPLAY_INTERVAL_SECONDS", "HOMAGE_REPLAY_INTERVAL_SECONDS", 300.0),
            replay_top_percent=_env_float_alias("ATANOR_REPLAY_TOP_PERCENT", "HOMAGE_REPLAY_TOP_PERCENT", 0.05),
            replay_max_edges_per_cycle=_env_int_alias("ATANOR_REPLAY_MAX_EDGES_PER_CYCLE", "HOMAGE_REPLAY_MAX_EDGES_PER_CYCLE", 8_192),
            replay_min_confidence=_env_float_alias("ATANOR_REPLAY_MIN_CONFIDENCE", "HOMAGE_REPLAY_MIN_CONFIDENCE", 0.62),
            ssm_ingest_chunk_tokens=_env_int_alias("ATANOR_SSM_INGEST_CHUNK_TOKENS", "HOMAGE_SSM_INGEST_CHUNK_TOKENS", 512),
            ssm_max_depth=_env_int_alias("ATANOR_SSM_MAX_DEPTH", "HOMAGE_SSM_MAX_DEPTH", 3),
            signing_key=_env_alias("ATANOR_FRAGMENT_SIGNING_KEY", "HOMAGE_FRAGMENT_SIGNING_KEY"),
        )

    @property
    def server_configured(self) -> bool:
        return bool(self.supabase_url and self.supabase_key)

    @property
    def standalone_localhost_ready(self) -> bool:
        return bool(self.local_payload_endpoint and self.local_payload_endpoint.startswith("http://127.0.0.1"))

    def public_status(self) -> dict[str, object]:
        return {
            "mode": self.mode,
            "local_peer_id": self.local_peer_id,
            "atanor_gateway_api": self.homage_gateway_api,
            "homage_gateway_api": self.homage_gateway_api,
            "standalone_localhost_ready": self.standalone_localhost_ready,
            "server_signaling_enabled": self.enable_server_signaling,
            "server_configured": self.server_configured,
            "local_peer_directory_enabled": self.enable_local_peer_directory,
            "p2p_payload_enabled": self.enable_p2p_payload,
            "http_payload_fallback_enabled": self.enable_http_payload_fallback,
            "fallback_to_server_payload": self.fallback_to_server_payload,
            "fragment_signature_verifier_configured": bool(self.signing_key),
            "max_fragment_bytes": self.max_fragment_bytes,
            "max_nodes": self.max_nodes,
            "max_edges": self.max_edges,
            "contradiction_threshold": self.contradiction_threshold,
            "replay_top_percent": self.replay_top_percent,
            "replay_max_edges_per_cycle": self.replay_max_edges_per_cycle,
            "ssm_ingest_chunk_tokens": self.ssm_ingest_chunk_tokens,
        }
