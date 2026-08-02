// ATANOR Surfer — background service worker.
// Receives page text from the content script and forwards it to the LOCAL engine only
// (127.0.0.1:8502). The engine shields the text and holds anything learned as a candidate —
// this extension never writes the production store and never sends data anywhere but localhost.
const ENGINE = "http://127.0.0.1:8502/api/expedition/ingest-page";

async function isEnabled() {
  const { enabled } = await chrome.storage.local.get("enabled");
  return enabled === true; // OFF by default — the user opts in from the popup
}

// the tab ATANOR is DIRECTLY active on right now — the orb lives only here and "follows" as focus
// moves (a page read updates it to that tab; autobrowse updates it to its own tab).
// PERSISTED, not just in-memory: an MV3 service worker is killed after ~30s idle and restarts with
// this reset to null, which made the orb vanish everywhere (atanor_orb_check → active:false for all
// tabs) until the next page-read/navigation. Storage-backed so the orb survives worker restarts.
let activeTabId = null;
async function getActiveTabId() {
  if (activeTabId !== null) return activeTabId;
  try {
    const { active_tab, ab_tab } = await chrome.storage.local.get(["active_tab", "ab_tab"]);
    if (typeof active_tab === "number") { activeTabId = active_tab; return active_tab; }
    if (typeof ab_tab === "number") { activeTabId = ab_tab; return ab_tab; } // autobrowse tab fallback
  } catch (_e) {}
  return null;
}
async function setActiveTabId(id) {
  activeTabId = id;
  try { await chrome.storage.local.set({ active_tab: id }); } catch (_e) {}
}

// Follow the user's focus (owner 2026-07-12: "돌던 애가 orb가 안 떠"). The orb only shows on the tab
// whose id === active_tab, and active_tab used to change ONLY on a manual popup 새로고침 — so if that
// tab was closed or the user switched tabs, active_tab went stale and the orb vanished everywhere.
// Now, while the orb is enabled, whatever tab comes to the front (the user's, or ATANOR's own during
// autobrowse) becomes active, so the orb rides along to the page actually in view.
async function _followFocus(tabId) {
  try {
    if (typeof tabId === "number" && (await chrome.storage.local.get("orb")).orb === true) {
      await setActiveTabId(tabId);
    }
  } catch (_e) {}
}
chrome.tabs.onActivated.addListener(({ tabId }) => { _followFocus(tabId); });
chrome.windows.onFocusChanged.addListener(async (winId) => {
  if (winId === chrome.windows.WINDOW_ID_NONE) return;   // all windows blurred — keep the last tab
  try {
    const [tab] = await chrome.tabs.query({ active: true, windowId: winId });
    if (tab) _followFocus(tab.id);
  } catch (_e) {}
});

const ACTIVITY = "http://127.0.0.1:8502/api/expedition/activity";
const CHAT = "http://127.0.0.1:8502/api/chat/atanor";

