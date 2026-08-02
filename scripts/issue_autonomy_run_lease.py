"""Issue one externally signed, bounded ATANOR autonomy run lease.

The command is intentionally signer-only: it does not generate keys, contact a
server, start a runner, or mutate the replay ledger.  The Ed25519 private key
must be supplied explicitly from outside the repository.  The resulting lease
is written atomically and never overwrites an existing path.
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import os
import secrets
import sys
import tempfile
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Mapping

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from packages.autonomy_envelope.operator_trust import (  # noqa: E402
    ED25519_SCHEME,
    SIGNATURE_FIELD,
    OperatorTrustRoot,
    canonical_payload_bytes,
    payload_sha256,
)
from packages.autonomy_envelope.run_lease import (  # noqa: E402
    RUN_LEASE_PURPOSE,
    RUN_LEASE_SCHEMA_VERSION,
    RunLeaseBoundaryConfig,
    verify_run_lease,
)


@dataclass(frozen=True)
class LoadedLiveContext:
    """Detached endpoint context plus any independently useful key pin."""

    live_context: dict[str, Any]
    advertised_key_id: str | None


def _reject_json_constant(value: str) -> None:
    raise ValueError(f"non-finite JSON value is forbidden: {value}")


def _strict_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate JSON field: {key}")
        result[key] = value
    return result


def _read_strict_json_object(path: str | Path) -> dict[str, Any]:
    source = Path(path).expanduser().resolve(strict=True)
    if not source.is_file():
        raise ValueError("live-context input must be a file")
    try:
        value = json.loads(
            source.read_text(encoding="utf-8"),
            object_pairs_hook=_strict_object,
            parse_constant=_reject_json_constant,
        )
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError("live-context input is unreadable JSON") from exc
    if type(value) is not dict:
        raise ValueError("live-context input must be a JSON object")
    return value


def _canonical_bytes(value: Mapping[str, Any]) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


def load_live_context(path: str | Path) -> LoadedLiveContext:
    """Load either the exact context object or its `/lease-context` response."""

    value = _read_strict_json_object(path)
    if "live_context" not in value:
        return LoadedLiveContext(
            live_context=value,
            advertised_key_id=None,
        )

    context = value.get("live_context")
    if (
        value.get("available") is not True
        or value.get("purpose") != RUN_LEASE_PURPOSE
        or type(context) is not dict
    ):
        raise ValueError("lease-context response is unavailable or invalid")
    advertised_digest = value.get("live_context_sha256")
    actual_digest = hashlib.sha256(_canonical_bytes(context)).hexdigest()
    if advertised_digest != actual_digest:
        raise ValueError("lease-context response digest mismatch")
    if value.get("signer_present_in_api") is not False:
        raise ValueError("lease-context response signer boundary is invalid")
    if value.get("private_key_required_outside_api") is not True:
        raise ValueError("lease-context response private-key boundary is invalid")

    advertised_values = [
        item
        for field in (
            "expected_key_id",
            "operator_expected_key_id",
            "operator_key_id",
        )
        if (item := value.get(field)) is not None
    ]
    if any(type(item) is not str or not item for item in advertised_values):
        raise ValueError("lease-context response key metadata is invalid")
    advertised_ids = set(advertised_values)
    if len(advertised_ids) > 1:
        raise ValueError("lease-context response key metadata conflicts")
    return LoadedLiveContext(
        live_context=context,
        advertised_key_id=next(iter(advertised_ids), None),
    )


def _external_file(path: str | Path, *, label: str) -> Path:
    candidate = Path(path).expanduser()
    if not candidate.is_absolute():
        raise ValueError(f"{label} path must be absolute")
    resolved = candidate.resolve(strict=True)
    if not resolved.is_file():
        raise ValueError(f"{label} path must name a file")
    try:
        resolved.relative_to(REPO.resolve(strict=True))
    except ValueError:
        return resolved
    raise ValueError(f"{label} must remain outside the repository")


def _load_private_key(path: str | Path) -> Ed25519PrivateKey:
    key_path = _external_file(path, label="operator private key")
    try:
        key = serialization.load_pem_private_key(
            key_path.read_bytes(),
            password=None,
        )
    except Exception as exc:
        raise ValueError(
            "operator private key is unreadable or encrypted"
        ) from exc
    if not isinstance(key, Ed25519PrivateKey):
        raise ValueError("operator private key must be Ed25519")
    return key


def _operator_key_id(private_key: Ed25519PrivateKey) -> str:
    raw = private_key.public_key().public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw,
    )
    return f"ed25519:{hashlib.sha256(raw).hexdigest()[:24]}"


def _public_pem(private_key: Ed25519PrivateKey) -> bytes:
    return private_key.public_key().public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    )


def _check_boundary_context(
    context: Mapping[str, Any],
    *,
    boundary: RunLeaseBoundaryConfig,
) -> None:
    expected = {
        "deployment_id": boundary.deployment_id,
        "operator_boundary_id": boundary.operator_boundary_id,
        "operator_boundary_config_sha256": (
            boundary.operator_boundary_config_sha256
        ),
        "nonce_replay_domain": boundary.replay_domain,
    }
    for field, value in expected.items():
        if context.get(field) != value:
            raise ValueError(
                f"live context does not match trust boundary field: {field}"
            )


def build_signed_run_lease(
    live_context: Mapping[str, Any],
    *,
    private_key_path: str | Path,
    duration_sec: int,
    lease_id: str | None = None,
    nonce: str | None = None,
    expected_key_id: str | None = None,
    advertised_key_id: str | None = None,
    trust_config_path: str | Path | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Build and locally verify one lease without writing or activating it."""

    if type(live_context) is not dict:
        raise ValueError("live context must be an exact JSON object")
    try:
        context = json.loads(_canonical_bytes(live_context))
    except (TypeError, ValueError, json.JSONDecodeError) as exc:
        raise ValueError("live context is not canonical JSON") from exc
    if type(context) is not dict:
        raise ValueError("live context must be an exact JSON object")
    if type(duration_sec) is not int or duration_sec < 1:
        raise ValueError("duration-sec must be a positive integer")
    limits = context.get("limits")
    if (
        type(limits) is not dict
        or type(limits.get("max_runtime_sec")) is not int
    ):
        raise ValueError("live context max_runtime_sec is invalid")
    if duration_sec > limits["max_runtime_sec"]:
        raise ValueError("duration-sec exceeds live context max_runtime_sec")

    private_key = _load_private_key(private_key_path)
    key_id = _operator_key_id(private_key)
    for pin_label, pin in (
        ("expected key", expected_key_id),
        ("advertised key", advertised_key_id),
    ):
        if pin is not None and pin != key_id:
            raise ValueError(f"operator private key does not match {pin_label} pin")

    boundary: RunLeaseBoundaryConfig | None = None
    if trust_config_path is not None:
        boundary = RunLeaseBoundaryConfig.from_external_file(
            _external_file(
                trust_config_path,
                label="run-lease trust config",
            ),
            repository_root=REPO,
        )
        if boundary.expected_key_id != key_id:
            raise ValueError(
                "operator private key does not match trust boundary key pin"
            )
        _check_boundary_context(context, boundary=boundary)

    issued = now or datetime.now(timezone.utc)
    if issued.tzinfo is None:
        raise ValueError("issuance clock must be timezone-aware")
    issued = issued.astimezone(timezone.utc).replace(microsecond=0)
    expires = issued + timedelta(seconds=duration_sec)
    document: dict[str, Any] = {
        "schema_version": RUN_LEASE_SCHEMA_VERSION,
        "purpose": RUN_LEASE_PURPOSE,
        "lease_id": lease_id or f"lease-{secrets.token_hex(16)}",
        **context,
        "issued_at": issued.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "expires_at": expires.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "nonce": nonce or f"nonce-{secrets.token_hex(24)}",
        SIGNATURE_FIELD: {
            "scheme": ED25519_SCHEME,
            "key_id": key_id,
            "payload_sha256": "",
            "signature": "",
        },
    }
    digest = payload_sha256(document)
    document[SIGNATURE_FIELD] = {
        "scheme": ED25519_SCHEME,
        "key_id": key_id,
        "payload_sha256": digest,
        "signature": base64.b64encode(
            private_key.sign(canonical_payload_bytes(document))
        ).decode("ascii"),
    }

    trust_root = (
        boundary.trust_root
        if boundary is not None
        else OperatorTrustRoot(_public_pem(private_key), expected_key_id=key_id)
    )
    verified = verify_run_lease(
        document,
        trust_root=trust_root,
        live_context=context,
    )
    if not verified.ok:
        raise ValueError(
            f"generated run lease failed local verification: {verified.reason}"
        )
    return document


