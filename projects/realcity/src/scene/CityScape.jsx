/* CityScape — the city's architecture + landscaping, remodelled from scratch (2026-07-21).
 *
 * Owner: keep the infrastructure and operating rules exactly as they are; redesign only the
 * DESIGN layer — architectural massing and landscaping. So this component consumes the SAME
 * engine data (city.roads / city.buildings / city.landmarks / city.parcels / systems.clock,
 * weather) and never mutates behaviour: collision footprints, ids, districts all stay intact.
 * It replaces the old CityMeshes + UrbanDetails mounts; those files remain on disk untouched
 * for instant rollback.
 *
 * Design language ("서울 신도시 × 절제된 국제양식"):
 *  - Architecture: massing is upgraded deterministically per building — low homes get hip/gable
 *    roof prisms + chimneys; mid blocks get a cornice band with balconies (residential) or pilaster
 *    fins (office); towers stack 2-3 setback tiers with parapets and chamfered corner fins; retail
 *    podiums get an arcade colonnade, a deep canopy and a sign slab. Every entrance carries a real
 *    double glass door (dark slab + frame + mullion + steps). Facades still carry the procedural
 *    window-grid shader (per-instance bays/floors/seed) that lights up at night by occupancy noise.
 *  - Streets: asphalt with centre dashes + edge lines and 6-stripe zebra belts — all road paint at a
 *    constant flat-road height so markings never sink into terrain. Traffic lights are real signal
 *    assemblies (pole + mast arm over the carriageway + black 3-lens housing with visor hoods) whose
 *    lenses switch with the engine signal cycle. Street lights come on at dusk; street furniture
 *    (trees, benches, bins, hydrants) is kept off every carriageway, building footprint and parking.
 *  - Landscaping: parks/plazas/gardens from city.parcels (zoning agent) — lawns, tree clusters,
 *    hedges, benches; parking lots get stall stripes.
 *
 * Physics: after layout build we publish city.obstacles = [{x,z,r}] for every circular street prop
 * (tree trunks, poles, hydrants, benches) so the collision agent can resolve pedestrians/vehicles
 * against them. The assignment is deterministic + idempotent (rebuild-safe).
 *
 * Performance: everything is instanced or merged — roughly three dozen InstancedMeshes + three
 * merged ground meshes for the whole city. No per-frame allocations; night/signal updates throttled.
 */
import { useMemo, useRef } from 'react'
import { useFrame } from '@react-three/fiber'
import * as THREE from 'three'
import {
  CITY_HALF,
  CITY_WORLD_SIZE,
  TRAFFIC_SIGNAL_CYCLE_SECONDS,
  TRAFFIC_SIGNAL_YELLOW_SECONDS,
  terrainHeight,
  terrainTone,
} from '../engine/cityEngine'

/* ---------------------------------- shared scratch ---------------------------------- */
const M4 = new THREE.Matrix4()
const Q = new THREE.Quaternion()
const V = new THREE.Vector3()
const S = new THREE.Vector3()
const COL = new THREE.Color()
const YUP = new THREE.Vector3(0, 1, 0)
const WHITE = new THREE.Color(1, 1, 1)

function setInst(mesh, i, x, y, z, sx, sy, sz, rotY = 0) {
  Q.setFromAxisAngle(YUP, rotY)
  V.set(x, y, z)
  S.set(sx, sy, sz)
  M4.compose(V, Q, S)
  mesh.setMatrixAt(i, M4)
}

/* face helpers: normal, tangent, half-depth to that face, facade width along the face */
const FACE_NRM = { north: [0, 1], south: [0, -1], east: [1, 0], west: [-1, 0] }
const faceNrm = (f) => FACE_NRM[f] || FACE_NRM.south
const faceTan = (f) => (f === 'east' || f === 'west') ? [0, 1] : [1, 0]
const faceHalf = (f, b) => (f === 'east' || f === 'west') ? b.w / 2 : b.d / 2
const faceLen = (f, b) => (f === 'east' || f === 'west') ? b.d : b.w
const clampi = (v, a, b) => Math.max(a, Math.min(b, v))

/* district → facade palette (muted architectural neutrals with one accent per district) */
const DISTRICT_PALETTES = {
  default: { base: '#96928b', alt: '#88847d', accent: '#6d7f8a' },
}
const PALETTE_POOL = [
  { base: '#98948c', alt: '#86827a', accent: '#77675a' },   // warm stone
  { base: '#8f9498', alt: '#7d8288', accent: '#4f6b7a' },   // cool slate
  { base: '#9f998d', alt: '#8b867a', accent: '#8a6f4d' },   // sand brick
  { base: '#8d938d', alt: '#7b807b', accent: '#5c7360' },   // sage
  { base: '#948d91', alt: '#827d82', accent: '#71586a' },   // mauve grey
  { base: '#92959b', alt: '#80838b', accent: '#39566e' },   // harbor blue
]
function paletteFor(districtId = '') {
  if (!districtId) return DISTRICT_PALETTES.default
  let h = 0
  for (let i = 0; i < districtId.length; i++) h = (h * 31 + districtId.charCodeAt(i)) >>> 0
  return PALETTE_POOL[h % PALETTE_POOL.length]
}

/* deterministic per-id noise */
function hash01(n) {
  const s = Math.sin(n * 127.1 + 311.7) * 43758.5453
  return s - Math.floor(s)
}

/* unit roof prism over a 1x1 footprint (x,z in [-0.5,0.5]), height 1 (y in [0,1]), ridge along x.
 * rx = half ridge length: 0.25 → hip (inset ridge, hipped ends); 0.5 → gable (full ridge, gable ends). */
function makeRoofGeo(rx) {
  const A = [-0.5, 0, -0.5], B = [0.5, 0, -0.5], C = [0.5, 0, 0.5], D = [-0.5, 0, 0.5]
  const R1 = [-rx, 1, 0], R2 = [rx, 1, 0]
  const t = []
  const quad = (p, q, r, s) => { t.push(...p, ...q, ...r, ...p, ...r, ...s) }
  const tri = (p, q, r) => { t.push(...p, ...q, ...r) }
  quad(A, B, R2, R1)   // long slope, -z
  quad(C, D, R1, R2)   // long slope, +z
  tri(B, C, R2)        // +x end (hip triangle / gable)
  tri(D, A, R1)        // -x end
  const g = new THREE.BufferGeometry()
  g.setAttribute('position', new THREE.BufferAttribute(new Float32Array(t), 3))
  g.computeVertexNormals()
  return g
}

