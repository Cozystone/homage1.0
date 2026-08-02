import { useEffect, useLayoutEffect, useMemo, useRef } from 'react'
import { useFrame } from '@react-three/fiber'
import { Billboard, Text } from '@react-three/drei'
import * as THREE from 'three'
import {
  CITY_BASE_Y,
  CITY_GRID_HALF,
  CITY_WORLD_SIZE,
  ROAD_SPACING,
  ROAD_WIDTH,
  TILE_SIZE,
  terrainHeight,
  terrainTone,
} from '../engine/cityEngine'
import { useCityStore } from '../engine/cityStore'

function exposeRenderingMetadata(patch) {
  if (typeof window === 'undefined' || !import.meta.env.DEV) return
  window.__REALCITY_RENDERING__ = {
    ...(window.__REALCITY_RENDERING__ || {}),
    ...patch,
  }
}

function makeTerrainGeometry() {
  const segments = 140
  const geometry = new THREE.PlaneGeometry(CITY_WORLD_SIZE, CITY_WORLD_SIZE, segments, segments)
  geometry.rotateX(-Math.PI / 2)
  const positions = geometry.attributes.position
  const colors = new Float32Array(positions.count * 3)

  for (let i = 0; i < positions.count; i += 1) {
    const x = positions.getX(i)
    const z = positions.getZ(i)
    const distance = Math.hypot(x, z)
    const h = distance < CITY_GRID_HALF * 1.08 ? CITY_BASE_Y - 0.22 : terrainHeight(x, z)
    positions.setY(i, h)
    const tone = terrainTone(x, z)
    colors[i * 3] = tone[0]
    colors[i * 3 + 1] = tone[1]
    colors[i * 3 + 2] = tone[2]
  }

  geometry.setAttribute('color', new THREE.BufferAttribute(colors, 3))
  geometry.computeVertexNormals()
  return geometry
}

function makeRoadGeometry(roads) {
  const vertices = []
  const normals = []
  const uvs = []

  for (const road of roads) {
    const hw = road.width / 2
    if (road.axis === 'x') {
      const z0 = road.z - hw
      const z1 = road.z + hw
      const y = CITY_BASE_Y + 0.1
      vertices.push(road.from, y, z0, road.to, y, z0, road.to, y, z1, road.from, y, z0, road.to, y, z1, road.from, y, z1)
      uvs.push(0, 0, 36, 0, 36, 1, 0, 0, 36, 1, 0, 1)
    } else {
      const x0 = road.x - hw
      const x1 = road.x + hw
      const y = CITY_BASE_Y + 0.1
      vertices.push(x0, y, road.from, x1, y, road.from, x1, y, road.to, x0, y, road.from, x1, y, road.to, x0, y, road.to)
      uvs.push(0, 0, 1, 0, 1, 36, 0, 0, 1, 36, 0, 36)
    }
    for (let i = 0; i < 6; i += 1) normals.push(0, 1, 0)
  }

  const geometry = new THREE.BufferGeometry()
  geometry.setAttribute('position', new THREE.Float32BufferAttribute(vertices, 3))
  geometry.setAttribute('normal', new THREE.Float32BufferAttribute(normals, 3))
  geometry.setAttribute('uv', new THREE.Float32BufferAttribute(uvs, 2))
  return geometry
}

function makeRoadTexture() {
  const canvas = document.createElement('canvas')
  canvas.width = 512
  canvas.height = 512
  const ctx = canvas.getContext('2d')
  ctx.fillStyle = '#242a2c'
  ctx.fillRect(0, 0, 512, 512)
  ctx.fillStyle = 'rgba(255,255,255,0.045)'
  for (let i = 0; i < 190; i += 1) {
    ctx.fillRect(Math.random() * 512, Math.random() * 512, 2 + Math.random() * 22, 1)
  }
  ctx.fillStyle = 'rgba(0,0,0,0.12)'
  for (let i = 0; i < 130; i += 1) {
    ctx.fillRect(Math.random() * 512, Math.random() * 512, 4 + Math.random() * 32, 1)
  }
  ctx.strokeStyle = 'rgba(255,255,255,0.12)'
  ctx.lineWidth = 1
  for (let p = 0; p <= 512; p += 64) {
    ctx.beginPath()
    ctx.moveTo(0, p + 0.5)
    ctx.lineTo(512, p + 0.5)
    ctx.stroke()
  }
  ctx.strokeStyle = 'rgba(235,241,244,0.08)'
  ctx.lineWidth = 1
  ctx.beginPath()
  ctx.moveTo(34, 0)
  ctx.lineTo(34, 512)
  ctx.moveTo(478, 0)
  ctx.lineTo(478, 512)
  ctx.moveTo(0, 34)
  ctx.lineTo(512, 34)
  ctx.moveTo(0, 478)
  ctx.lineTo(512, 478)
  ctx.stroke()
  const texture = new THREE.CanvasTexture(canvas)
  texture.wrapS = texture.wrapT = THREE.RepeatWrapping
  texture.colorSpace = THREE.SRGBColorSpace
  return texture
}

function makePavementTexture() {
  const canvas = document.createElement('canvas')
  canvas.width = 512
  canvas.height = 512
  const ctx = canvas.getContext('2d')
  ctx.fillStyle = '#676967'
  ctx.fillRect(0, 0, 512, 512)
  ctx.strokeStyle = 'rgba(46, 50, 50, 0.74)'
  ctx.lineWidth = 2
  for (let p = 0; p <= 512; p += 64) {
    ctx.beginPath()
    ctx.moveTo(p, 0)
    ctx.lineTo(p, 512)
    ctx.moveTo(0, p)
    ctx.lineTo(512, p)
    ctx.stroke()
  }
  ctx.fillStyle = 'rgba(255,255,255,0.035)'
  for (let i = 0; i < 140; i += 1) {
    ctx.fillRect(Math.random() * 512, Math.random() * 512, 1 + Math.random() * 18, 1)
  }
  ctx.fillStyle = 'rgba(0,0,0,0.035)'
  for (let i = 0; i < 110; i += 1) {
    ctx.fillRect(Math.random() * 512, Math.random() * 512, 2 + Math.random() * 20, 1)
  }
  const texture = new THREE.CanvasTexture(canvas)
  texture.wrapS = texture.wrapT = THREE.RepeatWrapping
  texture.repeat.set(1.5, 1.5)
  texture.colorSpace = THREE.SRGBColorSpace
  return texture
}

function splitIntervals(from, to, cuts, minLength = 12) {
  const sorted = cuts
    .map(cut => ({ from: Math.max(from, cut.from), to: Math.min(to, cut.to) }))
    .filter(cut => cut.to > from && cut.from < to)
    .sort((a, b) => a.from - b.from)
  const intervals = []
  let cursor = from
  for (const cut of sorted) {
    if (cut.from - cursor >= minLength) intervals.push({ from: cursor, to: cut.from })
    cursor = Math.max(cursor, cut.to)
  }
  if (to - cursor >= minLength) intervals.push({ from: cursor, to })
  return intervals
}

function makeSidewalkSegments(roads) {
  const width = 6.4
  const cornerClearance = 8.5
  const sidewalks = []
  for (const road of roads) {
    const crossingRoads = roads.filter(item => item.axis !== road.axis)
    const cuts = crossingRoads.map(cross => {
      const center = road.axis === 'x' ? cross.x : cross.z
      const half = cross.width / 2 + cornerClearance
      return { from: center - half, to: center + half }
    })
    const intervals = splitIntervals(road.from, road.to, cuts)
    for (const interval of intervals) {
      const length = interval.to - interval.from
      if (road.axis === 'x') {
        const x = (interval.from + interval.to) / 2
        sidewalks.push({
          axis: 'x',
          x,
          z: road.z - road.width / 2 - width / 2 - 1.0,
          sx: length,
          sz: width,
          curbX: x,
          curbZ: road.z - road.width / 2 - 0.34,
          curbSx: length,
          curbSz: 0.52,
        })
        sidewalks.push({
          axis: 'x',
          x,
          z: road.z + road.width / 2 + width / 2 + 1.0,
          sx: length,
          sz: width,
          curbX: x,
          curbZ: road.z + road.width / 2 + 0.34,
          curbSx: length,
          curbSz: 0.52,
        })
      } else {
        const z = (interval.from + interval.to) / 2
        sidewalks.push({
          axis: 'z',
          x: road.x - road.width / 2 - width / 2 - 1.0,
          z,
          sx: width,
          sz: length,
          curbX: road.x - road.width / 2 - 0.34,
          curbZ: z,
          curbSx: 0.52,
          curbSz: length,
        })
        sidewalks.push({
          axis: 'z',
          x: road.x + road.width / 2 + width / 2 + 1.0,
          z,
          sx: width,
          sz: length,
          curbX: road.x + road.width / 2 + 0.34,
          curbZ: z,
          curbSx: 0.52,
          curbSz: length,
        })
      }
    }
  }
  return sidewalks
}

