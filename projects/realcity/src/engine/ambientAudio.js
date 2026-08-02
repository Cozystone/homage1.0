// ambientAudio.js — procedural WebAudio soundscape (CT-track world system, self-driving).
//
// NO external assets: every layer is synthesized from noise buffers and oscillators. The whole graph
// is gesture-gated — the AudioContext is created and resumed only on the first pointerdown/keydown
// (browsers block autoplay), and all layer gains ramp smoothly so nothing clicks. CPU stays trivial:
// a few long looping buffers plus a handful of oscillators, no per-frame JS synthesis.
//
// Layers: traffic bed (brown noise -> lowpass 300Hz, constant low), rain (white noise -> bandpass,
// gain follows weather.intensity on rain/storm), night crickets (pulsed bandpassed tone on
// clear/cloudy nights), siren (700/950Hz two-tone while civic siren is active).
//
// Public API -> window.__REALCITY_AUDIO__ = { enabled, unlock() } (also city.systems.ambient)

const TICK_MS = 1000
const MASTER_GAIN = 0.12
const TRAFFIC_GAIN = 0.4
const RAIN_MAX_GAIN = 0.7
const CRICKET_BASE_GAIN = 0.015
const CRICKET_PULSE_DEPTH = 0.02
const SIREN_GAIN = 0.06

// ---- module state -------------------------------------------------------------------------------
let started = false
let ctx = null
let master = null
let rainGain = null
let cricketGain = null
let cricketPulseGain = null
let sirenGain = null
let built = false

const api = {
  enabled: false,
  unlock,
}

// ---- synthesis helpers -------------------------------------------------------------------------
function noiseBuffer(context, seconds, brown) {
  const length = Math.max(1, Math.floor(context.sampleRate * seconds))
  const buffer = context.createBuffer(1, length, context.sampleRate)
  const data = buffer.getChannelData(0)
  let last = 0
  for (let i = 0; i < length; i += 1) {
    const white = Math.random() * 2 - 1
    if (brown) {
      last = (last + 0.02 * white) / 1.02
      data[i] = last * 3.5
    } else {
      data[i] = white
    }
  }
  return buffer
}

function loopingSource(context, buffer) {
  const source = context.createBufferSource()
  source.buffer = buffer
  source.loop = true
  return source
}

function buildGraph() {
  if (built) return
  const AudioCtor = typeof window !== 'undefined' && (window.AudioContext || window.webkitAudioContext)
  if (!AudioCtor) return
  ctx = new AudioCtor()
  built = true

  master = ctx.createGain()
  master.gain.value = MASTER_GAIN
  master.connect(ctx.destination)

  // traffic bed: brown noise -> lowpass 300Hz -> constant low gain
  const trafficSource = loopingSource(ctx, noiseBuffer(ctx, 3, true))
  const trafficFilter = ctx.createBiquadFilter()
  trafficFilter.type = 'lowpass'
  trafficFilter.frequency.value = 300
  const trafficGain = ctx.createGain()
  trafficGain.gain.value = TRAFFIC_GAIN
  trafficSource.connect(trafficFilter).connect(trafficGain).connect(master)
  trafficSource.start()

  // rain: white noise -> bandpass -> gain (0 until weather says rain/storm)
  const rainSource = loopingSource(ctx, noiseBuffer(ctx, 3, false))
  const rainFilter = ctx.createBiquadFilter()
  rainFilter.type = 'bandpass'
  rainFilter.frequency.value = 1400
  rainFilter.Q.value = 0.6
  rainGain = ctx.createGain()
  rainGain.gain.value = 0
  rainSource.connect(rainFilter).connect(rainGain).connect(master)
  rainSource.start()

  // night crickets: bandpassed tone, pulsed by a square LFO on its gain (0 unless night+clear)
  const cricketOsc = ctx.createOscillator()
  cricketOsc.type = 'triangle'
  cricketOsc.frequency.value = 4200
  const cricketFilter = ctx.createBiquadFilter()
  cricketFilter.type = 'bandpass'
  cricketFilter.frequency.value = 4200
  cricketFilter.Q.value = 8
  cricketGain = ctx.createGain()
  cricketGain.gain.value = 0
  cricketOsc.connect(cricketFilter).connect(cricketGain).connect(master)
  cricketOsc.start()
  const cricketLfo = ctx.createOscillator()
  cricketLfo.type = 'square'
  cricketLfo.frequency.value = 9 // ~9 chirps/sec
  cricketPulseGain = ctx.createGain()
  cricketPulseGain.gain.value = 0 // pulse depth, raised when active
  cricketLfo.connect(cricketPulseGain).connect(cricketGain.gain)
  cricketLfo.start()

  // siren: one oscillator whose frequency is pushed 700<->950 by a square LFO (0.55s alternation)
  const sirenOsc = ctx.createOscillator()
  sirenOsc.type = 'sawtooth'
  sirenOsc.frequency.value = 825 // midpoint of 700 and 950
  sirenGain = ctx.createGain()
  sirenGain.gain.value = 0
  sirenOsc.connect(sirenGain).connect(master)
  sirenOsc.start()
  const sirenLfo = ctx.createOscillator()
  sirenLfo.type = 'square'
  sirenLfo.frequency.value = 1 / 1.1 // half-period ~0.55s -> alternate 700/950
  const sirenLfoGain = ctx.createGain()
  sirenLfoGain.gain.value = 125 // +/-125 around 825
  sirenLfo.connect(sirenLfoGain).connect(sirenOsc.frequency)
  sirenLfo.start()

  // stay silent until a gesture resumes the context
  try {
    if (ctx.state === 'running') ctx.suspend()
  } catch {
    /* some contexts start suspended already */
  }
}

