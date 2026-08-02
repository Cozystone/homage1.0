# -*- coding: utf-8 -*-
"""Defect ledger — what the advisors have actually complained about, and how insistently.

The night of 2026-07-21 supplied the design: GPT-5.4's comprehensive review flagged "a german
physicist" at 03:08, 05:33 and 07:19 — three independent sightings of one defect — while the
dialogue coach converged on junk-token drilling from three different angles. REPETITION IS THE
SIGNAL. An observation made once may be taste; the same observation reached independently again
and again is a defect the system keeps walking into.

So a defect's priority is how many separate advisor sessions arrived at it, not how strongly any
one of them worded it. That also resists flattery and one-off hobby-horses: a single insistent
advisor cannot outrank a fault that keeps recurring on its own.

Read-only over the journals. Nothing here changes code.
"""
from __future__ import annotations

import json
import re
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
SOURCES = (
    REPO / "data" / "advisor_loop" / "comprehensive_review.jsonl",
    REPO / "data" / "advisor_loop" / "dialogue_coach.jsonl",
)
LOG = REPO / "data" / "self_repair" / "defects.jsonl"

# Content words that identify WHAT a critique is about, so two wordings of the same fault collide.
_STOP = {"the", "and", "that", "this", "with", "from", "they", "them", "their", "there", "which",
         "would", "could", "should", "because", "when", "what", "your", "you", "its", "it's",
         "not", "but", "for", "are", "was", "were", "has", "have", "had", "can", "cannot", "does",
         "into", "than", "then", "them", "these", "those", "some", "more", "most", "only", "also",
         "very", "just", "still", "even", "here", "each", "both", "one", "two", "atanor", "turn",
         "turns", "answer", "answers", "reply", "replies", "line", "lines", "item", "items"}


# A critique is REPAIRABLE when it points at something a search/replace edit could reach: a repo
# path, a code identifier, or a quoted literal from real output. Discovered by running the loop
# live — the most-repeated defect (5 sightings, "a clean instance of the Chinese-room context
# problem") drew a correct NO PATCH, because no edit follows from a philosophical observation.
# Abstract critiques are still kept and still valuable (they steer design), they simply do not get
# repair cycles spent on them. Recurrence says WHAT MATTERS; concreteness says WHAT IS ACTIONABLE.
_CONCRETE = (
    re.compile(r"(?:packages|scripts|apps)[/\\][\w./\\-]+\.py"),   # a repo path
    re.compile(r"\b[a-z_][a-z0-9_]{3,}\(\)|\b_[a-z][a-z0-9_]{3,}\b"),  # func() or _identifier
    # A quoted literal long enough to BE the thing to change — a whole produced phrase like
    # "Einstein is a german physicist", not an example word. The 4-char version let the abstract
    # Chinese-room critique through, because it quotes sample words ("parts," "letter,") while
    # naming nothing an edit could reach. Measured live; tightened to a phrase.
    re.compile(r"[\"“”'‘’][^\"“”'‘’]{12,120}[\"“”'‘’]"),
)


@dataclass
class Defect:
    key: str                              # the normalized fingerprint (what the fault IS)
    sightings: int                        # how many independent advisor sessions reached it
    quotes: list[str] = field(default_factory=list)   # verbatim, for the repair request
    sources: list[str] = field(default_factory=list)  # which journal each sighting came from
    hints: list[str] = field(default_factory=list)    # repo files the reviews were LOOKING at

    @property
    def repairable(self) -> bool:
        """Can an edit actually REACH this? A repair needs a LOCATION, not just a symptom.

        Regex-guessing concreteness from prose was tried and kept failing honestly: a critique that
        quotes example words ('parts,' 'letter,' 'Lower South,') reads concrete but names nowhere to
        cut. The location is already recorded — comprehensive reviews journal WHICH FILE they were
        reviewing — so use that fact instead of inferring it from wording."""
        if self.hints:
            return True
        return any(rx.search(q) for q in self.quotes for rx in _CONCRETE[:2])   # path / identifier

    def best_quotes(self, n: int = 3) -> list[str]:
        """The sightings to hand an advisor, most ACTIONABLE first.

        A cluster is one recurring theme reported many ways, so it usually holds both a concrete
        sighting ('Einstein is a german physicist' is visibly non-native) and an abstract one (this
        is an instance of the Chinese-room context problem). Live runs showed the abstract one
        arriving first and drawing a correct NO PATCH — the evidence was in the cluster, just not
        in the part that got sent. Lead with what an edit can reach."""
        return sorted(self.quotes,
                      key=lambda q: -sum(bool(rx.search(q)) for rx in _CONCRETE))[:n]

    def record(self) -> dict:
        return {"key": self.key, "sightings": self.sightings, "repairable": self.repairable,
                "quotes": self.quotes[:3], "sources": self.sources, "hints": self.hints}


MIN_SHARED = 2          # distinctive words two reports must share to be judged the same fault


