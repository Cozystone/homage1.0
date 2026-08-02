# -*- coding: utf-8 -*-
"""The Surgeon — real-time contamination excision for the self-aware graph.

Owner directive (2026-07-09): ATANOR's self-aware AI should catch contamination
and errors in REAL TIME, like a surgeon — a precise excision with a stated
reason, not a carpet sweep.

The blade is TYPE DISJOINTNESS, read from the graph itself. A single entity
belongs to ONE top-type family: is a PLACE, is a GROUP, is
a PERSON. When an edge (or a freshly-derived candidate) would make an entity a
member of a family DISJOINT from the one it already occupies — ' is_a ',
'Florence Nightingale(film) is_a Website' — that is a sense-collision error, and
the Surgeon flags it with the exact conflicting families as the reason.

This is data-driven: both the subject's established types and the object's own
types are read from the graph's is_a edges and mapped to top families; the
family map is a small SURFACE ontology (DBpedia upper types + KO labels), the
same LAD-layer tier as morphology — it is type structure, not world knowledge.

Read-only and non-destructive by default: inspect() and scan() return verdicts
+ reasons; the operator/self-loop decides to quarantine (reuses the reversible
tombstone ledger). Never auto-deletes production."""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

# TOP-TYPE FAMILIES — mutually disjoint upper ontology (surface tier). A term is
# classified by keyword hit on its type labels. Extend by adding keywords; a
# term hitting two families is itself ambiguous and is treated as unknown.
# Keywords are matched as substrings, so they must be DISTINCTIVE — no 1-char

_FAMILIES: dict[str, tuple[str, ...]] = {
    "PLACE": ("place", "settlement", "city", "town", "village", "country", "region",
              "location", "지역", "도시", "나라", "국가", "마을", "수도", "특별시", "광역시",
              "river", "mountain", "administrativeregion", "capital city"),
    "PERSON": ("person", "human", "인물", "사람", "politician", "scientist", "artist",
               "writer", "player", "actor", "선수", "정치인", "철학자", "학자", "배우", "가수"),
    "GROUP": ("group", "ethnicgroup", "민족", "religion", "종교", "집단", "청교도",
              "부족", "종파", "신자", "교파", "교도", "sect", "denomination"),
    "ORG": ("organisation", "organization", "company", "조직", "회사", "기업", "단체",
            "institution", "agency", "정당", "party", "university", "대학교", "구단"),
    "WORK": ("creativework", "film", "movie", "book", "song", "album",
             "작품", "영화", "노래", "앨범", "website", "software", "게임"),
    "EVENT": ("event", "battle", "conflict", "사건", "전쟁", "전투", "대회",
              "election", "선거", "competition"),
    "SPECIES": ("species", "animal", "plant", "생물", "동물", "식물", "물고기", "fish",
                "bird", "insect", "곤충", "genus"),
    "SUBSTANCE": ("substance", "compound", "chemical", "물질", "화합물", "원소", "element",
                  "재료", "음식", "음료"),
}


# HARD-DISJOINT family pairs — physically incompatible (a place is not a person
# / species / substance / group / work; a person is not a species / substance /
# work; …). The Surgeon cuts ONLY on these, so a marginal ORG/GROUP overlap
# isn't excised — precision over recall, the surgeon's rule.
_HARD_DISJOINT: set[frozenset[str]] = {
    frozenset(p) for p in [
        ("PLACE", "PERSON"), ("PLACE", "GROUP"), ("PLACE", "SPECIES"),
        ("PLACE", "SUBSTANCE"), ("PLACE", "WORK"), ("PLACE", "EVENT"),
        ("PERSON", "SPECIES"), ("PERSON", "SUBSTANCE"), ("PERSON", "WORK"),
        ("PERSON", "PLACE"), ("SPECIES", "SUBSTANCE"), ("SPECIES", "WORK"),
        ("SPECIES", "ORG"), ("SPECIES", "EVENT"), ("SUBSTANCE", "WORK"),
        ("SUBSTANCE", "ORG"), ("SUBSTANCE", "EVENT"),
    ]
}


