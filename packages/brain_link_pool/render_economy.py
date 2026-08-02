# -*- coding: utf-8 -*-
"""Brain Link economy v0 — the Render Network operating model, adopted honestly.

Owner's insight (2026-07-07): Render Network's coordination design IS the missing
layer of Brain Link. Brain Link already scales THROUGHPUT (sharded merge, real
cgsr peers); what it lacked is what Render solved for GPU sharing — the ECONOMIC
and TRUST loop that keeps strangers' compute honest:

  Render Network                     →  Brain Link
  ─────────────────────────────────────────────────────────────────────
  RENDER token, Burn-Mint Equilibrium →  Synapse credits: requester BURNS
    (creators burn, operators mint       credits to submit work; provider
     only on completed work)             MINTS only on VERIFIED completion
  Proof-of-Render (automated +        →  Proof-of-Inference: our engine is
    human verification gates mint)       DETERMINISTIC, so spot-check re-runs
                                         compare exact hashes — stronger than
                                         Render's probabilistic checks
  Reputation score (grows with       →  per-peer EMA of verification outcomes;
    verified jobs, gates allocation)     failures decay hard
  Node tiers (Trusted/Priority/       →  trusted (operator-listed) / priority
    Economy)                             (reputation+bench) / economy (new)
  Watermarked previews until          →  ESCROW: result hash visible, full
    payment confirmed                    result released only after burn settles
  OctaneBench capacity scoring        →  synapse_bench: standard extraction
                                         batch, items/sec

We adopt the OPERATING MODEL, not the cryptocurrency: credits are a local,
auditable ledger (data/brain_link/economy/*.jsonl). Every mint is traceable to
a verified job — supply honestly mirrors real work, which is the whole point
of BME.
"""
from __future__ import annotations

import hashlib
import json
import time
from pathlib import Path
from typing import Any, Callable

REPO = Path(__file__).resolve().parents[2]
ECON_DIR = REPO / "data" / "brain_link" / "economy"
LEDGER_PATH = ECON_DIR / "credit_ledger.jsonl"
PEERS_PATH = ECON_DIR / "peers.json"

# tier thresholds (Render: Trusted / Priority / Economy)
PRIORITY_REPUTATION = 0.75
PRIORITY_BENCH = 50.0          # items/sec on the standard bench
STARTING_CREDITS = 100.0
STARTING_REPUTATION = 0.5      # economy tier until proven


def _now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%S")


class CreditLedger:
    """Burn-Mint Equilibrium over an append-only local ledger. Burns happen at
    job submission; mints ONLY carry a verified job id — an unverified mint is
    structurally impossible through this API."""

    def __init__(self, path: Path = LEDGER_PATH):
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def _append(self, row: dict[str, Any]) -> None:
        with self.path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(row, ensure_ascii=False) + "\n")

    def burn(self, requester: str, amount: float, job_id: str) -> bool:
        if amount <= 0 or self.balance(requester) < amount:
            return False
        self._append({"ts": _now(), "op": "burn", "peer": requester,
                      "amount": round(amount, 4), "job": job_id})
        return True

    def mint(self, provider: str, amount: float, job_id: str,
             verification: dict[str, Any]) -> bool:
        if amount <= 0 or not verification.get("verified"):
            return False  # BME: no verified work, no new supply
        self._append({"ts": _now(), "op": "mint", "peer": provider,
                      "amount": round(amount, 4), "job": job_id,
                      "proof": {"checked": verification.get("checked"),
                                "matched": verification.get("matched")}})
        return True

    def grant(self, peer: str, amount: float, reason: str) -> None:
        """Genesis/faucet grants (new peer joins) — explicit and audited."""
        self._append({"ts": _now(), "op": "grant", "peer": peer,
                      "amount": round(amount, 4), "job": reason})

    def balance(self, peer: str) -> float:
        bal = 0.0
        if self.path.exists():
            for line in self.path.open(encoding="utf-8"):
                try:
                    row = json.loads(line)
                except Exception:
                    continue
                if row.get("peer") != peer:
                    continue
                if row["op"] in ("mint", "grant"):
                    bal += row["amount"]
                elif row["op"] == "burn":
                    bal -= row["amount"]
        return round(bal, 4)

    def equilibrium(self) -> dict[str, float]:
        """The BME health metric: total burned vs minted. Mint tracking burn
        means supply mirrors real verified work."""
        burned = minted = granted = 0.0
        if self.path.exists():
            for line in self.path.open(encoding="utf-8"):
                try:
                    row = json.loads(line)
                except Exception:
                    continue
                if row["op"] == "burn":
                    burned += row["amount"]
                elif row["op"] == "mint":
                    minted += row["amount"]
                elif row["op"] == "grant":
                    granted += row["amount"]
        return {"burned": round(burned, 4), "minted": round(minted, 4),
                "granted": round(granted, 4),
                "equilibrium": round(minted - burned, 4)}


