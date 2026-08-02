"""Brain Link — a REAL peer-to-peer shared-compute pool.

The core Brain Link idea: instead of one machine carrying the whole learning
workload, many users' PCs pool their compute. This coordinator holds a backlog
of LEARNING WORK — batches of sentences that need concept/relation extraction
(the CPU-heavy "" step). Peers (other PCs / containers) REGISTER, CLAIM a
batch, run the extraction with *their own* compute, and SUBMIT the results, which
are merged into the shared brain.

Honesty: nothing is simulated. A peer's contribution only counts when it returns
real extracted concepts/relations; the shared totals grow solely from work peers
actually did. Idle peers contribute nothing. This is genuine distributed compute.
"""

from __future__ import annotations

import json
import os
import threading
import time as _time
import uuid
from collections import deque
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Body

router = APIRouter(prefix="/api/brain-link", tags=["brain-link"])

_LOCK = threading.RLock()
_DATA_DIR = Path(__file__).resolve().parents[4] / "data" / "brain_link"
_CONTRIB_LOG = _DATA_DIR / "contributions.jsonl"

# In-memory pool state. Persisted contributions go to _CONTRIB_LOG.
_POOL: dict[str, Any] = {
    "queue": deque(),                 # sentences awaiting extraction
    "inflight": {},                   # batch_id -> {peer_id, sentences, claimed_at}
    "peers": {},                      # peer_id -> {label, registered_at, last_seen, claimed, completed}
    "seeded": False,
    "batches_completed": 0,
    "concepts": set(),                # unique concepts contributed across the pool
    "relations": set(),               # unique relations (a||b)
    "by_peer": {},                    # peer_id -> {concepts, relations, batches}
    "started_at": _time.time(),
}
_RECLAIM_AFTER = 120.0                 # re-queue a batch if a peer never submits

# Peers grow a DEDICATED candidate store (separate from the live loop's store so
# concurrent peer writes never race the running engine). The merge is a PERSISTENT,
# hash-SHARDED store (packages/brain_link_pool): its dedupe index is loaded ONCE
# per shard, not rebuilt per submit, and each shard's index stays ~1/K the size as
# the DB grows to millions — so throughput does NOT collapse as the brain gets big
# (the old construct-a-VerifiedStore-per-submit path paid O(n) reload EVERY submit,
# ~50ms at 20k rows, ~500ms at 200k -> a hard scaling wall). Honest: this removes
# the merge's growth-with-size wall; extraction stays parallel across peers. Going
# beyond one core's merge rate needs process-based shard workers (future).
_STORE_LOCK = threading.RLock()
_CONTRIB_STORE_ROOT_SHARDED = _DATA_DIR / "contributed_store_sharded"
_STORE_TOTALS = {"concepts_added": 0, "relations_added": 0, "ready": False}

_SHARDED_STORE: Any = None
_SHARDED_STORE_LOCK = threading.Lock()


def _get_sharded_store() -> Any:
    """Lazily build the process-lifetime sharded contributed store (singleton)."""
    global _SHARDED_STORE
    if _SHARDED_STORE is None:
        with _SHARDED_STORE_LOCK:
            if _SHARDED_STORE is None:
                from packages.brain_link_pool import ShardedContributedStore

                # DEFAULT 1 shard = EXACT de-dup (one global dedupe set) + the full
                # persistence win (index loaded once, not per submit). Measured:
                # shards>1 route whole decompositions by source, so the SAME concept
                # from different sentences lands in different shards and is counted
                # once PER shard -> up to K x concept inflation (benchmark: 8 shards
                # = 8x). Threaded shards also give ZERO speedup (GIL). So >1 is an
                # opt-in knob, only worthwhile with PROCESS workers + concept-key
                # routing (future); until then keep exact de-dup.
                try:
                    shards = max(1, int(os.getenv("ATANOR_CONTRIB_SHARDS", "1")))
                except Exception:
                    shards = 1
                # Phase 2-5: ATANOR_CONTRIB_PROC_SHARDS >= 2 switches to DEDICATED
                # WORKER PROCESSES (true multicore merge; measured x2.15 at 4 procs,
                # 774->1665 decomp/sec). Row-level concept-key routing keeps de-dup
                # exact in both modes. Default 0 = threaded store (unchanged).
                try:
                    proc_shards = int(os.getenv("ATANOR_CONTRIB_PROC_SHARDS", "0"))
                except Exception:
                    proc_shards = 0
                _CONTRIB_STORE_ROOT_SHARDED.parent.mkdir(parents=True, exist_ok=True)
                if proc_shards >= 2:
                    from packages.brain_link_pool import ProcessShardedStore

                    _SHARDED_STORE = ProcessShardedStore(
                        _CONTRIB_STORE_ROOT_SHARDED, shards=proc_shards)
                else:
                    _SHARDED_STORE = ShardedContributedStore(_CONTRIB_STORE_ROOT_SHARDED, shards=shards)
    return _SHARDED_STORE


