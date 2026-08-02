# -*- coding: utf-8 -*-
"""Browser session orchestration — the layer between the native shell and ATANOR.

The ATANOR browser is a Chrome-like app: a NATIVE shell (Tauri WebviewWindow /
Electron BrowserView / CEF) renders the real web. That native shell cannot be
built in this Python engine — but the SESSION LOGIC it drives can, and it can
be fully tested here. This module is that logic: tabs as first-class objects,
navigation events routed to the two ATANOR lanes, per-tab history, active-tab
tracking. The native shell just emits events (opened, navigated, closed) and
this decides what the brain does with them.

Lane routing (the two-lane rule, enforced here):
  * EVERY navigation -> the PERSONAL activity journal (local, always).
  * page CONTENT -> the SHARED ingest lane ONLY when the shell hands us the DOM
    text (opt-in per navigation) — browsing history is private by default;
    contributing a page's facts to the shared graph is a separate, explicit act.

State is process-local (a running browser session); persistence of history is
the activity journal's job. Deterministic, no I/O beyond the journal it calls.
"""
from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from typing import Any


@dataclass
class Tab:
    tab_id: str
    url: str = ""
    title: str = ""
    history: list[dict[str, Any]] = field(default_factory=list)
    opened_at: float = field(default_factory=time.time)

    def to_dict(self) -> dict[str, Any]:
        return {"tab_id": self.tab_id, "url": self.url, "title": self.title,
                "history_len": len(self.history)}


class BrowserSession:
    """One running browser session: its tabs and the ATANOR wiring."""

    def __init__(self, *, journal: Any = None) -> None:
        self._tabs: dict[str, Tab] = {}
        self._active: str | None = None
        # injectable for tests; defaults to the real activity journal
        if journal is None:
            from . import activity_journal as journal
        self._journal = journal

    # ---- tab lifecycle ----
    def open_tab(self, url: str = "") -> dict[str, Any]:
        tab_id = uuid.uuid4().hex[:8]
        self._tabs[tab_id] = Tab(tab_id=tab_id, url=url)
        self._active = tab_id
        if url:
            self.navigate(tab_id, url)
        return {"tab_id": tab_id, "active": True}

    def close_tab(self, tab_id: str) -> dict[str, Any]:
        if tab_id not in self._tabs:
            return {"ok": False, "reason": "no such tab"}
        del self._tabs[tab_id]
        if self._active == tab_id:
            self._active = next(iter(self._tabs), None)
        return {"ok": True, "closed": tab_id, "active": self._active}

    def activate(self, tab_id: str) -> dict[str, Any]:
        if tab_id not in self._tabs:
            return {"ok": False, "reason": "no such tab"}
        self._active = tab_id
        return {"ok": True, "active": tab_id}

    # ---- navigation (the ATANOR wiring lives here) ----
    def navigate(self, tab_id: str, url: str, *, title: str = "",
                 dom_text: str | None = None,
                 contribute_content: bool = False) -> dict[str, Any]:
        """Drive a tab to a URL. ALWAYS journals to the personal lane; routes
        page CONTENT to the shared ingest lane only when the shell supplies the
        DOM AND the user opted to contribute (private by default)."""
        tab = self._tabs.get(tab_id)
        if tab is None:
            return {"ok": False, "reason": "no such tab"}
        tab.url, tab.title = url, title
        tab.history.append({"url": url, "title": title, "at": time.strftime("%Y-%m-%dT%H:%M:%S")})

        # PERSONAL lane — always, local only
        journaled = self._journal.record_activity("visit", url=url, title=title)

        # SHARED lane — opt-in, only if DOM text is provided
        contributed = None
        if contribute_content and dom_text:
            try:
                from .browser_ingest import ingest_page

                contributed = ingest_page(dom_text, url=url)
            except Exception:
                contributed = None
        return {"ok": True, "tab_id": tab_id, "journaled": journaled,
                "contributed": contributed}

    def search(self, tab_id: str, query: str, engine_url: str = "") -> dict[str, Any]:
        """A search action: journaled to the personal lane (PII-gated inside)."""
        j = self._journal.record_activity("search", url=engine_url, query=query)
        return {"ok": True, "journaled": j}

    def back(self, tab_id: str) -> dict[str, Any]:
        tab = self._tabs.get(tab_id)
        if tab is None or len(tab.history) < 2:
            return {"ok": False, "reason": "no back history"}
        tab.history.pop()                 # drop current
        prev = tab.history[-1]
        tab.url, tab.title = prev["url"], prev.get("title", "")
        return {"ok": True, "url": tab.url}

    # ---- introspection ----
    def state(self) -> dict[str, Any]:
        return {"tabs": [t.to_dict() for t in self._tabs.values()],
                "active": self._active, "count": len(self._tabs)}

    def tab_history(self, tab_id: str) -> list[dict[str, Any]]:
        tab = self._tabs.get(tab_id)
        return list(tab.history) if tab else []
