"""Adversarial tests for the only shipped-store promotion rename boundary."""
from __future__ import annotations

import base64
import hashlib
import json
import os
import shutil
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

REPO_ROOT = Path(__file__).resolve().parents[2]
for path in (str(REPO_ROOT), str(REPO_ROOT / "scripts")):
    if path not in sys.path:
        sys.path.insert(0, path)

import landing_chain_lib as landing  # noqa: E402
import install_signed_shipped_graph as installer  # noqa: E402
import promote_staging_to_shipped as promoter  # noqa: E402
from packages.autonomy_envelope.audit_ledger import AuditLedger  # noqa: E402
from packages.autonomy_envelope.operator_trust import (  # noqa: E402
    ED25519_SCHEME,
    SHIPPED_GRAPH_PURPOSE,
    SHIPPED_GRAPH_SCHEMA_VERSION,
    SIGNATURE_FIELD,
    OperatorTrustRoot,
    canonical_payload_bytes,
    payload_sha256,
)
from packages.autonomy_envelope.promotion_queue import (  # noqa: E402
    REQUIRED_CONFIRMATION_PHRASE,
    NightlyPromotionQueue,
)
from packages.graph_scale.triple_store import TripleStore  # noqa: E402
from packages.graph_scale.mutation_batch import (  # noqa: E402
    GraphAddition,
    MutationStage,
    create_mutation_batch,
    record_applied_receipt,
    record_lifecycle_receipt,
    validate_mutation_batch,
)


def _build_store(root: Path, triples: list[tuple[str, str, str]]) -> None:
    store = TripleStore(root, dict_backend="sharded")
    for subject, predicate, object_ in triples:
        store.add(subject, predicate, object_)
    store.flush()
    store.terms.flush()
    store.rebuild_index()
    if hasattr(store.terms, "close"):
        store.terms.close()


def _keypair() -> tuple[Ed25519PrivateKey, OperatorTrustRoot, bytes]:
    private = Ed25519PrivateKey.generate()
    public = private.public_key()
    raw = public.public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw,
    )
    pem = public.public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    )
    key_id = f"ed25519:{hashlib.sha256(raw).hexdigest()[:24]}"
    return private, OperatorTrustRoot(pem, expected_key_id=key_id), pem


def _sign(document: dict, private: Ed25519PrivateKey, root: OperatorTrustRoot) -> dict:
    document = dict(document)
    signature = private.sign(canonical_payload_bytes(document))
    document[SIGNATURE_FIELD] = {
        "scheme": ED25519_SCHEME,
        "key_id": root.key_id,
        "payload_sha256": payload_sha256(document),
        "signature": base64.b64encode(signature).decode("ascii"),
    }
    return document


def _staging_receipt(lane: Path, live: Path, candidate: Path) -> Path:
    candidate_payload = landing.StoreMerger.staging_receipt_payload(live, candidate)
    queue = NightlyPromotionQueue(
        lane / "operator-confirmed-receipts",
        AuditLedger(lane / "operator-confirmed-receipts" / "audit.jsonl"),
    )
    queue.queue(candidate_payload)
    result = queue.sign_batch(
        operator_confirmed=True,
        confirmation_phrase=REQUIRED_CONFIRMATION_PHRASE,
        operator_id="test-operator",
    )
    assert result["allowed"] is True
    return Path(result["manifest_path"])


def _canonical_json(value: dict) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


def _provision_boundary(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    *,
    trust_root: OperatorTrustRoot,
    public_key_pem: bytes,
) -> tuple[landing.ShippedGraphOperatorBoundary, Path]:
    external = tmp_path / "operator-boundary"
    external.mkdir()
    key_path = external / "operator.pub.pem"
    key_path.write_bytes(public_key_pem)
    ledger = external / "promotion-nonces"
    ledger.mkdir()
    ledger_id = "atanor:promotion-ledger:test-domain-00000001"
    identity = {
        "schema_version": "atanor.promotion-nonce-ledger-identity.v1",
        "ledger_id": ledger_id,
        "target_store_id": landing.SHIPPED_STORE_TARGET_ID,
        "lock_relative_path": ".shipped-store-promotion.lock",
        "claims_relative_path": "claims",
    }
    (ledger / "promotion-nonce-ledger-identity.json").write_bytes(
        _canonical_json(identity)
    )
    (ledger / ".shipped-store-promotion.lock").write_bytes(b"\0")
    (ledger / "claims").mkdir()
    config = {
        "schema_version": (
            "atanor.shipped-graph-operator-boundary-config.v1"
        ),
        "boundary_id": "atanor:test:shipped-graph-boundary",
        "target_store_id": landing.SHIPPED_STORE_TARGET_ID,
        "operator_public_key_path": str(key_path.resolve()),
        "operator_key_id": trust_root.key_id,
        "nonce_ledger_path": str(ledger.resolve()),
        "nonce_ledger_id": ledger_id,
    }
    config_path = external / "shipped_graph_promotion.v1.json"
    config_path.write_bytes(_canonical_json(config))
    monkeypatch.setattr(
        landing,
        "SYSTEM_SHIPPED_GRAPH_OPERATOR_BOUNDARY_CONFIG",
        config_path,
    )
    boundary = landing.load_system_shipped_graph_operator_boundary(
        repository_root=landing.REPOSITORY_ROOT,
        expected_target_store_id=landing.SHIPPED_STORE_TARGET_ID,
    )
    return boundary, ledger


