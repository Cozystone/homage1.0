// roleLife.js — every ollama/atanor citizen (and anyone with a job) visibly LIVES THEIR ROLE.
// Owner theme: "every ollama agent must be living out their own role."
//
// Self-driving side-effect module (see citySystems.js contract): starts its own ~2s loop, waits for
// window.__REALCITY_CITY__, guards every access, and NEVER throws. One boot log, nothing else.
//
// HOW IT MOVES THEM — reuse, never invent. The runtime's targetFor() (scene/Actors.jsx) resolves a
// walking destination each frame from, in priority order: agent.needErrand.targetId, then the current
// agent.schedule slot -> agent.workId ('work' slot) / agent.thirdId ('third' slot) / agent.home. We
// therefore steer citizens purely by writing those SAME schedule fields the engine already honors:
//   - work hours          -> agent.workId  = the role's anchor landmark   (engine walks them to work)
//   - lunch (12:00-13:00)  -> agent.workId  = nearest cafe/market          (engine walks them to lunch)
//   - evening (18:00-21:00)-> agent.thirdId = role-flavored leisure spot   ('third' slot walks them there)
// Outside those windows we restore the citizen's original thirdId, so the engine's own routine resumes.
// We invent NO new movement field, run NO pathfinding, and touch NO brain/dialogue field. We also never
// write while a citizen is on an engine-owned behavior we must not fight: mission, self-taxi, boarding,
// or an active needErrand.
//
// HOW IT SHOWS THE ROLE. When a citizen is within ~6u of the place their day-part points at, we fire a
// role-true capability animation every ~20-40s through window.__REALCITY_AVATAR__.play(id, anim, 3-5)
// (barista->work, nurse->help, courier->carry, banker/merchant->transact, teacher->talk, ...).
//
// THE GATE. window.__REALCITY_ROLELIFE__ = { status() } returns { atAnchor, enRoute, offDuty, byRole }
// — the measurable "are they living their role" survey, recomputed live over the current cast.

const TICK_MS = 2000
const MINUTES_PER_DAY = 1440
const ANCHOR_RADIUS = 6          // "within ~6u of anchor" -> at their role workplace
const NEARBY_RADIUS = 8          // a touch looser for lunch/leisure spots
const ANIM_MIN_S = 20            // role animation cadence: every ~20..40 real seconds
const ANIM_MAX_S = 40

// role -> workplace anchor landmark id. Mirrors the engine's ROLE_LIBRARY workplaces and adds the
// task's generic synonyms (nurse->hospital, merchant->market) so the map is robust to role naming.
const ROLE_ANCHOR = {
  barista: 'river_cafe',
  nurse: 'hanbit_hospital', doctor: 'hanbit_hospital',
  teacher: 'mirae_school', student: 'mirae_school',
  merchant: 'market_lane', shopkeeper: 'market_lane',
  courier: 'south_depot',
  engineer: 'maker_yard',
  banker: 'aster_exchange',
  artist: 'neon_square',
  security: 'central_station',
  gardener: 'hill_park', retiree: 'hill_park',
}

// role -> the capability animation that reads as "doing this job". Falls back to 'work'.
const ROLE_WORK_ANIM = {
  barista: 'work', nurse: 'help', doctor: 'work',
  teacher: 'talk', student: 'talk',
  merchant: 'transact', shopkeeper: 'transact', banker: 'transact',
  courier: 'carry', engineer: 'repair',
  artist: 'work', security: 'work', gardener: 'clean', retiree: 'sit',
}

// role -> evening leisure animation. teacher reads (sit) at the park, courier exercises; default 'talk'.
const ROLE_LEISURE_ANIM = {
  teacher: 'sit', student: 'sit', courier: 'exercise', artist: 'dance', gardener: 'sit', retiree: 'sit',
}
// role -> a preferred evening leisure landmark id (else nearest park/leisure is used).
const ROLE_LEISURE_PLACE = {
  teacher: 'hill_park', student: 'hill_park', courier: 'hill_park', retiree: 'hill_park', gardener: 'hill_park',
}

