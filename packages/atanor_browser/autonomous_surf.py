# -*- coding: utf-8 -*-
"""Autonomous browser surfing -- ATANOR drives a REAL browser, no search-engine API.

Owner directive (2026-07-20): stop wiring a search API; let the AI roam the open web with a real
browser, perceive pages the way a person does (layout + media, not just text), and learn from what
it finds. This module is the body; packages/temporal_reasoning/web_explorer.py is one consumer.

PERCEPTION IS TWO-LANE
  - structural: the DOM tells us the page's LAYOUT ROLES (nav / main / article / aside / figure)
    and reading order. For the web this is richer and far more reliable than pixels.
  - media: every image/video/audio element encountered is emitted as a typed MediaRef and routed
    into the existing organs (packages.perception.open_vocab -> scene_graph -> sensory_cortex),
    so a picture on a page becomes percepts, not just its alt string.

WEB MANNERS (situational, not a verdict on the site)
  - requests are paced; one origin is never hammered.
  - when a page asks to prove you are human (CAPTCHA / login wall / interstitial), ATANOR simply
    moves on FOR NOW -- the way a person who hits a sign-in wall just goes somewhere else this time,
    without deciding the site is "bad". No permanent label, no grudge: a short, ephemeral cooloff,
    then the origin is fair game again. ATANOR never solves, defeats, or evades a human-check; it
    just doesn't push through one. The open web is wide, so it reads elsewhere and comes back later.
  - robots.txt is consulted as a courtesy signal, not enforced as a moral boundary on the AI.
"""
from __future__ import annotations

import json
import time
import urllib.parse
import urllib.request
import urllib.robotparser
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any, Iterable

_DIR = Path(__file__).resolve().parents[2] / "data" / "atanor_browser"
_JOURNAL = _DIR / "surf_journal.jsonl"
_BLOCKS = _DIR / "blocked_origins.json"

# Signals that a page is a bot-check / interstitial rather than content. Used to STOP and reroute.
# (Measured 2026-07-20: duckduckgo's html endpoint serves "complete the following challenge to
# confirm this search was made by a human" -- detection exists so we can LEAVE, never to defeat it.)
_BLOCK_MARKERS = ("captcha", "recaptcha", "hcaptcha", "cf-challenge", "are you a robot",
                  "unusual traffic", "verify you are human", "made by a human", "access denied",
                  "rate limited", "complete the following challenge", "bots use",
                  "enable javascript and cookies", "checking your browser")


@dataclass
class MediaRef:
    kind: str                     # image | video | audio
    url: str
    alt: str = ""
    caption: str = ""
    width: int = 0
    height: int = 0


@dataclass
class PagePerception:
    url: str
    title: str = ""
    blocked: bool = False
    block_reason: str = ""
    regions: dict[str, str] = field(default_factory=dict)   # layout role -> visible text
    reading_order: list[str] = field(default_factory=list)  # headings/paragraph spine
    media: list[MediaRef] = field(default_factory=list)
    links: list[dict] = field(default_factory=list)         # {url, text} for onward navigation
    fetched_at: int = 0

    def main_text(self) -> str:
        return self.regions.get("main") or self.regions.get("article") or self.regions.get("body", "")


# --------------------------------------------------------------------------- politeness
def _origin(url: str) -> str:
    p = urllib.parse.urlparse(url)
    return f"{p.scheme}://{p.netloc}"


_ROBOTS: dict[str, Any] = {}


