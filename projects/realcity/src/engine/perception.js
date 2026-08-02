// perception.js — human-like, FOV-limited senses for agents (CT world-system, 2026-07-21).
// Self-driving side-effect module: ~1s loop, waits for window.__REALCITY_CITY__, then every 5s
// auto-computes perception for up to 3 ATANOR-brained agents and stores it on agent.percept.
// Exports nothing; attaches window.__REALCITY_PERCEPTION__ = { perceive } and city.systems.perception.
//
// perceive(agent, city, { fovDeg=110, range=60, hearRange=25 }) ->
//   { seen:[{id,name,kind,dist}], heard:[{kind,dist}], felt:{weather,phase,temperature,crowding} }
//   seen : other agents + landmarks (+ vehicles if present) inside range AND the forward FOV cone.
//   heard: talking agents within hearRange + rain (if raining/storming) + siren (active incident) — no facing test.
//   felt : ambient weather/phase, a crude temperature, and local crowding.

const TICK_MS = 1000
const AUTO_EVERY_MS = 5000
const SEEN_CAP = 12
const CROWD_RADIUS = 8

// Read a planar {x,z} position from an agent / landmark / vehicle in any of the shapes this world uses:
// live agents carry pos (a THREE.Vector3 with .x/.z), landmarks/cars carry top-level x/z, and static
// npcs fall back to their home coordinate.
function posOf(entity) {
  if (!entity) return null
  const p = entity.pos
  if (p && Number.isFinite(p.x) && Number.isFinite(p.z)) return p
  if (Number.isFinite(entity.x) && Number.isFinite(entity.z)) return entity
  const home = entity.home
  if (home && Number.isFinite(home.x) && Number.isFinite(home.z)) return home
  return null
}

// Forward unit vector in (x,z). This world moves agents by (sin(heading), cos(heading)), so facing
// uses the same convention. Falls back to agent.rot, then to a supplied previous position, then +z.
function forwardOf(agent, self) {
  let h = null
  if (Number.isFinite(agent.heading)) h = agent.heading
  else if (Number.isFinite(agent.rot)) h = agent.rot
  else if (agent.rot && Number.isFinite(agent.rot.y)) h = agent.rot.y
  if (h != null) return { x: Math.sin(h), z: Math.cos(h) }
  const prev = agent.prevPos || agent.lastPos
  if (self && prev && Number.isFinite(prev.x) && Number.isFinite(prev.z)) {
    const dx = self.x - prev.x
    const dz = self.z - prev.z
    const m = Math.hypot(dx, dz)
    if (m > 1e-4) return { x: dx / m, z: dz / m }
  }
  return { x: 0, z: 1 }
}

function readWeatherState() {
  try {
    const w = window.__REALCITY_WEATHER__ || (window.__REALCITY_CITY__ && window.__REALCITY_CITY__.systems && window.__REALCITY_CITY__.systems.weather)
    return w && w.state ? w.state : 'clear'
  } catch (_) {
    return 'clear'
  }
}

function readPhase() {
  try {
    const t = window.__REALCITY_TIME__ || (window.__REALCITY_CITY__ && window.__REALCITY_CITY__.systems && window.__REALCITY_CITY__.systems.clock)
    return t && t.phase ? t.phase : 'day'
  } catch (_) {
    return 'day'
  }
}

function crudeTemperature(weather, phase) {
  // Coarse Celsius-ish reading: snow/night cold, sunny day warm, everything else mild.
  if (weather === 'snow') return -2
  if (phase === 'night') return 8
  if (phase === 'day' && weather === 'clear') return 26
  return 16
}

function isTalking(other) {
  if (!other) return false
  if (other.talking || other.speaking || other.isSpeaking) return true
  if (other.speech && other.speech.active) return true
  const act = other.activity
  return typeof act === 'string' && /talk|chat|convers|greet|social/i.test(act)
}