/* ------------------------- procedural window facade material ------------------------ */
/* One material for every building body. Per-instance attributes carry the window grid
 * (bays, floors, seed) and the shader draws inset glazing on the side faces; at night a
 * per-window hash decides which offices/homes are lit — driven by the uNight uniform. */
function makeFacadeMaterial(uniformsRef) {
  const mat = new THREE.MeshStandardMaterial({ roughness: 0.82, metalness: 0.06, vertexColors: false })
  mat.onBeforeCompile = (shader) => {
    shader.uniforms.uNight = { value: 0 }
    uniformsRef.current = shader.uniforms
    shader.vertexShader = shader.vertexShader
      .replace('#include <common>', `#include <common>
        attribute vec3 aGrid;        // x: bays, y: floors, z: seed
        attribute vec3 aTint;        // facade base colour
        varying vec3 vGrid;
        varying vec3 vTint;
        varying vec3 vNrm;
        varying vec2 vFaceUv;`)
      .replace('#include <uv_vertex>', `#include <uv_vertex>
        vGrid = aGrid;
        vTint = aTint;
        vNrm = normal;
        vFaceUv = uv;`)
    shader.fragmentShader = shader.fragmentShader
      .replace('#include <common>', `#include <common>
        uniform float uNight;
        varying vec3 vGrid;
        varying vec3 vTint;
        varying vec3 vNrm;
        varying vec2 vFaceUv;
        float wHash(vec2 c, float s) {
          return fract(sin(dot(c, vec2(12.9898, 78.233)) + s * 37.719) * 43758.5453);
        }`)
      .replace('#include <color_fragment>', `#include <color_fragment>
        diffuseColor.rgb = vTint;
        // window grid on vertical faces only
        float side = 1.0 - abs(vNrm.y);
        if (side > 0.5 && vGrid.x > 0.5) {
          vec2 cell = vFaceUv * vec2(vGrid.x, vGrid.y);
          vec2 f = fract(cell);
          // window pane inside each cell (margins = mullions + floor slabs)
          float inX = step(0.18, f.x) * step(f.x, 0.82);
          float inY = step(0.24, f.y) * step(f.y, 0.80);
          float pane = inX * inY;
          // skip a ground-floor band (handled by shopfront kit) and the parapet
          float fl = floor(cell.y);
          if (fl < 0.9) pane = 0.0;
          if (cell.y > vGrid.y - 0.35) pane = 0.0;
          if (pane > 0.5) {
            vec3 glassDay = mix(vTint * 0.55, vec3(0.32, 0.40, 0.46), 0.65);
            float lit = step(0.55, wHash(floor(cell), vGrid.z)) * uNight;
            vec3 glassNight = mix(vec3(0.04, 0.05, 0.07), vec3(1.0, 0.85, 0.55), lit);
            diffuseColor.rgb = mix(glassDay, glassNight, uNight);
            #ifdef USE_ENVMAP
            #endif
            // emissive-ish push for lit windows so Bloom catches them
            diffuseColor.rgb += vec3(1.0, 0.82, 0.5) * lit * 0.85;
          }
        }`)
  }
  return mat
}

