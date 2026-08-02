# -*- coding: utf-8 -*-
"""Web-roaming temporal learner -- the AI goes OUT and learns order knowledge it does not have.

Doctrine (world-roaming-register-learning, BINDING): wiki mining is the commonsense floor; real
knowledge grows by roaming the open web, PREDICTING before reading (no pre-known answer), failing,
writing a failure receipt, and updating -- and never freezing a belief (anti-dogma: k-source
consensus across domains, staleness-driven re-exploration).

Structure of one exploration:
  1. TARGET   -- a pair the field is uncertain about (conf near 0.5, unknown vocab, or a judgment
                 abstention logged during exams).
  2. PREDICT  -- write down the current belief BEFORE looking (honest prior).
  3. ROAM     -- SearXNG (:8888) -> fetch result pages -> extract sentences AND image alt/figcaption
                 text (multimodal-lite lane: every observation is typed with its modality; video and
                 audio are declared ports, not yet filled).
  4. MINE     -- closed-class connective clauses mentioning the pair -> directed observations,
                 tagged (domain, modality, timestamp).
  5. VERDICT  -- k-source consensus: a direction is BELIEVED only when >=2 distinct domains agree.
  6. RECEIPT  -- if the prediction was contradicted, append a failure receipt (the engine that
                 steers future exploration); update web evidence store either way.
"""
from __future__ import annotations

import json
import re
import time
import urllib.parse
import urllib.request
from collections import Counter
from pathlib import Path

from packages.temporal_reasoning.order_miner import sentence_pairs_ctx
from packages.temporal_reasoning.precedence_field import PrecedenceField

_DIR = Path(__file__).resolve().parents[2] / "data" / "temporal_reasoning"
_WEB_OBS = _DIR / "web_observations.jsonl"     # append-only journal (timestamped, domain, modality)
_WEB_COUNTS = _DIR / "web_counts.json"         # aggregated {(a,b): {domain: n}}
_RECEIPTS = _DIR / "failure_receipts.jsonl"    # predictions the world contradicted

_SEARX = "http://localhost:8888/search"
_TAG = re.compile(r"<script[\s\S]*?</script>|<style[\s\S]*?</style>|<[^>]+>")
_ALT = re.compile(r'<img[^>]*\balt="([^"]{8,200})"', re.IGNORECASE)
_FIGCAP = re.compile(r"<figcaption[^>]*>([\s\S]{8,300}?)</figcaption>", re.IGNORECASE)


def _stem(w: str) -> str:
    """Light inflection strip (grammar, not knowledge): launched/launching/launches -> launch."""
    for suf in ("ing", "ed", "es", "s"):
        if w.endswith(suf) and len(w) - len(suf) >= 3:
            return w[: -len(suf)]
    return w


def _get(url: str, timeout: int = 10) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": "ATANOR-roamer/0.1"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read(400_000).decode("utf-8", errors="ignore")


def _search(query: str, n: int = 5) -> list[dict]:
    # engines pinned to the empirically-working lane (mojeek); paced to respect rate limits.
    q = urllib.parse.urlencode({"q": query, "format": "json", "engines": "mojeek"})
    try:
        data = json.loads(_get(f"{_SEARX}?{q}"))
        time.sleep(2.5)
        return data.get("results", [])[:n]
    except Exception:
        return []


def _domain(url: str) -> str:
    return urllib.parse.urlparse(url).netloc.lower().removeprefix("www.")


def _page_texts(html: str) -> list[tuple[str, str]]:
    """(modality, text) lanes from one page: body sentences + image alt + figure captions."""
    out: list[tuple[str, str]] = []
    body = _TAG.sub(" ", html)
    for sent in re.split(r"(?<=[.!?])\s+", body):
        out.append(("text", sent))
    for alt in _ALT.findall(html):                      # multimodal-lite: text ABOUT an image
        out.append(("img_alt", alt))
    for cap in _FIGCAP.findall(html):
        out.append(("figcaption", _TAG.sub(" ", cap)))
    return out


def _mine_page(url: str, tok_a: str, tok_b: str) -> list[dict]:
    """Directed observations touching the target pair, typed with domain+modality."""
    try:
        html = _get(url)
    except Exception:
        return []
    return _mine_texts(_page_texts(html), _domain(url), url, tok_a, tok_b)


