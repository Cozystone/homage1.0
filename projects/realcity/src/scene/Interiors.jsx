// Interiors.jsx — furnished ground floors for every landmark that has an interior.
//
// Owned by the interiors agent. Mounted elsewhere in the scene; renders inside the R3F <Canvas>.
// Design goals (see task brief):
//  - one furniture "kit" per landmark kind, placed in the landmark's LOCAL frame (a <group> at
//    [place.x, 0, place.z] rotated by place.rot reproduces collision.js worldPoint exactly).
//  - PERFORMANCE: two shared unit geometries (box + cylinder) and a small shared material palette,
//    reused across every interior (module-level singletons). Repeated pieces (chairs / student desks
//    / beds / shelves / crates / benches) are drawn with instancing. No per-frame allocations.
//  - CULL: each interior is a group whose .visible is toggled from a single cheap useFrame poll —
//    contents (and its one warm point light) only render when the camera is within ~60 units.
//  - AFFORDANCE REGISTRATION: once on mount, every furniture piece is pushed as a world-space
//    {id, kind, x, z, landmarkId} into window.__REALCITY_CITY__.props and mirrored onto
//    landmark.furniture, so the perception / capability engine can find a 'seat' to sit on or a
//    'kitchen' to cook at.
import { useEffect, useLayoutEffect, useMemo, useRef, useState } from 'react'
import { useFrame } from '@react-three/fiber'
import * as THREE from 'three'

// --- shared, reused across ALL interiors (created once, in the browser) --------------------------
const BOX = new THREE.BoxGeometry(1, 1, 1)
const CYL = new THREE.CylinderGeometry(0.5, 0.5, 1, 12) // radius 0.5 => scale by 2r for radius r
const DUMMY = new THREE.Object3D()

const MAT = {
  wood: new THREE.MeshStandardMaterial({ color: '#b08968', roughness: 0.72, metalness: 0.02 }),
  woodDark: new THREE.MeshStandardMaterial({ color: '#7a5c43', roughness: 0.7, metalness: 0.03 }),
  metal: new THREE.MeshStandardMaterial({ color: '#9aa3a8', roughness: 0.42, metalness: 0.55 }),
  steel: new THREE.MeshStandardMaterial({ color: '#c3ccd2', roughness: 0.34, metalness: 0.6 }),
  white: new THREE.MeshStandardMaterial({ color: '#eef2f4', roughness: 0.55, metalness: 0.03 }),
  cushion: new THREE.MeshStandardMaterial({ color: '#6f8496', roughness: 0.78, metalness: 0.02 }),
  fabric: new THREE.MeshStandardMaterial({ color: '#cdd6db', roughness: 0.85, metalness: 0.0 }),
  dark: new THREE.MeshStandardMaterial({ color: '#39424a', roughness: 0.5, metalness: 0.25 }),
  crate: new THREE.MeshStandardMaterial({ color: '#a9895f', roughness: 0.82, metalness: 0.02 }),
}
const matOf = key => MAT[key] || MAT.wood
const geoOf = key => (key === 'cyl' ? CYL : BOX)

const FLOOR_Y = 0.18 // furniture rests on the landmark floor slab (top ~0.16)
const CULL_RADIUS_SQ = 60 * 60

// --- pure layout: kind + interior dims -> plain furniture data (no THREE, no JSX) ---------------
function kitFor(kind) {
  if (kind === 'cafe' || kind === 'leisure') return 'cafe'
  if (kind === 'hospital') return 'hospital'
  if (kind === 'school') return 'school'
  if (kind === 'retail') return 'market'
  if (kind === 'logistics') return 'depot'
  if (kind === 'apartment' || kind === 'house') return 'apartment'
  return 'office' // transit (station), finance (exchange), workshop, default
}

function seatCluster(clusters, positions) {
  const seats = []
  const backs = []
  for (const [x, z] of positions) {
    seats.push({ p: [x, FLOOR_Y + 0.05 + 0.36, z], s: [0.5, 0.1, 0.5], ry: 0 })
    backs.push({ p: [x, FLOOR_Y + 0.25 + 0.36, z + 0.22], s: [0.5, 0.5, 0.1], ry: 0 })
  }
  clusters.push({ g: 'box', m: 'cushion', items: seats })
  clusters.push({ g: 'box', m: 'cushion', items: backs })
}