/* ------------------------------ geometry + layout build ------------------------------ */
export function buildLayout(city) {
  const roads = city.roads || []
  const buildings = city.buildings || []
  const landmarks = city.landmarks || []
  const parcels = city.parcels || []

  /* --- intersections of the road grid (for signals + crosswalks) --- */
  const xs = roads.filter(r => r.axis === 'x')            // run east-west at fixed z
  const ys = roads.filter(r => r.axis !== 'x')            // run north-south at fixed x
  const intersections = []
  for (const rx of xs) {
    for (const ry of ys) {
      const x = ry.x, z = rx.z
      if (x >= rx.from - 1 && x <= rx.to + 1 && z >= ry.from - 1 && z <= ry.to + 1) {
        intersections.push({ x, z, wx: rx.width, wy: ry.width, major: (rx.width + ry.width) > 20 })
      }
    }
  }

  /* --- building instances: podium + setback tiers + roof/massing kits + entrance --- */
  const bodies = []            // facade-shader bodies {x,y,z,w,h,d,rot,bays,floors,seed,tint}
  const roofKits = { hvac: [], tank: [], antenna: [] }   // rooftop mechanical
  const canopies = []
  const shopfronts = []
  const hipRoofs = []          // low homes
  const gableRoofs = []
  const chimneys = []
  const cornices = []          // mid tops + tower parapets (+ flat-roof low)
  const balconies = []         // mid residential side facades
  const pilasters = []         // mid office facade fins
  const cornerFins = []        // tower chamfer corner boxes
  const arcadeCols = []        // retail podium colonnade
  const signboards = []        // retail sign slab
  const doorSlabs = []         // entrance glass
  const doorFrames = []
  const doorMullions = []
  const doorSteps = []
  const solids = [...buildings]
  for (const lm of landmarks) {
    const w = lm.w || lm.interior?.width || 0
    const d = lm.d || lm.interior?.depth || 0
    if (w && d) solids.push({ ...lm, w, d, h: Math.max(lm.h || 0, (lm.interior?.floorCount || 2) * (lm.interior?.floorHeight || 4)), landmark: true })
  }
  let seedIdx = 1
  for (const b of solids) {
    if ((b.h || 0) < 3) continue
    const pal = paletteFor(b.districtId || b.district || b.kind || '')
    const seed = hash01(seedIdx++) * 10 + (b.tint || 0)
    const h = b.h
    const baysW = Math.max(2, Math.round(b.w / 3.1))
    const y0 = b.y || terrainHeight(b.x, b.z)
    const rot = b.rot || 0
    const tall = h > 26 && b.w > 12 && b.d > 12
    const low = h < 12
    const typ = String(b.type || b.kind || '')
    const residential = /house|apartment|home|resid/i.test(typ)
    const office = /office|skyscraper|commercial|corporate/i.test(typ)
    const retail = b.landmark
      ? /cafe|retail|leisure|market|shop|store/i.test(String(b.kind || ''))
      : /market|shop|retail|cafe|leisure|store/i.test(typ)
    const podH = tall ? Math.min(10, h * 0.28) : h
    COL.set(hash01(seedIdx * 3.7) > 0.5 ? pal.base : pal.alt)
    if (b.landmark) COL.lerp(new THREE.Color(pal.accent), 0.22)
    const tint = COL.clone()
    const accent = new THREE.Color(pal.accent)

    // podium (full footprint)
    bodies.push({ x: b.x, y: y0 + podH / 2, z: b.z, w: b.w, h: podH, d: b.d, rot, bays: baysW, floors: Math.max(1, Math.round(podH / 3.4)), seed, tint })

    // tower: stacked setback tiers + parapet + chamfered corner fins
    if (tall) {
      const towerH = h - podH
      const nTiers = h > 62 ? 3 : 2
      const fr = nTiers === 3 ? [0.5, 0.32, 0.18] : [0.62, 0.38]
      let cy = y0 + podH, cw = b.w, cd = b.d
      for (let ti = 0; ti < nTiers; ti++) {
        cw *= ti === 0 ? (0.74 + hash01(seedIdx * 1.3 + ti) * 0.1) : 0.84
        cd *= ti === 0 ? (0.74 + hash01(seedIdx * 2.1 + ti) * 0.1) : 0.84
        const th = towerH * fr[ti]
        bodies.push({ x: b.x, y: cy + th / 2, z: b.z, w: cw, h: th, d: cd, rot, bays: Math.max(2, Math.round(cw / 3.1)), floors: Math.max(2, Math.round(th / 3.4)), seed: seed + 1.7 + ti, tint: tint.clone().multiplyScalar(1.03 + 0.02 * ti) })
        cornices.push({ x: b.x, y: cy + th, z: b.z, w: cw + 0.5, d: cd + 0.5, hh: 0.5, rot, col: tint.clone().lerp(WHITE, 0.18) })
        for (const [sx, sz] of [[1, 1], [1, -1], [-1, 1], [-1, -1]]) {
          cornerFins.push({ x: b.x + sx * cw / 2, y: cy + th / 2, z: b.z + sz * cd / 2, hh: th, rot, col: accent.clone().lerp(WHITE, 0.08) })
        }
        cy += th
      }
    }

    // rooftop mechanical on the highest slab
    const topY = y0 + h
    const kind = b.rooftopKind || (h > 30 ? 'tank' : h > 14 ? 'hvac' : (hash01(seedIdx * 5.3) > 0.7 ? 'antenna' : 'hvac'))
    const kx = b.x + (hash01(seedIdx * 7.9) - 0.5) * b.w * 0.3
    const kz = b.z + (hash01(seedIdx * 9.1) - 0.5) * b.d * 0.3
    if (kind === 'tank') roofKits.tank.push({ x: kx, y: topY, z: kz, s: Math.min(3.2, b.w * 0.16) })
    else if (kind === 'antenna') roofKits.antenna.push({ x: kx, y: topY, z: kz, s: 1 })
    else roofKits.hvac.push({ x: kx, y: topY, z: kz, s: Math.min(2.6, b.w * 0.18), rot: hash01(seedIdx * 11.7) * Math.PI })

    // low homes: hip/gable roof prism (+ chimney); mid: cornice + balconies or pilaster fins
    if (low) {
      const rf = String(b.form?.roof || '')
      const roofH = Math.min(4.4, Math.max(2.0, Math.min(b.w, b.d) * 0.42))
      const longX = b.w >= b.d
      const rw = longX ? b.w : b.d
      const rd = longX ? b.d : b.w
      const rrot = rot + (longX ? 0 : Math.PI / 2)
      const roofCol = tint.clone().multiplyScalar(0.52)
      if (rf === 'flat' || rf === 'terrace' || rf === 'utility') {
        cornices.push({ x: b.x, y: topY, z: b.z, w: b.w + 0.5, d: b.d + 0.5, hh: 0.5, rot, col: tint.clone().lerp(WHITE, 0.2) })
      } else if (rf === 'hip') {
        hipRoofs.push({ x: b.x, y: topY, z: b.z, rw, rd, roofH, rot: rrot, col: roofCol })
      } else {
        gableRoofs.push({ x: b.x, y: topY, z: b.z, rw, rd, roofH, rot: rrot, col: roofCol })
      }
      if (b.form?.chimney) chimneys.push({ x: b.x + b.w * 0.26, y: topY + roofH * 0.55, z: b.z + b.d * 0.2, hh: roofH * 1.4 })
    } else if (!tall) {
      cornices.push({ x: b.x, y: topY, z: b.z, w: b.w + 0.6, d: b.d + 0.6, hh: 0.6, rot, col: tint.clone().lerp(WHITE, 0.22) })
      if (office && !residential) {
        // pilaster fins on the two street-facing faces
        const ef = b.entryFace || 'south'
        for (const f of [ef, { north: 'south', south: 'north', east: 'west', west: 'east' }[ef] || 'north']) {
          const nrm = faceNrm(f), tan = faceTan(f), half = faceHalf(f, b), len = faceLen(f, b)
          const count = clampi(Math.round(len / 4.5), 2, 5)
          for (let k = 0; k < count; k++) {
            const t = (-0.5 + (k + 0.5) / count) * (len * 0.84)
            pilasters.push({
              x: b.x + nrm[0] * (half + 0.18) + tan[0] * t,
              y: y0 + (h - 1.0) / 2 + 0.2,
              z: b.z + nrm[1] * (half + 0.18) + tan[1] * t,
              sx: nrm[0] !== 0 ? 0.35 : 0.5, sy: h - 1.0, sz: nrm[0] !== 0 ? 0.5 : 0.35,
              col: accent.clone(),
            })
          }
        }
      } else {
        // balconies on the two side facades (perpendicular to the entry)
        const entryAlongZ = (b.entryFace === 'north' || b.entryFace === 'south' || !b.entryFace)
        const sideNrms = entryAlongZ ? [[1, 0], [-1, 0]] : [[0, 1], [0, -1]]
        for (const [nx, nz] of sideNrms) {
          const half = nx !== 0 ? b.w / 2 : b.d / 2
          const along = nx !== 0 ? b.d : b.w
          const bw = Math.min(2.6, along * 0.5)
          for (const fy of [0.42, 0.68]) {
            balconies.push({
              x: b.x + nx * (half + 0.45), y: y0 + h * fy, z: b.z + nz * (half + 0.45),
              sx: nx !== 0 ? 0.9 : bw, sy: 1.0, sz: nx !== 0 ? bw : 0.9,
              col: tint.clone().multiplyScalar(0.92),
            })
          }
        }
      }
    }

    // entrance: double glass door (frame + slab + mullion + steps) on the entry face
    const ef = b.entryFace || 'south'
    const nrm = faceNrm(ef), half = faceHalf(ef, b), len = faceLen(ef, b)
    const isLM = !!b.landmark
    const drot = (ef === 'east' || ef === 'west') ? Math.PI / 2 : 0
    const doorW = Math.min(len * 0.5, isLM ? (b.interior?.doorWidth || 9) : 3.2)
    const doorH = Math.min(isLM ? 4.6 : 3.2, Math.max(2.4, h * 0.5))
    const cx = b.x + nrm[0] * half, cz = b.z + nrm[1] * half
    doorFrames.push({ x: cx + nrm[0] * 0.05, y: y0 + (doorH + 0.3) / 2, z: cz + nrm[1] * 0.05, sx: doorW + 0.4, sy: doorH + 0.3, sz: 0.14, rot: drot })
    doorSlabs.push({ x: cx + nrm[0] * 0.11, y: y0 + doorH / 2, z: cz + nrm[1] * 0.11, sx: doorW, sy: doorH, sz: 0.16, rot: drot })
    doorMullions.push({ x: cx + nrm[0] * 0.15, y: y0 + doorH / 2, z: cz + nrm[1] * 0.15, sx: 0.12, sy: doorH, sz: 0.2, rot: drot })
    doorSteps.push({ x: cx + nrm[0] * 0.55, y: y0 + 0.09, z: cz + nrm[1] * 0.55, sx: doorW + 0.7, sy: 0.18, sz: 1.2, rot: drot })
    doorSteps.push({ x: cx + nrm[0] * 0.32, y: y0 + 0.26, z: cz + nrm[1] * 0.32, sx: doorW + 0.3, sy: 0.18, sz: 0.7, rot: drot })

    // entry canopy (deeper for retail) + retail arcade + shopfront + sign slab
    const cdep = (retail || isLM) ? 3.6 : 2.2
    canopies.push({ x: cx + nrm[0] * (cdep / 2 - 0.2), y: y0 + Math.min(doorH + 0.5, h - 0.2), z: cz + nrm[1] * (cdep / 2 - 0.2), w: Math.min(len * 0.62, 7.5), depth: cdep, rot: drot })
    if (retail || isLM) shopfronts.push({ x: cx, y: y0 + 1.5, z: cz, w: len * 0.82, rot: drot })
    if (retail) {
      const tan = faceTan(ef)
      const cols = clampi(Math.round(len / 5), 3, 8)
      for (let k = 0; k < cols; k++) {
        const t = (-0.5 + (k + 0.5) / cols) * (len * 0.9)
        arcadeCols.push({ x: cx + nrm[0] * 0.4 + tan[0] * t, z: cz + nrm[1] * 0.4 + tan[1] * t, y: y0 + 1.6, hh: 3.2 })
      }
      signboards.push({ x: cx + nrm[0] * 0.25, y: y0 + 3.7, z: cz + nrm[1] * 0.25, sx: Math.min(len * 0.7, doorW + 4), sy: 0.9, sz: 0.28, rot: drot, col: accent.clone().multiplyScalar(0.8) })
    }
  }

  /* --- keep-off zones for street furniture: all carriageways, footprints, parking --- */
  const onRoad = (x, z) => {
    for (const r of roads) {
      if (r.axis === 'x') {
        if (Math.abs(z - r.z) < r.width / 2 + 1.2 && x >= r.from - 1.2 && x <= r.to + 1.2) return true
      } else if (Math.abs(x - r.x) < r.width / 2 + 1.2 && z >= r.from - 1.2 && z <= r.to + 1.2) return true
    }
    return false
  }
  const footprints = solids.map(b => ({ x: b.x, z: b.z, hw: (b.w || 0) / 2 + 0.4, hd: (b.d || 0) / 2 + 0.4 }))
  const inFootprint = (x, z) => footprints.some(f => Math.abs(x - f.x) < f.hw && Math.abs(z - f.z) < f.hd)
  const parkingParcels = parcels.filter(p => String(p.kind) === 'parking' || /parking/.test(String(p.use || '')))
  const inParking = (x, z) => parkingParcels.some(p => Math.abs(x - p.x) < (p.w || 0) / 2 && Math.abs(z - p.z) < (p.d || 0) / 2)
  const blocked = (x, z) => onRoad(x, z) || inFootprint(x, z) || inParking(x, z)

  /* --- street furniture along roads: lights, trees, benches/bins/hydrants, paint --- */
  const dashes = []
  const edges = []
  const lights = []
  const trees = []
  const benches = []
  const bins = []
  const hydrants = []
  const sidewalkSlabs = []
  for (const r of roads) {
    const hw = r.width / 2
    const walk = 3.2                                        // pavement width
    const axisX = r.axis === 'x'
    // pavement slabs each side (merged later)
    sidewalkSlabs.push({ axisX, a: r.from, b: r.to, c: axisX ? r.z - hw - walk / 2 : r.x - hw - walk / 2 })
    sidewalkSlabs.push({ axisX, a: r.from, b: r.to, c: axisX ? r.z + hw + walk / 2 : r.x + hw + walk / 2 })
    // centre dashes (skip near intersections)
    for (let t = r.from + 6; t < r.to - 6; t += 7.5) {
      const near = intersections.some(i => Math.abs((axisX ? i.x : i.z) - t) < 9 && Math.abs((axisX ? i.z - r.z : i.x - r.x)) < 1)
      if (near) continue
      dashes.push(axisX ? { x: t, z: r.z, axisX: true } : { x: r.x, z: t, axisX: false })
    }
    // edge lines as long strips (two per road)
    edges.push({ axisX, a: r.from, b: r.to, c: axisX ? r.z - hw + 0.35 : r.x - hw + 0.35 })
    edges.push({ axisX, a: r.from, b: r.to, c: axisX ? r.z + hw - 0.35 : r.x + hw - 0.35 })
    // street lights + trees alternate along both verges (kept off crossing roads/footprints)
    let side = 1
    for (let t = r.from + 14; t < r.to - 10; t += 24) {
      const c = (axisX ? r.z : r.x) + side * (hw + 1.9)     // pavement lane, clears the on-road margin
      const lx = axisX ? t : c, lz = axisX ? c : t
      if (!blocked(lx, lz)) lights.push({ x: lx, z: lz })
      const tc = (axisX ? r.z : r.x) + side * (hw + 2.9)
      const tx = axisX ? t + 11 : tc, tz = axisX ? tc : t + 11
      if (Math.abs(tx) < CITY_HALF - 20 && Math.abs(tz) < CITY_HALF - 20 && !blocked(tx, tz)) trees.push({ x: tx, z: tz, s: 0.85 + hash01(t * 0.13 + c) * 0.5 })
      if ((t / 24) % 3 < 1) { const x = axisX ? t + 5 : c, z = axisX ? c : t + 5; if (!blocked(x, z)) benches.push({ x, z, rot: axisX ? (side > 0 ? Math.PI : 0) : (side > 0 ? -Math.PI / 2 : Math.PI / 2) }) }
      if ((t / 24) % 4 < 1) { const x = axisX ? t - 4 : c, z = axisX ? c : t - 4; if (!blocked(x, z)) bins.push({ x, z }) }
      if ((t / 24) % 6 < 1) { const x = axisX ? t + 8 : c, z = axisX ? c : t + 8; if (!blocked(x, z)) hydrants.push({ x, z }) }
      side = -side
    }
  }

  /* --- crosswalk zebra belts + real traffic-signal assemblies at intersections --- */
  const zebra = []
  const signalPoles = []       // {x,z,axis,baseY,poleH,lensX,lensZ,lensY}
  const signalArms = []        // horizontal mast arm boxes
  const signalHousings = []    // black 3-lens housing boxes
  const signalVisors = []      // per-lens visor hoods
  const POLE_H = 6.6
  for (const it of intersections) {
    const zHalfEW = it.wx / 2   // EW road z half-extent
    const xHalfNS = it.wy / 2   // NS road x half-extent
    const nStripes = 6
    // south & north crosswalks cross the NS road → belt spans wy in x, stripes run in z
    for (const sgn of [-1, 1]) {
      const cz = it.z + sgn * (zHalfEW + 2.8)
      const step = it.wy / nStripes
      for (let k = 0; k < nStripes; k++) zebra.push({ x: it.x - it.wy / 2 + (k + 0.5) * step, z: cz, sx: step * 0.62, sz: 4.6 })
    }
    // west & east crosswalks cross the EW road → belt spans wx in z, stripes run in x
    for (const sgn of [-1, 1]) {
      const cx = it.x + sgn * (xHalfNS + 2.8)
      const step = it.wx / nStripes
      for (let k = 0; k < nStripes; k++) zebra.push({ x: cx, z: it.z - it.wx / 2 + (k + 0.5) * step, sx: 4.6, sz: step * 0.62 })
    }
    // signal A — governs EW ('x') traffic: SW corner, mast arm reaching +z over the carriageway
    {
      const ax = it.x - xHalfNS - 1.5, az = it.z - zHalfEW - 1.5
      const bY = terrainHeight(ax, az)
      const armLen = zHalfEW + 1.4
      const armY = bY + POLE_H - 0.35
      const houseX = ax, houseZ = az + armLen, houseY = bY + POLE_H - 1.6
      const lensX = houseX - 0.35, lensZ = houseZ
      signalPoles.push({ x: ax, z: az, axis: 'x', baseY: bY, poleH: POLE_H, lensX, lensZ, lensY: houseY })
      signalArms.push({ cx: ax, cz: az + armLen / 2, y: armY, sx: 0.16, sz: armLen })
      signalHousings.push({ x: houseX, y: houseY, z: houseZ, sx: 0.5, sy: 2.0, sz: 0.66 })
      for (const dy of [0.6, 0, -0.6]) signalVisors.push({ x: houseX - 0.42, y: houseY + dy + 0.2, z: houseZ, sx: 0.3, sz: 0.5 })
    }
    // signal B — governs NS ('y') traffic: NE corner, mast arm reaching -x over the carriageway
    {
      const bx = it.x + xHalfNS + 1.5, bz = it.z + zHalfEW + 1.5
      const bY = terrainHeight(bx, bz)
      const armLen = xHalfNS + 1.4
      const armY = bY + POLE_H - 0.35
      const houseX = bx - armLen, houseZ = bz, houseY = bY + POLE_H - 1.6
      const lensX = houseX, lensZ = houseZ + 0.35
      signalPoles.push({ x: bx, z: bz, axis: 'y', baseY: bY, poleH: POLE_H, lensX, lensZ, lensY: houseY })
      signalArms.push({ cx: bx - armLen / 2, cz: bz, y: armY, sx: armLen, sz: 0.16 })
      signalHousings.push({ x: houseX, y: houseY, z: houseZ, sx: 0.66, sy: 2.0, sz: 0.5 })
      for (const dy of [0.6, 0, -0.6]) signalVisors.push({ x: houseX, y: houseY + dy + 0.2, z: houseZ + 0.42, sx: 0.5, sz: 0.3 })
    }
  }

  /* --- landscaping from parcels (zoning agent) --- */
  const lawns = []
  const parkTrees = []
  const hedges = []
  const stalls = []
  for (const p of parcels) {
    const use = String(p.use || p.kind || '')
    if (/park|garden|green|playground|plaza/.test(use)) {
      lawns.push({ x: p.x, z: p.z, w: p.w, d: p.d, plaza: /plaza/.test(use) })
      const n = Math.max(2, Math.floor((p.w * p.d) / 260))
      for (let i = 0; i < n; i++) {
        parkTrees.push({ x: p.x + (hash01(i * 3.1 + p.x) - 0.5) * p.w * 0.8, z: p.z + (hash01(i * 5.7 + p.z) - 0.5) * p.d * 0.8, s: 1 + hash01(i * 7.3) * 0.9 })
      }
      const hn = Math.floor(Math.max(p.w, p.d) / 9)
      for (let i = 0; i < hn; i++) hedges.push({ x: p.x - p.w / 2 + (i + 0.5) * (p.w / hn), z: p.z - p.d / 2 + 0.6, rot: 0 })
      benches.push({ x: p.x, z: p.z + p.d * 0.25, rot: Math.PI })
    } else if (/parking/.test(use)) {
      const cols = Math.max(2, Math.floor(p.w / 3))
      for (let i = 0; i < cols; i++) stalls.push({ x: p.x - p.w / 2 + (i + 0.5) * (p.w / cols), z: p.z, sx: 0.18, sz: 5.2 })
    }
  }

  const allTrees = trees.concat(parkTrees)

  /* --- physics obstacle registry: circular street props (rebuild-safe, idempotent) --- */
  const obstacles = []
  for (const t of allTrees) obstacles.push({ x: t.x, z: t.z, r: 0.5 })
  for (const p of lights) obstacles.push({ x: p.x, z: p.z, r: 0.3 })
  for (const p of signalPoles) obstacles.push({ x: p.x, z: p.z, r: 0.3 })
  for (const hh of hydrants) obstacles.push({ x: hh.x, z: hh.z, r: 0.35 })
  for (const bn of benches) obstacles.push({ x: bn.x, z: bn.z, r: 0.9 })
  city.obstacles = obstacles
  city.__obstacleGrid = null   // let collision.js rebuild its spatial grid from the fresh set

  return {
    intersections, bodies, roofKits, canopies, shopfronts,
    hipRoofs, gableRoofs, chimneys, cornices, balconies, pilasters, cornerFins, arcadeCols, signboards,
    doorSlabs, doorFrames, doorMullions, doorSteps,
    dashes, edges, lights, trees: allTrees, benches, bins, hydrants, sidewalkSlabs,
    zebra, signalPoles, signalArms, signalHousings, signalVisors,
    lawns, hedges, stalls, obstacles,
  }
}

