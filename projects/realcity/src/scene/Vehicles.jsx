/* Vehicles — the parked street fleet that lines the city's kerbs.
 *
 * Context (2026-07-21): the live *moving* agent-driven traffic (city.cars, 120 vehicles) is
 * rendered by the `Traffic` component inside Actors.jsx and is still mounted — so it is NOT
 * re-rendered here (that would double-render the same fleet). What went missing when CityScape
 * replaced CityMeshes + UrbanDetails is the *parked* fleet that used to live in
 * UrbanDetails.ParkedCars (that file is now unmounted). This component restores those kerb-side
 * cars: instanced bodies + cabins + wheels, varied sedan / hatch / suv / van / truck silhouettes
 * and colours, with head- and tail-light lenses that glow at night off the engine clock phase.
 *
 * It consumes the SAME engine data (city.roads + terrainHeight) so the parked cars sit exactly on
 * the CityScape road surface and never mutate behaviour. Everything is instanced and written once
 * in a layout effect; the only per-frame work is easing the light-lens emissive by the day/night
 * clock, so it is effectively free.
 */
import { useLayoutEffect, useMemo, useRef } from 'react'
import { useFrame } from '@react-three/fiber'
import * as THREE from 'three'
import { terrainHeight } from '../engine/cityEngine'
import { useCityStore } from '../engine/cityStore'

/* ---- shared scratch (no per-frame allocation) ---- */
const M4 = new THREE.Matrix4()
const Q = new THREE.Quaternion()
const V = new THREE.Vector3()
const S = new THREE.Vector3()
const COL = new THREE.Color()
const YUP = new THREE.Vector3(0, 1, 0)

function setInst(mesh, i, x, y, z, sx, sy, sz, rotY = 0) {
  Q.setFromAxisAngle(YUP, rotY)
  V.set(x, y, z)
  S.set(sx, sy, sz)
  M4.compose(V, Q, S)
  mesh.setMatrixAt(i, M4)
}

/* deterministic hash so a given kerb slot always gets the same car */
function hash(n) {
  let h = (n | 0) * 374761393 + 1
  h = (h ^ (h >>> 13)) * 1274126177
  return ((h ^ (h >>> 16)) >>> 0) / 4294967295
}

/* parked silhouettes — width, height, length, cabin length, cabin height, roof drop */
const BODY_STYLES = [
  { k: 'sedan', w: 2.02, h: 0.70, l: 4.35, cl: 1.9, ch: 0.56 },
  { k: 'sedan', w: 2.02, h: 0.70, l: 4.35, cl: 1.9, ch: 0.56 },
  { k: 'hatch', w: 1.92, h: 0.72, l: 3.85, cl: 1.72, ch: 0.60 },
  { k: 'suv', w: 2.16, h: 0.90, l: 4.55, cl: 2.05, ch: 0.72 },
  { k: 'van', w: 2.20, h: 1.00, l: 4.9, cl: 2.7, ch: 0.86 },
  { k: 'truck', w: 2.24, h: 0.86, l: 5.2, cl: 1.5, ch: 0.66 },
]
const PAINT = [
  '#e5504f', '#f2f4f6', '#1f2733', '#3b82f6', '#16a34a', '#f59e0b',
  '#7c3aed', '#94a3b8', '#0f766e', '#b45309', '#dc2626', '#334155',
]

/* 0 = full day, 1 = full night — dusk ramps in ~18-20h, dawn out ~5-6.5h */
function nightFactor(minutes) {
  const h = (Number(minutes) || 0) / 60
  if (h >= 6.5 && h <= 18) return 0
  if (h > 18 && h < 20) return (h - 18) / 2
  if (h >= 20 || h < 5) return 1
  if (h >= 5 && h < 6.5) return 1 - (h - 5) / 1.5
  return 0
}

