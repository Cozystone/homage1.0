# -*- coding: utf-8 -*-
"""Contradiction pruning — self-refinement stage 1, in OUR safety frame.

Gemini's framing (" ") adapted to the honesty contract:
nothing is silently cut. The sweep DETECTS structural conflicts, RESOLVES only
when the evidence is lopsided, QUARANTINES the loser (tombstone — reversible,
auditable), and sends genuine ties to the CURRICULUM (the honest response to a
balanced contradiction is to learn more, not to pick a side).

What counts as a contradiction here (fully data-derived, no rule table):
 * FUNCTIONAL predicates — measured from the store itself: a predicate where
 the overwhelming share of subjects hold exactly ONE object (, ,
 class). Functionality is a per-predicate statistic, not a list.
 * On a functional predicate, one subject holding 2+ DISTINCT objects is a
 conflict candidate (()= vs ).
Resolution signal: provenance TRUST TIER. The store de-dups exact triples, so
"how many rows assert X" is structurally 1 — the honest discriminator is WHERE
each value came from (registered source name): a curated-tier value beats a
non-curated one; same tier -> genuinely balanced -> queued for evidence
(the same trust_state practice the rest of the engine already uses).

Definitional prose predicates (defined_as/is_a/evidence/alias/sense) are
EXEMPT: multiple definitions are senses (see sense_split), not contradictions.
"""
from __future__ import annotations

import json
import time
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

_EXEMPT = {"defined_as", "is_a", "evidence", "alias", "sense", "주조색",
           "시각_밝기", "시각_질감"}
_FUNCTIONAL_MIN_SUBJECTS = 20   # need this many subjects to trust the statistic
_FUNCTIONAL_SHARE = 0.9         # >=90% of subjects single-valued -> functional
# curated provenance tier: source-registry names that carry editorial review.
# This is provenance metadata (like trust_state), not domain knowledge.
_CURATED_PREFIXES = ("curated", "우리말샘", "wikidata", "위키백과", "urimalsaem")

LEDGER = Path(__file__).resolve().parents[2] / "data" / "graph_scale" / "contradictions.jsonl"


def measure_functionality(store: Any, max_rows: int = 2_000_000) -> dict[str, dict[str, Any]]:
    """Per-predicate functionality statistic, measured from the store's own
    columns: share of subjects with exactly one distinct object."""
    import numpy as np

    cols = store.open_columns()
    n = min(len(cols["s"]), max_rows)
    if n == 0:
        return {}
    s = np.asarray(cols["s"][:n])
    p = np.asarray(cols["p"][:n])
    o = np.asarray(cols["o"][:n])
    out: dict[str, dict[str, Any]] = {}
    for pid in np.unique(p):
        mask = p == pid
        subs, objs = s[mask], o[mask]
        pred = store.terms.term(int(pid))
        if pred in _EXEMPT:
            continue
        # distinct (subject, object) pairs, then objects-per-subject
        pairs = np.unique(np.stack([subs, objs], axis=1), axis=0)
        counts = Counter(pairs[:, 0].tolist())
        n_subjects = len(counts)
        if n_subjects < _FUNCTIONAL_MIN_SUBJECTS:
            continue
        single = sum(1 for c in counts.values() if c == 1)
        share = single / n_subjects
        out[pred] = {
            "pid": int(pid), "subjects": n_subjects,
            "single_valued_share": round(share, 4),
            "functional": share >= _FUNCTIONAL_SHARE,
        }
    return out


def find_conflicts(store: Any, functionality: dict[str, dict[str, Any]] | None = None,
                   max_rows: int = 2_000_000) -> list[dict[str, Any]]:
    """Conflict candidates: multi-valued subjects on measured-functional
    predicates, each value annotated with its distinct-source count."""
    import numpy as np

    if functionality is None:
        functionality = measure_functionality(store, max_rows=max_rows)
    functional_pids = {v["pid"] for v in functionality.values() if v["functional"]}
    if not functional_pids:
        return []
    cols = store.open_columns()
    n = min(len(cols["s"]), max_rows)
    s = np.asarray(cols["s"][:n])
    p = np.asarray(cols["p"][:n])
    o = np.asarray(cols["o"][:n])
    src_path = store.root / "src.col"
    src = None
    if src_path.exists():
        m = src_path.stat().st_size // 4
        src = np.fromfile(str(src_path), dtype=np.int32, count=min(m, n))

    conflicts: list[dict[str, Any]] = []
    tomb = store._tombstones()
    for pid in functional_pids:
        mask = p == pid
        idxs = np.nonzero(mask)[0]
        by_subject: dict[int, dict[int, set[int]]] = defaultdict(lambda: defaultdict(set))
        for i in idxs:
            row_src = int(src[i]) if src is not None and i < len(src) else 0
            by_subject[int(s[i])][int(o[i])].add(row_src)
        pred = store.terms.term(int(pid))
        src_names = store._sources() if hasattr(store, "_sources") else []
        for sid, values in by_subject.items():
            if len(values) < 2:
                continue
            subj = store.terms.term(sid)
            entries = []
            for oid, sources in values.items():
                obj = store.terms.term(oid)
                if (subj, pred, obj) in tomb:
                    continue
                names = [src_names[i].split("|")[0] if i < len(src_names) else ""
                         for i in sources]
                curated = any(n.lower().startswith(_CURATED_PREFIXES) or
                              any(n.startswith(p) for p in _CURATED_PREFIXES)
                              for n in names)
                entries.append({"object": obj, "sources": len(sources),
                                "curated": curated, "source_names": names})
            if len(entries) < 2:
                continue
            entries.sort(key=lambda e: (-int(e["curated"]), -e["sources"]))
            conflicts.append({"subject": subj, "predicate": pred, "values": entries})
    return conflicts


