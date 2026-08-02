import { useEffect, useMemo, useRef, useState } from 'react'
import { useFrame } from '@react-three/fiber'
import { Environment, Sky, Stars } from '@react-three/drei'
import * as THREE from 'three'
import { useCityStore } from '../engine/cityStore'
import { exposeTextureCatalog, makeProceduralTexture } from './proceduralTextures'

// --- frame-rate-independent helpers (no per-frame allocation) ---
const clamp01 = (v) => (Number.isFinite(v) ? (v < 0 ? 0 : v > 1 ? 1 : v) : 0)
const lerp = (a, b, t) => a + (b - a) * t
// exponential smoothing toward a target; independent of frame rate
const damp = (a, b, lambda, dt) => a + (b - a) * (1 - Math.exp(-lambda * dt))
function dampColor(color, target, lambda, dt) {
  color.r = damp(color.r, target.r, lambda, dt)
  color.g = damp(color.g, target.g, lambda, dt)
  color.b = damp(color.b, target.b, lambda, dt)
}
// live CT-track systems (attached async by sibling engine modules; may be absent)
function readSystems() {
  if (typeof window === 'undefined') return null
  const city = window.__REALCITY_CITY__
  return (city && city.systems) || null
}

function sunFor(minutes) {
  const hour = minutes / 60
  const angle = ((hour - 6) / 12) * Math.PI
  return new THREE.Vector3(-Math.cos(angle), Math.sin(angle), 0.42).normalize()
}

