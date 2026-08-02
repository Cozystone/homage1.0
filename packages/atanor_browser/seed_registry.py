# -*- coding: utf-8 -*-
"""Seed registry -- WHERE ATANOR starts roaming. Deliberately NOT encyclopedia-only.

Owner directive (2026-07-20): stop depending on Wikipedia; a textbook cannot solve every problem in
the world. Real order-of-events knowledge lives in news reports, incident write-ups, procedures,
Q&A threads, forums, standards, and manuals -- registers where things actually HAPPEN in time, not
where they are defined. Seeds span many registers so the link-graph roam leaves the encyclopedia
behind within one hop.

These are just doorways. The roamer follows outbound links from here across the open web; the seed
is the first step, not the source of truth. Nothing here is a whitelist of "approved" sites -- it is
a diverse set of starting points, and the roamer will end up on domains not listed here.
"""
from __future__ import annotations

import urllib.parse

# register -> list of (query_url_template with {q}) doorways. Mixed on purpose.
_REGISTERS: dict[str, list[str]] = {
    "qna": [                                   # people narrating real sequences of events
        "https://www.reddit.com/search/?q={q}",
        "https://stackexchange.com/search?q={q}",
        "https://www.quora.com/search?q={q}",
    ],
    "news": [                                  # events unfold in time here, with dates
        "https://apnews.com/search?q={q}",
        "https://www.reuters.com/site-search/?query={q}",
        "https://www.bbc.co.uk/search?q={q}",
    ],
    "reference_nonwiki": [                      # encyclopedic but NOT wikipedia
        "https://www.britannica.com/search?query={q}",
        "https://www.sciencedirect.com/search?qs={q}",
    ],
    "gov_standards": [                          # procedures, incident/recall/lifecycle records
        "https://www.nasa.gov/?s={q}",
        "https://search.usa.gov/search?query={q}",
        "https://www.faa.gov/search?q={q}",
    ],
    "howto_procedure": [                        # ordered steps -- pure temporal signal
        "https://www.wikihow.com/wikiHowTo?search={q}",
        "https://www.instructables.com/search/?q={q}",
    ],
    "science": [
        "https://arxiv.org/abs/{q}",
        "https://www.ncbi.nlm.nih.gov/pmc/?term={q}",
    ],
}

# a few evergreen deep-content doorways to guarantee the roam has somewhere rich to go even offline
# of any search box (these are followed, not trusted, and are NOT wikipedia).
_EVERGREEN: list[str] = [
    "https://apnews.com/hub/business",
    "https://www.reuters.com/technology/",
    "https://www.nasa.gov/news/all-news/",
    "https://www.recalls.gov/",
    "https://stackexchange.com/questions",
]


def doorways_for(query: str, registers: list[str] | None = None, per_register: int = 1) -> list[str]:
    """Concrete starting URLs for a topic, spread across registers (news/qna/gov/howto/...),
    never all from one place. Encyclopedia-free by construction."""
    q = urllib.parse.quote(query)
    picks = registers or list(_REGISTERS.keys())
    urls: list[str] = []
    for reg in picks:
        for tmpl in _REGISTERS.get(reg, [])[:per_register]:
            urls.append(tmpl.replace("{q}", q))
    return urls


def evergreen_seeds() -> list[str]:
    return list(_EVERGREEN)


def all_registers() -> list[str]:
    return list(_REGISTERS.keys())
