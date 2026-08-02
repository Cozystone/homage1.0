# -*- coding: utf-8 -*-
"""Grounded opinion engagement -- participate in a subjective/comparison turn WITHOUT fabricating.

The ITT pilot exposed that opinion turns ("Do museums matter more than cinemas?") had no engagement
path at all: they fell to the generic greeting bank ("Hi. Let's look at it together."). This composes
a real contribution the honest way (the #116 doctrine, hallucination-0):

  - extract the two things being weighed (X vs Y);
  - for each, use ONLY grounded facts supplied by the caller (what X is, what Y is) -- never invent
    a property;
  - present both sides and then DECLINE to assert a single correct answer, because a value question
    has none. Taking a fake side would be a fabrication; naming the trade-off is the honest view.

No hand-authored 'opinions' are stored. If no grounding is available for either side, it says so and
engages at the level of the trade-off itself, still without inventing facts.
"""
from __future__ import annotations

import re

# SUBJECTIVE-comparison markers ONLY. Deliberately excludes measurable comparatives (taller/bigger/
# faster/older) and the bare "or" either/or form, because those can be FACTUAL questions ("Is Everest
# taller than K2?", "Is Paris in France or Germany?") which must go to the fact lane, not here.
_COMPARE = re.compile(
    r"\b(?:do|does|is|are|should)\b.*?\b(\w[\w\- ]*?)\s+"
    r"(?:matter\s+more\s+than|more\s+important\s+than|better\s+than|worth\s+more\s+than|vs\.?|versus)\s+"
    r"(\w[\w\- ]*?)\b(?:\s+for\b|\s+in\b|\s+as\b|\?|$)",
    re.IGNORECASE)


def extract_pair(question: str) -> tuple[str, str] | None:
    """(X, Y) being weighed, or None. Grammar-level extraction, not a topic table."""
    m = _COMPARE.search(question or "")
    if not m:
        return None
    x, y = m.group(1).strip(" ?."), m.group(2).strip(" ?.")
    # trim a trailing verb the 'or' form can capture ("tea or coffee better" -> coffee, not "coffee better")
    y = re.sub(r"\s+(better|more|worse|matter[s]?)$", "", y, flags=re.IGNORECASE).strip()
    if not x or not y or x.lower() == y.lower():
        return None
    return x, y


def compose(question: str, grounding: dict[str, str] | None = None) -> str | None:
    """Compose a grounded, balanced reflection for a comparison/value turn, or None if the turn is
    not a comparison. `grounding` maps a term (lowercased) -> one grounded fact sentence about it
    (supplied by the caller from the graph); missing terms are handled honestly."""
    pair = extract_pair(question)
    if pair is None:
        return None
    x, y = pair
    g = {k.lower(): v for k, v in (grounding or {}).items()}
    gx, gy = g.get(x.lower()), g.get(y.lower())
    parts: list[str] = []
    if gx and gy:
        parts.append(f"Both matter, in different ways. {gx.rstrip('.')}. {gy.rstrip('.')}.")
    elif gx or gy:
        known = gx or gy
        parts.append(f"They serve different ends. {known.rstrip('.')}.")
    else:
        parts.append(f"{x[:1].upper()}{x[1:]} and {y} each answer a different need.")
    # the honest close: a value question has no single right answer; name the trade-off, don't fake a side
    parts.append(f"Which weighs more isn't a fact to look up — it depends on what you value more "
                 f"between what {x} offers and what {y} offers.")
    return " ".join(parts)
