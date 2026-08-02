// dialogueEavesdrop — ATANOR ambassadors OVERHEAR the city's ollama-NPCs and ship what they hear to
// the backend learning loop, WITHOUT ever treating an NPC sentence as fact.
//
// Self-driving side-effect module (citySystems.js contract): it starts its own interval, waits for
// window.__REALCITY_CITY__, guards every call, and NEVER throws or mutates an agent — the city runs
// fine whether or not ATANOR is reachable. Offline / timeout are silent no-ops. One boot log, nothing
// more (mirrors atanorLink.js).
//
// Doctrine (external-minds-are-data): a line an ambassador overhears is DATA. This module only SHIPS
// raw exchanges to POST /api/realcity/overhear; the backend quarantines them, distils anonymized
// register by consensus, and files topic pointers as UNGROUNDED curiosity. Nothing here writes to the
// brain, and nothing is surfaced back into the city as a fact.

const ATANOR_BASE = 'http://127.0.0.1:8502'
const EAVESDROP_MS = 10000
const FETCH_TIMEOUT_MS = 4000
const HEAR_RADIUS = 25          // world units: an ambassador overhears talk within this range
const SEEN_CAP = 800            // bound the dedupe memory

let booted = false
const heard = new Set()         // hashes of exchanges already shipped, so each is sent exactly once

// Position of an agent whether __REALCITY_CITY__.agents holds live instances (.pos.x/.z) or
// snapshots (.x/.z). Returns null when neither is present (read-only, never mutates the agent).
function positionOf(agent) {
  const x = agent && (agent.pos ? agent.pos.x : agent.x)
  const z = agent && (agent.pos ? agent.pos.z : agent.z)
  return typeof x === 'number' && typeof z === 'number' ? { x, z } : null
}

// djb2 -> base36: a compact stable hash so the same overheard line is never shipped twice.
function hashLine(speaker, text) {
  const key = `${speaker}${text}`
  let hash = 5381
  for (let i = 0; i < key.length; i += 1) hash = (((hash << 5) + hash) ^ key.charCodeAt(i)) >>> 0
  return hash.toString(36)
}

// One eavesdrop tick: find ATANOR ambassadors, collect the DISTINCT new lines that OTHER agents are
// speaking within earshot of any ambassador, and batch-POST them to the backend learning endpoint.
async function overhearOnce() {
  try {
    if (typeof window === 'undefined' || typeof fetch === 'undefined') return
    const city = window.__REALCITY_CITY__
    const agents = city && Array.isArray(city.agents) ? city.agents : []
    if (!agents.length) return

    const ambassadors = agents
      .filter(agent => agent && agent.brain === 'atanor')
      .map(agent => ({ agent, pos: positionOf(agent) }))
      .filter(entry => entry.pos)
    if (!ambassadors.length) return       // no ATANOR citizen present -> nothing to overhear for

    const speakers = []
    const lines = []
    let place = ''
    for (const agent of agents) {
      if (!agent || agent.brain === 'atanor') continue     // ambassadors do not overhear each other
      const line = typeof agent.talkLine === 'string' ? agent.talkLine.trim() : ''
      const talking = line && (agent.talkTimer === undefined || Number(agent.talkTimer) > 0)
      if (!talking) continue
      const pos = positionOf(agent)
      if (!pos) continue
      const withinEarshot = ambassadors.find(
        entry => Math.hypot(entry.pos.x - pos.x, entry.pos.z - pos.z) <= HEAR_RADIUS,
      )
      if (!withinEarshot) continue
      const key = hashLine(agent.name || 'npc', line)
      if (heard.has(key)) continue         // already shipped this exact utterance
      heard.add(key)
      const name = String(agent.name || 'NPC')
      if (!speakers.includes(name)) speakers.push(name)
      lines.push({ speaker: name, text: line.slice(0, 240) })
      if (!place) place = String(withinEarshot.agent.placeName || agent.placeName || '')
    }
    if (!lines.length) return

    if (heard.size > SEEN_CAP) {            // bound memory: forget old hashes wholesale
      heard.clear()
      lines.forEach(line => heard.add(hashLine(line.speaker, line.text)))
    }

    const controller = new AbortController()
    const timer = setTimeout(() => controller.abort(), FETCH_TIMEOUT_MS)
    try {
      await fetch(`${ATANOR_BASE}/api/realcity/overhear`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        signal: controller.signal,
        body: JSON.stringify({ speakers, lines, place, ts: Date.now() / 1000 }),
      })
    } catch {
      // offline / timeout / HTTP error — silent; the city never depends on ATANOR being reachable
    } finally {
      clearTimeout(timer)
    }
  } catch {
    // never throw out of the loop
  }
}

function boot() {
  if (booted || typeof window === 'undefined') return
  booted = true
  try {
    console.log('[dialogueEavesdrop] live — ATANOR ambassadors overhear NPC talk -> :8502 /overhear (quarantine + consensus register + ungrounded topics)')
  } catch {
    /* console unavailable — ignore */
  }
  setInterval(overhearOnce, EAVESDROP_MS)
}

boot()

export {}