def _mine_texts(texts: list[tuple[str, str]], dom: str, url: str,
                tok_a: str, tok_b: str) -> list[dict]:
    sa, sb, obs = _stem(tok_a), _stem(tok_b), []
    for modality, text in texts:
        for a, b, ctx in sentence_pairs_ctx(text):
            a, b = _stem(a), _stem(b)                   # store stem-normalized (grammar op)
            if {a, b} & {sa, sb}:                       # touches the exploration target
                obs.append({"a": a, "b": b, "ctx": list(ctx), "domain": dom,
                            "modality": modality, "ts": int(time.time()), "url": url})
    return obs


def _queries(tok_a: str, tok_b: str) -> list[str]:
    # natural connective probes, both directions -- the WORLD decides which one is real.
    # (quoted-phrase queries return nothing on the working engine lane; natural phrasing mines.)
    return [f"{tok_a} before {tok_b}", f"{tok_b} before {tok_a}",
            f"{tok_b} after {tok_a}", f"{tok_a} after {tok_b}",
            f"{tok_a} {tok_b} sequence timeline"]


def load_web_counts() -> dict:
    if _WEB_COUNTS.exists():
        return json.loads(_WEB_COUNTS.read_text(encoding="utf-8"))
    return {}


def web_consensus(tok_a: str, tok_b: str, counts: dict | None = None) -> tuple[float, int, int] | None:
    """(P(a before b), n_domains_ab, n_domains_ba) from k-source web evidence; None = no belief.
    A direction only counts through DOMAIN diversity (one loud site is one vote)."""
    c = counts if counts is not None else load_web_counts()
    sa, sb = _stem(tok_a), _stem(tok_b)
    dom_ab = set((c.get(f"{sa}|{sb}") or {}).keys())
    dom_ba = set((c.get(f"{sb}|{sa}") or {}).keys())
    if len(dom_ab | dom_ba) < 2:
        return None                                      # consensus needs >=2 independent sources
    p = (len(dom_ab) + 1) / (len(dom_ab) + len(dom_ba) + 2)
    return p, len(dom_ab), len(dom_ba)


def explore_pair(tok_a: str, tok_b: str, field: PrecedenceField | None,
                 max_pages: int = 6) -> dict:
    """One full predict->roam->verdict->receipt cycle for an uncertain pair."""
    _DIR.mkdir(parents=True, exist_ok=True)
    prior = field.order_confidence(tok_a, tok_b) if field else None      # PREDICT before looking

    seen_urls: set[str] = set()
    all_obs: list[dict] = []
    for q in _queries(tok_a, tok_b):
        for r in _search(q, n=3):
            url = r.get("url", "")
            snippet = str(r.get("content", ""))         # SERP snippet = cleanest sentence lane
            if snippet:
                all_obs.extend(_mine_texts([("serp", snippet)], _domain(url), url, tok_a, tok_b))
            if not url or url in seen_urls or len(seen_urls) >= max_pages:
                continue
            seen_urls.add(url)
            all_obs.extend(_mine_page(url, tok_a, tok_b))

    counts = load_web_counts()
    with open(_WEB_OBS, "a", encoding="utf-8") as f:
        for o in all_obs:
            f.write(json.dumps(o) + "\n")
            key = f"{o['a']}|{o['b']}"
            counts.setdefault(key, {})
            counts[key][o["domain"]] = counts[key].get(o["domain"], 0) + 1
    _WEB_COUNTS.write_text(json.dumps(counts), encoding="utf-8")

    verdict = web_consensus(tok_a, tok_b, counts)
    contradicted = (prior is not None and verdict is not None
                    and (prior > 0.5) != (verdict[0] > 0.5))
    if contradicted:                                     # the world said no -> failure receipt
        with open(_RECEIPTS, "a", encoding="utf-8") as f:
            f.write(json.dumps({"pair": [tok_a, tok_b], "prior": round(prior, 3),
                                "web": round(verdict[0], 3), "domains": verdict[1] + verdict[2],
                                "ts": int(time.time())}) + "\n")
    return {"pair": [tok_a, tok_b], "prior": prior, "pages": len(seen_urls),
            "observations": len(all_obs), "verdict": verdict, "contradicted": contradicted}