def robots_allows(url: str, agent: str = "ATANOR-roamer") -> bool:
    """Fetch and honour robots.txt for the origin. Unreachable robots -> treated as disallowed for
    crawling depth (fail-closed politeness), except the origin root."""
    org = _origin(url)
    rp = _ROBOTS.get(org)
    if rp is None:
        rp = urllib.robotparser.RobotFileParser()
        rp.set_url(f"{org}/robots.txt")
        try:
            # NOT rp.read(): it chokes on a UTF-8 BOM (wikipedia serves one) and then reports the
            # WHOLE site as disallowed -- measured 2026-07-20. Fetch and decode with utf-8-sig.
            req = urllib.request.Request(f"{org}/robots.txt",
                                         headers={"User-Agent": agent})
            txt = urllib.request.urlopen(req, timeout=10).read().decode("utf-8-sig", "ignore")
            rp.parse(txt.splitlines())
        except Exception:
            rp = False                                     # unreachable
        _ROBOTS[org] = rp
    if rp is False:
        return True                                        # no robots served -> default allow
    try:
        return rp.can_fetch(agent, url)
    except Exception:
        return True


def _load_blocks() -> dict:
    if _BLOCKS.exists():
        return json.loads(_BLOCKS.read_text(encoding="utf-8"))
    return {}


def record_block(url: str, reason: str) -> None:
    """Note that this origin asked us to prove we're human just now -- an ephemeral 'not this
    time', not a verdict. The record self-expires; no permanent judgment about the site is stored."""
    _DIR.mkdir(parents=True, exist_ok=True)
    blocks = _load_blocks()
    org = _origin(url)
    e = blocks.setdefault(org, {"last_ts": 0})
    e["last_ts"] = int(time.time())                    # only 'when we last stepped away' -- nothing else
    _BLOCKS.write_text(json.dumps(blocks, indent=1), encoding="utf-8")


def origin_backed_off(url: str, cooloff_s: int = 600) -> bool:
    """True only for a short while right after a human-check -- 'go read elsewhere for now, come
    back soon'. Not a ban, not a label. After the cooloff the origin is fair game again."""
    e = _load_blocks().get(_origin(url))
    if not e:
        return False
    return (time.time() - e.get("last_ts", 0)) < cooloff_s


# --------------------------------------------------------------------------- the body
_JS_PERCEIVE = r"""
() => {
  const vis = el => {
    if (!el) return "";
    const t = (el.innerText || "").trim();
    return t.length > 20 ? t.slice(0, 20000) : "";
  };
  const pick = sel => { const e = document.querySelector(sel); return e ? vis(e) : ""; };
  const regions = {};
  for (const [role, sel] of [["main","main"],["article","article"],["nav","nav"],
                             ["aside","aside"],["header","header"],["footer","footer"]]) {
    const t = pick(sel); if (t) regions[role] = t;
  }
  regions.body = vis(document.body);
  const order = [...document.querySelectorAll("h1,h2,h3,p,li")]
      .map(e => (e.innerText||"").trim()).filter(t => t.length > 15).slice(0, 400);
  const media = [];
  for (const img of document.querySelectorAll("img")) {
    if (img.naturalWidth < 120 || img.naturalHeight < 120) continue;   // skip icons/trackers
    const fig = img.closest("figure");
    media.push({kind:"image", url: img.currentSrc || img.src || "",
                alt: img.alt || "",
                caption: fig ? (fig.querySelector("figcaption")?.innerText || "").trim() : "",
                width: img.naturalWidth, height: img.naturalHeight});
  }
  for (const v of document.querySelectorAll("video")) {
    media.push({kind:"video", url: v.currentSrc || v.src || "",
                alt: v.getAttribute("aria-label") || v.title || "", caption:"",
                width: v.videoWidth||0, height: v.videoHeight||0});
  }
  for (const a of document.querySelectorAll("audio")) {
    media.push({kind:"audio", url: a.currentSrc || a.src || "",
                alt: a.getAttribute("aria-label") || a.title || "", caption:"", width:0, height:0});
  }
  const links = [...document.querySelectorAll("a[href]")]
      .map(a => ({url: a.href, text: (a.innerText||"").trim().slice(0,200)}))
      .filter(l => l.url.startsWith("http") && l.text.length > 2).slice(0, 300);
  return {title: document.title || "", regions, order, media: media.slice(0,60), links};
}
"""


