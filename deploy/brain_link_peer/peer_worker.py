#!/usr/bin/env python3
"""Brain Link peer worker — runs ATANOR's REAL engine on a peer machine.

Philosophy: NO external LLM, NO sLLM, NO rule-based. Extraction here is the same
graph-native neuro-symbolic decomposition the core engine uses
(`verify_sentence` + `decompose_sentence`, the cgsr ingestion pipeline). The peer
claims sentence batches, runs that real engine with its own CPU, and submits the
extracted concept/relation graph fragment. Distributed compute = the actual
ATANOR engine running across machines, not a stand-in.
"""
import json
import os
import time
import urllib.request

# The real engine: SourceSentence -> verification gate -> neuro-symbolic decompose
# (cgsr). Built directly (no continuous_learning import, which pulls an optional
# rhfc dep) so the peer stays lean while running the genuine extraction.
import datetime
import hashlib

from packages.cgsr.cgsr.ingestion.source_reader import SourceSentence
from packages.cgsr.cgsr.ingestion.decomposer import decompose_sentence
from packages.cgsr.cgsr.ingestion.verification_gate import verify_sentence


def _lang(s):
    return "ko" if any("가" <= ch <= "힣" for ch in s) else "en"


def _source_sentence(s, i):
    return SourceSentence(
        text=s, language=_lang(s), source_id=f"{PEER_ID}-{i}",
        source_name="brain_link_peer", source_type="local_public_corpus_shard",
        source_hash=hashlib.sha256(s.encode("utf-8")).hexdigest()[:16],
        document_id=f"{PEER_ID}-{i}", title="brain_link", url="brain_link_peer",
        license="CC BY-SA 4.0", usage_allowed=True,
        collected_at=datetime.datetime.utcnow().isoformat() + "Z",
    )

COORDINATOR = os.environ.get("COORDINATOR_URL", "http://host.docker.internal:8502").rstrip("/")
PEER_ID = os.environ.get("PEER_ID", "docker-peer-1")
PEER_LABEL = os.environ.get("PEER_LABEL", "Docker virtual PC")
BATCH = int(os.environ.get("BATCH", "25"))


def _post(path, payload):
    req = urllib.request.Request(COORDINATOR + path, data=json.dumps(payload).encode("utf-8"),
                                headers={"Content-Type": "application/json"}, method="POST")
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read().decode("utf-8"))


def _get(path):
    with urllib.request.urlopen(COORDINATOR + path, timeout=30) as r:
        return json.loads(r.read().decode("utf-8"))


def _label(d, *keys):
    for k in keys:
        v = d.get(k)
        if v:
            return str(v).strip()
    return ""


def extract(sentences):
    """REAL ATANOR neuro-symbolic extraction (cgsr) — no regex, no LLM, no sLLM.
    Returns the raw decompositions so the coordinator can MERGE them into the
    shared candidate store (the brain actually grows). The verification gate only
    admits fact-shaped statements, so contributions are genuine engine output."""
    decompositions = []
    n_c = n_r = 0
    for i, s in enumerate(sentences):
        try:
            sent = _source_sentence(s, i)
            decision = verify_sentence(sent, existing_dedupe_keys=set())
            if getattr(decision, "status", None) != "verified":
                continue
            dr = decompose_sentence(sent, decision, ingest_run_id="brain_link_peer")
        except Exception:
            continue
        decompositions.append({
            "concepts": dr.concepts, "relations": dr.relations,
            "case_frames": dr.case_frames, "evidence": dr.evidence,
        })
        n_c += len(dr.concepts)
        n_r += len(dr.relations)
    return decompositions, n_c, n_r


def main():
    print(f"[peer] {PEER_ID} ({PEER_LABEL}) -> {COORDINATOR} | engine=cgsr (graph-native, no LLM/regex)", flush=True)
    for _ in range(30):
        try:
            print("[peer] register:", _post("/api/brain-link/peer/register", {"peer_id": PEER_ID, "label": PEER_LABEL}), flush=True)
            break
        except Exception as e:
            print("[peer] register retry:", e, flush=True)
            time.sleep(2)
    idle = 0
    while True:
        try:
            claim = _get(f"/api/brain-link/work/claim?peer_id={PEER_ID}&n={BATCH}")
        except Exception as e:
            print("[peer] claim error:", e, flush=True)
            time.sleep(3)
            continue
        sents = claim.get("sentences") or []
        if not sents:
            idle += 1
            if idle % 10 == 1:
                print("[peer] no work, waiting…", flush=True)
            time.sleep(3)
            continue
        idle = 0
        t0 = time.time()
        decomps, n_c, n_r = extract(sents)
        dt = time.time() - t0
        res = _post("/api/brain-link/work/submit", {
            "peer_id": PEER_ID, "batch_id": claim["batch_id"],
            "decompositions": decomps,
        })
        print(f"[peer] batch {claim['batch_id']}: {len(sents)} sents -> engine decomposed "
              f"{len(decomps)} ({n_c}c/{n_r}r) -> store +{res.get('store_concepts_added')}c "
              f"in {dt*1000:.0f}ms | store={res.get('store_concepts_total')}c", flush=True)


if __name__ == "__main__":
    main()
