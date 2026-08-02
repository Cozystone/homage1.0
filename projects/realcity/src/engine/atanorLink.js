// atanorLink — the city's live link to ATANOR (the No-LLM engine at :8502).
//
// Self-driving side-effect module (see citySystems.js contract): it starts its own interval loops,
// guards every call, and NEVER throws — the city runs fine whether or not ATANOR is reachable.
// Two loops:
//   (1) city-edit puller (every 20s): pull the edits ATANOR queued (rename a building, set a norm,
//       set a rule), apply each through the norms module (__REALCITY_NORMS__.applyFromAtanor), and
//       ack the ones that applied so the backend queue drains exactly once.
//   (2) ambassador live loop (every 45s): let an ATANOR-brained citizen ACT in the world — read one
//       such citizen's perceived world-state, ask ATANOR /api/realcity/act what to DO, and play the
//       chosen action as an avatar animation. The moral 0th gate is enforced backend-side.
// Offline / missing-module states are silent no-ops. One boot log, nothing more.

const ATANOR_BASE = 'http://127.0.0.1:8502'
const EDIT_POLL_MS = 20000
const AMBASSADOR_MS = 45000
const FETCH_TIMEOUT_MS = 4000

let booted = false
let ambassadorCursor = 0

// Short-timeout fetch that resolves to parsed JSON or null — offline/timeout/HTTP-error are all
// swallowed to null so no loop ever throws and the city never blocks on ATANOR.
async function atanorFetch(path, init = {}) {
  if (typeof window === 'undefined' || typeof fetch === 'undefined') return null
  const controller = new AbortController()
  const timer = setTimeout(() => controller.abort(), FETCH_TIMEOUT_MS)
  try {
    const response = await fetch(`${ATANOR_BASE}${path}`, {
      ...init,
      signal: controller.signal,
      headers: { 'Content-Type': 'application/json', ...(init.headers || {}) },
    })
    if (!response.ok) return null
    return await response.json()
  } catch {
    return null
  } finally {
    clearTimeout(timer)
  }
}

// (1) Pull queued city edits and apply them through the norms module; ack each one that applied.
async function pullCityEdits() {
  try {
    const norms = typeof window !== 'undefined' ? window.__REALCITY_NORMS__ : null
    if (!norms || typeof norms.applyFromAtanor !== 'function') return   // norms module absent -> skip
    const data = await atanorFetch('/api/realcity/city-edits')
    const edits = data && Array.isArray(data.edits) ? data.edits : []
    for (const edit of edits) {
      let applied = false
      try {
        applied = norms.applyFromAtanor(edit) === true
      } catch {
        applied = false
      }
      if (applied && edit && edit.id) {
        await atanorFetch('/api/realcity/city-edits/ack', {
          method: 'POST',
          body: JSON.stringify({ id: edit.id }),
        })
      }
    }
  } catch {
    // never throw out of the loop
  }
}

// (2) Drive one ATANOR-brained citizen's live action, round-robin across all such citizens.
async function driveAmbassador() {
  try {
    const city = typeof window !== 'undefined' ? window.__REALCITY_CITY__ : null
    const agents = city && Array.isArray(city.agents) ? city.agents : []
    const ambassadors = agents.filter(a => a && a.brain === 'atanor')
    if (!ambassadors.length) return
    const agent = ambassadors[ambassadorCursor % ambassadors.length]
    ambassadorCursor += 1
    if (!agent) return

    const seen = agent.percept && Array.isArray(agent.percept.seen) ? agent.percept.seen : []
    const body = {
      place: agent.placeName || '',
      place_kind: 'street',
      activity: agent.activity || '',
      nearby: seen.map(s => s && s.kind).filter(Boolean).slice(0, 8),
      nearby_agents: seen.filter(s => s && s.kind === 'agent').map(s => s && s.name).filter(Boolean).slice(0, 4),
      holding: [],
      needs: agent.needs || {},
      intent: agent.activity || '',
      role: String(agent.job || '').toLowerCase(),
      money: 10,
      tier: 'guarded',
    }

    const result = await atanorFetch('/api/realcity/act', {
      method: 'POST',
      body: JSON.stringify(body),
    })
    if (result && result.chosen) {
      window.dispatchEvent(new CustomEvent('realcity:avatar-action', {
        detail: {
          agentId: agent.id,
          animation: result.chosen.animation || 'emote',
          duration: Math.min(result.chosen.duration || 2, 6),
        },
      }))
    }
  } catch {
    // never throw out of the loop
  }
}

function boot() {
  if (booted || typeof window === 'undefined') return
  booted = true
  try {
    console.log('[atanorLink] live — ATANOR :8502 city-edit + ambassador loops running')
  } catch {
    /* console unavailable — ignore */
  }
  setInterval(pullCityEdits, EDIT_POLL_MS)
  setInterval(driveAmbassador, AMBASSADOR_MS)
}

boot()

export {}
