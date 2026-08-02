# -*- coding: utf-8 -*-
"""Profile domain audit — find (and optionally retract) wrong-referent structured profiles.

Owner (2026-07-13): an earlier structured_profile.fetch_profile run resolved Korean
dictionary words to WRONG Wikidata QIDs and attached that entity's attributes, so abstract
concepts surfaced geographic " " ( → "39.8282,-98.5795"; → 
"n "). profile_block() then appends the garbage to an otherwise clean definition.

This tool scans every stored _PROFILE_PREDS fact and checks DOMAIN CONSISTENCY between the
attribute and what the subject's own is_a / defined_as say it is:

 HIGH-shape the stored value violates fetch_profile's OWN writing contract for the
 predicate (_format_value renders quantities as numbers, as 'N M D',
 as 'lat, lon', item labels short): → '', → 'Pidurutalagala',
 → 'apartment building' cannot have been written by a correct run — mechanical
 proof of row corruption, no sense judgment involved.
 HIGH-domain subject has positive ABSTRACT evidence (///// …) and NO
 place/org/work evidence, yet carries a wikidata-sourced GEO attribute
 (///////). A concept has no capital. The whole
 same-QID batch is condemned with it (the wrong entity donated ALL its attributes,
 not just the geographic ones — 's "" rode in with its ).
 MEDIUM subject classifies UNKNOWN/PERSON/WORK but carries geo attributes, or an agentive
 attribute (/ …) whose VALUE positively classifies as a place/abstract.
 Report-only: multi-sense subjects ( the bull vs the element; the
 constellation vs the city) make auto-retraction here a false-positive machine.
 OK geo attributes on a place/org subject (, ), agentive/causal
 attributes anywhere the value doesn't contradict ( → ).

Retraction is a TripleStore.retract() tombstone — append-only, audit-logged, reversible by
deleting the retractions.jsonl lines. Only wikidata.org-sourced rows are ever planned;
battery/canary place entities sit behind an always-keep floor.

 python scripts/profile_domain_audit.py # read-only audit report
 python scripts/profile_domain_audit.py --retract # plan only (dry-run default)
 python scripts/profile_domain_audit.py --retract # print an exact review plan

Direct ``--apply`` is disabled. Accepted retractions must be compiled into a
GraphMutationBatch and pass candidate verification plus signed promotion.
"""
from __future__ import annotations

import argparse
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from packages.graph_scale.structured_profile import _PROFILE_PREDS  # noqa: E402
from packages.graph_scale.graph_paths import SHIPPED_GRAPH_ROOT  # noqa: E402
from packages.graph_scale.triple_store import TripleStore  # noqa: E402

STORE_ROOT = SHIPPED_GRAPH_ROOT

# attribute classes: GEO only makes sense for a locatable entity; AGENT wants a

# judge by predicate alone — it is only condemned by riding in a condemned QID batch.
GEO_PREDS = ("수도", "인구", "면적", "좌표", "최고점", "고도", "소재지", "수도인 지역", "국가")
AGENT_PREDS = ("저자", "제작자", "설립자", "최고경영자", "발견자")

# battery/canary entities whose geo profiles are load-bearing — never in a retraction plan,

_NEVER_RETRACT = {
    "대한민국", "일본", "서울", "서울특별시", "부산", "도쿄", "도쿄도", "중국", "미국",
    "한강", "백두산", "한라산", "제주도", "에베레스트산", "설악산", "독도", "경복궁",
}

# ── evidence markers (kind strings may be Korean OR English — DBpedia/Kaikki mix) ────────
# skip-side (place/org/work) is deliberately GENEROUS: a false 'place' is a safe miss,
# a false 'abstract' would retract a real profile.
_PLACE = re.compile(
    r"나라|국가|도시|수도|지역|지방|반도|섬|대륙|산맥|화산|봉우리|호수|바다|해협|사막|평야|"
    r"고원|군도|왕국|제국|공화국|마을|고을|영토|행정|지명|위치한|위치하고|소재|궁궐|사당|공항|"
    r"Settlement|City|Country|Island|Mountain|River|Lake|Region|Province|State|Continent|"
    r"Territory|Place|Village|Town|WorldHeritageSite|Skyscraper|Building|Airport|"
    r"country|city|capital|island|mountain|river|lake|region|province|continent|peninsula",
)
_ORG = re.compile(r"기업|회사|조직|단체|^기관$|정당|은행|Company|Organi[sz]ation|University|Band")
_WORK = re.compile(r"영화|소설|노래|앨범|작품|게임|Film|Album|Book|Song|novel|film|album")
_PERSON = re.compile(r"사람|인물|왕$|대왕|장군|학자|작가|가수|배우|대통령|Person|Human")
_ABSTRACT = re.compile(
    r"학문|분야|사상|이론|개념|체제|제도|현상|감정|정서|행위|행동|활동|성질|상태|방법|방식|"
    r"과정|능력|기술|법칙|원리|원칙|믿음|주의$|정신|마음|생각|세는 숫자|세는 수|숫자|"
    r"뜻|의미|관계|어근|접미사|접두사|조사$|어미|품사|인칭|여격|주격|목적격|복수|단수|"
    r"하는 곳|위한 곳|마련된 곳|(?:는|은|던|한|할)\s*(?:것|일|힘|말|수)$|"
    r"field|branch|study|science|theory|concept|ideology|phenomenon|force|emotion|"
    r"number|numeral|ability|act of|process|grammatical|particle|suffix|allomorphic|"
    r"form of|plural of",
)