const LUNCH_KINDS = ['cafe', 'retail']            // "nearest cafe/market"
const LEISURE_KINDS = ['park', 'leisure']          // role-flavored evening leisure

let booted = false
const cacheById = new Map()   // agent.id -> { anchorId, thirdId0, lunchId, leisureId, workAnim, leisureAnim, role }
const nextAnimAt = new Map()  // agent.id -> monotonic seconds when the next animation may fire

function nowSeconds() {
  return (typeof performance !== 'undefined' && performance.now ? performance.now() : Date.now()) / 1000
}

// Prefer the live-Agent cast (has .pos + is what the render/avatar layer drives) else the source cast.
function resolveCast(city) {
  if (city && Array.isArray(city.agents) && city.agents.length) return city.agents
  if (city && Array.isArray(city.npcs) && city.npcs.length) return city.npcs
  return []
}

// A usable clock, mirroring lifePatterns: attached system clock first, global fallback before handoff.
function readClock(city) {
  const clock = (city && city.systems && city.systems.clock)
    || (typeof window !== 'undefined' ? window.__REALCITY_TIME__ : null)
  if (!clock || !Number.isFinite(clock.hour)) return null
  return clock
}

// lifePatterns' weekday convention: floor(simMinutes/1440) % 7, with 0=Sunday and 6=Saturday weekend.
function dayIndexFrom(clock) {
  if (!clock || !Number.isFinite(clock.simMinutes)) return 1 // default to a weekday if minutes absent
  const days = Math.floor(clock.simMinutes / MINUTES_PER_DAY)
  return ((days % 7) + 7) % 7
}

// Which part of a citizen's role-day is it? Only 'work' contributes to the anchored/en-route gate.
function dayPartFor(hour, weekend) {
  if (weekend) return 'off'
  if (hour >= 8 && hour < 12) return 'work'
  if (hour >= 12 && hour < 13) return 'lunch'
  if (hour >= 13 && hour < 18) return 'work'
  if (hour >= 18 && hour < 21) return 'evening'
  return 'off'
}

// Live position of a citizen whether it is a live Agent (.pos.x/.z) or a source snapshot (.x/.z).
function posOf(agent) {
  const p = agent && agent.pos
  const x = p ? p.x : (agent ? agent.x : undefined)
  const z = p ? p.z : (agent ? agent.z : undefined)
  return Number.isFinite(x) && Number.isFinite(z) ? { x, z } : null
}

// The citizen is on an engine-owned behavior we must never override.
function isBusy(agent) {
  return !!(agent.mission || agent.selfTaxi || agent.boardingTaxi || agent.needErrand)
}

// Target set: any ollama/atanor mind, else (fallback) anyone the city gave a job.
function isRoleCitizen(agent) {
  if (!agent || typeof agent !== 'object') return false
  const brain = agent.dialogueBrain
  if (brain === 'ollama' || brain === 'atanor') return true
  return typeof agent.job === 'string' && agent.job.length > 0
}

function landmarkMapOf(city) {
  const map = new Map()
  const list = city && Array.isArray(city.landmarks) ? city.landmarks : []
  for (const place of list) if (place && place.id != null) map.set(place.id, place)
  return map
}

function distanceTo(from, place) {
  if (!from || !place || !Number.isFinite(place.x) || !Number.isFinite(place.z)) return Infinity
  return Math.hypot(place.x - from.x, place.z - from.z)
}

// Nearest landmark (by id) of one of the given kinds to a reference point; null if none exist.
function nearestOfKinds(landmarks, kinds, from, excludeId) {
  let bestId = null
  let bestDist = Infinity
  for (const place of landmarks.values()) {
    if (!place || place.id === excludeId || !kinds.includes(place.kind)) continue
    const dist = distanceTo(from, place)
    if (dist < bestDist) { bestDist = dist; bestId = place.id }
  }
  return bestId
}

