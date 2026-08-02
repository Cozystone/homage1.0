# -*- coding: utf-8 -*-
"""Browser-automation roaming lane -- the AI surfs with a REAL browser, not a search API.

Owner directive (2026-07-20): search-engine API lanes are brittle (broken engines, rate limits);
drive an actual browser instead, and route incoming multimodal content into the existing organs.
This lane uses Playwright headless Chromium (off-the-shelf, approved) to:
  - run searches through a search engine's real HTML UI (rendered, JS included)
  - fetch and render target pages (full text after JS)
  - collect page IMAGES and pass them to the OWLv2 open-vocabulary eye
    (packages/perception/open_vocab.py -- the same organ the local camera uses), producing
    modality="vision" observations whose detected labels anchor the page's SENSE (a page whose
    images contain a rocket grounds 'restored' in the aerospace sense, not architecture).
Video/audio remain declared ports: the structure types every observation with its modality, so an
ear organ (ASR) and a video organ can plug in without reshaping the store.
"""
from __future__ import annotations

import io
import re
import time
import urllib.parse
import urllib.request

from packages.temporal_reasoning.web_explorer import (_mine_texts, _domain, _stem)

_DDG_HTML = "https://html.duckduckgo.com/html/?q="


def _sync_playwright():
    from playwright.sync_api import sync_playwright
    return sync_playwright()


class BrowserRoamer:
    """A real headless browser session. Use as a context manager."""

    def __enter__(self):
        self._pw = _sync_playwright().start()
        self._browser = self._pw.chromium.launch(headless=True)
        self._page = self._browser.new_page(user_agent=(
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/126.0 Safari/537.36"))
        return self

    def __exit__(self, *exc):
        try:
            self._browser.close()
            self._pw.stop()
        except Exception:
            pass

    # ---------------------------------------------------------------- search via real HTML UI
    def search(self, query: str, n: int = 6) -> list[dict]:
        """DuckDuckGo HTML lane rendered in the real browser (no API, no JSON endpoint)."""
        self._page.goto(_DDG_HTML + urllib.parse.quote(query), timeout=25_000)
        self._page.wait_for_timeout(800)
        out = []
        for a in self._page.query_selector_all("a.result__a")[:n]:
            href = a.get_attribute("href") or ""
            m = re.search(r"uddg=([^&]+)", href)         # ddg wraps target urls
            url = urllib.parse.unquote(m.group(1)) if m else href
            out.append({"url": url, "title": (a.inner_text() or "")[:120]})
        # snippets travel next to the links
        for i, sn in enumerate(self._page.query_selector_all("a.result__snippet")[:n]):
            if i < len(out):
                out[i]["snippet"] = (sn.inner_text() or "")[:400]
        return out

    # ---------------------------------------------------------------- rendered page intake
    def fetch(self, url: str, max_images: int = 4) -> dict:
        """Rendered page -> {'text': full visible text, 'images': [absolute urls]}."""
        try:
            self._page.goto(url, timeout=25_000)
            self._page.wait_for_timeout(1_000)
            text = self._page.inner_text("body")[:200_000]
            imgs = []
            for im in self._page.query_selector_all("img"):
                src = im.get_attribute("src") or ""
                try:
                    w = int(im.get_attribute("width") or 0)
                except ValueError:
                    w = 0
                if src.startswith("http") and (w == 0 or w >= 120):
                    imgs.append(src)
                if len(imgs) >= max_images:
                    break
            return {"text": text, "images": imgs}
        except Exception:
            return {"text": "", "images": []}


# -------------------------------------------------------------------- vision organ adapter
def vision_labels(image_url: str, vocabulary: list[str], threshold: float = 0.25) -> list[str]:
    """Route a web image into the OWLv2 open-vocabulary eye (the local-camera organ, reused for
    the web intake). Returns detected label names; [] when the organ or image is unavailable."""
    try:
        from packages.perception import open_vocab
        if not open_vocab.available():
            return []
        from PIL import Image
        req = urllib.request.Request(image_url, headers={"User-Agent": "ATANOR-roamer/0.1"})
        with urllib.request.urlopen(req, timeout=12) as r:
            img = Image.open(io.BytesIO(r.read(3_000_000))).convert("RGB")
        dets = open_vocab.detect(img, vocabulary=vocabulary, threshold=threshold)
        return sorted({d.get("label", "") for d in dets if d.get("label")})
    except Exception:
        return []


# -------------------------------------------------------------------- one roaming cycle
def browser_roam_pair(tok_a: str, tok_b: str, field=None, max_pages: int = 4,
                      with_vision: bool = False) -> dict:
    """Predict -> browser-surf -> mine (text + optional vision sense-anchors) -> store.
    Same journal/consensus stores as the API lane (web_explorer)."""
    import json
    from packages.temporal_reasoning import web_explorer as wx
    prior = field.order_confidence(tok_a, tok_b) if field else None
    queries = [f"{tok_a} before {tok_b}", f"{tok_b} after {tok_a}",
               f"{tok_a} {tok_b} sequence timeline"]
    # HYBRID lane (2026-07-20): direct search UIs challenge headless browsers (DDG error page,
    # Mojeek ALTCHA) and we do NOT bypass bot checks. Discovery goes through the working SearXNG
    # lane; the real browser does what it is uniquely good at -- rendering target pages (JS text)
    # and collecting their images for the OWLv2 eye.
    all_obs, pages = [], 0
    with BrowserRoamer() as br:
        seen = set()
        for q in queries:
            for r in wx._search(q, n=4):
                url = r.get("url", "")
                snippet = str(r.get("content") or r.get("snippet") or "")
                if snippet:
                    all_obs.extend(_mine_texts([("serp", snippet)], _domain(url), url,
                                               tok_a, tok_b))
                if not url or url in seen or pages >= max_pages:
                    continue
                seen.add(url)
                pages += 1
                got = br.fetch(url)
                texts = [("text", s) for s in re.split(r"(?<=[.!?])\s+", got["text"])]
                if with_vision and got["images"]:         # multimodal sense anchor
                    labels = vision_labels(got["images"][0], [tok_a, tok_b, "rocket", "ship",
                                                              "package", "factory", "satellite"])
                    if labels:
                        texts.append(("vision", " ".join(labels) + f" {tok_a} {tok_b}"))
                all_obs.extend(_mine_texts(texts, _domain(url), url, tok_a, tok_b))
            time.sleep(1.5)

    counts = wx.load_web_counts()
    with open(wx._WEB_OBS, "a", encoding="utf-8") as f:
        for o in all_obs:
            f.write(json.dumps(o) + "\n")
            key = f"{o['a']}|{o['b']}"
            counts.setdefault(key, {})
            counts[key][o["domain"]] = counts[key].get(o["domain"], 0) + 1
    wx._WEB_COUNTS.write_text(json.dumps(counts), encoding="utf-8")
    verdict = wx.web_consensus(tok_a, tok_b, counts)
    return {"pair": [tok_a, tok_b], "prior": prior, "pages": pages,
            "observations": len(all_obs), "verdict": verdict}
