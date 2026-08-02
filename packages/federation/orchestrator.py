# -*- coding: utf-8 -*-
"""The dev-PC ORCHESTRATOR — monitors self-evolving nodes privately, gathers their VERIFIED-good
capabilities, integrates the promoted ones into a signed universal generation, and redistributes.

DOCTRINE (BINDING):
  * TWO-LAYER SPLIT (constitution 3): the orchestrator writes ONLY the UNIVERSAL layer — promoted
    capability SHAPES that become everyone's floor. It NEVER reads or writes any node's PERSONAL layer
    (subjectivity / felt-state / lived-record / local grounding). A node gains an ABILITY, never
    another node's memories or personhood. This is enforced structurally: every write goes through one
    chokepoint that REFUSES a path under the personal directory.
  * SEALED JUDGE (constitution 2): a contribution is integrated only on a promote verdict from
    judge.evaluate() against the developer-blind holdout — never on self-report.
  * SIGNED, ROLLBACKABLE GENERATIONS (constitution 5): each integration appends a generation to a
    hash-chained, HMAC-signed log. redistribute() emits the manifest of the generation at HEAD;
    rollback(to_generation) re-points HEAD to a prior generation (append-only — nothing is erased),
    giving instant regression recovery. (Honest scope: the signature is a local HMAC integrity seal;
    real networked federation would add per-node asymmetric signatures. See package README/report.)
"""
from __future__ import annotations

import hashlib
import hmac
import json
import os
import secrets
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from . import judge as judge_mod
from .contribution import Contribution


def repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _now() -> str:
    import datetime
    return datetime.datetime.now().replace(microsecond=0).isoformat()


def _canon(obj: Any) -> str:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


class PersonalLayerWriteError(RuntimeError):
    """Raised if federation code ever attempts to write a node's personal layer. Constitution 3 makes
    this structurally impossible: the ability federates, the personhood never does."""