// Resolve (once) everything role-life needs for a citizen, keyed to stable landmark ids so nothing
// churns frame-to-frame. Recomputed only if landmarks were still missing on the first pass.
function ensureCache(agent, landmarks) {
  const existing = cacheById.get(agent.id)
  if (existing && existing.resolved) return existing

  const role = String(agent.role || '')
  // Anchor: role map -> validate against real landmarks -> else the engine's own workId -> else nearest.
  let anchorId = ROLE_ANCHOR[role]
  if (!anchorId || !landmarks.has(anchorId)) {
    anchorId = (agent.workId && landmarks.has(agent.workId)) ? agent.workId : null
  }
  const home = posOf(agent) || (agent.home && Number.isFinite(agent.home.x) ? { x: agent.home.x, z: agent.home.z } : null)
  if (!anchorId) anchorId = nearestOfKinds(landmarks, ['transit', 'finance', 'workshop', 'retail', 'cafe', 'hospital', 'school', 'logistics', 'leisure', 'park'], home)
  const anchorPlace = anchorId ? landmarks.get(anchorId) : null

  // Leisure spot: role preference -> validate -> else nearest park/leisure to the anchor.
  let leisureId = ROLE_LEISURE_PLACE[role]
  if (!leisureId || !landmarks.has(leisureId)) leisureId = nearestOfKinds(landmarks, LEISURE_KINDS, anchorPlace || home)

  const cache = {
    role,
    anchorId,
    thirdId0: agent.thirdId,                                          // original social place, to restore
    lunchId: nearestOfKinds(landmarks, LUNCH_KINDS, anchorPlace || home), // nearest cafe/market for lunch
    leisureId,
    workAnim: ROLE_WORK_ANIM[role] || 'work',
    leisureAnim: ROLE_LEISURE_ANIM[role] || 'talk',
    resolved: !!(anchorId && landmarks.size),
  }
  cacheById.set(agent.id, cache)
  return cache
}

// Fire a role animation on the cadence when the citizen is close enough to the day-part's place.
function maybeAnimate(agent, anim, target, radius) {
  if (typeof window === 'undefined') return
  const avatar = window.__REALCITY_AVATAR__
  if (!avatar || typeof avatar.play !== 'function' || !target) return
  const here = posOf(agent)
  if (!here || distanceTo(here, target) > radius) return
  const t = nowSeconds()
  const due = nextAnimAt.get(agent.id) || 0
  if (t < due) return
  try {
    avatar.play(agent.id, anim, 3 + Math.random() * 2)   // duration 3..5
  } catch (_) { /* avatar not ready — ignore */ }
  nextAnimAt.set(agent.id, t + ANIM_MIN_S + Math.random() * (ANIM_MAX_S - ANIM_MIN_S))
}

// Steer one citizen for the current day-part by writing ONLY the schedule fields the engine honors,
// then fire the matching role animation when they have arrived.
function driveAgent(agent, part, landmarks) {
  const cache = ensureCache(agent, landmarks)
  if (!cache.anchorId) return                 // no anchor resolvable yet — nothing safe to do
  if (isBusy(agent)) return                   // engine owns this citizen right now — never fight it

  // Desired destinations for this part. Default (off/night/weekend) = the citizen's own routine.
  let desiredWork = cache.anchorId
  let desiredThird = cache.thirdId0
  if (part === 'lunch') desiredWork = cache.lunchId || cache.anchorId
  else if (part === 'evening') desiredThird = cache.leisureId || cache.thirdId0

  // Reuse the engine-honored movement fields (idempotent writes only).
  if (agent.workId !== desiredWork) agent.workId = desiredWork
  if (agent.thirdId !== desiredThird) agent.thirdId = desiredThird

  // Show the role once they are actually there.
  if (part === 'work') {
    maybeAnimate(agent, cache.workAnim, landmarks.get(cache.anchorId), ANCHOR_RADIUS)
  } else if (part === 'lunch') {
    maybeAnimate(agent, 'eat', landmarks.get(desiredWork), NEARBY_RADIUS)
  } else if (part === 'evening') {
    maybeAnimate(agent, cache.leisureAnim, landmarks.get(desiredThird), NEARBY_RADIUS)
  }
}