// Returns { meshes:[{g,m,p,s,ry}], clusters:[{g,m,items:[{p,s,ry}]}], aff:[{kind,lx,lz}], light }.
// Layout convention: door is on local -z (south); the vertical core sits back-right (+x,+z), so
// heavy furniture is biased to the left / front to leave the entrance corridor and core clear.
function buildKit(kind, w, d, h) {
  const hw = w / 2
  const hd = d / 2
  const meshes = []
  const clusters = []
  const aff = []
  const box = (m, x, y, z, sx, sy, sz, ry = 0) => meshes.push({ g: 'box', m, p: [x, y, z], s: [sx, sy, sz], ry })
  const cyl = (m, x, y, z, r, ht, ry = 0) => meshes.push({ g: 'cyl', m, p: [x, y, z], s: [r * 2, ht, r * 2], ry })
  const A = (k, lx, lz) => aff.push({ kind: k, lx, lz })
  const sit = sy => FLOOR_Y + sy / 2
  const kit = kitFor(kind)
  const light = {
    p: [-hw * 0.05, h * 0.72, 0],
    intensity: Math.min(2.4, 0.6 + (w * d) / 900),
    distance: Math.max(w, d) * 0.95,
  }

  if (kit === 'cafe') {
    const cLen = Math.min(w * 0.46, w - 3)
    const cX = -hw + cLen / 2 + 1.4
    const cZ = hd - 1.7
    box('woodDark', cX, sit(1.1), cZ, cLen, 1.1, 1.4)
    box('steel', cX, FLOOR_Y + 1.12, cZ, cLen, 0.06, 1.5)
    A('counter', cX, cZ)
    A('kitchen', cX, cZ - 1.15) // prep side behind the counter
    const eX = cX - cLen * 0.32
    box('metal', eX, FLOOR_Y + 1.15 + 0.28, cZ, 1.2, 0.56, 0.9) // espresso block
    cyl('dark', eX + 0.35, FLOOR_Y + 1.15 + 0.2, cZ + 0.1, 0.12, 0.4)
    A('appliance', eX, cZ)
    box('wood', -hw + 0.45, sit(2.2) + 0.4, hd * 0.05, 0.5, 2.2, Math.min(4.2, d * 0.24)) // wall shelf
    A('shelf', -hw + 0.45, hd * 0.05)
    const tPos = [
      [-hw * 0.5, -hd * 0.45], [0, -hd * 0.45], [hw * 0.35, -hd * 0.45],
      [-hw * 0.5, 0.0], [0, 0.0],
    ]
    const tops = []
    const legs = []
    const seats = []
    const backs = []
    for (const [tx, tz] of tPos) {
      tops.push({ p: [tx, FLOOR_Y + 0.72, tz], s: [1.5, 0.08, 1.5], ry: 0 })
      legs.push({ p: [tx, FLOOR_Y + 0.36, tz], s: [0.24, 0.72, 0.24], ry: 0 })
      A('table', tx, tz)
      for (const off of [-0.95, 0.95]) {
        seats.push({ p: [tx + off, sit(0.1) + 0.36, tz], s: [0.5, 0.1, 0.5], ry: 0 })
        backs.push({ p: [tx + off, sit(0.5) + 0.36, tz + (off > 0 ? 0.22 : -0.22)], s: [0.5, 0.5, 0.1], ry: 0 })
        A('seat', tx + off, tz)
      }
    }
    clusters.push({ g: 'cyl', m: 'wood', items: tops })
    clusters.push({ g: 'cyl', m: 'metal', items: legs })
    clusters.push({ g: 'box', m: 'cushion', items: seats })
    clusters.push({ g: 'box', m: 'cushion', items: backs })
  } else if (kit === 'hospital') {
    const rX = -hw * 0.4
    box('white', rX, sit(1.15), -hd + 3.5, w * 0.34, 1.15, 1.6) // reception desk
    A('counter', rX, -hd + 3.5)
    const bedX = [-hw * 0.62, -hw * 0.24, hw * 0.14, hw * 0.5]
    const bZ = -hd * 0.05
    const frames = []
    const mats = []
    const pillows = []
    const stands = []
    for (const bx of bedX) {
      frames.push({ p: [bx, sit(0.4), bZ], s: [1.6, 0.4, 2.6], ry: 0 })
      mats.push({ p: [bx, FLOOR_Y + 0.4 + 0.12, bZ], s: [1.5, 0.22, 2.5], ry: 0 })
      pillows.push({ p: [bx, FLOOR_Y + 0.64, bZ - 0.9], s: [1.1, 0.16, 0.6], ry: 0 })
      A('bed', bx, bZ)
      stands.push({ p: [bx + 1.05, sit(0.7), bZ - 0.7], s: [0.5, 0.7, 0.5], ry: 0 })
      A('table', bx + 1.05, bZ - 0.7)
    }
    clusters.push({ g: 'box', m: 'metal', items: frames })
    clusters.push({ g: 'box', m: 'fabric', items: mats })
    clusters.push({ g: 'box', m: 'white', items: pillows })
    clusters.push({ g: 'box', m: 'steel', items: stands })
  } else if (kit === 'school') {
    box('woodDark', 0, sit(1.1), -hd + 3.2, 3.2, 1.1, 1.2) // teacher desk
    A('table', 0, -hd + 3.2)
    seatCluster(clusters, [[0, -hd + 4.2]]) // teacher chair
    A('seat', 0, -hd + 4.2)
    const colX = [-hw * 0.5, -hw * 0.12, hw * 0.26]
    const rowZ = [-hd * 0.25, 0.0, hd * 0.25, hd * 0.5]
    const tops = []
    const panels = []
    const seats = []
    const backs = []
    for (const rz of rowZ) {
      for (const cxs of colX) {
        tops.push({ p: [cxs, FLOOR_Y + 0.7, rz], s: [1.2, 0.06, 0.7], ry: 0 })
        panels.push({ p: [cxs, FLOOR_Y + 0.35, rz + 0.28], s: [1.0, 0.7, 0.08], ry: 0 })
        A('table', cxs, rz)
        seats.push({ p: [cxs, sit(0.1) + 0.36, rz - 0.7], s: [0.5, 0.1, 0.5], ry: 0 })
        backs.push({ p: [cxs, sit(0.5) + 0.36, rz - 0.92], s: [0.5, 0.5, 0.1], ry: 0 })
        A('seat', cxs, rz - 0.7)
      }
    }
    clusters.push({ g: 'box', m: 'wood', items: tops })
    clusters.push({ g: 'box', m: 'metal', items: panels })
    clusters.push({ g: 'box', m: 'cushion', items: seats })
    clusters.push({ g: 'box', m: 'cushion', items: backs })
  } else if (kit === 'market' || kit === 'depot') {
    const depot = kit === 'depot'
    const cX = -hw * (depot ? 0.6 : 0.55)
    box('woodDark', cX, sit(1.12), -hd + 3.0, w * (depot ? 0.2 : 0.28), 1.12, 1.5) // checkout / dispatch
    A('counter', cX, -hd + 3.0)
    const shelfCount = depot ? 6 : 4
    const sSize = depot ? [4, 2.4, 1.0] : [3.0, 2.0, 0.8]
    const colX = depot ? [-hw * 0.55, -hw * 0.2, hw * 0.12] : [-hw * 0.45, 0.0]
    const rowZ = [-hd * 0.2, hd * 0.2]
    const bodies = []
    const boards = []
    let made = 0
    for (const rz of rowZ) {
      for (const sx of colX) {
        if (made >= shelfCount) break
        bodies.push({ p: [sx, sit(sSize[1]), rz], s: sSize, ry: 0 })
        boards.push({ p: [sx, FLOOR_Y + sSize[1] * 0.55, rz], s: [sSize[0] * 0.96, 0.06, sSize[2] * 0.9], ry: 0 })
        A('shelf', sx, rz)
        made += 1
      }
    }
    clusters.push({ g: 'box', m: 'wood', items: bodies })
    clusters.push({ g: 'box', m: 'woodDark', items: boards })
    const crates = [] // decorative stock, no affordance
    const crateN = depot ? 6 : 4
    for (let i = 0; i < crateN; i += 1) {
      const gx = -hw + 1.6 + (i % 3) * 1.25
      const gz = hd - 1.6 - Math.floor(i / 3) * 1.25
      crates.push({ p: [gx, sit(1.1), gz], s: [1.1, 1.1, 1.1], ry: 0 })
    }
    clusters.push({ g: 'box', m: 'crate', items: crates })
  } else if (kit === 'apartment') {
    box('fabric', -hw * 0.5, sit(0.5), hd * 0.3, 1.6, 0.5, 2.4) // bed
    box('white', -hw * 0.5, FLOOR_Y + 0.62, hd * 0.3 - 0.9, 1.2, 0.16, 0.6)
    A('bed', -hw * 0.5, hd * 0.3)
    cyl('wood', hw * 0.2, FLOOR_Y + 0.72, -hd * 0.1, 0.7, 0.08) // table
    cyl('metal', hw * 0.2, FLOOR_Y + 0.36, -hd * 0.1, 0.12, 0.72)
    A('table', hw * 0.2, -hd * 0.1)
    box('woodDark', hw * 0.4, sit(1.05), hd * 0.5, w * 0.3, 1.05, 1.2) // kitchen counter
    box('metal', hw * 0.5, FLOOR_Y + 1.1 + 0.2, hd * 0.5, 0.7, 0.4, 0.7)
    A('kitchen', hw * 0.4, hd * 0.5)
    box('woodDark', -hw + 0.6, sit(2.2), -hd * 0.3, 1.0, 2.2, 1.4) // wardrobe
    A('shelf', -hw + 0.6, -hd * 0.3)
    const seats = []
    for (const off of [-0.95, 0.95]) {
      seats.push({ p: [hw * 0.2 + off, sit(0.1) + 0.36, -hd * 0.1], s: [0.5, 0.1, 0.5], ry: 0 })
      A('seat', hw * 0.2 + off, -hd * 0.1)
    }
    clusters.push({ g: 'box', m: 'cushion', items: seats })
  } else { // office: transit, finance, workshop, default (desks + benches)
    const cX = -hw * 0.5
    box('woodDark', cX, sit(1.1), -hd + 3.0, w * 0.2, 1.1, 1.4) // reception
    A('counter', cX, -hd + 3.0)
    const deskX = [-hw * 0.5, -hw * 0.1]
    const deskZ = [-hd * 0.1, hd * 0.25]
    const tops = []
    const panels = []
    const chairs = []
    const chBacks = []
    for (const dz of deskZ) {
      for (const dx of deskX) {
        tops.push({ p: [dx, FLOOR_Y + 0.75, dz], s: [2.0, 0.06, 1.0], ry: 0 })
        panels.push({ p: [dx, FLOOR_Y + 0.38, dz + 0.45], s: [1.9, 0.75, 0.08], ry: 0 })
        A('table', dx, dz)
        chairs.push({ p: [dx, sit(0.1) + 0.36, dz - 0.7], s: [0.55, 0.1, 0.55], ry: 0 })
        chBacks.push({ p: [dx, sit(0.55) + 0.36, dz - 0.92], s: [0.55, 0.55, 0.1], ry: 0 })
        A('seat', dx, dz - 0.7)
      }
    }
    clusters.push({ g: 'box', m: 'wood', items: tops })
    clusters.push({ g: 'box', m: 'metal', items: panels })
    clusters.push({ g: 'box', m: 'cushion', items: chairs })
    clusters.push({ g: 'box', m: 'cushion', items: chBacks })
    const benches = []
    for (const bz of [-hd * 0.3, 0, hd * 0.3]) {
      benches.push({ p: [-hw + 1.0, sit(0.45), bz], s: [0.9, 0.45, 2.4], ry: 0 })
      A('seat', -hw + 1.0, bz)
    }
    clusters.push({ g: 'box', m: 'wood', items: benches })
  }

  return { meshes, clusters, aff, light }
}