export default function Vehicles({ city }) {
  const bodyRef = useRef()
  const cabinRef = useRef()
  const wheelRef = useRef()
  const headRef = useRef()
  const tailRef = useRef()
  const headMat = useRef()
  const tailMat = useRef()
  const night = useRef(-1)

  // Build the parked fleet from the road graph: pack cars along the outer kerb of the main
  // roads, skipping road ends (junction boxes) so nothing parks inside an intersection.
  const cars = useMemo(() => {
    const roads = (city?.roads || []).filter(r => r && Number.isFinite(r.from) && Number.isFinite(r.to))
    const items = []
    const MAX = 168
    // longer / main roads first so the densest streets fill before the cap
    const ordered = [...roads].sort((a, b) => (b.to - b.from) - (a.to - a.from))
    for (let ri = 0; ri < ordered.length && items.length < MAX; ri += 1) {
      const road = ordered[ri]
      const span = road.to - road.from
      if (span < 120) continue
      const halfW = (road.width || 12) * 0.5
      // both kerbs on wide/main roads, one kerb on the rest
      const sides = road.main && halfW > 6 ? [-1, 1] : [ri % 2 === 0 ? -1 : 1]
      for (const side of sides) {
        const offset = (halfW - 1.6) * side
        const gap = 8.5 + hash(ri * 7 + (side + 2)) * 5.5
        let p = road.from + 26 + hash(ri * 13) * 12
        while (p < road.to - 26 && items.length < MAX) {
          const seed = Math.abs(Math.round(p * 3.1 + ri * 91 + (side + 2) * 17))
          // leave the occasional empty slot so the row is not a solid wall of cars
          if (hash(seed) > 0.16) {
            const style = BODY_STYLES[Math.floor(hash(seed + 1) * BODY_STYLES.length)]
            const jitter = (hash(seed + 2) - 0.5) * 0.5
            if (road.axis === 'x') {
              items.push({ x: p, z: road.z + offset + jitter, yaw: Math.PI / 2, style, seed })
            } else {
              items.push({ x: road.x + offset + jitter, z: p, yaw: 0, style, seed })
            }
          }
          // parked bumper-to-bumper spacing: average car length (~4.6) + a small gap
          p += 4.6 + gap
        }
      }
    }
    return items
  }, [city])

  useLayoutEffect(() => {
    const body = bodyRef.current
    const cabin = cabinRef.current
    const wheel = wheelRef.current
    const head = headRef.current
    const tail = tailRef.current
    if (!body || !cabin || !wheel || !head || !tail) return
    cars.forEach((car, i) => {
      const s = car.style
      const gy = terrainHeight(car.x, car.z)
      const bodyY = gy + 0.5
      const cy = Math.cos(car.yaw)
      const sy = Math.sin(car.yaw)
      // forward (fx,fz) and right (rx,rz) unit vectors in the ground plane for this car heading
      const fx = sy
      const fz = cy
      const rx = cy
      const rz = -sy

      setInst(body, i, car.x, bodyY, car.z, s.w, s.h, s.l, car.yaw)
      const cabZ = s.k === 'truck' ? s.l * 0.16 : -s.l * 0.05
      setInst(cabin, i, car.x + fx * cabZ, bodyY + s.h * 0.62 + s.ch * 0.5, car.z + fz * cabZ,
        s.w * 0.86, s.ch, s.cl, car.yaw)
      body.setColorAt(i, COL.set(PAINT[Math.floor(hash(car.seed + 5) * PAINT.length)]))
      cabin.setColorAt(i, COL.set('#0d1420'))

      const wx = s.w * 0.42
      const wz = s.l * 0.31
      const wheelY = gy + 0.32
      const wheels = [
        [-wx, -wz], [wx, -wz], [-wx, wz], [wx, wz],
      ]
      wheels.forEach(([lx, lz], w) => {
        const px = car.x + rx * lx + fx * lz
        const pz = car.z + rz * lx + fz * lz
        // cylinder axis is Y; tip it 90deg about the car's forward axis so the wheel disc
        // stands upright and its axle runs left-right. Height (0.2) is the tyre thickness.
        Q.setFromAxisAngle(V.set(fx, 0, fz), Math.PI / 2)
        V.set(px, wheelY, pz)
        S.set(0.33, 0.2, 0.33)
        M4.compose(V, Q, S)
        wheel.setMatrixAt(i * 4 + w, M4)
      })

      // head / tail light lenses (two each), placed at the car's nose and tail
      const noseZ = s.l * 0.5
      const lampX = s.w * 0.3
      const headYpos = gy + 0.55
      ;[-1, 1].forEach((sideL, k) => {
        const hx = car.x + rx * (lampX * sideL) + fx * noseZ
        const hz = car.z + rz * (lampX * sideL) + fz * noseZ
        setInst(head, i * 2 + k, hx, headYpos, hz, 0.22, 0.14, 0.1, car.yaw)
        const tx = car.x + rx * (lampX * sideL) - fx * noseZ
        const tz = car.z + rz * (lampX * sideL) - fz * noseZ
        setInst(tail, i * 2 + k, tx, headYpos, tz, 0.22, 0.13, 0.1, car.yaw)
      })
    })
    body.instanceMatrix.needsUpdate = true
    cabin.instanceMatrix.needsUpdate = true
    wheel.instanceMatrix.needsUpdate = true
    head.instanceMatrix.needsUpdate = true
    tail.instanceMatrix.needsUpdate = true
    if (body.instanceColor) body.instanceColor.needsUpdate = true
    if (cabin.instanceColor) cabin.instanceColor.needsUpdate = true
  }, [cars])

  // Only per-frame work: ease the lamp lenses from inert (day) to a soft glow (night).
  useFrame(() => {
    if (!headMat.current || !tailMat.current) return
    const nf = nightFactor(useCityStore.getState().timeMinutes)
    if (Math.abs(nf - night.current) < 0.01) return
    night.current = nf
    headMat.current.emissiveIntensity = 0.08 + nf * 1.15
    tailMat.current.emissiveIntensity = 0.05 + nf * 0.75
  })

  const count = cars.length
  if (!count) return null
  return (
    <>
      <instancedMesh ref={bodyRef} args={[undefined, undefined, count]} castShadow receiveShadow frustumCulled={false}>
        <boxGeometry args={[1, 1, 1]} />
        <meshStandardMaterial color="#ffffff" vertexColors roughness={0.36} metalness={0.42} />
      </instancedMesh>
      <instancedMesh ref={cabinRef} args={[undefined, undefined, count]} castShadow frustumCulled={false}>
        <boxGeometry args={[1, 1, 1]} />
        <meshStandardMaterial color="#ffffff" vertexColors roughness={0.1} metalness={0.32} />
      </instancedMesh>
      <instancedMesh ref={wheelRef} args={[undefined, undefined, count * 4]} castShadow frustumCulled={false}>
        <cylinderGeometry args={[1, 1, 1, 16]} />
        <meshStandardMaterial color="#0a0c10" roughness={0.72} metalness={0.14} />
      </instancedMesh>
      <instancedMesh ref={headRef} args={[undefined, undefined, count * 2]} frustumCulled={false}>
        <boxGeometry args={[1, 1, 1]} />
        <meshStandardMaterial ref={headMat} color="#fff6d8" emissive="#ffe08a" emissiveIntensity={0.08} roughness={0.3} />
      </instancedMesh>
      <instancedMesh ref={tailRef} args={[undefined, undefined, count * 2]} frustumCulled={false}>
        <boxGeometry args={[1, 1, 1]} />
        <meshStandardMaterial ref={tailMat} color="#b3201d" emissive="#ff1d18" emissiveIntensity={0.05} roughness={0.34} />
      </instancedMesh>
    </>
  )
}