// ---- gesture gate ------------------------------------------------------------------------------
function unlock() {
  try {
    if (!built) buildGraph()
    if (ctx && ctx.state !== 'running') {
      const resumed = ctx.resume()
      if (resumed && typeof resumed.catch === 'function') resumed.catch(() => {})
    }
    api.enabled = !!(ctx && ctx.state !== 'closed')
  } catch {
    /* never throw from a gesture handler */
  }
}

function attachGestureListeners() {
  if (typeof window === 'undefined') return
  const handler = () => unlock()
  window.addEventListener('pointerdown', handler, { passive: true })
  window.addEventListener('keydown', handler)
  window.addEventListener('touchstart', handler, { passive: true })
}

// ---- per-second poll ---------------------------------------------------------------------------
function ramp(param, target, time = 0.5) {
  try {
    param.setTargetAtTime(target, ctx.currentTime, time)
  } catch {
    try { param.value = target } catch { /* ignore */ }
  }
}

function poll() {
  try {
    if (!ctx || !built) return
    const city = typeof window !== 'undefined' ? window.__REALCITY_CITY__ : null
    const weather = city?.systems?.weather
    const clock = city?.systems?.clock
    const civic = city?.systems?.civic

    // rain follows weather intensity on rain/storm, else fades out
    const rainy = weather && (weather.state === 'rain' || weather.state === 'storm')
    const rainTarget = rainy ? Math.max(0, Math.min(1, Number(weather.intensity) || 0.5)) * RAIN_MAX_GAIN : 0
    if (rainGain) ramp(rainGain.gain, rainTarget, 0.6)

    // crickets only at night when the sky is clear/cloudy (weather absent => treat as clear)
    const clearish = !weather || weather.state === 'clear' || weather.state === 'cloudy'
    const night = clock && clock.phase === 'night'
    const cricketsOn = !!(night && clearish)
    if (cricketGain) ramp(cricketGain.gain, cricketsOn ? CRICKET_BASE_GAIN : 0, 0.8)
    if (cricketPulseGain) ramp(cricketPulseGain.gain, cricketsOn ? CRICKET_PULSE_DEPTH : 0, 0.8)

    // siren while the civic layer reports an active siren
    const sirenOn = !!(civic && civic.siren)
    if (sirenGain) ramp(sirenGain.gain, sirenOn ? SIREN_GAIN : 0, 0.08)

    api.enabled = ctx.state === 'running'
  } catch {
    /* poll must never throw */
  }
}

// ---- lifecycle ---------------------------------------------------------------------------------
function init(city) {
  attachGestureListeners()
  if (typeof window !== 'undefined') window.__REALCITY_AUDIO__ = api
  city.systems = city.systems || {}
  city.systems.ambient = api

  // eslint-disable-next-line no-console
  console.log('[realcity:ambient] procedural soundscape armed (gesture to unlock)')
}

function boot() {
  if (typeof window === 'undefined') return
  setInterval(() => {
    try {
      const city = window.__REALCITY_CITY__
      if (!city) return
      if (!started) {
        started = true
        init(city)
      }
      poll()
    } catch {
      /* self-driving loop must never throw */
    }
  }, TICK_MS)
}

boot()

export {}