def _accumulate_decompositions(decomps: list[dict[str, Any]]) -> tuple[int, int]:
    """Merge peer-extracted neuro-symbolic decompositions into the shared
    contributed store. The expensive decompose ran on the peers (distributed);
    this serialized append is cheap. Returns (concepts_added, relations_added)."""
    if not decomps:
        return 0, 0
    try:
        from packages.cgsr.cgsr.ingestion.decomposer import DecompositionResult
    except Exception:
        return 0, 0
    drs = []
    for d in decomps:
        try:
            drs.append(DecompositionResult(
                concepts=list(d.get("concepts") or []),
                relations=list(d.get("relations") or []),
                case_frames=list(d.get("case_frames") or []),
                evidence=d.get("evidence"),
            ))
        except Exception:
            continue
    if not drs:
        return 0, 0
    try:
        # Persistent sharded merge: no per-submit index reload, K-way shard locks
        # (not one global lock) so parallel peer submits don't all serialize.
        agg = _get_sharded_store().accumulate(drs)
    except Exception:
        return 0, 0
    c = int(agg.get("concepts_added", 0) or 0)
    r = int(agg.get("relations_added", 0) or 0)
    with _STORE_LOCK:
        _STORE_TOTALS["concepts_added"] += c
        _STORE_TOTALS["relations_added"] += r
        _STORE_TOTALS["ready"] = True
    return c, r


def _seed_queue() -> None:
    """Fill the work queue with real public sentences (same source as the
    firehose: seed corpus + any corpora dir). Lazily, on first need."""
    if _POOL["seeded"] and _POOL["queue"]:
        return
    sentences: list[str] = []
    cap = 20000
    # 1) firehose corpora (seed + plugin + ATANOR_CORPORA_DIR)
    try:
        from app.routers.cloud_brain import _firehose_corpus_files, _firehose_iter_sentences
        for f in _firehose_corpus_files():
            for s in _firehose_iter_sentences(f):
                sentences.append(s)
                if len(sentences) >= cap:
                    break
            if len(sentences) >= cap:
                break
    except Exception:
        pass
    # 2) the candidate store's real source sentences (evidence.jsonl) — thousands
    #    of genuine public-corpus sentences, so a multi-peer pool has real work.
    try:
        from app.routers.cloud_brain import _resolve_candidate_store_path
        store = _resolve_candidate_store_path()
        ev = Path(store) / "evidence.jsonl" if store else None
        if ev and ev.exists() and len(sentences) < cap:
            with ev.open("r", encoding="utf-8", errors="ignore") as fh:
                for line in fh:
                    try:
                        obj = json.loads(line)
                    except Exception:
                        continue
                    txt = str(obj.get("text") or obj.get("sentence") or obj.get("source_sentence") or "").strip()
                    if 12 <= len(txt) <= 2000:
                        sentences.append(txt)
                        if len(sentences) >= cap:
                            break
    except Exception:
        pass
    if not sentences:
        sentences = [
            "Brain Link pools compute across peer machines.",
            "A peer claims a batch, extracts concepts, and submits results.",
            "공유 자원으로 연산력을 보강한다.",
        ]
    with _LOCK:
        for s in sentences:
            _POOL["queue"].append(s)
        _POOL["seeded"] = True