def _classify(topic_texts: list[str]) -> tuple[str, str]:
    """(class, evidence) from a subject's own is_a/defined_as strings. Precedence:
    place/org/work (profile-consistent, skip) > abstract (HIGH-eligible) > person > unknown."""
    for kind, rx in (("place", _PLACE), ("org", _ORG), ("work", _WORK)):
        for t in topic_texts:
            m = rx.search(t)
            if m:
                return kind, f"{m.group(0)!r} in {t[:40]!r}"
    for kind, rx in (("abstract", _ABSTRACT), ("person", _PERSON)):
        for t in topic_texts:
            m = rx.search(t)
            if m:
                return kind, f"{m.group(0)!r} in {t[:40]!r}"
    return "unknown", ""


# a defined_as gloss that is really a leaked attribute value (coordinates / bare quantity) —
# a SEPARATE pollution class discovered by this audit; reported, never touched here
_LEAKED_GLOSS = re.compile(r"^\s*-?\d+\.\d+,\s*-?\d+\.\d+\s*$|^\s*[\d,]+(?:\.\d+)?\s*(?:km²|km|m)?\s*$")

# ── writer-contract value shapes (mirror structured_profile._format_value exactly) ──────
_NUMQ = re.compile(r"^[\d,]+(?:\.\d+)?(?: km²| km| m)?$")            # quantity: number [+unit]
_DATE = re.compile(r"^\d{1,4}년(?: \d{1,2}월)?(?: \d{1,2}일)?$")
_COORD = re.compile(r"^-?\d+\.\d+, -?\d+\.\d+$")                     # globe: 'lat, lon'
_QUANTITY_PREDS = ("인구", "면적", "고도")
_TIME_PREDS = ("설립",)
_GLOBE_PREDS = ("좌표",)


def _shape_violation(pred: str, value: str) -> str:
    """Non-empty reason when `value` could not have been produced by _format_value for
    `pred` — proof the row is corrupt (misaligned/scrambled), whatever the subject is."""
    if pred in _QUANTITY_PREDS:
        return "" if _NUMQ.match(value) else "quantity pred, non-numeric value"
    if pred in _TIME_PREDS:
        return "" if _DATE.match(value) else "time pred, non-date value"
    if pred in _GLOBE_PREDS:
        return "" if _COORD.match(value) else "globe pred, non-coordinate value"
    # item preds carry a SHORT entity label — never a bare number/date/coordinate/sentence
    if _NUMQ.match(value) or _DATE.match(value) or _COORD.match(value):
        return "item pred, quantity/date/coordinate-shaped value"
    if len(value) > 60:
        return "item pred, sentence-length value (leaked gloss)"
    return ""


