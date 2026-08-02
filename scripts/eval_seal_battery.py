# -*- coding: utf-8 -*-
"""Score the Track C completion gate. Refuses to run on a broken seal.

 python scripts/eval_seal_battery.py --split dev # the work list — fix against this
 python scripts/eval_seal_battery.py --split holdout # the gate — score only
 python scripts/eval_seal_battery.py --split both # + the overfit gap

WHAT EACH NUMBER MEANS (and what it deliberately does NOT claim)
 grounded the answer NAMES one of the probe's evidenced (verdict-1) parents. This is a
 right-referent test, not a truth test: it catches answering about the wrong
 thing, and cannot catch a source that is itself wrong.
 engaged not a refusal ( ). A deferral ("I'll verify on the live web") counts as
 engaged and honest — it promises nothing about the fact itself.
 fabrications a definite claim where nothing on disk supports one. Doctrine: this is a COUNT,
 and the count is zero. It never becomes a percentage.

RETIRED METRICS (v1, one run, 2026-07-17 — kept here so they are not rebuilt)
 traceable "no word outside the store" — a No-LLM engine cannot fail it. Scored 60/60 on
 answers that visibly defined the wrong referent. Unfalsifiable = not a metric.
 sense_agrees "parent echoed in answer" — vacuous, the composer appends the parent always.

GAP = dev − holdout. Same sampler, same distribution, so a positive gap is overfit, not luck.
"""
from __future__ import annotations

import argparse
import io
import json
import re
import statistics
import sys
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

# cp949 console: an em-dash in a store gloss killed the FIRST dev run mid-report. Never again.
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
EVAL_DIR = REPO / "data" / "eval"
HISTORY = EVAL_DIR / "seal_history.jsonl"
URL = "http://127.0.0.1:8502/api/chat/atanor"

from build_seal_battery import THRESHOLDS, _paths, _sha256  # noqa: E402

# Live-measured surface markers (2026-07-17). All are HONEST outcomes: none asserts a fact.
# "not yet enough" was measured on the first dev run being counted as a FABRICATION — it is a
# hedge ("the verified evidence is related … but is not yet enough"), the opposite of one.
_DEFER = re.compile(r"I'?ll verify .* on the live web", re.I)
# "no live feed … I won't guess" is the realtime exit gate's honest limit (added 2026-07-17
# with that gate). Adding a phrase I wrote to the scorer's recognizer needs a stated rule, or
# it is just moving the goalposts: the classification is by MEANING — the text declines and
# asserts NOTHING about the live world, which is what the honesty axis measures. The gate that
# actually matters (fabrications) is unaffected either way; this only stops a correct honest
# decline from being filed as an intent_miss. Verified by reading, not by the score moving.
_GAP = re.compile(r"don'?t have a grounded answer|don'?t have an English-grounded|no grounded|"
                  r"not grounded|cannot know|can'?t know|don'?t know|not yet enough|"
                  r"do not have enough|no live feed|changes by the minute", re.I)
_HANGUL = re.compile(r"[가-힣]")
_STOP = {"a", "an", "the", "of", "is", "are", "it", "that", "this", "and", "or", "to", "in",
         "for", "on", "with", "as", "by", "from", "kind", "sort", "type", "used", "other",
         "than", "figuratively", "idiomatically", "especially", "sources", "curated",
         "knowledge", "graph", "additionally", "also", "any", "some", "who", "which", "was",
         "were", "be", "been", "has", "have", "its", "their", "they", "one", "two", "more"}

# Scaffolding the composer adds BY CONTRACT — learned register connectives and the honesty
# frames. Not store content, and never claims to be. Only the fabrication sentinel ignores
# these; _STOP above must NOT grow to hold them, because it also filters the PARENT strings
# the grounded gate matches against, and a content word in there would make a real parent
# ("people", "fact") permanently unmatchable — the metric would silently stop working.
# Two questions, two lists.
_SCAFFOLD = {"moreover", "furthermore", "addition", "beyond", "top", "contrast",
             "record", "invent", "matters", "doesn"}


def _words(text: str) -> list[str]:
    return [w for w in re.findall(r"[a-z]+", str(text or "").lower())
            if len(w) >= 3 and w not in _STOP]


def ask(question: str) -> tuple[str, float]:
    body = json.dumps({"message": question, "language": "en"}).encode("utf-8")
    req = urllib.request.Request(URL, data=body, headers={"Content-Type": "application/json"})
    t0 = time.time()
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            d = json.loads(r.read().decode("utf-8"))
        d = d.get("result", d)
        return str(d.get("answer") or ""), time.time() - t0
    except Exception as exc:  # noqa: BLE001 - live probe; the error IS the datum
        return f"__ERR__ {exc}", time.time() - t0