// Live "living-their-role" survey over the current cast. Only the 'work' part scores atAnchor/enRoute;
// lunch, evening, night, weekend and engine-busy citizens are counted offDuty.
function computeStatus() {
  const totals = { atAnchor: 0, enRoute: 0, offDuty: 0, total: 0, byRole: {} }
  try {
    const city = typeof window !== 'undefined' ? window.__REALCITY_CITY__ : null
    if (!city) return totals
    const clock = readClock(city)
    const hour = clock ? Math.floor(clock.hour) : -1
    const weekend = clock ? (dayIndexFrom(clock) === 6 || dayIndexFrom(clock) === 0) : false
    const part = dayPartFor(hour, weekend)
    const landmarks = landmarkMapOf(city)
    const cast = resolveCast(city)

    for (const agent of cast) {
      if (!isRoleCitizen(agent)) continue
      totals.total += 1
      const role = String(agent.role || 'other')
      const bucketRole = totals.byRole[role] || (totals.byRole[role] = { atAnchor: 0, enRoute: 0, offDuty: 0, total: 0 })
      bucketRole.total += 1

      let bucket = 'offDuty'
      if (part === 'work' && !isBusy(agent)) {
        const cache = cacheById.get(agent.id)
        const anchorPlace = cache && cache.anchorId ? landmarks.get(cache.anchorId) : null
        const here = posOf(agent)
        if (anchorPlace && here) bucket = distanceTo(here, anchorPlace) <= ANCHOR_RADIUS ? 'atAnchor' : 'enRoute'
      }
      totals[bucket] += 1
      bucketRole[bucket] += 1
    }
  } catch (_) { /* return best-effort counts on any failure */ }
  api.counts = totals
  return totals
}

// Shared state, attached to both window.__REALCITY_ROLELIFE__ and city.systems.roleLife (same identity).
const api = {
  counts: { atAnchor: 0, enRoute: 0, offDuty: 0, total: 0, byRole: {} },
  status: computeStatus,
}

function loop() {
  try {
    const city = typeof window !== 'undefined' ? window.__REALCITY_CITY__ : null
    if (!city) return
    if (!city.systems) city.systems = {}
    if (city.systems.roleLife !== api) city.systems.roleLife = api

    const clock = readClock(city)
    if (!clock) return                          // clock not online yet — wait
    const landmarks = landmarkMapOf(city)
    if (!landmarks.size) return                 // landmarks not built yet — wait
    const cast = resolveCast(city)
    if (!cast.length) return                    // cast not built yet — wait

    const hour = Math.floor(clock.hour)
    const weekend = dayIndexFrom(clock) === 6 || dayIndexFrom(clock) === 0
    const part = dayPartFor(hour, weekend)

    for (const agent of cast) {
      if (!isRoleCitizen(agent)) continue
      try {
        driveAgent(agent, part, landmarks)
      } catch (_) { /* one bad citizen must never stop the rest */ }
    }
    computeStatus()                             // refresh the cached survey
  } catch (_) { /* never throw out of the loop */ }
}

function boot() {
  if (booted || typeof window === 'undefined') return
  booted = true
  window.__REALCITY_ROLELIFE__ = api            // expose immediately (zeroed) so peers can read the shape
  try {
    console.log('[realcity] role life online — ollama/atanor citizens live their role (work anchor, lunch, evening leisure)')
  } catch (_) { /* console unavailable — ignore */ }
  setInterval(loop, TICK_MS)
  loop()
}

boot()

export {}