def _scan(store: TripleStore):
    """One consistent read of every profile-pred row: the store is LIVE (learner appending),
    so clamp all four columns to their common prefix. Returns per-row tuples + term maps."""
    try:
        import numpy as np
    except Exception:
        raise SystemExit("numpy required for the audit scan")
    cols = store.open_columns()
    src_path = store.root / "src.col"
    nsrc = (src_path.stat().st_size // 4) if src_path.exists() else 0
    src_col = np.memmap(str(src_path), dtype="<i4", mode="r", shape=(nsrc,)) if nsrc else None
    n = min(len(cols["s"]), len(cols["p"]), len(cols["o"]), nsrc or 0)
    s_col = np.asarray(cols["s"][:n]); p_col = np.asarray(cols["p"][:n])
    o_col = np.asarray(cols["o"][:n]); sr_col = np.asarray(src_col[:n])
    pids = {store.terms.lookup(p) for p in _PROFILE_PREDS}
    pids.discard(None)
    pid_arr = np.array(sorted(pids), dtype=p_col.dtype)
    rows = np.nonzero(np.isin(p_col, pid_arr))[0]
    srcs = store._sources()
    out = []
    for i in rows:
        sid = int(sr_col[i])
        line = srcs[sid] if 0 <= sid < len(srcs) else srcs[0]
        name, _, pattern = line.partition("|")
        out.append((store.terms.term(int(s_col[i])), store.terms.term(int(p_col[i])),
                    store.terms.term(int(o_col[i])), sid, name, pattern))
    return out, n


def _topics(store: TripleStore, subject: str) -> list[str]:
    return [o for (_s, _p, o) in store.facts_about(subject, limit=60, preds=("is_a", "defined_as"))]


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--retract", action="store_true", help="build a retraction plan for HIGH findings")
    ap.add_argument(
        "--apply",
        action="store_true",
        help="disabled: shipped retractions require a signed mutation batch",
    )
    ap.add_argument("--max-retract", type=int, default=400,
                    help="abort without writing if the plan exceeds this bound (default 400)")
    args = ap.parse_args()
    if args.apply:
        print(
            "REFUSING before scan: direct shipped-store retraction is disabled; "
            "emit a reviewed GraphMutationBatch instead."
        )
        return 2
    try:  # Windows console defaults to cp949 — the report is Korean
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

    store = TripleStore(STORE_ROOT)
    # live-store safety: this is a READER. TripleStore.flush() on the query path rewrites
    # meta.json when it thinks the count moved (it always does on a fresh handle while the
    # learner appends) — and that write would revert index_ts to OUR stale generation.
    store._meta_count_written = store._count
    tomb = store._tombstones()

    rows, n = _scan(store)
    live = [r for r in rows if (r[0], r[1], r[2]) not in tomb]
    print(f"store rows scanned: {n:,}   profile-pred rows: {len(rows)} "
          f"({len(rows) - len(live)} already tombstoned, {len(live)} live)")
    by_src = Counter(r[4] for r in live)
    print(f"live rows by source: {dict(by_src.most_common())}")

    wd = [r for r in live if r[4] == "wikidata.org"]
    subjects = sorted({r[0] for r in wd})
    print(f"wikidata-profiled subjects: {len(subjects)}\n")

    cls: dict[str, tuple[str, str]] = {s: _classify(_topics(store, s)) for s in subjects}
    high: dict[tuple[str, str, str], tuple] = {}   # (s,p,o) -> (src_id, url, why); deduped
    medium_subj: list[tuple] = []
    medium_val: list[tuple] = []
    floor_hits: list[str] = []
    ok_geo_subjects: set[str] = set()

    rows_by_subj: dict[str, list[tuple]] = defaultdict(list)
    for r in wd:
        rows_by_subj[r[0]].append(r)

    def _condemn(r: tuple, why: str) -> None:
        high.setdefault((r[0], r[1], r[2]), (r[3], r[5], why))

    geo_item = tuple(p for p in GEO_PREDS if p not in _QUANTITY_PREDS + _TIME_PREDS + _GLOBE_PREDS)
    for s in subjects:
        kind, ev = cls[s]
        srows = rows_by_subj[s]
        floored = s in _NEVER_RETRACT
        # HIGH-shape: value breaks the writer's own contract — mechanical proof, applies to
        # every class of subject (the scramble hit place rows too). Floor subjects included:
        # a shape violation cannot be a classifier mistake, and garbage on a battery entity
        # is worse, not better.
        bad_batches: set[int] = set()
        for r in srows:
            reason = _shape_violation(r[1], r[2])
            if reason:
                _condemn(r, f"shape: {reason}")
                bad_batches.add(r[3])

        # dictionary abstraction or a person cannot be right on ANY subject — a country is

        for r in srows:
            if r[1] in geo_item and (r[0], r[1], r[2]) not in high:
                vkind, vev = _classify(_topics(store, r[2]))
                if vkind in ("abstract", "person"):
                    _condemn(r, f"value: geo item pred, {vkind} value [{vev}]")
                    bad_batches.add(r[3])
        geo = [r for r in srows if r[1] in GEO_PREDS]
        if geo and kind in ("place", "org"):
            ok_geo_subjects.add(s)
        elif geo and kind == "abstract":
            if floored:
                floor_hits.append(s)
            else:
                # HIGH-domain: condemn the geo rows AND every same-QID batch sibling — the
                # batch id (src_id == one wikidata entity URL) says which entity donated it
                bad_batches.update(r[3] for r in geo)
                for r in geo:
                    _condemn(r, f"domain: abstract subject [{ev}]")
        elif geo:  # unknown / person / work — real mismatch smell, but multi-sense risk
            for r in geo:
                if (r[0], r[1], r[2]) not in high:
                    medium_subj.append((*r[:3], r[5], f"subject class={kind} [{ev}]"))
        # batch expansion — NOT on place/org subjects: the src misalignment means their

        # them out would delete real knowledge. Elsewhere a condemned batch condemns its

        if bad_batches and not floored and kind not in ("place", "org"):
            for r in srows:
                if r[3] in bad_batches:
                    _condemn(r, "batch sibling of a condemned row (same subject+QID)")
        # value-side: a discoverer/author that is itself a place/phenomenon is a wrong-batch
        # tell even when the subject looks fine — report for the operator, never auto-retract
        for r in srows:
            if r[1] in AGENT_PREDS and (r[0], r[1], r[2]) not in high:
                vkind, vev = _classify(_topics(store, r[2]))
                if vkind in ("place", "abstract"):
                    medium_val.append((*r[:3], r[5], f"value class={vkind} [{vev}]"))

    def _show(title: str, items: list[tuple], cap: int = 250) -> None:
        print(f"── {title}: {len(items)}")
        for it in items[:cap]:
            s, p, o, url_or_why = it[0], it[1], it[2], it[-2] if len(it) > 4 else ""
            print(f"   {s!r} —{p}→ {o[:50]!r}   {url_or_why}  {it[-1]}")
        if len(items) > cap:
            print(f"   … {len(items) - cap} more")
        print()

    high_rows = [(s, p, o, sid, url, why) for (s, p, o), (sid, url, why) in sorted(high.items())]
    _show("HIGH (shape-violation / abstract×geo / condemned-batch sibling)", high_rows)
    _show("MEDIUM (geo on unknown/person/work subject — review, no auto-retract)", medium_subj)
    _show("MEDIUM (agentive attribute with place/abstract-shaped value)", medium_val)
    print(f"── OK: geo profiles on place/org subjects: {len(ok_geo_subjects)} "
          f"(e.g. {sorted(ok_geo_subjects)[:8]})")
    if floor_hits:
        print(f"── FLOOR: {sorted(set(floor_hits))} classified abstract but are always-keep — review markers")
    # non-wikidata rows: profile_block reads EVERY source, so legacy-tier scramble rows





    nonwd = [r for r in live if r[4] != "wikidata.org"]
    nonwd_plan, nonwd_report = [], []
    for r in nonwd:
        reason = _shape_violation(r[1], r[2])
        if not reason:
            continue
        # floor does NOT shield shape proofs (same rule as the wikidata pass): a
        # mechanically-impossible row on a battery entity is the worst kind to keep
        if "sentence-length" not in reason:
            high.setdefault((r[0], r[1], r[2]), (r[3], r[4], f"shape (non-wikidata): {reason}"))
            nonwd_plan.append((r[0], r[1], r[2][:40], r[4]))
        else:
            nonwd_report.append((r[0], r[1], r[2][:40], r[4]))
    print(f"── non-wikidata profile-pred rows: {len(nonwd)} — numeric-contract violations "
          f"joining the plan: {len(nonwd_plan)}; item-pred oddities (report-only): {len(nonwd_report)}")
    for row in nonwd_plan[:20]:
        print(f"   PLAN {row}")
    for row in nonwd_report[:10]:
        print(f"   note {row}")

    # appendix: leaked attribute values stored as defined_as (separate disease, report-only)
    leaked = []
    for s in subjects:
        for (_s, p, o) in store.facts_about(s, limit=40, preds=("defined_as",)):
            if _LEAKED_GLOSS.match(o):
                leaked.append((s, o))
    if leaked:
        print(f"── appendix: coordinate/quantity-shaped defined_as glosses (NOT touched): {leaked}")

    if not args.retract:
        print("\nread-only audit done (use --retract for a review plan).")
        return 0

    plan = sorted(high.keys())
    print(f"\nretraction plan: {len(plan)} unique triples over "
          f"{len({s for (s, _p, _o) in plan})} subjects (bound {args.max_retract})")
    if len(plan) > args.max_retract:
        raise SystemExit(f"plan exceeds --max-retract={args.max_retract}; refusing (raise the bound "
                         "only after reading the full plan above)")
    print(
        "review plan only — nothing written. Convert accepted rows to an "
        "immutable retraction batch before candidate assembly."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
