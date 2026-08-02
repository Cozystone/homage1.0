# -*- coding: utf-8 -*-
"""Expedition API — the local engine's endpoint for the ATANOR web-surfer Chrome extension.

The extension sends the text of a page the user is browsing; the engine runs it through the SAME
safety pipeline as an autonomous expedition (epistemic shield → candidate, never production). This
is the "browser control / free surfing → learn" road, with the composure guarantee built in:
swallowed page text is DATA, never a command, and nothing here writes the curated store.

Local-only, read-toward-production. Every ingest is journaled to data/autonomy/expedition_journal.jsonl.
"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter
from pydantic import BaseModel, Field

router = APIRouter(prefix="/api/expedition", tags=["expedition"])


class IngestPageIn(BaseModel):
    url: str = Field(default="", max_length=2000)
    text: str = Field(default="", max_length=200_000)


@router.post("/ingest-page")
def ingest_page(body: IngestPageIn) -> dict[str, Any]:
    """Ingest one browsed page: shield → distill → candidate (never production). Returns a report
    the extension can show (blocked-as-injection, or N candidate sentences held for consensus)."""
    from packages.autonomy_kernel.web_expedition import ingest_page as _ingest
    return _ingest(body.url, body.text)


@router.get("/activity")
def activity() -> dict[str, Any]:
    """Live feed of what ATANOR is doing right now (unified autonomy journals) — the Ato orb
    overlay polls this to show, in real time, what the AI is reading/learning/saying."""
    from packages.autonomy_kernel.activity_feed import feed
    return feed()


@router.get("/next-destination")
def next_destination() -> dict[str, Any]:
    """Autonomous browse: where does ATANOR want to read next? The extension polls this and, if
    {navigate:true}, navigates the tab to the returned safe URL (Wikipedia frontier topic). Only
    ever a READ; off unless the owner enabled autobrowse (browse_director.json)."""
    from packages.autonomy_kernel.browse_director import next_destination as _nd
    return _nd()


class ChooseResultIn(BaseModel):
    topic: str = Field(default="", max_length=200)
    results: list[dict[str, Any]] = Field(default_factory=list)


@router.post("/choose-result")
def choose_result(body: ChooseResultIn) -> dict[str, Any]:
    """Search-first autobrowse, step 2: the extension sends the live search results it sees, and
    ATANOR CHOOSES which platform to read (palette tier × topic fit) — a real decision over real
    options, journaled with the why. The extension then navigates to the chosen URL only."""
    from packages.autonomy_kernel.browse_director import choose_result as _cr
    return _cr(body.topic, body.results)


@router.post("/run")
def run_expedition(topic: str = "", min_consensus: int = 2) -> dict[str, Any]:
    """Kick one topic expedition (search → shield → domain-consensus → candidate). A READ; writes
    nothing to production. Empty candidates if no search source is reachable."""
    from packages.autonomy_kernel.web_expedition import expedition
    if not topic.strip():
        return {"error": "topic required"}
    rep = expedition(topic.strip(), min_consensus=min_consensus)
    rep.pop("candidates", None)  # keep the API response light; full set is in the journal
    return rep
