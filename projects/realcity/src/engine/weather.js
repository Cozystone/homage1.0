// weather.js — procedural weather state machine (CT world-system, 2026-07-21).
// Self-driving side-effect module: ~1s loop, waits for window.__REALCITY_CITY__, publishes live
// weather to BOTH window.__REALCITY_WEATHER__ and city.systems.weather (same object).
//
// States: clear | cloudy | rain | storm | fog | snow (snow is rare).
// Each state dwells 3-8 sim-hours, then a Markov step chooses the next state (fog is dawn-biased).
// intensity ramps toward the state's target over ~minutes; wet rises during rain/storm and decays
// slowly afterwards. On every state change a CustomEvent('realcity:weather',{detail:{state,intensity}})
// is dispatched. factors summarise the sim effects: { walkSpeed, taxiDemand, shelter }.

const TICK_MS = 1000
const MINUTES_PER_DAY = 1440
const RAMP_STEP = 0.025 // intensity glide per tick (~40s to fully ramp)
const WET_RISE = 0.015 // per tick, scaled by intensity, while raining/storming
const WET_DECAY = 0.003 // per tick, slow dry-out afterwards

// Markov transition weights per current state. "rain" is reachable from cloudy, "storm" from rain,
// clear<->cloudy is the common oscillation, and snow is a rare branch off cloudy.
const TRANSITIONS = {
  clear: [['clear', 0.55], ['cloudy', 0.4], ['fog', 0.05]],
  cloudy: [['cloudy', 0.4], ['clear', 0.3], ['rain', 0.18], ['fog', 0.08], ['snow', 0.04]],
  rain: [['rain', 0.35], ['cloudy', 0.4], ['storm', 0.2], ['clear', 0.05]],
  storm: [['storm', 0.3], ['rain', 0.5], ['cloudy', 0.2]],
  fog: [['fog', 0.4], ['cloudy', 0.35], ['clear', 0.25]],
  snow: [['snow', 0.4], ['cloudy', 0.45], ['clear', 0.15]],
}

const TARGET_INTENSITY = {
  clear: 0,
  cloudy: 0.3,
  rain: 0.7,
  storm: 1,
  fog: 0.6,
  snow: 0.6,
}

const state = {
  state: 'clear',
  intensity: 0,
  wet: 0,
  factors: { walkSpeed: 1, taxiDemand: 1, shelter: false },
}

// Timing is driven off the clock's simMinutes when available, else an internal accumulator so
// weather still advances if it boots before the clock.
let internalSim = 10 * 60 + 30
let dwellUntilSim = internalSim + dwellHours() * 60

function dwellHours() {
  return 3 + Math.random() * 5 // 3..8 sim-hours
}

function phaseForHour(hour) {
  if (hour >= 5 && hour < 7) return 'dawn'
  if (hour >= 7 && hour < 18) return 'day'
  if (hour >= 18 && hour < 20) return 'dusk'
  return 'night'
}

function readClock() {
  const clock = window.__REALCITY_TIME__ || (window.__REALCITY_CITY__ && window.__REALCITY_CITY__.systems && window.__REALCITY_CITY__.systems.clock)
  const simMinutes = clock && Number.isFinite(clock.simMinutes) ? clock.simMinutes : internalSim
  const dayMinutes = ((simMinutes % MINUTES_PER_DAY) + MINUTES_PER_DAY) % MINUTES_PER_DAY
  const phase = clock && clock.phase ? clock.phase : phaseForHour(Math.floor(dayMinutes / 60))
  return { simMinutes, phase }
}

function weightedPick(entries) {
  let total = 0
  for (let i = 0; i < entries.length; i++) total += entries[i][1]
  let roll = Math.random() * total
  for (let i = 0; i < entries.length; i++) {
    roll -= entries[i][1]
    if (roll <= 0) return entries[i][0]
  }
  return entries[entries.length - 1][0]
}

function nextState(current, phase) {
  const base = TRANSITIONS[current] || TRANSITIONS.clear
  // Dawn fog bias: clone and add extra weight to a 'fog' option.
  if (phase === 'dawn') {
    const biased = base.map(pair => (pair[0] === 'fog' ? [pair[0], pair[1] + 0.35] : pair))
    if (!biased.some(pair => pair[0] === 'fog')) biased.push(['fog', 0.35])
    return weightedPick(biased)
  }
  return weightedPick(base)
}

function updateFactors() {
  const s = state.state
  let walkSpeed = 1
  if (s === 'storm' || s === 'snow') walkSpeed = 0.7
  else if (s === 'rain') walkSpeed = 0.85
  const taxiDemand = (s === 'rain' || s === 'storm') ? 1.6 : 1
  const shelter = (s === 'rain' || s === 'storm')
  state.factors.walkSpeed = walkSpeed
  state.factors.taxiDemand = taxiDemand
  state.factors.shelter = shelter
}

function transitionTo(next) {
  if (next === state.state) return
  state.state = next
  try {
    window.dispatchEvent(new CustomEvent('realcity:weather', { detail: { state: state.state, intensity: state.intensity } }))
  } catch (_) {
    /* CustomEvent may be unavailable in exotic hosts */
  }
}

function boot() {
  if (typeof window === 'undefined') return
  updateFactors()
  window.__REALCITY_WEATHER__ = state

  let anchor = (typeof performance !== 'undefined' ? performance.now() : Date.now())

  const loop = () => {
    try {
      const now = (typeof performance !== 'undefined' ? performance.now() : Date.now())
      const dtSec = Math.max(0, (now - anchor) / 1000)
      anchor = now
      internalSim += dtSec // mirror of 1 real-sec == 1 sim-min for the fallback path

      const { simMinutes, phase } = readClock()

      // Dwell then Markov transition.
      if (simMinutes >= dwellUntilSim) {
        transitionTo(nextState(state.state, phase))
        dwellUntilSim = simMinutes + dwellHours() * 60
      }

      // Ramp intensity toward the current state's target.
      const target = TARGET_INTENSITY[state.state] != null ? TARGET_INTENSITY[state.state] : 0
      if (state.intensity < target) state.intensity = Math.min(target, state.intensity + RAMP_STEP)
      else if (state.intensity > target) state.intensity = Math.max(target, state.intensity - RAMP_STEP)

      // Wet accumulates while raining/storming, dries slowly otherwise.
      if (state.state === 'rain' || state.state === 'storm') {
        state.wet = Math.min(1, state.wet + WET_RISE * state.intensity)
      } else {
        state.wet = Math.max(0, state.wet - WET_DECAY)
      }

      updateFactors()

      const city = window.__REALCITY_CITY__
      if (city) {
        if (!city.systems) city.systems = {}
        if (city.systems.weather !== state) city.systems.weather = state
      }
    } catch (_) {
      /* never throw out of the loop */
    }
  }

  setInterval(loop, TICK_MS)
  loop()
  console.log('[realcity] weather online')
}

boot()

export {}