def refit_with_web(base_counts: Counter | None = None) -> PrecedenceField:
    """Fold roamed web observations into the SAME cognitive space: web pairs join the Bradley-Terry
    fit weighted by DOMAIN DIVERSITY (each independent domain votes; one loud site cannot shout).
    Even without a direct (a,b) observation, roamed neighbors (e.g. ignition) align coordinates
    transitively. Saves and returns the refit field."""
    if base_counts is None:
        base_counts = Counter({tuple(k.split("|")): v for k, v in
                               json.loads((_DIR / "order_counts.json").read_text()).items()})
    web = load_web_counts()
    for key, domains in web.items():
        a, b = key.split("|")
        # weight: capped per-domain evidence x domain-diversity bonus
        w = sum(min(n, 3) for n in domains.values()) * (2 if len(domains) >= 2 else 1)
        base_counts[(a, b)] += w
    field = PrecedenceField.fit(base_counts)
    field.save()
    return field


def uncertain_targets(field: PrecedenceField | None, candidate_pairs: list[tuple[str, str]],
                      band: float = 0.2) -> list[tuple[str, str]]:
    """Curiosity queue: pairs whose current belief is weak (|conf-0.5|<band) or absent."""
    out = []
    for a, b in candidate_pairs:
        conf = field.order_confidence(a, b) if field else None
        if conf is None or abs(conf - 0.5) < band:
            out.append((a, b))
    return out


# --------------------------------------------------------------------------- browser-backed roam
def roam_and_learn(topics: list[str], max_pages_per_topic: int = 8,
                   headless: bool = True) -> dict:
    """WIRE-UP: drive the real browser across DIVERSE (non-encyclopedia) doorways, follow the link
    graph, mine order observations from what it reads, and fold them into the precedence field.
    No search-engine API. The seed registry starts the roam across many registers; the roamer ends
    up on domains nobody listed. Returns a harvest summary; the refit field is saved."""
    from packages.atanor_browser.autonomous_surf import Surfer
    from packages.atanor_browser.seed_registry import doorways_for, evergreen_seeds

    counts = load_web_counts()
    pages_read = blocked = new_obs = 0
    with Surfer(headless=headless) as s:
        for topic in topics:
            toks = [t for t in re.split(r"[^a-z0-9]+", topic.lower()) if len(t) > 2]
            seeds = doorways_for(topic, per_register=1)[:6] + evergreen_seeds()[:2]
            pages = s.roam_from_seeds(seeds, toks, max_pages=max_pages_per_topic, per_page_links=4)
            for p in pages:
                if p.blocked:
                    blocked += 1
                    continue
                pages_read += 1
                dom = urllib.parse.urlparse(p.url).netloc.lower().removeprefix("www.")
                for line in p.reading_order:
                    for a, b, _ in sentence_pairs_ctx(line):
                        key = f"{a}|{b}"
                        counts.setdefault(key, {})
                        counts[key][dom] = counts[key].get(dom, 0) + 1
                        new_obs += 1
    _WEB_COUNTS.write_text(json.dumps(counts), encoding="utf-8")
    field = refit_with_web()
    return {"topics": len(topics), "pages_read": pages_read, "stepped_away": blocked,
            "observations": new_obs, "web_pairs": len(counts), "field_tokens": len(field.phase)}


def curiosity_topics(field, seed_pairs: list[tuple[str, str]], band: float = 0.25) -> list[str]:
    """Turn the uncertain-pair queue into natural-language roam topics (what to go learn about)."""
    tops = []
    for a, b in uncertain_targets(field, seed_pairs, band=band):
        tops.append(f"{a.replace('_',' ')} {b.replace('_',' ')} timeline sequence")
    return tops


def daemon(rounds: int = 0, sleep_s: int = 900, topics: list[str] | None = None) -> None:
    """Self-continuing roam (알아서 계속): each round pulls the curiosity queue, roams to learn,
    refits, and (honestly) logs what moved. rounds=0 means loop until interrupted."""
    from packages.temporal_reasoning.precedence_field import PrecedenceField
    default_pairs = [("dispatched_at", "arrived_at"), ("detected_at", "resolved_at"),
                     ("launched_at", "abort_decision_at"), ("ordered_at", "delivered_at"),
                     ("manufactured_at", "shipped_at"), ("symptom_at", "diagnosis_at")]
    i = 0
    while rounds == 0 or i < rounds:
        i += 1
        field = PrecedenceField.load()
        tops = topics or curiosity_topics(field, default_pairs)
        if not tops:
            tops = ["product recall defect timeline", "rocket launch abort sequence"]
        summary = roam_and_learn(tops[:4])
        print(f"[roam-daemon r{i}] {summary}", flush=True)
        if rounds and i >= rounds:
            break
        time.sleep(sleep_s)