export default function Atmosphere() {
  const sunRef = useRef(sunFor(useCityStore.getState().timeMinutes))
  const dirRef = useRef()
  const fillRef = useRef()
  const ambientRef = useRef()
  const hemiRef = useRef()
  const fogRef = useRef()
  const sunDiscRef = useRef()
  const moonDiscRef = useRef()
  const skyTick = useRef(-1)
  const [skySun, setSkySun] = useState(() => sunRef.current.toArray())
  // Sky shader mood is driven through React state (single source of truth for drei's
  // Sky uniforms) so per-frame damping never fights prop reconciliation. Updated on the
  // same throttled tick that moves the sky sun, so it adds zero extra re-renders.
  const [skyMood, setSkyMood] = useState({ turbidity: 2.9, rayleigh: 1.25, mie: 0.0045 })

  // Reusable scratch objects + read-only color palette (allocated once).
  const tmp = useMemo(
    () => ({ sun: new THREE.Vector3(), wind: new THREE.Vector2(), tint: new THREE.Color(), fog: new THREE.Color() }),
    [],
  )
  const palette = useMemo(
    () => ({
      // sun / directional tint per phase (dawn warm-pink, day neutral, dusk orange, night cool-blue)
      sunDawn: new THREE.Color('#f6a99f'),
      sunDay: new THREE.Color('#fff3e2'),
      sunDusk: new THREE.Color('#ff8a3c'),
      sunNight: new THREE.Color('#5566a0'),
      // fog base per phase
      fogDawn: new THREE.Color('#a88a80'),
      fogDay: new THREE.Color('#7f91a0'),
      fogDusk: new THREE.Color('#9a7358'),
      fogNight: new THREE.Color('#192133'),
      // weather fog modifiers
      fogOvercast: new THREE.Color('#c2cbd2'),
      fogStorm: new THREE.Color('#3b4149'),
      fogSnow: new THREE.Color('#d7dee4'),
      // precipitation
      rain: new THREE.Color('#c6d2e6'),
      snow: new THREE.Color('#ffffff'),
      flash: new THREE.Color('#eaf1ff'),
    }),
    [],
  )
  // Smoothed weather scalars + lightning envelope (mutated in place, never re-allocated).
  const sm = useRef({ overcast: 0, fog: 0, rain: 0, snow: 0, storm: 0, flash: 0, flashTimer: 4 }).current

  // GPU-cheap precipitation field: one preallocated THREE.Points buffer recycled every frame.
  const precip = useMemo(() => {
    const COUNT = 1500
    const XZ = 55 // horizontal half-extent of the field that follows the camera
    const TOP = 60
    const BOTTOM = 34 // vertical span TOP+BOTTOM ~= 94 units around the camera
    const pos = new Float32Array(COUNT * 3)
    const vel = new Float32Array(COUNT) // per-particle fall-speed multiplier
    const ph = new Float32Array(COUNT) // per-particle drift phase (snow sway)
    let s = 1337
    const rnd = () => {
      s = (s * 1664525 + 1013904223) & 0xffffffff
      return (s >>> 0) / 4294967296
    }
    for (let i = 0; i < COUNT; i++) {
      pos[i * 3] = (rnd() * 2 - 1) * XZ
      pos[i * 3 + 1] = rnd() * (TOP + BOTTOM) - BOTTOM
      pos[i * 3 + 2] = (rnd() * 2 - 1) * XZ
      vel[i] = 0.8 + rnd() * 0.45
      ph[i] = rnd() * Math.PI * 2
    }
    const geo = new THREE.BufferGeometry()
    geo.setAttribute('position', new THREE.BufferAttribute(pos, 3))
    const mat = new THREE.PointsMaterial({
      color: new THREE.Color('#c6d2e6'),
      size: 0.6,
      sizeAttenuation: true,
      transparent: true,
      opacity: 0,
      depthWrite: false,
      fog: true,
    })
    const points = new THREE.Points(geo, mat)
    points.frustumCulled = false
    points.visible = false
    points.renderOrder = 2
    return { COUNT, XZ, TOP, BOTTOM, pos, vel, ph, geo, mat, points }
  }, [])

  const clouds = useMemo(() => {
    let seed = 404
    const rnd = () => {
      seed = (seed * 1664525 + 1013904223) & 0xffffffff
      return (seed >>> 0) / 4294967296
    }
    const visibleAnchors = [
      { x: -520, y: 185, z: -780 },
      { x: 420, y: 215, z: -1080 },
      { x: -860, y: 235, z: 360 },
      { x: 760, y: 205, z: 560 },
      { x: -120, y: 255, z: -1340 },
      { x: 1160, y: 265, z: -340 },
    ]
    return Array.from({ length: 18 }, (_, i) => {
      const anchor = visibleAnchors[i]
      const width = anchor ? 68 + rnd() * 96 : 80 + rnd() * 155
      const depth = anchor ? 38 + rnd() * 72 : 42 + rnd() * 115
      const height = anchor ? 9 + rnd() * 15 : 12 + rnd() * 23
      const opacity = anchor ? 0.34 + rnd() * 0.2 : 0.2 + rnd() * 0.26
      const puffCount = 7 + Math.floor(rnd() * 6)
      const puffs = Array.from({ length: puffCount }, (_, puffIndex) => {
        const angle = rnd() * Math.PI * 2
        const spread = Math.sqrt(rnd())
        const centerBias = puffIndex < 2 ? 0.32 : 1
        return {
          x: Math.cos(angle) * width * 0.36 * spread * centerBias,
          y: (rnd() - 0.28) * height * 0.72,
          z: Math.sin(angle) * depth * 0.42 * spread * centerBias,
          sx: width * (0.2 + rnd() * 0.25),
          sy: height * (0.42 + rnd() * 0.38),
          sz: depth * (0.24 + rnd() * 0.28),
          shade: rnd() > 0.58 ? '#f8fbff' : '#edf4fa',
          opacity: opacity * (0.72 + rnd() * 0.4),
        }
      })
      puffs.push({
        x: 0,
        y: -height * 0.34,
        z: 0,
        sx: width * 0.58,
        sy: height * 0.18,
        sz: depth * 0.52,
        shade: '#dfe8f0',
        opacity: opacity * 0.54,
      })
      return {
        x: anchor?.x ?? (rnd() - 0.5) * 3400,
        y: anchor?.y ?? (250 + rnd() * 235),
        z: anchor?.z ?? (rnd() - 0.5) * 3400,
        speed: 0.35 + rnd() * 1.1,
        phase: i * 0.51,
        opacity,
        width,
        depth,
        height,
        puffs,
      }
    })
  }, [])

  const cloudRefs = useRef([])
  const cloudTexture = useMemo(() => makeProceduralTexture('cloud-vapor', { size: 128, seed: 909, repeatX: 1.4, repeatY: 1 }), [])

  useEffect(() => {
    exposeTextureCatalog()
    if (typeof window !== 'undefined' && import.meta.env.DEV) {
      window.__REALCITY_CLOUDS__ = {
        system: 'layered-procedural-puffs',
        count: clouds.length,
        puffCount: clouds.reduce((sum, cloud) => sum + cloud.puffs.length, 0),
        averagePuffs: clouds.reduce((sum, cloud) => sum + cloud.puffs.length, 0) / clouds.length,
        maxVerticalAspect: Math.max(...clouds.map(cloud => Number((cloud.height / Math.max(1, cloud.width)).toFixed(3)))),
        hasFlattenedUndersides: clouds.every(cloud => cloud.puffs.some(puff => puff.sy < cloud.height * 0.25 && puff.y < 0)),
        textured: !!cloudTexture,
      }
    }
  }, [clouds, cloudTexture])

  // Dispose the precipitation buffers when Atmosphere unmounts.
  useEffect(() => {
    const P = precip
    return () => {
      P.geo.dispose()
      P.mat.dispose()
    }
  }, [precip])

  useFrame((state, delta) => {
    const dt = Math.min(delta, 0.05) // clamp so a stalled tab does not jump the sim
    const { timeMinutes, weather } = useCityStore.getState()
    const systems = readSystems()
    const clock = systems?.clock // { hour, minute, phase, sunAngle } — may be absent at boot
    const wx = systems?.weather // { state, intensity, wet } — may be absent at boot

    // --- resolve sun direction: engine clock preferred, static store fallback ---
    let angle
    let engineDriven = false
    if (clock) {
      if (Number.isFinite(clock.sunAngle)) {
        angle = clock.sunAngle
        engineDriven = true
      } else if (Number.isFinite(clock.hour)) {
        angle = ((clock.hour + (clock.minute || 0) / 60 - 6) / 12) * Math.PI
        engineDriven = true
      }
    }
    if (!engineDriven) angle = ((timeMinutes / 60 - 6) / 12) * Math.PI
    tmp.sun.set(-Math.cos(angle), Math.sin(angle), 0.42).normalize()
    sunRef.current.copy(tmp.sun)
    const sun = sunRef.current

    const day = Math.max(0, sun.y)
    const night = sun.y < -0.08
    const twilight = Math.max(0, 1 - Math.abs(sun.y) * 4.5)

    // Throttle tick follows whichever clock is actually advancing.
    const clockMinutes = engineDriven && Number.isFinite(clock.hour) ? clock.hour * 60 + (clock.minute || 0) : timeMinutes
    const tick = Math.floor(clockMinutes * 1.2)

    // Phase used for colour tinting (engine phase authoritative, else derived from elevation).
    let phaseName = clock?.phase
    if (phaseName !== 'dawn' && phaseName !== 'day' && phaseName !== 'dusk' && phaseName !== 'night') {
      phaseName = night ? 'night' : twilight > 0.35 ? (sun.x < 0 ? 'dawn' : 'dusk') : 'day'
    }
    // Legacy store report phase — contract unchanged for existing consumers of setSky.
    const reportPhase = night ? 'night' : twilight > 0.35 ? (sun.y > 0 ? 'golden-hour' : 'dawn') : 'day'

    // --- weather targets from engine (all 0 when weather system is absent -> static look) ---
    const wState = wx && typeof wx.state === 'string' ? wx.state : 'clear'
    const wInt = clamp01(wx?.intensity)
    const wet = clamp01(wx?.wet)
    const storeClouds = clamp01(weather?.clouds)

    const tRain = wState === 'rain' || wState === 'storm' ? Math.max(0.35, wInt) : 0
    const tSnow = wState === 'snow' ? Math.max(0.3, wInt) : 0
    const tStorm = wState === 'storm' ? Math.max(0.55, wInt) : 0
    let tOver =
      wState === 'cloudy' ? 0.45 + 0.5 * wInt
        : wState === 'storm' ? 0.9
        : wState === 'fog' ? 0.7
        : wState === 'rain' ? 0.55
        : wState === 'snow' ? 0.45
        : 0
    tOver = clamp01(tOver + storeClouds * 0.15)
    let tFog =
      wState === 'fog' ? 0.5 + 0.5 * wInt
        : wState === 'storm' ? 0.35 + 0.35 * wInt
        : wState === 'rain' ? 0.25 * wInt + 0.08
        : wState === 'snow' ? 0.2 + 0.15 * wInt
        : 0
    tFog = clamp01(tFog + wet * 0.15)

    sm.rain = damp(sm.rain, tRain, 2.5, dt)
    sm.snow = damp(sm.snow, tSnow, 2.0, dt)
    sm.storm = damp(sm.storm, tStorm, 2.5, dt)
    sm.overcast = damp(sm.overcast, tOver, 1.6, dt)
    sm.fog = damp(sm.fog, tFog, 1.6, dt)

    // --- lightning envelope (storm only, subtle) ---
    if (sm.storm > 0.35) {
      sm.flashTimer -= dt
      if (sm.flashTimer <= 0) {
        sm.flash = 1
        sm.flashTimer = 3.5 + Math.random() * 6.5
      }
    }
    sm.flash = Math.max(0, sm.flash - dt * 3.2)
    const flash = sm.flash * Math.min(1, sm.storm * 1.4)

    const reflection = (night ? 0.35 : 0.72 + day * 0.72 + twilight * 0.25) + wet * 0.2

    // Wind (from store) reused by both precipitation slant and cloud drift.
    const windAngle = weather?.windAngle || 0
    const windSpeed = weather?.windSpeed || 0
    tmp.wind.set(Math.cos(windAngle), Math.sin(windAngle))

    // --- directional sun light: position, intensity, phase tint, lightning ---
    if (dirRef.current) {
      dirRef.current.position.set(sun.x * 300, sun.y * 300, sun.z * 300)
      const baseI = (night ? 0.03 : 0.38 + day * 3.4 + twilight * 0.8) * (1 - sm.overcast * 0.55)
      dirRef.current.intensity = baseI + flash * 2.4
      tmp.tint.copy(
        phaseName === 'dawn'
          ? palette.sunDawn
          : phaseName === 'dusk'
          ? palette.sunDusk
          : phaseName === 'night'
          ? palette.sunNight
          : palette.sunDay,
      )
      dampColor(dirRef.current.color, tmp.tint, 3.2, dt)
      if (flash > 0) dirRef.current.color.lerp(palette.flash, Math.min(0.6, flash * 0.6))
    }
    if (fillRef.current) {
      fillRef.current.position.set(-sun.x * 220, Math.max(70, sun.y * 120 + 80), -sun.z * 220)
      fillRef.current.intensity = (night ? 0.1 : 0.24 + twilight * 0.4) + flash * 0.6
    }
    // Ambient / hemisphere dim at night but floored so the city stays readable.
    if (ambientRef.current) {
      ambientRef.current.intensity = (night ? 0.25 : 0.62 + day * 0.46) * (1 - sm.storm * 0.12) + flash * 0.5
    }
    if (hemiRef.current) {
      hemiRef.current.intensity = (night ? 0.3 : 0.98 + day * 0.54) * (1 - sm.overcast * 0.18)
    }

    // --- fog: phase colour + weather tint, density ramps with fog/overcast ---
    if (fogRef.current) {
      tmp.fog.copy(
        phaseName === 'night'
          ? palette.fogNight
          : phaseName === 'dawn'
          ? palette.fogDawn
          : phaseName === 'dusk'
          ? palette.fogDusk
          : palette.fogDay,
      )
      if (wState === 'snow') tmp.fog.lerp(palette.fogSnow, Math.min(0.6, sm.snow))
      if (sm.overcast > 0) tmp.fog.lerp(palette.fogOvercast, Math.min(0.65, sm.overcast))
      if (sm.storm > 0) tmp.fog.lerp(palette.fogStorm, Math.min(0.6, sm.storm))
      dampColor(fogRef.current.color, tmp.fog, 2.2, dt)
      const haze = clamp01(sm.fog + storeClouds * 0.35)
      fogRef.current.near = lerp(520, 95, haze)
      fogRef.current.far = lerp(2240, 620, haze)
    }

    if (sunDiscRef.current) {
      sunDiscRef.current.visible = sun.y > -0.12
      sunDiscRef.current.position.set(sun.x * 1220, sun.y * 1220 + 120, sun.z * 1220)
      sunDiscRef.current.scale.setScalar(1 + twilight * 0.45)
    }
    if (moonDiscRef.current) {
      moonDiscRef.current.visible = sun.y < 0.22
      moonDiscRef.current.position.set(-sun.x * 1180, Math.max(120, -sun.y * 900 + 120), -sun.z * 1180)
    }

    // --- throttled sky-dome update + store report (one batched re-render per tick) ---
    if (tick !== skyTick.current) {
      skyTick.current = tick
      setSkySun(sun.toArray())
      setSkyMood({
        turbidity: 2.9 + sm.overcast * 6.6,
        rayleigh: Math.max(0.3, 1.25 - sm.overcast * 0.9),
        mie: 0.0045 + sm.overcast * 0.02,
      })
      useCityStore.getState().setSky({
        phase: reportPhase,
        sunElevation: Number(sun.y.toFixed(3)),
        sunlight: Number((night ? 0.03 : 0.2 + day).toFixed(3)),
        reflection: Number(reflection.toFixed(3)),
      })
      if (import.meta.env.DEV && typeof window !== 'undefined') {
        window.__REALCITY_WEATHER_FX__ = {
          clockSource: engineDriven ? 'engine-clock' : 'store-fallback',
          weatherSource: wx ? 'engine-weather' : 'fallback',
          phase: phaseName,
          weatherState: wState,
          rain: Number(sm.rain.toFixed(2)),
          snow: Number(sm.snow.toFixed(2)),
          storm: Number(sm.storm.toFixed(2)),
          fog: Number(sm.fog.toFixed(2)),
          overcast: Number(sm.overcast.toFixed(2)),
          precipActive: precip.points.visible,
        }
      }
    }

    // --- precipitation particle field (rain / storm / snow) ---
    const rainAmt = sm.rain
    const snowAmt = sm.snow
    const active = Math.max(rainAmt, snowAmt)
    const P = precip
    if (active < 0.02) {
      if (P.points.visible) {
        P.points.visible = false
        P.mat.opacity = 0
      }
    } else {
      P.points.visible = true
      P.points.position.copy(state.camera.position) // field glued to the camera (local offsets in buffer)
      const isRain = rainAmt >= snowAmt
      const intensity = active
      const targetSize = isRain ? 0.55 : 1.5
      const targetOpacity = (isRain ? 0.55 : 0.85) * Math.min(1, intensity * 1.3)
      P.mat.size = damp(P.mat.size, targetSize, 6, dt)
      P.mat.opacity = damp(P.mat.opacity, targetOpacity, 6, dt)
      dampColor(P.mat.color, isRain ? palette.rain : palette.snow, 5, dt)

      // count scales with intensity; storm is denser
      const dens = isRain ? (0.35 + 0.65 * intensity) * (sm.storm > 0.3 ? 1 : 0.82) : 0.3 + 0.55 * intensity
      const drawCount = Math.max(1, Math.min(P.COUNT, Math.floor(P.COUNT * dens)))
      P.geo.setDrawRange(0, drawCount)

      // fall speed scales with intensity; snow drifts slowly, storm falls harder
      const fall = isRain ? (46 + 46 * intensity) * (sm.storm > 0.3 ? 1.15 : 1) : 5.5 + 7 * intensity
      const sway = isRain ? 0 : 4.2
      const windAmt = (isRain ? 6 : 2.4) * (0.4 + windSpeed * 0.08)
      const t = state.clock.elapsedTime
      const arr = P.pos
      const XZ = P.XZ
      const TOP = P.TOP
      const BOTTOM = P.BOTTOM
      const span = TOP + BOTTOM
      for (let i = 0; i < drawCount; i++) {
        const b = i * 3
        let x = arr[b]
        let y = arr[b + 1]
        let z = arr[b + 2]
        y -= fall * P.vel[i] * dt
        x += (tmp.wind.x * windAmt + (isRain ? 0 : Math.sin(t * 0.6 + P.ph[i]) * sway)) * dt
        z += (tmp.wind.y * windAmt + (isRain ? 0 : Math.cos(t * 0.5 + P.ph[i]) * sway)) * dt
        if (y < -BOTTOM) {
          // recycle to the top with a fresh horizontal position
          y += span
          x = (Math.random() * 2 - 1) * XZ
          z = (Math.random() * 2 - 1) * XZ
        }
        if (x > XZ) x -= 2 * XZ
        else if (x < -XZ) x += 2 * XZ
        if (z > XZ) z -= 2 * XZ
        else if (z < -XZ) z += 2 * XZ
        arr[b] = x
        arr[b + 1] = y
        arr[b + 2] = z
      }
      P.geo.attributes.position.needsUpdate = true
    }

    // --- clouds drift (existing behaviour, wind reused, no allocation) ---
    cloudRefs.current.forEach((cloud, i) => {
      if (!cloud) return
      const c = clouds[i]
      cloud.position.x += tmp.wind.x * windSpeed * c.speed * dt
      cloud.position.z += tmp.wind.y * windSpeed * c.speed * dt
      cloud.position.y = c.y + Math.sin(state.clock.elapsedTime * 0.08 + c.phase) * 3.4
      if (cloud.position.x > 1800) cloud.position.x = -1800
      if (cloud.position.x < -1800) cloud.position.x = 1800
      if (cloud.position.z > 1800) cloud.position.z = -1800
      if (cloud.position.z < -1800) cloud.position.z = 1800
    })
  })

  return (
    <>
      <Sky sunPosition={skySun} distance={4700} turbidity={skyMood.turbidity} rayleigh={skyMood.rayleigh} mieCoefficient={skyMood.mie} mieDirectionalG={0.84} />
      <Stars radius={2300} depth={90} count={2600} factor={4} fade speed={0.18} />
      <directionalLight
        ref={dirRef}
        castShadow
        position={[220, 260, 80]}
        intensity={4}
        shadow-mapSize-width={2048}
        shadow-mapSize-height={2048}
        shadow-camera-left={-760}
        shadow-camera-right={760}
        shadow-camera-top={760}
        shadow-camera-bottom={-760}
        shadow-camera-near={1}
        shadow-camera-far={2800}
        shadow-bias={-0.00012}
        shadow-normalBias={0.05}
        shadow-radius={3}
      />
      <directionalLight ref={fillRef} position={[-140, 150, -220]} intensity={0.28} color="#d7e9ff" />
      <ambientLight ref={ambientRef} color="#c6d2dc" intensity={0.68} />
      <hemisphereLight ref={hemiRef} skyColor="#a9d0f4" groundColor="#777164" intensity={1.02} />
      <fog ref={fogRef} attach="fog" args={['#6f8496', 520, 2240]} />
      <Environment preset="city" background={false} />
      <primitive object={precip.points} dispose={null} />
      <mesh ref={sunDiscRef} position={[900, 650, 300]} renderOrder={-1}>
        <sphereGeometry args={[22, 24, 16]} />
        <meshBasicMaterial color="#fff2b7" toneMapped={false} />
      </mesh>
      <mesh ref={moonDiscRef} position={[-900, 450, -300]} renderOrder={-1}>
        <sphereGeometry args={[13, 18, 12]} />
        <meshBasicMaterial color="#d9e5ff" toneMapped={false} />
      </mesh>
      {clouds.map((cloud, i) => (
        <group
          key={i}
          ref={node => { cloudRefs.current[i] = node }}
          position={[cloud.x, cloud.y, cloud.z]}
          rotation={[0, cloud.phase * 0.34, 0]}
          renderOrder={-2}
        >
          {cloud.puffs.map((puff, puffIndex) => (
            <mesh key={puffIndex} position={[puff.x, puff.y, puff.z]} scale={[puff.sx, puff.sy, puff.sz]} frustumCulled={false}>
              <sphereGeometry args={[1, 18, 12]} />
              <meshStandardMaterial
                map={cloudTexture}
                color={puff.shade}
                transparent
                opacity={Math.min(0.7, puff.opacity)}
                roughness={1}
                metalness={0}
                depthWrite={false}
              />
            </mesh>
          ))}
        </group>
      ))}
    </>
  )
}
