// ATANOR Surfer — the Ato orb (particle field) + thought bubble + chat bar.
// A living PARTICLE orb rendered in ATANOR's real aesthetic (the cyan→blue→violet→pink Siri-ribbon
// of HologramVoiceOrb, approximated in 2D canvas), that says — in a small bubble — what ATANOR is
// DOING right now (the engine's honest first-person intention for the real pending action, never
// authored prose). CLICK the orb to open a wide chat bar and talk to ATANOR in real time; click
// again to close. The orb appears ONLY on the tab ATANOR is active on, is draggable, never blocks,
// and stays legible on both light and dark pages. Activity + chat are fetched THROUGH the background
// worker (a content-script fetch is CORS-blocked by the hardened engine). Off unless enabled.
(function () {
  if (window.__atanorOrb) return;
  window.__atanorOrb = true;

  // When the extension is reloaded, THIS script (already injected into an open tab) is orphaned:
  // touching chrome.runtime then throws "Extension context invalidated". Guard EVERY chrome access,
  // shut this instance down cleanly on invalidation (the freshly-injected script in new/reloaded
  // tabs takes over), and swallow any stray rejection so nothing ever reaches the page console.
  let dead = false;
  function ctxAlive() {
    try { return !!(chrome && chrome.runtime && chrome.runtime.id); } catch (_e) { return false; }
  }
  function stop() {
    if (dead) return;
    dead = true;
    try { if (raf) cancelAnimationFrame(raf); } catch (_e) {}
    try { if (timer) clearInterval(timer); } catch (_e) {}
    try { host.remove(); } catch (_e) {}
  }
  window.addEventListener("unhandledrejection", (e) => {
    const m = e && e.reason && (e.reason.message || e.reason);
    if (typeof m === "string" && m.indexOf("Extension context invalidated") !== -1) {
      e.preventDefault(); stop();
    }
  });

  // ATANOR's real orb palette (from HologramVoiceOrb PALETTE): cyan, sky-blue, violet, pink.
  const PALETTE = [[32, 244, 255], [58, 168, 255], [189, 109, 255], [255, 79, 157]];
  // a faint per-activity tint that shifts the whole orb's mood without leaving the ATANOR identity
  const KIND_TINT = { web: [58, 168, 255], talk: [32, 244, 255], surf: [58, 168, 255],
                      drive: [189, 109, 255], post: [120, 230, 170], idle: [140, 170, 210] };

  const host = document.createElement("div");
  host.id = "atanor-orb-host";
  host.style.cssText =
    "position:fixed;right:18px;bottom:18px;z-index:2147483647;display:none;user-select:none;";
  const rootEl = host.attachShadow({ mode: "open" });
  rootEl.innerHTML = `
    <style>
      .wrap{display:flex;align-items:flex-end;gap:8px;font:12px/1.45 system-ui,-apple-system,sans-serif;}
      .bubble{background:rgba(18,20,28,.86);backdrop-filter:blur(12px);color:#f4f6ff;
        padding:8px 12px;border-radius:14px 14px 4px 14px;max-width:230px;
        box-shadow:0 6px 22px rgba(0,0,0,.35);border:1px solid rgba(120,180,255,.18);
        opacity:0;transform:translateY(4px);transition:opacity .35s,transform .35s;pointer-events:none;}
      .bubble.show{opacity:1;transform:none;}
      canvas{width:60px;height:60px;cursor:pointer;display:block;}

      .chat{position:fixed;left:50%;transform:translateX(-50%) translateY(16px);bottom:20px;
        width:min(680px,calc(100vw - 40px));opacity:0;pointer-events:none;
        transition:opacity .28s ease,transform .28s ease;font:13px/1.5 system-ui,-apple-system,sans-serif;}
      .chat.open{opacity:1;transform:translateX(-50%) translateY(0);pointer-events:auto;}
      .msgs{max-height:44vh;overflow-y:auto;display:flex;flex-direction:column;gap:8px;
        margin-bottom:10px;padding:2px;}
      .msgs:empty{display:none;}
      .msg{max-width:80%;padding:9px 13px;border-radius:15px;white-space:pre-wrap;word-break:break-word;
        box-shadow:0 4px 16px rgba(0,0,0,.28);}
      .msg.me{align-self:flex-end;background:linear-gradient(135deg,#3aa8ff,#6557ff);color:#fff;
        border-radius:15px 15px 4px 15px;}
      .msg.ato{align-self:flex-start;background:rgba(20,22,30,.92);color:#eef2ff;
        border:1px solid rgba(120,180,255,.22);border-radius:15px 15px 15px 4px;backdrop-filter:blur(10px);}
      .msg.ato.pending{color:#9fb4d6;font-style:italic;}
      .inputrow{display:flex;gap:8px;align-items:center;background:rgba(16,18,26,.92);
        backdrop-filter:blur(16px);border:1px solid rgba(120,180,255,.28);border-radius:16px;
        padding:7px 8px 7px 16px;box-shadow:0 10px 40px rgba(0,0,0,.45);}
      .inputrow input{flex:1;background:transparent;border:none;outline:none;color:#f4f6ff;
        font:14px/1.4 system-ui,-apple-system,sans-serif;}
      .inputrow input::placeholder{color:#7f92b5;}
      .send{width:34px;height:34px;flex:0 0 34px;border:none;border-radius:11px;cursor:pointer;
        background:linear-gradient(135deg,#20f4ff,#3aa8ff 45%,#bd6dff);color:#08121f;font-size:17px;
        font-weight:700;display:flex;align-items:center;justify-content:center;transition:filter .15s;}
      .send:hover{filter:brightness(1.12);}
      .send:disabled{opacity:.5;cursor:default;}
    </style>
    <div class="wrap"><div class="bubble" id="bubble"></div><canvas id="c" width="120" height="120"></canvas></div>
    <div class="chat" id="chat">
      <div class="msgs" id="msgs"></div>
      <div class="inputrow">
        <input id="chatin" type="text" placeholder="ATANOR에게 말 걸기…" autocomplete="off" spellcheck="false" />
        <button class="send" id="send" title="보내기">↑</button>
      </div>
    </div>`;
  document.documentElement.appendChild(host);

  const bubbleEl = rootEl.getElementById("bubble");
  const canvas = rootEl.getElementById("c");
  const ctx = canvas.getContext("2d");
  const chatEl = rootEl.getElementById("chat");
  const msgsEl = rootEl.getElementById("msgs");
  const inputEl = rootEl.getElementById("chatin");
  const sendBtn = rootEl.getElementById("send");
  const CX = 60, CY = 60;

  // ── particle field: four tilted "ribbon" bands (one per palette color) that flow and cross,
  // echoing the real orb's Siri-ribbon. Each band is a squashed, tilted ellipse of particles whose
  // radius ripples along its angle so the bands read as flowing ribbons, not rigid rings.
  const BANDS = 4, PER = 15;
  const parts = [];
  for (let b = 0; b < BANDS; b++) {
    for (let i = 0; i < PER; i++) {
      parts.push({
        band: b, a0: (i / PER) * Math.PI * 2,
        tilt: b * 0.62 + Math.sin(b) * 0.15,
        ecc: 0.42 + b * 0.07,
        base: 20 + b * 2.4,
        spd: (0.006 + b * 0.0016) * (b % 2 ? -1 : 1),
        sz: 1.0 + Math.random() * 1.4, ph: Math.random() * Math.PI * 2,
        col: PALETTE[b],
      });
    }
  }
  let tint = KIND_TINT.idle.slice();
  let target = KIND_TINT.idle.slice();
  let t = 0, raf = null, timer = null;

  function mix(c, tn, w) { return [c[0] + (tn[0] - c[0]) * w, c[1] + (tn[1] - c[1]) * w, c[2] + (tn[2] - c[2]) * w]; }

  function draw() {
    if (dead) return;
    t += 0.016;
    for (let k = 0; k < 3; k++) tint[k] += (target[k] - tint[k]) * 0.04;
    const breathe = 1 + 0.075 * Math.sin(t * 1.25);
    ctx.clearRect(0, 0, 120, 120);

    // (1) adaptive backing lens — a soft dark disc so the additive glow keeps contrast on WHITE
    // pages; invisible on dark pages. This is what makes the orb legible on any background.
    ctx.globalCompositeOperation = "source-over";
    const lens = ctx.createRadialGradient(CX, CY, 0, CX, CY, 40);
    lens.addColorStop(0, "rgba(8,11,20,0.46)");
    lens.addColorStop(0.7, "rgba(8,11,20,0.30)");
    lens.addColorStop(1, "rgba(8,11,20,0)");
    ctx.fillStyle = lens;
    ctx.beginPath(); ctx.arc(CX, CY, 40, 0, Math.PI * 2); ctx.fill();

    // (2) glowing ribbons + core, additively blended (the ATANOR luminous look)
    ctx.globalCompositeOperation = "lighter";
    // core bloom (cyan-white heart)
    const core = ctx.createRadialGradient(CX, CY, 0, CX, CY, 16 * breathe);
    core.addColorStop(0, "rgba(210,250,255,0.55)");
    core.addColorStop(0.5, "rgba(90,200,255,0.30)");
    core.addColorStop(1, "rgba(60,120,255,0)");
    ctx.fillStyle = core;
    ctx.beginPath(); ctx.arc(CX, CY, 24, 0, Math.PI * 2); ctx.fill();

    for (const p of parts) {
      const ang = p.a0 + t * p.spd * 12 + p.ph;
      const ripple = 1 + 0.16 * Math.sin(ang * 1.7 + p.band);
      const R = p.base * ripple * breathe;
      const ex = Math.cos(ang) * R;
      const ey = Math.sin(ang) * R * p.ecc;
      const ct = Math.cos(p.tilt + t * 0.05), st = Math.sin(p.tilt + t * 0.05);
      const x = CX + ex * ct - ey * st;
      const y = CY + ex * st + ey * ct;
      const tw = 0.55 + 0.45 * Math.sin(t * 2.1 + p.ph);
      const c = mix(p.col, tint, 0.28);
      const cr = Math.round(c[0]), cg = Math.round(c[1]), cb = Math.round(c[2]);
      const g = ctx.createRadialGradient(x, y, 0, x, y, p.sz * 3.1);
      g.addColorStop(0, `rgba(${Math.min(255, cr + 40)},${Math.min(255, cg + 30)},${Math.min(255, cb + 20)},${0.9 * tw})`);
      g.addColorStop(1, `rgba(${cr},${cg},${cb},0)`);
      ctx.fillStyle = g;
      ctx.beginPath(); ctx.arc(x, y, p.sz * 3.1, 0, Math.PI * 2); ctx.fill();
    }
    ctx.globalCompositeOperation = "source-over";
    raf = requestAnimationFrame(draw);
  }
  raf = requestAnimationFrame(draw);

  // ── drag vs click: a small movement is a CLICK (toggle chat); a real drag MOVES the orb.
  let down = null, userMoved = false, chatOpen = false;
  canvas.addEventListener("mousedown", (e) => {
    down = { x: e.clientX, y: e.clientY, moved: false };
    e.preventDefault();
  });
  window.addEventListener("mousemove", (e) => {
    if (!down) return;
    const dx = e.clientX - down.x, dy = e.clientY - down.y;
    if (Math.hypot(dx, dy) > 6) {
      down.moved = true; userMoved = true;
      host.style.left = e.clientX - 30 + "px";
      host.style.top = e.clientY - 30 + "px";
      host.style.right = "auto"; host.style.bottom = "auto";
    }
  });
  window.addEventListener("mouseup", () => {
    if (down && !down.moved) toggleChat();  // clean click → open/close the chat bar
    down = null;
  });

  function toggleChat() {
    chatOpen = !chatOpen;
    chatEl.classList.toggle("open", chatOpen);
    if (chatOpen) {
      bubbleEl.classList.remove("show");            // hide the thought bubble while chatting
      if (!userMoved) { host.style.bottom = "120px"; host.style.right = "18px"; } // lift above the bar
      setTimeout(() => { try { inputEl.focus(); } catch (_e) {} }, 60);
    } else if (!userMoved) {
      host.style.bottom = "18px"; host.style.right = "18px";
    }
  }

  function ask(type, extra) {
    return new Promise((res) => {
      if (!ctxAlive()) { res(null); return; }
      try {
        chrome.runtime.sendMessage(Object.assign({ type }, extra || {}), (r) => {
          if (chrome.runtime.lastError) { res(null); return; }  // swallow "context invalidated"
          res(r);
        });
      } catch (_e) { res(null); }
    });
  }

  // ── chat bar
  function addMsg(who, text) {
    const el = document.createElement("div");
    el.className = "msg " + who;
    el.textContent = text;
    msgsEl.appendChild(el);
    msgsEl.scrollTop = msgsEl.scrollHeight;
    return el;
  }
  // CONTINUITY across pages (owner 2026-07-10: "창을 넘어가면 대화나 사고가 바로 리셋"): the log
  // lives in chrome.storage, not the page — every navigation used to wipe it, and worse, each
  // message went to the engine ALONE, starving the anaphora/working-memory machinery the engine
  // already has. Now the last turns ride along as conversation_context, plus a synthetic turn
  // naming the CURRENT page so "이 사이트 알려줘" grounds on what we're both looking at.
  const CHAT_LOG_KEY = "atanor_chat_log";
  async function loadChatLog() {
    try {
      const { [CHAT_LOG_KEY]: log } = await chrome.storage.local.get(CHAT_LOG_KEY);
      (Array.isArray(log) ? log : []).forEach((m) => addMsg(m.who, m.text));
    } catch (_e) { /* storage unavailable → start empty */ }
  }
  async function saveTurn(who, text) {
    try {
      const { [CHAT_LOG_KEY]: log } = await chrome.storage.local.get(CHAT_LOG_KEY);
      const next = (Array.isArray(log) ? log : []).concat([{ who, text }]).slice(-16);
      await chrome.storage.local.set({ [CHAT_LOG_KEY]: next });
    } catch (_e) {}
  }
  async function chatContext() {
    let turns = [];
    try {
      const { [CHAT_LOG_KEY]: log } = await chrome.storage.local.get(CHAT_LOG_KEY);
      turns = (Array.isArray(log) ? log : []).slice(-6)
        .map((m) => ({ role: m.who === "me" ? "user" : "assistant", text: m.text }));
    } catch (_e) {}
    // the shared gaze: the page we are both looking at, as a context turn the engine's
    // working-memory field can settle "이 사이트/이 페이지" onto.
    const title = (document.title || "").slice(0, 80);
    if (title) {
      turns.push({ role: "assistant",
                   text: `지금 함께 보고 있는 페이지는 '${title}'(${location.hostname})입니다.` });
    }
    return turns;
  }
  loadChatLog();
  let sending = false;
  async function sendChat() {
    if (sending || dead) return;
    const q = (inputEl.value || "").trim();
    if (!q) return;
    inputEl.value = "";
    sending = true; sendBtn.disabled = true;
    addMsg("me", q);
    saveTurn("me", q);
    const pend = addMsg("ato", "…"); pend.classList.add("pending");
    const ctx = await chatContext();
    const r = await ask("atanor_chat", { question: q, language: "ko", conversation_context: ctx });
    pend.classList.remove("pending");
    const answer = (r && r.ok && r.answer) ? r.answer : "지금은 대답을 만들지 못했어요. 잠시 후 다시 말 걸어 주세요.";
    pend.textContent = answer;
    if (r && r.ok && r.answer) saveTurn("ato", r.answer);
    msgsEl.scrollTop = msgsEl.scrollHeight;
    sending = false; sendBtn.disabled = false;
    try { inputEl.focus(); } catch (_e) {}
  }
  sendBtn.addEventListener("click", sendChat);
  inputEl.addEventListener("keydown", (e) => {
    if (e.key === "Enter" && !e.isComposing) { e.preventDefault(); sendChat(); }
    e.stopPropagation();  // don't leak keystrokes to the page
  });

  async function tick() {
    if (dead) return;
    if (!ctxAlive()) { stop(); return; }   // extension reloaded → retire this orphan cleanly
    let orb = false;
    try { orb = (await chrome.storage.local.get("orb")).orb === true; }
    catch (_e) { stop(); return; }
    const who = await ask("atanor_orb_check");
    if (!orb || !(who && who.active)) { host.style.display = "none"; return; }
    host.style.display = "block";
    const r = await ask("atanor_activity");
    if (r && r.ok && r.data) {
      target = KIND_TINT[r.data.current_kind] || KIND_TINT.idle;
      if (!chatOpen) {                       // thought bubble only when not actively chatting
        // monologue = PRESENT-TENSE inner voice (breathing/추론 상태 포함) — the intention line
        // alone went stale between actions (owner: "말도 안 하고 화면도 안 움직이면 뭐 하는지 모르겠어")
        bubbleEl.textContent = r.data.monologue || r.data.intention || r.data.current || "…";
        bubbleEl.classList.add("show");
      }
    } else if (!chatOpen) {
      bubbleEl.textContent = "엔진과 연결 대기 중…";
      bubbleEl.classList.add("show");
    }
  }

  tick();
  timer = setInterval(tick, 3500);
})();
