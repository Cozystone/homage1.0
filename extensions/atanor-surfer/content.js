// ATANOR Surfer — content script (v0.2: SPA-aware, Google/YouTube-aware).
// Extracts the MAIN readable content of whatever the user is browsing and hands it to the
// background worker, which forwards it to the LOCAL engine's expedition ingest endpoint.
// Read-only: never modifies the page, submits forms, or clicks. The engine's shield decides
// what (if anything) is learned; nothing is ever written to the production store.
(function () {
  function clean(el, drop) {
    if (!el) return "";
    const c = el.cloneNode(true);
    c.querySelectorAll(drop).forEach((n) => n.remove());
    return (c.innerText || "").replace(/\s+/g, " ").trim();
  }

  // VISUAL LAYER (v0 of "reading the screen like eyes"): the page is not just its body text — it
  // shows images and video. We read their accessible meaning (alt text, captions, titles) so
  // ATANOR knows what is DEPICTED, not only what is written. This is the grounded first layer;
  // pixel-level OCR + object detection run client-side in a later capability (see roadmap doc).
  function visualContext() {
    const parts = [];
    const imgs = Array.from(document.images || [])
      .map((im) => (im.alt || im.title || "").trim())
      .filter((s) => s.length >= 3);
    // figure captions (often richer than alt)
    Array.from(document.querySelectorAll("figcaption")).forEach((f) => {
      const t = (f.innerText || "").trim();
      if (t.length >= 3) imgs.push(t);
    });
    const uniqImgs = [...new Set(imgs)].slice(0, 25);
    if (uniqImgs.length) parts.push("[이미지] " + uniqImgs.join(" · "));
    const vids = Array.from(document.querySelectorAll("video, ytd-player, .html5-video-player"))
      .map((v) => (v.getAttribute("title") || v.getAttribute("aria-label")
        || document.querySelector('meta[property="og:title"]')?.content || "").trim())
      .filter((s) => s.length >= 3);
    if (vids.length) parts.push("[영상] " + [...new Set(vids)].slice(0, 5).join(" · "));
    const counts = `[화면 구성] 이미지 ${document.images.length}개, 영상 ${document.querySelectorAll("video").length}개`;
    parts.push(counts);
    return parts.join("\n");
  }

  // site-aware extraction: Google search results and YouTube watch pages carry their signal in
  // specific containers (and load it via JS), not in <main>/<article>, so target them directly.
  function extract() {
    const host = location.hostname;
    if (host.includes("youtube.com") && location.pathname === "/watch") {
      const title = (document.querySelector('meta[name="title"]')?.content
        || document.querySelector("h1.ytd-watch-metadata, h1.title")?.innerText || "").trim();
      const desc = (document.querySelector('meta[name="description"]')?.content || "").trim();
      const chan = (document.querySelector("#channel-name a, ytd-channel-name a")?.innerText || "").trim();
      return [title, chan ? "채널: " + chan : "", desc].filter(Boolean).join(". ").slice(0, 20000);
    }
    if (host.includes("google.") && location.pathname.startsWith("/search")) {
      const q = new URLSearchParams(location.search).get("q") || "";
      const body = clean(document.querySelector("#rso, #search") || document.body,
        "script,style,cite,nav,header,footer,form");
      return (q ? "검색: " + q + ". " : "") + body.slice(0, 20000);
    }
    return clean(document.querySelector("main, article, [role=main]") || document.body,
      "script,style,nav,aside,footer,header,noscript,form").slice(0, 200000);
  }

  let lastSent = "";
  async function send() {
    const url = location.href;
    if (url === lastSent) return;          // dedupe: one send per URL
    const body = extract();
    if (body.length < 120) return;         // skip thin pages
    lastSent = url;
    // the visual layer (image alt/captions, video titles, media inventory) rides ALONG with the
    // body text — one payload the engine shields together. (In-image OCR is a separate offscreen-
    // document capability, not injected here.)
    const visual = visualContext();
    const text = [visual, body].filter(Boolean).join("\n\n");
    chrome.runtime.sendMessage({ type: "atanor_page", url, text });
    // READING-FOLLOW (owner 2026-07-11: "문서 읽거나 할 때도 읽는 부분 따라가게"): on ATANOR's
    // own tab with 과정 보기 on, replay the read visibly — the cursor walks the very paragraphs
    // the extracted text came from. Honesty note: the engine swallows the text in one gulp; this
    // sweep is a faithful REPLAY of coverage (which parts were read), not a fake gaze.
    try {
      chrome.runtime.sendMessage({ type: "atanor_read_check" }, (rep) => {
        if (rep && rep.show) readingSweep();
      });
    } catch (_e) { /* worker asleep — skip the animation, never the read */ }
  }

  async function readingSweep() {
    const host = location.hostname;
    if (host.includes("google.") && location.pathname.startsWith("/search")) return; // SERP has its own sweep
    const root = document.querySelector("main, article, [role=main]") || document.body;
    const nodes = Array.from(root.querySelectorAll("p, li, h2, h3"))
      .filter((el) => (el.innerText || "").trim().length >= 60 && el.offsetParent !== null);
    if (nodes.length < 2) return;
    // eyes visit up to 12 paragraphs spread across the whole article (bounded: ~8s per page)
    const step = Math.max(1, Math.floor(nodes.length / 12));
    const path = nodes.filter((_, i) => i % step === 0).slice(0, 12);
    const cursor = procCursor();
    await procBanner("ATANOR ▸ 읽기 스윕: 본문 문단 추적");
    for (const el of path) {
      if (!el.isConnected) continue;
      el.scrollIntoView({ block: "center", behavior: "smooth" });
      moveCursorTo(cursor, el);
      const prev = el.style.cssText;
      el.style.background = "rgba(32,244,255,.10)";
      el.style.boxShadow = "inset 3px 0 0 rgba(32,244,255,.7)";
      el.style.transition = "background .4s";
      await new Promise((r) => setTimeout(r, 620));
      el.style.cssText = prev;
    }
    cursor.remove();
    const b = document.getElementById("atanor-proc-banner");
    if (b) setTimeout(() => b.remove(), 2500);
  }

  // debounce so SPA content has time to render before we read it
  let timer = null;
  function schedule() { clearTimeout(timer); timer = setTimeout(send, 1200); }

  // fire on first load, on history navigation, and on SPA route changes (YouTube/Google use the
  // History API and don't do full page loads when you click around).
  if (document.readyState === "complete") schedule();
  else window.addEventListener("load", schedule, { once: true });
  window.addEventListener("popstate", schedule);
  for (const m of ["pushState", "replaceState"]) {
    const orig = history[m];
    history[m] = function () { const r = orig.apply(this, arguments); schedule(); return r; };
  }
  // poll fallback for SPAs that swap content without a clean history event
  setInterval(() => { if (location.href !== lastSent) schedule(); }, 2000);

  // ── SEARCH-FIRST autobrowse: on a Google results page, hand the LIVE results to the engine so
  // it can CHOOSE the platform to read (owner: 적절한 데를 골라서 가게). With 과정 보기 모드 on,
  // the whole thought is VISIBLE: a banner types the query, a cursor sweeps the results, the
  // chosen link lights up, then the tab moves. We never dispatch DOM clicks or submit forms —
  // the only action is a tab navigation to the engine-approved URL.
  function serpResults() {
    const out = [];
    const seen = new Set();
    document.querySelectorAll("#search a, #rso a").forEach((a) => {
      const h3 = a.querySelector("h3");
      if (!h3) return;
      const href = a.href || "";
      if (!href.startsWith("https://") || href.includes("google.")) return;
      if (seen.has(href)) return;
      seen.add(href);
      out.push({ title: (h3.innerText || "").trim(), url: href, _el: a });
    });
    return out.slice(0, 8);
  }

  function procBanner(text) {
    let b = document.getElementById("atanor-proc-banner");
    if (!b) {
      b = document.createElement("div");
      b.id = "atanor-proc-banner";
      b.style.cssText = "position:fixed;top:14px;left:50%;transform:translateX(-50%);z-index:2147483646;"
        + "background:rgba(10,14,22,.92);color:#e8f6ff;padding:10px 18px;border-radius:12px;"
        + "font:500 14px/1.4 system-ui;box-shadow:0 6px 24px rgba(0,0,0,.35);max-width:70vw;"
        + "border:1px solid rgba(32,244,255,.35);pointer-events:none;white-space:nowrap;overflow:hidden;text-overflow:ellipsis";
      document.documentElement.appendChild(b);
    }
    return new Promise((res) => {
      let i = 0;
      b.textContent = "";
      const t = setInterval(() => {
        b.textContent = text.slice(0, ++i);
        if (i >= text.length) { clearInterval(t); res(b); }
      }, 22);
    });
  }

  function procCursor() {
    let c = document.getElementById("atanor-proc-cursor");
    if (!c) {
      c = document.createElement("div");
      c.id = "atanor-proc-cursor";
      c.style.cssText = "position:fixed;width:18px;height:18px;border-radius:50%;z-index:2147483647;"
        + "background:radial-gradient(circle,#20f4ff 0%,#3aa8ff 55%,rgba(58,168,255,0) 72%);"
        + "box-shadow:0 0 14px 4px rgba(32,244,255,.55);pointer-events:none;left:50%;top:30%;"
        + "transition:left .5s cubic-bezier(.4,0,.2,1),top .5s cubic-bezier(.4,0,.2,1)";
      document.documentElement.appendChild(c);
    }
    return c;
  }

  function moveCursorTo(c, el) {
    const r = el.getBoundingClientRect();
    c.style.left = Math.max(8, r.left - 14) + "px";
    c.style.top = (r.top + r.height / 2 - 9) + "px";
  }

  async function animateChoice(results, chosenUrl, why) {
    const cursor = procCursor();
    // sweep: the eye runs down the results like reading
    for (const r of results.slice(0, 5)) {
      if (!r._el || !r._el.isConnected) continue;
      r._el.scrollIntoView({ block: "center", behavior: "smooth" });
      moveCursorTo(cursor, r._el);
      await new Promise((res) => setTimeout(res, 420));
    }
    const chosen = results.find((r) => r.url === chosenUrl);
    if (chosen && chosen._el && chosen._el.isConnected) {
      chosen._el.scrollIntoView({ block: "center", behavior: "smooth" });
      moveCursorTo(cursor, chosen._el);
      chosen._el.style.outline = "3px solid #20f4ff";
      chosen._el.style.borderRadius = "6px";
      chosen._el.style.boxShadow = "0 0 18px rgba(32,244,255,.5)";
    }
    // telemetry register: `why` now carries the engine's raw decision variables (no authored
    // first-person prose — the voice channel is generated-or-silent, owner 2026-07-11)
    await procBanner("ATANOR ▸ " + (why || "선택"));
    await new Promise((res) => setTimeout(res, 1400));
  }

  async function serpStep() {
    const host = location.hostname;
    if (!(host.includes("google.") && location.pathname.startsWith("/search"))) return;
    const results = serpResults();
    if (!results.length) return;
    const q = new URLSearchParams(location.search).get("q") || "";
    const { showProcess } = await chrome.storage.local.get("showProcess");
    if (showProcess === true) await procBanner("ATANOR ▸ SERP 판독: " + q);
    chrome.runtime.sendMessage(
      { type: "atanor_serp", results: results.map(({ title, url }) => ({ title, url })) },
      async (rep) => {
        if (!rep || !rep.ok || !rep.url) return;
        if (rep.show) {
          await animateChoice(results, rep.url, rep.why);
          chrome.runtime.sendMessage({ type: "atanor_go", url: rep.url });
        }
        // show=false → the worker already navigated; nothing to do here
      }
    );
  }
  // give the SERP a moment to render, then offer the results to the engine (once per URL)
  let serpDone = "";
  setInterval(() => {
    if (location.href !== serpDone && location.pathname.startsWith("/search")) {
      serpDone = location.href;
      setTimeout(serpStep, 1500);
    }
  }, 1200);
})();
