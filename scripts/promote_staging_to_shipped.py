# -*- coding: utf-8 -*-
"""Promote one immutable GraphMutationBatch into the shipped graph.

The legacy S1 staging store remains available for read-only projection, but it
is not production authority and cannot be promoted directly. ``--promote``
requires a sealed proposed mutation batch and builds a verified all-or-nothing
candidate. ``--i-am-operator`` is only a presence gesture; it is never
authority. The final rename additionally requires the exact queue receipt and
a detached Ed25519 promotion document verified through the installation-fixed
external operator boundary.

MODES
-----
  --dry-run (default)  READ-ONLY. Projects the merge (net-new per relation, dup counts, new
                       terms) via the same planner the measurement uses; touches no store.
                       Optionally runs the firewall T0 nogood pre-check (--t0 --firewall).
  --promote            Builds a verified mixed add/retract candidate from
                       --mutation-batch. Does NOT swap. Requires
                       --i-am-operator.
  --receipt-payload    READ-ONLY. Prints the exact one-item candidate payload to enqueue for
                       NightlyPromotionQueue operator confirmation.
  --swap-context       READ-ONLY. Re-evaluates and hashes the candidate/base and binds the actual
                       NightlyPromotionQueue receipt for an external operator signer.
  --swap               Copies the signed candidate into a sealed sibling, re-hashes candidate
                       and live base, durably consumes the signed nonce, then renames. The prior
                       live store is preserved as a recovery artifact. After COMMITTED, records
                       the exact batch's applied receipt. The engine MUST be stopped.
  --rollback           DISABLED until a distinct signed rollback authorization schema exists.

SAFETY INVARIANTS
-----------------
  * measure-first  : dry-run refuses an incomplete legacy staging store.
                     Candidate build requires a sealed proposed batch bound to
                     the current shipped-tree digest.
  * back-up-first  : --swap preserves the live store by an ATOMIC rename to .prev.<ts> before
                     the merged dir takes its place (a rename cannot half-fail the way a copy
                     can; the merged dir is already a full independent copy of the original).
  * verify         : --swap independently recomputes verification; mutable report ``ok`` is not
                     trusted. Current candidate/base/report bytes are signature-bound.
  * replay         : an external O_EXCL+fsync nonce receipt is consumed immediately before rename.
  * recovery       : the prior live tree is retained, but in-process rollback remains disabled
                     rather than treating a promotion signature as rollback authority.
  * mutation scope : additions and retractions are exactly those in the sealed
                     batch; no implicit merge or mutable staging input.

  python scripts/promote_staging_to_shipped.py                 # dry-run projection
  python scripts/promote_staging_to_shipped.py --promote --i-am-operator \
      --mutation-batch <runtime/graph_mutation_spool/batches/gmb_...>
  python scripts/promote_staging_to_shipped.py --swap-context --merged <dir> \
      --staging-receipt <receipt.json>
  # --swap also needs --promotion-document, --staging-receipt, and --i-am-operator.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "scripts"))
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

import landing_chain_lib as L  # noqa: E402
from packages.graph_scale.graph_paths import SHIPPED_GRAPH_ROOT  # noqa: E402
from packages.graph_scale.mutation_batch import (  # noqa: E402
    MutationStage,
    load_validated_mutation_batch,
    record_applied_receipt,
)

DEF_STAGING = REPO / "data" / "graph_scale" / "staging_b1_wikidata"
DEF_SHIPPED = SHIPPED_GRAPH_ROOT
DEF_SOURCE_URL = "https://www.wikidata.org/w/index.php?search={s}"
REPORT_DIR = REPO / "runtime" / "promotion"
FIREWALL_OUT = REPO / "runtime" / "firewall" / "s1_wikidata_firewall_manifest.json"


def _rule(t: str) -> None:
    print("=" * 78)
    print(t)


def _require_complete(staging_root: Path) -> bool:
    ok, det = L.store_completeness(staging_root)
    print(json.dumps(det, indent=2, ensure_ascii=False))
    if not ok:
        print("\nREFUSING: staging store is incomplete / still being written by S1. The promoter\n"
              "runs only AFTER S1 has finished and finalized the store (and the engine is down).")
    return ok


def _load_t0(path: str) -> tuple[list[tuple[str, str, str]], str]:
    if not path or not Path(path).exists():
        return [], "wikidata-truthy"
    t0 = json.loads(Path(path).read_text(encoding="utf-8"))
    return [tuple(f) for f in t0.get("facts", [])], t0.get("provenance", "wikidata-truthy")


def do_dry_run(args) -> int:
    staging_root, shipped_root = Path(args.staging), Path(args.shipped)
    _rule("DRY-RUN — merge projection (READ-ONLY, writes nothing to any store)")
    if not _require_complete(staging_root) and not args.allow_incomplete:
        return 3
    plan = L.plan_merge(staging_root, shipped_root)
    t = plan["totals"]
    print(f"\n  shipped edges now      : {plan['shipped_edges']:,}")
    print(f"  staged distinct edges  : {t['staged_distinct']:,}")
    print(f"  duplicates of shipped  : {t['duplicates']:,}")
    print(f"  NET-NEW edges to add   : {t['net_new']:,}")
    print(f"  new terms to add       : {plan['n_new_terms']:,}")
    print(f"  shipped AFTER promote  : {t['projected_shipped_after']:,}")
    print("\n  per-relation (shipped -> +net_new):")
    for pred, d in plan["per_relation"].items():
        print(f"    {pred:<24} {d['shipped']:>10,} -> +{d['net_new']:<10,} "
              f"(dup {d['duplicates']:,})")
    # optional firewall
    if args.firewall:
        facts, prov = _load_t0(args.t0)
        _rule("FIREWALL T0 NOGOOD PRE-CHECK")
        if not facts:
            print("  no T0 seed (--t0) provided; skipping.")
        else:
            fw = L.firewall_nogood_check(staging_root, prov, facts)
            print(f"  T0 axioms: {len(facts):,}  checked: {fw['observed']:,}  "
                  f"passed: {fw['passed']:,}  QUARANTINED: {len(fw['quarantined']):,}")
            for q in fw["quarantined"][:30]:
                print(f"    NOGOOD {q['predicate']}({q['subject']})={q['object']} "
                      f"contradicts {q['contradicts']}")
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    out = REPORT_DIR / "S1_PROMOTION_DRYRUN.json"
    out.write_text(json.dumps(plan, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\n  projection written (out-of-tree): {out}")
    _rule("DRY-RUN done. If the numbers look right, run --promote --i-am-operator.")
    return 0


def do_promote(args) -> int:
    if not args.i_am_operator:
        print("REFUSING: --promote requires --i-am-operator.")
        return 2
    mutation_batch = str(getattr(args, "mutation_batch", "") or "").strip()
    if not mutation_batch:
        print(
            "REFUSING: legacy staging cannot authorize production. "
            "--promote requires --mutation-batch."
        )
        return 2
    shipped_root = Path(args.shipped)
    _rule("PROMOTE — build one sealed mutation candidate (no swap)")
    try:
        batch, _manifest, stage = load_validated_mutation_batch(
            mutation_batch,
            expected_base_digest_sha256=L._tree_sha256(shipped_root),
        )
    except Exception as exc:
        print(f"REFUSING: mutation batch is invalid or stale: {exc}")
        return 3
    if stage is not MutationStage.PROPOSED:
        print(
            "REFUSING: mutation batch lifecycle must be proposed before "
            "candidate assembly."
        )
        return 3
    ts = time.strftime("%Y%m%d_%H%M%S")
    merged = shipped_root.parent / (
        f"{shipped_root.name}.staged_merge.{batch.batch_id}.{ts}"
    )

    print(f"\n  building mutation candidate -> {merged}")
    merger = L.StoreMerger(shipped_root, shipped_root)
    try:
        breport = merger.build_mutation_candidate(
            merged,
            mutation_batch_root=batch.root,
        )
    except Exception as exc:
        print(f"\nCANDIDATE BUILD FAILED (live unchanged): {exc}")
        return 4
    print(json.dumps(breport, indent=2, ensure_ascii=False))

    _rule("FRESH VERIFY")
    vr = merger.verify(merged)
    print(json.dumps(vr, indent=2, ensure_ascii=False))

    if not vr["ok"]:
        print("\nVERIFY FAILED — the candidate did NOT pass. NOT promoting. Inspect "
              f"{merged}/VERIFY_REPORT.json. The live store is untouched.")
        return 4
    _rule("PROMOTE built + verified. Live store UNCHANGED until you run --swap.")
    print(
        "  next (read-only queue entry): python "
        "scripts/promote_staging_to_shipped.py --receipt-payload "
        f"--merged \"{merged}\""
    )
    print(
        "  swap remains BLOCKED until the installation-fixed external operator "
        "boundary is provisioned and its pinned signer issues the exact v3 document."
    )
    return 0


def do_swap(args) -> int:
    if getattr(args, "i_am_operator", False) is not True:
        print("REFUSING: --swap requires --i-am-operator.")
        return 2
    required = {
        "--merged": getattr(args, "merged", ""),
        "--mutation-batch": getattr(args, "mutation_batch", ""),
        "--promotion-document": getattr(args, "promotion_document", ""),
        "--staging-receipt": getattr(args, "staging_receipt", ""),
    }
    missing = [
        name for name, value in required.items()
        if not isinstance(value, str) or not value.strip()
    ]
    if missing:
        print(
            "REFUSING: --i-am-operator is only a human-presence gesture, not authority. "
            f"Missing signed-boundary inputs: {', '.join(missing)}"
        )
        return 2
    shipped_root = Path(args.shipped)
    try:
        if shipped_root.resolve(strict=True) != DEF_SHIPPED.resolve(strict=True):
            print("REFUSING: --swap target is not the canonical shipped store.")
            return 2
    except (FileNotFoundError, OSError):
        print("REFUSING: canonical shipped store is unavailable.")
        return 2
    merged = Path(args.merged)
    try:
        batch, _manifest, stage = load_validated_mutation_batch(
            args.mutation_batch,
        )
    except Exception as exc:
        print(f"REFUSING: mutation batch could not be validated: {exc}")
        return 2
    if stage is not MutationStage.STAGED:
        print("REFUSING: --swap requires the candidate's staged mutation batch.")
        return 2
    try:
        document = L._strict_json_object(
            Path(args.promotion_document).read_bytes(),
            label="promotion document",
        )
    except Exception as exc:
        print(f"REFUSING: signed promotion authority could not be loaded: {exc}")
        return 2
    if (
        document.get("mutation_batch_manifest_sha256")
        != batch.manifest_sha256
    ):
        print(
            "REFUSING: supplied mutation batch does not match the signed "
            "candidate document."
        )
        return 2
    _rule("SWAP - signed guarded replacement of the canonical live store")
    print(f"  merged (verified) : {merged}")
    print(f"  live target       : {shipped_root}")
    print(
        "\n  WARNING: the engine/watchdog MUST be stopped (single-writer) before swapping.\n"
        "  Windows refuses to rename a directory a live process has memory-mapped."
    )
    try:
        res = L.StoreMerger.swap(
            shipped_root,
            merged,
            promotion_document=document,
            staging_receipt=args.staging_receipt,
        )
    except Exception as exc:
        print(f"\nSWAP FAILED (fail-closed): {exc}")
        return 4
    if res.get("mutation_batch_manifest_sha256") != batch.manifest_sha256:
        print(
            "\nSWAP COMMITTED, BUT LIFECYCLE BINDING FAILED: committed result "
            "does not bind the supplied mutation batch."
        )
        return 5
    try:
        applied_receipt = record_applied_receipt(
            batch.root,
            committed_promotion=res,
        )
    except Exception as exc:
        print(
            "\nSWAP COMMITTED, BUT APPLIED RECEIPT FAILED: "
            f"{type(exc).__name__}: {exc}"
        )
        print(
            "Do not repeat the swap. Preserve the COMMITTED journal and "
            "reconcile the lifecycle receipt from that evidence."
        )
        return 5
    res = {
        **res,
        "applied_receipt": str(applied_receipt),
        "lifecycle_stage": MutationStage.APPLIED.value,
    }
    print(json.dumps(res, indent=2, ensure_ascii=False))
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    (REPORT_DIR / "S1_PROMOTION_SWAP.json").write_text(
        json.dumps(
            {**res, "ts": time.strftime("%Y-%m-%dT%H:%M:%S")},
            indent=2,
        ),
        encoding="utf-8",
    )
    _rule("SWAP done. Verify the live store answers, then restart the engine.")
    print(
        "  Recovery artifact is listed above. In-process rollback remains disabled; "
        "use the external operator-controlled recovery service."
    )
    return 0


def do_swap_context(args) -> int:
    """Print a fresh read-only context for the external operator signer."""
    if not isinstance(args.merged, str) or not args.merged.strip():
        print("REFUSING: --swap-context requires an explicit --merged candidate.")
        return 2
    receipt_path = getattr(args, "staging_receipt", "")
    if not isinstance(receipt_path, str) or not receipt_path.strip():
        print("REFUSING: --swap-context requires the actual --staging-receipt.")
        return 2
    shipped_root = Path(args.shipped)
    try:
        if shipped_root.resolve(strict=True) != DEF_SHIPPED.resolve(strict=True):
            print("REFUSING: context target is not the canonical shipped store.")
            return 2
        context = L.StoreMerger.promotion_context(
            shipped_root,
            Path(args.merged),
            staging_receipt=receipt_path,
        )
    except Exception as exc:
        print(f"REFUSING: candidate context could not be established: {exc}")
        return 4
    _rule("SIGNED SWAP CONTEXT (READ-ONLY; no authority, no mutation)")
    print(json.dumps(context, indent=2, ensure_ascii=False))
    print(
        "\nAn external operator signer must place these exact values in an unexpired "
        "atanor.shipped-graph-promotion-document.v3 document. Re-run this command after "
        "any store/report change; a stale signature will fail closed."
    )
    return 0


def do_receipt_payload(args) -> int:
    """Print the exact read-only candidate entry to enqueue for operator confirmation."""
    if not isinstance(args.merged, str) or not args.merged.strip():
        print("REFUSING: --receipt-payload requires an explicit --merged candidate.")
        return 2
    shipped_root = Path(args.shipped)
    try:
        if shipped_root.resolve(strict=True) != DEF_SHIPPED.resolve(strict=True):
            print("REFUSING: receipt target is not the canonical shipped store.")
            return 2
        payload = L.StoreMerger.staging_receipt_payload(
            shipped_root,
            Path(args.merged),
        )
    except Exception as exc:
        print(f"REFUSING: candidate receipt payload could not be established: {exc}")
        return 4
    _rule("NIGHTLY PROMOTION QUEUE ENTRY (READ-ONLY; no authority, no mutation)")
    print(json.dumps(payload, indent=2, ensure_ascii=False))
    print(
        "\nEnqueue this exact object as the single NightlyPromotionQueue item, then create "
        "the exclusive operator-confirmed staging receipt. That receipt remains unsigned "
        "and cannot authorize the shipped-store rename by itself."
    )
    return 0


def do_rollback(args) -> int:
    print(
        "REFUSING: in-process rollback is disabled. The promotion signature is not "
        "rollback authority; use an external operator-controlled recovery service with "
        "the preserved backup artifact."
    )
    return 2


def main() -> int:
    ap = argparse.ArgumentParser(description="S1 staging -> shipped safe promoter")
    ap.add_argument("--staging", default=str(DEF_STAGING))
    ap.add_argument("--shipped", default=str(DEF_SHIPPED))
    ap.add_argument("--provenance", default="wikidata-truthy")
    ap.add_argument("--source-url", default=DEF_SOURCE_URL)
    ap.add_argument("--t0", default="", help="T0 axiom seed json (build_t0_axioms.py output)")
    ap.add_argument("--merged", default="", help="explicit merged dir for --swap")
    ap.add_argument(
        "--mutation-batch",
        default="",
        help="sealed GraphMutationBatch root for --promote and --swap",
    )
    ap.add_argument("--promote", action="store_true")
    ap.add_argument("--swap", action="store_true")
    ap.add_argument(
        "--swap-context",
        action="store_true",
        help="read-only: print the fresh byte-bound context for an external signer",
    )
    ap.add_argument(
        "--receipt-payload",
        action="store_true",
        help="read-only: print the exact single item to enqueue before operator confirmation",
    )
    ap.add_argument("--rollback", action="store_true")
    ap.add_argument(
        "--promotion-document",
        default="",
        help="strict externally signed shipped-graph promotion JSON",
    )
    ap.add_argument(
        "--staging-receipt",
        default="",
        help="exclusive operator-confirmed NightlyPromotionQueue receipt for this candidate",
    )
    ap.add_argument("--firewall", action="store_true", help="run T0 nogood in --dry-run")
    ap.add_argument("--i-am-operator", dest="i_am_operator", action="store_true")
    ap.add_argument("--allow-incomplete", action="store_true")
    args = ap.parse_args()

    if args.rollback:
        return do_rollback(args)
    if args.swap:
        return do_swap(args)
    if args.swap_context:
        return do_swap_context(args)
    if args.receipt_payload:
        return do_receipt_payload(args)
    if args.promote:
        return do_promote(args)
    return do_dry_run(args)


if __name__ == "__main__":
    raise SystemExit(main())
