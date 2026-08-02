# -*- coding: utf-8 -*-
"""Whether ATANOR can still see the world — measured by what comes back, not by a health check.

    from packages.autonomy_kernel.source_health import world_sight
    world_sight()

WHY THIS EXISTS, and it is the eighth silent failure of one day. The primary web source is a
self-hosted SearXNG; the agreed doctrine names it the first source for open-web intake. It went down
with the Docker engine, `_searxng_reachable()` returned False, `provider_api_search` fell back to the
reference lanes, and **every search still returned results** -- Wikipedia, Wiktionary, WordNet, GCIDE.
Nothing anywhere reported a problem, because from the caller's side nothing looked like one.

So for three days the roaming loop roamed a dictionary while believing it was reading the world. Its
inner life shows the consequence directly: 23,485 turns of "the world holds X, and I know it exists
but little of what it is" and not one contact with a person's actual words.

WHAT IS MEASURED, and why not the health check. A reachability probe answers "is the port open",
which is the question that was already being asked and already answered uselessly -- a degraded lane
that still returns rows is invisible to it. What matters is the SHAPE OF WHAT COMES BACK:

    reference_share   the fraction of results from dictionary/encyclopedia hosts. At 1.0 the system
                      is not reading the world, whatever the port says.

That distinguishes the three states a health check collapses into one: the source is up and diverse,
the source is up and returning only reference, and the source is gone.

WHERE IT GOES. Into `sense_deficits`, which the living beat's interoception already reads, which
`standing_concerns` already takes up as work. Nothing new is wired -- the signal joins the path that
exists, so the MIND notices "I cannot see the world right now" and decides what to do about it. That
is the owner's rule kept: the organ senses; it does not decide.
"""
from __future__ import annotations

from urllib.parse import urlparse

#: hosts that are reference works rather than the world. Not a quality judgement -- a dictionary is
#: excellent at being a dictionary. It is simply not people, and people are what the voice lacks.
_REFERENCE = ("wikipedia.org", "wiktionary.org", "wordnetweb.princeton.edu", "gcide.gnu.org.ua",
              "dbpedia.org", "britannica.com", "merriam-webster.com", "dictionary.com")

#: a probe that any working open-web source answers with ordinary pages. Deliberately mundane: a
#: query whose answer is not in a dictionary, so a reference-only lane has nothing to return but
#: definitions of its words.
_PROBE = "people describing what helped them get through a hard week"


def _is_reference(url: str) -> bool:
    host = (urlparse(str(url or "")).hostname or "").lower()
    return any(host.endswith(d) or d in host for d in _REFERENCE)


def world_sight(probe: str = _PROBE, count: int = 20) -> dict:
    """Can I currently reach the world, or only its dictionaries?"""
    import sys
    from pathlib import Path
    api = Path(__file__).resolve().parents[2] / "apps" / "api"
    if str(api) not in sys.path:
        sys.path.insert(0, str(api))
    try:
        from app.services.web_search import _searxng_reachable, provider_api_search
    except Exception as exc:
        return {"state": "unknown", "why": f"search module unavailable: {type(exc).__name__}",
                "primary_up": None, "reference_share": None}

    primary = None
    try:
        primary = bool(_searxng_reachable())
    except Exception:
        primary = None

    try:
        rows = provider_api_search(probe, count) or []
    except Exception as exc:
        return {"state": "blind", "why": f"search raised {type(exc).__name__}",
                "primary_up": primary, "results": 0, "reference_share": None}

    if not rows:
        return {"state": "blind", "why": "no results at all", "primary_up": primary,
                "results": 0, "reference_share": None}

    ref = sum(1 for r in rows if _is_reference(r.get("url") or ""))
    share = round(ref / len(rows), 3)

    # THE TRIGGER IS THE FACT, NOT A THRESHOLD I PICKED.
    #
    # The first version keyed everything on `reference_share` against bars of 0.7 and 0.95, chosen by
    # guessing. Measured immediately afterwards: 0.382 with the source up, 0.565 with it down. Both
    # below 0.7, so the sensor built to catch a three-day silent failure reported "sighted" while
    # simulating that exact failure -- decorative, and by the same hand-picked-constant mistake this
    # session has been removing from other people's code all day.
    #
    # The primary source being down is not a statistic. The doctrine names SearXNG as the first source
    # for open-web intake; if it is gone, this system IS reduced to fallbacks, whatever the mix
    # happens to look like on one probe. So that fact triggers, and the share becomes what it should
    # always have been -- evidence of HOW degraded, reported alongside rather than deciding.
    if primary is False:
        state = "dictionary_only" if share >= 0.9 else "degraded"
        why = ("the primary open-web source is unreachable; what returns is coming from fallback "
               f"lanes, {int(share * 100)}% of it reference works")
    elif share >= 0.9:
        state, why = "dictionary_only", ("the source answers and returns nothing but reference works. "
                                         "The port is open and I am still not seeing the world")
    else:
        state, why = "sighted", ""
    return {"state": state, "why": why, "primary_up": primary, "results": len(rows),
            "reference_share": share,
            "reading": ("measured by the SHAPE of what returns, not by whether a port answers -- a "
                        "degraded lane that still returns rows is invisible to a health check")}


def deficit() -> dict | None:
    """The world-sight signal as a deficit, for `sense_deficits` to carry into the mind."""
    s = world_sight()
    if s["state"] == "sighted":
        return None
    sev = {"blind": 0.9, "dictionary_only": 0.8, "degraded": 0.5, "unknown": 0.3}.get(s["state"], 0.3)
    ref = s.get("reference_share")
    return {"kind": "world_unseen", "severity": sev,
            "evidence": f"{s['state']}: {s['why']}"
                        + (f" (reference share {ref}, primary source up={s.get('primary_up')})"
                           if ref is not None else "")}
