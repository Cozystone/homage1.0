#!/usr/bin/env python3
"""Install only a journal-committed, operator-signed shipped graph generation.

This is a deployment evidence verifier, not mutation authority.  It accepts an
expired promotion document only when the fixed replay-domain receipt proves the
nonce was consumed inside the document's signed time window and the append-only
swap journal ended in COMMITTED.  The source is code-pinned to the repository's
canonical shipped store; callers cannot substitute another tree.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[1]
for value in (str(REPO), str(REPO / "scripts")):
    if value not in sys.path:
        sys.path.insert(0, value)

import landing_chain_lib as landing  # noqa: E402
from packages.autonomy_envelope.operator_trust import (  # noqa: E402
    verify_shipped_graph_promotion_historical,
)

_LEGACY_RECEIPT_FIELDS = {
    "schema_version",
    "nonce",
    "ledger_id",
    "nonce_replay_domain_sha256",
    "transaction_id",
    "swap_intent_sha256",
    "prepared_event_sha256",
    "promotion_payload_sha256",
    "candidate_digest_sha256",
    "base_revision",
    "target_store_id",
    "planned_backup_path",
    "planned_sealed_snapshot_path",
    "consumed_at_utc",
}
_RECEIPT_FIELDS = _LEGACY_RECEIPT_FIELDS | {
    "mutation_batch_manifest_sha256"
}


def _canonical_json(value: dict[str, Any]) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


def _absolute_directory(path: str | Path, *, label: str) -> Path:
    lexical = Path(path)
    if not lexical.is_absolute():
        raise RuntimeError(f"{label} must be an absolute path")
    absolute = Path(os.path.abspath(lexical))
    resolved = lexical.resolve(strict=True)
    if os.path.normcase(str(absolute)) != os.path.normcase(str(resolved)):
        raise RuntimeError(f"{label} must not traverse a link")
    if landing._is_link_or_junction(lexical) or not resolved.is_dir():
        raise RuntimeError(f"{label} must be a real directory")
    return resolved


def _load_document(path: str | Path) -> tuple[dict[str, Any], bytes]:
    raw = Path(path).read_bytes()
    document = landing._strict_json_object(
        raw,
        label="promotion document",
    )
    return document, raw


def _parse_consumed_at(value: Any) -> datetime:
    if not isinstance(value, str):
        raise RuntimeError("nonce receipt consumption time is missing")
    try:
        parsed = datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ")
    except ValueError as exc:
        raise RuntimeError("nonce receipt consumption time is invalid") from exc
    return parsed.replace(tzinfo=timezone.utc)


def verify_deployment_evidence(
    promotion_document_path: str | Path,
    *,
    source_root: Path | None = None,
) -> dict[str, Any]:
    """Return a seal only if source bytes have complete signed swap evidence."""
    source = (
        landing.CANONICAL_SHIPPED_ROOT
        if source_root is None
        else Path(source_root)
    )
    source = landing._canonical_directory(
        source,
        label="canonical shipped deployment source",
    )
    approved = landing._canonical_directory(
        landing.CANONICAL_SHIPPED_ROOT,
        label="approved canonical shipped source",
    )
    if source != approved:
        raise RuntimeError("deployment source is not the canonical shipped store")
    boundary = landing.load_system_shipped_graph_operator_boundary(
        repository_root=landing.REPOSITORY_ROOT,
        expected_target_store_id=landing.SHIPPED_STORE_TARGET_ID,
    )
    document, document_raw = _load_document(promotion_document_path)
    nonce = document.get("nonce")
    if not isinstance(nonce, str):
        raise RuntimeError("promotion document nonce is missing")
    receipt_name = (
        hashlib.sha256(nonce.encode("utf-8")).hexdigest()
        + ".consumed.json"
    )
    receipt_path = boundary.replay_domain.claims_root / receipt_name
    receipt_raw = receipt_path.read_bytes()
    receipt = landing._strict_json_object(
        receipt_raw,
        label="promotion nonce receipt",
    )
    receipt_schema = receipt.get("schema_version")
    expected_receipt_fields = (
        _LEGACY_RECEIPT_FIELDS
        if receipt_schema == "atanor.promotion-nonce-consumption.v2"
        else _RECEIPT_FIELDS
    )
    if (
        set(receipt) != expected_receipt_fields
        or receipt_raw != _canonical_json(receipt)
        or receipt_schema
        not in {
            "atanor.promotion-nonce-consumption.v2",
            "atanor.promotion-nonce-consumption.v3",
        }
    ):
        raise RuntimeError(
            "promotion nonce receipt is not exact canonical v2/v3"
        )

    source_digest = landing._tree_sha256(source)
    context = {
        "staging_receipt_sha256": document.get(
            "staging_receipt_sha256"
        ),
        "candidate_digest_sha256": source_digest,
        "item_ids": document.get("item_ids"),
        "target_store_id": landing.SHIPPED_STORE_TARGET_ID,
        **boundary.context_binding,
        "base_revision": document.get("base_revision"),
        "rollback_artifact_sha256": document.get(
            "rollback_artifact_sha256"
        ),
    }
    if "mutation_batch_manifest_sha256" in document:
        context["mutation_batch_manifest_sha256"] = document.get(
            "mutation_batch_manifest_sha256"
        )
    consumed_at = _parse_consumed_at(receipt.get("consumed_at_utc"))
    verified = verify_shipped_graph_promotion_historical(
        document,
        trust_root=boundary.trust_root,
        live_context=context,
        consumption_time=consumed_at,
    )
    if verified.ok is not True or not isinstance(
        verified.payload_sha256,
        str,
    ):
        raise RuntimeError(
            f"historical promotion evidence rejected: {verified.reason}"
        )
    expected_receipt = {
        "ledger_id": boundary.replay_domain.ledger_id,
        "nonce_replay_domain_sha256": (
            boundary.replay_domain.binding_sha256
        ),
        "promotion_payload_sha256": verified.payload_sha256,
        "candidate_digest_sha256": source_digest,
        "base_revision": document.get("base_revision"),
        "target_store_id": landing.SHIPPED_STORE_TARGET_ID,
    }
    if receipt_schema == "atanor.promotion-nonce-consumption.v3":
        expected_receipt["mutation_batch_manifest_sha256"] = (
            document.get("mutation_batch_manifest_sha256")
        )
    for field, expected in expected_receipt.items():
        if receipt.get(field) != expected:
            raise RuntimeError(
                f"promotion nonce receipt {field} binding mismatch"
            )

    # This rejects incomplete/aborted/tampered journals and proves that the
    # current source equals the latest committed signed generation.
    landing._assert_no_unresolved_swap_transactions(
        boundary.replay_domain,
        live=source,
    )
    transaction_id = receipt.get("transaction_id")
    if not isinstance(transaction_id, str):
        raise RuntimeError("nonce receipt transaction id is missing")
    transaction_root = (
        boundary.replay_domain.claims_root
        / "transactions"
        / transaction_id
    )
    commit_events = list(transaction_root.glob("*.COMMITTED.json"))
    if len(commit_events) != 1:
        raise RuntimeError("promotion transaction has no unique COMMITTED event")
    commit_raw = commit_events[0].read_bytes()
    commit = landing._strict_json_object(
        commit_raw,
        label="promotion COMMITTED event",
    )
    intent_raw = (transaction_root / "intent.json").read_bytes()
    intent = landing._strict_json_object(
        intent_raw,
        label="promotion swap intent",
    )
    if (
        commit_raw != _canonical_json(commit)
        or intent_raw != _canonical_json(intent)
        or commit.get("transaction_id") != transaction_id
        or intent.get("transaction_id") != transaction_id
        or commit.get("intent_sha256")
        != hashlib.sha256(intent_raw).hexdigest()
        or receipt.get("swap_intent_sha256")
        != hashlib.sha256(intent_raw).hexdigest()
        or intent.get("promotion_payload_sha256")
        != verified.payload_sha256
        or intent.get("authorized_candidate_sha256") != source_digest
        or (
            (
                intent.get("schema_version")
                == "atanor.shipped-store-swap-intent.v2"
            )
            != (
                receipt_schema
                == "atanor.promotion-nonce-consumption.v3"
            )
        )
        or (
            intent.get("schema_version")
            == "atanor.shipped-store-swap-intent.v2"
            and (
                intent.get("mutation_batch_manifest_sha256")
                != document.get("mutation_batch_manifest_sha256")
                or receipt.get("mutation_batch_manifest_sha256")
                != document.get("mutation_batch_manifest_sha256")
            )
        )
    ):
        raise RuntimeError("promotion transaction evidence is inconsistent")
    boundary.revalidate()
    if landing._tree_sha256(source) != source_digest:
        raise RuntimeError("canonical source changed during evidence verification")
    result = {
        "schema_version": (
            "atanor.shipped-graph-deployment-seal.v2"
            if "mutation_batch_manifest_sha256" in document
            else "atanor.shipped-graph-deployment-seal.v1"
        ),
        "target_store_id": landing.SHIPPED_STORE_TARGET_ID,
        "source_digest_sha256": source_digest,
        "promotion_payload_sha256": verified.payload_sha256,
        "promotion_document_file_sha256": hashlib.sha256(
            document_raw
        ).hexdigest(),
        "nonce_receipt_sha256": hashlib.sha256(receipt_raw).hexdigest(),
        "transaction_id": transaction_id,
        "committed_event_sha256": hashlib.sha256(commit_raw).hexdigest(),
        "operator_boundary_id": boundary.boundary_id,
        "operator_boundary_config_sha256": boundary.config_sha256,
        "nonce_replay_domain_sha256": (
            boundary.replay_domain.binding_sha256
        ),
        "verified_at_utc": datetime.now(timezone.utc).strftime(
            "%Y-%m-%dT%H:%M:%SZ"
        ),
    }
    if "mutation_batch_manifest_sha256" in document:
        result["mutation_batch_manifest_sha256"] = document[
            "mutation_batch_manifest_sha256"
        ]
    return result


def _installed_store(root: Path) -> Path:
    return root / "opt" / "atanor" / "data" / "graph_scale" / "kg_triples"


def _set_read_only_tree(root: Path) -> None:
    for directory, _children, files in os.walk(root):
        directory_path = Path(directory)
        for name in files:
            (directory_path / name).chmod(0o444)
        directory_path.chmod(0o555)


def install(
    rootfs: str | Path,
    promotion_document_path: str | Path,
) -> dict[str, Any]:
    root = _absolute_directory(rootfs, label="rootfs")
    seal = verify_deployment_evidence(promotion_document_path)
    source = landing.CANONICAL_SHIPPED_ROOT.resolve(strict=True)
    destination = _installed_store(root)
    destination.parent.mkdir(parents=True, exist_ok=True)
    tag = uuid.uuid4().hex
    temporary = destination.parent / f".kg_triples.installing.{tag}"
    backup = destination.parent / f".kg_triples.replaced.{tag}"
    shutil.copytree(source, temporary, symlinks=False)
    if landing._tree_sha256(temporary) != seal["source_digest_sha256"]:
        shutil.rmtree(temporary)
        raise RuntimeError("copied shipped graph digest mismatch")
    moved_old = False
    try:
        if destination.exists():
            destination.rename(backup)
            moved_old = True
        temporary.rename(destination)
        if landing._tree_sha256(destination) != seal["source_digest_sha256"]:
            raise RuntimeError("installed shipped graph digest mismatch")
    except Exception:
        if destination.exists():
            shutil.rmtree(destination)
        if moved_old and backup.exists():
            backup.rename(destination)
        if temporary.exists():
            shutil.rmtree(temporary)
        raise
    if backup.exists():
        shutil.rmtree(backup)
    _set_read_only_tree(destination)
    evidence = (
        root
        / "usr"
        / "share"
        / "atanor"
        / "evidence"
        / "shipped-graph"
    )
    evidence.mkdir(parents=True, exist_ok=True)
    (evidence / "deployment-seal.json").write_bytes(_canonical_json(seal))
    shutil.copy2(
        promotion_document_path,
        evidence / "promotion-document.json",
    )
    return {**seal, "installed_path": str(destination)}


def verify_copy(
    root: str | Path,
    promotion_document_path: str | Path,
) -> dict[str, Any]:
    filesystem_root = _absolute_directory(root, label="filesystem root")
    seal = verify_deployment_evidence(promotion_document_path)
    installed = _installed_store(filesystem_root)
    digest = landing._tree_sha256(installed)
    if digest != seal["source_digest_sha256"]:
        raise RuntimeError("deployed shipped graph copy digest mismatch")
    return {**seal, "verified_copy": str(installed)}


def main() -> int:
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="command", required=True)
    install_parser = subparsers.add_parser("install")
    install_parser.add_argument("--rootfs", required=True)
    install_parser.add_argument("--promotion-document", required=True)
    verify_parser = subparsers.add_parser("verify-copy")
    verify_parser.add_argument("--root", required=True)
    verify_parser.add_argument("--promotion-document", required=True)
    args = parser.parse_args()
    try:
        if args.command == "install":
            result = install(args.rootfs, args.promotion_document)
        else:
            result = verify_copy(args.root, args.promotion_document)
    except Exception as exc:
        print(
            json.dumps(
                {
                    "ok": False,
                    "reason": f"{type(exc).__name__}: {exc}",
                },
                ensure_ascii=False,
            ),
            file=sys.stderr,
        )
        return 4
    print(json.dumps({"ok": True, **result}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