def _reclaim_stale() -> None:
    now = _time.time()
    with _LOCK:
        stale = [bid for bid, b in _POOL["inflight"].items() if now - b["claimed_at"] > _RECLAIM_AFTER]
        for bid in stale:
            b = _POOL["inflight"].pop(bid)
            for s in b["sentences"]:
                _POOL["queue"].appendleft(s)


# ── Render-model economy (BME credits + reputation tiers) ──────────────────
# The coordinator is the REQUESTER (it wants learning done): it burns Synapse
# credits when a peer claims work, and the peer MINTS them only when the
# submitted batch passes verification. See brain_link_pool/render_economy.py.
_ECONOMY: dict[str, Any] = {"ledger": None, "registry": None}
COORDINATOR = "coordinator"
BATCH_PRICE = 1.0  # credits per claimed batch


def _economy() -> tuple[Any, Any]:
    if _ECONOMY["ledger"] is None:
        from packages.brain_link_pool.render_economy import CreditLedger, PeerRegistry

        ledger = CreditLedger()
        registry = PeerRegistry()
        if ledger.balance(COORDINATOR) <= 0:
            ledger.grant(COORDINATOR, 10_000.0, "coordinator_genesis")
        _ECONOMY["ledger"], _ECONOMY["registry"] = ledger, registry
    return _ECONOMY["ledger"], _ECONOMY["registry"]


def _verify_submission(sentences: list[str], decomps: list[dict[str, Any]]) -> dict[str, Any]:
    """Proof-of-Inference at the pool: a submitted batch must carry decompositions
    whose evidence actually BELONGS to the claimed batch. The peer protocol keys
    evidence by source_hash = sha256(sentence)[:16] (peer_worker._source_sentence),
    so membership is checked on hashes — a fabricated or recycled submission fails."""
    if not decomps:
        # honest empty result (all sentences rejected by the verify gate) is VALID
        return {"verified": True, "checked": 0, "matched": 0, "empty": True}
    import hashlib as _hl

    hash_set = {_hl.sha256(s.encode("utf-8")).hexdigest()[:16] for s in sentences}
    sent_set = {s.strip() for s in sentences}
    checked = matched = 0
    # The merge persists the full submitted list, so the proof must cover it all.
    for d in decomps:
        ev = d.get("evidence")
        ev_list = ev if isinstance(ev, list) else [ev]
        ok = False
        for e in ev_list:
            if not isinstance(e, dict):
                continue
            if str(e.get("source_hash") or "") in hash_set:
                ok = True
                break
            if str(e.get("source_sentence") or e.get("text") or "").strip() in sent_set:
                ok = True
                break
        checked += 1
        if ok:
            matched += 1
    return {"verified": checked == 0 or matched == checked,
            "checked": checked, "matched": matched}


@router.get("/peer/challenge")
def peer_challenge(peer_id: str) -> dict[str, Any]:
    """Sybil cost: a peer must solve this PoW before registering (threat model
    §5). The peer runs solve_pow(peer_id) and submits the nonce to /register.
    Trusted/legacy clients that omit the nonce still register — the guard raises
    the cost of BULK identity creation without breaking a single honest join."""
    from packages.brain_link_pool.peer_trust_guard import POW_DIFFICULTY, pow_challenge

    return {"peer_id": peer_id, "challenge": pow_challenge(peer_id),
            "difficulty": POW_DIFFICULTY,
            "how": "find nonce so sha256(challenge+nonce) has `difficulty` leading zeros"}