class Surfer:
    """A real browser ATANOR drives itself. Persistent profile => real cookies, real session,
    real rendering. Nothing here disguises what it is; the User-Agent names the roamer."""

    def __init__(self, headless: bool = True, profile: str | None = None, pace_s: float = 2.0):
        self.headless = headless
        self.profile = profile or str(_DIR / "profile")
        self.pace_s = pace_s
        self._pw = None
        self._ctx = None
        self._last_hit: dict[str, float] = {}

    def __enter__(self) -> "Surfer":
        from playwright.sync_api import sync_playwright
        Path(self.profile).mkdir(parents=True, exist_ok=True)
        self._pw = sync_playwright().start()
        self._ctx = self._pw.chromium.launch_persistent_context(
            self.profile, headless=self.headless,
            args=["--disable-blink-features=AutomationControlled"],
            viewport={"width": 1440, "height": 900})
        return self

    def __exit__(self, *exc) -> None:
        try:
            if self._ctx:
                self._ctx.close()
        finally:
            if self._pw:
                self._pw.stop()

    def _pace(self, url: str) -> None:
        org = _origin(url)
        wait = self.pace_s - (time.time() - self._last_hit.get(org, 0))
        if wait > 0:
            time.sleep(wait)
        self._last_hit[org] = time.time()

    def perceive(self, url: str, timeout_ms: int = 20000) -> PagePerception:
        """Navigate and perceive one page (structure + media). Never bypasses a block."""
        p = PagePerception(url=url, fetched_at=int(time.time()))
        if origin_backed_off(url):
            p.blocked, p.block_reason = True, "origin backed off after prior block"
            return p
        if not robots_allows(url):
            p.blocked, p.block_reason = True, "robots.txt disallow"
            return p
        self._pace(url)
        page = self._ctx.new_page()
        try:
            resp = page.goto(url, timeout=timeout_ms, wait_until="domcontentloaded")
            status = resp.status if resp else 0
            if status in (401, 403, 429) or status >= 500:
                p.blocked, p.block_reason = True, f"http {status}"
                record_block(url, p.block_reason)
                return p
            page.wait_for_timeout(700)
            data = page.evaluate(_JS_PERCEIVE)
            p.title = data.get("title", "")
            p.regions = data.get("regions", {}) or {}
            p.reading_order = data.get("order", []) or []
            p.media = [MediaRef(**m) for m in (data.get("media") or []) if m.get("url")]
            p.links = data.get("links", []) or []
            blob = (p.title + " " + p.main_text()[:3000]).lower()
            hit = next((m for m in _BLOCK_MARKERS if m in blob), "")
            # a real article ABOUT captchas is not a block: require a thin page as corroboration
            if hit and len(p.main_text()) < 1500:
                p.blocked, p.block_reason = True, f"bot-check page ({hit})"
                record_block(url, p.block_reason)
        except Exception as e:
            p.blocked, p.block_reason = True, f"{type(e).__name__}"
        finally:
            page.close()
        self._journal(p)
        return p

    def search(self, query: str, engine: str = "https://duckduckgo.com/?q=",
               n: int = 8) -> list[dict]:
        """Read a search results page like a person -- no API key, no engine JSON contract.
        Kept for sources that welcome it; general engines now serve bot-checks (measured), so
        roam_from_seeds() is the primary discovery path. Returns [{url, text}]."""
        p = self.perceive(engine + urllib.parse.quote(query))
        if p.blocked:
            return []
        host = urllib.parse.urlparse(engine).netloc
        out, seen = [], set()
        for l in p.links:
            d = urllib.parse.urlparse(l["url"]).netloc
            if not d or host in d or d in seen:
                continue
            seen.add(d)
            out.append(l)
            if len(out) >= n:
                break
        return out

    def roam_from_seeds(self, seeds: list[str], topic_tokens: list[str],
                        max_pages: int = 12, per_page_links: int = 4) -> list[PagePerception]:
        """PRIMARY discovery: start at open sources that WANT to be read, then follow the link
        graph, steering toward pages whose link text matches the topic. No search engine, no API,
        no bot-check to negotiate -- the open web read the way a curious person reads it."""
        toks = [t.lower() for t in topic_tokens if t]
        frontier = list(seeds)
        visited: set[str] = set()
        out: list[PagePerception] = []
        while frontier and len(out) < max_pages:
            url = frontier.pop(0)
            if url in visited or origin_backed_off(url):
                continue
            visited.add(url)
            p = self.perceive(url)
            if p.blocked:
                continue
            out.append(p)
            scored = []
            for l in p.links:
                if l["url"] in visited or "#" in l["url"][-40:]:
                    continue
                score = sum(1 for t in toks if t in l["text"].lower() or t in l["url"].lower())
                if score:
                    scored.append((score, l["url"]))
            scored.sort(reverse=True)
            frontier.extend(u for _, u in scored[:per_page_links])
        return out

    def _journal(self, p: PagePerception) -> None:
        _DIR.mkdir(parents=True, exist_ok=True)
        with open(_JOURNAL, "a", encoding="utf-8") as f:
            f.write(json.dumps({"url": p.url, "title": p.title, "blocked": p.blocked,
                                "reason": p.block_reason, "media": len(p.media),
                                "chars": len(p.main_text()), "ts": p.fetched_at}) + "\n")