function UrbanBase({ roads }) {
  const blockRef = useRef()
  const curbRef = useRef()
  const curbLineRef = useRef()
  const sidewalkRef = useRef()
  const pavementTexture = useMemo(() => makePavementTexture(), [])
  const blocks = useMemo(() => {
    const items = []
    for (let x = -CITY_GRID_HALF + ROAD_SPACING / 2; x < CITY_GRID_HALF; x += ROAD_SPACING) {
      for (let z = -CITY_GRID_HALF + ROAD_SPACING / 2; z < CITY_GRID_HALF; z += ROAD_SPACING) {
        const distance = Math.hypot(x, z)
        if (distance > 930) continue
        const isPlaza = distance < 132
        items.push({ x, z, size: ROAD_SPACING - ROAD_WIDTH - (isPlaza ? 2 : 10), plaza: isPlaza })
      }
    }
    return items
  }, [])
  const sidewalks = useMemo(() => makeSidewalkSegments(roads), [roads])

  useEffect(() => {
    exposeRenderingMetadata({
      streetHierarchy: {
        segmentedSidewalks: true,
        sidewalkSegments: sidewalks.length,
        sourceRoads: roads.length,
        curbEdgeSegments: sidewalks.length,
        intersectionGapMeters: 17,
        roadMaterial: 'dark asphalt',
        sidewalkMaterial: 'raised light pavers',
        roadSidewalkContrast: 'raised pale sidewalk slabs, bright curb lips, white road-edge paint',
        curbLipMeters: 0.52,
        sidewalkElevationMeters: 0.12,
      },
    })
  }, [roads.length, sidewalks.length])

  useLayoutEffect(() => {
    if (!blockRef.current || !curbRef.current || !curbLineRef.current || !sidewalkRef.current) return
    const dummy = new THREE.Object3D()
    const color = new THREE.Color()
    blocks.forEach((block, i) => {
      dummy.position.set(block.x, CITY_BASE_Y + 0.02, block.z)
      dummy.scale.set(block.size, 0.12, block.size)
      dummy.updateMatrix()
      blockRef.current.setMatrixAt(i, dummy.matrix)
      blockRef.current.setColorAt(i, color.set(block.plaza ? '#d7d2c6' : '#e0dfd4'))

      dummy.position.set(block.x, CITY_BASE_Y + 0.12, block.z)
      dummy.scale.set(block.size + 2.6, 0.16, block.size + 2.6)
      dummy.updateMatrix()
      curbRef.current.setMatrixAt(i, dummy.matrix)
    })
    sidewalks.forEach((sidewalk, i) => {
      dummy.position.set(sidewalk.x, CITY_BASE_Y + 0.155, sidewalk.z)
      dummy.scale.set(sidewalk.sx, 0.05, sidewalk.sz)
      dummy.updateMatrix()
      sidewalkRef.current.setMatrixAt(i, dummy.matrix)

      dummy.position.set(sidewalk.curbX, CITY_BASE_Y + 0.235, sidewalk.curbZ)
      dummy.scale.set(sidewalk.curbSx, 0.13, sidewalk.curbSz)
      dummy.updateMatrix()
      curbLineRef.current.setMatrixAt(i, dummy.matrix)
    })
    blockRef.current.instanceMatrix.needsUpdate = true
    curbRef.current.instanceMatrix.needsUpdate = true
    curbLineRef.current.instanceMatrix.needsUpdate = true
    sidewalkRef.current.instanceMatrix.needsUpdate = true
    if (blockRef.current.instanceColor) blockRef.current.instanceColor.needsUpdate = true
  }, [blocks, sidewalks])

  return (
    <>
      <mesh rotation={[-Math.PI / 2, 0, 0]} position={[0, CITY_BASE_Y - 0.03, 0]}>
        <planeGeometry args={[CITY_GRID_HALF * 2.08, CITY_GRID_HALF * 2.08]} />
        <meshBasicMaterial color="#444845" toneMapped={false} />
      </mesh>
      <instancedMesh ref={curbRef} args={[undefined, undefined, blocks.length]} frustumCulled={false}>
        <boxGeometry args={[1, 1, 1]} />
        <meshBasicMaterial color="#343839" toneMapped={false} />
      </instancedMesh>
      <instancedMesh ref={curbLineRef} args={[undefined, undefined, sidewalks.length]} frustumCulled={false}>
        <boxGeometry args={[1, 1, 1]} />
        <meshBasicMaterial color="#eee8cf" toneMapped={false} />
      </instancedMesh>
      <instancedMesh ref={sidewalkRef} args={[undefined, undefined, sidewalks.length]} frustumCulled={false}>
        <boxGeometry args={[1, 1, 1]} />
        <meshBasicMaterial map={pavementTexture} color="#f0eee4" toneMapped={false} />
      </instancedMesh>
      <instancedMesh ref={blockRef} args={[undefined, undefined, blocks.length]} frustumCulled={false}>
        <boxGeometry args={[1, 1, 1]} />
        <meshBasicMaterial map={pavementTexture} color="#ffffff" vertexColors toneMapped={false} />
      </instancedMesh>
    </>
  )
}

function RoadMarkings({ roads }) {
  const centerRef = useRef()
  const laneRef = useRef()
  const edgeRef = useRef()
  const curbPaintRef = useRef()
  const centerDashes = useMemo(() => {
    const items = []
    for (const road of roads) {
      const dashLength = road.main ? 16 : 9.5
      const step = road.main ? 52 : 38
      for (let p = road.from + 30; p < road.to - 30; p += step) {
        items.push(road.axis === 'x'
          ? { x: p, z: road.z, sx: dashLength, sz: road.main ? 0.42 : 0.34 }
          : { x: road.x, z: p, sx: road.main ? 0.42 : 0.34, sz: dashLength })
      }
    }
    return items
  }, [roads])
  const laneDashes = useMemo(() => {
    const items = []
    for (const road of roads) {
      if (!road.main) continue
      const offset = road.width * 0.27
      for (let p = road.from + 24; p < road.to - 24; p += 34) {
        if (road.axis === 'x') {
          items.push({ x: p, z: road.z - offset, sx: 7.4, sz: 0.18 })
          items.push({ x: p, z: road.z + offset, sx: 7.4, sz: 0.18 })
        } else {
          items.push({ x: road.x - offset, z: p, sx: 0.18, sz: 7.4 })
          items.push({ x: road.x + offset, z: p, sx: 0.18, sz: 7.4 })
        }
      }
    }
    return items
  }, [roads])
  const edges = useMemo(() => roads.flatMap(road => {
    if (road.axis === 'x') {
      const x = (road.from + road.to) / 2
      const sx = road.to - road.from
      return [
        { x, z: road.z - road.width / 2 + 0.18, sx, sz: 0.16 },
        { x, z: road.z + road.width / 2 - 0.18, sx, sz: 0.16 },
      ]
    }
    const z = (road.from + road.to) / 2
    const sz = road.to - road.from
    return [
      { x: road.x - road.width / 2 + 0.18, z, sx: 0.16, sz },
      { x: road.x + road.width / 2 - 0.18, z, sx: 0.16, sz },
    ]
  }), [roads])
  const curbPaints = useMemo(() => roads.flatMap(road => {
    const inset = road.width / 2 + 0.62
    if (road.axis === 'x') {
      const x = (road.from + road.to) / 2
      const sx = road.to - road.from
      return [
        { x, z: road.z - inset, sx, sz: 0.1 },
        { x, z: road.z + inset, sx, sz: 0.1 },
      ]
    }
    const z = (road.from + road.to) / 2
    const sz = road.to - road.from
    return [
      { x: road.x - inset, z, sx: 0.1, sz },
      { x: road.x + inset, z, sx: 0.1, sz },
    ]
  }), [roads])

  useEffect(() => {
    exposeRenderingMetadata({
      roadMarkings: {
        centerLineDashes: centerDashes.length,
        laneDividerDashes: laneDashes.length,
        roadEdgeLines: edges.length,
        curbPaintLines: curbPaints.length,
        hierarchy: 'yellow center dashes, white lane dividers, white edge lines, pale curb paint',
        texturePolicy: 'asphalt texture carries grit only; navigational paint is separate geometry for readable boundaries',
      },
    })
  }, [centerDashes.length, laneDashes.length, edges.length, curbPaints.length])

  useLayoutEffect(() => {
    if (!centerRef.current || !laneRef.current || !edgeRef.current || !curbPaintRef.current) return
    const dummy = new THREE.Object3D()
    centerDashes.forEach((stripe, i) => {
      dummy.position.set(stripe.x, CITY_BASE_Y + 0.17, stripe.z)
      dummy.scale.set(stripe.sx, 0.035, stripe.sz)
      dummy.updateMatrix()
      centerRef.current.setMatrixAt(i, dummy.matrix)
    })
    laneDashes.forEach((dash, i) => {
      dummy.position.set(dash.x, CITY_BASE_Y + 0.178, dash.z)
      dummy.scale.set(dash.sx, 0.024, dash.sz)
      dummy.updateMatrix()
      laneRef.current.setMatrixAt(i, dummy.matrix)
    })
    edges.forEach((edge, i) => {
      dummy.position.set(edge.x, CITY_BASE_Y + 0.185, edge.z)
      dummy.scale.set(edge.sx, 0.036, edge.sz)
      dummy.updateMatrix()
      edgeRef.current.setMatrixAt(i, dummy.matrix)
    })
    curbPaints.forEach((edge, i) => {
      dummy.position.set(edge.x, CITY_BASE_Y + 0.255, edge.z)
      dummy.scale.set(edge.sx, 0.028, edge.sz)
      dummy.updateMatrix()
      curbPaintRef.current.setMatrixAt(i, dummy.matrix)
    })
    centerRef.current.instanceMatrix.needsUpdate = true
    laneRef.current.instanceMatrix.needsUpdate = true
    edgeRef.current.instanceMatrix.needsUpdate = true
    curbPaintRef.current.instanceMatrix.needsUpdate = true
  }, [centerDashes, laneDashes, edges, curbPaints])

  return (
    <>
      <instancedMesh ref={curbPaintRef} args={[undefined, undefined, curbPaints.length]} frustumCulled={false}>
        <boxGeometry args={[1, 1, 1]} />
        <meshBasicMaterial color="#f7f2da" toneMapped={false} />
      </instancedMesh>
      <instancedMesh ref={edgeRef} args={[undefined, undefined, edges.length]} frustumCulled={false}>
        <boxGeometry args={[1, 1, 1]} />
        <meshBasicMaterial color="#f2f4ec" toneMapped={false} />
      </instancedMesh>
      <instancedMesh ref={laneRef} args={[undefined, undefined, laneDashes.length]} frustumCulled={false}>
        <boxGeometry args={[1, 1, 1]} />
        <meshBasicMaterial color="#f6f8f0" toneMapped={false} />
      </instancedMesh>
      <instancedMesh ref={centerRef} args={[undefined, undefined, centerDashes.length]} frustumCulled={false}>
        <boxGeometry args={[1, 1, 1]} />
        <meshBasicMaterial color="#f2c94c" toneMapped={false} />
      </instancedMesh>
    </>
  )
}