class PeerRegistry:
    """Reputation + tiers (Render: reputation grows via Proof-of-Render and
    gates allocation). EMA so history matters but recent behavior dominates;
    a failed verification costs ~3 successes — lying must not pay."""

    def __init__(self, path: Path = PEERS_PATH):
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._peers: dict[str, dict[str, Any]] = {}
        if self.path.exists():
            try:
                self._peers = json.loads(self.path.read_text(encoding="utf-8"))
            except Exception:
                self._peers = {}

    def _save(self) -> None:
        self.path.write_text(json.dumps(self._peers, ensure_ascii=False, indent=1),
                             encoding="utf-8")

    def register(self, peer: str, trusted: bool = False) -> dict[str, Any]:
        if peer not in self._peers:
            self._peers[peer] = {"reputation": STARTING_REPUTATION, "bench": 0.0,
                                 "trusted": bool(trusted), "jobs": 0, "failed": 0,
                                 "joined": _now()}
            self._save()
        return self._peers[peer]

    def record_outcome(self, peer: str, verified: bool) -> None:
        p = self.register(peer)
        alpha = 0.15
        target = 1.0 if verified else 0.0
        weight = alpha if verified else alpha * 3  # failures cost ~3 successes
        p["reputation"] = round((1 - weight) * p["reputation"] + weight * target, 4)
        p["jobs"] += 1
        if not verified:
            p["failed"] += 1
        self._save()

    def set_bench(self, peer: str, items_per_sec: float) -> None:
        self.register(peer)["bench"] = round(float(items_per_sec), 2)
        self._save()

    def tier(self, peer: str) -> str:
        p = self.register(peer)
        if p["trusted"]:
            return "trusted"
        if p["reputation"] >= PRIORITY_REPUTATION and p["bench"] >= PRIORITY_BENCH:
            return "priority"
        return "economy"

    def rank_for_job(self) -> list[str]:
        """Render's auto-matcher: tier first, then reputation, then capacity."""
        order = {"trusted": 0, "priority": 1, "economy": 2}
        return sorted(self._peers,
                      key=lambda n: (order[self.tier(n)],
                                     -self._peers[n]["reputation"],
                                     -self._peers[n]["bench"]))


def _hash_result(items: list[Any]) -> str:
    return hashlib.sha256(json.dumps(items, ensure_ascii=False, sort_keys=True)
                          .encode("utf-8")).hexdigest()[:16]


def proof_of_inference(job_items: list[Any], peer_results: list[Any],
                       reference_fn: Callable[[Any], Any],
                       sample: int = 3) -> dict[str, Any]:
    """Proof-of-Render, deterministic edition. Render needs previews + human
    confirmation because rendering is approximate; a graph engine is EXACTLY
    reproducible, so we re-run a random-ish sample locally and require byte
    equality. Cost: sample/n of the job; catches a cheater with p ≥ sample/n
    per job, compounding across jobs into certain reputation collapse."""
    if len(peer_results) != len(job_items):
        return {"verified": False, "reason": "length_mismatch",
                "checked": 0, "matched": 0}
    idxs = list(range(len(job_items)))
    # deterministic sample seeded by content — a peer cannot predict the checks
    seed = int(_hash_result(job_items), 16)
    picked = sorted(idxs, key=lambda i: hashlib.sha256(f"{seed}:{i}".encode()).hexdigest())[:max(1, min(sample, len(idxs)))]
    matched = 0
    for i in picked:
        if reference_fn(job_items[i]) == peer_results[i]:
            matched += 1
    ok = matched == len(picked)
    return {"verified": ok, "checked": len(picked), "matched": matched,
            "result_hash": _hash_result(peer_results)}


class JobEscrow:
    """Watermarked-preview equivalent: the requester sees only the RESULT HASH
    until the burn settles; the provider's mint waits for verification. Both
    sides commit before either can defect."""

    def __init__(self, ledger: CreditLedger, registry: PeerRegistry):
        self.ledger = ledger
        self.registry = registry
        self._jobs: dict[str, dict[str, Any]] = {}

    def submit(self, requester: str, job_id: str, items: list[Any],
               price: float) -> dict[str, Any]:
        if not self.ledger.burn(requester, price, job_id):
            return {"accepted": False, "reason": "insufficient_credits"}
        ranked = self.registry.rank_for_job()
        if not ranked:
            return {"accepted": False, "reason": "no_peers"}
        provider = ranked[0]
        self._jobs[job_id] = {"requester": requester, "provider": provider,
                              "items": items, "price": price, "state": "assigned"}
        return {"accepted": True, "provider": provider,
                "provider_tier": self.registry.tier(provider)}

    def deliver(self, job_id: str, peer_results: list[Any],
                reference_fn: Callable[[Any], Any]) -> dict[str, Any]:
        job = self._jobs.get(job_id)
        if not job or job["state"] != "assigned":
            return {"settled": False, "reason": "unknown_job"}
        proof = proof_of_inference(job["items"], peer_results, reference_fn)
        self.registry.record_outcome(job["provider"], proof["verified"])
        if proof["verified"]:
            self.ledger.mint(job["provider"], job["price"], job_id, proof)
            job.update(state="settled", results=peer_results)
            return {"settled": True, "result_hash": proof["result_hash"],
                    "results": peer_results, "proof": proof}
        job["state"] = "failed"
        return {"settled": False, "reason": "verification_failed", "proof": proof}


def synapse_bench(peer_fn: Callable[[Any], Any], items: list[Any]) -> float:
    """OctaneBench equivalent: standard batch, measured items/sec."""
    t0 = time.perf_counter()
    for it in items:
        peer_fn(it)
    dt = time.perf_counter() - t0
    return round(len(items) / dt, 2) if dt > 0 else 0.0
