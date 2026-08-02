# -*- coding: utf-8 -*-
"""Pack purity — audit & quarantine flood-junk from the curated answer pack.

Owner (2026-07-11, after the diet-flood P0 regression): " 
 ." When un-gated promotion (or a candidate flood) bloats
the curated answer pack with obscure/foreign entities, this tool restores the sanctuary WITHOUT
a naive backup rollback — a rollback silently drops legit concepts learned since the backup
(measured: the 21:41 backup lacked , a P0 concept). Instead it QUARANTINES only the
junk, keeping every curated-quality concept.

A concept is JUNK when it is NOT in the trusted clean baseline AND it looks like flood debris:
 * a foreign / Latin-script proper-noun name (Erythrodiplax fervida, Hyundai WIA Corporation),
 * an empty / foreign-majority / grammar-note definition (no clean Korean sentence),
Concepts with a clean Korean definition ( → '… ') are KEPT even when they
were added after the baseline — they are exactly what legit learning is supposed to add.
Battery-referenced subjects are ALWAYS kept (an explicit safety floor).

A SECOND, distinct junk stratum (added 2026-07-11) is the NOISE-RELATION concept: its
definition reads as grammatical Korean ("… "), so the checks above KEEP it, but the
canonical_name is unrelated to that definition and the relations are incoherent scrape verbs.
Measured seed: canonical_name "" / desc " 2023-24 " / relations is_a ,
is_a , — it surfaces as garbage on " ". This stratum lives in
the baseline (it predates the flood), so it is gated tightly enough to reach in there safely;
see _is_noise_relation for the four-conjunct precision gate that spares every learned predicate.

Reversible: quarantined concepts are written to a sidecar file; --restore puts them back.

 python scripts/pack_purity.py audit # dry-run report
 python scripts/pack_purity.py quarantine # remove junk (backs up first)
 python scripts/pack_purity.py restore <quarantine.json> # undo
"""
from __future__ import annotations

import json
import re
import shutil
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
PACK = REPO / "data" / "base_brain" / "packs" / "atanor_base_brain_v0.json"
BASELINE = REPO / "data" / "base_brain" / "packs" / "atanor_base_brain_v0.bak-20260710-214128.json"
QUARANTINE_DIR = REPO / "data" / "base_brain" / "packs"

# battery-referenced subjects — an ALWAYS-KEEP floor so a purge can never drop a P0/P1/P2 concept
_BATTERY_SUBJECTS = {
    "물", "DNA", "상대성이론", "세종대왕", "한글", "훈민정음", "대한민국", "서울", "부산",
    "커피", "광합성", "인공지능", "반도체", "한강", "아인슈타인", "김치", "중력", "원자",
}

_KOREAN_SENT_END = re.compile(r"(다|요|죠|음|함)[.\s]*$")
_GRAMMAR_NOTE = re.compile(r"어미\s*'?-|따위(?:에|,).{0,6}쓰(?:여|이)|뜻을\s*더(?:한다|하는)|"
                           r"일부\s*명사(?:나|에|의)|관형사\s*'|의존\s*명사")

# ── noise-relation layer ─────────────────────────────────────────────────────
# Structural (English) predicates and legit Korean copular/locative/definitional



_STRUCT_PREDS = {
    "is_a", "part_of", "used_for", "contrasts_with", "requires", "have", "uses",
    "manages", "depends_on", "contains", "has_property", "related_to", "synonym_of",
    "antonym_of", "instance_of", "capable_of", "located_in", "made_of", "causes",
    "has", "produces", "enables",
}
_LEGIT_KO_PREDS = {
    "위치하다", "자리하다", "이루어지다", "뜻하다", "일컫다", "가리키다", "의하다",
    "해당하다", "속하다", "포함하다", "구성하다", "존재하다", "이르다", "되다", "있다",
}
# A schedule / roster / standings / fixtures fragment — the description shape that
# betrays a scraped sports-table concept masquerading behind an unrelated head word.
_SCHEDULE_ROSTER = re.compile(
    r"경기\s*일정|경기\s*결과|대진표|일정\s*및\s*결과|"
    r"라리가|프리미어\s*리그|분데스리가|세리에|리그앙|에레디비시|K리그|MLS|리그\s*\d|"
    r"로스터|라인업|스쿼드|출전\s*명단|선수\s*명단|"
    r"순위표|승점|순위\s*기록|"
    r"\d{4}\s*[-–~]\s*\d{2,4}\s*(?:시즌|리그|경기|일정|시리즈)"
)


def _is_noise_predicate(pred: str) -> bool:
    p = str(pred or "")
    if p in _STRUCT_PREDS or p in _LEGIT_KO_PREDS:
        return False
    return p.endswith("다") and any("가" <= ch <= "힣" for ch in p)


def _concepts(pack: dict) -> list[dict]:
    return pack.get("semantic_graph", {}).get("concepts") or []


def _name(c: dict) -> str:
    return str(c.get("canonical_name") or "")


def _desc(c: dict) -> str:
    return str(c.get("short_description") or "").strip()


def _is_junk(c: dict) -> tuple[bool, str]:
    """A (kept-since-baseline) concept is junk when it can't teach a clean Korean fact."""
    name, desc = _name(c), _desc(c)
    if name in _BATTERY_SUBJECTS:
        return False, "battery-floor"
    hangul = sum(1 for ch in name if "가" <= ch <= "힣")
    if hangul < len(name) * 0.5:                 # foreign / Latin-script proper-noun name
        return True, "foreign-name"
    if not desc:
        return True, "empty-def"
    if _GRAMMAR_NOTE.search(desc):
        return True, "grammar-note-def"
    d_hangul = sum(1 for ch in desc if "가" <= ch <= "힣")
    if d_hangul < len(desc) * 0.4:               # foreign-majority definition
        return True, "foreign-def"
    if not _KOREAN_SENT_END.search(desc):        # not a real sentence (caption/fragment)
        return True, "no-korean-sentence"
    return False, "clean-korean"