def _terms(text: str) -> set[str]:
    """The distinctive content words of a critique — what it is ABOUT, stripped of phrasing."""
    return {w for w in re.findall(r"[a-z']{3,}", text.lower()) if w not in _STOP}


def _same_fault(a: set[str], b: set[str]) -> bool:
    """Two reports describe one fault when they share enough distinctive vocabulary.

    Exact-key matching was tried first and FAILED on real data: the advisors word the same defect
    differently every night ('the demonym german should be capitalized' / 'a nationality adjective
    german must be capitalized' / 'the demonym german is lowercase'), so identical keys never
    collided and a thrice-reported fault looked like three one-offs — the exact signal this ledger
    exists to catch. Overlap, not equality, is what recurrence actually looks like."""
    shared = a & b
    if len(shared) < MIN_SHARED:
        return False
    return len(shared) / max(1, min(len(a), len(b))) >= 0.25


# An advisor that asks for the material is not reporting a defect. The journals still hold such
# replies from before the openclaw transport bug was found (the .cmd shim silently ate everything
# after the first newline, so GPT genuinely received no transcript and honestly said so). Those are
# records of OUR bug, already fixed — not faults to spend a repair cycle on.
_DEFLECTION = re.compile(
    r"\b(send|paste|share|provide|attach)\b.{0,40}\b(transcript|code|material|exchange|file)\b"
    r"|\bnot (actually )?(present|included|visible|attached)\b"
    r"|\bi (can'?t|cannot) (critique|review|analyze|assess)\b", re.I | re.S)


def _critique_items(text: str) -> list[str]:
    """Split a numbered critique into its individual findings (each is a separate claim),
    dropping replies that request material instead of reporting a fault."""
    parts = re.split(r"(?m)^\s*(?:\d+[.)]|[-*])\s+", text or "")
    return [p.strip() for p in parts
            if len(p.strip()) > 40 and not _DEFLECTION.search(p)]


def collect(limit_per_source: int = 40) -> list[Defect]:
    """Every defect the advisors have reported, most-repeated first. Read-only.

    Reports are CLUSTERED by shared vocabulary (see `_same_fault`), so three differently-worded
    sightings of one fault count as three — which is the whole point of the ledger."""
    clusters: list[tuple[set[str], Defect]] = []
    for src in SOURCES:
        if not src.exists():
            continue
        rows = [json.loads(l) for l in src.open(encoding="utf-8") if l.strip()]
        for row in rows[-limit_per_source:]:
            hint = (row.get("source") or "").replace("\\", "/")
            for item in _critique_items(row.get("critique", "")):
                terms = _terms(item)
                if len(terms) < 3:
                    continue
                for known, d in clusters:
                    if _same_fault(terms, known):
                        d.sightings += 1
                        d.quotes.append(item[:400])
                        d.sources.append(src.name)
                        if hint and hint not in d.hints:
                            d.hints.append(hint)
                        known |= terms                    # the cluster's vocabulary widens
                        d.key = _key_of(known, d.quotes)
                        break
                else:
                    clusters.append((set(terms),
                                     Defect(key=_key_of(terms, [item]), sightings=1,
                                            quotes=[item[:400]], sources=[src.name],
                                            hints=[hint] if hint else [])))
    return sorted((d for _, d in clusters), key=lambda d: (-d.sightings, d.key))


def _key_of(terms: set[str], quotes: list[str]) -> str:
    """A stable name for a cluster: the words its reports actually keep repeating."""
    counts = Counter(w for q in quotes for w in _terms(q) if w in terms)
    return " ".join(sorted(w for w, _ in counts.most_common(5)))


def top_defect(exclude_keys: set[str] | None = None, require_repairable: bool = True) -> Defect | None:
    """The most-repeated REPAIRABLE defect not already attempted.

    Both filters earn their place from live runs: recurrence stops one insistent advisor from
    setting the agenda, and repairability stops the loop from spending its cycles asking for a
    patch that cannot exist. Pass require_repairable=False to see the whole ledger."""
    ex = exclude_keys or set()
    for d in collect():
        if d.key in ex:
            continue
        if require_repairable and not d.repairable:
            continue
        return d
    return None


def journal(d: Defect, outcome: str, detail: str = "", now_utc: float = 0.0) -> None:
    LOG.parent.mkdir(parents=True, exist_ok=True)
    rec = d.record() | {"outcome": outcome, "detail": detail, "ts": now_utc}
    with LOG.open("a", encoding="utf-8") as f:
        f.write(json.dumps(rec, ensure_ascii=False) + "\n")


def attempted_keys() -> set[str]:
    """Defect keys already tried (any outcome) — so the loop advances instead of retrying one fault."""
    if not LOG.exists():
        return set()
    out = set()
    for line in LOG.open(encoding="utf-8"):
        if line.strip():
            try:
                out.add(json.loads(line)["key"])
            except Exception:
                continue
    return out