def _fixture(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> dict:
    lane = tmp_path / "approved-lane"
    live = lane / "kg_triples"
    staged = tmp_path / "source-staging"
    candidate = lane / "kg_triples.staged_merge.test"
    lane.mkdir()
    _build_store(
        live,
        [
            ("france", "capital", "paris"),
            ("dog", "is_a", "animal"),
        ],
    )
    base_digest = landing._tree_sha256(live)
    batch = create_mutation_batch(
        producer_id="promotion_test",
        producer_run_id=f"run-{tmp_path.name}",
        base_digest_sha256=base_digest,
        additions=(
            GraphAddition(
                "germany",
                "capital",
                "berlin",
                "curated:test",
                ("urn:test:germany",),
            ),
        ),
        batches_root=tmp_path / "mutation-batches",
    )
    record_lifecycle_receipt(batch.root, stage="detected")
    record_lifecycle_receipt(batch.root, stage="proposed")
    merger = landing.StoreMerger(live, live)
    built = merger.build_mutation_candidate(
        candidate,
        mutation_batch_root=batch.root,
    )
    assert built["verified"] is True
    monkeypatch.setattr(landing, "CANONICAL_SHIPPED_ROOT", live.resolve())

    private, trust_root, pem = _keypair()
    boundary, ledger = _provision_boundary(
        tmp_path,
        monkeypatch,
        trust_root=trust_root,
        public_key_pem=pem,
    )
    receipt = _staging_receipt(lane, live, candidate)
    context = landing.StoreMerger.promotion_context(
        live,
        candidate,
        staging_receipt=receipt,
    )
    now = datetime.now(timezone.utc).replace(microsecond=0)
    payload = {
        "schema_version": SHIPPED_GRAPH_SCHEMA_VERSION,
        "purpose": SHIPPED_GRAPH_PURPOSE,
        "merge_authorized": True,
        "production_store_mutated": False,
        "rollback_required": True,
        **context,
        "issued_at": (now - timedelta(minutes=1)).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "expires_at": (now + timedelta(minutes=10)).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "nonce": f"promotion-nonce-{tmp_path.name}",
    }
    document = _sign(payload, private, trust_root)
    return {
        "lane": lane,
        "live": live,
        "staged": staged,
        "candidate": candidate,
        "receipt": receipt,
        "document": document,
        "boundary": boundary,
        "ledger": ledger,
        "mutation_batch": batch,
    }


def _swap(fixture: dict) -> dict:
    return landing.StoreMerger.swap(
        fixture["live"],
        fixture["candidate"],
        promotion_document=fixture["document"],
        staging_receipt=fixture["receipt"],
    )


def test_old_flag_only_swap_and_unsigned_rollback_are_disabled(tmp_path) -> None:
    args = SimpleNamespace(i_am_operator=True)
    assert promoter.do_swap(args) == 2
    assert promoter.do_rollback(args) == 2
    with pytest.raises(TypeError):
        landing.StoreMerger.swap(tmp_path / "live", tmp_path / "candidate")
    with pytest.raises(RuntimeError, match="signed rollback authorization"):
        landing.StoreMerger.rollback(tmp_path / "live")


def test_promote_cli_requires_and_builds_exact_proposed_batch(
    tmp_path,
) -> None:
    live = tmp_path / "kg_triples"
    _build_store(live, [("france", "capital", "paris")])
    batch = create_mutation_batch(
        producer_id="promotion_cli_test",
        producer_run_id="run-build",
        base_digest_sha256=landing._tree_sha256(live),
        additions=(
            GraphAddition(
                "germany",
                "capital",
                "berlin",
                "curated:test",
            ),
        ),
        batches_root=tmp_path / "mutation-batches",
    )
    record_lifecycle_receipt(batch.root, stage="detected")
    record_lifecycle_receipt(batch.root, stage="proposed")

    missing = SimpleNamespace(
        i_am_operator=True,
        mutation_batch="",
        shipped=str(live),
    )
    assert promoter.do_promote(missing) == 2

    args = SimpleNamespace(
        i_am_operator=True,
        mutation_batch=str(batch.root),
        shipped=str(live),
    )
    assert promoter.do_promote(args) == 0
    candidates = list(
        live.parent.glob(f"kg_triples.staged_merge.{batch.batch_id}.*")
    )
    assert len(candidates) == 1
    assert validate_mutation_batch(batch.root).latest_stage is MutationStage.STAGED
    assert landing._tree_sha256(live) == batch.base_digest_sha256


def test_swap_cli_records_applied_receipt_from_committed_journal(
    tmp_path,
    monkeypatch,
) -> None:
    fixture = _fixture(tmp_path, monkeypatch)
    document_path = tmp_path / "promotion-document.json"
    document_path.write_text(
        json.dumps(fixture["document"], ensure_ascii=False),
        encoding="utf-8",
    )
    monkeypatch.setattr(promoter, "DEF_SHIPPED", fixture["live"])
    monkeypatch.setattr(promoter, "REPORT_DIR", tmp_path / "reports")
    args = SimpleNamespace(
        i_am_operator=True,
        mutation_batch=str(fixture["mutation_batch"].root),
        shipped=str(fixture["live"]),
        merged=str(fixture["candidate"]),
        promotion_document=str(document_path),
        staging_receipt=str(fixture["receipt"]),
    )

    assert promoter.do_swap(args) == 0
    validation = validate_mutation_batch(fixture["mutation_batch"].root)
    assert validation.latest_stage is MutationStage.APPLIED
    assert (fixture["mutation_batch"].root / "receipts" / "0004.applied.json").is_file()


def test_valid_signed_context_swaps_sealed_bytes_and_consumes_nonce(
    tmp_path, monkeypatch
) -> None:
    fixture = _fixture(tmp_path, monkeypatch)
    authorized_digest = fixture["document"]["candidate_digest_sha256"]
    result = _swap(fixture)

    assert result["swapped"] is True
    assert result["rollback_in_process_enabled"] is False
    assert Path(result["backup_prev_dir"]).is_dir()
    assert Path(result["nonce_receipt"]).is_file()
    journal = Path(result["swap_journal"])
    phases = [
        path.name.split(".", 2)[1]
        for path in sorted(journal.glob("[0-9]*.*.json"))
    ]
    installed_phase = (
        "INSTALLED_NAMESPACE_OBSERVED"
        if os.name == "nt"
        else "INSTALLED_NAMESPACE_DURABLE"
    )
    assert phases == [
        "PREPARED",
        "NONCE_CLAIMED",
        "ARMED",
        "OLD_MOVED",
        installed_phase,
        "COMMITTED",
    ]
    assert (journal / "intent.json").is_file()
    assert result["crash_durability_e4"] is (os.name != "nt")
    assert fixture["candidate"].is_dir(), "source candidate must remain preserved"
    assert landing._tree_sha256(fixture["live"]) == authorized_digest
    manifest_sha256 = fixture["mutation_batch"].manifest_sha256
    receipt = json.loads(fixture["receipt"].read_text(encoding="utf-8"))
    nonce_receipt = json.loads(
        Path(result["nonce_receipt"]).read_text(encoding="utf-8")
    )
    intent = json.loads(
        (journal / "intent.json").read_text(encoding="utf-8")
    )
    assert (
        receipt["entries"][0]["payload"][
            "mutation_batch_manifest_sha256"
        ]
        == fixture["document"]["mutation_batch_manifest_sha256"]
        == nonce_receipt["mutation_batch_manifest_sha256"]
        == intent["mutation_batch_manifest_sha256"]
        == result["mutation_batch_manifest_sha256"]
        == manifest_sha256
    )
    applied = record_applied_receipt(
        fixture["mutation_batch"].root,
        committed_promotion=result,
    )
    assert applied.is_file()
    assert (
        validate_mutation_batch(
            fixture["mutation_batch"].root
        ).latest_stage
        is MutationStage.APPLIED
    )


@pytest.mark.parametrize("truthy_ok", ["true", 1])
def test_forged_truthy_verify_report_is_independently_rejected(
    truthy_ok, tmp_path, monkeypatch
) -> None:
    fixture = _fixture(tmp_path, monkeypatch)
    report_path = fixture["candidate"] / "VERIFY_REPORT.json"
    forged = json.loads(report_path.read_text(encoding="utf-8"))
    forged["ok"] = truthy_ok
    (fixture["candidate"] / "VERIFY_REPORT.json").write_text(
        json.dumps(forged),
        encoding="utf-8",
    )
    with pytest.raises(RuntimeError, match="fresh passing evaluation"):
        _swap(fixture)
    assert fixture["live"].is_dir()
    assert fixture["candidate"].is_dir()
    assert not list((fixture["ledger"] / "claims").glob("*.consumed.json"))


def test_candidate_path_substitution_outside_approved_lane_is_rejected(
    tmp_path, monkeypatch
) -> None:
    fixture = _fixture(tmp_path, monkeypatch)
    outside = tmp_path / "outside" / fixture["candidate"].name
    outside.parent.mkdir()
    shutil.copytree(fixture["candidate"], outside)
    fixture["candidate"] = outside
    with pytest.raises(RuntimeError, match="approved staged-merge lane"):
        _swap(fixture)
    assert fixture["live"].is_dir()


def test_build_and_verify_cannot_write_into_or_below_shipped_store(
    tmp_path,
    monkeypatch,
) -> None:
    fixture = _fixture(tmp_path, monkeypatch)
    merger = landing.StoreMerger(fixture["live"], fixture["staged"])
    before = landing._tree_sha256(fixture["live"])

    with pytest.raises(RuntimeError, match="distinct|staged-merge lane"):
        merger.verify(fixture["live"])
    with pytest.raises(RuntimeError, match="staged-merge lane"):
        merger.build(fixture["live"] / "nested_candidate")

    assert not (fixture["live"] / "VERIFY_REPORT.json").exists()
    assert not (fixture["live"] / "nested_candidate").exists()
    assert landing._tree_sha256(fixture["live"]) == before


@pytest.mark.parametrize("target", ["candidate", "base", "receipt"])
def test_signed_context_rejects_post_signature_byte_mutation(
    target, tmp_path, monkeypatch
) -> None:
    fixture = _fixture(tmp_path, monkeypatch)
    if target == "candidate":
        with (fixture["candidate"] / "BUILD_REPORT.json").open("ab") as handle:
            handle.write(b" ")
    elif target == "base":
        with (fixture["live"] / "meta.json").open("ab") as handle:
            handle.write(b" ")
    else:
        receipt = json.loads(fixture["receipt"].read_text(encoding="utf-8"))
        receipt["note"] += " edited"
        fixture["receipt"].write_text(
            json.dumps(receipt, ensure_ascii=False, indent=2, sort_keys=True),
            encoding="utf-8",
        )
    with pytest.raises(RuntimeError):
        _swap(fixture)
    assert fixture["live"].is_dir()
    assert not list((fixture["ledger"] / "claims").glob("*.consumed.json"))


def test_consumed_nonce_blocks_retry_after_rename_failure(tmp_path, monkeypatch) -> None:
    fixture = _fixture(tmp_path, monkeypatch)
    original_rename = Path.rename

    def fail_live_rename(path: Path, target: Path):
        if path == fixture["live"]:
            raise OSError("injected rename failure")
        return original_rename(path, target)

    with monkeypatch.context() as scoped:
        scoped.setattr(Path, "rename", fail_live_rename)
        with pytest.raises(RuntimeError, match="nonce remains consumed"):
            _swap(fixture)
    assert fixture["live"].is_dir()
    assert len(
        list((fixture["ledger"] / "claims").glob("*.consumed.json"))
    ) == 1

    with pytest.raises(RuntimeError, match="already consumed"):
        _swap(fixture)
    assert fixture["live"].is_dir()


def test_mutation_during_nonce_claim_burns_nonce_without_install(
    tmp_path, monkeypatch
) -> None:
    fixture = _fixture(tmp_path, monkeypatch)
    original_consume = landing._consume_promotion_nonce

    def consume_then_mutate(replay_domain, **kwargs):
        receipt = original_consume(replay_domain, **kwargs)
        with (kwargs["sealed"] / "BUILD_REPORT.json").open("ab") as handle:
            handle.write(b" ")
        return receipt

    monkeypatch.setattr(
        landing,
        "_consume_promotion_nonce",
        consume_then_mutate,
    )
    original_live_digest = landing._tree_sha256(fixture["live"])

    with pytest.raises(
        RuntimeError,
        match="changed after nonce consumption",
    ):
        _swap(fixture)
    assert landing._tree_sha256(fixture["live"]) == original_live_digest
    assert len(
        list((fixture["ledger"] / "claims").glob("*.consumed.json"))
    ) == 1


def test_commit_journal_failure_never_returns_success_and_blocks_reentry(
    tmp_path, monkeypatch
) -> None:
    fixture = _fixture(tmp_path, monkeypatch)
    receipt_before = fixture["receipt"].read_bytes()
    original_record = landing.SwapJournal.record

    def fail_commit(journal, phase, **kwargs):
        if phase == "COMMITTED":
            raise OSError("injected COMMITTED journal failure")
        return original_record(journal, phase, **kwargs)

    with monkeypatch.context() as scoped:
        scoped.setattr(landing.SwapJournal, "record", fail_commit)
        with pytest.raises(OSError, match="COMMITTED journal failure"):
            _swap(fixture)

    transactions = (
        fixture["boundary"].replay_domain.claims_root
        / "transactions"
    )
    journals = list(transactions.iterdir())
    assert len(journals) == 1
    assert not list(journals[0].glob("*.COMMITTED.json"))
    assert fixture["receipt"].read_bytes() == receipt_before

    with pytest.raises(RuntimeError, match="unresolved shipped-store swap"):
        _swap(fixture)


def test_external_swap_lock_serializes_distinct_promotion_attempts(
    tmp_path, monkeypatch
) -> None:
    fixture = _fixture(tmp_path, monkeypatch)
    with landing._exclusive_promotion_lock(
        fixture["boundary"].replay_domain
    ):
        with pytest.raises(RuntimeError, match="already in progress"):
            _swap(fixture)
    assert fixture["live"].is_dir()
    assert not list((fixture["ledger"] / "claims").glob("*.consumed.json"))


def test_store_merger_api_rejects_caller_injected_key_and_ledger(
    tmp_path, monkeypatch
) -> None:
    fixture = _fixture(tmp_path, monkeypatch)
    _private, attacker_root, _pem = _keypair()

    with pytest.raises(TypeError):
        landing.StoreMerger.swap(
            fixture["live"],
            fixture["candidate"],
            promotion_document=fixture["document"],
            staging_receipt=fixture["receipt"],
            trust_root=attacker_root,
            nonce_ledger=tmp_path / "attacker-ledger",
        )


def test_copied_identity_in_fresh_ledger_changes_signed_replay_domain(
    tmp_path, monkeypatch
) -> None:
    fixture = _fixture(tmp_path, monkeypatch)
    ledger_b = fixture["ledger"].parent / "promotion-nonces-b"
    ledger_b.mkdir()
    shutil.copy2(
        fixture["ledger"] / "promotion-nonce-ledger-identity.json",
        ledger_b / "promotion-nonce-ledger-identity.json",
    )
    (ledger_b / ".shipped-store-promotion.lock").write_bytes(b"\0")
    (ledger_b / "claims").mkdir()

    domain_b = landing.PromotionReplayDomain.from_external_directory(
        ledger_b,
        repository_root=landing.REPOSITORY_ROOT,
        expected_ledger_id=fixture["boundary"].replay_domain.ledger_id,
        target_store_id=landing.SHIPPED_STORE_TARGET_ID,
    )
    assert (
        domain_b.identity_manifest_sha256
        == fixture["boundary"].replay_domain.identity_manifest_sha256
    )
    assert (
        domain_b.resolved_root_sha256
        != fixture["boundary"].replay_domain.resolved_root_sha256
    )

    config_path = landing.SYSTEM_SHIPPED_GRAPH_OPERATOR_BOUNDARY_CONFIG
    config = json.loads(config_path.read_text(encoding="utf-8"))
    config["nonce_ledger_path"] = str(ledger_b.resolve())
    config_path.write_bytes(_canonical_json(config))

    with pytest.raises(
        RuntimeError,
        match="promotion authorization rejected",
    ):
        _swap(fixture)
    assert not list((ledger_b / "claims").glob("*.consumed.json"))
    assert fixture["live"].is_dir()


def test_identity_manifest_mutation_after_signing_fails_before_claim(
    tmp_path, monkeypatch
) -> None:
    fixture = _fixture(tmp_path, monkeypatch)
    identity = fixture["ledger"] / "promotion-nonce-ledger-identity.json"
    identity.write_bytes(identity.read_bytes() + b"\n")

    with pytest.raises(RuntimeError, match="not canonical JSON"):
        _swap(fixture)
    assert not list(
        (fixture["ledger"] / "claims").glob("*.consumed.json")
    )
    assert fixture["live"].is_dir()


def test_missing_fixed_boundary_config_fails_closed(
    tmp_path, monkeypatch
) -> None:
    fixture = _fixture(tmp_path, monkeypatch)
    monkeypatch.setattr(
        landing,
        "SYSTEM_SHIPPED_GRAPH_OPERATOR_BOUNDARY_CONFIG",
        tmp_path / "missing-system-boundary.json",
    )

    with pytest.raises(RuntimeError, match="does not exist"):
        _swap(fixture)
    assert fixture["live"].is_dir()


def test_unresolved_swap_journal_blocks_all_later_promotions(
    tmp_path, monkeypatch
) -> None:
    fixture = _fixture(tmp_path, monkeypatch)
    unresolved = (
        fixture["boundary"].replay_domain.claims_root
        / "transactions"
        / ("a" * 64)
    )
    unresolved.mkdir(parents=True)
    before = landing._tree_sha256(fixture["live"])

    with pytest.raises(RuntimeError, match="unresolved shipped-store swap"):
        _swap(fixture)

    assert landing._tree_sha256(fixture["live"]) == before
    assert not list(
        fixture["boundary"].replay_domain.claims_root.glob(
            "*.consumed.json"
        )
    )


def test_deployment_accepts_only_committed_signed_generation(
    tmp_path, monkeypatch
) -> None:
    fixture = _fixture(tmp_path, monkeypatch)
    _swap(fixture)
    document_path = tmp_path / "promotion-document.json"
    document_path.write_text(
        json.dumps(fixture["document"], ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    seal = installer.verify_deployment_evidence(
        document_path,
        source_root=fixture["live"],
    )
    assert seal["source_digest_sha256"] == landing._tree_sha256(
        fixture["live"]
    )
    assert seal["schema_version"] == (
        "atanor.shipped-graph-deployment-seal.v2"
    )
    assert (
        seal["mutation_batch_manifest_sha256"]
        == fixture["mutation_batch"].manifest_sha256
    )

    rootfs = tmp_path / "rootfs"
    rootfs.mkdir()
    installed = installer.install(rootfs, document_path)
    installer.verify_copy(rootfs, document_path)
    destination = Path(installed["installed_path"])
    assert landing._tree_sha256(destination) == seal["source_digest_sha256"]
    assert (
        rootfs
        / "usr"
        / "share"
        / "atanor"
        / "evidence"
        / "shipped-graph"
        / "deployment-seal.json"
    ).is_file()


@pytest.mark.parametrize(
    "journal_file",
    ["promotion_document.json", "000006.COMMITTED.json"],
)
def test_deployment_rejects_tampered_committed_journal_file(
    journal_file, tmp_path, monkeypatch
) -> None:
    fixture = _fixture(tmp_path, monkeypatch)
    result = _swap(fixture)
    document_path = tmp_path / "promotion-document.json"
    document_path.write_text(
        json.dumps(fixture["document"]),
        encoding="utf-8",
    )
    target = Path(result["swap_journal"]) / journal_file
    target.write_bytes(target.read_bytes() + b"\n")

    with pytest.raises(RuntimeError):
        installer.verify_deployment_evidence(
            document_path,
            source_root=fixture["live"],
        )


def test_deployment_rejects_post_commit_source_tamper(
    tmp_path, monkeypatch
) -> None:
    fixture = _fixture(tmp_path, monkeypatch)
    _swap(fixture)
    document_path = tmp_path / "promotion-document.json"
    document_path.write_text(
        json.dumps(fixture["document"]),
        encoding="utf-8",
    )
    with (fixture["live"] / "meta.json").open("ab") as handle:
        handle.write(b" ")

    with pytest.raises(RuntimeError):
        installer.verify_deployment_evidence(
            document_path,
            source_root=fixture["live"],
        )