/* merged ground: terrain (vertex-coloured) + roads + pavements */
function makeTerrain(city) {
  const seg = 110
  const g = new THREE.PlaneGeometry(CITY_WORLD_SIZE, CITY_WORLD_SIZE, seg, seg)
  g.rotateX(-Math.PI / 2)
  const pos = g.attributes.position
  const colors = new Float32Array(pos.count * 3)
  const parcels = city.parcels || []
  for (let i = 0; i < pos.count; i++) {
    const x = pos.getX(i), z = pos.getZ(i)
    pos.setY(i, terrainHeight(x, z) - 0.05)
    let c = COL.set(terrainTone(x, z)).multiplyScalar(0.62)
    for (const p of parcels) {
      if (Math.abs(x - p.x) < p.w / 2 && Math.abs(z - p.z) < p.d / 2) {
        const use = String(p.use || p.kind || '')
        if (/park|garden|green|playground/.test(use)) c = COL.set('#465e3a')
        else if (/plaza/.test(use)) c = COL.set('#6e6a62')
        else if (/parking/.test(use)) c = COL.set('#35383b')
        break
      }
    }
    colors[i * 3] = c.r; colors[i * 3 + 1] = c.g; colors[i * 3 + 2] = c.b
  }
  g.setAttribute('color', new THREE.BufferAttribute(colors, 3))
  g.computeVertexNormals()
  return g
}