// --- one instanced draw for a repeated furniture element -----------------------------------------
function Cluster({ geo, mat, items }) {
  const ref = useRef()
  useLayoutEffect(() => {
    const mesh = ref.current
    if (!mesh) return
    for (let i = 0; i < items.length; i += 1) {
      const it = items[i]
      DUMMY.position.set(it.p[0], it.p[1], it.p[2])
      DUMMY.rotation.set(0, it.ry || 0, 0)
      DUMMY.scale.set(it.s[0], it.s[1], it.s[2])
      DUMMY.updateMatrix()
      mesh.setMatrixAt(i, DUMMY.matrix)
    }
    mesh.instanceMatrix.needsUpdate = true
  }, [items])
  return (
    <instancedMesh ref={ref} args={[geo, mat, items.length]} castShadow receiveShadow frustumCulled={false} />
  )
}

// --- one landmark's furnished ground floor (its own cull group) -----------------------------------
function InteriorFurniture({ place, kit, innerRef }) {
  return (
    <group ref={innerRef} position={[place.x, 0, place.z]} rotation={[0, place.rot || 0, 0]} visible={false}>
      {kit.meshes.map((m, i) => (
        <mesh
          key={`m${i}`}
          geometry={geoOf(m.g)}
          material={matOf(m.m)}
          position={m.p}
          scale={m.s}
          rotation-y={m.ry}
          castShadow
          receiveShadow
        />
      ))}
      {kit.clusters.map((c, i) =>
        c.items.length ? <Cluster key={`c${i}`} geo={geoOf(c.g)} mat={matOf(c.m)} items={c.items} /> : null,
      )}
      <pointLight
        position={kit.light.p}
        intensity={kit.light.intensity}
        distance={kit.light.distance}
        decay={2}
        color="#ffd9a8"
      />
    </group>
  )
}