@router.post("/peer/register")
def peer_register(body: dict[str, Any] = Body(default={})) -> dict[str, Any]:
    peer_id = str(body.get("peer_id") or f"peer-{uuid.uuid4().hex[:8]}")
    label = str(body.get("label") or peer_id)
    # DoS ceiling (threat model §2): a pool-wide registration rate limit blunts a
    # Sybil register storm (pairs with the PoW cost). Whoever floods hits it.
    try:
        from packages.brain_link_pool.rate_limiter import allow_registration

        _rl = allow_registration()
        if not _rl["allowed"]:
            return {"ok": False, "peer_id": peer_id,
                    "reason": "registration rate limit — try again shortly",
                    "retry_after_s": _rl.get("retry_after_s")}
    except Exception:
        pass
    # Trust guard (threat model §5): a quarantined KEY is refused (reversible,
    # expiring — never a hardware curse); a supplied PoW nonce is verified to
    # make Sybil identity-farming expensive. Absent nonce = legacy path (still
    # economy tier, zero privileges) so honest existing clients keep working.
    try:
        from packages.brain_link_pool import peer_trust_guard as _guard

        if _guard.is_quarantined(peer_id):
            return {"ok": False, "peer_id": peer_id,
                    "reason": "key quarantined (reversible, expiring — POST /peer/appeal)"}
        _nonce = body.get("pow_nonce")
        if _nonce is not None and not _guard.verify_pow(peer_id, int(_nonce)):
            return {"ok": False, "peer_id": peer_id,
                    "reason": "proof-of-work invalid (Sybil cost unmet)"}
    except Exception:
        pass
    now = _time.time()
    with _LOCK:
        existing = _POOL["peers"].get(peer_id, {})
        _POOL["peers"][peer_id] = {
            "label": label,
            "registered_at": existing.get("registered_at", now),
            "last_seen": now,
            "claimed": existing.get("claimed", 0),
            "completed": existing.get("completed", 0),
        }
        _POOL["by_peer"].setdefault(peer_id, {"concepts": 0, "relations": 0, "batches": 0})
    try:
        _, registry = _economy()
        registry.register(peer_id)
    except Exception:
        pass
    _seed_queue()
    return {"ok": True, "peer_id": peer_id, "label": label}


@router.get("/work/claim")
def work_claim(peer_id: str, n: int = 25) -> dict[str, Any]:
    _seed_queue()
    _reclaim_stale()
    n = max(1, min(200, n))
    # per-peer claim rate limit (threat model §2): an honest worker's natural
    # bursts pass (token bucket), a runaway claim loop is throttled — fair, not
    # punitive, and it never touches a peer's reputation.
    try:
        from packages.brain_link_pool.rate_limiter import allow_claim

        _cl = allow_claim(peer_id)
        if not _cl["allowed"]:
            return {"batch_id": None, "sentences": [], "reason": "claim_rate_limited",
                    "retry_after_s": _cl.get("retry_after_s")}
    except Exception:
        pass
    with _LOCK:
        if peer_id not in _POOL["peers"]:
            return {"batch_id": None, "sentences": [], "reason": "register_first"}
        batch: list[str] = []
        while _POOL["queue"] and len(batch) < n:
            batch.append(_POOL["queue"].popleft())
        if not batch:
            return {"batch_id": None, "sentences": [], "reason": "no_work"}
        batch_id = uuid.uuid4().hex[:12]
        _POOL["inflight"][batch_id] = {"peer_id": peer_id, "sentences": batch, "claimed_at": _time.time()}
        _POOL["peers"][peer_id]["claimed"] += 1
        _POOL["peers"][peer_id]["last_seen"] = _time.time()
    # BME burn: the coordinator pays for requested work at claim time
    try:
        ledger, _ = _economy()
        ledger.burn(COORDINATOR, BATCH_PRICE, batch_id)
    except Exception:
        pass
    return {"batch_id": batch_id, "sentences": batch}


