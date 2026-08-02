# -*- coding: utf-8 -*-
"""S1 LANDING CHAIN — shared library for the measure-then-promote pipeline.

This module is the load-bearing core behind three CLIs (all in scripts/):
  * measure_wikidata_staging.py   — READ-ONLY report on a staged store.
  * promote_staging_to_shipped.py — the SAFE bulk promoter (backup / merge into a NEW
    dir / verify / atomic swap / rollback).
  * build_t0_axioms.py            — the firewall T0 operator-axiom seed.

The store format it operates on (packages/graph_scale/triple_store.py):
  int32-columnar (s/p/o/src.col, one <i4 per row per column) + a term dictionary
  (ShardedTermDict = 16 sqlite shards under term_shards/, OR a RAM TermDict = terms.txt)
  + sources.txt (provenance registry, line index == src id) + meta.json + the subject
  index sidecars (s.perm.<ts>.npy / s.sorted.<ts>.npy).

THE CRUX — WHY A MERGE MUST REMAP TERM IDS
------------------------------------------
ShardedTermDict assigns a global id as ``gid = (rowid-1)*N + shard`` where ``shard =
crc32(term) % N`` and ``rowid`` is the term's per-shard sqlite rowid (1,2,3...). Two
independently-built stores therefore use DIFFERENT integer spaces for the SAME string:
"paris" is some gid in the shipped store and a completely different gid in the staged
store. So the merge cannot copy staged columns verbatim — every staged (s,p,o) id must be
translated through the staged term dict back to strings and re-interned into the merged
store's dict. Because both stores shard by the same crc32, a term lands in the same shard
number in both, which lets us remap with a per-shard sqlite JOIN instead of 10^7 python
lookups.

SAFETY MODEL
------------
The promoter builds the merged store as a COPY of the shipped store plus APPENDED novel
edges. The shipped rows/ids are therefore byte-identical in the new store — "every prior
fact still resolves at the same id" is guaranteed by construction, and verify() proves it
by byte-comparing the column prefix. The live store is only ever replaced by an atomic
directory rename, with the original preserved as a deterministic recovery artifact. The
rename boundary loads one installation-fixed external operator config; callers cannot
inject a key, key pin, replay ledger, or target. It requires an exact queue receipt, a v2
operator-signed v3 context, immutable mutation-batch manifest, current byte
digests, a sealed candidate copy, exclusive nonce
consumption, and an append-only crash journal. Unsigned in-process rollback is disabled.
On platforms where namespace directory durability cannot be demonstrated, the journal
records that limitation instead of claiming crash-durable E4.

numpy + the fail-closed Ed25519 verifier + stdlib.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import sqlite3
import stat
import time
import zlib
from collections import Counter
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from threading import Lock
from typing import Any, Iterable, Iterator, Mapping

import numpy as np

from packages.autonomy_envelope.operator_trust import (
    NONCE_LEDGER_CLAIMS_RELATIVE_PATH,
    NONCE_LEDGER_IDENTITY_FILENAME,
    NONCE_LEDGER_IDENTITY_SCHEMA_VERSION,
    NONCE_LEDGER_LOCK_RELATIVE_PATH,
    NONCE_REPLAY_DOMAIN_SCHEMA_VERSION,
    OperatorTrustRoot,
    verify_shipped_graph_promotion,
)
from packages.autonomy_envelope.promotion_queue import (
    INVARIANTS as STAGING_RECEIPT_INVARIANTS,
    REQUIRED_CONFIRMATION_PHRASE,
)
from packages.graph_scale.graph_paths import (
    SHIPPED_GRAPH_ROOT,
    SHIPPED_STORE_TARGET_ID,
)
from packages.graph_scale.mutation_batch import (
    MutationStage,
    load_validated_mutation_batch,
    record_lifecycle_receipt,
    validate_sealed_manifest_bytes,
)

# ShardedTermDict shard count (packages/graph_scale/sharded_term_dict.py: n_shards=16).
SHARD_N = 16

# English-only containment gate (owner directive 2026-07-17); mirrors triple_store._HANGUL_WRITE_GATE.
HANGUL = re.compile(r"[가-힣]")

# A dry-run assigns "brand new" staged terms synthetic ids ABOVE any real gid so they can
# never collide with a shipped column value (=> an edge touching a new term is always novel).
# It MUST stay below 2^31 so _pack's `s << 32` never overflows int64, and above any real gid so
# its low-32 bits can't alias a real gid. 2^30 clears both: real gids at S1 scale are < ~2.5e7
# (18M merged terms) and new terms number a few million, so 2^30 + n_new stays < 2^31.
_SYNTH_BASE = 1 << 30
_MAX_PACKABLE_GID = 1 << 31  # (s,o) dedup packs (s<<32)|o; both ids must be < this

# The production mutation boundary is deliberately pinned in code. Tests may monkeypatch
# this constant to a throwaway store, but callers cannot authorize an arbitrary --shipped
# path by passing it as another argument to StoreMerger.swap().
REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
CANONICAL_SHIPPED_ROOT = SHIPPED_GRAPH_ROOT
SYSTEM_SHIPPED_GRAPH_OPERATOR_BOUNDARY_CONFIG = (
    Path(r"C:\ProgramData\ATANOR\operator-boundary\shipped_graph_promotion.v1.json")
    if os.name == "nt"
    else Path("/etc/atanor/operator-boundary/shipped_graph_promotion.v1.json")
)
OPERATOR_BOUNDARY_CONFIG_SCHEMA_VERSION = (
    "atanor.shipped-graph-operator-boundary-config.v1"
)
MERGE_VERIFY_SCHEMA_VERSION = "atanor.store-merge-verification.v2"
MUTATION_BUILD_SCHEMA_VERSION = (
    "atanor.graph-scale.mutation-candidate-build.v1"
)
MUTATION_VERIFY_SCHEMA_VERSION = (
    "atanor.graph-scale.mutation-candidate-verification.v1"
)
MUTATION_BINDING_SCHEMA_VERSION = (
    "atanor.graph-scale.mutation-candidate-binding.v1"
)
MUTATION_BINDING_DIRECTORY = "MUTATION_BATCH"
_CANDIDATE_SUFFIX_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
_LEDGER_ID_RE = re.compile(
    r"^atanor:promotion-ledger:[A-Za-z0-9][A-Za-z0-9._-]{15,127}$"
)
_BOUNDARY_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/@+-]{0,255}$")
_OPERATOR_KEY_ID_RE = re.compile(r"^ed25519:[0-9a-f]{24}$")
_LOCAL_PROMOTION_LOCK = Lock()


def _is_link_or_junction(path: Path) -> bool:
    is_junction = getattr(os.path, "isjunction", None)
    return path.is_symlink() or bool(is_junction and is_junction(path))


def _canonical_directory(path: str | Path, *, label: str) -> Path:
    lexical = Path(path).expanduser()
    if _is_link_or_junction(lexical):
        raise RuntimeError(f"{label} must not be a symlink or junction")
    absolute = Path(os.path.abspath(lexical))
    try:
        resolved = lexical.resolve(strict=True)
    except (FileNotFoundError, OSError) as exc:
        raise RuntimeError(f"{label} does not exist") from exc
    if not resolved.is_dir():
        raise RuntimeError(f"{label} must be a directory")
    if os.path.normcase(str(absolute)) != os.path.normcase(str(resolved)):
        raise RuntimeError(f"{label} must not traverse a symlink or junction")
    return resolved


def _strict_json_object(raw: bytes, *, label: str) -> dict[str, Any]:
    def reject_duplicates(pairs):
        result: dict[str, Any] = {}
        for key, value in pairs:
            if key in result:
                raise ValueError(f"duplicate JSON key: {key}")
            result[key] = value
        return result

    try:
        value = json.loads(
            raw.decode("utf-8"),
            object_pairs_hook=reject_duplicates,
            parse_constant=lambda token: (_ for _ in ()).throw(
                ValueError(f"non-finite JSON number: {token}")
            ),
        )
    except (UnicodeDecodeError, ValueError, TypeError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"{label} is not strict JSON") from exc
    if not isinstance(value, dict):
        raise RuntimeError(f"{label} must be a JSON object")
    return value


def _strict_structure_equal(left: Any, right: Any) -> bool:
    """JSON equality that does not collapse ``1 == True`` or ``1 == 1.0``."""
    if type(left) is not type(right):
        return False
    if isinstance(left, dict):
        return (
            left.keys() == right.keys()
            and all(_strict_structure_equal(left[key], right[key]) for key in left)
        )
    if isinstance(left, list):
        return (
            len(left) == len(right)
            and all(_strict_structure_equal(a, b) for a, b in zip(left, right))
        )
    return left == right


def _tree_sha256(root: str | Path) -> str:
    """Hash every path, file type, and byte under a store without following links.

    The before/after stat comparison makes a concurrently changing file fail closed rather
    than producing an authorization context for a mixed snapshot.
    """
    root_path = _canonical_directory(root, label="store")
    digest = hashlib.sha256()
    pending: list[tuple[Path, str]] = [(root_path, "")]
    observed: list[tuple[Path, os.stat_result, str]] = []
    stable_fields = ("st_size", "st_mtime_ns", "st_dev", "st_ino")
    while pending:
        directory, relative_dir = pending.pop()
        try:
            directory_before = directory.stat()
            with os.scandir(directory) as iterator:
                entries = sorted(iterator, key=lambda entry: entry.name)
        except OSError as exc:
            raise RuntimeError("store tree could not be enumerated") from exc
        observed.append((directory, directory_before, relative_dir or "."))
        child_directories: list[tuple[Path, str]] = []
        for entry in entries:
            relative = (
                f"{relative_dir}/{entry.name}" if relative_dir else entry.name
            ).replace("\\", "/")
            entry_path = Path(entry.path)
            if entry.is_symlink() or _is_link_or_junction(entry_path):
                raise RuntimeError(f"store tree contains a link: {relative}")
            if entry.is_dir(follow_symlinks=False):
                digest.update(b"D\0")
                digest.update(relative.encode("utf-8"))
                digest.update(b"\0")
                child_directories.append((entry_path, relative))
                continue
            if not entry.is_file(follow_symlinks=False):
                raise RuntimeError(f"store tree contains a special file: {relative}")
            try:
                before = entry_path.lstat()
                digest.update(b"F\0")
                digest.update(relative.encode("utf-8"))
                digest.update(b"\0")
                digest.update(str(before.st_size).encode("ascii"))
                digest.update(b"\0")
                with entry_path.open("rb") as handle:
                    while True:
                        chunk = handle.read(1024 * 1024)
                        if not chunk:
                            break
                        digest.update(chunk)
                after = entry_path.lstat()
            except OSError as exc:
                raise RuntimeError(f"store file could not be hashed: {relative}") from exc
            if any(getattr(before, field, None) != getattr(after, field, None)
                   for field in stable_fields):
                raise RuntimeError(f"store file changed while hashing: {relative}")
            observed.append((entry_path, after, relative))
        # Reverse because this is a stack; the resulting traversal remains lexical.
        pending.extend(reversed(child_directories))
    for observed_path, before, relative in observed:
        try:
            after = observed_path.lstat()
        except OSError as exc:
            raise RuntimeError(f"store path disappeared while hashing: {relative}") from exc
        if any(getattr(before, field, None) != getattr(after, field, None)
               for field in stable_fields):
            raise RuntimeError(f"store path changed while hashing: {relative}")
    return digest.hexdigest()


def _canonical_path_string(path: Path, *, strict: bool = True) -> str:
    return os.path.normcase(str(path.resolve(strict=strict))).replace("\\", "/")


def _validated_staging_receipt(
    receipt_path: str | Path,
    *,
    candidate: Path,
    candidate_digest: str,
    verification_report_sha256: str,
    base_digest: str,
    mutation_batch_manifest_sha256: str,
) -> tuple[bytes, list[str], str]:
    """Validate the actual NightlyPromotionQueue receipt and its one bulk candidate."""
    try:
        resolved_receipt = Path(receipt_path).expanduser().resolve(strict=True)
        raw = resolved_receipt.read_bytes()
    except OSError as exc:
        raise RuntimeError("operator-confirmed staging receipt is unavailable") from exc
    receipt = _strict_json_object(raw, label="operator-confirmed staging receipt")
    expected_fields = frozenset(STAGING_RECEIPT_INVARIANTS) | {
        "batch_id",
        "confirmed_at",
        "operator_id",
        "operator_confirmed",
        "signed",
        "staging_allowed",
        "status",
        "attestation_level",
        "required_confirmation_phrase",
        "item_ids",
        "item_count",
        "entries",
        "note",
    }
    if frozenset(receipt) != expected_fields:
        raise RuntimeError("staging receipt schema fields do not match the queue contract")
    for field, expected in STAGING_RECEIPT_INVARIANTS.items():
        actual = receipt.get(field)
        if isinstance(expected, bool):
            valid = actual is expected
        else:
            valid = actual == expected
        if not valid:
            raise RuntimeError(f"staging receipt invariant invalid: {field}")
    literal_contract = {
        "operator_confirmed": True,
        "staging_allowed": True,
        "signed": False,
        "cryptographically_signed": False,
        "merge_authorized": False,
        "production_store_mutated": False,
        "shipped_graph_write": False,
        "rollback_required": True,
        "proof_only": True,
    }
    for field, expected in literal_contract.items():
        if receipt.get(field) is not expected:
            raise RuntimeError(f"staging receipt contract invalid: {field}")
    if receipt.get("status") != "operator_confirmed_staged":
        raise RuntimeError("staging receipt status is not operator-confirmed")
    if receipt.get("attestation_level") != "interactive_confirmation":
        raise RuntimeError("staging receipt attestation level is invalid")
    if receipt.get("required_confirmation_phrase") != REQUIRED_CONFIRMATION_PHRASE:
        raise RuntimeError("staging receipt confirmation phrase binding is invalid")

    item_ids = receipt.get("item_ids")
    entries = receipt.get("entries")
    if (
        not isinstance(item_ids, list)
        or len(item_ids) != 1
        or not isinstance(item_ids[0], str)
        or not item_ids[0]
        or len(item_ids[0]) > 256
        or not isinstance(receipt.get("item_count"), int)
        or isinstance(receipt.get("item_count"), bool)
        or receipt.get("item_count") != 1
        or not isinstance(entries, list)
        or len(entries) != 1
        or not isinstance(entries[0], dict)
    ):
        raise RuntimeError("staging receipt must bind exactly one valid promotion item")
    entry = entries[0]
    if (
        entry.get("item_id") != item_ids[0]
        or entry.get("production_store_mutated") is not False
        or entry.get("status") != "pending_operator_signature"
    ):
        raise RuntimeError("staging receipt entry contract is invalid")
    expected_payload = {
        "promotion_kind": "graph_store_candidate",
        "candidate_store_path": _canonical_path_string(candidate),
        "candidate_digest_sha256": candidate_digest,
        "mutation_batch_manifest_sha256": (
            mutation_batch_manifest_sha256
        ),
        "verification_report_sha256": verification_report_sha256,
        "target_store_id": SHIPPED_STORE_TARGET_ID,
        "base_revision": f"sha256:{base_digest}",
    }
    if entry.get("payload") != expected_payload:
        raise RuntimeError("staging receipt does not bind the current bulk-store candidate")
    operator_id = receipt.get("operator_id")
    if not isinstance(operator_id, str) or not operator_id.strip():
        raise RuntimeError("staging receipt operator id is invalid")
    batch_digest = hashlib.sha256(
        (
            json.dumps(
                tuple(entries),
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
                default=str,
            )
            + "::"
            + operator_id.strip()
        ).encode("utf-8")
    ).hexdigest()[:24]
    expected_batch_id = f"nightly_promotion_confirmed_{batch_digest}"
    if (
        receipt.get("batch_id") != expected_batch_id
        or resolved_receipt.name != f"{expected_batch_id}.json"
    ):
        raise RuntimeError("staging receipt batch identity or exclusive path is invalid")
    canonical_receipt_bytes = json.dumps(
        receipt,
        ensure_ascii=False,
        indent=2,
        sort_keys=True,
    ).encode("utf-8")
    if raw != canonical_receipt_bytes:
        raise RuntimeError("staging receipt bytes are not the queue's canonical format")
    return raw, item_ids, mutation_batch_manifest_sha256


def _validate_store_paths(kg_root: str | Path, merged_root: str | Path) -> tuple[Path, Path]:
    live = _canonical_directory(kg_root, label="live shipped store")
    approved = _canonical_directory(
        CANONICAL_SHIPPED_ROOT,
        label="canonical shipped store",
    )
    if live != approved:
        raise RuntimeError("live shipped path is not the canonical approved store")
    candidate = _validate_candidate_lane(
        live,
        merged_root,
        require_exists=True,
    )
    return live, candidate


def _validate_candidate_lane(
    shipped_root: str | Path,
    candidate_root: str | Path,
    *,
    require_exists: bool,
) -> Path:
    """Confine build/receipt writes to one exact sibling candidate lane."""
    live = _canonical_directory(shipped_root, label="shipped store")
    candidate_lexical = Path(candidate_root).expanduser()
    if _is_link_or_junction(candidate_lexical):
        raise RuntimeError("candidate store must not be a symlink or junction")
    candidate_absolute = Path(os.path.abspath(candidate_lexical))
    parent = _canonical_directory(
        candidate_absolute.parent,
        label="candidate parent",
    )
    if parent != live.parent:
        raise RuntimeError("candidate path is outside the approved staged-merge lane")
    if candidate_absolute == live:
        raise RuntimeError("candidate store must be distinct from the shipped store")
    prefix = f"{live.name}.staged_merge."
    if not candidate_absolute.name.startswith(prefix):
        raise RuntimeError("candidate path is outside the approved staged-merge lane")
    suffix = candidate_absolute.name[len(prefix):]
    if _CANDIDATE_SUFFIX_RE.fullmatch(suffix) is None:
        raise RuntimeError("candidate staged-merge name is not canonical")
    exists_or_link = candidate_absolute.exists() or _is_link_or_junction(
        candidate_absolute
    )
    if require_exists:
        if not exists_or_link:
            raise RuntimeError("candidate store does not exist")
        candidate = _canonical_directory(
            candidate_absolute,
            label="candidate store",
        )
    else:
        if exists_or_link:
            raise FileExistsError(
                f"{candidate_absolute} exists — refusing to overwrite a "
                "half-built merge; remove it explicitly first"
            )
        candidate = candidate_absolute
    if candidate == live:
        raise RuntimeError("candidate store must be distinct from the live store")
    if candidate.parent != live.parent:
        raise RuntimeError("candidate path is outside the approved staged-merge lane")
    return candidate


def _discard_sealed_snapshot(path: Path, *, approved_parent: Path) -> None:
    """Delete only the exact internal snapshot lane; never follow a replaced link."""
    if not path.exists() and not _is_link_or_junction(path):
        return
    if _is_link_or_junction(path):
        raise RuntimeError("sealed snapshot became a link; refusing recursive cleanup")
    resolved = path.resolve(strict=True)
    if resolved.parent != approved_parent:
        raise RuntimeError("sealed snapshot escaped the approved parent")
    shutil.rmtree(resolved)


def _canonical_json_bytes(value: Mapping[str, Any]) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


def _stable_stat_token(path: Path, *, kind: str, label: str) -> tuple[int, ...]:
    """Return a within-attempt identity token for one non-link filesystem node."""
    if _is_link_or_junction(path):
        raise RuntimeError(f"{label} must not be a symlink or junction")
    try:
        info = path.stat(follow_symlinks=False)
    except (FileNotFoundError, OSError) as exc:
        raise RuntimeError(f"{label} does not exist") from exc
    if kind == "file" and not stat.S_ISREG(info.st_mode):
        raise RuntimeError(f"{label} must be a regular file")
    if kind == "directory" and not stat.S_ISDIR(info.st_mode):
        raise RuntimeError(f"{label} must be a directory")
    identity = (
        int(info.st_dev),
        int(info.st_ino),
        int(info.st_mode),
    )
    if kind == "directory":
        # Claim creation legitimately changes directory size/mtime.  The
        # security-relevant within-attempt identity is the directory node.
        return identity
    return identity + (int(info.st_size), int(info.st_mtime_ns))


@dataclass(frozen=True)
class PromotionReplayDomain:
    """One pre-provisioned, externally protected nonce and lock domain.

    The signed binding combines an operator-provisioned identity manifest with
    the canonical resolved root.  Identity alone can be copied to another
    empty ledger; path alone cannot distinguish deletion/recreation.  This
    descriptor blocks the copied-ledger replay and detects within-attempt
    replacement.  Same-path replacement still requires an operator-owned ACL
    or remote append-only ledger to prevent.
    """

    root: Path
    ledger_id: str
    target_store_id: str
    resolved_root_sha256: str
    identity_manifest_sha256: str
    lock_path: Path
    claims_root: Path
    _root_token: tuple[int, ...]
    _identity_token: tuple[int, ...]
    _lock_token: tuple[int, ...]
    _claims_token: tuple[int, ...]
    _repository_root: Path

    @property
    def binding(self) -> dict[str, str]:
        return {
            "schema_version": NONCE_REPLAY_DOMAIN_SCHEMA_VERSION,
            "ledger_id": self.ledger_id,
            "target_store_id": self.target_store_id,
            "resolved_root_sha256": self.resolved_root_sha256,
            "identity_manifest_sha256": self.identity_manifest_sha256,
            "lock_relative_path": NONCE_LEDGER_LOCK_RELATIVE_PATH,
            "claims_relative_path": NONCE_LEDGER_CLAIMS_RELATIVE_PATH,
        }

    @property
    def binding_sha256(self) -> str:
        return hashlib.sha256(_canonical_json_bytes(self.binding)).hexdigest()

    @classmethod
    def from_external_directory(
        cls,
        path: str | Path,
        *,
        repository_root: str | Path,
        expected_ledger_id: str,
        target_store_id: str,
    ) -> "PromotionReplayDomain":
        if (
            not isinstance(expected_ledger_id, str)
            or _LEDGER_ID_RE.fullmatch(expected_ledger_id) is None
        ):
            raise RuntimeError(
                "an externally pinned canonical promotion ledger id is required"
            )
        if target_store_id != SHIPPED_STORE_TARGET_ID:
            raise RuntimeError("promotion replay domain target is not approved")
        ledger = _canonical_directory(path, label="nonce replay domain")
        repo = Path(repository_root).resolve(strict=True)
        try:
            ledger.relative_to(repo)
        except ValueError:
            pass
        else:
            raise RuntimeError(
                "nonce replay domain must be outside the mutable repository"
            )

        identity_path = ledger / NONCE_LEDGER_IDENTITY_FILENAME
        root_token = _stable_stat_token(
            ledger,
            kind="directory",
            label="nonce replay domain",
        )
        identity_before = _stable_stat_token(
            identity_path,
            kind="file",
            label="nonce replay identity manifest",
        )
        try:
            identity_raw = identity_path.read_bytes()
        except OSError as exc:
            raise RuntimeError(
                "nonce replay identity manifest could not be read"
            ) from exc
        identity_after = _stable_stat_token(
            identity_path,
            kind="file",
            label="nonce replay identity manifest",
        )
        if identity_before != identity_after:
            raise RuntimeError(
                "nonce replay identity manifest changed while being read"
            )
        identity = _strict_json_object(
            identity_raw,
            label="nonce replay identity manifest",
        )
        expected_fields = {
            "schema_version",
            "ledger_id",
            "target_store_id",
            "lock_relative_path",
            "claims_relative_path",
        }
        if set(identity) != expected_fields:
            raise RuntimeError(
                "nonce replay identity manifest fields are not exact"
            )
        if identity_raw != _canonical_json_bytes(identity):
            raise RuntimeError(
                "nonce replay identity manifest is not canonical JSON"
            )
        expected_identity = {
            "schema_version": NONCE_LEDGER_IDENTITY_SCHEMA_VERSION,
            "ledger_id": expected_ledger_id,
            "target_store_id": target_store_id,
            "lock_relative_path": NONCE_LEDGER_LOCK_RELATIVE_PATH,
            "claims_relative_path": NONCE_LEDGER_CLAIMS_RELATIVE_PATH,
        }
        if not _strict_structure_equal(identity, expected_identity):
            raise RuntimeError(
                "nonce replay identity does not match the external pin"
            )

        lock_path = ledger / NONCE_LEDGER_LOCK_RELATIVE_PATH
        claims_root = ledger / NONCE_LEDGER_CLAIMS_RELATIVE_PATH
        lock_token = _stable_stat_token(
            lock_path,
            kind="file",
            label="promotion lock",
        )
        if lock_path.stat().st_size < 1:
            raise RuntimeError("pre-provisioned promotion lock is empty")
        claims_token = _stable_stat_token(
            claims_root,
            kind="directory",
            label="promotion nonce claims directory",
        )
        resolved_root_sha256 = hashlib.sha256(
            b"atanor.promotion-nonce-ledger-root.v1\0"
            + str(ledger).encode("utf-8")
        ).hexdigest()
        return cls(
            root=ledger,
            ledger_id=expected_ledger_id,
            target_store_id=target_store_id,
            resolved_root_sha256=resolved_root_sha256,
            identity_manifest_sha256=hashlib.sha256(identity_raw).hexdigest(),
            lock_path=lock_path,
            claims_root=claims_root,
            _root_token=root_token,
            _identity_token=identity_after,
            _lock_token=lock_token,
            _claims_token=claims_token,
            _repository_root=repo,
        )

    def revalidate(self) -> None:
        fresh = type(self).from_external_directory(
            self.root,
            repository_root=self._repository_root,
            expected_ledger_id=self.ledger_id,
            target_store_id=self.target_store_id,
        )
        if (
            fresh.binding != self.binding
            or fresh._root_token != self._root_token
            or fresh._identity_token != self._identity_token
            or fresh._lock_token != self._lock_token
            or fresh._claims_token != self._claims_token
        ):
            raise RuntimeError(
                "nonce replay domain changed during the promotion attempt"
            )


def _canonical_regular_file(
    path: str | Path,
    *,
    label: str,
) -> tuple[Path, tuple[int, ...]]:
    lexical = Path(path).expanduser()
    if not lexical.is_absolute():
        raise RuntimeError(f"{label} path must be absolute")
    if _is_link_or_junction(lexical):
        raise RuntimeError(f"{label} must not be a symlink or junction")
    absolute = Path(os.path.abspath(lexical))
    try:
        resolved = lexical.resolve(strict=True)
    except (FileNotFoundError, OSError) as exc:
        raise RuntimeError(f"{label} does not exist") from exc
    if os.path.normcase(str(absolute)) != os.path.normcase(str(resolved)):
        raise RuntimeError(f"{label} must not traverse a symlink or junction")
    token = _stable_stat_token(resolved, kind="file", label=label)
    return resolved, token


@dataclass(frozen=True)
class ShippedGraphOperatorBoundary:
    """Fixed system-owned key, replay domain, and signed context binding."""

    config_path: Path
    boundary_id: str
    target_store_id: str
    config_sha256: str
    operator_key_path: Path
    operator_key_id: str
    trust_root: OperatorTrustRoot
    replay_domain: PromotionReplayDomain
    _config_token: tuple[int, ...]
    _operator_key_token: tuple[int, ...]

    @property
    def context_binding(self) -> dict[str, Any]:
        return {
            "operator_boundary_id": self.boundary_id,
            "operator_boundary_config_sha256": self.config_sha256,
            "nonce_replay_domain": self.replay_domain.binding,
        }

    def revalidate(self) -> None:
        fresh = load_system_shipped_graph_operator_boundary(
            repository_root=REPOSITORY_ROOT,
            expected_target_store_id=self.target_store_id,
        )
        if (
            fresh.config_path != self.config_path
            or fresh.boundary_id != self.boundary_id
            or fresh.config_sha256 != self.config_sha256
            or fresh.operator_key_path != self.operator_key_path
            or fresh.operator_key_id != self.operator_key_id
            or fresh.replay_domain.binding != self.replay_domain.binding
            or fresh._config_token != self._config_token
            or fresh._operator_key_token != self._operator_key_token
        ):
            raise RuntimeError(
                "system shipped-graph operator boundary changed during promotion"
            )
        self.replay_domain.revalidate()


def load_system_shipped_graph_operator_boundary(
    *,
    repository_root: str | Path,
    expected_target_store_id: str,
) -> ShippedGraphOperatorBoundary:
    """Load the one installation-fixed authority boundary.

    The path is intentionally not a parameter or environment variable.  Tests
    may monkeypatch the module constant; production callers cannot substitute
    a key, pin, or empty replay ledger through the CLI or StoreMerger API.
    """
    config_path, config_before = _canonical_regular_file(
        SYSTEM_SHIPPED_GRAPH_OPERATOR_BOUNDARY_CONFIG,
        label="system shipped-graph operator boundary config",
    )
    repo = Path(repository_root).resolve(strict=True)
    try:
        config_path.relative_to(repo)
    except ValueError:
        pass
    else:
        raise RuntimeError(
            "operator boundary config must be outside the mutable repository"
        )
    try:
        raw = config_path.read_bytes()
    except OSError as exc:
        raise RuntimeError("operator boundary config could not be read") from exc
    config_after = _stable_stat_token(
        config_path,
        kind="file",
        label="system shipped-graph operator boundary config",
    )
    if config_before != config_after:
        raise RuntimeError("operator boundary config changed while being read")
    config = _strict_json_object(raw, label="operator boundary config")
    expected_fields = {
        "schema_version",
        "boundary_id",
        "target_store_id",
        "operator_public_key_path",
        "operator_key_id",
        "nonce_ledger_path",
        "nonce_ledger_id",
    }
    if set(config) != expected_fields:
        raise RuntimeError("operator boundary config fields are not exact")
    if raw != _canonical_json_bytes(config):
        raise RuntimeError("operator boundary config is not canonical JSON")
    if config.get("schema_version") != OPERATOR_BOUNDARY_CONFIG_SCHEMA_VERSION:
        raise RuntimeError("operator boundary config schema is unsupported")
    boundary_id = config.get("boundary_id")
    if (
        not isinstance(boundary_id, str)
        or _BOUNDARY_ID_RE.fullmatch(boundary_id) is None
    ):
        raise RuntimeError("operator boundary id is invalid")
    if config.get("target_store_id") != expected_target_store_id:
        raise RuntimeError("operator boundary target is not approved")
    key_id = config.get("operator_key_id")
    if (
        not isinstance(key_id, str)
        or _OPERATOR_KEY_ID_RE.fullmatch(key_id) is None
    ):
        raise RuntimeError("operator key pin is invalid")
    key_path_raw = config.get("operator_public_key_path")
    ledger_path_raw = config.get("nonce_ledger_path")
    ledger_id = config.get("nonce_ledger_id")
    if not isinstance(key_path_raw, str) or not isinstance(
        ledger_path_raw,
        str,
    ):
        raise RuntimeError("operator boundary paths must be strings")

    key_path, key_token = _canonical_regular_file(
        key_path_raw,
        label="operator public key",
    )
    try:
        key_path.relative_to(repo)
    except ValueError:
        pass
    else:
        raise RuntimeError("operator public key must be outside the repository")
    trust_root = OperatorTrustRoot.from_external_file(
        key_path,
        repository_root=repo,
        expected_key_id=key_id,
    )
    replay_domain = PromotionReplayDomain.from_external_directory(
        ledger_path_raw,
        repository_root=repo,
        expected_ledger_id=ledger_id,
        target_store_id=expected_target_store_id,
    )
    return ShippedGraphOperatorBoundary(
        config_path=config_path,
        boundary_id=boundary_id,
        target_store_id=expected_target_store_id,
        config_sha256=hashlib.sha256(raw).hexdigest(),
        operator_key_path=key_path,
        operator_key_id=key_id,
        trust_root=trust_root,
        replay_domain=replay_domain,
        _config_token=config_after,
        _operator_key_token=key_token,
    )


@contextmanager
def _exclusive_promotion_lock(
    replay_domain: PromotionReplayDomain,
) -> Iterator[None]:
    """Serialize distinct signed nonces across threads and cooperating processes."""
    if not isinstance(replay_domain, PromotionReplayDomain):
        raise RuntimeError("resolved promotion replay domain is required")
    replay_domain.revalidate()
    if not _LOCAL_PROMOTION_LOCK.acquire(blocking=False):
        raise RuntimeError("another shipped-store promotion is already in progress")
    handle = None
    try:
        flags = os.O_RDWR
        if hasattr(os, "O_BINARY"):
            flags |= os.O_BINARY
        if hasattr(os, "O_NOFOLLOW"):
            flags |= os.O_NOFOLLOW
        try:
            descriptor = os.open(replay_domain.lock_path, flags)
        except OSError as exc:
            raise RuntimeError(
                "pre-provisioned promotion lock could not be opened"
            ) from exc
        info = os.fstat(descriptor)
        descriptor_token = (
            int(info.st_dev),
            int(info.st_ino),
            int(info.st_mode),
            int(info.st_size),
            int(info.st_mtime_ns),
        )
        if (
            not stat.S_ISREG(info.st_mode)
            or descriptor_token != replay_domain._lock_token
        ):
            os.close(descriptor)
            raise RuntimeError("promotion lock identity changed")
        handle = os.fdopen(descriptor, "r+b", closefd=True)
        handle.seek(0)
        try:
            if os.name == "nt":
                import msvcrt

                msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl

                fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as exc:
            raise RuntimeError(
                "another shipped-store promotion holds the external lock"
            ) from exc
        try:
            replay_domain.revalidate()
            yield
        finally:
            handle.seek(0)
            if os.name == "nt":
                import msvcrt

                msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                import fcntl

                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
    finally:
        try:
            if handle is not None:
                handle.close()
        finally:
            _LOCAL_PROMOTION_LOCK.release()


def _consume_promotion_nonce(
    replay_domain: PromotionReplayDomain,
    *,
    document: Mapping[str, Any],
    verification_payload_sha256: str,
    context: Mapping[str, Any],
    previous: Path,
    sealed: Path,
    transaction_id: str,
    intent_sha256: str,
    prepared_event_sha256: str,
) -> Path:
    """Atomically and durably record one nonce before the first rename."""
    replay_domain.revalidate()
    nonce = document.get("nonce")
    if not isinstance(nonce, str):
        raise RuntimeError("verified promotion nonce is missing")
    nonce_name = hashlib.sha256(nonce.encode("utf-8")).hexdigest() + ".consumed.json"
    receipt_path = replay_domain.claims_root / nonce_name
    receipt = {
        "schema_version": "atanor.promotion-nonce-consumption.v3",
        "nonce": nonce,
        "ledger_id": replay_domain.ledger_id,
        "nonce_replay_domain_sha256": replay_domain.binding_sha256,
        "transaction_id": transaction_id,
        "swap_intent_sha256": intent_sha256,
        "prepared_event_sha256": prepared_event_sha256,
        "promotion_payload_sha256": verification_payload_sha256,
        "candidate_digest_sha256": context["candidate_digest_sha256"],
        "mutation_batch_manifest_sha256": context[
            "mutation_batch_manifest_sha256"
        ],
        "base_revision": context["base_revision"],
        "target_store_id": context["target_store_id"],
        "planned_backup_path": _canonical_path_string(previous, strict=False),
        "planned_sealed_snapshot_path": _canonical_path_string(sealed),
        "consumed_at_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }
    encoded = json.dumps(
        receipt,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    flags = os.O_CREAT | os.O_EXCL | os.O_WRONLY
    if hasattr(os, "O_BINARY"):
        flags |= os.O_BINARY
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    try:
        descriptor = os.open(receipt_path, flags, 0o600)
    except FileExistsError as exc:
        raise RuntimeError("promotion nonce was already consumed") from exc
    except OSError as exc:
        raise RuntimeError("promotion nonce could not be consumed") from exc
    try:
        with os.fdopen(descriptor, "wb", closefd=True) as handle:
            handle.write(encoded)
            handle.flush()
            os.fsync(handle.fileno())
    except Exception as exc:
        # A possibly-created receipt remains a consumed nonce. Never unlink it and accidentally
        # reopen replay after an uncertain persistence result.
        raise RuntimeError("promotion nonce receipt could not be made durable") from exc
    if os.name != "nt":
        try:
            directory_fd = os.open(replay_domain.claims_root, os.O_RDONLY)
            try:
                os.fsync(directory_fd)
            finally:
                os.close(directory_fd)
        except OSError as exc:
            raise RuntimeError("promotion nonce directory could not be synced") from exc
    return receipt_path


def _sync_directory(path: Path) -> bool:
    """Persist directory entries where Python exposes a verified primitive.

    POSIX directory fsync is required and failures abort.  Python on Windows
    does not expose a demonstrated directory-handle flush here, so callers
    record ``False`` and keep the production crash-durability gate open.
    """
    if os.name == "nt":
        return False
    flags = os.O_RDONLY
    if hasattr(os, "O_DIRECTORY"):
        flags |= os.O_DIRECTORY
    try:
        descriptor = os.open(path, flags)
        try:
            os.fsync(descriptor)
        finally:
            os.close(descriptor)
    except OSError as exc:
        raise RuntimeError(f"directory could not be synced: {path}") from exc
    return True


def _sync_tree_files(root: Path) -> dict[str, Any]:
    """fsync every sealed regular file and, on POSIX, directories bottom-up."""
    canonical = _canonical_directory(root, label="sealed candidate")
    directories: list[Path] = []
    files_synced = 0
    for directory, child_dirs, child_files in os.walk(canonical, topdown=True):
        directory_path = Path(directory)
        directories.append(directory_path)
        for name in tuple(child_dirs) + tuple(child_files):
            child = directory_path / name
            if _is_link_or_junction(child):
                raise RuntimeError("sealed candidate contains a link")
        for name in child_files:
            child = directory_path / name
            info = child.stat(follow_symlinks=False)
            if not stat.S_ISREG(info.st_mode):
                raise RuntimeError("sealed candidate contains a special file")
            # Windows' os.fsync/_commit rejects a read-only descriptor.
            # The sealed copy is private to the promoter, so open read-write
            # solely to flush existing bytes; no content is modified.
            with child.open("r+b") as handle:
                os.fsync(handle.fileno())
            files_synced += 1
    directory_sync = True
    for directory in reversed(directories):
        directory_sync = _sync_directory(directory) and directory_sync
    parent_sync = _sync_directory(canonical.parent)
    return {
        "regular_files_synced": files_synced,
        "directory_entries_synced": directory_sync and parent_sync,
        "platform_directory_sync_verified": os.name != "nt",
    }


def _write_exclusive_json(
    path: Path,
    value: Mapping[str, Any],
) -> tuple[str, bool]:
    encoded = _canonical_json_bytes(value)
    flags = os.O_CREAT | os.O_EXCL | os.O_WRONLY
    if hasattr(os, "O_BINARY"):
        flags |= os.O_BINARY
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    try:
        descriptor = os.open(path, flags, 0o600)
    except FileExistsError as exc:
        raise RuntimeError(f"append-only journal entry already exists: {path.name}") from exc
    except OSError as exc:
        raise RuntimeError(f"append-only journal entry could not be created: {path}") from exc
    try:
        with os.fdopen(descriptor, "wb", closefd=True) as handle:
            handle.write(encoded)
            handle.flush()
            os.fsync(handle.fileno())
    except Exception as exc:
        raise RuntimeError(f"append-only journal entry could not be synced: {path}") from exc
    return hashlib.sha256(encoded).hexdigest(), _sync_directory(path.parent)


def _swap_path_state(path: Path) -> dict[str, Any]:
    if not path.exists() and not _is_link_or_junction(path):
        return {"state": "absent", "sha256": None, "identity": None}
    if _is_link_or_junction(path):
        raise RuntimeError("swap state path became a link or junction")
    canonical = _canonical_directory(path, label="swap state directory")
    info = canonical.stat()
    return {
        "state": "directory",
        "sha256": _tree_sha256(canonical),
        "identity": {
            "device": int(info.st_dev),
            "inode": int(info.st_ino),
        },
    }


@dataclass
class SwapJournal:
    """Append-only evidence for diagnosing a two-rename promotion."""

    transaction_root: Path
    transaction_id: str
    intent_sha256: str
    last_event_sha256: str | None = None
    sequence: int = 0
    namespace_directory_sync_verified: bool = True

    @classmethod
    def prepare(
        cls,
        *,
        replay_domain: PromotionReplayDomain,
        transaction_id: str,
        promotion_document: Mapping[str, Any],
        promotion_payload_sha256: str,
        operator_key_id: str,
        context: Mapping[str, Any],
        live: Path,
        candidate: Path,
        sealed: Path,
        previous: Path,
        sealed_sync: Mapping[str, Any],
    ) -> "SwapJournal":
        transactions_root = replay_domain.claims_root / "transactions"
        if _is_link_or_junction(transactions_root):
            raise RuntimeError("swap transaction root must not be a link")
        transactions_root.mkdir(mode=0o700, exist_ok=True)
        if not transactions_root.is_dir():
            raise RuntimeError("swap transaction root is not a directory")
        root_sync = _sync_directory(transactions_root.parent)
        transaction_root = transactions_root / transaction_id
        try:
            transaction_root.mkdir(mode=0o700)
        except FileExistsError as exc:
            nonce = promotion_document.get("nonce")
            nonce_name = (
                hashlib.sha256(str(nonce).encode("utf-8")).hexdigest()
                + ".consumed.json"
            )
            if (replay_domain.claims_root / nonce_name).exists():
                raise RuntimeError("promotion nonce was already consumed") from exc
            raise RuntimeError(
                "an incomplete swap transaction already exists"
            ) from exc
        tx_parent_sync = _sync_directory(transactions_root)
        full_document_sha256, document_dir_sync = _write_exclusive_json(
            transaction_root / "promotion_document.json",
            promotion_document,
        )
        nonce = promotion_document.get("nonce")
        intent = {
            "schema_version": "atanor.shipped-store-swap-intent.v2",
            "transaction_id": transaction_id,
            "target_store_id": context["target_store_id"],
            "replay_domain_sha256": replay_domain.binding_sha256,
            "promotion_payload_sha256": promotion_payload_sha256,
            "promotion_document_sha256": full_document_sha256,
            "operator_key_id": operator_key_id,
            "nonce_sha256": hashlib.sha256(
                str(nonce).encode("utf-8")
            ).hexdigest(),
            "live_path": _canonical_path_string(live),
            "candidate_source_path": _canonical_path_string(candidate),
            "sealed_path": _canonical_path_string(sealed),
            "previous_path": _canonical_path_string(previous, strict=False),
            "authorized_candidate_sha256": context[
                "candidate_digest_sha256"
            ],
            "mutation_batch_manifest_sha256": context[
                "mutation_batch_manifest_sha256"
            ],
            "authorized_base_sha256": context[
                "rollback_artifact_sha256"
            ],
            "staging_receipt_sha256": context[
                "staging_receipt_sha256"
            ],
            "recovery_policy": "observe_only_no_automatic_rename_v1",
            "sealed_sync": dict(sealed_sync),
            "created_at_utc": time.strftime(
                "%Y-%m-%dT%H:%M:%SZ",
                time.gmtime(),
            ),
        }
        intent_sha256, intent_dir_sync = _write_exclusive_json(
            transaction_root / "intent.json",
            intent,
        )
        journal = cls(
            transaction_root=transaction_root,
            transaction_id=transaction_id,
            intent_sha256=intent_sha256,
            namespace_directory_sync_verified=all(
                (
                    root_sync,
                    tx_parent_sync,
                    document_dir_sync,
                    intent_dir_sync,
                    bool(
                        sealed_sync.get(
                            "directory_entries_synced",
                            False,
                        )
                    ),
                )
            ),
        )
        journal.record(
            "PREPARED",
            live=live,
            sealed=sealed,
            previous=previous,
            nonce_receipt_sha256=None,
        )
        return journal

    def record(
        self,
        phase: str,
        *,
        live: Path,
        sealed: Path,
        previous: Path,
        nonce_receipt_sha256: str | None,
    ) -> str:
        self.sequence += 1
        event = {
            "schema_version": "atanor.shipped-store-swap-event.v1",
            "transaction_id": self.transaction_id,
            "sequence": self.sequence,
            "phase": phase,
            "intent_sha256": self.intent_sha256,
            "previous_event_sha256": self.last_event_sha256,
            "nonce_receipt_sha256": nonce_receipt_sha256,
            "observed_at_utc": time.strftime(
                "%Y-%m-%dT%H:%M:%SZ",
                time.gmtime(),
            ),
            "observed_at_unix_ns": time.time_ns(),
            "live": _swap_path_state(live),
            "sealed": _swap_path_state(sealed),
            "previous": _swap_path_state(previous),
            "namespace_directory_sync_verified": (
                self.namespace_directory_sync_verified
            ),
        }
        filename = f"{self.sequence:06d}.{phase}.json"
        digest, directory_synced = _write_exclusive_json(
            self.transaction_root / filename,
            event,
        )
        self.namespace_directory_sync_verified = (
            self.namespace_directory_sync_verified and directory_synced
        )
        self.last_event_sha256 = digest
        return digest


_SWAP_EVENT_FILE_RE = re.compile(
    r"^(?P<sequence>\d{6})\.(?P<phase>[A-Z_]+)\.json$"
)
_SWAP_EVENT_FIELDS = frozenset(
    {
        "schema_version",
        "transaction_id",
        "sequence",
        "phase",
        "intent_sha256",
        "previous_event_sha256",
        "nonce_receipt_sha256",
        "observed_at_utc",
        "observed_at_unix_ns",
        "live",
        "sealed",
        "previous",
        "namespace_directory_sync_verified",
    }
)
_LEGACY_SWAP_INTENT_FIELDS = frozenset(
    {
        "schema_version",
        "transaction_id",
        "target_store_id",
        "replay_domain_sha256",
        "promotion_payload_sha256",
        "promotion_document_sha256",
        "operator_key_id",
        "nonce_sha256",
        "live_path",
        "candidate_source_path",
        "sealed_path",
        "previous_path",
        "authorized_candidate_sha256",
        "authorized_base_sha256",
        "staging_receipt_sha256",
        "recovery_policy",
        "sealed_sync",
        "created_at_utc",
    }
)
_SWAP_INTENT_FIELDS = _LEGACY_SWAP_INTENT_FIELDS | {
    "mutation_batch_manifest_sha256"
}
_SWAP_PHASE_TRANSITIONS = {
    None: frozenset({"PREPARED"}),
    "PREPARED": frozenset({"NONCE_CLAIMED"}),
    "NONCE_CLAIMED": frozenset({"ARMED"}),
    "ARMED": frozenset(
        {"OLD_MOVED", "ABORTED_NONCE_BURNED", "RECOVERY_REQUIRED"}
    ),
    "OLD_MOVED": frozenset(
        {
            "INSTALLED_NAMESPACE_DURABLE",
            "INSTALLED_NAMESPACE_OBSERVED",
            "ABORTED_NONCE_BURNED",
            "RECOVERY_REQUIRED",
        }
    ),
    "INSTALLED_NAMESPACE_DURABLE": frozenset({"COMMITTED"}),
    "INSTALLED_NAMESPACE_OBSERVED": frozenset({"COMMITTED"}),
    "COMMITTED": frozenset(),
    "ABORTED_NONCE_BURNED": frozenset(),
    "RECOVERY_REQUIRED": frozenset(),
}
_TERMINAL_SWAP_PHASES = frozenset(
    {"COMMITTED", "ABORTED_NONCE_BURNED"}
)


def _validate_recorded_swap_path_state(
    value: Any,
    *,
    label: str,
) -> None:
    if type(value) is not dict or set(value) != {
        "state",
        "sha256",
        "identity",
    }:
        raise RuntimeError(f"{label} has invalid fields")
    state = value.get("state")
    if state == "absent":
        if value.get("sha256") is not None or value.get("identity") is not None:
            raise RuntimeError(f"{label} absent state is inconsistent")
        return
    if state != "directory":
        raise RuntimeError(f"{label} state is invalid")
    digest = value.get("sha256")
    identity = value.get("identity")
    if (
        not isinstance(digest, str)
        or re.fullmatch(r"[0-9a-f]{64}", digest) is None
        or type(identity) is not dict
        or set(identity) != {"device", "inode"}
        or any(
            not isinstance(identity.get(field), int)
            or isinstance(identity.get(field), bool)
            or identity.get(field) < 0
            for field in ("device", "inode")
        )
    ):
        raise RuntimeError(f"{label} directory state is malformed")


def _assert_no_unresolved_swap_transactions(
    replay_domain: PromotionReplayDomain,
    *,
    live: Path,
) -> None:
    """Refuse a new promotion while an append-only journal needs recovery."""
    transactions_root = replay_domain.claims_root / "transactions"
    if not transactions_root.exists():
        return
    if _is_link_or_junction(transactions_root) or not transactions_root.is_dir():
        raise RuntimeError("swap transaction journal root is invalid")
    committed: list[tuple[int, str]] = []
    for transaction_root in sorted(transactions_root.iterdir()):
        if (
            _is_link_or_junction(transaction_root)
            or not transaction_root.is_dir()
            or re.fullmatch(r"[0-9a-f]{64}", transaction_root.name) is None
        ):
            raise RuntimeError("swap transaction journal contains an invalid entry")
        previous_digest: str | None = None
        previous_phase: str | None = None
        last_event: dict[str, Any] | None = None
        event_paths = [
            path
            for path in sorted(transaction_root.iterdir())
            if _SWAP_EVENT_FILE_RE.fullmatch(path.name)
        ]
        for expected_sequence, event_path in enumerate(event_paths, start=1):
            match = _SWAP_EVENT_FILE_RE.fullmatch(event_path.name)
            assert match is not None
            if int(match.group("sequence")) != expected_sequence:
                raise RuntimeError("swap transaction journal sequence is broken")
            raw = event_path.read_bytes()
            event = _strict_json_object(raw, label="swap transaction event")
            if raw != _canonical_json_bytes(event):
                raise RuntimeError("swap transaction event is not canonical JSON")
            phase = event.get("phase")
            if (
                set(event) != _SWAP_EVENT_FIELDS
                or event.get("schema_version")
                != "atanor.shipped-store-swap-event.v1"
                or event.get("transaction_id") != transaction_root.name
                or event.get("sequence") != expected_sequence
                or phase != match.group("phase")
                or event.get("previous_event_sha256") != previous_digest
                or not isinstance(phase, str)
                or phase not in _SWAP_PHASE_TRANSITIONS.get(
                    previous_phase,
                    frozenset(),
                )
                or not isinstance(event.get("observed_at_utc"), str)
                or not isinstance(event.get("observed_at_unix_ns"), int)
                or isinstance(event.get("observed_at_unix_ns"), bool)
                or event.get("observed_at_unix_ns") < 0
                or type(event.get("namespace_directory_sync_verified"))
                is not bool
            ):
                raise RuntimeError("swap transaction journal chain is invalid")
            for state_name in ("live", "sealed", "previous"):
                _validate_recorded_swap_path_state(
                    event.get(state_name),
                    label=f"swap event {state_name}",
                )
            previous_digest = hashlib.sha256(raw).hexdigest()
            previous_phase = phase
            last_event = event
        if (
            last_event is None
            or last_event.get("phase") not in _TERMINAL_SWAP_PHASES
        ):
            raise RuntimeError(
                "unresolved shipped-store swap transaction requires "
                f"external recovery: {transaction_root}"
            )
        if last_event.get("phase") == "COMMITTED":
            intent_path = transaction_root / "intent.json"
            raw_intent = intent_path.read_bytes()
            intent = _strict_json_object(
                raw_intent,
                label="swap transaction intent",
            )
            document_path = transaction_root / "promotion_document.json"
            raw_document = document_path.read_bytes()
            document = _strict_json_object(
                raw_document,
                label="swap promotion document",
            )
            intent_schema = intent.get("schema_version")
            expected_intent_fields = (
                _LEGACY_SWAP_INTENT_FIELDS
                if intent_schema
                == "atanor.shipped-store-swap-intent.v1"
                else _SWAP_INTENT_FIELDS
            )
            if (
                set(intent) != expected_intent_fields
                or intent_schema
                not in {
                    "atanor.shipped-store-swap-intent.v1",
                    "atanor.shipped-store-swap-intent.v2",
                }
                or raw_intent != _canonical_json_bytes(intent)
                or hashlib.sha256(raw_intent).hexdigest()
                != last_event.get("intent_sha256")
                or intent.get("transaction_id") != transaction_root.name
                or raw_document != _canonical_json_bytes(document)
                or hashlib.sha256(raw_document).hexdigest()
                != intent.get("promotion_document_sha256")
                or (
                    (
                        "mutation_batch_manifest_sha256"
                        in document
                    )
                    != (
                        intent_schema
                        == "atanor.shipped-store-swap-intent.v2"
                    )
                )
                or (
                    intent_schema
                    == "atanor.shipped-store-swap-intent.v2"
                    and (
                        not isinstance(
                            intent.get(
                                "mutation_batch_manifest_sha256"
                            ),
                            str,
                        )
                        or re.fullmatch(
                            r"[0-9a-f]{64}",
                            intent.get(
                                "mutation_batch_manifest_sha256"
                            ),
                        )
                        is None
                        or intent.get(
                            "mutation_batch_manifest_sha256"
                        )
                        != document.get(
                            "mutation_batch_manifest_sha256"
                        )
                    )
                )
            ):
                raise RuntimeError("committed swap intent is invalid")
            observed_ns = last_event.get("observed_at_unix_ns")
            candidate_digest = intent.get("authorized_candidate_sha256")
            if (
                not isinstance(observed_ns, int)
                or isinstance(observed_ns, bool)
                or not isinstance(candidate_digest, str)
            ):
                raise RuntimeError("committed swap event is malformed")
            committed.append((observed_ns, candidate_digest))
    if committed:
        latest = max(committed, key=lambda item: item[0])
        if _tree_sha256(live) != latest[1]:
            raise RuntimeError(
                "canonical shipped store differs from the latest committed "
                "swap journal"
            )


def _candidate_promotion_material(
    kg_root: str | Path,
    merged_root: str | Path,
) -> dict[str, Any]:
    """Fresh, read-only material shared by queue staging and signature context."""
    live, candidate = _validate_store_paths(kg_root, merged_root)
    report_path = candidate / "VERIFY_REPORT.json"
    try:
        report_raw = report_path.read_bytes()
    except OSError as exc:
        raise RuntimeError(
            "candidate has no readable VERIFY_REPORT.json; run verify() first"
        ) from exc
    persisted = _strict_json_object(
        report_raw,
        label="candidate VERIFY_REPORT.json",
    )
    evaluated = StoreMerger(live, live)._evaluate_verification(candidate)
    mutation_batch_manifest_sha256 = evaluated.get(
        "mutation_batch_manifest_sha256"
    )
    if (
        not _strict_structure_equal(persisted, evaluated)
        or persisted.get("ok") is not True
        or evaluated.get("ok") is not True
        or not isinstance(mutation_batch_manifest_sha256, str)
        or re.fullmatch(
            r"[0-9a-f]{64}",
            mutation_batch_manifest_sha256,
        )
        is None
    ):
        raise RuntimeError(
            "candidate verification receipt does not match a fresh passing "
            "evaluation of the mutation batch"
        )
    candidate_digest = _tree_sha256(candidate)
    base_digest = _tree_sha256(live)
    try:
        report_after = report_path.read_bytes()
    except OSError as exc:
        raise RuntimeError("candidate verification receipt changed during preflight") from exc
    if report_after != report_raw:
        raise RuntimeError("candidate verification receipt changed during preflight")
    return {
        "live": live,
        "candidate": candidate,
        "report_raw": report_raw,
        "candidate_digest": candidate_digest,
        "base_digest": base_digest,
        "mutation_batch_manifest_sha256": (
            mutation_batch_manifest_sha256
        ),
    }


# ----------------------------------------------------------------------------------------
# term id <-> (shard, rowid) math (identical to ShardedTermDict, reproduced so this module
# never has to instantiate a writable dict just to decode)
# ----------------------------------------------------------------------------------------
def shard_of(term: str, n: int = SHARD_N) -> int:
    return zlib.crc32(term.encode("utf-8")) % n


def gid_of(rowid: int, shard: int, n: int = SHARD_N) -> int:
    return (rowid - 1) * n + shard


def rowid_shard_of(gid: int, n: int = SHARD_N) -> tuple[int, int]:
    return (gid // n + 1, gid % n)


# ----------------------------------------------------------------------------------------
# read-only store view (never opens a writable handle on the store it is pointed at)
# ----------------------------------------------------------------------------------------
class ReadOnlyStore:
    """Read-only view of a columnar triple store. Term shards are opened ``mode=ro`` and the
    columns as read-only memmaps, so a ReadOnlyStore CANNOT mutate the store — the same
    guarantee measure_r2_density_lift.py relies on. Supports both the sharded and the RAM
    (terms.txt) term-dict backends."""

    def __init__(self, root: str | Path):
        self.root = Path(root)
        self.meta = {}
        mp = self.root / "meta.json"
        if mp.exists():
            try:
                self.meta = json.loads(mp.read_text(encoding="utf-8"))
            except Exception:
                self.meta = {}
        self.backend = self.meta.get("dict_backend") or (
            "sharded" if (self.root / "term_shards").exists() else "ram")
        self._conns: list[sqlite3.Connection] = []
        self._ram_terms: list[str] = []
        self._ram_id: dict[str, int] = {}
        if self.backend == "sharded":
            for i in range(SHARD_N):
                p = self.root / "term_shards" / f"terms_{i:02d}.db"
                uri = f"file:{p.as_posix()}?mode=ro"
                self._conns.append(sqlite3.connect(uri, uri=True, check_same_thread=False))
        else:
            tp = self.root / "terms.txt"
            if tp.exists():
                self._ram_terms = [ln.rstrip("\n") for ln in tp.open(encoding="utf-8")]
                self._ram_id = {t: i for i, t in enumerate(self._ram_terms)}

    # ---- columns --------------------------------------------------------------
    def col(self, name: str) -> np.ndarray:
        """Load a column fully into RAM via np.fromfile. Deliberately NOT a memmap: a memmap
        keeps an OS file handle open, which on Windows blocks the rename/rmtree the promoter
        relies on for its atomic swap and half-build cleanup. At S1 scale a column is
        ~148MB (37M x <i4), which the promoter needs resident anyway."""
        p = self.root / f"{name}.col"
        if not p.exists():
            return np.zeros(0, dtype="<i4")
        return np.fromfile(str(p), dtype="<i4")

    @property
    def n_edges(self) -> int:
        p = self.root / "s.col"
        return (p.stat().st_size // 4) if p.exists() else 0

    @property
    def n_terms(self) -> int:
        if self.backend == "sharded":
            return sum(c.execute("SELECT COUNT(*) FROM t").fetchone()[0] for c in self._conns)
        return len(self._ram_terms)

    # ---- dictionary -----------------------------------------------------------
    def lookup(self, term: str) -> int | None:
        if self.backend != "sharded":
            return self._ram_id.get(term)
        sh = shard_of(term)
        r = self._conns[sh].execute("SELECT rowid FROM t WHERE term=?", (term,)).fetchone()
        return gid_of(r[0], sh) if r else None

    def term(self, gid: int) -> str:
        if gid is None or gid < 0:
            return ""
        if self.backend != "sharded":
            return self._ram_terms[gid] if 0 <= gid < len(self._ram_terms) else ""
        rowid, sh = rowid_shard_of(gid)
        r = self._conns[sh].execute("SELECT term FROM t WHERE rowid=?", (rowid,)).fetchone()
        return r[0] if r else ""

    def iter_terms(self) -> Iterator[tuple[int, str]]:
        """Yield (gid, term) for every term in the dictionary (one full pass)."""
        if self.backend != "sharded":
            for i, t in enumerate(self._ram_terms):
                yield i, t
            return
        for sh, c in enumerate(self._conns):
            for rowid, t in c.execute("SELECT rowid, term FROM t"):
                yield gid_of(rowid, sh), t

    def source_lines(self) -> list[str]:
        p = self.root / "sources.txt"
        base = ["curated:legacy|"]
        if p.exists():
            lines = [ln.rstrip("\n") for ln in p.open(encoding="utf-8") if ln.strip()]
            if lines:
                return lines
        return base

    # ---- predicate distribution ----------------------------------------------
    def predicate_counts(self) -> Counter:
        """{predicate_string: edge_count} over the whole store (one p.col pass)."""
        p = self.col("p")
        out: Counter = Counter()
        if not len(p):
            return out
        vals, counts = np.unique(p, return_counts=True)
        for gid, c in zip(vals.tolist(), counts.tolist()):
            out[self.term(int(gid))] = int(c)
        return out

    def pid(self, predicate: str) -> int | None:
        return self.lookup(predicate)

    def close(self) -> None:
        for c in self._conns:
            try:
                c.close()
            except Exception:
                pass


# ----------------------------------------------------------------------------------------
# completeness guard — is a staged store safe to read/promote, or still mid-write?
# ----------------------------------------------------------------------------------------
def store_completeness(root: str | Path) -> tuple[bool, dict]:
    """A staged store is COMPLETE (safe to promote) iff meta.json exists with count>0 AND the
    s/p/o(/src) columns all have the SAME number of rows AND that equals meta.count. A store
    still being written by an ingest shows the mismatch signature (meta count ahead of the
    columns, or unequal columns mid-flush) — see the b1_wikidata staging store observed
    2026-07-23 with meta.count=37,000,000 but 36,000,000 column rows. This is the machine
    check the promoter runs before it will touch anything; the operator additionally asserts
    completion out-of-band (S1 finished + engine stopped)."""
    root = Path(root)
    det: dict = {"root": str(root)}
    literal_manifest: dict | None = None
    partial_literal = root / "S1_WIKIDATA_LITERAL_PARTIAL.json"
    if partial_literal.exists():
        return False, {**det, "reason": "literal staging manifest declares a partial input scope"}
    for manifest_name in ("S1_WIKIDATA_LITERAL_MANIFEST.json", "B1_WIKIDATA_MANIFEST.json"):
        manifest_path = root / manifest_name
        if not manifest_path.exists():
            continue
        try:
            stage_manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        except Exception as e:
            return False, {**det, "reason": f"{manifest_name} unreadable: {e}"}
        det["stage_manifest"] = manifest_name
        det["completion_state"] = stage_manifest.get("completion_state")
        if manifest_name.startswith("S1_"):
            literal_manifest = stage_manifest
        if manifest_name.startswith("S1_") and stage_manifest.get("completion_state") != "complete":
            return False, {**det, "reason": "literal staging manifest is not strictly complete"}
        if not manifest_name.startswith("S1_") \
                and stage_manifest.get("completion_state") not in (None, "complete"):
            return False, {**det, "reason": "staging manifest is not complete"}
        if manifest_name.startswith("S1_") and stage_manifest.get("promotion_eligible") is not True:
            return False, {**det, "reason": "literal staging manifest is not promotion eligible"}
    literal_evidence = root / "qid_pid.col"
    if literal_manifest is None and literal_evidence.exists():
        return False, {
            **det,
            "reason": "literal QID/PID evidence sidecar is present without a literal manifest",
        }
    mp = root / "meta.json"
    if not mp.exists():
        return False, {**det, "reason": "no meta.json"}
    try:
        meta = json.loads(mp.read_text(encoding="utf-8"))
    except Exception as e:
        return False, {**det, "reason": f"meta.json unreadable: {e}"}
    count = int(meta.get("count") or 0)
    det["meta_count"] = count
    rows = {}
    for name in ("s", "p", "o", "src"):
        p = root / f"{name}.col"
        rows[name] = (p.stat().st_size // 4) if p.exists() else 0
    det["col_rows"] = rows
    if count <= 0:
        return False, {**det, "reason": "meta count is 0/absent"}
    core = [rows["s"], rows["p"], rows["o"]]
    if len(set(core)) != 1:
        return False, {**det, "reason": "s/p/o columns have unequal length (mid-write)"}
    if rows["src"] not in (0, rows["s"]):
        return False, {**det, "reason": "src.col length != s.col length (mid-write)"}
    if rows["s"] != count:
        return False, {**det, "reason": f"meta count {count} != column rows {rows['s']} (mid-write)"}
    if literal_manifest is not None:
        if rows["src"] != count:
            return False, {**det, "reason": "literal src.col must contain one source id per edge"}
        evidence = literal_evidence
        if not evidence.is_file():
            return False, {**det, "reason": "literal QID/PID evidence sidecar is missing"}
        evidence_bytes = evidence.stat().st_size
        if evidence_bytes % 12:
            return False, {**det, "reason": "literal QID/PID evidence sidecar is torn"}
        evidence_rows = evidence_bytes // 12
        declared = literal_manifest.get("qid_pid_sidecar")
        det["qid_pid_rows"] = evidence_rows
        if evidence_rows != count:
            return False, {**det, "reason": "literal QID/PID evidence rows != staged edge count"}
        if not isinstance(declared, dict) or declared.get("record_bytes") != 12 \
                or declared.get("records") != count or declared.get("path") != "qid_pid.col":
            return False, {**det, "reason": "literal QID/PID manifest declaration is inconsistent"}
    det["n_edges"] = rows["s"]
    return True, {**det, "reason": "complete"}


# ----------------------------------------------------------------------------------------
# English-only scan (owner directive: the staged EN store must be Hangul-free)
# ----------------------------------------------------------------------------------------
def scan_english_only(store: ReadOnlyStore, sample_cap: int = 40) -> dict:
    """Scan every term in the dictionary; count Hangul (hard fail) and any non-ASCII (soft,
    reported) terms and collect violator samples. Scanning the DICTIONARY (not the edges)
    covers every subject/object exactly once — a term absent from the dict cannot appear in
    a row."""
    n_hangul = n_nonascii = n_total = 0
    hangul_samples: list[str] = []
    nonascii_samples: list[str] = []
    for _gid, t in store.iter_terms():
        n_total += 1
        if not t.isascii():
            n_nonascii += 1
            if HANGUL.search(t):
                n_hangul += 1
                if len(hangul_samples) < sample_cap:
                    hangul_samples.append(t)
            elif len(nonascii_samples) < sample_cap:
                nonascii_samples.append(t)
    return {
        "terms_scanned": n_total,
        "hangul_terms": n_hangul,
        "non_ascii_terms": n_nonascii,
        "hangul_samples": hangul_samples,
        "non_ascii_samples": nonascii_samples,
        "english_only_ok": n_hangul == 0,
    }


# ----------------------------------------------------------------------------------------
# term remap — translate staged term ids into the target (shipped/merged) id space
# ----------------------------------------------------------------------------------------
def _staged_gid_capacity(staged_root: Path) -> int:
    """Max staged gid + 1, to size the remap array. gid = (rowid-1)*16+shard, so the ceiling
    is 16 * max_rowid_over_shards."""
    max_rowid = 0
    for sh in range(SHARD_N):
        db = staged_root / "term_shards" / f"terms_{sh:02d}.db"
        if not db.exists():
            continue
        con = sqlite3.connect(f"file:{db.as_posix()}?mode=ro", uri=True)
        r = con.execute("SELECT MAX(rowid) FROM t").fetchone()[0]
        con.close()
        if r:
            max_rowid = max(max_rowid, r)
    return SHARD_N * (max_rowid + 1)


def build_term_map(staged_root: str | Path, other_root: str | Path,
                   *, other_is_writable_copy: bool) -> tuple[np.ndarray, int]:
    """Return (remap, n_new_terms) where remap[staged_gid] -> id in `other` space.
    other_is_writable_copy=False (dry-run): map into the shipped store (read-only), new terms
    get synthetic ids >= _SYNTH_BASE. =True (build): `other` is the merged copy; new terms are
    INSERTed and mapped to real merged ids. Only the sharded backend is supported for staged
    (S1's stores are sharded); a RAM staged store would need the terms.txt path (not needed here)."""
    staged_root = Path(staged_root)
    other_root = Path(other_root)
    if not (staged_root / "term_shards").exists():
        raise ValueError(f"staged store {staged_root} is not sharded (no term_shards/) — "
                         f"build_term_map supports the sharded backend S1 produces")
    cap = _staged_gid_capacity(staged_root)
    remap = np.full(cap, -1, dtype=np.int64)
    n_new, _max = _attach_sql(staged_root, other_root, remap,
                              other_is_writable_copy=other_is_writable_copy)
    return remap, n_new


def _attach_sql(staged_root: Path, other_root: Path, into_arr: np.ndarray,
                *, other_is_writable_copy: bool) -> tuple[int, int]:
    """Real implementation of the per-shard join (the ATTACH target must be a literal, so it is
    formatted here rather than parameter-bound)."""
    n_new = 0
    max_gid = -1
    synth_next = _SYNTH_BASE
    for sh in range(SHARD_N):
        st_db = staged_root / "term_shards" / f"terms_{sh:02d}.db"
        ot_db = other_root / "term_shards" / f"terms_{sh:02d}.db"
        if not st_db.exists():
            continue
        st_uri = f"file:{st_db.as_posix()}?mode=ro"
        if other_is_writable_copy:
            # main (merged) shard opened read-write VIA URI so the ATTACH URI below is parsed;
            # the staged shard is attached mode=ro so this can never write the staged store.
            con = sqlite3.connect(f"file:{ot_db.as_posix()}", uri=True)
            con.execute("PRAGMA journal_mode=OFF")
            con.execute("PRAGMA synchronous=OFF")
            con.execute(f"ATTACH DATABASE '{st_uri}' AS st")
            before = con.execute("SELECT COUNT(*) FROM t").fetchone()[0]
            con.execute("INSERT OR IGNORE INTO t(term) SELECT term FROM st.t")
            after = con.execute("SELECT COUNT(*) FROM t").fetchone()[0]
            con.commit()
            n_new += (after - before)
            for st_rowid, m_rowid in con.execute(
                    "SELECT s.rowid, m.rowid FROM st.t s JOIN t m ON s.term = m.term"):
                g = gid_of(st_rowid, sh)
                into_arr[g] = gid_of(m_rowid, sh)
                if g > max_gid:
                    max_gid = g
            con.execute("DETACH DATABASE st")
            con.close()
        else:
            con = sqlite3.connect(st_uri, uri=True)
            ot_uri = f"file:{ot_db.as_posix()}?mode=ro"
            con.execute(f"ATTACH DATABASE '{ot_uri}' AS shp")
            for st_rowid, shp_rowid in con.execute(
                    "SELECT s.rowid, p.rowid FROM t s LEFT JOIN shp.t p ON s.term = p.term"):
                g = gid_of(st_rowid, sh)
                if shp_rowid is None:
                    into_arr[g] = synth_next
                    synth_next += 1
                    n_new += 1
                else:
                    into_arr[g] = gid_of(shp_rowid, sh)
                if g > max_gid:
                    max_gid = g
            con.execute("DETACH DATABASE shp")
            con.close()
    return n_new, max_gid


# ----------------------------------------------------------------------------------------
# per-predicate dedup — exact (s,p,o) identity via int64 (s<<32|o) packing within a predicate
# ----------------------------------------------------------------------------------------
def _pack(s_arr: np.ndarray, o_arr: np.ndarray) -> np.ndarray:
    """Pack (s,o) gids (non-negative, < 2^31) into a unique int64 key. Within a fixed predicate
    this is an exact (s,p,o) identity — no hashing, no collisions (unlike the store's own
    _tri_key multiply-hash which overflows at large ids). Guarded: at S1 scale all ids are
    < 2^25; a store big enough to exceed 2^31 gids would need a wider key (int128 / tuple dedup)."""
    if len(s_arr):
        hi = max(int(s_arr.max()), int(o_arr.max()))
        if hi >= _MAX_PACKABLE_GID:
            raise OverflowError(f"gid {hi} >= 2^31 — the (s<<32)|o dedup key would overflow; "
                                f"this store is too large for the int64-packed merge path")
    return (s_arr.astype(np.int64) << np.int64(32)) | (o_arr.astype(np.int64) & np.int64(0xFFFFFFFF))


def plan_merge(staged_root: str | Path, shipped_root: str | Path) -> dict:
    """DRY-RUN planner (READ-ONLY on both stores): translate staged term ids into the shipped
    id space (new terms -> synthetic), then per predicate compute shipped edges, staged edges,
    exact duplicates, and net-new. This is the density-lift measurement AND the promoter's
    projection — one routine so the numbers can never disagree."""
    staged_root, shipped_root = Path(staged_root), Path(shipped_root)
    remap, n_new_terms = build_term_map(staged_root, shipped_root, other_is_writable_copy=False)
    shipped = ReadOnlyStore(shipped_root)
    staged = ReadOnlyStore(staged_root)
    try:
        st_s, st_p, st_o = staged.col("s"), staged.col("p"), staged.col("o")
        sh_s, sh_p, sh_o = shipped.col("s"), shipped.col("p"), shipped.col("o")
        # translate staged s/o into shipped space
        st_s_m = remap[st_s]
        st_o_m = remap[st_o]
        # group staged by its OWN predicate gid; map that predicate to a string + shipped gid
        per_rel: dict[str, dict] = {}
        tot_staged = tot_dup = tot_new = 0
        st_pred_ids, st_pred_counts = (np.unique(st_p, return_counts=True)
                                       if len(st_p) else (np.zeros(0, "<i4"), np.zeros(0)))
        for gid, cnt in zip(st_pred_ids.tolist(), st_pred_counts.tolist()):
            pred = staged.term(int(gid))
            mask = st_p == gid
            staged_keys = _pack(st_s_m[mask], st_o_m[mask])
            staged_keys = np.unique(staged_keys)  # dedup WITHIN staged
            shipped_gid = shipped.lookup(pred)
            if shipped_gid is None:
                shipped_n = 0
                dup = 0
            else:
                smask = sh_p == shipped_gid
                shipped_keys = np.unique(_pack(sh_s[smask], sh_o[smask]))
                shipped_n = int(len(shipped_keys))
                if len(shipped_keys):
                    pos = np.searchsorted(shipped_keys, staged_keys)
                    pos = np.clip(pos, 0, len(shipped_keys) - 1)
                    dup = int((shipped_keys[pos] == staged_keys).sum())
                else:
                    dup = 0
            staged_n = int(len(staged_keys))
            net_new = staged_n - dup
            per_rel[pred] = {"shipped": shipped_n, "staged_distinct": staged_n,
                             "duplicates": dup, "net_new": net_new}
            tot_staged += staged_n
            tot_dup += dup
            tot_new += net_new
        return {
            "n_new_terms": int(n_new_terms),
            "staged_edges_raw": int(len(st_s)),
            "shipped_edges": int(len(sh_s)),
            "per_relation": dict(sorted(per_rel.items(), key=lambda kv: -kv[1]["net_new"])),
            "totals": {"staged_distinct": tot_staged, "duplicates": tot_dup, "net_new": tot_new,
                       "projected_shipped_after": int(len(sh_s)) + tot_new},
        }
    finally:
        shipped.close()
        staged.close()


# ----------------------------------------------------------------------------------------
# immutable mixed-mutation candidate helpers
# ----------------------------------------------------------------------------------------
def _mutation_source_line(
    addition: Mapping[str, Any],
    *,
    manifest_sha256: str,
    index: int,
) -> str:
    refs = addition.get("source_refs")
    reference = (
        refs[0]
        if isinstance(refs, list) and len(refs) == 1
        else (
            f"urn:atanor:mutation-batch:{manifest_sha256}"
            f"#addition-{index}"
        )
    )
    return f"{addition['provenance']}|{reference}"


def _mutation_retraction_suffix(
    manifest: Mapping[str, Any],
    *,
    manifest_sha256: str,
) -> bytes:
    rows: list[bytes] = []
    for value in manifest["retractions"]:
        row = {
            "schema_version": "atanor.graph-scale.retraction-event.v1",
            "batch_id": manifest["batch_id"],
            "mutation_batch_manifest_sha256": manifest_sha256,
            "s": value["subject"],
            "p": value["predicate"],
            "o": value["object"],
            "reason": value["reason"],
            "evidence_refs": value["evidence_refs"],
        }
        rows.append(_canonical_json_bytes(row) + b"\n")
    return b"".join(rows)


def _strict_retraction_ledger(
    raw: bytes,
    *,
    label: str,
) -> tuple[set[tuple[str, str, str]], int]:
    if raw and not raw.endswith(b"\n"):
        raise RuntimeError(f"{label} does not end at a complete JSONL record")
    triples: set[tuple[str, str, str]] = set()
    count = 0
    for line in raw.splitlines():
        if not line:
            raise RuntimeError(f"{label} contains an empty JSONL record")
        event = _strict_json_object(line, label=label)
        triple = tuple(event.get(field) for field in ("s", "p", "o"))
        if not all(isinstance(value, str) and value for value in triple):
            raise RuntimeError(f"{label} contains a malformed retraction")
        triples.add((triple[0], triple[1], triple[2]))
        count += 1
    return triples, count


def _raw_triple_present(
    store: "ReadOnlyStore",
    triple: tuple[str, str, str],
) -> bool:
    identifiers = tuple(store.lookup(value) for value in triple)
    if any(value is None for value in identifiers):
        return False
    s_col, p_col, o_col = store.col("s"), store.col("p"), store.col("o")
    return bool(
        (
            (s_col == identifiers[0])
            & (p_col == identifiers[1])
            & (o_col == identifiers[2])
        ).any()
    )


def _atomic_replace_bytes(path: Path, raw: bytes) -> None:
    temporary = path.with_name(
        f".{path.name}.{os.getpid()}.{time.time_ns()}.tmp"
    )
    try:
        with temporary.open("xb") as handle:
            handle.write(raw)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
        _sync_directory(path.parent)
    finally:
        if temporary.exists() and not _is_link_or_junction(temporary):
            temporary.unlink()


def _write_exclusive_bytes(path: Path, raw: bytes) -> None:
    try:
        with path.open("xb") as handle:
            handle.write(raw)
            handle.flush()
            os.fsync(handle.fileno())
    except FileExistsError as exc:
        raise RuntimeError(
            f"immutable candidate evidence already exists: {path.name}"
        ) from exc
    _sync_directory(path.parent)


def _embedded_mutation_material(
    candidate: Path,
    *,
    expected_base_digest_sha256: str | None = None,
) -> tuple[dict[str, Any], str, dict[str, Any]]:
    binding_root = candidate / MUTATION_BINDING_DIRECTORY
    if _is_link_or_junction(binding_root) or not binding_root.is_dir():
        raise RuntimeError("candidate mutation binding directory is invalid")
    expected_names = {"manifest.json", "seal.json", "binding.json"}
    if {path.name for path in binding_root.iterdir()} != expected_names:
        raise RuntimeError("candidate mutation binding entries mismatch")
    manifest_raw = (binding_root / "manifest.json").read_bytes()
    seal_raw = (binding_root / "seal.json").read_bytes()
    manifest, manifest_sha256 = validate_sealed_manifest_bytes(
        manifest_raw,
        seal_raw,
        expected_base_digest_sha256=expected_base_digest_sha256,
    )
    binding_raw = (binding_root / "binding.json").read_bytes()
    binding = _strict_json_object(
        binding_raw,
        label="candidate mutation binding",
    )
    if (
        binding_raw != _canonical_json_bytes(binding)
        or set(binding)
        != {
            "schema_version",
            "batch_id",
            "manifest_sha256",
            "base_digest_sha256",
            "all_or_nothing",
            "production_store_mutated",
        }
        or binding.get("schema_version")
        != MUTATION_BINDING_SCHEMA_VERSION
        or binding.get("batch_id") != manifest["batch_id"]
        or binding.get("manifest_sha256") != manifest_sha256
        or binding.get("base_digest_sha256")
        != manifest["base_digest_sha256"]
        or binding.get("all_or_nothing") is not True
        or binding.get("production_store_mutated") is not False
    ):
        raise RuntimeError("candidate mutation binding is invalid")
    return manifest, manifest_sha256, binding


# ----------------------------------------------------------------------------------------
# the SAFE bulk promoter
# ----------------------------------------------------------------------------------------
class StoreMerger:
    """Build a merged store as (copy of shipped) + (novel staged edges), verify it against the
    shipped original, then swap it into place with a reversible rename. Never writes the live
    store until swap(); never deletes a backup."""

    def __init__(self, shipped_root: str | Path, staged_root: str | Path,
                 provenance: str = "wikidata-truthy"):
        self.shipped_root = Path(shipped_root)
        self.staged_root = Path(staged_root)
        self.provenance = provenance

    def build_mutation_candidate(
        self,
        out_root: str | Path,
        *,
        mutation_batch_root: str | Path,
    ) -> dict[str, Any]:
        """Materialize one sealed mixed add/retract batch in a sibling candidate.

        The live store is only read and repeatedly re-hashed.  All writes occur
        in a process-private sibling directory which is renamed to ``out_root``
        only after exact semantic postconditions pass.  A successful fresh
        verification then records the batch's ``staged`` lifecycle receipt.
        """

        candidate = _validate_candidate_lane(
            self.shipped_root,
            out_root,
            require_exists=False,
        )
        live = _canonical_directory(
            self.shipped_root,
            label="live shipped store",
        )
        base_digest = _tree_sha256(live)
        reference, manifest, latest_stage = load_validated_mutation_batch(
            mutation_batch_root,
            expected_base_digest_sha256=base_digest,
        )
        if latest_stage is not MutationStage.PROPOSED:
            raise RuntimeError(
                "mutation candidate build requires a proposed batch"
            )
        temporary = candidate.parent / (
            f".{candidate.name}.assembling.{os.getpid()}.{time.time_ns()}"
        )
        if temporary.exists() or _is_link_or_junction(temporary):
            raise FileExistsError("private mutation candidate lane already exists")

        started = time.time()
        try:
            shutil.copytree(live, temporary, symlinks=True)
            if (
                _tree_sha256(temporary) != base_digest
                or _tree_sha256(live) != base_digest
            ):
                raise RuntimeError(
                    "live store changed while copying mutation candidate base"
                )

            # Copied receipts describe the previous installed candidate, not
            # this build.  They are never accepted as authority for a new one.
            for stale_name in ("BUILD_REPORT.json", "VERIFY_REPORT.json"):
                stale = temporary / stale_name
                if stale.exists() and not _is_link_or_junction(stale):
                    stale.unlink()
            stale_binding = temporary / MUTATION_BINDING_DIRECTORY
            if stale_binding.exists() or _is_link_or_junction(stale_binding):
                _discard_sealed_snapshot(
                    stale_binding,
                    approved_parent=temporary,
                )

            base_store = ReadOnlyStore(live)
            candidate_store = None
            try:
                base_retractions_path = live / "retractions.jsonl"
                base_retractions_raw = (
                    base_retractions_path.read_bytes()
                    if base_retractions_path.exists()
                    else b""
                )
                base_tombstones, base_retraction_records = (
                    _strict_retraction_ledger(
                        base_retractions_raw,
                        label="base retraction ledger",
                    )
                )
                additions = [
                    (value["subject"], value["predicate"], value["object"])
                    for value in manifest["additions"]
                ]
                retractions = [
                    (value["subject"], value["predicate"], value["object"])
                    for value in manifest["retractions"]
                ]
                for triple in additions:
                    if triple in base_tombstones:
                        raise RuntimeError(
                            "mutation addition would resurrect a tombstoned "
                            "triple without an unretract contract"
                        )
                    if _raw_triple_present(base_store, triple):
                        raise RuntimeError(
                            "mutation addition already exists in the base store"
                        )
                for triple in retractions:
                    if triple in base_tombstones:
                        raise RuntimeError(
                            "mutation retraction target is already tombstoned"
                        )
                    if not _raw_triple_present(base_store, triple):
                        raise RuntimeError(
                            "mutation retraction target is absent from the base"
                        )

                if additions and (
                    (live / "qid_pid.col").exists()
                    or (live / "S1_WIKIDATA_LITERAL_MANIFEST.json").exists()
                ):
                    raise RuntimeError(
                        "mutation additions cannot extend the count-aligned "
                        "literal evidence sidecar"
                    )

                from packages.graph_scale.triple_store import TripleStore

                candidate_store = TripleStore(temporary)
                base_count = base_store.n_edges
                for index, value in enumerate(manifest["additions"]):
                    source_line = _mutation_source_line(
                        value,
                        manifest_sha256=reference.manifest_sha256,
                        index=index,
                    )
                    source_name, _, source_reference = source_line.partition("|")
                    source_id = candidate_store.intern_source(
                        source_name,
                        source_reference,
                    )
                    if not candidate_store.add(
                        value["subject"],
                        value["predicate"],
                        value["object"],
                        source=source_id,
                    ):
                        raise RuntimeError(
                            "mutation addition was refused by the store gate"
                        )
                candidate_store.flush()
                expected_count = base_count + len(additions)
                if len(candidate_store) != expected_count:
                    raise RuntimeError(
                        "mutation additions did not append exactly once"
                    )

                retraction_suffix = _mutation_retraction_suffix(
                    manifest,
                    manifest_sha256=reference.manifest_sha256,
                )
                if retraction_suffix:
                    _atomic_replace_bytes(
                        temporary / "retractions.jsonl",
                        base_retractions_raw + retraction_suffix,
                    )
                candidate_store.rebuild_index()
                if hasattr(candidate_store.terms, "close"):
                    candidate_store.terms.close()
                candidate_store = None

                binding_root = temporary / MUTATION_BINDING_DIRECTORY
                binding_root.mkdir(exist_ok=False)
                _write_exclusive_json(
                    binding_root / "binding.json",
                    {
                        "schema_version": MUTATION_BINDING_SCHEMA_VERSION,
                        "batch_id": reference.batch_id,
                        "manifest_sha256": reference.manifest_sha256,
                        "base_digest_sha256": base_digest,
                        "all_or_nothing": True,
                        "production_store_mutated": False,
                    },
                )
                _write_exclusive_bytes(
                    binding_root / "manifest.json",
                    reference.manifest_path.read_bytes(),
                )
                _write_exclusive_bytes(
                    binding_root / "seal.json",
                    reference.seal_path.read_bytes(),
                )
                build_report = {
                    "schema_version": MUTATION_BUILD_SCHEMA_VERSION,
                    "batch_id": reference.batch_id,
                    "mutation_batch_manifest_sha256": (
                        reference.manifest_sha256
                    ),
                    "base_digest_sha256": base_digest,
                    "shipped_edges": base_count,
                    "additions_appended": len(additions),
                    "retractions_appended": len(retractions),
                    "base_retraction_records": base_retraction_records,
                    "merged_edges_total": expected_count,
                    "all_or_nothing": True,
                    "production_store_mutated": False,
                    "out_root": str(candidate),
                    "elapsed_s": round(time.time() - started, 3),
                }
                _atomic_replace_bytes(
                    temporary / "BUILD_REPORT.json",
                    _canonical_json_bytes(build_report),
                )
            finally:
                base_store.close()
                if candidate_store is not None:
                    try:
                        candidate_store.flush()
                    finally:
                        if hasattr(candidate_store.terms, "close"):
                            candidate_store.terms.close()

            preflight = self._evaluate_mutation_verification(temporary)
            if preflight.get("ok") is not True:
                raise RuntimeError(
                    "mutation candidate preflight verification failed"
                )
            _sync_tree_files(temporary)
            if _tree_sha256(live) != base_digest:
                raise RuntimeError(
                    "live store changed before mutation candidate publication"
                )
            temporary.rename(candidate)
            _sync_directory(candidate.parent)
        except Exception:
            _discard_sealed_snapshot(
                temporary,
                approved_parent=candidate.parent,
            )
            raise

        verified = self.verify(candidate)
        if verified.get("ok") is not True:
            raise RuntimeError(
                "published mutation candidate failed fresh verification"
            )
        candidate_digest = _tree_sha256(candidate)
        verify_digest = hashlib.sha256(
            (candidate / "VERIFY_REPORT.json").read_bytes()
        ).hexdigest()
        record_lifecycle_receipt(
            reference.root,
            stage=MutationStage.STAGED.value,
            evidence={
                "candidate_store_path": _canonical_path_string(candidate),
                "candidate_digest_sha256": candidate_digest,
                "verification_report_sha256": verify_digest,
                "mutation_batch_manifest_sha256": reference.manifest_sha256,
                "production_store_mutated": False,
            },
        )
        return {
            "built": True,
            "verified": True,
            "candidate_store_path": str(candidate),
            "candidate_digest_sha256": candidate_digest,
            "verification_report_sha256": verify_digest,
            "mutation_batch_manifest_sha256": reference.manifest_sha256,
            "batch_id": reference.batch_id,
            "base_digest_sha256": base_digest,
            "additions_appended": reference.addition_count,
            "retractions_appended": reference.retraction_count,
            "production_store_mutated": False,
            "staged": True,
        }

    # ---- build -----------------------------------------------------------------
    def build(self, out_root: str | Path, *, source_url: str = "",
              exclude_triples: Iterable[tuple[str, str, str]] | None = None) -> dict:
        """Copy shipped -> out_root, remap staged terms into out_root's dict, dedup, and append
        the novel edges. English-only is a HARD gate: if any novel edge carries Hangul the build
        REFUSES (fail-closed) rather than contaminate the store.

        exclude_triples: (s,p,o) triples to EXCLUDE from the append even if novel — the promoter
        passes the firewall's T0-nogood quarantine here, so a staged edge contradicting an
        operator axiom is kept OUT of the shipped store (live_membrane stays observe-only; the
        enforcement lives here, at the bulk-merge boundary). Returns a build report."""
        out_root = _validate_candidate_lane(
            self.shipped_root,
            out_root,
            require_exists=False,
        )
        t0 = time.time()
        # (a) COPY shipped -> out_root (this preserves every shipped id byte-for-byte)
        shutil.copytree(self.shipped_root, out_root)
        shipped = ReadOnlyStore(self.shipped_root)
        shipped_n = shipped.n_edges
        shipped_terms = shipped.n_terms

        # (b) remap staged term ids into the merged (out_root) dict (new terms INSERTed there)
        remap, n_new_terms = build_term_map(self.staged_root, out_root, other_is_writable_copy=True)

        staged = ReadOnlyStore(self.staged_root)
        st_s, st_p, st_o = staged.col("s"), staged.col("p"), staged.col("o")
        st_src = staged.col("src")
        st_s_m = remap[st_s].astype("<i4")
        st_o_m = remap[st_o].astype("<i4")
        st_p_m = remap[st_p].astype("<i4")

        # (c) provenance: intern the staged source lines into the merged store's registry and
        # remap staged src ids -> merged src ids (default all to `provenance` if no src.col)
        src_remap = self._merge_sources(out_root, staged, source_url)
        if len(st_src):
            merged_src = np.array([src_remap.get(int(x), src_remap.get("__default__", 0))
                                   for x in st_src], dtype="<i4")
        else:
            merged_src = np.full(len(st_s), src_remap.get("__default__", 0), dtype="<i4")

        # (d) dedup against shipped, per predicate (in merged space; shipped cols ARE merged
        # space because out_root's first shipped_n rows are the copied shipped rows)
        sh = ReadOnlyStore(out_root)  # read the copy (== shipped) for its columns
        sh_s = sh.col("s")[:shipped_n]
        sh_p = sh.col("p")[:shipped_n]
        sh_o = sh.col("o")[:shipped_n]
        novel_mask = self._novel_mask(st_s_m, st_p_m, st_o_m, sh_s, sh_p, sh_o)
        sh.close()

        # firewall enforcement: drop any novel edge whose (s,p,o) is in exclude_triples
        n_excluded = 0
        if exclude_triples:
            n_excluded = self._apply_exclusions(out_root, exclude_triples,
                                                st_s_m, st_p_m, st_o_m, novel_mask)

        nov_s = st_s_m[novel_mask]
        nov_p = st_p_m[novel_mask]
        nov_o = st_o_m[novel_mask]
        nov_src = merged_src[novel_mask]

        # (e) English-only HARD gate on the novel edges (we bypass TripleStore.add so we must
        # re-assert the containment contract ourselves before appending)
        eng = self._english_gate(out_root, nov_s, nov_o, remap, staged)
        if not eng["ok"]:
            staged.close(); shipped.close()
            shutil.rmtree(out_root, ignore_errors=True)
            raise ValueError(f"REFUSED: {eng['hangul_edges']} novel edges carry Hangul "
                             f"(samples: {eng['samples']}); staged store is not English-clean")

        # (f) pad src.col to s.col length (legacy lockstep), then append novel columns
        self._pad_src(out_root)
        self._append(out_root, nov_s, nov_p, nov_o, nov_src)

        # (g) finalize meta + rebuild subject index via the real TripleStore
        n_after = shipped_n + int(novel_mask.sum())
        self._finalize(out_root, n_after)

        report = {
            "shipped_edges": shipped_n,
            "shipped_terms": shipped_terms,
            "staged_edges_raw": int(len(st_s)),
            "novel_edges_appended": int(novel_mask.sum()),
            "duplicates_skipped": int(len(st_s) - novel_mask.sum() - n_excluded),
            "firewall_excluded": int(n_excluded),
            "new_terms_added": int(n_new_terms),
            "merged_edges_total": n_after,
            "merged_terms_total": ReadOnlyStore(out_root).n_terms,
            "provenance": self.provenance,
            "english_only_ok": True,
            "elapsed_s": round(time.time() - t0, 2),
            "out_root": str(out_root),
        }
        staged.close()
        shipped.close()
        (out_root / "BUILD_REPORT.json").write_text(
            json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
        return report

    def _merge_sources(self, out_root: Path, staged: ReadOnlyStore, source_url: str) -> dict:
        """Intern staged source-registry lines into the merged store's sources.txt; return a
        map staged_src_id -> merged_src_id (+ a '__default__' for the promotion provenance)."""
        merged_path = out_root / "sources.txt"
        lines = [ln.rstrip("\n") for ln in merged_path.open(encoding="utf-8")] if merged_path.exists() else ["curated:legacy|"]
        index = {ln: i for i, ln in enumerate(lines)}

        def intern(line: str) -> int:
            if line in index:
                return index[line]
            index[line] = len(lines)
            lines.append(line)
            return index[line]

        out: dict = {}
        for i, line in enumerate(staged.source_lines()):
            out[i] = intern(line)
        default_line = f"{self.provenance}|{source_url}"
        out["__default__"] = intern(default_line)
        merged_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        return out

    @staticmethod
    def _novel_mask(st_s, st_p, st_o, sh_s, sh_p, sh_o) -> np.ndarray:
        """Boolean mask over staged edges: True = novel (not already a shipped triple, and the
        first occurrence within staged). Grouped by predicate; exact (s,o) identity per group."""
        n = len(st_s)
        novel = np.ones(n, dtype=bool)
        # precompute shipped keys per predicate
        for gid in np.unique(st_p).tolist():
            smask = st_p == gid
            staged_keys = _pack(st_s[smask], st_o[smask])
            # within-staged dedup: keep first occurrence
            _uniq, first_idx = np.unique(staged_keys, return_index=True)
            keep_local = np.zeros(len(staged_keys), dtype=bool)
            keep_local[first_idx] = True
            # shipped dup removal
            ship_sel = sh_p == gid
            if ship_sel.any():
                shipped_keys = np.unique(_pack(sh_s[ship_sel], sh_o[ship_sel]))
                pos = np.searchsorted(shipped_keys, staged_keys)
                pos = np.clip(pos, 0, len(shipped_keys) - 1)
                is_dup = shipped_keys[pos] == staged_keys
                keep_local &= ~is_dup
            local_idx = np.nonzero(smask)[0]
            novel[local_idx] = keep_local
        return novel

    @staticmethod
    def _apply_exclusions(out_root: Path, exclude_triples, st_s_m, st_p_m, st_o_m,
                          novel_mask) -> int:
        """Clear novel_mask for any edge whose (s,p,o) — resolved to merged ids — is in
        exclude_triples (the firewall quarantine). Mutates novel_mask in place; returns count."""
        merged = ReadOnlyStore(out_root)
        n = 0
        try:
            for (s, p, o) in exclude_triples:
                sm, pm, om = merged.lookup(s), merged.lookup(p), merged.lookup(o)
                if sm is None or pm is None or om is None:
                    continue
                hit = (st_s_m == sm) & (st_p_m == pm) & (st_o_m == om) & novel_mask
                k = int(hit.sum())
                if k:
                    novel_mask[hit] = False
                    n += k
        finally:
            merged.close()
        return n

    def _english_gate(self, out_root: Path, nov_s, nov_o, remap, staged: ReadOnlyStore) -> dict:
        """Verify novel edges are Hangul-free. We already have merged ids; decode a sample of
        subjects/objects via the merged store and check. For a full guarantee we check EVERY
        distinct novel term id against the merged dict (bounded by the novel vocabulary)."""
        merged = ReadOnlyStore(out_root)
        try:
            distinct = np.unique(np.concatenate([nov_s, nov_o])) if len(nov_s) else np.zeros(0, "<i4")
            hangul_edges = 0
            samples: list[str] = []
            bad_ids: set[int] = set()
            for gid in distinct.tolist():
                t = merged.term(int(gid))
                if HANGUL.search(t):
                    bad_ids.add(int(gid))
                    if len(samples) < 20:
                        samples.append(t)
            if bad_ids:
                # count edges touching a bad id
                mask = np.isin(nov_s, list(bad_ids)) | np.isin(nov_o, list(bad_ids))
                hangul_edges = int(mask.sum())
            return {"ok": hangul_edges == 0, "hangul_edges": hangul_edges, "samples": samples}
        finally:
            merged.close()

    @staticmethod
    def _pad_src(out_root: Path) -> None:
        """Ensure src.col has exactly one int32 per s row before appending (mirrors
        TripleStore._backfill_src; rows written before provenance are legacy tier 0)."""
        s_path = out_root / "s.col"
        src_path = out_root / "src.col"
        if not s_path.exists():
            return
        s_rows = s_path.stat().st_size // 4
        src_rows = (src_path.stat().st_size // 4) if src_path.exists() else 0
        missing = s_rows - src_rows
        if missing > 0:
            with src_path.open("ab") as fh:
                fh.write(np.zeros(missing, dtype="<i4").tobytes())

    @staticmethod
    def _append(out_root: Path, s, p, o, src) -> None:
        for name, arr in (("s", s), ("p", p), ("o", o), ("src", src)):
            with (out_root / f"{name}.col").open("ab") as fh:
                fh.write(np.ascontiguousarray(arr, dtype="<i4").tobytes())

    @staticmethod
    def _finalize(out_root: Path, n_after: int) -> None:
        import sys
        REPO = Path(__file__).resolve().parents[1]
        if str(REPO) not in sys.path:
            sys.path.insert(0, str(REPO))
        from packages.graph_scale.triple_store import TripleStore
        # write meta count first so TripleStore opens with the right count, then rebuild index
        meta_p = out_root / "meta.json"
        meta = json.loads(meta_p.read_text(encoding="utf-8"))
        meta["count"] = n_after
        meta_p.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
        st = TripleStore(out_root)
        st._count = n_after
        st.rebuild_index()
        if hasattr(st.terms, "close"):
            st.terms.close()

    # ---- verify ----------------------------------------------------------------
    def _evaluate_mutation_verification(
        self,
        out_root: str | Path,
    ) -> dict[str, Any]:
        """Freshly reconstruct the exact semantics of a mixed mutation candidate."""

        candidate = Path(out_root).resolve(strict=True)
        checks: dict[str, Any] = {}
        shipped = None
        merged = None
        try:
            live = _canonical_directory(
                self.shipped_root,
                label="live shipped store",
            )
            base_digest_before = _tree_sha256(live)
            manifest, manifest_sha256, _binding = (
                _embedded_mutation_material(
                    candidate,
                    expected_base_digest_sha256=base_digest_before,
                )
            )
            checks["base_digest_binding"] = {
                "expected": manifest["base_digest_sha256"],
                "observed": base_digest_before,
                "ok": manifest["base_digest_sha256"]
                == base_digest_before,
            }

            shipped = ReadOnlyStore(live)
            merged = ReadOnlyStore(candidate)
            base_count = shipped.n_edges
            expected_additions = [
                (value["subject"], value["predicate"], value["object"])
                for value in manifest["additions"]
            ]
            expected_retractions = [
                (value["subject"], value["predicate"], value["object"])
                for value in manifest["retractions"]
            ]
            s_s, s_p, s_o = (
                shipped.col("s"),
                shipped.col("p"),
                shipped.col("o"),
            )
            m_s, m_p, m_o, m_src = (
                merged.col("s"),
                merged.col("p"),
                merged.col("o"),
                merged.col("src"),
            )
            prefix_ok = (
                len(m_s) >= base_count
                and np.array_equal(m_s[:base_count], s_s)
                and np.array_equal(m_p[:base_count], s_p)
                and np.array_equal(m_o[:base_count], s_o)
            )
            checks["base_column_prefix"] = {"ok": bool(prefix_ok)}

            base_src = shipped.col("src")
            if len(base_src):
                source_prefix_ok = (
                    len(m_src) >= base_count
                    and np.array_equal(m_src[:base_count], base_src)
                )
            else:
                source_prefix_ok = (
                    len(m_src) >= base_count
                    and not np.asarray(m_src[:base_count]).any()
                )
            checks["base_source_prefix"] = {
                "base_had_source_column": bool(len(base_src)),
                "ok": bool(source_prefix_ok),
            }

            appended: list[tuple[str, str, str]] = []
            appended_sources: list[str] = []
            source_lines = merged.source_lines()
            for row in range(base_count, len(m_s)):
                appended.append(
                    (
                        merged.term(int(m_s[row])),
                        merged.term(int(m_p[row])),
                        merged.term(int(m_o[row])),
                    )
                )
                source_id = int(m_src[row]) if row < len(m_src) else -1
                appended_sources.append(
                    source_lines[source_id]
                    if 0 <= source_id < len(source_lines)
                    else ""
                )
            expected_sources = [
                _mutation_source_line(
                    value,
                    manifest_sha256=manifest_sha256,
                    index=index,
                )
                for index, value in enumerate(manifest["additions"])
            ]
            checks["exact_additions"] = {
                "expected": len(expected_additions),
                "observed": len(appended),
                "triples_ok": appended == expected_additions,
                "sources_ok": appended_sources == expected_sources,
                "ok": (
                    appended == expected_additions
                    and appended_sources == expected_sources
                ),
            }

            meta_count = merged.meta.get("count")
            expected_count = base_count + len(expected_additions)
            lockstep_ok = (
                len(m_s)
                == len(m_p)
                == len(m_o)
                == len(m_src)
                == expected_count
                and type(meta_count) is int
                and meta_count == expected_count
            )
            checks["column_lockstep"] = {
                "base": base_count,
                "expected": expected_count,
                "observed": len(m_s),
                "meta_count": meta_count,
                "ok": bool(lockstep_ok),
            }

            base_retraction_path = live / "retractions.jsonl"
            candidate_retraction_path = candidate / "retractions.jsonl"
            base_retraction_raw = (
                base_retraction_path.read_bytes()
                if base_retraction_path.exists()
                else b""
            )
            candidate_retraction_raw = (
                candidate_retraction_path.read_bytes()
                if candidate_retraction_path.exists()
                else b""
            )
            base_tombstones, base_retraction_records = (
                _strict_retraction_ledger(
                    base_retraction_raw,
                    label="base retraction ledger",
                )
            )
            candidate_tombstones, candidate_retraction_records = (
                _strict_retraction_ledger(
                    candidate_retraction_raw,
                    label="candidate retraction ledger",
                )
            )
            expected_suffix = _mutation_retraction_suffix(
                manifest,
                manifest_sha256=manifest_sha256,
            )
            expected_tombstones = base_tombstones | set(
                expected_retractions
            )
            retractions_ok = (
                candidate_retraction_raw
                == base_retraction_raw + expected_suffix
                and candidate_tombstones == expected_tombstones
                and candidate_retraction_records
                == base_retraction_records + len(expected_retractions)
            )
            checks["exact_retractions"] = {
                "expected": len(expected_retractions),
                "observed_new_records": (
                    candidate_retraction_records
                    - base_retraction_records
                ),
                "base_prefix_preserved": candidate_retraction_raw.startswith(
                    base_retraction_raw
                ),
                "ok": bool(retractions_ok),
            }

            base_operation_contract = True
            for triple in expected_additions:
                base_operation_contract = (
                    base_operation_contract
                    and triple not in base_tombstones
                    and not _raw_triple_present(shipped, triple)
                )
            for triple in expected_retractions:
                base_operation_contract = (
                    base_operation_contract
                    and triple not in base_tombstones
                    and _raw_triple_present(shipped, triple)
                )
            checks["base_operation_contract"] = {
                "ok": bool(base_operation_contract)
            }

            index_ts = merged.meta.get("index_ts")
            index_ok = False
            if isinstance(index_ts, int) and not isinstance(index_ts, bool):
                perm_path = candidate / f"s.perm.{index_ts}.npy"
                sorted_path = candidate / f"s.sorted.{index_ts}.npy"
                if perm_path.is_file() and sorted_path.is_file():
                    permutation = np.load(str(perm_path), mmap_mode="r")
                    sorted_subjects = np.load(
                        str(sorted_path),
                        mmap_mode="r",
                    )
                    index_ok = (
                        len(permutation) == len(m_s)
                        and len(sorted_subjects) == len(m_s)
                        and np.array_equal(
                            np.sort(np.asarray(permutation)),
                            np.arange(len(m_s), dtype=permutation.dtype),
                        )
                        and np.array_equal(
                            np.asarray(sorted_subjects),
                            np.asarray(m_s)[np.asarray(permutation)],
                        )
                    )
            checks["subject_index"] = {"ok": bool(index_ok)}

            build_raw = (candidate / "BUILD_REPORT.json").read_bytes()
            build_report = _strict_json_object(
                build_raw,
                label="mutation candidate BUILD_REPORT.json",
            )
            build_fields = {
                "schema_version",
                "batch_id",
                "mutation_batch_manifest_sha256",
                "base_digest_sha256",
                "shipped_edges",
                "additions_appended",
                "retractions_appended",
                "base_retraction_records",
                "merged_edges_total",
                "all_or_nothing",
                "production_store_mutated",
                "out_root",
                "elapsed_s",
            }
            build_ok = (
                build_raw == _canonical_json_bytes(build_report)
                and set(build_report) == build_fields
                and build_report.get("schema_version")
                == MUTATION_BUILD_SCHEMA_VERSION
                and build_report.get("batch_id") == manifest["batch_id"]
                and build_report.get(
                    "mutation_batch_manifest_sha256"
                )
                == manifest_sha256
                and build_report.get("base_digest_sha256")
                == base_digest_before
                and build_report.get("shipped_edges") == base_count
                and build_report.get("additions_appended")
                == len(expected_additions)
                and build_report.get("retractions_appended")
                == len(expected_retractions)
                and build_report.get("base_retraction_records")
                == base_retraction_records
                and build_report.get("merged_edges_total")
                == expected_count
                and build_report.get("all_or_nothing") is True
                and build_report.get("production_store_mutated") is False
            )
            checks["build_report_binding"] = {"ok": bool(build_ok)}

            base_digest_after = _tree_sha256(live)
            checks["live_unchanged_during_verification"] = {
                "before": base_digest_before,
                "after": base_digest_after,
                "ok": base_digest_after == base_digest_before,
            }
            ok = all(
                value.get("ok") is True
                for value in checks.values()
                if isinstance(value, dict)
            )
            return {
                "schema_version": MUTATION_VERIFY_SCHEMA_VERSION,
                "ok": bool(ok),
                "mutation_batch_manifest_sha256": manifest_sha256,
                "base_digest_sha256": base_digest_before,
                "checks": checks,
                "out_root": str(candidate),
            }
        except Exception as exc:
            return {
                "schema_version": MUTATION_VERIFY_SCHEMA_VERSION,
                "ok": False,
                "mutation_batch_manifest_sha256": None,
                "base_digest_sha256": None,
                "checks": checks,
                "error": f"{type(exc).__name__}: {exc}",
                "out_root": str(candidate),
            }
        finally:
            if shipped is not None:
                shipped.close()
            if merged is not None:
                merged.close()

    def _evaluate_verification(self, out_root: str | Path, *, sample: int = 500) -> dict:
        """Prove the merged store is a faithful superset of shipped:
          1. the column PREFIX (first shipped_n rows of s/p/o) is byte-identical to shipped —
             this is the real guarantee that every prior fact survives at the same id/row;
          2. a random sample of shipped triples decodes to the identical strings in the merged
             store (term-dict integrity + no id drift);
          3. edge count == shipped + novel; term count grew by exactly the new terms;
          4. novel appended rows are Hangul-free;
          5. a few facts_about() queries still answer.
        Returns a report with per-check pass/fail without writing a receipt."""
        out_root = Path(out_root).resolve(strict=True)
        if (out_root / MUTATION_BINDING_DIRECTORY).exists():
            return self._evaluate_mutation_verification(out_root)
        shipped = ReadOnlyStore(self.shipped_root)
        merged = ReadOnlyStore(out_root)
        checks: dict = {}
        try:
            shipped_n = shipped.n_edges
            m_s, m_p, m_o = merged.col("s"), merged.col("p"), merged.col("o")
            m_src = merged.col("src")
            s_s, s_p, s_o = shipped.col("s"), shipped.col("p"), shipped.col("o")
            # 1) prefix byte-identity
            prefix_ok = (len(m_s) >= shipped_n and
                         np.array_equal(m_s[:shipped_n], s_s) and
                         np.array_equal(m_p[:shipped_n], s_p) and
                         np.array_equal(m_o[:shipped_n], s_o))
            checks["prefix_byte_identical"] = bool(prefix_ok)
            # 2) sample shipped triples decode identically in merged
            rng = np.random.default_rng(0)
            idx = rng.choice(shipped_n, size=min(sample, shipped_n), replace=False) if shipped_n else np.zeros(0, int)
            mism = 0
            for i in idx.tolist():
                trip_ship = (shipped.term(int(s_s[i])), shipped.term(int(s_p[i])), shipped.term(int(s_o[i])))
                trip_merged = (merged.term(int(m_s[i])), merged.term(int(m_p[i])), merged.term(int(m_o[i])))
                if trip_ship != trip_merged or "" in trip_ship:
                    mism += 1
            checks["sampled_shipped_triples_resolve"] = {"sampled": int(len(idx)), "mismatches": mism, "ok": mism == 0}
            # 3) counts
            n_novel = len(m_s) - shipped_n
            meta_count = merged.meta.get("count")
            column_lockstep = (
                len(m_s) == len(m_p) == len(m_o) == len(m_src)
                and isinstance(meta_count, int)
                and not isinstance(meta_count, bool)
                and meta_count == len(m_s)
            )
            checks["edge_count"] = {"shipped": shipped_n, "merged": int(len(m_s)),
                                    "novel": int(n_novel), "meta_count": meta_count,
                                    "ok": bool(n_novel >= 0 and column_lockstep)}
            checks["term_count"] = {"shipped": shipped.n_terms, "merged": merged.n_terms,
                                    "ok": merged.n_terms >= shipped.n_terms}
            try:
                build_report = _strict_json_object(
                    (out_root / "BUILD_REPORT.json").read_bytes(),
                    label="candidate BUILD_REPORT.json",
                )
                build_counts = (
                    build_report.get("shipped_edges"),
                    build_report.get("novel_edges_appended"),
                    build_report.get("merged_edges_total"),
                )
                build_report_ok = (
                    all(isinstance(value, int) and not isinstance(value, bool)
                        for value in build_counts)
                    and build_report.get("shipped_edges") == shipped_n
                    and build_report.get("novel_edges_appended") == n_novel
                    and build_report.get("merged_edges_total") == len(m_s)
                    and build_report.get("english_only_ok") is True
                    and Path(str(build_report.get("out_root", ""))).resolve(strict=True)
                    == out_root
                )
            except Exception:
                build_report_ok = False
            checks["build_report_binding"] = {"ok": bool(build_report_ok)}
            # 4) novel rows Hangul-free
            hangul = 0
            if n_novel > 0:
                distinct = np.unique(np.concatenate([m_s[shipped_n:], m_o[shipped_n:]]))
                for gid in distinct.tolist():
                    if HANGUL.search(merged.term(int(gid))):
                        hangul += 1
            checks["novel_rows_english_only"] = {"hangul_terms": hangul, "ok": hangul == 0}
            # 5) facts_about smoke (via a real read-only TripleStore) on a couple shipped subjects
            checks["facts_about_smoke"] = self._facts_about_smoke(out_root, shipped, s_s, sample=5)
            ok = (checks["prefix_byte_identical"]
                  and checks["sampled_shipped_triples_resolve"]["ok"]
                  and checks["edge_count"]["ok"] and checks["term_count"]["ok"]
                  and checks["build_report_binding"]["ok"]
                  and checks["novel_rows_english_only"]["ok"]
                  and checks["facts_about_smoke"]["ok"])
            return {
                "schema_version": MERGE_VERIFY_SCHEMA_VERSION,
                "ok": bool(ok),
                "checks": checks,
                "out_root": str(out_root),
            }
        finally:
            shipped.close()
            merged.close()

    def verify(self, out_root: str | Path, *, sample: int = 500) -> dict:
        """Evaluate the candidate and atomically persist the exact verification receipt."""
        out_root = _validate_candidate_lane(
            self.shipped_root,
            out_root,
            require_exists=True,
        )
        report = self._evaluate_verification(out_root, sample=sample)
        report_path = out_root / "VERIFY_REPORT.json"
        temporary = out_root / f".VERIFY_REPORT.{os.getpid()}.{time.time_ns()}.tmp"
        encoded = json.dumps(
            report,
            indent=2,
            ensure_ascii=False,
            allow_nan=False,
        ).encode("utf-8")
        try:
            with temporary.open("xb") as handle:
                handle.write(encoded)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary, report_path)
        finally:
            if temporary.exists():
                temporary.unlink()
        return report

    @staticmethod
    def _facts_about_smoke(out_root: Path, shipped: ReadOnlyStore, s_s, *, sample: int) -> dict:
        import sys
        REPO = Path(__file__).resolve().parents[1]
        if str(REPO) not in sys.path:
            sys.path.insert(0, str(REPO))
        from packages.graph_scale.triple_store import TripleStore
        st = TripleStore(out_root)
        answered = 0
        tried = 0
        if len(s_s):
            for gid in np.unique(s_s)[:sample].tolist():
                subj = shipped.term(int(gid))
                if not subj:
                    continue
                tried += 1
                if st.facts_about(subj, limit=5):
                    answered += 1
        if hasattr(st.terms, "close"):
            st.terms.close()
        return {"subjects_tried": tried, "answered": answered, "ok": answered == tried and tried > 0}

    # ---- swap / rollback -------------------------------------------------------
    @staticmethod
    def staging_receipt_payload(
        kg_root: str | Path,
        merged_root: str | Path,
    ) -> dict[str, Any]:
        """Return the exact single entry to enqueue before operator confirmation."""
        material = _candidate_promotion_material(kg_root, merged_root)
        return {
            "promotion_kind": "graph_store_candidate",
            "candidate_store_path": _canonical_path_string(material["candidate"]),
            "candidate_digest_sha256": material["candidate_digest"],
            "mutation_batch_manifest_sha256": material[
                "mutation_batch_manifest_sha256"
            ],
            "verification_report_sha256": hashlib.sha256(
                material["report_raw"]
            ).hexdigest(),
            "target_store_id": SHIPPED_STORE_TARGET_ID,
            "base_revision": f"sha256:{material['base_digest']}",
        }

    @staticmethod
    def promotion_context(
        kg_root: str | Path,
        merged_root: str | Path,
        *,
        staging_receipt: str | Path,
    ) -> dict[str, Any]:
        """Return the exact current live context that an operator must sign.

        A prior VERIFY_REPORT ``ok`` value is never authority. The persisted report must
        exactly match a fresh independent evaluation before any digest is emitted.
        """
        boundary = load_system_shipped_graph_operator_boundary(
            repository_root=REPOSITORY_ROOT,
            expected_target_store_id=SHIPPED_STORE_TARGET_ID,
        )
        return StoreMerger._promotion_context_with_boundary(
            kg_root,
            merged_root,
            staging_receipt=staging_receipt,
            boundary=boundary,
        )

    @staticmethod
    def _promotion_context_with_boundary(
        kg_root: str | Path,
        merged_root: str | Path,
        *,
        staging_receipt: str | Path,
        boundary: ShippedGraphOperatorBoundary,
    ) -> dict[str, Any]:
        if not isinstance(boundary, ShippedGraphOperatorBoundary):
            raise RuntimeError("fixed shipped-graph operator boundary is required")
        boundary.revalidate()
        material = _candidate_promotion_material(kg_root, merged_root)
        candidate = material["candidate"]
        candidate_digest = material["candidate_digest"]
        base_digest = material["base_digest"]
        report_raw = material["report_raw"]
        (
            receipt_raw,
            item_ids,
            mutation_batch_manifest_sha256,
        ) = _validated_staging_receipt(
            staging_receipt,
            candidate=candidate,
            candidate_digest=candidate_digest,
            verification_report_sha256=hashlib.sha256(report_raw).hexdigest(),
            base_digest=base_digest,
            mutation_batch_manifest_sha256=material[
                "mutation_batch_manifest_sha256"
            ],
        )
        return {
            "staging_receipt_sha256": hashlib.sha256(receipt_raw).hexdigest(),
            "candidate_digest_sha256": candidate_digest,
            "mutation_batch_manifest_sha256": (
                mutation_batch_manifest_sha256
            ),
            "item_ids": item_ids,
            "target_store_id": SHIPPED_STORE_TARGET_ID,
            **boundary.context_binding,
            "base_revision": f"sha256:{base_digest}",
            "rollback_artifact_sha256": base_digest,
        }

    @staticmethod
    def swap(
        kg_root: str | Path,
        merged_root: str | Path,
        *,
        promotion_document: Mapping[str, Any],
        staging_receipt: str | Path,
    ) -> dict:
        """Promote through the one installation-fixed authority boundary."""
        boundary = load_system_shipped_graph_operator_boundary(
            repository_root=REPOSITORY_ROOT,
            expected_target_store_id=SHIPPED_STORE_TARGET_ID,
        )
        with _exclusive_promotion_lock(boundary.replay_domain):
            return StoreMerger._swap_locked(
                kg_root,
                merged_root,
                promotion_document=promotion_document,
                staging_receipt=staging_receipt,
                boundary=boundary,
            )

    @staticmethod
    def _swap_locked(
        kg_root: str | Path,
        merged_root: str | Path,
        *,
        promotion_document: Mapping[str, Any],
        staging_receipt: str | Path,
        boundary: ShippedGraphOperatorBoundary,
    ) -> dict:
        if type(promotion_document) is not dict:
            raise RuntimeError("signed promotion document is required")
        if not isinstance(boundary, ShippedGraphOperatorBoundary):
            raise RuntimeError("fixed shipped-graph operator boundary is required")
        boundary.revalidate()
        live, candidate = _validate_store_paths(kg_root, merged_root)
        _assert_no_unresolved_swap_transactions(
            boundary.replay_domain,
            live=live,
        )

        # Re-run the evaluator and hash the current candidate/base under the
        # already-held global replay-domain lock.
        context = StoreMerger._promotion_context_with_boundary(
            live,
            candidate,
            staging_receipt=staging_receipt,
            boundary=boundary,
        )
        verified = verify_shipped_graph_promotion(
            promotion_document,
            trust_root=boundary.trust_root,
            live_context=context,
        )
        if verified.ok is not True or not isinstance(verified.payload_sha256, str):
            raise RuntimeError(f"promotion authorization rejected: {verified.reason}")

        nonce = promotion_document.get("nonce")
        if not isinstance(nonce, str):
            raise RuntimeError("verified promotion nonce is missing")
        transaction_id = hashlib.sha256(
            b"atanor.shipped-store-swap.v1\0"
            + verified.payload_sha256.encode("ascii")
            + b"\0"
            + boundary.replay_domain.binding_sha256.encode("ascii")
        ).hexdigest()
        nonce_name = (
            hashlib.sha256(nonce.encode("utf-8")).hexdigest()
            + ".consumed.json"
        )
        if (boundary.replay_domain.claims_root / nonce_name).exists():
            raise RuntimeError("promotion nonce was already consumed")
        previous = live.parent / f"{live.name}.prev.{transaction_id}"
        if previous.exists():
            raise RuntimeError("backup destination already exists")

        # Copy the authorized byte tree to a process-created sibling and bind
        # the bytes that will actually be renamed, rather than trusting the
        # mutable source candidate after preflight.
        sealed = live.parent / f"{candidate.name}.sealed.{transaction_id}"
        journal: SwapJournal | None = None
        try:
            shutil.copytree(candidate, sealed, symlinks=True)
            if _tree_sha256(sealed) != context["candidate_digest_sha256"]:
                raise RuntimeError(
                    "candidate changed while creating the sealed swap snapshot"
                )
            if _tree_sha256(live) != context["rollback_artifact_sha256"]:
                raise RuntimeError("live base changed after authorization preflight")
            sealed_sync = _sync_tree_files(sealed)
            journal = SwapJournal.prepare(
                replay_domain=boundary.replay_domain,
                transaction_id=transaction_id,
                promotion_document=promotion_document,
                promotion_payload_sha256=verified.payload_sha256,
                operator_key_id=str(verified.key_id),
                context=context,
                live=live,
                candidate=candidate,
                sealed=sealed,
                previous=previous,
                sealed_sync=sealed_sync,
            )
        except Exception:
            _discard_sealed_snapshot(sealed, approved_parent=live.parent)
            raise

        # Reload/revalidate the fixed config, key, identity manifest, lock, and
        # claims directory after the potentially long copy.
        try:
            boundary.revalidate()
            verified = verify_shipped_graph_promotion(
                promotion_document,
                trust_root=boundary.trust_root,
                live_context=context,
            )
            if (
                verified.ok is not True
                or not isinstance(verified.payload_sha256, str)
            ):
                raise RuntimeError(
                    f"promotion authorization rejected: {verified.reason}"
                )
            if _tree_sha256(sealed) != context["candidate_digest_sha256"]:
                raise RuntimeError("sealed candidate changed before nonce claim")
            if _tree_sha256(live) != context["rollback_artifact_sha256"]:
                raise RuntimeError("live base changed before nonce claim")
        except Exception:
            _discard_sealed_snapshot(sealed, approved_parent=live.parent)
            raise

        # Claim first: an uncertain or failed attempt is never replayable.
        nonce_receipt = _consume_promotion_nonce(
            boundary.replay_domain,
            document=promotion_document,
            verification_payload_sha256=verified.payload_sha256,
            context=context,
            previous=previous,
            sealed=sealed,
            transaction_id=transaction_id,
            intent_sha256=journal.intent_sha256,
            prepared_event_sha256=str(journal.last_event_sha256),
        )
        nonce_receipt_sha256 = hashlib.sha256(
            nonce_receipt.read_bytes()
        ).hexdigest()
        journal.record(
            "NONCE_CLAIMED",
            live=live,
            sealed=sealed,
            previous=previous,
            nonce_receipt_sha256=nonce_receipt_sha256,
        )

        # Detect the concrete race found by the adversarial review: mutation
        # during claim persistence must consume the nonce but must not install
        # unauthorized bytes.  This narrows the remaining race to the final
        # hash/rename window; only engine stop plus OS ACLs can close that
        # non-cooperating-writer window.
        if (
            _tree_sha256(sealed) != context["candidate_digest_sha256"]
            or _tree_sha256(live) != context["rollback_artifact_sha256"]
        ):
            raise RuntimeError(
                "swap bytes changed after nonce consumption; nonce remains consumed"
            )
        journal.record(
            "ARMED",
            live=live,
            sealed=sealed,
            previous=previous,
            nonce_receipt_sha256=nonce_receipt_sha256,
        )

        try:
            live.rename(previous)
            journal.namespace_directory_sync_verified = (
                journal.namespace_directory_sync_verified
                and _sync_directory(live.parent)
            )
            if _tree_sha256(previous) != context["rollback_artifact_sha256"]:
                if not live.exists() and previous.exists():
                    previous.rename(live)
                raise RuntimeError(
                    "recovery artifact changed before candidate install"
                )
            journal.record(
                "OLD_MOVED",
                live=live,
                sealed=sealed,
                previous=previous,
                nonce_receipt_sha256=nonce_receipt_sha256,
            )
            try:
                sealed.rename(live)
                journal.namespace_directory_sync_verified = (
                    journal.namespace_directory_sync_verified
                    and _sync_directory(live.parent)
                )
            except Exception:
                if not live.exists() and previous.exists():
                    previous.rename(live)
                raise
        except Exception as exc:
            try:
                phase = (
                    "ABORTED_NONCE_BURNED"
                    if live.exists()
                    else "RECOVERY_REQUIRED"
                )
                journal.record(
                    phase,
                    live=live,
                    sealed=sealed,
                    previous=previous,
                    nonce_receipt_sha256=nonce_receipt_sha256,
                )
            except Exception:
                pass
            raise RuntimeError(
                "signed promotion rename failed; nonce remains consumed"
            ) from exc

        installed_digest = _tree_sha256(live)
        recovery_digest = _tree_sha256(previous)
        if (
            installed_digest != context["candidate_digest_sha256"]
            or recovery_digest != context["rollback_artifact_sha256"]
        ):
            raise RuntimeError(
                "post-install digest mismatch; external recovery required and "
                "nonce remains consumed"
            )
        journal.record(
            (
                "INSTALLED_NAMESPACE_DURABLE"
                if journal.namespace_directory_sync_verified
                else "INSTALLED_NAMESPACE_OBSERVED"
            ),
            live=live,
            sealed=sealed,
            previous=previous,
            nonce_receipt_sha256=nonce_receipt_sha256,
        )
        committed_event_sha256 = journal.record(
            "COMMITTED",
            live=live,
            sealed=sealed,
            previous=previous,
            nonce_receipt_sha256=nonce_receipt_sha256,
        )
        return {
            "swapped": True,
            "journal_phase": "COMMITTED",
            "backup_prev_dir": str(previous),
            "new_live": str(live),
            "installed_digest_sha256": installed_digest,
            "recovery_digest_sha256": recovery_digest,
            "promotion_payload_sha256": verified.payload_sha256,
            "mutation_batch_manifest_sha256": context[
                "mutation_batch_manifest_sha256"
            ],
            "operator_key_id": verified.key_id,
            "operator_boundary_id": boundary.boundary_id,
            "operator_boundary_config_sha256": boundary.config_sha256,
            "nonce_replay_domain": boundary.replay_domain.binding,
            "nonce_receipt": str(nonce_receipt),
            "transaction_id": transaction_id,
            "swap_journal": str(journal.transaction_root),
            "committed_event_sha256": committed_event_sha256,
            "namespace_directory_sync_verified": (
                journal.namespace_directory_sync_verified
            ),
            "crash_durability_e4": (
                journal.namespace_directory_sync_verified
            ),
            "source_candidate_preserved": str(candidate),
            "rollback_in_process_enabled": False,
            "recovery_artifact": str(previous),
            "single_writer_enforcement": "external_engine_stop_and_acl_required",
        }

    @staticmethod
    def rollback(kg_root: str | Path) -> dict:
        """Fail closed until a distinct signed rollback authorization is specified.

        A promotion signature cannot be reused as rollback authority. Recovery currently
        requires an external operator-controlled service to rename the reported backup.
        """
        raise RuntimeError(
            "in-process rollback is disabled: no signed rollback authorization schema exists"
        )

# ----------------------------------------------------------------------------------------
# firewall glue (observe-only nogood pre-check over the T0 operator axioms)
# ----------------------------------------------------------------------------------------
def firewall_nogood_check(staged_root: str | Path, provenance: str,
                          t0_facts: list[tuple[str, str, str]],
                          *, restrict_to_t0_predicates: bool = True,
                          manifest_out: str | Path | None = None) -> dict:
    """Route staged edges through the live-membrane FirewallStagePass (observe-only) with the
    T0 operator axioms seeded, so any staged edge contradicting an axiom on a FUNCTIONAL
    predicate (e.g. capital(France)=Lyon vs the axiom capital(France)=Paris) is quarantined.
    Restricts to edges whose predicate appears in a T0 axiom (the only ones that CAN clash),
    which keeps the pass cheap at 10^7 scale. Never opens or writes any store.

    If ``manifest_out`` is given, the firewall's provenance/nogood manifest is written there via
    live_membrane.write_manifest, which REFUSES any path under data/graph_scale (out-of-tree only)."""
    import sys
    REPO = Path(__file__).resolve().parents[1]
    if str(REPO) not in sys.path:
        sys.path.insert(0, str(REPO))
    from packages.truth_maintenance.live_membrane import FirewallStagePass, write_manifest

    staged = ReadOnlyStore(staged_root)
    try:
        fp = FirewallStagePass(provenance=provenance, t0_facts=tuple(t0_facts))
        t0_preds = {p for (_s, p, _o) in t0_facts}
        st_s, st_p, st_o = staged.col("s"), staged.col("p"), staged.col("o")
        # resolve the staged gids of the T0 predicates once
        want_pids = {staged.lookup(p) for p in t0_preds}
        want_pids.discard(None)
        if restrict_to_t0_predicates and want_pids:
            mask = np.isin(st_p, list(want_pids))
            rows = np.nonzero(mask)[0]
        else:
            rows = range(len(st_s))
        for i in rows:
            i = int(i)
            fp.observe(staged.term(int(st_s[i])), staged.term(int(st_p[i])), staged.term(int(st_o[i])))
        manifest_path = None
        if manifest_out is not None:
            manifest_path = str(write_manifest(fp, manifest_out))
        return {"observed": fp.observed, "passed": fp.passed,
                "quarantined": fp.quarantined, "nogoods": fp.nogoods,
                "t0_facts": [list(f) for f in t0_facts],
                "manifest_out": manifest_path}
    finally:
        staged.close()