export default function Interiors({ city: cityProp } = {}) {
  const [city, setCity] = useState(
    () => cityProp || (typeof window !== 'undefined' ? window.__REALCITY_CITY__ : null),
  )

  // the city may not exist at first render — retry until it registers once
  useEffect(() => {
    if (city) return undefined
    const id = setInterval(() => {
      const c = cityProp || (typeof window !== 'undefined' ? window.__REALCITY_CITY__ : null)
      if (c) {
        setCity(c)
        clearInterval(id)
      }
    }, 200)
    return () => clearInterval(id)
  }, [city, cityProp])

  const furnished = useMemo(() => {
    if (!city || !Array.isArray(city.landmarks)) return []
    return city.landmarks
      .filter(p => p.interior && p.interior.width && p.interior.depth)
      .map(p => ({
        place: p,
        kit: buildKit(p.kind, p.interior.width, p.interior.depth, p.interior.height || 6),
      }))
  }, [city])

  // AFFORDANCE REGISTRATION — once per city. World-space props for the perception engine.
  useEffect(() => {
    if (!city || !furnished.length || city.__interiorsRegistered) return
    city.__interiorsRegistered = true
    city.props = city.props || []
    for (const { place, kit } of furnished) {
      const rot = place.rot || 0
      const cos = Math.cos(rot)
      const sin = Math.sin(rot)
      const items = kit.aff.map((a, i) => ({
        id: `${place.id}:${a.kind}:${i}`,
        kind: a.kind,
        x: place.x + a.lx * cos + a.lz * sin,
        z: place.z - a.lx * sin + a.lz * cos,
        landmarkId: place.id,
      }))
      for (const it of items) city.props.push(it)
      place.furniture = items
    }
  }, [city, furnished])

  const groupRefs = useRef([])

  // CULL — one cheap poll per frame; toggle each interior (and its light) by camera distance.
  useFrame(state => {
    const cam = state.camera
    const cx = cam.position.x
    const cz = cam.position.z
    for (let i = 0; i < furnished.length; i += 1) {
      const g = groupRefs.current[i]
      if (!g) continue
      const p = furnished[i].place
      const dx = cx - p.x
      const dz = cz - p.z
      const visible = dx * dx + dz * dz < CULL_RADIUS_SQ
      if (g.visible !== visible) g.visible = visible
    }
  })

  if (!furnished.length) return null

  return (
    <group>
      {furnished.map((f, i) => (
        <InteriorFurniture
          key={f.place.id}
          place={f.place}
          kit={f.kit}
          innerRef={el => {
            groupRefs.current[i] = el
          }}
        />
      ))}
    </group>
  )
}
