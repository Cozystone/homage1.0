// populationMix.js — the brain ratio across the whole cast (CT world-system, 2026-07-21).
// Owner goal: mix ATANOR + ollama minds through the population, as many as sensible, at a good ratio.
//
// Self-driving side-effect module (see citySystems.js contract): starts its own ~1s loop, waits for
// window.__REALCITY_CITY__ and a built cast, then assigns each citizen a dialogueBrain EXACTLY ONCE
// and stops. Guards everything, never throws, one boot log. It does NOT call any LLM and does NOT
// modify localLLM.js — it only stamps a routing flag that dialogue code consumes elsewhere.
//
// Assignment policy:
//   - brain==='atanor' citizens (the ambassadors) -> dialogueBrain='atanor' (their mind is our engine)
//   - of the remaining citizens, the N most social/talkative -> dialogueBrain='ollama'
//   - everyone else -> dialogueBrain='engine' (canned / behavior-only; no LLM cost)
// N = VITE_OLLAMA_CAST (default 24). Capping ollama keeps local GPU load sane: one dolphin3 on a
// single GPU only serves a few live conversations per minute, so most of the crowd stays 'engine'.

const TICK_MS = 1000

let booted = false
let assigned = false

// Public state, attached to both window.__REALCITY_CAST__ and city.systems.cast (same identity).
const api = {
  counts: { atanor: 0, ollama: 0, engine: 0 },
  byId: new Map(),
}

// Resolve the citizen cast from the city handle, tolerating either shape.
function resolveCast(city) {
  if (city && Array.isArray(city.agents) && city.agents.length) return city.agents
  if (city && Array.isArray(city.npcs) && city.npcs.length) return city.npcs
  return []
}

// How many citizens should carry the ollama brain. import.meta.env is Vite-injected at build; guard
// for non-Vite contexts (tests) and non-numeric values, defaulting to 24.
function ollamaTarget() {
  let raw
  try {
    const env = (typeof import.meta !== 'undefined' && import.meta && import.meta.env) ? import.meta.env : null
    raw = env ? env.VITE_OLLAMA_CAST : undefined
  } catch (_) {
    raw = undefined
  }
  const n = Number(raw ?? 24)
  return Number.isFinite(n) && n >= 0 ? Math.floor(n) : 24
}

// Talkativeness heuristics — there is no numeric extraversion in the cast, so we derive one from the
// authored personality / speech-style / relationship-style. If a numeric agent.extraversion is ever
// present we trust it directly. Absent any signal, order falls back to cast order (i.e. "first N").
const PERSONALITY_TALK = {
  warm: 0.9, funny: 0.9, curious: 0.8, optimistic: 0.8, 'street-smart': 0.7, restless: 0.65,
  direct: 0.55, ambitious: 0.55, 'dry-humored': 0.45, patient: 0.4, skeptical: 0.4, careful: 0.35,
  tired: 0.3, formal: 0.3, 'soft-spoken': 0.25, reserved: 0.2,
}
const SPEECH_TALK = {
  warm_chatty: 0.9, bright_casual: 0.8, playful: 0.85, curious_precise: 0.6, street_practical: 0.55,
  polite_brief: 0.4, tired_soft: 0.35, dry_direct: 0.4, careful_formal: 0.3, reserved: 0.25,
}
const RELATIONSHIP_TALK = {
  chatty: 0.9, curious: 0.75, neighborly: 0.7, helpful: 0.6, 'busy-but-kind': 0.45, practical: 0.45,
  formal: 0.35, private: 0.2,
}

function talkScore(agent) {
  if (Number.isFinite(agent.extraversion)) return agent.extraversion
  let score = 0
  let signals = 0
  const personality = agent.personality
  if (personality != null) {
    score += PERSONALITY_TALK[personality] != null ? PERSONALITY_TALK[personality] : 0.5
    signals += 1
  }
  const speechId = agent.speechStyle && agent.speechStyle.id
  if (speechId != null) {
    score += SPEECH_TALK[speechId] != null ? SPEECH_TALK[speechId] : 0.5
    signals += 1
  }
  const rel = agent.autonomy && agent.autonomy.relationshipStyle
  if (rel != null) {
    score += RELATIONSHIP_TALK[rel] != null ? RELATIONSHIP_TALK[rel] : 0.5
    signals += 1
  }
  // No authored signals at all -> neutral 0.5 so ordering degrades to cast order (first N).
  return signals ? score / signals : 0.5
}

function assign(cast) {
  const target = ollamaTarget()
  const counts = { atanor: 0, ollama: 0, engine: 0 }
  const byId = new Map()

  // Ambassadors first: their mind is the ATANOR engine, they keep it.
  const others = []
  cast.forEach((agent, index) => {
    if (!agent || typeof agent !== 'object') return
    if (agent.brain === 'atanor') {
      agent.dialogueBrain = 'atanor'
      counts.atanor += 1
      byId.set(agent.id, 'atanor')
    } else {
      others.push({ agent, index })
    }
  })

  // Rank the rest by talkativeness (desc); ties keep cast order so it degrades cleanly to "first N".
  others.sort((a, b) => {
    const diff = talkScore(b.agent) - talkScore(a.agent)
    return diff !== 0 ? diff : a.index - b.index
  })

  const ollamaCount = Math.max(0, Math.min(target, others.length))
  others.forEach((entry, rank) => {
    const brain = rank < ollamaCount ? 'ollama' : 'engine'
    entry.agent.dialogueBrain = brain
    counts[brain] += 1
    byId.set(entry.agent.id, brain)
  })

  api.counts = counts
  api.byId = byId
  return counts
}

function loop() {
  try {
    if (assigned) return
    const city = typeof window !== 'undefined' ? window.__REALCITY_CITY__ : null
    if (!city) return
    if (!city.systems) city.systems = {}
    if (city.systems.cast !== api) city.systems.cast = api

    const cast = resolveCast(city)
    if (!cast.length) return // cast not built yet — try again next tick

    const counts = assign(cast)
    assigned = true
    try {
      console.log(`[realcity] population mix — atanor=${counts.atanor} ollama=${counts.ollama} engine=${counts.engine}`)
    } catch (_) {
      /* console unavailable — ignore */
    }
  } catch (_) {
    /* never throw out of the loop */
  }
}

function boot() {
  if (booted || typeof window === 'undefined') return
  booted = true
  // Expose immediately (empty) so callers can read the shape before assignment completes.
  window.__REALCITY_CAST__ = api
  setInterval(loop, TICK_MS)
  loop()
}

boot()

export {}
