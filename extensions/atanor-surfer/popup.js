// ATANOR Surfer — popup: opt-in toggle + last-page readout.
const stateEl = document.getElementById("state");
const btn = document.getElementById("toggle");
const lastEl = document.getElementById("last");

function render(enabled) {
  stateEl.textContent = enabled ? "켜짐" : "꺼짐";
  btn.textContent = enabled ? "끄기" : "켜기";
  btn.className = enabled ? "" : "off";
}

async function refresh() {
  const { enabled, last } = await chrome.storage.local.get(["enabled", "last"]);
  render(enabled === true);
  if (last) {
    const host = (() => { try { return new URL(last.url).hostname; } catch { return last.url; } })();
    lastEl.textContent = last.blocked
      ? `⛔ ${host} — 주입 시도로 판정, 학습 안 함(면역 기록)`
      : `✅ ${host} — 후보 문장 ${last.candidates}개 격리(합의 대기)`;
  }
}

btn.addEventListener("click", async () => {
  const { enabled } = await chrome.storage.local.get("enabled");
  const next = !(enabled === true);
  await chrome.storage.local.set({ enabled: next });
  render(next);
});

// autonomous surfing toggle
const abEl = document.getElementById("abstate");
const abBtn = document.getElementById("abtoggle");
function renderAb(on) {
  abEl.textContent = on ? "켜짐" : "꺼짐";
  abBtn.textContent = on ? "끄기" : "켜기";
  abBtn.className = on ? "" : "off";
}
abBtn.addEventListener("click", async () => {
  const { autobrowse } = await chrome.storage.local.get("autobrowse");
  const next = !(autobrowse === true);
  await chrome.storage.local.set({ autobrowse: next });
  renderAb(next);
});

async function refreshAb() {
  const { autobrowse } = await chrome.storage.local.get("autobrowse");
  renderAb(autobrowse === true);
}

// Ato orb overlay toggle
const orbEl = document.getElementById("orbstate");
const orbBtn = document.getElementById("orbtoggle");
function renderOrb(on) {
  orbEl.textContent = on ? "켜짐" : "꺼짐";
  orbBtn.textContent = on ? "끄기" : "켜기";
  orbBtn.className = on ? "" : "off";
}
orbBtn.addEventListener("click", async () => {
  const { orb } = await chrome.storage.local.get("orb");
  const next = !(orb === true);
  await chrome.storage.local.set({ orb: next });
  renderOrb(next);
});
async function refreshOrb() {
  const { orb } = await chrome.storage.local.get("orb");
  renderOrb(orb === true);
}

// 과정 보기 모드 — 검색어 배너, 결과 훑는 커서, 선택 하이라이트까지 사고 과정을 화면에 그대로 보여줌
const procEl = document.getElementById("procstate");
const procBtn = document.getElementById("proctoggle");
function renderProc(on) {
  procEl.textContent = on ? "켜짐" : "꺼짐";
  procBtn.textContent = on ? "끄기" : "켜기";
  procBtn.className = on ? "" : "off";
}
procBtn.addEventListener("click", async () => {
  const { showProcess } = await chrome.storage.local.get("showProcess");
  const next = !(showProcess === true);
  await chrome.storage.local.set({ showProcess: next });
  renderProc(next);
});
async function refreshProc() {
  const { showProcess } = await chrome.storage.local.get("showProcess");
  renderProc(showProcess === true);
}

// 새로고침 — the fix for "orb doesn't appear": make THIS tab ATANOR's active tab (the orb only
// shows on the active tab, and an MV3 worker restart can drop that), then reload so orb.js
// re-injects fresh. After this the orb appears on the current page within a tick.
const refreshBtn = document.getElementById("refresh");
refreshBtn.addEventListener("click", async () => {
  refreshBtn.textContent = "↻ 새로고침 중…";
  try {
    const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
    if (tab && tab.id != null) {
      try { await chrome.runtime.sendMessage({ type: "atanor_focus_here", tabId: tab.id }); } catch (_e) {}
      try { await chrome.tabs.reload(tab.id); } catch (_e) {}
    }
  } finally {
    refresh(); refreshAb(); refreshOrb(); refreshProc();
    setTimeout(() => { window.close(); }, 250);  // close popup so the user sees the page + orb
  }
});

refresh();
refreshAb();
refreshOrb();
refreshProc();