chrome.runtime.onMessage.addListener((msg, sender, sendResponse) => {
  // the orb asks "is THIS tab the one ATANOR is active on?" — resolves against the PERSISTED
  // active/autobrowse tab so it survives MV3 worker restarts.
  if (msg && msg.type === "atanor_orb_check") {
    (async () => {
      const known = await getActiveTabId();
      sendResponse({ active: !!(sender.tab && sender.tab.id === known) });
    })();
    return true; // async response
  }
  // the popup's 새로고침 makes THIS tab ATANOR's active tab so the orb appears on the page the
  // user is looking at (then the popup reloads it to guarantee a fresh orb.js injection).
  if (msg && msg.type === "atanor_focus_here" && typeof msg.tabId === "number") {
    setActiveTabId(msg.tabId).then(() => sendResponse({ ok: true }));
    return true; // async response
  }
  // READING-FOLLOW gate (owner 2026-07-11: "문서 읽을 때도 읽는 부분 따라가게"): the content
  // script may run its paragraph sweep only on ATANOR's OWN tab with 과정 보기 on — the user's
  // personal tabs must never animate.
  if (msg && msg.type === "atanor_read_check") {
    (async () => {
      const known = await getAtanorTabId();
      const { showProcess } = await chrome.storage.local.get("showProcess");
      sendResponse({ show: showProcess === true && !!(sender.tab && sender.tab.id === known) });
    })();
    return true; // async response
  }
  // the orb fetches ATANOR's live activity THROUGH the worker — a content-script fetch is bound to
  // the page's origin (CORS-blocked by the hardened engine), but the worker has host_permissions.
  if (msg && msg.type === "atanor_activity") {
    fetch(ACTIVITY)
      .then((r) => r.json())
      .then((data) => sendResponse({ ok: true, data }))
      .catch(() => sendResponse({ ok: false }));
    return true; // async response
  }
  // the orb's chat bar sends the owner's message to ATANOR and relays the real answer back.
  // Routed through the worker for the same CORS reason as activity (page-origin fetch is blocked).
  if (msg && msg.type === "atanor_chat" && msg.question) {
    fetch(CHAT, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      // conversation_context: the orb's persisted turns + the current page — this is what lets
      // the engine's anaphora/working-memory machinery run in the browser too (it was starving:
      // each message used to arrive alone, so every navigation read as total amnesia).
      body: JSON.stringify({ question: msg.question, language: msg.language || "ko",
                             conversation_context: Array.isArray(msg.conversation_context)
                               ? msg.conversation_context.slice(-8) : [] }),
    })
      .then((r) => r.json())
      .then(async (d) => {
        const ans = d && d.result && d.result.answer ? d.result.answer : null;
        // BROWSER COMMAND (owner 2026-07-10: 'moltbook 열어봐' must act, not console): the
        // engine answers with a browser_action; the Ato tab executes it — navigation only,
        // to the engine-approved URL. The spoken ack still returns to the chat bar.
        const act = d && d.result && d.result.browser_action;
        if (act && act.kind === "navigate" && typeof act.url === "string"
            && act.url.startsWith("https://")) {
          try { await navigateAtanorTab(act.url); } catch (_e) { /* tab gone → next tick */ }
        }
        sendResponse({ ok: !!ans, answer: ans });
      })
      .catch(() => sendResponse({ ok: false }));
    return true; // async response
  }
  // SERP step (search-first autobrowse): the content script on ATANOR's tab sends the live search
  // results; the ENGINE chooses the platform; we reply with the choice (+ whether to animate the
  // process) and the content script either animates then asks to go, or we navigate right away.
  if (msg && msg.type === "atanor_serp" && Array.isArray(msg.results)) {
    (async () => {
      const tabId = sender.tab && sender.tab.id;
      const known = await getAtanorTabId();
      const { ab_pending, showProcess } = await chrome.storage.local.get(["ab_pending", "showProcess"]);
      if (tabId !== known || !ab_pending || Date.now() - (ab_pending.at || 0) > 180000) {
        sendResponse({ ok: false, reason: "not_autobrowse_context" });
        return;
      }
      try {
        const rep = await (await fetch(CHOOSER, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ topic: ab_pending.topic, results: msg.results.slice(0, 10) }),
        })).json();
        if (!rep || !rep.chosen || !rep.url) {
          await chrome.storage.local.set({ ab_pending: null });
          sendResponse({ ok: false, reason: "no_choice" });
          return;
        }
        await chrome.storage.local.set({ ab_pending: null }); // one choice per outing
        if (showProcess === true) {
          // process-view mode: let the page animate (cursor → highlight), then it sends atanor_go
          sendResponse({ ok: true, url: rep.url, title: rep.title || "", why: rep.why || "", show: true });
        } else {
          sendResponse({ ok: true, url: rep.url, show: false });
          await navigateAtanorTab(rep.url);
        }
      } catch (_e) {
        sendResponse({ ok: false, reason: "engine_offline" });
      }
    })();
    return true; // async response
  }
  // the process animation finished — go to the chosen page now
  if (msg && msg.type === "atanor_go" && msg.url) {
    (async () => {
      const known = await getAtanorTabId();
      if (sender.tab && sender.tab.id === known) await navigateAtanorTab(msg.url);
      sendResponse({ ok: true });
    })();
    return true;
  }
  if (msg && msg.type === "atanor_page") {
    isEnabled().then((on) => {
      if (!on) return;
      if (sender.tab && sender.tab.id) setActiveTabId(sender.tab.id); // ATANOR's focus is here now
      fetch(ENGINE, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ url: msg.url, text: msg.text }),
      })
        .then((r) => r.json())
        .then((rep) => {
          const n = rep.injection_blocked ? 0 : rep.candidates || 0;
          chrome.storage.local.set({
            last: { url: rep.url, candidates: n, blocked: !!rep.injection_blocked, at: Date.now() },
          });
        })
        .catch(() => {}); // engine offline → silently skip; never disrupt browsing
    });
  }
  return false;
});