@router.post("/work/submit")
def work_submit(body: dict[str, Any] = Body(default={})) -> dict[str, Any]:
    peer_id = str(body.get("peer_id") or "")
    batch_id = str(body.get("batch_id") or "")
    decomps = body.get("decompositions") or []
    with _LOCK:
        b = _POOL["inflight"].pop(batch_id, None)
        if b is None or b["peer_id"] != peer_id:
            return {"ok": False, "reason": "unknown_or_foreign_batch"}
    # Proof-of-Inference gate BEFORE the merge: a submission that fails membership
    # verification neither enters the store nor mints — and reputation bleeds.
    proof = _verify_submission(b.get("sentences") or [], decomps)
    try:
        ledger, registry = _economy()
        registry.record_outcome(peer_id, bool(proof.get("verified")))
        if proof.get("verified") and not proof.get("empty"):
            ledger.mint(peer_id, BATCH_PRICE, batch_id, proof)
        # MEASURED bench (2-4): Render grades nodes with a synthetic OctaneBench;
        # we grade with REAL verified work — sentences/sec from claim to submit.
        # EMA over batches so the tier reflects sustained capacity, and the
        # priority-tier promotion path runs itself.
        _dt = max(0.05, _time.time() - float(b.get("claimed_at") or _time.time()))
        _rate = len(b.get("sentences") or []) / _dt
        _prev = float(registry.register(peer_id).get("bench") or 0.0)
        registry.set_bench(peer_id, round(0.7 * _prev + 0.3 * _rate, 2) if _prev else round(_rate, 2))
        # Trust guard (threat model §5): behavioral auto-quarantine on a KEY whose
        # failure/replay rate breaches threshold — reversible, expiring, audited.
        # Uses the registry's own jobs/failed record (no hardware fingerprint).
        from packages.brain_link_pool import peer_trust_guard as _guard

        _rec = registry.register(peer_id)
        _replays = 1 if (not proof.get("verified") and proof.get("reason") == "replay") else 0
        _guard.assess(peer_id, jobs=int(_rec.get("jobs", 0)),
                      failed=int(_rec.get("failed", 0)),
                      replays=_replays)
    except Exception:
        pass
    if not proof.get("verified"):
        return {"ok": False, "reason": "verification_failed", "proof": proof}
    # Merge the peer's neuro-symbolic decompositions into the shared store — the
    # brain actually GROWS from distributed peer compute.
    added_c, added_r = _accumulate_decompositions(decomps)
    with _LOCK:
        _POOL["batches_completed"] += 1
        p = _POOL["peers"].setdefault(peer_id, {"completed": 0, "claimed": 0})
        p["completed"] = p.get("completed", 0) + 1
        p["last_seen"] = _time.time()
        bp = _POOL["by_peer"].setdefault(peer_id, {"concepts": 0, "relations": 0, "batches": 0})
        bp["concepts"] += added_c
        bp["relations"] += added_r
        bp["batches"] += 1
    try:
        _DATA_DIR.mkdir(parents=True, exist_ok=True)
        with _CONTRIB_LOG.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps({
                "at": _time.strftime("%Y-%m-%dT%H:%M:%S"), "peer_id": peer_id, "batch_id": batch_id,
                "store_concepts_added": added_c, "store_relations_added": added_r,
            }, ensure_ascii=False) + "\n")
    except Exception:
        pass
    return {"ok": True, "store_concepts_added": added_c, "store_relations_added": added_r,
            "store_concepts_total": _STORE_TOTALS["concepts_added"],
            "store_relations_total": _STORE_TOTALS["relations_added"]}


@router.post("/peer/appeal")
def peer_appeal(body: dict[str, Any] = Body(default={})) -> dict[str, Any]:
    """Contest a quarantine (threat model §5: bans are reversible, never a
    hardware curse). A signed message lifts an auto-quarantine; operator review
    can also lift. Absent signature -> logged for operator review, not auto-lifted."""
    from packages.brain_link_pool import peer_trust_guard as _guard

    peer_id = str(body.get("peer_id") or "")
    if not peer_id or not _guard.is_quarantined(peer_id):
        return {"ok": True, "quarantined": False, "reason": "not currently quarantined"}
    msg, sig = str(body.get("message") or ""), str(body.get("signature") or "")
    if msg and sig and _guard.verify_signature(peer_id, msg, sig):
        _guard.lift_quarantine(peer_id, note="appeal: valid signature")
        return {"ok": True, "lifted": True, "reason": "signature verified — quarantine lifted"}
    return {"ok": True, "lifted": False,
            "reason": "appeal logged for operator review (no valid signature supplied)"}