@dataclass
class Verdict:
    subject: str
    obj: str
    status: str                    # clean | suspect | contaminated
    reason: str
    subject_family: str | None = None
    obj_family: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {"subject": self.subject, "object": self.obj, "status": self.status,
                "reason": self.reason, "subject_family": self.subject_family,
                "object_family": self.obj_family}


def _kw_hit(kw: str, lab: str) -> bool:
    """ASCII keywords match on WORD BOUNDARIES ('place' must not fire inside
    'placental'/'placebo'); Korean (no word boundaries) matches as substring,
    where the multi-char tokens are distinctive enough."""
    if kw.isascii():
        return re.search(r"\b" + re.escape(kw) + r"\b", lab) is not None
    return kw in lab


def _family_of_label(label: str) -> str | None:
    lab = (label or "").lower()
    hits = {fam for fam, kws in _FAMILIES.items() if any(_kw_hit(k, lab) for k in kws)}
    return next(iter(hits)) if len(hits) == 1 else None


def _isa_parents(store: Any, term: str, limit: int = 30) -> list[str]:
    try:
        return [str(o) for _s, p, o in (store.facts_about(term, limit=limit) or [])
                if p in ("is_a", "instance_of", "subclass_of") and o]
    except Exception:
        return []


def _entity_family(store: Any, term: str, *, exclude: str | None = None) -> str | None:
    """Dominant top-type family of a term, from its OWN label + its is_a parents.
    exclude drops one parent (the edge under test) so we read prior context."""
    from collections import Counter
    votes: Counter = Counter()
    f0 = _family_of_label(term)
    if f0:
        votes[f0] += 1
    for par in _isa_parents(store, term):
        if exclude and par == exclude:
            continue
        f = _family_of_label(par)
        if f:
            votes[f] += 1
    if not votes:
        return None, 0
    top, n = votes.most_common(1)[0]
    # a clear majority family; return its strength (vote count) so the Surgeon
    # only CUTS on a well-established subject type, never a single weak signal.
    if len(votes) == 1 or n > sum(votes.values()) / 2:
        return top, n
    return None, 0


def inspect(store: Any, subject: str, obj: str) -> Verdict:
    """Is 'subject is_a obj' type-consistent? contaminated ONLY when the
    subject's family is well-established (>=2 signals) AND its family is
    HARD-DISJOINT from the object's — precision over recall (surgeon's rule)."""
    subj_fam, strength = _entity_family(store, subject, exclude=obj)
    obj_fam = _family_of_label(obj) or _entity_family(store, obj)[0]
    if subj_fam and obj_fam and subj_fam != obj_fam:
        if strength >= 2 and frozenset((subj_fam, obj_fam)) in _HARD_DISJOINT:
            return Verdict(subject, obj, "contaminated",
                           f"type disjoint: '{subject}' is established as {subj_fam} "
                           f"({strength} signals), but '{obj}' is {obj_fam} — physically "
                           f"incompatible, a sense-collision error", subj_fam, obj_fam)
        return Verdict(subject, obj, "suspect",
                       f"family mismatch {subj_fam}/{obj_fam} but not hard-disjoint or "
                       f"subject weakly typed ({strength}) — needs evidence, not excised",
                       subj_fam, obj_fam)
    if subj_fam and obj_fam and subj_fam == obj_fam:
        return Verdict(subject, obj, "clean",
                       f"type-consistent ({subj_fam})", subj_fam, obj_fam)
    return Verdict(subject, obj, "suspect",
                   "type family unknown for one endpoint — cannot confirm; needs evidence",
                   subj_fam, obj_fam)


def scan(store: Any, edges: list[tuple[str, str]], *, cap: int = 5000
         ) -> dict[str, Any]:
    """Real-time review of a batch of candidate is_a edges. Returns the
    contaminated ones with reasons — the surgeon's incision list. Non-
    destructive: the caller quarantines via the reversible ledger."""
    contaminated: list[dict[str, Any]] = []
    clean = suspect = 0
    for s, o in edges[:cap]:
        v = inspect(store, s, o)
        if v.status == "contaminated":
            contaminated.append(v.to_dict())
        elif v.status == "clean":
            clean += 1
        else:
            suspect += 1
    n = min(len(edges), cap)
    return {"reviewed": n, "clean": clean, "suspect": suspect,
            "contaminated": len(contaminated),
            "contamination_rate": round(len(contaminated) / n, 4) if n else 0.0,
            "incisions": contaminated[:50]}