function makeWindowTexture(type) {
  const canvas = document.createElement('canvas')
  canvas.width = 512
  canvas.height = 1024
  const ctx = canvas.getContext('2d')
  const wall = {
    skyscraper: ['#b8e3f4', '#6f9db1'],
    office: ['#dfe5df', '#a8b4ae'],
    apartment: ['#e2c8a5', '#b58f68'],
    house: ['#e2a77d', '#b87860'],
  }[type] || ['#c5ced1', '#8d9aa1']
  const cols = type === 'skyscraper' ? 10 : type === 'house' ? 4 : type === 'office' ? 7 : 6
  const rows = type === 'skyscraper' ? 30 : type === 'house' ? 6 : 18
  const gradient = ctx.createLinearGradient(0, 0, 512, 1024)
  gradient.addColorStop(0, wall[0])
  gradient.addColorStop(0.58, wall[1])
  gradient.addColorStop(1, wall[0])
  ctx.fillStyle = gradient
  ctx.fillRect(0, 0, 512, 1024)

  ctx.fillStyle = 'rgba(255,255,255,0.08)'
  for (let i = 0; i < 520; i += 1) {
    const x = (i * 47) % 512
    const y = (i * 83) % 1024
    ctx.fillRect(x, y, 1 + (i % 11), 1)
  }
  ctx.fillStyle = type === 'house' ? 'rgba(76, 47, 35, 0.1)' : 'rgba(255,255,255,0.075)'
  for (let r = 0; r < rows; r += 1) {
    const y = (r / rows) * 1024
    ctx.fillRect(0, y, 512, 3)
    if (type !== 'house' && r % 4 === 0) ctx.fillRect(0, y + 7, 512, 1.5)
  }
  ctx.strokeStyle = type === 'house' ? 'rgba(80,54,40,0.32)' : 'rgba(255,255,255,0.24)'
  ctx.lineWidth = 3
  for (let c = 0; c <= cols; c += 1) {
    const x = (c / cols) * 512
    ctx.beginPath()
    ctx.moveTo(x, 0)
    ctx.lineTo(x, 1024)
    ctx.stroke()
  }
  for (let r = 0; r < rows; r += 1) {
    for (let c = 0; c < cols; c += 1) {
      const lit = (r * 17 + c * 11 + type.length) % 5 !== 0
      const cellW = 512 / cols
      const cellH = 1024 / rows
      const x = c * cellW + cellW * 0.2
      const y = r * cellH + cellH * 0.25
      const w = cellW * 0.58
      const h = cellH * 0.5
      ctx.fillStyle = type === 'house' ? 'rgba(91,58,42,0.38)' : 'rgba(12,24,32,0.32)'
      ctx.fillRect(x - 3, y - 3, w + 6, h + 6)
      ctx.fillStyle = lit ? (type === 'house' ? '#ffd98a' : '#dff5ff') : (type === 'house' ? '#6b5148' : '#48616f')
      ctx.fillRect(x, y, w, h)
      ctx.fillStyle = lit ? 'rgba(255,255,255,0.42)' : 'rgba(148,188,204,0.22)'
      ctx.fillRect(x + w * 0.08, y + h * 0.08, w * 0.18, h * 0.82)
      ctx.fillStyle = 'rgba(255,255,255,0.22)'
      ctx.fillRect(x + w * 0.54, y + h * 0.08, w * 0.08, h * 0.82)
      ctx.strokeStyle = type === 'house' ? 'rgba(255,245,225,0.18)' : 'rgba(210,242,255,0.3)'
      ctx.lineWidth = 1
      ctx.strokeRect(x + 1, y + 1, w - 2, h - 2)
      if (type === 'apartment' && r % 3 === 1) {
        ctx.fillStyle = 'rgba(240,244,245,0.42)'
        ctx.fillRect(x - 8, y + h + 5, w + 16, 5)
      }
    }
  }
  ctx.strokeStyle = type === 'apartment' || type === 'house' ? 'rgba(68,45,32,0.34)' : 'rgba(20,28,35,0.2)'
  ctx.lineWidth = 4
  for (let r = 1; r < rows; r += 1) {
    const y = (r / rows) * 1024
      ctx.beginPath()
      ctx.moveTo(0, y)
      ctx.lineTo(512, y)
      ctx.stroke()
  }
  ctx.strokeStyle = type === 'house' ? 'rgba(255,245,225,0.22)' : 'rgba(255,255,255,0.28)'
  ctx.lineWidth = 2
  ctx.beginPath()
  ctx.moveTo(24, 0)
  ctx.lineTo(24, 1024)
  ctx.moveTo(488, 0)
  ctx.lineTo(488, 1024)
  ctx.stroke()
  const texture = new THREE.CanvasTexture(canvas)
  texture.wrapS = texture.wrapT = THREE.RepeatWrapping
  texture.repeat.set(1, type === 'skyscraper' ? 3.2 : type === 'office' ? 2.1 : type === 'apartment' ? 1.55 : 1)
  texture.colorSpace = THREE.SRGBColorSpace
  texture.anisotropy = 4
  return texture
}

function makeGableRoofGeometry() {
  const vertices = [
    -0.5, 0, -0.5, 0.5, 0, -0.5, 0, 1, -0.5,
    0.5, 0, 0.5, -0.5, 0, 0.5, 0, 1, 0.5,
    -0.5, 0, -0.5, -0.5, 0, 0.5, 0, 1, 0.5,
    -0.5, 0, -0.5, 0, 1, 0.5, 0, 1, -0.5,
    0.5, 0, -0.5, 0, 1, -0.5, 0, 1, 0.5,
    0.5, 0, -0.5, 0, 1, 0.5, 0.5, 0, 0.5,
    -0.5, 0, -0.5, 0.5, 0, 0.5, -0.5, 0, 0.5,
    -0.5, 0, -0.5, 0.5, 0, -0.5, 0.5, 0, 0.5,
  ]
  const geometry = new THREE.BufferGeometry()
  geometry.setAttribute('position', new THREE.Float32BufferAttribute(vertices, 3))
  geometry.computeVertexNormals()
  return geometry
}

function worldOffset(building, lx = 0, lz = 0) {
  const cos = Math.cos(building.rot || 0)
  const sin = Math.sin(building.rot || 0)
  return {
    x: building.x + lx * cos + lz * sin,
    z: building.z - lx * sin + lz * cos,
  }
}

function bodyColor(type) {
  return {
    skyscraper: '#b6d4e4',
    office: '#cbd3cf',
    apartment: '#d4b99a',
    house: '#d29a79',
  }[type] || '#b9c0c2'
}

function roofColor(building) {
  if (building.type === 'house') {
    return {
      brick: '#9a4f3d',
      stucco: '#9b6b58',
      timber: '#6d5749',
      painted: '#446a80',
    }[building.form?.facade] || '#825642'
  }
  if (building.type === 'skyscraper') return '#2d4b5c'
  if (building.type === 'office') return '#697981'
  return '#82796e'
}

