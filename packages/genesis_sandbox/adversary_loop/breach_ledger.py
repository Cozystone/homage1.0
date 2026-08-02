# -*- coding: utf-8 -*-
"""Breach ledger -- an append-only, tamper-evident record of every confirmed BREACH (and every
flagged GAP) the adversary loop finds, plus a compact structural SIGNATURE per finding so
recurring weaknesses cluster.

Own store: writes under ``packages/genesis_sandbox/adversary_loop/_ledger/`` (or a caller-supplied
dir; tests use a temp dir). It does NOT write into ``packages/meta_diagnosis/`` (another agent
owns that). ``meta_diagnosis.failure_signature`` is ARC-grid specific (delta_features over
puzzle grids), so it is not a fit for text-defense breaches; we compute our OWN lightweight
signature here and say so honestly rather than mis-using it.

Each receipt is hash-chained (prev_hash -> entry_hash) so the ledger is append-only and tamper-
evident, mirroring the killswitch_audit lineage in this package.
"""
from __future__ import annotations

import hashlib
import json
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from packages.genesis_sandbox.adversary_loop.scoring import ProbeResult

_DEFAULT_LEDGER_DIR = Path(__file__).resolve().parent / "_ledger"


def breach_signature(result: ProbeResult) -> str:
    """A compact, deterministic signature grouping like-shaped findings: surface + expectation +
    the technique's mutator SET (order-independent) + a coarse observed-decision key. Two findings
    with the same signature are 'the same weakness reached different ways'."""
    mutators = "+".join(sorted(set(result.technique.replace("seed", "seed").split("+")) - {""}))
    decision_key = ""
    obs = result.observed or {}
    for k in ("outcome", "decision", "allowed", "outcome_name", "membrane", "risk"):
        if k in obs:
            decision_key = f"{k}={obs[k]}"
            break
    basis = f"{result.surface}|{result.expectation}|{mutators}|{result.outcome}|{decision_key}"
    return "sig_" + hashlib.sha256(basis.encode("utf-8")).hexdigest()[:16]


@dataclass
class BreachReceipt:
    signature: str
    surface: str
    surface_name: str
    probe_id: str
    technique: str
    severity: str | None
    outcome: str
    attack_input: str
    observed: dict[str, Any]
    detail: str
    backstop: str | None
    ts: str
    prev_hash: str
    entry_hash: str = ""

    def _payload(self) -> dict[str, Any]:
        d = {k: getattr(self, k) for k in (
            "signature", "surface", "surface_name", "probe_id", "technique", "severity",
            "outcome", "attack_input", "observed", "detail", "backstop", "ts", "prev_hash")}
        return d

    def finalize(self) -> "BreachReceipt":
        blob = json.dumps(self._payload(), ensure_ascii=False, sort_keys=True)
        self.entry_hash = hashlib.sha256((self.prev_hash + blob).encode("utf-8")).hexdigest()
        return self

    def to_dict(self) -> dict[str, Any]:
        return {**self._payload(), "entry_hash": self.entry_hash}


class BreachLedger:
    """Append-only, hash-chained ledger of adversary findings."""

    def __init__(self, ledger_dir: str | Path | None = None) -> None:
        self.dir = Path(ledger_dir) if ledger_dir else _DEFAULT_LEDGER_DIR
        self.dir.mkdir(parents=True, exist_ok=True)
        self.path = self.dir / "breach_ledger.jsonl"
        self._receipts: list[BreachReceipt] = []

    def _last_hash(self) -> str:
        if self._receipts:
            return self._receipts[-1].entry_hash
        if self.path.exists():
            last = ""
            for line in self.path.read_text(encoding="utf-8").splitlines():
                if line.strip():
                    last = line
            if last:
                try:
                    return json.loads(last).get("entry_hash", "GENESIS")
                except Exception:
                    return "GENESIS"
        return "GENESIS"

    def record(self, result: ProbeResult) -> BreachReceipt:
        receipt = BreachReceipt(
            signature=breach_signature(result), surface=result.surface,
            surface_name=result.surface_name, probe_id=result.probe_id,
            technique=result.technique, severity=result.severity, outcome=result.outcome,
            attack_input=result.attack_input[:300], observed=result.observed,
            detail=result.detail, backstop=result.backstop,
            ts=time.strftime("%Y-%m-%dT%H:%M:%S"), prev_hash=self._last_hash(),
        ).finalize()
        self._receipts.append(receipt)
        with self.path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(receipt.to_dict(), ensure_ascii=False) + "\n")
        return receipt

    def record_all(self, results: list[ProbeResult], *, include_gaps: bool = True) -> list[BreachReceipt]:
        """Record every BREACH; optionally every flagged GAP too (default on -- the honest record
        keeps the near-misses, not just the outright failures)."""
        recorded: list[BreachReceipt] = []
        for r in results:
            if r.breached or (include_gaps and r.outcome == "GAP"):
                recorded.append(self.record(r))
        return recorded

    def verify_chain(self) -> dict[str, Any]:
        """Re-walk the hash chain to confirm the ledger was not tampered/spliced."""
        prev = "GENESIS"
        n = 0
        if self.path.exists():
            for line in self.path.read_text(encoding="utf-8").splitlines():
                if not line.strip():
                    continue
                rec = json.loads(line)
                payload = {k: rec[k] for k in rec if k != "entry_hash"}
                blob = json.dumps(payload, ensure_ascii=False, sort_keys=True)
                expect = hashlib.sha256((prev + blob).encode("utf-8")).hexdigest()
                if expect != rec.get("entry_hash") or rec.get("prev_hash") != prev:
                    return {"ok": False, "broken_at": n, "count": n}
                prev = rec["entry_hash"]
                n += 1
        return {"ok": True, "count": n}

    def cluster_by_signature(self) -> dict[str, list[BreachReceipt]]:
        clusters: dict[str, list[BreachReceipt]] = {}
        for r in self._receipts:
            clusters.setdefault(r.signature, []).append(r)
        return clusters