// AUTONOMOUS BROWSE v2 — SEARCH-FIRST (owner 2026-07-10: "기본을 구글에서 찾게, 플랫폼을 골라서
// 가게"). The engine plans a SEARCH for its frontier topic; we navigate to the results page; the
// content script sends the real results back; the ENGINE chooses which platform to read
// (choose-result); we navigate there. Reads only — the only "clicks" are tab navigations to
// engine-approved URLs; no form is ever submitted, no login touched.
const DIRECTOR = "http://127.0.0.1:8502/api/expedition/next-destination";
const CHOOSER = "http://127.0.0.1:8502/api/expedition/choose-result";
let atanorTabId = null; // in-memory cache; source of truth persists in storage (MV3 worker dies)

async function getAtanorTabId() {
  if (atanorTabId !== null) return atanorTabId;
  const { ab_tab } = await chrome.storage.local.get("ab_tab");
  atanorTabId = typeof ab_tab === "number" ? ab_tab : null;
  return atanorTabId;
}
async function setAtanorTabId(id) {
  atanorTabId = id;
  await chrome.storage.local.set({ ab_tab: id });
}

async function autobrowseEnabled() {
  const { autobrowse } = await chrome.storage.local.get("autobrowse");
  return autobrowse === true;
}

async function navigateAtanorTab(url) {
  const known = await getAtanorTabId();
  if (known !== null) {
    try {
      const t = await chrome.tabs.update(known, { url, active: true });
      try { await chrome.windows.update(t.windowId, { focused: true }); } catch (_e) {}
      await setActiveTabId(known);
      return known;
    } catch (_e) {
      await setAtanorTabId(null); // tab was closed; make a fresh one
    }
  }
  const tab = await chrome.tabs.create({ url, active: true }); // open focused → view follows
  try { await chrome.windows.update(tab.windowId, { focused: true }); } catch (_e) {}
  await setAtanorTabId(tab.id);
  await setActiveTabId(tab.id);
  return tab.id;
}

async function autobrowseTick() {
  if (!(await autobrowseEnabled())) return;
  try {
    const rep = await (await fetch(DIRECTOR)).json();
    if (!rep || !rep.navigate || !rep.url) return;
    // remember the outing so the SERP step knows what we're searching for
    await chrome.storage.local.set({
      ab_pending: rep.mode === "search"
        ? { topic: rep.topic || "", query: rep.query || "", at: Date.now() }
        : null,
    });
    await navigateAtanorTab(rep.url);
  } catch (_e) {
    /* engine offline → skip this tick */
  }
}

// poll on a bounded cadence; the engine enforces its own polite rate floor between navigations
chrome.alarms.create("atanor_autobrowse", { periodInMinutes: 0.5 });
chrome.alarms.onAlarm.addListener((a) => {
  if (a.name === "atanor_autobrowse") autobrowseTick();
});