function partFromBuilding(building, { lx = 0, lz = 0, yOffset = 0, sx = building.w, sy = building.h, sz = building.d, rx = 0, rz = 0, color = bodyColor(building.type), textureType = building.type }) {
  const position = worldOffset(building, lx, lz)
  return {
    building,
    textureType,
    localX: lx,
    localZ: lz,
    x: position.x,
    z: position.z,
    y: building.y + yOffset + sy / 2,
    sx,
    sy,
    sz,
    rot: building.rot || 0,
    rx,
    rz,
    color,
  }
}

function roofPartFromBuilding(building, { lx = 0, lz = 0, baseY = building.h, sx = building.w, sy = 1, sz = building.d, rx = 0, rz = 0, centered = false, color = roofColor(building) }) {
  const position = worldOffset(building, lx, lz)
  return {
    building,
    localX: lx,
    localZ: lz,
    x: position.x,
    z: position.z,
    y: building.y + baseY + (centered ? sy / 2 : 0),
    sx,
    sy,
    sz,
    rot: building.rot || 0,
    rx,
    rz,
    color,
  }
}

function entryFaceForBuilding(building) {
  return building.facadePlan?.entryFace || building.entryFace || building.interior?.entryFace || 'south'
}

function faceLengthForBuilding(building, face) {
  return face === 'north' || face === 'south' ? building.w : building.d
}

function faceAttachedPart(building, face, { along = 0, outward = 0, yOffset = 0, width = faceLengthForBuilding(building, face), height = 1, depth = 1, color = bodyColor(building.type), textureType = building.type }) {
  if (face === 'north') {
    return partFromBuilding(building, { lx: along, lz: building.d / 2 + depth / 2 + outward, yOffset, sx: width, sy: height, sz: depth, color, textureType })
  }
  if (face === 'south') {
    return partFromBuilding(building, { lx: along, lz: -building.d / 2 - depth / 2 - outward, yOffset, sx: width, sy: height, sz: depth, color, textureType })
  }
  if (face === 'east') {
    return partFromBuilding(building, { lx: building.w / 2 + depth / 2 + outward, lz: along, yOffset, sx: depth, sy: height, sz: width, color, textureType })
  }
  return partFromBuilding(building, { lx: -building.w / 2 - depth / 2 - outward, lz: along, yOffset, sx: depth, sy: height, sz: width, color, textureType })
}

function mainMassFor(building) {
  const form = building.form || {}
  const profile = form.profile || 'slab'
  if (building.type === 'house') {
    const sy = Math.max(3.2, building.h * (form.bodyRatio || 0.72))
    const row = profile === 'rowhouse'
    return partFromBuilding(building, {
      sx: building.w * (row ? 1.08 : 0.92),
      sy,
      sz: building.d * (row ? 0.82 : 0.9),
      color: bodyColor(building.type),
    })
  }

  if (building.type === 'skyscraper') {
    const podiumH = Math.min(13, building.h * 0.16)
    const narrow = profile === 'needle' ? 0.58 : profile === 'setback' ? 0.68 : 0.76
    return partFromBuilding(building, {
      lx: profile === 'twin_core' ? -building.w * 0.16 : 0,
      yOffset: podiumH * 0.72,
      sx: building.w * narrow,
      sy: Math.max(22, building.h - podiumH * 0.72),
      sz: building.d * (profile === 'needle' ? 0.6 : 0.76),
    })
  }

  if (building.type === 'office') {
    const podiumH = Math.min(8, building.h * 0.24)
    const compact = profile === 'podium_tower' || profile === 'offset_core'
    return partFromBuilding(building, {
      lx: profile === 'offset_core' ? building.w * 0.08 : 0,
      lz: profile === 'atrium' ? -building.d * 0.08 : 0,
      yOffset: compact ? podiumH * 0.85 : 0,
      sx: building.w * (compact ? 0.72 : 0.92),
      sy: compact ? building.h - podiumH * 0.85 : building.h,
      sz: building.d * (compact ? 0.78 : 0.9),
    })
  }

  const bar = profile === 'bar' || profile === 'balcony_stack'
  return partFromBuilding(building, {
    sx: building.w * (bar ? 1.05 : 0.82),
    sy: building.h * (profile === 'terraced' ? 0.88 : 1),
    sz: building.d * (bar ? 0.62 : 0.94),
  })
}

function createBuildingRenderData(buildings) {
  const bodies = { skyscraper: [], office: [], apartment: [], house: [] }
  const podiums = []
  const wings = []
  const flatRoofs = []
  const gableRoofs = []
  const hipRoofs = []
  const shedRoofs = []
  const crowns = []
  const balconies = []
  const porches = []
  const garages = []
  const chimneys = []
  const antennas = []

  for (const building of buildings) {
    const form = building.form || {}
    const body = mainMassFor(building)
    bodies[building.type]?.push(body)

    if (building.type !== 'house' && form.podium) {
      const podiumH = Math.min(building.type === 'skyscraper' ? 13 : 8, building.h * 0.22)
      podiums.push(partFromBuilding(building, {
        sx: building.w * 1.08,
        sy: podiumH,
        sz: building.d * 1.05,
        color: building.type === 'apartment' ? '#b99778' : '#7d898a',
      }))
    }

    if (form.wing) {
      const side = building.tint > 0.5 ? 1 : -1
      if (building.type === 'house') {
        wings.push(partFromBuilding(building, {
          lx: side * building.w * 0.26,
          lz: building.d * 0.08,
          sx: building.w * 0.42,
          sy: body.sy * 0.76,
          sz: building.d * 0.52,
          color: '#b8795e',
        }))
      } else {
        wings.push(partFromBuilding(building, {
          lx: side * building.w * 0.28,
          lz: building.d * 0.05,
          sx: building.w * 0.42,
          sy: Math.max(6, body.sy * 0.72),
          sz: building.d * (building.type === 'apartment' ? 0.88 : 0.62),
          color: building.type === 'office' ? '#aeb9b8' : '#b89b7b',
        }))
      }
    }

    const topY = body.y - building.y + body.sy / 2
    if (building.type === 'house') {
      const roofH = 1.15 + building.tint * 1.35
      const roofW = body.sx * 1.16
      const roofD = body.sz * 1.16
      if (form.roof === 'hip') {
        hipRoofs.push(roofPartFromBuilding(building, { baseY: topY, sx: roofW / 2, sy: roofH, sz: roofD / 2, centered: true }))
      } else if (form.roof === 'flat') {
        flatRoofs.push(roofPartFromBuilding(building, { baseY: topY, sx: roofW, sy: 0.38, sz: roofD, centered: true }))
      } else if (form.roof === 'shed') {
        shedRoofs.push(roofPartFromBuilding(building, { baseY: topY + 0.12, sx: roofW, sy: 0.42, sz: roofD, rx: -0.12, centered: true }))
      } else {
        gableRoofs.push(roofPartFromBuilding(building, { baseY: topY, sx: roofW, sy: roofH, sz: roofD }))
      }

      if (form.porch) {
        const face = entryFaceForBuilding(building)
        porches.push(faceAttachedPart(building, face, {
          width: Math.min(5.2, faceLengthForBuilding(building, face) * 0.48),
          height: 0.18,
          depth: 2.4,
          yOffset: 2.25,
          color: '#5d4a3a',
        }))
      }
      if (form.garage) {
        const face = entryFaceForBuilding(building)
        const faceLen = faceLengthForBuilding(building, face)
        garages.push(faceAttachedPart(building, face, {
          along: (building.tint > 0.5 ? 1 : -1) * faceLen * 0.26,
          width: Math.min(faceLen * 0.34, 4.4),
          height: Math.min(2.5, body.sy * 0.62),
          depth: Math.min(4.8, Math.max(2.8, body.sz * 0.42)),
          color: '#8c8175',
        }))
      }
      if (form.chimney) {
        chimneys.push(roofPartFromBuilding(building, {
          lx: body.sx * 0.26,
          lz: -body.sz * 0.12,
          baseY: topY + roofH * 0.48,
          sx: 0.42,
          sy: 1.55,
          sz: 0.42,
          centered: true,
          color: '#4f342b',
        }))
      }
    } else {
      flatRoofs.push(roofPartFromBuilding(building, {
        lx: body.localX,
        lz: body.localZ,
        baseY: topY,
        sx: body.sx * 1.02,
        sy: 0.5,
        sz: body.sz * 1.02,
        centered: true,
      }))

      if (building.type === 'skyscraper' || form.roof === 'crown') {
        crowns.push(roofPartFromBuilding(building, {
          lx: body.localX,
          lz: body.localZ,
          baseY: topY + 0.3,
          sx: body.sx * 0.54,
          sy: Math.max(1.2, building.h * 0.035),
          sz: body.sz * 0.54,
          centered: true,
          color: '#2c4654',
        }))
      }
      if (form.roof === 'antenna') {
        antennas.push(roofPartFromBuilding(building, {
          lx: body.localX,
          lz: body.localZ,
          baseY: topY + 1.4,
          sx: 0.12,
          sy: Math.max(6, building.h * 0.12),
          sz: 0.12,
          centered: true,
          color: '#c9d2d7',
        }))
      }
      if (building.type === 'apartment' && form.balconies) {
        const face = entryFaceForBuilding(building)
        const width = Math.min(faceLengthForBuilding(building, face) * 0.62, 9.2)
        const floors = Math.min(8, Math.max(3, Math.floor(building.h / 4.2)))
        for (let floor = 1; floor <= floors; floor += 1) {
          balconies.push(faceAttachedPart(building, face, {
            yOffset: Math.min(building.h - 1.2, floor * (building.h / (floors + 1))),
            width,
            height: 0.14,
            depth: 0.72,
            color: '#d7d0c4',
          }))
        }
      }
    }
  }

  return { bodies, podiums, wings, flatRoofs, gableRoofs, hipRoofs, shedRoofs, crowns, balconies, porches, garages, chimneys, antennas }
}