def sweep(store: Any, *, apply: bool = False,
          max_rows: int = 2_000_000) -> dict[str, Any]:
    """Detect -> resolve-or-queue. Lopsided evidence tombstones the losers;
    ties go to the curriculum (learn more). Every action is ledgered."""
    functionality = measure_functionality(store, max_rows=max_rows)
    conflicts = find_conflicts(store, functionality, max_rows=max_rows)
    resolved, queued = [], []
    for c in conflicts:
        winner, losers = c["values"][0], c["values"][1:]
        # trust-tier resolution: curated beats non-curated; curated-vs-curated
        # or blog-vs-blog is a genuine open question -> queue, never judge
        lopsided = winner.get("curated") and all(not l.get("curated") for l in losers)
        if lopsided and apply:
            for l in losers:
                store.retract(c["subject"], c["predicate"], l["object"],
                              reason=f"contradiction_sweep: curated "
                                     f"{winner['source_names']} beats {l['source_names']}")
            resolved.append({**c, "kept": winner["object"]})
        else:
            queued.append(c)
            try:  # a balanced contradiction is a QUESTION — feed the learner
                from . import abstain_queue

                abstain_queue.record_abstain(f"{c['subject']} {c['predicate']}")
            except Exception:
                pass
    LEDGER.parent.mkdir(parents=True, exist_ok=True)
    with LEDGER.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps({
            "at": time.strftime("%Y-%m-%dT%H:%M:%S"),
            "functional_predicates": sorted(
                k for k, v in functionality.items() if v["functional"]),
            "conflicts": len(conflicts), "resolved": resolved, "queued_for_evidence": queued,
        }, ensure_ascii=False) + "\n")
    return {"functional_predicates": sum(1 for v in functionality.values() if v["functional"]),
            "conflicts": len(conflicts), "resolved": len(resolved),
            "queued_for_evidence": len(queued)}


def find_taxonomic_noise(store: Any, max_rows: int = 2_000_000) -> list[dict[str, Any]]:
    """Structurally impossible is_a edges — pure noise, not opinion:
 * self-loop: X is_a X
 * mutual: X is_a Y AND Y is_a X (each can't be a KIND of the other)
 Found by measurement ( is_a class). No rule table — the graph's
 own is_a edges are checked against these two impossibilities."""
    import numpy as np

    cols = store.open_columns()
    n = min(len(cols["s"]), max_rows)
    if n == 0:
        return []
    p = np.asarray(cols["p"][:n])
    pid = store.terms.lookup("is_a")
    if pid is None:
        return []
    mask = p == pid
    s = np.asarray(cols["s"][:n])[mask]
    o = np.asarray(cols["o"][:n])[mask]
    tomb = store._tombstones()
    isa: set[tuple[int, int]] = set(zip(s.tolist(), o.tolist()))
    noise: list[dict[str, Any]] = []
    seen: set[tuple[int, int]] = set()
    for si, oi in isa:
        subj, obj = store.terms.term(int(si)), store.terms.term(int(oi))
        if (subj, "is_a", obj) in tomb:
            continue
        if si == oi:
            noise.append({"subject": subj, "object": obj, "kind": "self_loop"})
        elif (oi, si) in isa and (oi, si) not in seen:
            # a mutual is_a: keep the DIRECTION the graph supports more (which
            # side's object also appears as another subject's genus = the real
            # parent), else flag both for evidence. Here we just report the pair.
            seen.add((si, oi))
            noise.append({"subject": subj, "object": obj, "kind": "mutual_is_a",
                          "reverse": store.terms.term(int(oi))})
    return noise


def sweep_taxonomy(store: Any, *, apply: bool = False,
                   max_rows: int = 2_000_000) -> dict[str, Any]:
    """Quarantine structurally-impossible is_a noise (self-loops always;
    mutual is_a: the weaker-supported direction). Reversible, ledgered."""
    noise = find_taxonomic_noise(store, max_rows=max_rows)
    removed = 0
    for item in noise:
        if not apply:
            continue
        if item["kind"] == "self_loop":
            store.retract(item["subject"], "is_a", item["object"],
                          reason="taxonomic_self_loop")
            removed += 1
        elif item["kind"] == "mutual_is_a":
            # drop the direction whose subject has FEWER other facts (the
            # thinner node is likelier the mis-extracted child)
            a, b = item["subject"], item["object"]
            fa = len(store.facts_about(a, limit=50) or [])
            fb = len(store.facts_about(b, limit=50) or [])
            drop_s, drop_o = (a, b) if fa <= fb else (b, a)
            store.retract(drop_s, "is_a", drop_o, reason="taxonomic_mutual_is_a")
            removed += 1
    if noise:
        LEDGER.parent.mkdir(parents=True, exist_ok=True)
        with LEDGER.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps({"at": time.strftime("%Y-%m-%dT%H:%M:%S"),
                                 "taxonomic_noise": len(noise), "removed": removed,
                                 "items": noise[:50]}, ensure_ascii=False) + "\n")
    return {"taxonomic_noise": len(noise), "removed": removed}
