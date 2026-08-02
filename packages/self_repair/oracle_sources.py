# -*- coding: utf-8 -*-
"""Where the arbiter's evidence comes from — enumerated, measured, and expandable by the loop.

    from packages.self_repair.oracle_sources import survey_sources, load_oracle
    survey_sources()     # what evidence exists on disk, and how much of it is in use
    load_oracle()        # subject -> ["Relation:object", ...] across every usable source

WHY THIS EXISTS, and it is the fifth instance of one pathology in a single day. The loop measured its
own next constraint honestly: the external arbiter knew 9-16% of the subjects its cues produce, out of
4,731 subjects total, so most disputes could not be settled. The conclusion looked like "we need to go
and acquire more evidence".

We did not. The evidence was already on disk:

    concept_properties.json          4,731 subjects   <- the only source anything read
    conceptnet_is_a.jsonl          121,015 subjects
    conceptnet_located_in.jsonl      8,705
    conceptnet_capable_of.jsonl      8,496
    conceptnet_part_of.jsonl         8,210
    conceptnet_has_property.jsonl    5,964
    conceptnet_used_for.jsonl        3,944
    conceptnet_has_part.jsonl        3,321
                                   -------
    union                          139,599 subjects   -- 29x what was being used

Built, present, and unread — the same shape as a code lane behind a permanently false gate and a
defect ledger reading only advisor journals. Acquisition was not the constraint. Enumeration was.

WHAT MAKES THIS AN RSI PIECE RATHER THAN A ONE-OFF FIX. The loop diagnosed `oracle_coverage` by
itself. If a person then widens the oracle, the loop has not improved — a person has. So this is a
REGISTRY: it enumerates what evidence exists, measures each source's coverage, and reports what is in
use against what is available. When coverage saturates again, the same call reports the gap rather
than requiring someone to remember which files exist.

WHAT IS DELIBERATELY LEFT OUT. Two files carry Korean predicate names (`conceptnet_구성요소`,
`conceptnet_원인`). Their subject/object data is fine, but naming their RELATION in English would mean
inventing a mapping, and an oracle whose relation names were guessed is not an oracle. They are
reported as skipped, with the reason, rather than silently dropped or silently guessed.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
CANDIDATES = REPO / "data" / "cloud_brain" / "derived_candidates"
LEGACY = REPO / "data" / "perception" / "concept_properties.json"

_CACHE: dict = {}


def _external_name(snake: str) -> str:
    """`has_part` -> `HasPart`. Mechanical; the file names already carry the relation."""
    return "".join(p.capitalize() for p in snake.split("_"))


def sources() -> list[dict]:
    """Every evidence file that could serve as an arbiter, with why it is or is not usable."""
    out: list[dict] = []
    if LEGACY.exists():
        out.append({"path": str(LEGACY.relative_to(REPO)), "kind": "bundled",
                    "relation": "*", "usable": True})
    for p in sorted(CANDIDATES.glob("conceptnet_*.jsonl")):
        rel = p.stem[len("conceptnet_"):]
        ascii_named = bool(re.fullmatch(r"[a-z_]+", rel))
        out.append({
            "path": str(p.relative_to(REPO)), "kind": "per-relation",
            "relation": _external_name(rel) if ascii_named else rel,
            "usable": ascii_named,
            "skipped_because": None if ascii_named else
            ("the relation name is not English, and naming it would mean inventing a mapping; "
             "an oracle whose relation names were guessed is not an oracle"),
        })
    return out


def survey_sources() -> dict:
    """How much evidence exists, how much is usable, and how much any one source covers."""
    rows = []
    union: set = set()
    for s in sources():
        subs = _subjects(REPO / s["path"])
        s = dict(s, subjects=len(subs))
        if s["usable"]:
            union |= subs
        rows.append(s)
    legacy = next((r["subjects"] for r in rows if r["kind"] == "bundled"), 0)
    return {"sources": rows, "usable_union_subjects": len(union),
            "in_use_before": legacy,
            "multiple": round(len(union) / max(1, legacy), 1),
            "skipped": [r["path"] for r in rows if not r["usable"]]}


def _subjects(path: Path) -> set:
    key = ("subs", str(path))
    if key in _CACHE:
        return _CACHE[key]
    out: set = set()
    try:
        if path.suffix == ".json":
            out = {str(k).lower() for k in json.loads(path.read_text(encoding="utf-8"))}
        else:
            for line in path.read_text(encoding="utf-8", errors="ignore").splitlines():
                if line.strip():
                    try:
                        out.add(str(json.loads(line).get("s", "")).lower())
                    except Exception:
                        continue
    except OSError:
        pass
    _CACHE[key] = out
    return out


#: provenance tags that would make the arbiter judge our own output. Excluded structurally rather
#: than assumed absent -- an arbiter that can read what it is arbitrating is not one.
OURS = ("kaikki_gloss", "codebase:ast", "wiki_property_sweep", "gloss")


def graph_evidence(subjects, relations=("capable_of", "used_for", "made_of", "has_a", "part_of",
                                        "is_a", "located_in")) -> dict:
    """Relation facts from the shipped triple store, for subjects the caller names.

    115,455,726 triples with real provenance -- curated:legacy, wikidata-truthy, conceptnet-5.7 -- and
    97% subject coverage on the case that motivated this, against ConceptNet's 61%. Rows whose source
    is one of OUR extraction pipelines are dropped, so the arbiter cannot end up grading our homework.

    MEASURED LIMIT, and it is the reason this is not the fix it looks like: on the disputed case the
    store knew 57 of 59 subjects and held THREE capable_of facts about them -- exactly what ConceptNet
    held. Subject coverage and RELATION coverage are different scarcities, and 115M triples does not
    cure the second. What this buys is disputes where the relation IS recorded."""
    try:
        from packages.graph_scale.graph_paths import SHIPPED_GRAPH_ROOT
        from packages.graph_scale.triple_store import TripleStore
        st = TripleStore(SHIPPED_GRAPH_ROOT, read_only=True)
    except Exception:
        return {}
    wanted = set(relations)
    out: dict = {}
    for s in {str(x).lower() for x in subjects}:
        try:
            rows = st.facts_with_sources(s, limit=60)
        except Exception:
            continue
        for _s, pred, obj, src, _url in rows:
            if pred in wanted and not any(o in str(src or "") for o in OURS):
                out.setdefault(s, []).append(f"{_external(pred)}:{obj}")
    return out


def _external(snake: str) -> str:
    return "".join(p.capitalize() for p in snake.split("_"))


def load_oracle() -> dict:
    """subject -> ["Relation:object", ...], merged across every usable source.

    Same shape the arbiter already consumes, so nothing downstream has to change to see 29x the
    evidence."""
    if "oracle" in _CACHE:
        return _CACHE["oracle"]
    merged: dict = {}
    try:
        for k, v in json.loads(LEGACY.read_text(encoding="utf-8")).items():
            merged.setdefault(str(k).lower(), []).extend(v)
    except Exception:
        pass
    for s in sources():
        if not s["usable"] or s["kind"] != "per-relation":
            continue
        rel = s["relation"]
        try:
            for line in (REPO / s["path"]).read_text(encoding="utf-8",
                                                     errors="ignore").splitlines():
                if not line.strip():
                    continue
                try:
                    r = json.loads(line)
                except Exception:
                    continue
                subj, obj = str(r.get("s", "")).lower(), str(r.get("o", ""))
                if subj and obj:
                    merged.setdefault(subj, []).append(f"{rel}:{obj}")
        except OSError:
            continue
    _CACHE["oracle"] = merged
    return merged