# ---- VECTORIZED family table: O(1)/edge scan for real-time, whole-batch use --
_FAM_LIST = list(_FAMILIES.keys())


def precompute_families(store: Any) -> dict[str, Any]:
    """One vectorized pass over the is_a columns → each subject's dominant top
    family + strength, so scan_fast is O(1) per edge (per-edge store reads made
    the surgeon 58ms/edge; this makes a whole 88k candidate batch ~1s). The
    object-as-type family comes from its label directly (cached)."""
    import numpy as np
    root = store.root
    p = np.fromfile(root / "p.col", dtype="<i4")
    s = np.fromfile(root / "s.col", dtype="<i4")
    o = np.fromfile(root / "o.col", dtype="<i4")
    n = min(len(p), len(s), len(o))
    pid = store.terms.lookup("is_a")
    if pid is None:
        return {"fam_by_subj": {}, "obj_fam_cache": {}}
    m = p[:n] == pid
    s, o = s[:n][m], o[:n][m]
    # each distinct OBJECT id -> family index (-1 unknown) via its label
    obj_ids = np.unique(o)
    fam_idx_of_obj: dict[int, int] = {}
    obj_fam_cache: dict[str, str | None] = {}
    for oid in obj_ids.tolist():
        lab = store.terms.term(oid)
        f = _family_of_label(lab) if lab else None
        obj_fam_cache[lab or ""] = f
        fam_idx_of_obj[oid] = _FAM_LIST.index(f) if f in _FAM_LIST else -1
    obj_fam = np.array([fam_idx_of_obj.get(int(x), -1) for x in o], dtype=np.int64)
    maxid = int(s.max()) + 1 if len(s) else 1
    # per-family vote counts per subject (8 bincounts over the edges)
    counts = np.zeros((len(_FAM_LIST), maxid), dtype=np.int32)
    for fi in range(len(_FAM_LIST)):
        sel = obj_fam == fi
        if sel.any():
            counts[fi] = np.bincount(s[sel], minlength=maxid)
    total = counts.sum(axis=0)
    best = counts.argmax(axis=0)
    best_n = counts.max(axis=0)
    fam_by_subj: dict[int, tuple[str, int]] = {}
    subj_ids = np.unique(s)
    for sid in subj_ids.tolist():
        n_best = int(best_n[sid])
        if n_best == 0:
            continue
        # clear-majority rule (same as _entity_family)
        if n_best * 2 > int(total[sid]) or int((counts[:, sid] > 0).sum()) == 1:
            fam_by_subj[sid] = (_FAM_LIST[int(best[sid])], n_best)
    return {"fam_by_subj": fam_by_subj, "obj_fam_cache": obj_fam_cache}


def scan_fast(store: Any, edges: list[tuple[str, str]], table: dict[str, Any]
              ) -> dict[str, Any]:
    """O(1)/edge Surgeon scan using a precomputed family table — for whole
    candidate batches / the real-time self-loop. Same verdict logic as inspect."""
    fam_by_subj = table["fam_by_subj"]
    obj_cache = table["obj_fam_cache"]
    contaminated: list[dict[str, Any]] = []
    clean = suspect = 0
    for s, o in edges:
        sid = store.terms.lookup(s)
        sf = fam_by_subj.get(sid) if sid is not None else None
        of = obj_cache.get(o)
        if of is None:
            of = _family_of_label(o)
        if sf and of and sf[0] != of:
            if sf[1] >= 2 and frozenset((sf[0], of)) in _HARD_DISJOINT:
                contaminated.append({"subject": s, "object": o, "status": "contaminated",
                                     "reason": f"type disjoint: {s}={sf[0]}({sf[1]}) vs "
                                               f"{o}={of} — physically incompatible",
                                     "subject_family": sf[0], "object_family": of})
            else:
                suspect += 1
        elif sf and of and sf[0] == of:
            clean += 1
        else:
            suspect += 1
    n = len(edges)
    return {"reviewed": n, "clean": clean, "suspect": suspect,
            "contaminated": len(contaminated),
            "contamination_rate": round(len(contaminated) / n, 4) if n else 0.0,
            "incisions": contaminated[:100]}