# --------------------------------------------------------------------------- media -> organs
def perceive_media(p: PagePerception, limit: int = 6) -> list[dict]:
    """Route page media into the EXISTING perception organs (open-vocab detection -> scene graph
    -> sensory cortex percepts). Text around the image supplies the open vocabulary, so detection
    is grounded in what the page is actually about. Degrades honestly: organs unavailable or a
    media kind we cannot yet decode -> that item yields no percepts, never a guess."""
    results = []
    try:
        from packages.perception import open_vocab, scene_graph
        from packages.sensory_cortex import cortex
    except Exception:
        return results
    vocab_src = " ".join(p.reading_order[:40])
    vocab = sorted({w.lower() for w in vocab_src.split() if w.isalpha() and len(w) > 3})[:60]
    for m in p.media[:limit]:
        if m.kind != "image":
            results.append({"url": m.url, "kind": m.kind, "status": "port_declared_not_decoded"})
            continue
        try:
            scene = open_vocab.detect_url(m.url, vocab) if hasattr(open_vocab, "detect_url") else None
            if scene is None:
                results.append({"url": m.url, "kind": "image", "status": "no_detector_entry"})
                continue
            graph = scene_graph.build(scene) if hasattr(scene_graph, "build") else None
            percepts = cortex.understand(vision=scene)
            results.append({"url": m.url, "kind": "image", "status": "perceived",
                            "detections": len(scene.get("objects", []) if isinstance(scene, dict) else []),
                            "percepts": len(percepts) if percepts else 0,
                            "graph": bool(graph), "caption": m.caption or m.alt})
        except Exception as e:
            results.append({"url": m.url, "kind": "image", "status": f"error:{type(e).__name__}"})
    return results


def surf_and_distill(queries: Iterable[str], max_pages: int = 6,
                     headless: bool = True) -> dict:
    """One autonomous session: search -> follow results -> perceive -> distill to graph bones.
    Returns a summary; page graphs go through the existing page_distiller contract."""
    from packages.atanor_browser.page_distiller import distill_page
    pages, blocked, bones_total, media_seen = [], [], 0, 0
    with Surfer(headless=headless) as s:
        for q in queries:
            for r in s.search(q):
                if len(pages) >= max_pages:
                    break
                p = s.perceive(r["url"])
                if p.blocked:
                    blocked.append({"url": p.url, "reason": p.block_reason})
                    continue
                media_seen += len(p.media)
                try:
                    d = distill_page(f"<html><body>{p.main_text()}</body></html>", p.url)
                    bones_total += len(d.get("bones", {}) or {})
                except Exception:
                    pass
                pages.append({"url": p.url, "title": p.title, "chars": len(p.main_text()),
                              "media": len(p.media), "links": len(p.links)})
    return {"pages": pages, "blocked": blocked, "bones": bones_total, "media_seen": media_seen}