function applyPart(mesh, index, part, dummy, color) {
  dummy.position.set(part.x, part.y, part.z)
  dummy.rotation.set(part.rx || 0, part.rot || 0, part.rz || 0)
  dummy.scale.set(part.sx, part.sy, part.sz)
  dummy.updateMatrix()
  mesh.setMatrixAt(index, dummy.matrix)
  if (color) {
    const lift = part.textureType === 'house' ? 0.5 : part.textureType === 'apartment' ? 0.36 : part.textureType ? 0.24 : 0
    color.set(part.color)
    if (lift) color.lerp(new THREE.Color('#fbf7ed'), lift)
    mesh.setColorAt(index, color.lerp(new THREE.Color('#44525c'), (part.building?.tint || 0) * 0.04))
  }
}

function Buildings({ buildings }) {
  const refs = useRef({})
  const detailRefs = useRef({})
  const materialRefs = useRef({})
  const textures = useMemo(() => ({
    skyscraper: makeWindowTexture('skyscraper'),
    office: makeWindowTexture('office'),
    apartment: makeWindowTexture('apartment'),
    house: makeWindowTexture('house'),
  }), [])
  const gableGeometry = useMemo(() => makeGableRoofGeometry(), [])
  const renderData = useMemo(() => createBuildingRenderData(buildings), [buildings])

  useEffect(() => {
    exposeRenderingMetadata({
      facades: {
        proceduralWindowTexture: true,
        textureSize: '512x1024',
        wallPalettes: ['glass tower', 'office stone', 'apartment brick', 'house stucco'],
        hasMullions: true,
        hasLitWindows: true,
        materialPass: 'bright wall color plus reflective glass grid',
      },
    })
  }, [])

  useLayoutEffect(() => {
    const dummy = new THREE.Object3D()
    const color = new THREE.Color()
    for (const [type, items] of Object.entries(renderData.bodies)) {
      const mesh = refs.current[type]
      if (!mesh) continue
      for (let i = 0; i < items.length; i += 1) {
        applyPart(mesh, i, items[i], dummy, color)
      }
      mesh.instanceMatrix.needsUpdate = true
      if (mesh.instanceColor) mesh.instanceColor.needsUpdate = true
    }
    for (const [key, items] of Object.entries(renderData)) {
      if (key === 'bodies') continue
      const mesh = detailRefs.current[key]
      if (!mesh) continue
      for (let i = 0; i < items.length; i += 1) applyPart(mesh, i, items[i], dummy, color)
      mesh.instanceMatrix.needsUpdate = true
      if (mesh.instanceColor) mesh.instanceColor.needsUpdate = true
    }
  }, [renderData])

  useFrame(() => {
    const sky = useCityStore.getState().sky
    const reflection = sky?.reflection ?? 1
    const sunlight = sky?.sunlight ?? 1
    const nightBoost = sky?.phase === 'night' ? 1.7 : sky?.phase === 'golden-hour' || sky?.phase === 'dawn' ? 1.2 : 1
    const settings = {
      skyscraper: { env: 2.05, emissive: 0.42 },
      office: { env: 1.28, emissive: 0.3 },
      apartment: { env: 0.86, emissive: 0.31 },
      house: { env: 0.68, emissive: 0.27 },
    }
    for (const [type, material] of Object.entries(materialRefs.current)) {
      const setting = settings[type] || settings.office
      material.envMapIntensity = setting.env * reflection
      material.emissiveIntensity = setting.emissive * nightBoost * Math.max(0.92, 1.18 - sunlight * 0.18)
    }
  })

  return (
    <>
      {Object.entries(renderData.bodies).map(([type, items]) => {
        if (!items.length) return null
        const isGlass = type === 'skyscraper'
        return (
          <instancedMesh
            key={type}
            ref={node => { if (node) refs.current[type] = node }}
            args={[undefined, undefined, items.length]}
            frustumCulled={false}
          >
            <boxGeometry args={[1, 1, 1]} />
            <meshStandardMaterial
              ref={node => { if (node) materialRefs.current[type] = node }}
              map={textures[type]}
              emissiveMap={textures[type]}
              color="#ffffff"
              vertexColors
              roughness={isGlass ? 0.12 : type === 'office' ? 0.26 : type === 'house' ? 0.58 : 0.46}
              metalness={isGlass ? 0.6 : type === 'office' ? 0.22 : type === 'apartment' ? 0.08 : 0.05}
              emissive={isGlass ? '#9bcde3' : type === 'apartment' ? '#c5a17d' : type === 'house' ? '#c98c6d' : '#c7d2cc'}
              emissiveIntensity={isGlass ? 0.42 : type === 'house' ? 0.27 : type === 'apartment' ? 0.31 : 0.3}
              envMapIntensity={isGlass ? 2.05 : type === 'office' ? 1.28 : type === 'apartment' ? 0.86 : 0.68}
            />
          </instancedMesh>
        )
      })}
      {renderData.podiums.length ? (
        <instancedMesh ref={node => { if (node) detailRefs.current.podiums = node }} args={[undefined, undefined, renderData.podiums.length]} castShadow receiveShadow frustumCulled={false}>
          <boxGeometry args={[1, 1, 1]} />
          <meshStandardMaterial color="#ffffff" vertexColors roughness={0.58} metalness={0.08} emissive="#151515" emissiveIntensity={0.07} />
        </instancedMesh>
      ) : null}
      {renderData.wings.length ? (
        <instancedMesh ref={node => { if (node) detailRefs.current.wings = node }} args={[undefined, undefined, renderData.wings.length]} castShadow receiveShadow frustumCulled={false}>
          <boxGeometry args={[1, 1, 1]} />
          <meshStandardMaterial color="#ffffff" vertexColors roughness={0.62} metalness={0.06} emissive="#211611" emissiveIntensity={0.12} />
        </instancedMesh>
      ) : null}
      {renderData.flatRoofs.length ? (
        <instancedMesh ref={node => { if (node) detailRefs.current.flatRoofs = node }} args={[undefined, undefined, renderData.flatRoofs.length]} castShadow frustumCulled={false}>
          <boxGeometry args={[1, 1, 1]} />
          <meshStandardMaterial color="#ffffff" vertexColors roughness={0.5} metalness={0.12} emissive="#181818" emissiveIntensity={0.08} />
        </instancedMesh>
      ) : null}
      {renderData.gableRoofs.length ? (
        <instancedMesh ref={node => { if (node) detailRefs.current.gableRoofs = node }} args={[gableGeometry, undefined, renderData.gableRoofs.length]} castShadow frustumCulled={false}>
          <meshStandardMaterial color="#ffffff" vertexColors roughness={0.66} metalness={0.06} emissive="#4a281d" emissiveIntensity={0.2} />
        </instancedMesh>
      ) : null}
      {renderData.hipRoofs.length ? (
        <instancedMesh ref={node => { if (node) detailRefs.current.hipRoofs = node }} args={[undefined, undefined, renderData.hipRoofs.length]} castShadow frustumCulled={false}>
          <coneGeometry args={[1, 1, 4]} />
          <meshStandardMaterial color="#ffffff" vertexColors roughness={0.66} metalness={0.06} emissive="#4a281d" emissiveIntensity={0.2} flatShading />
        </instancedMesh>
      ) : null}
      {renderData.shedRoofs.length ? (
        <instancedMesh ref={node => { if (node) detailRefs.current.shedRoofs = node }} args={[undefined, undefined, renderData.shedRoofs.length]} castShadow frustumCulled={false}>
          <boxGeometry args={[1, 1, 1]} />
          <meshStandardMaterial color="#ffffff" vertexColors roughness={0.62} metalness={0.07} emissive="#4a281d" emissiveIntensity={0.2} />
        </instancedMesh>
      ) : null}
      {renderData.crowns.length ? (
        <instancedMesh ref={node => { if (node) detailRefs.current.crowns = node }} args={[undefined, undefined, renderData.crowns.length]} castShadow frustumCulled={false}>
          <boxGeometry args={[1, 1, 1]} />
          <meshStandardMaterial color="#ffffff" vertexColors roughness={0.22} metalness={0.32} emissive="#122a34" emissiveIntensity={0.24} />
        </instancedMesh>
      ) : null}
      {renderData.balconies.length ? (
        <instancedMesh ref={node => { if (node) detailRefs.current.balconies = node }} args={[undefined, undefined, renderData.balconies.length]} castShadow frustumCulled={false}>
          <boxGeometry args={[1, 1, 1]} />
          <meshStandardMaterial color="#ffffff" vertexColors roughness={0.46} metalness={0.14} />
        </instancedMesh>
      ) : null}
      {renderData.porches.length ? (
        <instancedMesh ref={node => { if (node) detailRefs.current.porches = node }} args={[undefined, undefined, renderData.porches.length]} castShadow frustumCulled={false}>
          <boxGeometry args={[1, 1, 1]} />
          <meshStandardMaterial color="#ffffff" vertexColors roughness={0.78} metalness={0.04} emissive="#201712" emissiveIntensity={0.12} />
        </instancedMesh>
      ) : null}
      {renderData.garages.length ? (
        <instancedMesh ref={node => { if (node) detailRefs.current.garages = node }} args={[undefined, undefined, renderData.garages.length]} castShadow receiveShadow frustumCulled={false}>
          <boxGeometry args={[1, 1, 1]} />
          <meshStandardMaterial color="#ffffff" vertexColors roughness={0.66} metalness={0.1} emissive="#171717" emissiveIntensity={0.1} />
        </instancedMesh>
      ) : null}
      {renderData.chimneys.length ? (
        <instancedMesh ref={node => { if (node) detailRefs.current.chimneys = node }} args={[undefined, undefined, renderData.chimneys.length]} castShadow frustumCulled={false}>
          <boxGeometry args={[1, 1, 1]} />
          <meshStandardMaterial color="#ffffff" vertexColors roughness={0.9} metalness={0.02} emissive="#1c100c" emissiveIntensity={0.14} />
        </instancedMesh>
      ) : null}
      {renderData.antennas.length ? (
        <instancedMesh ref={node => { if (node) detailRefs.current.antennas = node }} args={[undefined, undefined, renderData.antennas.length]} frustumCulled={false}>
          <cylinderGeometry args={[1, 1, 1, 6]} />
          <meshStandardMaterial color="#ffffff" vertexColors roughness={0.35} metalness={0.7} />
        </instancedMesh>
      ) : null}
    </>
  )
}