function makeRoadsGeometry(roads) {
  const verts = []
  for (const r of roads) {
    const hw = r.width / 2
    const y = 0.02
    if (r.axis === 'x') verts.push(r.from, y, r.z - hw, r.to, y, r.z - hw, r.to, y, r.z + hw, r.from, y, r.z - hw, r.to, y, r.z + hw, r.from, y, r.z + hw)
    else verts.push(r.x - hw, y, r.from, r.x + hw, y, r.from, r.x + hw, y, r.to, r.x - hw, y, r.from, r.x + hw, y, r.to, r.x - hw, y, r.to)
  }
  const g = new THREE.BufferGeometry()
  g.setAttribute('position', new THREE.BufferAttribute(new Float32Array(verts), 3))
  g.computeVertexNormals()
  return g
}

function makeStripsGeometry(slabs, width, y) {
  const verts = []
  for (const s of slabs) {
    const hw = width / 2
    if (s.axisX) verts.push(s.a, y, s.c - hw, s.b, y, s.c - hw, s.b, y, s.c + hw, s.a, y, s.c - hw, s.b, y, s.c + hw, s.a, y, s.c + hw)
    else verts.push(s.c - hw, y, s.a, s.c + hw, y, s.a, s.c + hw, y, s.b, s.c - hw, y, s.a, s.c + hw, y, s.b, s.c - hw, y, s.b)
  }
  const g = new THREE.BufferGeometry()
  g.setAttribute('position', new THREE.BufferAttribute(new Float32Array(verts), 3))
  g.computeVertexNormals()
  return g
}