def _atomic_write_new_json(path: str | Path, value: Mapping[str, Any]) -> Path:
    destination = Path(path).expanduser()
    parent = destination.parent.resolve(strict=True)
    destination = parent / destination.name
    if not destination.name:
        raise ValueError("output path must name a file")
    if destination.exists():
        raise FileExistsError("output path already exists")
    payload = json.dumps(
        value,
        ensure_ascii=False,
        indent=2,
        sort_keys=True,
        allow_nan=False,
    ).encode("utf-8") + b"\n"

    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{destination.name}.",
        suffix=".tmp",
        dir=parent,
    )
    temporary = Path(temporary_name)
    try:
        try:
            os.chmod(temporary, 0o600)
        except OSError:
            pass
        with os.fdopen(descriptor, "wb") as stream:
            descriptor = -1
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        try:
            os.link(temporary, destination)
        except FileExistsError as exc:
            raise FileExistsError("output path already exists") from exc
        return destination
    finally:
        if descriptor >= 0:
            os.close(descriptor)
        try:
            temporary.unlink()
        except FileNotFoundError:
            pass


def issue_run_lease_file(
    *,
    input_path: str | Path,
    output_path: str | Path,
    private_key_path: str | Path,
    duration_sec: int,
    lease_id: str | None = None,
    nonce: str | None = None,
    expected_key_id: str | None = None,
    trust_config_path: str | Path | None = None,
) -> dict[str, Any]:
    """Load, sign, verify, and atomically persist one non-overwriting lease."""

    input_resolved = Path(input_path).expanduser().resolve(strict=True)
    key_resolved = Path(private_key_path).expanduser()
    if not key_resolved.is_absolute():
        raise ValueError("operator private key path must be absolute")
    key_resolved = key_resolved.resolve(strict=True)
    output_candidate = Path(output_path).expanduser()
    output_resolved = (
        output_candidate.parent.resolve(strict=True) / output_candidate.name
    )
    if key_resolved in {input_resolved, output_resolved}:
        raise ValueError("private key cannot be used as input or output")
    if output_resolved.exists():
        raise FileExistsError("output path already exists")

    loaded = load_live_context(input_resolved)
    document = build_signed_run_lease(
        loaded.live_context,
        private_key_path=key_resolved,
        duration_sec=duration_sec,
        lease_id=lease_id,
        nonce=nonce,
        expected_key_id=expected_key_id,
        advertised_key_id=loaded.advertised_key_id,
        trust_config_path=trust_config_path,
    )
    written = _atomic_write_new_json(output_resolved, document)
    return {
        "ok": True,
        "output": str(written),
        "lease_id": document["lease_id"],
        "runner_id": document["runner_id"],
        "key_id": document[SIGNATURE_FIELD]["key_id"],
        "payload_sha256": document[SIGNATURE_FIELD]["payload_sha256"],
        "expires_at": document["expires_at"],
    }


