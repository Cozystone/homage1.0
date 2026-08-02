# -*- coding: utf-8 -*-
"""Self-teaching loop — the AI learns from its OWN failures using the live open web.

Owner (2026-07-13): " ."
So instead of hand-patching each wrong answer, this closes a loop that turns the AI's
adversarial failures into learning material and lets it teach itself:

 run battery ─▶ classify each failure
 ├─ KNOWLEDGE miss ( / " " / ungrounded)
 │ └─▶ SearXNG (live open web) ─▶ ingest_web_result
 │ (clean-definition gate ─▶ CANDIDATE store, never prod)
 │ └─▶ failure receipt (so the loop doesn't chase the same miss)
 └─ ROUTING miss (opinion/advice/creation got a definition/felt dump)
 └─▶ (question, expected_lane) label for the learned router
 ─▶ [gated] merge candidates → production (only if the P0 sentinel stays GREEN)
 ─▶ re-run the same questions ─▶ measured Δ (misses that became real answers)

Nothing here fabricates: the web branch only keeps snippets that pass the existing
clean-definition filter, learns them into the CANDIDATE store, and promotes only behind
the P0 gate. The teacher is built once; it fixes many — and keeps fixing as it reads more.

 python scripts/self_teach_from_failures.py --limit 12 # learn, no promote
 python scripts/self_teach_from_failures.py --limit 12 --promote # + gated promote + re-measure
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "apps" / "api"))

ENGINE = "http://127.0.0.1:8502"
BATTERY = ROOT / "data" / "answer_quality" / "adversarial_battery_100.json"


_MISS_MARKS = (
    "확인된 근거가 없", "확인된 근거가 부족", "근거가 부족", "웹 검색을 켜", "웹에서",
    "실시간 웹으로", "무엇에 대해 궁금", "조금 더 구체적", "지어내", "못해요",
    "단계별 근거가 없", "아직 제 그래프에", "확정해서 답하기 어렵",
)
_MISS_KINDS = (
    "relation_ungrounded", "honest_capability_limit", "false_premise_abstention",
    "base_brain_after_low_quality_grounding", "needs_more",
)
# lanes that ENGAGE (opinion / advice / smalltalk) — a knowledge dump here is a routing miss,
# but it is NOT a knowledge miss, so we don't web-learn it.
_ENGAGE_CATS = {"opinion_debate", "emotion_complex", "creation_hard", "daily_awkward", "followup_context"}


def _ask(q: str, language: str) -> dict:
    body = json.dumps({"message": q, "language": language, "web_search": False}).encode()
    req = urllib.request.Request(ENGINE + "/api/chat/atanor", data=body,
                                 headers={"Content-Type": "application/json"})
    r = json.loads(urllib.request.urlopen(req, timeout=45).read()).get("result", {})
    return {"answer": (r.get("answer") or "").strip(), "kind": r.get("answer_kind") or ""}


def _is_miss(cat: str, answer: str, kind: str) -> bool:
    if not answer:
        return True
    if any(m in answer for m in _MISS_MARKS):
        return True
    # a bare dictionary echo for an ENGAGE prompt is a routing miss, handled separately;
    # here we only flag KNOWLEDGE gaps that the web can actually fill.
    if kind in _MISS_KINDS and cat not in _ENGAGE_CATS:
        return True
    return False


_FILLER = re.compile(r"(왜|어떻게|뭐야|뭐지|모야|뭔데|인거임|거임|건데|일까|을까|나요|나여|는거|은거|그거|대체|진짜|좀|걍|이해가안감|\?+|!+)")


def _topic(q: str) -> str:
    """Head content word of the question — what to look up. The adversarial prompts are messy
 (' ??'), so strip fillers/particles hard and keep the longest real noun."""
    from app.services.answer_orchestrator import _entity  # reuse the engine's extractor
    ent = (_entity(q) or "").strip()
    ent = _FILLER.sub(" ", ent)
    ent = re.sub(r"(은|는|이|가|을|를|이란|란|이라는|라는|이야|야|이에요|예요)$", "", ent).strip()
    _josa = lambda w: re.sub(r"(은|는|이|가|을|를|의|도|만|과|와|이란|란)$", "", w)
    toks = [_josa(t) for t in re.findall(r"[0-9A-Za-z가-힣]{2,}", ent) if not _FILLER.fullmatch(t)]
    toks = [t for t in toks if len(t) >= 2]
    if toks:
        return max(toks, key=len)          # the most specific noun in the phrase
    # fall back to the longest content token of the raw question
    raw = [t for t in re.findall(r"[가-힣A-Za-z]{2,}", q) if not _FILLER.search(t)]
    return max(raw, key=len) if raw else ent


def _p0_green() -> bool:
    try:
        out = subprocess.run([sys.executable, "scripts/p0_sentinel.py", "--once"],
                             cwd=ROOT, capture_output=True, text=True, timeout=180)
        return '"state": "GREEN"' in out.stdout or '"ok": true' in out.stdout
    except Exception:
        return False


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=12, help="max knowledge-miss topics to web-learn")
    ap.add_argument("--promote", action="store_true", help="gated candidate→production merge + re-measure")
    args = ap.parse_args()

    from app.services.web_search import (searxng_search, wikipedia_search, _searxng_reachable,
                                         _wikipedia_extract_for_page, _split_source_sentences)
    from app.services.wikipedia_grounded_learning import ingest_web_result
    from packages.flywheel import failure_receipts

    def _clean_def_rows(topic: str, lang: str) -> list:
        """A COMPLETE clean definition sentence from the encyclopedic extract (not the truncated
        search snippet, which fails the intake purity gate). This is the open-web distiller v0:
        resolve the real page, pull the intro extract, keep the first whole sentence(s)."""
        try:
            hits = wikipedia_search(topic, count=1) or []
        except Exception:
            hits = []
        title = str((hits[0].get("title") if hits else "") or topic).strip()
        host = "ko.wikipedia.org" if any("가" <= c <= "힣" for c in title) else "en.wikipedia.org"
        try:
            extract = _wikipedia_extract_for_page(title) or ""
        except Exception:
            extract = ""
        sents = _split_source_sentences(extract)
        if not sents:
            return []
        snippet = " ".join(sents[:2])[:400]
        url = f"https://{host}/wiki/" + urllib.parse.quote(title.replace(" ", "_"))
        return [{"title": title, "snippet": snippet, "url": url}]

    spec = json.load(open(BATTERY, encoding="utf-8"))["questions"]
    web_live = _searxng_reachable()
    print(f"SearXNG open-web tap: {'LIVE' if web_live else 'DOWN — knowledge branch idle'}")

    knowledge_misses, routing_labels, learned = [], [], []
    for it in spec:
        q, cat = it["q"], it["cat"]
        lang = "ko" if any("가" <= c <= "힣" for c in q) else "en"
        try:
            res = _ask(q, lang)
        except Exception as e:
            res = {"answer": "", "kind": f"__err__:{type(e).__name__}"}
        if not _is_miss(cat, res["answer"], res["kind"]):
            continue
        if cat in _ENGAGE_CATS:
            # routing miss: the RIGHT lane exists, the router just didn't pick it → label it.
            want = {"opinion_debate": "opinion", "emotion_complex": "advice",
                    "creation_hard": "creation", "daily_awkward": "smalltalk",
                    "followup_context": "followup"}.get(cat, "engage")
            routing_labels.append({"q": q, "expected_lane": want, "got_kind": res["kind"]})
            continue
        knowledge_misses.append({"id": it["id"], "q": q, "topic": _topic(q), "lang": lang, "kind": res["kind"]})

    print(f"\nfailures found: {len(knowledge_misses)} knowledge-miss · {len(routing_labels)} routing-miss")

    # ── KNOWLEDGE BRANCH: fetch the open web, learn into the candidate store (gated/clean) ──
    todo = [k for k in knowledge_misses if k["topic"]][: args.limit]
    for k in todo:
        topic = k["topic"]

        # clean-definition gate); SearXNG gives BREADTH but its raw snippets are usually too messy
        # for the purity filter. So: encyclopedic first, open-web as the breadth fallback.
        rows = _clean_def_rows(topic, k["lang"])
        ing = ingest_web_result(rows, language=k["lang"]) if rows else {"ingested": False, "concepts_added": 0}
        if not ing.get("concepts_added") and web_live:
            try:
                srows = searxng_search(topic, count=6) or []
            except Exception:
                srows = []
            if srows:
                ing = ingest_web_result(srows, language=k["lang"])
                rows = rows or srows
        failure_receipts.record_receipt(
            topic=topic, causes=[k["kind"], "adversarial_battery"], source="self_teach_loop",
            chars=len(k["q"]),
        )
        status = f"+{ing.get('concepts_added', 0)}c/{ing.get('relations_added', 0)}r" if ing.get("ingested") else "no clean fact"
        learned.append({**k, "web_rows": len(rows), "ingested": bool(ing.get("ingested")), "delta": status})
        print(f"  learn [{k['id']}] {topic!r:22} web={len(rows):>2}  {status}")

    report = {
        "at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "knowledge_misses": len(knowledge_misses), "routing_misses": len(routing_labels),
        "web_learned": sum(1 for x in learned if x["ingested"]),
        "routing_labels": routing_labels[:40],
        "learned": learned,
    }
    outdir = ROOT / "data" / "answer_quality" / "self_teach_runs"
    outdir.mkdir(parents=True, exist_ok=True)
    (outdir / f"run_{time.strftime('%Y%m%d_%H%M%S')}.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=1), encoding="utf-8")

    print(f"\nweb-learned into candidate store: {report['web_learned']}/{len(todo)} topics")
    print(f"routing labels for the learned router: {len(routing_labels)} (feed flywheel.distill_router)")

    # ── GATED PROMOTE + RE-MEASURE (only behind the P0 sentinel) ──
    if args.promote and report["web_learned"] > 0:
        print("\nP0 sentinel gate before promotion...", flush=True)
        if not _p0_green():
            print("  P0 not GREEN — HOLDING promotion (owner's safety invariant).")
            return 0
        try:
            from packages.cloud_brain.candidate_promotion_merge import merge_candidates_to_production
            from app.services.wikipedia_grounded_learning import WIKIPEDIA_GROUNDED_STORE
            m = merge_candidates_to_production(candidate_store=str(WIKIPEDIA_GROUNDED_STORE))
            print(f"  merged to production: {m if isinstance(m, dict) else m}")
        except Exception as e:
            print(f"  merge unavailable ({type(e).__name__}: {e}) — candidate store still holds the learning.")
            return 0
        if not _p0_green():
            print("  ⚠ P0 regressed AFTER merge — this is exactly what the gate guards; investigate.")
            return 1
        # re-ask the learned topics: did the misses become real answers?
        fixed = 0
        for k in todo:
            try:
                after = _ask(k["q"], k["lang"])
            except Exception:
                continue
            if not _is_miss("world_knowledge", after["answer"], after["kind"]):
                fixed += 1
        print(f"\n  Δ re-measured: {fixed}/{len(todo)} knowledge-misses now answer for real. P0 still GREEN.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