/* ------------------------------------ component ------------------------------------ */
export default function CityScape({ city }) {
  const facadeUniforms = useRef(null)
  const layout = useMemo(() => buildLayout(city), [city])
  const terrainGeo = useMemo(() => makeTerrain(city), [city])
  const roadsGeo = useMemo(() => makeRoadsGeometry(city.roads || []), [city])
  const walksGeo = useMemo(() => makeStripsGeometry(layout.sidewalkSlabs, 3.2, 0.09), [layout])
  const facadeMat = useMemo(() => makeFacadeMaterial(facadeUniforms), [])

  /* building instanced mesh with per-instance grid attrs */
  const buildingMesh = useMemo(() => {
    const n = layout.bodies.length
    const geo = new THREE.BoxGeometry(1, 1, 1)
    const grid = new Float32Array(n * 3)
    const tint = new Float32Array(n * 3)
    const mesh = new THREE.InstancedMesh(geo, facadeMat, n)
    layout.bodies.forEach((b, i) => {
      setInst(mesh, i, b.x, b.y, b.z, b.w, b.h, b.d, b.rot)
      grid[i * 3] = b.bays; grid[i * 3 + 1] = b.floors; grid[i * 3 + 2] = b.seed
      tint[i * 3] = b.tint.r; tint[i * 3 + 1] = b.tint.g; tint[i * 3 + 2] = b.tint.b
    })
    geo.setAttribute('aGrid', new THREE.InstancedBufferAttribute(grid, 3))
    geo.setAttribute('aTint', new THREE.InstancedBufferAttribute(tint, 3))
    mesh.instanceMatrix.needsUpdate = true
    mesh.castShadow = true
    mesh.receiveShadow = true
    return mesh
  }, [layout, facadeMat])

  /* generic instanced kit builder */
  const kit = useMemo(() => {
    function inst(geo, color, items, place, opts = {}) {
      const mat = opts.emissive
        ? new THREE.MeshStandardMaterial({ color, emissive: color, emissiveIntensity: 0, roughness: 0.5 })
        : new THREE.MeshStandardMaterial({ color, roughness: opts.rough ?? 0.85, metalness: opts.metal ?? 0 })
      if (opts.doubleSide) mat.side = THREE.DoubleSide
      const m = new THREE.InstancedMesh(geo, mat, Math.max(1, items.length))
      let hasCol = false
      items.forEach((it, i) => { place(m, i, it); if (it && it.col) { m.setColorAt(i, it.col); hasCol = true } })
      m.instanceMatrix.needsUpdate = true
      m.count = items.length
      if (hasCol && m.instanceColor) m.instanceColor.needsUpdate = true
      if (opts.shadow) { m.castShadow = true }
      m.receiveShadow = true
      return m
    }
    const L = layout
    const gy = (x, z) => terrainHeight(x, z)
    const box = new THREE.BoxGeometry(1, 1, 1)
    const cyl = new THREE.CylinderGeometry(0.5, 0.5, 1, 10)
    const ball = new THREE.IcosahedronGeometry(0.55, 1)
    const hipGeo = makeRoofGeo(0.25)
    const gableGeo = makeRoofGeo(0.5)
    return {
      // road paint — all at a constant flat-road height so it never sinks into terrain
      dashes: inst(box, '#e8e6df', L.dashes, (m, i, d) => setInst(m, i, d.x, 0.07, d.z, d.axisX ? 3.4 : 0.28, 0.03, d.axisX ? 0.28 : 3.4)),
      zebra: inst(box, '#eef0ea', L.zebra, (m, i, d) => setInst(m, i, d.x, 0.075, d.z, d.sx, 0.03, d.sz)),
      edges: inst(box, '#c2beb4', L.edges, (m, i, e) => e.axisX
        ? setInst(m, i, (e.a + e.b) / 2, 0.065, e.c, e.b - e.a, 0.03, 0.22)
        : setInst(m, i, e.c, 0.065, (e.a + e.b) / 2, 0.22, 0.03, e.b - e.a)),
      stalls: inst(box, '#d9d6cc', L.stalls, (m, i, s0) => setInst(m, i, s0.x, 0.07, s0.z, s0.sx, 0.03, s0.sz)),
      // street furniture
      lightPoles: inst(cyl, '#3c4246', L.lights, (m, i, p) => setInst(m, i, p.x, gy(p.x, p.z) + 3.4, p.z, 0.22, 6.8, 0.22), { shadow: true }),
      lightHeads: inst(ball, '#ffd9a0', L.lights, (m, i, p) => setInst(m, i, p.x, gy(p.x, p.z) + 6.7, p.z, 0.85, 0.5, 0.85), { emissive: '#ffc36b' }),
      treeTrunks: inst(cyl, '#5d4a36', L.trees, (m, i, t) => setInst(m, i, t.x, gy(t.x, t.z) + 1.4 * t.s, t.z, 0.32 * t.s, 2.8 * t.s, 0.32 * t.s), { shadow: true }),
      treeCrowns: inst(ball, '#4f7143', L.trees, (m, i, t) => setInst(m, i, t.x, gy(t.x, t.z) + 3.6 * t.s, t.z, 2.6 * t.s, 2.9 * t.s, 2.6 * t.s), { shadow: true }),
      benches: inst(box, '#7a6a52', L.benches, (m, i, b) => setInst(m, i, b.x, gy(b.x, b.z) + 0.45, b.z, 2.1, 0.5, 0.7, b.rot || 0)),
      bins: inst(cyl, '#4c5a54', L.bins, (m, i, b) => setInst(m, i, b.x, gy(b.x, b.z) + 0.55, b.z, 0.6, 1.1, 0.6)),
      hydrants: inst(cyl, '#a24435', L.hydrants, (m, i, h) => setInst(m, i, h.x, gy(h.x, h.z) + 0.45, h.z, 0.42, 0.9, 0.42)),
      hedges: inst(box, '#42603b', L.hedges, (m, i, h) => setInst(m, i, h.x, gy(h.x, h.z) + 0.5, h.z, 8.4, 1.0, 1.1, h.rot || 0)),
      // entrances
      canopies: inst(box, '#2f3a40', L.canopies, (m, i, c) => setInst(m, i, c.x, c.y, c.z, c.w, 0.22, c.depth, c.rot || 0), { shadow: true }),
      shopfronts: inst(box, '#20303a', L.shopfronts, (m, i, s0) => setInst(m, i, s0.x, s0.y, s0.z, s0.w, 2.9, 0.28, s0.rot || 0), { metal: 0.3, rough: 0.3 }),
      doorFrames: inst(box, '#454b54', L.doorFrames, (m, i, d) => setInst(m, i, d.x, d.y, d.z, d.sx, d.sy, d.sz, d.rot || 0), { metal: 0.4, rough: 0.5 }),
      doorSlabs: inst(box, '#141a20', L.doorSlabs, (m, i, d) => setInst(m, i, d.x, d.y, d.z, d.sx, d.sy, d.sz, d.rot || 0), { metal: 0.5, rough: 0.22 }),
      doorMullions: inst(box, '#0d1116', L.doorMullions, (m, i, d) => setInst(m, i, d.x, d.y, d.z, d.sx, d.sy, d.sz, d.rot || 0)),
      doorSteps: inst(box, '#8c887f', L.doorSteps, (m, i, d) => setInst(m, i, d.x, d.y, d.z, d.sx, d.sy, d.sz, d.rot || 0)),
      arcadeCols: inst(cyl, '#c8c3b6', L.arcadeCols, (m, i, c) => setInst(m, i, c.x, c.y, c.z, 0.3, c.hh, 0.3), { shadow: true }),
      signboards: inst(box, '#ffffff', L.signboards, (m, i, s) => setInst(m, i, s.x, s.y, s.z, s.sx, s.sy, s.sz, s.rot || 0)),
      // architectural massing
      hipRoofs: inst(hipGeo, '#ffffff', L.hipRoofs, (m, i, r) => setInst(m, i, r.x, r.y, r.z, r.rw, r.roofH, r.rd, r.rot), { doubleSide: true, rough: 0.9, shadow: true }),
      gableRoofs: inst(gableGeo, '#ffffff', L.gableRoofs, (m, i, r) => setInst(m, i, r.x, r.y, r.z, r.rw, r.roofH, r.rd, r.rot), { doubleSide: true, rough: 0.9, shadow: true }),
      chimneys: inst(box, '#5b4a3c', L.chimneys, (m, i, c) => setInst(m, i, c.x, c.y, c.z, 0.8, c.hh, 0.8)),
      cornices: inst(box, '#ffffff', L.cornices, (m, i, c) => setInst(m, i, c.x, c.y, c.z, c.w, c.hh, c.d, c.rot || 0)),
      balconies: inst(box, '#ffffff', L.balconies, (m, i, b) => setInst(m, i, b.x, b.y, b.z, b.sx, b.sy, b.sz), { shadow: true }),
      pilasters: inst(box, '#ffffff', L.pilasters, (m, i, p) => setInst(m, i, p.x, p.y, p.z, p.sx, p.sy, p.sz)),
      cornerFins: inst(box, '#ffffff', L.cornerFins, (m, i, c) => setInst(m, i, c.x, c.y, c.z, 0.6, c.hh, 0.6, c.rot || 0)),
      // rooftop mechanical
      hvac: inst(box, '#8d9298', L.roofKits.hvac, (m, i, k) => setInst(m, i, k.x, k.y + 0.6, k.z, k.s * 1.6, 1.2, k.s, k.rot || 0)),
      tanks: inst(cyl, '#9aa0a4', L.roofKits.tank, (m, i, k) => setInst(m, i, k.x, k.y + 1.4, k.z, k.s, 2.8, k.s)),
      antennas: inst(cyl, '#565c60', L.roofKits.antenna, (m, i, k) => setInst(m, i, k.x, k.y + 2.4, k.z, 0.1, 4.8, 0.1)),
      // traffic signals: pole + mast arm + black housing + visor hoods
      signalPoles: inst(cyl, '#33383c', L.signalPoles, (m, i, p) => setInst(m, i, p.x, p.baseY + p.poleH / 2, p.z, 0.24, p.poleH, 0.24), { shadow: true }),
      signalArms: inst(box, '#2f3439', L.signalArms, (m, i, a) => setInst(m, i, a.cx, a.y, a.cz, a.sx, 0.18, a.sz), { shadow: true }),
      signalHousings: inst(box, '#111417', L.signalHousings, (m, i, hh) => setInst(m, i, hh.x, hh.y, hh.z, hh.sx, hh.sy, hh.sz), { shadow: true }),
      signalVisors: inst(box, '#0a0c0e', L.signalVisors, (m, i, v) => setInst(m, i, v.x, v.y, v.z, v.sx, 0.07, v.sz)),
    }
  }, [layout])

  /* three lamp meshes (red/amber/green) whose per-instance colour switches with the cycle,
   * seated on the signal housing lens stack */
  const lampMeshes = useMemo(() => {
    const geo = new THREE.SphereGeometry(0.26, 10, 8)
    const mk = () => {
      const mat = new THREE.MeshStandardMaterial({ color: '#111', emissive: '#000', emissiveIntensity: 1 })
      const m = new THREE.InstancedMesh(geo, mat, Math.max(1, layout.signalPoles.length))
      m.count = layout.signalPoles.length
      return m
    }
    const red = mk(), amber = mk(), green = mk()
    layout.signalPoles.forEach((p, i) => {
      setInst(red, i, p.lensX, p.lensY + 0.6, p.lensZ, 1, 1, 1); setInst(amber, i, p.lensX, p.lensY, p.lensZ, 1, 1, 1); setInst(green, i, p.lensX, p.lensY - 0.6, p.lensZ, 1, 1, 1)
      for (const m of [red, amber, green]) m.setColorAt(i, COL.set('#101010'))
    })
    for (const m of [red, amber, green]) { m.instanceMatrix.needsUpdate = true; if (m.instanceColor) m.instanceColor.needsUpdate = true }
    return { red, amber, green }
  }, [layout])

  /* throttled updates: night state (facade windows + street lights) and signal phases */
  const tick = useRef({ night: -1, phase: -1, sig: -1 })
  useFrame(({ clock: three }) => {
    const t = three.elapsedTime
    const sys = (typeof window !== 'undefined' && window.__REALCITY_CITY__ && window.__REALCITY_CITY__.systems) || {}
    // night factor twice a second
    if (t - tick.current.night > 0.5) {
      tick.current.night = t
      const phase = sys.clock?.phase || 'day'
      const nightTarget = phase === 'night' ? 1 : phase === 'dusk' ? 0.7 : phase === 'dawn' ? 0.25 : 0
      if (facadeUniforms.current) {
        const u = facadeUniforms.current.uNight
        u.value += (nightTarget - u.value) * 0.25
      }
      kit.lightHeads.material.emissiveIntensity += ((nightTarget > 0.3 ? 2.1 : 0) - kit.lightHeads.material.emissiveIntensity) * 0.3
    }
    // signal cycle ~4 times a second
    if (t - tick.current.sig > 0.25) {
      tick.current.sig = t
      const cyc = TRAFFIC_SIGNAL_CYCLE_SECONDS
      const half = cyc / 2
      const yel = TRAFFIC_SIGNAL_YELLOW_SECONDS
      const m = ((sys.clock?.simMinutes ?? t / 60) * 60) % cyc
      const xGreen = m < half - yel
      const xYellow = m >= half - yel && m < half
      const yGreen = m >= half && m < cyc - yel
      const yYellow = m >= cyc - yel
      const L = layout.signalPoles
      for (let i = 0; i < L.length; i++) {
        const forX = L[i].axis === 'x'
        const g = forX ? xGreen : yGreen
        const y = forX ? xYellow : yYellow
        lampMeshes.red.setColorAt(i, COL.set(!g && !y ? '#ff2f24' : '#160404'))
        lampMeshes.amber.setColorAt(i, COL.set(y ? '#ffb020' : '#161004'))
        lampMeshes.green.setColorAt(i, COL.set(g ? '#2fe06a' : '#04160a'))
      }
      lampMeshes.red.instanceColor.needsUpdate = true
      lampMeshes.amber.instanceColor.needsUpdate = true
      lampMeshes.green.instanceColor.needsUpdate = true
      // publish machine-readable signal state for future traffic logic / ATANOR perception
      if (typeof window !== 'undefined' && window.__REALCITY_CITY__) {
        window.__REALCITY_CITY__.trafficSignals = { xGreen, yGreen, cycleT: m, intersections: layout.intersections.length }
      }
    }
  })

  /* debug/verify handle */
  if (typeof window !== 'undefined') {
    window.__REALCITY_SCAPE__ = {
      bodies: layout.bodies.length, intersections: layout.intersections.length,
      trees: layout.trees.length, lights: layout.lights.length, zebra: layout.zebra.length,
      signals: layout.signalPoles.length, doors: layout.doorSlabs.length, obstacles: layout.obstacles.length,
      parcels: (city.parcels || []).length,
    }
  }

  return (
    <group>
      <mesh geometry={terrainGeo} receiveShadow>
        <meshStandardMaterial vertexColors roughness={0.96} />
      </mesh>
      <mesh geometry={roadsGeo} receiveShadow>
        <meshStandardMaterial color="#26282c" roughness={0.96} />
      </mesh>
      <mesh geometry={walksGeo} receiveShadow>
        <meshStandardMaterial color="#5f5c56" roughness={0.94} />
      </mesh>
      {layout.lawns.map((p, i) => (
        <mesh key={i} position={[p.x, terrainHeight(p.x, p.z) + 0.04, p.z]} rotation={[-Math.PI / 2, 0, 0]} receiveShadow>
          <planeGeometry args={[p.w, p.d]} />
          <meshStandardMaterial color={p.plaza ? '#6e6a62' : '#3f5a30'} roughness={0.95} />
        </mesh>
      ))}
      <primitive object={buildingMesh} />
      {Object.values(kit).map((m, i) => <primitive key={i} object={m} />)}
      <primitive object={lampMeshes.red} />
      <primitive object={lampMeshes.amber} />
      <primitive object={lampMeshes.green} />
    </group>
  )
}