function perceive(agent, city, opts) {
  const out = { seen: [], heard: [], felt: { weather: 'clear', phase: 'day', temperature: 16, crowding: 0 } }
  try {
    if (!agent || !city) return out
    const fovDeg = opts && Number.isFinite(opts.fovDeg) ? opts.fovDeg : 110
    const range = opts && Number.isFinite(opts.range) ? opts.range : 60
    const hearRange = opts && Number.isFinite(opts.hearRange) ? opts.hearRange : 25

    const self = posOf(agent)
    if (!self) {
      // Without a position we can still report ambient feeling.
      const weather0 = readWeatherState()
      const phase0 = readPhase()
      out.felt.weather = weather0
      out.felt.phase = phase0
      out.felt.temperature = crudeTemperature(weather0, phase0)
      return out
    }

    const forward = forwardOf(agent, self)
    const cosHalfFov = Math.cos((fovDeg / 2) * (Math.PI / 180))
    const rangeSq = range * range
    const hearRangeSq = hearRange * hearRange

    const agents = Array.isArray(city.agents) ? city.agents : (Array.isArray(city.npcs) ? city.npcs : [])
    const landmarks = Array.isArray(city.landmarks) ? city.landmarks : []
    const vehicles = Array.isArray(city.cars) ? city.cars : (Array.isArray(city.vehicles) ? city.vehicles : [])

    // ---- SEEN: FOV + range cone over agents, landmarks, vehicles ----
    const consider = (entity, kind) => {
      if (!entity || entity === agent || entity.id === agent.id) return
      const p = posOf(entity)
      if (!p) return
      const dx = p.x - self.x
      const dz = p.z - self.z
      const distSq = dx * dx + dz * dz
      if (distSq > rangeSq || distSq < 1e-6) return
      const dist = Math.sqrt(distSq)
      // cos(angle) between forward and direction-to-target; both must be unit for the test.
      const dot = (forward.x * dx + forward.z * dz) / dist
      if (dot <= cosHalfFov) return
      out.seen.push({ id: entity.id, name: entity.name || entity.driverName || entity.id, kind, dist: Math.round(dist) })
    }

    for (let i = 0; i < agents.length; i++) consider(agents[i], 'agent')
    for (let i = 0; i < landmarks.length; i++) consider(landmarks[i], 'landmark')
    for (let i = 0; i < vehicles.length; i++) consider(vehicles[i], 'vehicle')

    out.seen.sort((a, b) => a.dist - b.dist)
    if (out.seen.length > SEEN_CAP) out.seen.length = SEEN_CAP

    // ---- HEARD: omnidirectional within hearRange ----
    for (let i = 0; i < agents.length; i++) {
      const other = agents[i]
      if (!other || other === agent || other.id === agent.id) continue
      if (!isTalking(other)) continue
      const p = posOf(other)
      if (!p) continue
      const dx = p.x - self.x
      const dz = p.z - self.z
      const distSq = dx * dx + dz * dz
      if (distSq <= hearRangeSq) out.heard.push({ kind: 'talk', dist: Math.round(Math.sqrt(distSq)) })
    }

    const weather = readWeatherState()
    if (weather === 'rain' || weather === 'storm') out.heard.push({ kind: 'rain', dist: 0 })

    // Siren from any active civic incident (civic system is optional).
    try {
      const incidents = city.systems && city.systems.civic && city.systems.civic.incidents
      if (Array.isArray(incidents)) {
        let sirenDist = Infinity
        for (let i = 0; i < incidents.length; i++) {
          const inc = incidents[i]
          if (!inc || inc.active === false || inc.resolved) continue
          const p = posOf(inc)
          if (p) {
            const d = Math.hypot(p.x - self.x, p.z - self.z)
            if (d < sirenDist) sirenDist = d
          } else if (sirenDist === Infinity) {
            sirenDist = 0
          }
        }
        if (sirenDist !== Infinity) out.heard.push({ kind: 'siren', dist: Math.round(sirenDist === Infinity ? 0 : sirenDist) })
      }
    } catch (_) {
      /* civic optional */
    }

    // ---- FELT: ambient state + crude temperature + local crowding ----
    const phase = readPhase()
    let crowding = 0
    for (let i = 0; i < out.seen.length; i++) {
      if (out.seen[i].dist <= CROWD_RADIUS) crowding++
    }
    out.felt.weather = weather
    out.felt.phase = phase
    out.felt.temperature = crudeTemperature(weather, phase)
    out.felt.crowding = crowding
  } catch (_) {
    /* never throw */
  }
  return out
}

function boot() {
  if (typeof window === 'undefined') return
  const api = { perceive }
  window.__REALCITY_PERCEPTION__ = api

  let lastAuto = 0

  const loop = () => {
    try {
      const city = window.__REALCITY_CITY__
      if (!city) return
      if (!city.systems) city.systems = {}
      if (city.systems.perception !== api) city.systems.perception = api

      const now = (typeof performance !== 'undefined' ? performance.now() : Date.now())
      if (now - lastAuto < AUTO_EVERY_MS) return
      lastAuto = now

      const agents = Array.isArray(city.agents) ? city.agents : (Array.isArray(city.npcs) ? city.npcs : [])
      let done = 0
      for (let i = 0; i < agents.length && done < 3; i++) {
        const agent = agents[i]
        if (agent && agent.brain === 'atanor') {
          agent.percept = perceive(agent, city)
          done++
        }
      }
    } catch (_) {
      /* never throw out of the loop */
    }
  }

  setInterval(loop, TICK_MS)
  loop()
  console.log('[realcity] perception online')
}

boot()

export {}