def _is_noise_relation(c: dict) -> tuple[bool, str]:
    """The name↔definition mismatch stratum ( → + ).

 Reaches past the baseline whitelist on purpose — the seed is a pre-flood concept
 _is_junk() KEEPs (its Korean sentence is grammatical). Precision is the whole point,
 so a concept is flagged ONLY when ALL four conjuncts hold; any one sparing a legit
 learned predicate ( , , ):
 (1) it is not a battery-floor subject,
 (2) it carries a NON-structural Korean verb predicate (// …),
 (3) its definition is a schedule/roster/standings fragment, AND
 (4) its canonical_name does not appear in that definition — i.e. the fragment is
 about some other entity, so the head word is a mislabel, not the real owner.
 """
    name, desc = _name(c), _desc(c)
    if name in _BATTERY_SUBJECTS:                 # (1) never touch a battery concept
        return False, "battery-floor"
    if not any(_is_noise_predicate(r.get("relation")) for r in (c.get("relations") or [])):
        return False, "no-noise-predicate"       # (2)
    if not _SCHEDULE_ROSTER.search(desc):         # (3)
        return False, "desc-not-roster-fragment"
    if name and name in desc:                     # (4) fragment legitimately about this name
        return False, "name-owns-fragment"
    return True, "noise-relation"


def _load(p: Path) -> dict:
    return json.loads(p.read_text(encoding="utf-8"))


def audit(apply: bool = False) -> None:
    pack = _load(PACK)
    baseline_names = {_name(c) for c in _concepts(_load(BASELINE))} if BASELINE.exists() else set()
    concepts = _concepts(pack)
    keep, junk = [], []
    for c in concepts:
        nr_junk, nr_reason = _is_noise_relation(c)   # runs first — can reach into the baseline
        if nr_junk:
            junk.append(c if apply else (c, nr_reason))
            continue
        if _name(c) in baseline_names:           # trusted pre-flood concept — never touched
            keep.append(c)
            continue
        is_junk, reason = _is_junk(c)
        (junk if is_junk else keep).append((c, reason) if not apply else c)
    if not apply:
        from collections import Counter
        by_reason = Counter(r for _c, r in junk)
        print(f"pack: {len(concepts)} concepts | baseline: {len(baseline_names)} | "
              f"since-baseline: {len(concepts) - len(baseline_names & {_name(c) for c in concepts})}")
        print(f"JUNK (would quarantine): {len(junk)}  {dict(by_reason)}")
        print(f"KEEP: {len(keep)}  (baseline + battery-floor + clean-korean since-baseline)")
        print("\nsample junk:")
        for c, r in junk[:12]:
            print(f"  [{r:18s}] {_name(c)[:24]:24s} :: {_desc(c)[:44]}")
        print("\nsample KEPT since-baseline (clean-korean learned today):")
        kept_new = [c for c in keep if isinstance(c, dict) and _name(c) not in baseline_names]
        for c in kept_new[:10]:
            print(f"  {_name(c)[:24]:24s} :: {_desc(c)[:50]}")
        return
    # apply: rewrite pack keeping only `keep`, sidecar the junk (reversible)
    shutil.copy2(PACK, str(PACK) + f".prepurity-{time.strftime('%Y%m%d-%H%M%S')}.bak")
    qpath = QUARANTINE_DIR / f"quarantined-{time.strftime('%Y%m%d-%H%M%S')}.json"
    qpath.write_text(json.dumps(junk, ensure_ascii=False, indent=0), encoding="utf-8")
    pack["semantic_graph"]["concepts"] = keep
    PACK.write_text(json.dumps(pack, ensure_ascii=False), encoding="utf-8")
    # feed the AVOID direction of the self-correction loop: each quarantined concept is a junk
    # source → a receipt so the learner steers away from re-probing it (bounded ring, best-effort).
    try:
        from packages.flywheel.failure_receipts import record_receipt
        for c in junk:
            nm = _name(c) if isinstance(c, dict) else _name(c[0])
            if nm:
                record_receipt(topic=nm, causes=["pack-junk"], source="pack_purity", kind="junk")
    except Exception:
        pass
    print(f"quarantined {len(junk)} junk concepts -> {qpath.name}")
    print(f"pack now {len(keep)} concepts (was {len(concepts)}); backup written")


def restore(qfile: str) -> None:
    qpath = Path(qfile) if Path(qfile).is_absolute() else QUARANTINE_DIR / qfile
    junk = json.loads(qpath.read_text(encoding="utf-8"))
    pack = _load(PACK)
    have = {_name(c) for c in _concepts(pack)}
    added = [c for c in junk if _name(c) not in have]
    pack["semantic_graph"]["concepts"] = _concepts(pack) + added
    shutil.copy2(PACK, str(PACK) + f".prerestore-{time.strftime('%Y%m%d-%H%M%S')}.bak")
    PACK.write_text(json.dumps(pack, ensure_ascii=False), encoding="utf-8")
    print(f"restored {len(added)} concepts from {qpath.name}")


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "audit"
    if cmd == "audit":
        audit(apply=False)
    elif cmd == "quarantine":
        audit(apply=True)
    elif cmd == "restore" and len(sys.argv) > 2:
        restore(sys.argv[2])
    else:
        print(__doc__)