function DistantMountains() {
  const ref = useRef()
  const mountains = useMemo(() => Array.from({ length: 38 }, (_, i) => {
    const angle = (i / 38) * Math.PI * 2
    const radius = 1540 + ((i * 97) % 220)
    const height = 85 + ((i * 53) % 160)
    return {
      x: Math.cos(angle) * radius,
      z: Math.sin(angle) * radius,
      y: -24,
      sx: 120 + ((i * 71) % 190),
      sy: height,
      sz: 70 + ((i * 37) % 120),
      yaw: -angle,
      tint: i / 38,
    }
  }), [])

  useLayoutEffect(() => {
    if (!ref.current) return
    const dummy = new THREE.Object3D()
    const color = new THREE.Color()
    mountains.forEach((mountain, i) => {
      dummy.position.set(mountain.x, mountain.y + mountain.sy / 2, mountain.z)
      dummy.rotation.set(0, mountain.yaw, 0)
      dummy.scale.set(mountain.sx, mountain.sy, mountain.sz)
      dummy.updateMatrix()
      ref.current.setMatrixAt(i, dummy.matrix)
      ref.current.setColorAt(i, color.set('#45514d').lerp(new THREE.Color('#6d766d'), mountain.tint * 0.28))
    })
    ref.current.instanceMatrix.needsUpdate = true
    if (ref.current.instanceColor) ref.current.instanceColor.needsUpdate = true
  }, [mountains])

  return (
    <instancedMesh ref={ref} args={[undefined, undefined, mountains.length]} frustumCulled={false}>
      <coneGeometry args={[1, 1, 6]} />
      <meshStandardMaterial color="#ffffff" vertexColors roughness={0.94} metalness={0.02} flatShading />
    </instancedMesh>
  )
}

function Trees({ trees }) {
  const trunkRef = useRef()
  const crownRef = useRef()

  useLayoutEffect(() => {
    if (!trunkRef.current || !crownRef.current) return
    const dummy = new THREE.Object3D()
    const color = new THREE.Color()
    for (let i = 0; i < trees.length; i += 1) {
      const tree = trees[i]
      dummy.position.set(tree.x, tree.y + tree.scale * 1.6, tree.z)
      dummy.scale.set(tree.scale * 0.18, tree.scale * 3.2, tree.scale * 0.18)
      dummy.updateMatrix()
      trunkRef.current.setMatrixAt(i, dummy.matrix)

      dummy.position.set(tree.x, tree.y + tree.scale * 4.2, tree.z)
      dummy.scale.set(tree.scale * 1.3, tree.scale * 2.1, tree.scale * 1.3)
      dummy.updateMatrix()
      crownRef.current.setMatrixAt(i, dummy.matrix)
      crownRef.current.setColorAt(i, color.set('#2f7d3a').lerp(new THREE.Color('#8abf55'), tree.tint * 0.35))
    }
    trunkRef.current.instanceMatrix.needsUpdate = true
    crownRef.current.instanceMatrix.needsUpdate = true
    if (crownRef.current.instanceColor) crownRef.current.instanceColor.needsUpdate = true
  }, [trees])

  return (
    <>
      <instancedMesh ref={trunkRef} args={[undefined, undefined, trees.length]} castShadow frustumCulled={false}>
        <cylinderGeometry args={[1, 1, 1, 6]} />
        <meshStandardMaterial color="#4d321f" roughness={0.95} />
      </instancedMesh>
      <instancedMesh ref={crownRef} args={[undefined, undefined, trees.length]} castShadow frustumCulled={false}>
        <dodecahedronGeometry args={[1, 0]} />
        <meshStandardMaterial color="#ffffff" vertexColors roughness={0.9} flatShading />
      </instancedMesh>
    </>
  )
}

function AutomaticDoorPanels({ place, color }) {
  const leftRef = useRef()
  const rightRef = useRef()
  const open = useRef(0)
  const interior = place.interior

  const door = interior.doorWidth
  const frontZ = -interior.depth / 2

  useFrame((_, delta) => {
    const player = useCityStore.getState().player
    const localX = player.x - place.x
    const localZ = player.z - place.z
    const nearDoor = Math.abs(localX) < door * 0.9 && Math.abs(localZ - frontZ) < 6.5
    const insideLobby = Math.abs(localX) < interior.width / 2 && Math.abs(localZ) < interior.depth / 2
    const target = nearDoor || insideLobby ? 1 : 0
    open.current += (target - open.current) * (1 - Math.exp(-8 * Math.min(delta, 0.05)))
    const slide = open.current * door * 0.42
    if (leftRef.current) leftRef.current.position.x = -door * 0.28 - slide
    if (rightRef.current) rightRef.current.position.x = door * 0.28 + slide
  })

  return (
    <group>
      <mesh ref={leftRef} position={[-door * 0.28, 2.1, frontZ - 0.12]}>
        <boxGeometry args={[door * 0.42, 3.8, 0.12]} />
        <meshStandardMaterial color="#b8ecff" roughness={0.08} metalness={0.34} transparent opacity={0.45} />
      </mesh>
      <mesh ref={rightRef} position={[door * 0.28, 2.1, frontZ - 0.12]}>
        <boxGeometry args={[door * 0.42, 3.8, 0.12]} />
        <meshStandardMaterial color="#b8ecff" roughness={0.08} metalness={0.34} transparent opacity={0.45} />
      </mesh>
      <mesh position={[0, 4.45, frontZ - 0.18]}>
        <boxGeometry args={[door + 1.2, 0.48, 0.18]} />
        <meshStandardMaterial color="#101820" emissive={color} emissiveIntensity={0.55} roughness={0.28} metalness={0.24} />
      </mesh>
    </group>
  )
}

