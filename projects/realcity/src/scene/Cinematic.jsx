// Cinematic.jsx — the scene's single cinematic post-processing stack.
//
// Browser-honest "near-Unreal" ceiling: an HDR half-float pipeline with depth-aware ambient
// occlusion, threshold-gated bloom (only emissives / neon / streetlights glow), ACES filmic
// tone mapping, a subtle vignette, and a whisper-thin final grade. The look is graded live by
// the city clock and weather.
//
// Design notes:
//  - This owns the one and only <EffectComposer> for the scene. Two composers would each do a
//    full-scene render and fight over the framebuffer, so RealCityScene mounts this INSTEAD of
//    the older PostFX.
//  - Time/weather adaptation is done imperatively by mutating effect instances via refs inside
//    a single useFrame, NOT by re-rendering React each frame (which would rebuild the effect
//    passes every frame and reconfigure N8AO). Cheap, allocation-free, no console output.
//  - The whole stack unmounts on WebGL context loss and remounts (with fresh GPU resources) on
//    restore, so a lost context never spams errors or renders through a dead composer.
//  - The world signals are read defensively with optional chaining; everything works when the
//    clock/weather systems are absent (it simply holds the neutral daytime grade).

import { useEffect, useRef, useState } from 'react'
import { useFrame, useThree } from '@react-three/fiber'
import { Bloom, BrightnessContrast, EffectComposer, N8AO, SMAA, ToneMapping, Vignette } from '@react-three/postprocessing'
import { ToneMappingMode } from 'postprocessing'
import { HalfFloatType } from 'three'

// Base look — daytime, clear weather. Time/weather nudges these within tight, tasteful bounds.
const BASE = {
  bloomIntensity: 0.55,
  vignetteOffset: 0.32,
  vignetteDarkness: 0.3,
  brightness: 0.0,
  contrast: 0.05,
}

function clamp01(v) {
  return v < 0 ? 0 : v > 1 ? 1 : v
}

// Frame-rate independent smoothing so dawn/dusk and weather transitions glide instead of pop.
function approach(current, target, dt, rate = 5) {
  return current + (target - current) * (1 - Math.exp(-rate * dt))
}

// Read the live world grade signals. Any of these may be absent — never throw, never assume.
// Returns nightness (0 = full day, 0.5 = dawn/dusk, 1 = deep night) and murk (0 = clear .. 1 = heavy fog/storm).
function readGrade() {
  let nightness = 0
  let murk = 0
  try {
    const city = typeof window !== 'undefined' ? window.__REALCITY_CITY__ : null
    const clock = city?.systems?.clock
    const weather = city?.systems?.weather

    const phase = clock?.phase
    if (phase === 'night') nightness = 1
    else if (phase === 'dawn' || phase === 'dusk') nightness = 0.5
    else if (phase === 'day') nightness = 0
    else if (typeof clock?.sunAngle === 'number') nightness = clamp01(0.5 - clock.sunAngle * 0.5) // soft fallback

    const wstate = weather?.state
    const wi = typeof weather?.intensity === 'number' ? clamp01(weather.intensity) : 0.5
    if (wstate === 'fog') murk = 0.6 + 0.4 * wi
    else if (wstate === 'storm') murk = 0.5 + 0.5 * wi
    else if (wstate === 'rain') murk = 0.35 * wi
    else if (wstate === 'cloudy' || wstate === 'snow') murk = 0.2 * wi
  } catch {
    // window / systems not available yet — hold the neutral grade.
  }
  return { nightness, murk }
}

export default function Cinematic() {
  const gl = useThree(state => state.gl)
  const [ready, setReady] = useState(true)

  // WebGL context-loss guard: drop the composer while the context is gone, rebuild on restore.
  useEffect(() => {
    const canvas = gl?.domElement
    if (!canvas) return undefined
    const onLost = e => {
      e.preventDefault() // let the browser attempt a restore instead of killing the page
      setReady(false)
    }
    const onRestored = () => setReady(true)
    canvas.addEventListener('webglcontextlost', onLost, false)
    canvas.addEventListener('webglcontextrestored', onRestored, false)
    return () => {
      canvas.removeEventListener('webglcontextlost', onLost)
      canvas.removeEventListener('webglcontextrestored', onRestored)
    }
  }, [gl])

  const bloomRef = useRef(null)
  const vignetteRef = useRef(null)
  const gradeRef = useRef(null) // BrightnessContrast instance

  // Imperative grade. Runs at default priority (0), i.e. before the composer's render (priority 1),
  // so uniform changes land in the same frame with no visual lag. Refs are null while the composer
  // is unmounted (context loss) — we simply skip.
  useFrame((_, delta) => {
    const bloom = bloomRef.current
    const vignette = vignetteRef.current
    const grade = gradeRef.current
    if (!bloom && !vignette && !grade) return

    const dt = Math.min(delta, 0.1) // clamp long frames (tab refocus) so nothing jumps
    const { nightness, murk } = readGrade()

    // Night: neon / streetlights bloom bigger and the image sits a touch darker (lower "exposure").
    // Fog / storm: pull bloom back slightly and soften contrast so highlights don't smear.
    const bloomTarget = Math.max(0, BASE.bloomIntensity + nightness * 0.85 - murk * 0.2)
    const vignetteTarget = BASE.vignetteDarkness + nightness * 0.15
    const brightnessTarget = BASE.brightness - nightness * 0.05
    const contrastTarget = BASE.contrast - murk * 0.09

    if (bloom) bloom.intensity = approach(bloom.intensity, bloomTarget, dt)
    if (vignette) vignette.darkness = approach(vignette.darkness, vignetteTarget, dt)
    if (grade) {
      grade.brightness = approach(grade.brightness, brightnessTarget, dt)
      grade.contrast = approach(grade.contrast, contrastTarget, dt)
    }
  })

  if (!ready) return null

  return (
    <EffectComposer multisampling={0} enableNormalPass={false} frameBufferType={HalfFloatType}>
      {/* Depth-aware ambient occlusion grounds meshes with soft contact shade. Half-res + the
          performance quality tier keeps it affordable across the full city and 160 agents.
          N8AO auto-detects the renderer's logarithmic depth buffer, so it stays correct here. */}
      <N8AO halfRes quality="performance" aoRadius={5} distanceFalloff={1.0} intensity={1.0} />

      {/* High luminance threshold so only genuinely bright emissives bloom — faint by day, big at night. */}
      <Bloom
        ref={bloomRef}
        mipmapBlur
        luminanceThreshold={0.85}
        luminanceSmoothing={0.12}
        intensity={BASE.bloomIntensity}
        radius={0.7}
        levels={7}
      />

      {/* ACES filmic: the cinematic HDR->LDR curve, applied on the half-float buffer.
          (The composer sets the renderer to NoToneMapping while it runs, so this is the only tone map.) */}
      <ToneMapping mode={ToneMappingMode.ACES_FILMIC} />

      {/* Whisper-thin final grade; brightness doubles as the subtle night "exposure" pull. */}
      <BrightnessContrast ref={gradeRef} brightness={BASE.brightness} contrast={BASE.contrast} />

      {/* Subtle vignette to seat the eye toward frame center. */}
      <Vignette ref={vignetteRef} offset={BASE.vignetteOffset} darkness={BASE.vignetteDarkness} />

      {/* Antialiasing last — cleans the edges of the final tone-mapped image (hardware MSAA is off). */}
      <SMAA />
    </EffectComposer>
  )
}