# ======================================================================================
# The federation store — all on-disk state. Parametrized by data_dir so tests stay isolated.
# ======================================================================================
class FederationStore:
    """Owns the UNIVERSAL layer files and the signing key. Knows WHERE the personal layer lives only
    so it can REFUSE to write there — it never opens a personal file for writing."""

    def __init__(self, data_dir: Path | str | None = None):
        self.data_dir = Path(data_dir) if data_dir else (repo_root() / "data" / "federation")
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.universal_ledger = self.data_dir / "universal.jsonl"     # append-only promoted-capability log
        self.generations_log = self.data_dir / "generations.jsonl"   # append-only signed generation chain
        self.head_file = self.data_dir / "HEAD"                      # current active generation id
        self.key_file = self.data_dir / "orchestrator_key"          # local HMAC key (see doctrine)
        self.personal_dir = self.data_dir / "personal"              # NODE-owned; federation never writes here

    # ── the single write chokepoint (constitution 3 enforcement) ─────────────────────────────────
    def _guard(self, path: Path) -> Path:
        rp = path.resolve()
        pdir = self.personal_dir.resolve()
        if rp == pdir or pdir in rp.parents:
            raise PersonalLayerWriteError(
                f"federation refused to write a personal-layer path: {path} "
                f"(constitution 3: share the ability, never the personhood)")
        return path

    def _write_text(self, path: Path, text: str) -> Path:
        self._guard(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
        return path

    def _append_line(self, path: Path, obj: dict[str, Any]) -> None:
        self._guard(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as fh:
            fh.write(_canon(obj) + "\n")

    # ── signing key ──────────────────────────────────────────────────────────────────────────────
    def key(self) -> bytes:
        if not self.key_file.exists():
            self._write_text(self.key_file, secrets.token_hex(32))
        return bytes.fromhex(self.key_file.read_text(encoding="utf-8").strip())

    def sign(self, prev_signature: str, generation_id: str, capabilities: list[dict[str, Any]]) -> str:
        msg = (prev_signature + "|" + generation_id + "|" + _canon(capabilities)).encode("utf-8")
        return hmac.new(self.key(), msg, hashlib.sha256).hexdigest()

    # ── generations ────────────────────────────────────────────────────────────────────────────────
    def read_generations(self) -> list[dict[str, Any]]:
        if not self.generations_log.exists():
            return []
        out = []
        for line in self.generations_log.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line:
                out.append(json.loads(line))
        return out

    def generation(self, generation_id: str) -> dict[str, Any] | None:
        for g in self.read_generations():
            if g["generation_id"] == generation_id:
                return g
        return None

    def head(self) -> str | None:
        if self.head_file.exists():
            h = self.head_file.read_text(encoding="utf-8").strip()
            return h or None
        return None

    def set_head(self, generation_id: str) -> None:
        self._write_text(self.head_file, generation_id)

    def _next_generation_id(self) -> str:
        n = len(self.read_generations())
        return f"gen-{n + 1:04d}"

    def head_generation(self) -> dict[str, Any] | None:
        h = self.head()
        return self.generation(h) if h else None

    def universal_layer(self, generation_id: str | None = None) -> dict[str, dict[str, Any]]:
        """The universal capability layer as of a generation (default: HEAD). Keyed by capability_id;
        a later generation's capability replaces an earlier one with the same id."""
        gid = generation_id or self.head()
        if not gid:
            return {}
        layer: dict[str, dict[str, Any]] = {}
        for g in self.read_generations():
            for cap in g.get("capabilities", []):
                layer[cap["capability_id"]] = cap
            if g["generation_id"] == gid:
                break
        return layer

    # ── the node-owned personal layer (READ path only; never written by federation) ──────────────
    def personal_path(self, node_id: str) -> Path:
        return self.personal_dir / f"{node_id}.json"


# ======================================================================================
# The orchestrator.
# ======================================================================================
@dataclass
class ContributionReview:
    node_id: str
    capability_id: str
    capability_kind: str
    accepted: bool                        # passed sanitize AND the sealed judge
    stage: str                            # "sanitize" | "judge"
    sanitize_ok: bool
    sanitize_reasons: list[str] = field(default_factory=list)
    verdict: dict[str, Any] | None = None
    reason: str = ""

    def as_dict(self) -> dict[str, Any]:
        from dataclasses import asdict
        return asdict(self)


class Orchestrator:
    def __init__(self, store: FederationStore | None = None):
        self.store = store or FederationStore()

    # ── collect + judge (no promotion yet) ───────────────────────────────────────────────────────
    def review_contributions(self, contributions: list[Contribution]) -> list[ContributionReview]:
        """Sanitize each contribution (structure-only + privacy), then blind-judge the survivors
        against the current HEAD floor. Returns a review per contribution — promotion happens in
        integrate()."""
        floor = self.store.universal_layer()
        reviews: list[ContributionReview] = []
        for c in contributions:
            san = c.sanitize()
            if not san.ok or not c.kind_ok():
                reasons = list(san.reasons) + ([] if c.kind_ok() else ["bad_capability_kind"])
                reviews.append(ContributionReview(
                    node_id=c.node_id, capability_id=c.capability_id, capability_kind=c.capability_kind,
                    accepted=False, stage="sanitize", sanitize_ok=san.ok, sanitize_reasons=reasons,
                    reason=("rejected at sanitize (structure-not-data / privacy gate): "
                            + ", ".join(reasons))))
                continue
            v = judge_mod.evaluate(c, floor=floor)
            reviews.append(ContributionReview(
                node_id=c.node_id, capability_id=c.capability_id, capability_kind=c.capability_kind,
                accepted=bool(v.promote), stage="judge", sanitize_ok=True,
                verdict=v.as_dict(), reason=v.reason))
        return reviews

    # ── integrate the promoted capabilities into a NEW signed generation ─────────────────────────
    def integrate(self, contributions: list[Contribution]) -> dict[str, Any]:
        """Full pass: review -> promote the accepted -> append a signed generation -> advance HEAD.

        A generation is created only if at least one capability is promoted (no empty generations).
        Personal layers are never touched (the store's write chokepoint enforces it)."""
        reviews = self.review_contributions(contributions)
        accepted = [c for c, r in zip(contributions, reviews) if r.accepted]

        result: dict[str, Any] = {
            "reviewed": len(contributions),
            "promoted": [r.capability_id for r in reviews if r.accepted],
            "rejected": [{"capability_id": r.capability_id, "stage": r.stage, "reason": r.reason}
                         for r in reviews if not r.accepted],
            "reviews": [r.as_dict() for r in reviews],
            "generation": None,
        }
        if not accepted:
            result["note"] = "no capability passed the sealed judge; no generation created"
            return result

        prev = self.store.head_generation()
        prev_sig = prev["signature"] if prev else ("0" * 64)
        gid = self.store._next_generation_id()
        capabilities = [{
            "node_id": c.node_id,
            "capability_id": c.capability_id,
            "capability_kind": c.capability_kind,
            "target_suite": c.target_suite,
            "payload": c.payload,                       # STRUCTURE ONLY (sanitize already enforced)
            "digest": c.digest(),
            "provenance": c.provenance,
        } for c in accepted]
        signature = self.store.sign(prev_sig, gid, capabilities)
        generation = {
            "generation_id": gid,
            "created_at": _now(),
            "parent": prev["generation_id"] if prev else None,
            "prev_signature": prev_sig,
            "signature": signature,
            "capability_ids": [c.capability_id for c in accepted],
            "capabilities": capabilities,
        }
        self.store._append_line(self.store.generations_log, generation)
        # flat audit ledger the task names explicitly (data/federation/universal.jsonl)
        for cap in capabilities:
            self.store._append_line(self.store.universal_ledger,
                                    {"generation_id": gid, "signature": signature, **cap})
        self.store.set_head(gid)
        result["generation"] = {"generation_id": gid, "signature": signature,
                                "parent": generation["parent"],
                                "capability_ids": generation["capability_ids"]}
        return result

    # ── redistribute: the signed manifest nodes ADOPT ────────────────────────────────────────────
    def redistribute(self, generation_id: str | None = None) -> dict[str, Any]:
        """The signed universal manifest a node pulls to gain the floor. Contains capability SHAPES
        only — no personal data can be in it (nothing personal was ever written). Verifiable: a node
        recomputes the hash chain and HMAC before adopting."""
        gid = generation_id or self.store.head()
        if not gid:
            return {"generation_id": None, "capabilities": [], "signature": None,
                    "note": "no universal generation yet"}
        layer = self.store.universal_layer(gid)
        gen = self.store.generation(gid)
        manifest = {
            "generation_id": gid,
            "signature": gen["signature"] if gen else None,
            "chain_valid": self.verify_chain(gid),
            "capabilities": [
                {"capability_id": cap["capability_id"], "capability_kind": cap["capability_kind"],
                 "target_suite": cap.get("target_suite", ""), "payload": cap["payload"],
                 "digest": cap.get("digest"), "source_node": cap.get("node_id")}
                for cap in layer.values()],
            "adopt_note": ("adopt these ABILITY shapes into your universal layer; your personal layer "
                           "(felt-state, lived-record, local grounding) is yours and is not in here"),
        }
        return manifest

    # ── rollback: instant regression recovery (constitution 5) ───────────────────────────────────
    def rollback(self, to_generation: str) -> dict[str, Any]:
        """Re-point HEAD to a prior generation. Append-only: nothing is erased, so a later generation
        can be re-adopted (roll-forward) just by re-pointing HEAD. Verifies the target's signature."""
        target = self.store.generation(to_generation)
        if not target:
            return {"ok": False, "reason": f"unknown generation {to_generation!r}"}
        if not self.verify_generation(to_generation):
            return {"ok": False, "reason": f"signature/chain invalid at {to_generation!r} — refusing rollback"}
        prev_head = self.store.head()
        self.store.set_head(to_generation)
        return {"ok": True, "from": prev_head, "to": to_generation,
                "universal_capability_ids": sorted(self.store.universal_layer(to_generation).keys())}

    # ── signature / chain verification ───────────────────────────────────────────────────────────
    def verify_generation(self, generation_id: str) -> bool:
        g = self.store.generation(generation_id)
        if not g:
            return False
        expect = self.store.sign(g["prev_signature"], g["generation_id"], g["capabilities"])
        return hmac.compare_digest(expect, g.get("signature", ""))

    def verify_chain(self, up_to: str | None = None) -> bool:
        """Every generation up to ``up_to`` (default: all) has a valid HMAC AND a correctly linked
        prev_signature. Tamper anywhere in the chain fails here."""
        prev_sig = "0" * 64
        for g in self.store.read_generations():
            if g.get("prev_signature") != prev_sig:
                return False
            if not self.verify_generation(g["generation_id"]):
                return False
            prev_sig = g["signature"]
            if up_to and g["generation_id"] == up_to:
                break
        return True


# ======================================================================================
# Node-side adoption (models what a node does with a manifest) — used by the demo + tests.
# ======================================================================================
def adopt(manifest: dict[str, Any], node_universal: dict[str, dict[str, Any]] | None = None
          ) -> dict[str, dict[str, Any]]:
    """A node installs the manifest's ABILITY shapes into ITS universal layer. Pure function over the
    node's universal dict — it CANNOT touch the node's personal layer (it is not even passed in)."""
    layer = dict(node_universal or {})
    for cap in manifest.get("capabilities", []):
        layer[cap["capability_id"]] = {
            "capability_kind": cap["capability_kind"], "payload": cap["payload"],
            "target_suite": cap.get("target_suite", ""), "source_node": cap.get("source_node")}
    return layer