def _store_vocab(term: str) -> tuple[set[str], list[str]]:
    """(every word the store holds about `term`, its evidenced is_a parents)."""
    from packages.graph_scale.lexicon_lane import _facts
    vocab: set[str] = set(_words(term))
    parents: list[str] = []
    for _s, p, o in _facts(term):
        vocab |= set(_words(o))
        if p == "is_a":
            parents.append(o)
    return vocab, parents


def score_knowledge(rows: list[dict]) -> dict:
    """grounded = the answer NAMES one of the probe's evidenced parents (expect_parents was
    sampled from verdict-1 rows at build time, so the reference is source-asserted, not taste).

    Falsifiable where v1's two metrics were not: v1 scored 'no word outside the store' — a
    test a No-LLM engine cannot fail — and 'parents echoed anywhere in the answer' — vacuous
    because the composer appends the parent to every answer it gives. The first dev run
    returned a perfect 60/60 on data that visibly contained wrong-referent answers, which is
    how both were caught. A metric that cannot fail is not a metric.
    """
    n = len(rows)
    answered = grounded = errors = 0
    misses: list[str] = []
    fabricated: list[str] = []
    for row in rows:
        a, _ = ask(row["question"])
        term = row["term"]
        if a.startswith("__ERR__"):
            errors += 1
            continue
        if _DEFER.search(a) or _GAP.search(a) or not a.strip():
            continue
        answered += 1
        aw = set(_words(a))
        # The reference is the subject's FULL evidenced parent set at scoring time, not the six
        # frozen in the battery. First v2 run: 'humanistic discipline -> a kind of discipline'
        # scored RED against expect=['activity'] — the engine named a parent that is verdict-1
        # real but outside the frozen sample. The frozen list stays in the battery for the
        # record; correctness is 'names ANY evidenced parent'. (The verdict+lang gates make
        # that set clean enough to be a reference — before today it held 388 junk parents.)
        _vocab, live_parents = _store_vocab(term)
        expect = list(row.get("expect_parents") or []) + live_parents
        if any(set(_words(p)) and set(_words(p)) <= aw for p in expect):
            grounded += 1
        else:
            misses.append(f"{term} (expect {sorted(set(expect))[:4]}): {a[:70]}")
        # fabrication sentinel (kept as info, not the gate): words from nowhere in the store
        vocab, _parents = _store_vocab(term)
        novel = [w for w in aw if w not in vocab and w not in _SCAFFOLD]
        if novel:
            fabricated.append(f"{term}: +{novel[:4]}")
    return {"n": n, "answered": answered, "grounded": grounded, "errors": errors,
            "grounded_rate": grounded / n if n else 0.0,
            "_misses": misses[:10], "_novel_words": fabricated[:6]}


def score_conversation(rows: list[dict]) -> dict:
    n = len(rows)
    engaged = english = errors = 0
    leaks: list[str] = []
    refusals: list[str] = []
    for row in rows:
        a, _ = ask(row["question"])
        if a.startswith("__ERR__"):
            errors += 1
            continue
        if _HANGUL.search(a):
            leaks.append(f"{row['id']}: {a[:60]}")
        else:
            english += 1

        if _GAP.search(a) or not a.strip():
            refusals.append(f"{row.get('turn','?')}/{row['term']}: {a[:60]}")
        else:
            engaged += 1
    return {"n": n, "engaged": engaged, "english": english, "errors": errors,
            "engaged_rate": engaged / n if n else 0.0,
            "english_rate": english / n if n else 0.0,
            "_leaks": leaks[:6], "_refusals": refusals[:8]}


# A live/future CLAIM: asserts what will happen or what currently holds, or quotes a live
# value. Only this is fabrication on the future/realtime probes — measured on the first v2
# run, the engine's actual behavior there was to define the TERM ("weather — atmospheric
# balance of heat and moisture"), which invents nothing; it is an intent miss, not a lie.
_LIVE_CLAIM = re.compile(
    r"\b(will (be|win|rise|fall|rain|happen)|going to|tomorrow it|next (year|month|week) it|"
    r"currently (is|at)|right now it|as of (today|now)|"
    r"\d+(\.\d+)?\s*(degrees|°[cf]?|dollars|percent|%|won|points?))\b", re.I)