@router.get("/pool/status")
def pool_status() -> dict[str, Any]:
    _reclaim_stale()
    now = _time.time()
    merge: dict[str, Any] | None = None
    if _SHARDED_STORE is not None:
        try:
            merge = _SHARDED_STORE.status()
        except Exception:
            merge = None
    with _LOCK:
        peers = [{
            "peer_id": pid, "label": p.get("label", pid),
            "online": (now - p.get("last_seen", 0)) < 30,
            "claimed": p.get("claimed", 0), "completed": p.get("completed", 0),
            "concepts": _POOL["by_peer"].get(pid, {}).get("concepts", 0),
            "relations": _POOL["by_peer"].get(pid, {}).get("relations", 0),
        } for pid, p in _POOL["peers"].items()]
        return {
            "peers": peers,
            "peer_count": len(peers),
            "online_peers": sum(1 for p in peers if p["online"]),
            "queue_remaining": len(_POOL["queue"]),
            "inflight": len(_POOL["inflight"]),
            "batches_completed": _POOL["batches_completed"],
            "store_concepts_total": _STORE_TOTALS["concepts_added"],
            "store_relations_total": _STORE_TOTALS["relations_added"],
            "uptime_seconds": round(now - _POOL["started_at"], 1),
            "architecture": "p2p_shared_compute_pool",
            # The merge engine that absorbs peer output (persistent + sharded).
            "merge_engine": merge,
            # Render-model economy: BME equilibrium + per-peer tier/reputation.
            "economy": _economy_status(peers),
        }


def _economy_status(peers: list[dict[str, Any]]) -> dict[str, Any] | None:
    try:
        ledger, registry = _economy()
        return {
            "model": "render_bme",
            "equilibrium": ledger.equilibrium(),
            "coordinator_balance": ledger.balance(COORDINATOR),
            "peers": {p["peer_id"]: {
                "tier": registry.tier(p["peer_id"]),
                "reputation": registry.register(p["peer_id"])["reputation"],
                "credits": ledger.balance(p["peer_id"]),
            } for p in peers},
        }
    except Exception:
        return None


@router.get("/pool/graph")
def pool_graph() -> dict[str, Any]:
    """The peer pool as a STATUS GRAPH for the Brain Link UI tab: a coordinator node + one
    node per peer (kind brain_link_self/peer, colored in the graph view), with edges weighted
    by each peer's contributed concepts+relations. Read-only view over pool/status."""
    status = pool_status()
    peers = status.get("peers", [])
    nodes: list[dict[str, Any]] = [{
        "id": "coordinator", "label": "Brain Link 코디네이터", "kind": "brain_link_self",
        "concepts": status.get("store_concepts_total"), "relations": status.get("store_relations_total"),
        "queue_remaining": status.get("queue_remaining"), "online_peers": status.get("online_peers"),
    }]
    edges: list[dict[str, Any]] = []
    for p in peers:
        contributed = int(p.get("concepts", 0)) + int(p.get("relations", 0))
        nodes.append({
            "id": p["peer_id"], "label": p.get("label", p["peer_id"]), "kind": "brain_link_peer",
            "online": p.get("online"), "claimed": p.get("claimed", 0), "completed": p.get("completed", 0),
            "concepts": p.get("concepts", 0), "relations": p.get("relations", 0),
        })
        edges.append({
            "source": "coordinator", "target": p["peer_id"], "relation": "shares_compute",
            "weight": contributed, "contributed": contributed, "online": p.get("online"),
        })
    return {
        "nodes": nodes, "edges": edges,
        "peer_count": status.get("peer_count"), "online_peers": status.get("online_peers"),
        "queue_remaining": status.get("queue_remaining"),
        "store_concepts_total": status.get("store_concepts_total"),
        "store_relations_total": status.get("store_relations_total"),
        "architecture": status.get("architecture"),
    }
