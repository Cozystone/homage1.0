// cityClock.js — master simulation clock (CT world-system, 2026-07-21).
// Self-driving side-effect module: starts its own ~1s loop, waits for window.__REALCITY_CITY__,
// then publishes a live clock to BOTH window.__REALCITY_TIME__ and city.systems.clock (same object).
//
// Time base: 1 real second = 1 sim minute, so a full 24h sim day takes 24 real minutes.
// Derived state: { simMinutes, hour, minute, phase, timeLabel, sunAngle }.
//   phase   : 'dawn'(5-7) | 'day'(7-18) | 'dusk'(18-20) | 'night'(20-5)
//   sunAngle: radians swept over 24h with solar noon = up (sin(sunAngle) is crude height).
// simMinutes is persisted to localStorage 'rc_clock' every 30s and restored on boot.

const STORAGE_KEY = 'rc_clock'
const TICK_MS = 1000
const SAVE_EVERY_MS = 30000
const MINUTES_PER_DAY = 1440
const DEFAULT_START = 10 * 60 + 30 // 10:30, matches the store's opening time

const state = {
  simMinutes: DEFAULT_START,
  hour: 0,
  minute: 0,
  phase: 'day',
  timeLabel: '00:00',
  sunAngle: 0,
}

function pad2(n) {
  return n < 10 ? '0' + n : '' + n
}

function phaseFor(hour) {
  if (hour >= 5 && hour < 7) return 'dawn'
  if (hour >= 7 && hour < 18) return 'day'
  if (hour >= 18 && hour < 20) return 'dusk'
  return 'night'
}

function derive() {
  const dayMinutes = ((state.simMinutes % MINUTES_PER_DAY) + MINUTES_PER_DAY) % MINUTES_PER_DAY
  const hour = Math.floor(dayMinutes / 60)
  const minute = Math.floor(dayMinutes % 60)
  state.hour = hour
  state.minute = minute
  state.phase = phaseFor(hour)
  state.timeLabel = pad2(hour) + ':' + pad2(minute)
  // Noon (720 min) -> +PI/2 (up); sunrise 06:00 -> 0; sunset 18:00 -> PI; midnight -> -PI/2.
  state.sunAngle = (dayMinutes / MINUTES_PER_DAY) * Math.PI * 2 - Math.PI / 2
}

function restore() {
  try {
    const raw = window.localStorage.getItem(STORAGE_KEY)
    if (raw == null) return
    const saved = parseFloat(raw)
    if (Number.isFinite(saved) && saved >= 0) state.simMinutes = saved
  } catch (_) {
    /* localStorage may be blocked; keep default */
  }
}

function persist() {
  try {
    window.localStorage.setItem(STORAGE_KEY, String(state.simMinutes))
  } catch (_) {
    /* ignore quota / privacy-mode errors */
  }
}

function boot() {
  if (typeof window === 'undefined') return
  restore()
  derive()
  // Expose immediately so peers that boot first can read a valid clock before the city handle lands.
  window.__REALCITY_TIME__ = state

  let anchor = (typeof performance !== 'undefined' ? performance.now() : Date.now())
  let lastSave = anchor

  const loop = () => {
    try {
      const now = (typeof performance !== 'undefined' ? performance.now() : Date.now())
      const dtSec = Math.max(0, (now - anchor) / 1000)
      anchor = now
      // 1 real second advances the sim by 1 minute; delta-based so tab-throttling stays consistent.
      state.simMinutes += dtSec
      derive()

      const city = window.__REALCITY_CITY__
      if (city) {
        if (!city.systems) city.systems = {}
        if (city.systems.clock !== state) city.systems.clock = state
      }

      if (now - lastSave >= SAVE_EVERY_MS) {
        persist()
        lastSave = now
      }
    } catch (_) {
      /* never throw out of the loop */
    }
  }

  setInterval(loop, TICK_MS)
  loop()
  console.log('[realcity] clock online')
}

boot()

export {}