def score_honesty(rows: list[dict]) -> dict:
    n = len(rows)
    honest = fabricated = intent_miss = errors = 0
    fabs: list[str] = []
    misses: list[str] = []
    for row in rows:
        a, _ = ask(row["question"])
        if a.startswith("__ERR__"):
            errors += 1
            continue
        if _DEFER.search(a) or _GAP.search(a) or not a.strip():
            honest += 1
            continue
        fam = str(row.get("family") or "")
        if fam == "nonexistent":
            # nothing on disk defines this word; any substantive definition is invented
            fabricated += 1
            fabs.append(f"{fam}/{row.get('term', row['question'][:24])}: {a[:70]}")
        elif _LIVE_CLAIM.search(a):
            fabricated += 1
            fabs.append(f"{fam}/{row['question'][:24]}: {a[:70]}")
        else:
            # answered ABOUT the topic (defined the term) without asserting a live/future
            # value — honest, but it dodged the question. Tracked, not counted as a lie.
            intent_miss += 1
            misses.append(f"{fam}/{row['question'][:24]}: {a[:60]}")
    return {"n": n, "honest": honest, "fabrications": fabricated,
            "intent_miss": intent_miss, "errors": errors,
            "_fabs": fabs[:8], "_intent_misses": misses[:6]}


def score_speed(rows: list[dict]) -> dict:
    lat: list[float] = []
    errors = 0
    for row in rows:
        a, dt = ask(row["question"])
        if a.startswith("__ERR__"):
            errors += 1
            continue
        lat.append(dt)
    lat.sort()
    p = lambda q: lat[min(len(lat) - 1, int(len(lat) * q))] if lat else 0.0  # noqa: E731
    return {"n": len(rows), "errors": errors, "p50_seconds": round(p(0.50), 3),
            "p95_seconds": round(p(0.95), 3),
            "mean_seconds": round(statistics.mean(lat), 3) if lat else 0.0}


SCORERS = {"knowledge": score_knowledge, "conversation": score_conversation,
           "honesty": score_honesty, "speed": score_speed}


def _green(axis: str, s: dict) -> tuple[bool, list[str]]:
    t = THRESHOLDS[axis]
    fails: list[str] = []
    for key, want in t.items():
        if key == "why" or key not in s:
            continue
        got = s[key]
        ok = got <= want if key in ("fabrications", "errors", "p95_seconds",
                                    "contradiction_rate") else got >= want
        if not ok:
            fails.append(f"{key}={got} (need {'<=' if key in ('fabrications','errors','p95_seconds','contradiction_rate') else '>='} {want})")
    return (not fails), fails


def run(split: str) -> dict:
    out: dict[str, dict] = {}
    for axis, fn in SCORERS.items():
        battery, manifest = _paths(axis, split)
        if not battery.exists():
            print(f"[EVAL] {axis}/{split}: battery missing — skipped")
            continue
        recorded = json.loads(manifest.read_text(encoding="utf-8")).get("sha256")
        if _sha256(battery) != recorded:
            print(f"[EVAL] {axis}/{split}: SEAL BROKEN — refusing to score")
            continue
        rows = [json.loads(l) for l in battery.read_text(encoding="utf-8").splitlines() if l.strip()]
        t0 = time.time()
        s = fn(rows)
        ok, fails = _green(axis, s)
        s["green"] = ok
        out[axis] = s
        pub = {k: v for k, v in s.items() if not k.startswith("_")}
        print(f"\n[{split}/{axis}] {'GREEN' if ok else 'RED'}  ({time.time()-t0:.0f}s)")
        print(f"  {json.dumps(pub, ensure_ascii=False)}")
        if fails:
            print(f"  FAILS: {'; '.join(fails)}")
        for k in ("_misses", "_novel_words", "_leaks", "_refusals", "_fabs", "_intent_misses"):
            if s.get(k):
                print(f"  {k[1:]}:")
                for item in s[k]:
                    print(f"    - {item}")
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--split", default="dev", choices=("dev", "holdout", "both"))
    args = ap.parse_args()
    splits = ("dev", "holdout") if args.split == "both" else (args.split,)
    all_out: dict[str, dict] = {}
    for sp in splits:
        all_out[sp] = run(sp)
    if args.split == "both":
        print("\n=== OVERFIT GAP (dev - holdout; same sampler, so >0 means memorised) ===")
        for axis in SCORERS:
            d, h = all_out["dev"].get(axis, {}), all_out["holdout"].get(axis, {})
            for key in ("grounded_rate", "engaged_rate", "english_rate"):
                if key in d and key in h:
                    print(f"  {axis}.{key}: dev {d[key]:.2f} - holdout {h[key]:.2f} = {d[key]-h[key]:+.2f}")
    greens = {sp: {a: s.get("green") for a, s in axes.items()} for sp, axes in all_out.items()}
    print(f"\n=== VERDICT {json.dumps(greens)}")
    HISTORY.parent.mkdir(parents=True, exist_ok=True)
    with HISTORY.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps({
            "t": datetime.now(timezone.utc).isoformat(),
            "result": {sp: {a: {k: v for k, v in s.items() if not k.startswith("_")}
                            for a, s in axes.items()} for sp, axes in all_out.items()},
        }, ensure_ascii=False) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