function InteriorShell({ place, color }) {
  const interior = place.interior
  if (!interior) return null

  const w = interior.width
  const d = interior.depth
  const h = interior.height
  const t = 0.42
  const door = interior.doorWidth
  const sideWidth = (w - door) / 2
  const frontZ = -d / 2
  const backZ = d / 2
  const wallColor = place.kind === 'hospital' ? '#dfe8ed' : place.kind === 'logistics' ? '#9fa7ac' : '#c7c0b3'

  const verticalCore = interior.verticalCore === 'elevator'
    ? (
      <group position={[w * 0.25, 0, d * 0.25]}>
        <mesh castShadow receiveShadow position={[0, h * 0.36, 0]}>
          <boxGeometry args={[4.6, h * 0.72, 4.2]} />
          <meshStandardMaterial color="#303941" roughness={0.36} metalness={0.28} />
        </mesh>
        <mesh position={[0, 2.2, -2.14]}>
          <boxGeometry args={[3.2, 3.7, 0.16]} />
          <meshStandardMaterial color="#b6c0c6" roughness={0.26} metalness={0.62} />
        </mesh>
        <mesh position={[0, 4.7, -2.24]}>
          <boxGeometry args={[2.4, 0.34, 0.18]} />
          <meshStandardMaterial color="#6be6ff" emissive="#3db8ff" emissiveIntensity={0.5} />
        </mesh>
      </group>
    )
    : interior.verticalCore === 'escalator'
      ? (
        <group position={[w * 0.22, 0.7, d * 0.18]} rotation={[0.18, 0, -0.35]}>
          <mesh castShadow receiveShadow>
            <boxGeometry args={[2.2, 0.38, 8.4]} />
            <meshStandardMaterial color="#49515a" roughness={0.38} metalness={0.34} />
          </mesh>
          <mesh position={[-1.2, 0.32, 0]}>
            <boxGeometry args={[0.18, 0.42, 8.8]} />
            <meshStandardMaterial color="#d8e4ea" roughness={0.22} metalness={0.6} />
          </mesh>
          <mesh position={[1.2, 0.32, 0]}>
            <boxGeometry args={[0.18, 0.42, 8.8]} />
            <meshStandardMaterial color="#d8e4ea" roughness={0.22} metalness={0.6} />
          </mesh>
        </group>
      )
      : (
        <group position={[w * 0.23, 0.25, d * 0.18]}>
          {Array.from({ length: 7 }, (_, i) => (
            <mesh key={i} castShadow receiveShadow position={[0, i * 0.22, i * 0.54]}>
              <boxGeometry args={[4.5, 0.2, 0.5]} />
              <meshStandardMaterial color="#7c858b" roughness={0.58} metalness={0.12} />
            </mesh>
          ))}
          <mesh position={[2.35, 0.92, 1.7]}>
            <boxGeometry args={[0.15, 1.4, 4.5]} />
            <meshStandardMaterial color="#d8e4ea" roughness={0.24} metalness={0.58} />
          </mesh>
        </group>
      )

  return (
    <group>
      <mesh receiveShadow position={[0, 0.08, 0]}>
        <boxGeometry args={[w, 0.16, d]} />
        <meshStandardMaterial color={place.kind === 'logistics' ? '#697176' : '#bfc4c5'} roughness={0.48} metalness={0.06} />
      </mesh>
      <mesh castShadow receiveShadow position={[0, h / 2, backZ]}>
        <boxGeometry args={[w, h, t]} />
        <meshStandardMaterial color={wallColor} roughness={0.54} metalness={0.08} />
      </mesh>
      <mesh castShadow receiveShadow position={[-w / 2, h / 2, 0]}>
        <boxGeometry args={[t, h, d]} />
        <meshStandardMaterial color={wallColor} roughness={0.54} metalness={0.08} />
      </mesh>
      <mesh castShadow receiveShadow position={[w / 2, h / 2, 0]}>
        <boxGeometry args={[t, h, d]} />
        <meshStandardMaterial color={wallColor} roughness={0.54} metalness={0.08} />
      </mesh>
      <mesh castShadow receiveShadow position={[-door / 2 - sideWidth / 2, h / 2, frontZ]}>
        <boxGeometry args={[sideWidth, h, t]} />
        <meshStandardMaterial color={wallColor} roughness={0.54} metalness={0.08} />
      </mesh>
      <mesh castShadow receiveShadow position={[door / 2 + sideWidth / 2, h / 2, frontZ]}>
        <boxGeometry args={[sideWidth, h, t]} />
        <meshStandardMaterial color={wallColor} roughness={0.54} metalness={0.08} />
      </mesh>
      <mesh castShadow receiveShadow position={[0, h + 0.22, 0]}>
        <boxGeometry args={[w + 1.8, 0.44, d + 1.8]} />
        <meshStandardMaterial color="#343b42" roughness={0.45} metalness={0.16} />
      </mesh>
      <AutomaticDoorPanels place={place} color={color} />
      <mesh receiveShadow position={[0, 0.11, -d * 0.1]}>
        <boxGeometry args={[Math.max(3, door * 0.8), 0.05, Math.max(6, interior.lobbyDepth)]} />
        <meshStandardMaterial color="#d7dce0" roughness={0.32} metalness={0.04} />
      </mesh>
      {Array.from({ length: Math.min(4, Math.max(0, (interior.floorCount || 1) - 1)) }, (_, i) => {
        const y = h * ((i + 1) / (Math.min(4, Math.max(0, (interior.floorCount || 1) - 1)) + 1))
        return (
          <mesh key={`floor-plate-${i}`} receiveShadow position={[0, y, 0]}>
            <boxGeometry args={[w * 0.92, 0.08, d * 0.92]} />
            <meshStandardMaterial color="#aeb6bb" roughness={0.48} metalness={0.08} transparent opacity={0.72} />
          </mesh>
        )
      })}
      {[-0.26, 0.26].map((x, i) => (
        <mesh key={`partition-${i}`} castShadow receiveShadow position={[x * w, 1.75, d * 0.08]}>
          <boxGeometry args={[0.12, 3.1, Math.max(3.5, interior.lobbyDepth * 0.56)]} />
          <meshStandardMaterial color="#dce3e6" roughness={0.42} metalness={0.04} transparent opacity={0.84} />
        </mesh>
      ))}
      {[-0.28, 0, 0.28].map((x, i) => (
        <mesh key={`light-${i}`} position={[x * w, h - 0.32, -d * 0.08]}>
          <boxGeometry args={[Math.max(2.4, w * 0.16), 0.05, 0.18]} />
          <meshStandardMaterial color="#e9fbff" emissive="#98eaff" emissiveIntensity={0.75} roughness={0.2} />
        </mesh>
      ))}
      <mesh position={[-w * 0.2, 1.25, d * 0.18]}>
        <boxGeometry args={[4.8, 2.2, 1.0]} />
        <meshStandardMaterial color="#5f6b72" roughness={0.56} metalness={0.14} />
      </mesh>
      {verticalCore}
    </group>
  )
}

function LandmarkFacadeGlass({ fw, fd, kind, color }) {
  if (kind === 'park') return null
  const rows = kind === 'finance' ? [9, 17, 25, 33, 41] : kind === 'hospital' ? [5.8, 8.6, 11.4] : [4.8, 7.6, 10.4]
  const faces = [
    { id: 'north', length: fw, z: fd * 0.48, x: null },
    { id: 'south', length: fw, z: -fd * 0.48, x: null },
    { id: 'east', length: fd, x: fw * 0.48, z: null },
    { id: 'west', length: fd, x: -fw * 0.48, z: null },
  ]
  return (
    <group>
      {faces.flatMap((face, faceIndex) => {
        const columns = Math.max(2, Math.min(5, Math.floor(face.length / 8)))
        return rows.flatMap((y, rowIndex) => (
          Array.from({ length: columns }, (_, col) => {
            if ((faceIndex + rowIndex + col) % 5 === 0 && kind !== 'finance') return null
            const along = ((col + 0.5) / columns - 0.5) * face.length * 0.68
            const scale = face.x === null
              ? [Math.min(5.2, face.length * 0.13), 1.45, 0.24]
              : [0.24, 1.45, Math.min(5.2, face.length * 0.13)]
            const position = face.x === null ? [along, y, face.z] : [face.x, y, along]
            return (
              <mesh key={`${face.id}-${rowIndex}-${col}`} position={position}>
                <boxGeometry args={scale} />
                <meshStandardMaterial color="#d4f4ff" emissive={color} emissiveIntensity={0.18 + (kind === 'finance' ? 0.18 : 0.06)} roughness={0.16} metalness={0.24} />
              </mesh>
            )
          })
        ))
      })}
    </group>
  )
}