def _positive_integer(value: str) -> int:
    if not value.isascii() or not value.isdigit():
        raise argparse.ArgumentTypeError("must be a positive integer")
    parsed = int(value)
    if parsed < 1:
        raise argparse.ArgumentTypeError("must be a positive integer")
    return parsed


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True, help="live-context JSON file")
    parser.add_argument("--output", required=True, help="new lease JSON file")
    parser.add_argument(
        "--private-key",
        required=True,
        help="absolute external Ed25519 private-key PEM path",
    )
    parser.add_argument(
        "--duration-sec",
        required=True,
        type=_positive_integer,
    )
    parser.add_argument("--lease-id")
    parser.add_argument("--nonce")
    parser.add_argument(
        "--expected-key-id",
        help="optional independent ed25519 key-id pin",
    )
    parser.add_argument(
        "--trust-config",
        help="optional external run-lease trust config for full binding checks",
    )
    args = parser.parse_args(argv)
    try:
        receipt = issue_run_lease_file(
            input_path=args.input,
            output_path=args.output,
            private_key_path=args.private_key,
            duration_sec=args.duration_sec,
            lease_id=args.lease_id,
            nonce=args.nonce,
            expected_key_id=args.expected_key_id,
            trust_config_path=args.trust_config,
        )
    except Exception as exc:
        print(
            json.dumps(
                {
                    "ok": False,
                    "error": f"{type(exc).__name__}: {exc}",
                    "lease_written": False,
                },
                sort_keys=True,
            ),
            file=sys.stderr,
        )
        return 2
    print(json.dumps(receipt, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