function Landmark({ place }) {
  const color = {
    transit: '#55a7ff',
    finance: '#8ecae6',
    cafe: '#d98b5f',
    hospital: '#e85d75',
    workshop: '#9b7ede',
    retail: '#f4a261',
    school: '#78c6a3',
    leisure: '#ff7ab6',
    park: '#8ac926',
    logistics: '#adb5bd',
  }[place.kind] || '#ffffff'

  const footprint = place.footprint || { width: place.interior?.width || 28, depth: place.interior?.depth || 24 }
  const fw = footprint.width
  const fd = footprint.depth
  const signHeight = place.kind === 'finance' ? 58 : place.kind === 'transit' ? 22 : 15

  return (
    <group position={[place.x, CITY_BASE_Y, place.z]}>
      <InteriorShell place={place} color={color} />
      <LandmarkFacadeGlass fw={fw} fd={fd} kind={place.kind} color={color} />
      {place.kind === 'finance' ? (
        <>
          <mesh castShadow receiveShadow position={[0, 42, 0]}>
            <boxGeometry args={[15, 50, 15]} />
            <meshStandardMaterial color="#9fb8c7" roughness={0.18} metalness={0.35} transparent opacity={0.88} />
          </mesh>
        </>
      ) : place.kind === 'transit' ? (
        <>
          <mesh castShadow receiveShadow position={[0, 8.2, 0]}>
            <boxGeometry args={[Math.max(12, fw - 4), 3.4, Math.max(10, fd - 1)]} />
            <meshStandardMaterial color="#cfd7dd" roughness={0.32} metalness={0.18} />
          </mesh>
          <mesh castShadow position={[0, 11, 0]} rotation={[0, 0, Math.PI / 8]}>
            <boxGeometry args={[fw, 1.4, fd]} />
            <meshStandardMaterial color="#2a3034" roughness={0.55} metalness={0.12} />
          </mesh>
        </>
      ) : place.kind === 'park' ? (
        <>
          <mesh receiveShadow position={[0, 0.14, 0]}>
            <cylinderGeometry args={[Math.min(fw, fd) / 2, Math.min(fw, fd) / 2, 0.24, 48]} />
            <meshStandardMaterial color="#2f6f3d" roughness={0.9} />
          </mesh>
          <mesh castShadow position={[0, 3.5, 0]}>
            <cylinderGeometry args={[5, 6, 7, 14]} />
            <meshStandardMaterial color="#826d4f" roughness={0.78} />
          </mesh>
        </>
      ) : place.kind === 'logistics' ? (
        <>
          <mesh castShadow receiveShadow position={[0, 12.2, 0]}>
            <boxGeometry args={[fw, 2.4, fd]} />
            <meshStandardMaterial color="#3e474f" roughness={0.44} metalness={0.18} />
          </mesh>
          {[-fw * 0.3, 0, fw * 0.3].map(x => (
            <mesh key={`dock-${x}`} receiveShadow position={[x, 3.2, -fd * 0.46]}>
              <boxGeometry args={[Math.min(9.5, fw * 0.18), 5.8, 0.42]} />
              <meshStandardMaterial color="#2d343a" roughness={0.62} metalness={0.18} />
            </mesh>
          ))}
          {[-fw * 0.36, -fw * 0.14, fw * 0.14, fw * 0.36].map(x => (
            <mesh key={`window-${x}`} position={[x, 7.8, fd * 0.43]}>
              <boxGeometry args={[Math.min(4.5, fw * 0.11), 1.55, 0.36]} />
              <meshStandardMaterial color="#bde8ff" emissive="#4bb6ff" emissiveIntensity={0.36} roughness={0.22} metalness={0.28} />
            </mesh>
          ))}
          <mesh position={[0, 1.35, -fd * 0.46]}>
            <boxGeometry args={[fw * 0.84, 0.18, 0.34]} />
            <meshStandardMaterial color="#f5c542" emissive="#b7791f" emissiveIntensity={0.22} roughness={0.48} />
          </mesh>
          <mesh castShadow position={[-fw * 0.34, 1.4, -fd * 0.34]}>
            <boxGeometry args={[Math.min(8, fw * 0.16), 2.8, Math.min(4.6, fd * 0.16)]} />
            <meshStandardMaterial color="#d9a441" roughness={0.48} metalness={0.12} />
          </mesh>
          <mesh castShadow position={[fw * 0.31, 1.1, -fd * 0.34]}>
            <boxGeometry args={[Math.min(7, fw * 0.15), 2.2, Math.min(5, fd * 0.18)]} />
            <meshStandardMaterial color="#58616a" roughness={0.52} metalness={0.12} />
          </mesh>
        </>
      ) : place.kind === 'hospital' ? (
        <>
          <mesh castShadow receiveShadow position={[0, 14.8, 0]}>
            <boxGeometry args={[Math.min(31, fw * 0.78), 6, Math.min(22, fd * 0.74)]} />
            <meshStandardMaterial color="#cbd9df" roughness={0.42} metalness={0.06} />
          </mesh>
          {[-fw * 0.32, -fw * 0.11, fw * 0.11, fw * 0.32].map(x => (
            <mesh key={`hospital-window-${x}`} position={[x, 7.2, -fd * 0.47]}>
              <boxGeometry args={[Math.min(4.4, fw * 0.12), 2.2, 0.28]} />
              <meshStandardMaterial color="#c8f2ff" emissive="#76d6ff" emissiveIntensity={0.22} roughness={0.18} metalness={0.16} />
            </mesh>
          ))}
          <mesh position={[0, 8.2, -fd * 0.48]}>
            <boxGeometry args={[1.5, 6.8, 0.36]} />
            <meshStandardMaterial color="#e85d75" emissive="#e85d75" emissiveIntensity={0.32} />
          </mesh>
          <mesh position={[0, 8.2, -fd * 0.49]}>
            <boxGeometry args={[6.8, 1.5, 0.38]} />
            <meshStandardMaterial color="#e85d75" emissive="#e85d75" emissiveIntensity={0.32} />
          </mesh>
        </>
      ) : (
        <>
          <mesh castShadow receiveShadow position={[0, 10.5, 0]}>
            <boxGeometry args={[fw * 0.68, 4, fd * 0.72]} />
            <meshStandardMaterial color="#343b42" roughness={0.45} metalness={0.08} />
          </mesh>
          {[-fw * 0.24, 0, fw * 0.24].map(x => (
            <mesh key={`front-window-${x}`} position={[x, 5.2, -fd * 0.43]}>
              <boxGeometry args={[Math.min(4.2, fw * 0.15), 2.0, 0.3]} />
              <meshStandardMaterial color="#d4f4ff" emissive="#57c7ff" emissiveIntensity={0.25} roughness={0.2} metalness={0.2} />
            </mesh>
          ))}
          <mesh position={[0, 1.8, -fd * 0.44]}>
            <boxGeometry args={[4.4, 3.4, 0.34]} />
            <meshStandardMaterial color="#202831" roughness={0.45} metalness={0.18} />
          </mesh>
          <mesh position={[0, 8.8, -fd * 0.45]}>
            <boxGeometry args={[fw * 0.52, 1.1, 0.36]} />
            <meshStandardMaterial color="#101820" emissive={color} emissiveIntensity={0.6} roughness={0.28} metalness={0.24} />
          </mesh>
        </>
      )}
      <mesh position={[0, signHeight - 3, 0]}>
        <sphereGeometry args={[1.35, 16, 10]} />
        <meshStandardMaterial color="#ffffff" emissive={color} emissiveIntensity={1.6} />
      </mesh>
      <Billboard position={[0, signHeight, 0]}>
        <Text fontSize={3.2} maxWidth={64} textAlign="center" color="#f8fbff" outlineWidth={0.1} outlineColor="#07111d">
          {place.name}
        </Text>
      </Billboard>
    </group>
  )
}

function TileStreamingTelemetry({ city }) {
  const clock = useRef(0)

  useFrame((_, delta) => {
    if (typeof window === 'undefined' || !import.meta.env.DEV) return
    clock.current += delta
    if (clock.current < 0.32) return
    clock.current = 0
    const player = useCityStore.getState().player || { x: 0, z: 0 }
    const tiles = city.tiles || []
    const ranked = tiles
      .map(tile => {
        const dx = (tile.center?.x || 0) - player.x
        const dz = (tile.center?.z || 0) - player.z
        const distance = Math.hypot(dx, dz)
        const lod = distance < TILE_SIZE * 1.15
          ? 'near-detail'
          : distance < TILE_SIZE * 2.45
            ? 'mid-massing'
            : 'far-shell'
        const visible = distance < TILE_SIZE * 4.2
        return {
          id: tile.id,
          distance: Number(distance.toFixed(1)),
          lod,
          visible,
          contentUri: tile.contentUri,
          geometricError: tile.geometricError,
          featureCount: tile.content?.metadata?.properties?.featureCount || ((tile.buildings?.length || 0) + (tile.landmarks?.length || 0)),
        }
      })
      .sort((a, b) => a.distance - b.distance)
    window.__REALCITY_TILE_STREAMING__ = {
      tilesetVersion: city.tileset?.asset?.tilesetVersion || null,
      schemaId: city.tileset?.schema?.id || null,
      totalTiles: tiles.length,
      visibleTiles: ranked.filter(tile => tile.visible).length,
      nearTiles: ranked.filter(tile => tile.lod === 'near-detail').length,
      midTiles: ranked.filter(tile => tile.lod === 'mid-massing').length,
      farTiles: ranked.filter(tile => tile.lod === 'far-shell').length,
      nearest: ranked.slice(0, 8),
      boundingVolumeType: city.tileset?.root?.boundingVolume?.box ? 'box' : 'missing',
      runtimeRule: 'near tiles keep detailed facade/landmark content, mid tiles are massing candidates, far tiles are shell/aggregate candidates',
    }
  })

  return null
}

export default function CityMeshes({ city }) {
  const terrain = useMemo(() => makeTerrainGeometry(), [])
  const roads = useMemo(() => makeRoadGeometry(city.roads), [city.roads])
  const roadTexture = useMemo(() => makeRoadTexture(), [])

  return (
    <>
      <mesh geometry={terrain}>
        <meshLambertMaterial vertexColors />
      </mesh>

      <UrbanBase roads={city.roads} />

      <mesh geometry={roads}>
        <meshBasicMaterial map={roadTexture} color="#ffffff" toneMapped={false} />
      </mesh>
      <RoadMarkings roads={city.roads} />

      <mesh rotation={[-Math.PI / 2, 0, 0]} position={[0, -1.8, -980]} receiveShadow>
        <planeGeometry args={[CITY_WORLD_SIZE, 150]} />
        <meshStandardMaterial color="#14324b" roughness={0.1} metalness={0.25} />
      </mesh>
      <DistantMountains />

      <Buildings buildings={city.buildings} />
      <Trees trees={city.trees} />
      {city.landmarks.map(place => <Landmark key={place.id} place={place} />)}
      <TileStreamingTelemetry city={city} />
    </>
  )
}
