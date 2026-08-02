import { useEffect, useLayoutEffect, useMemo, useRef } from 'react'
import { useFrame } from '@react-three/fiber'
import { Billboard, Text } from '@react-three/drei'
import * as THREE from 'three'
import { CITY_BASE_Y, CITY_GRID_HALF, ROAD_SPACING, ROAD_WIDTH, SUMO_TL_LOGIC, pedestrianSignalForAxis, trafficPhaseAt, trafficSignalForAxis } from '../engine/cityEngine'
import { useCityStore } from '../engine/cityStore'

function setInstance(mesh, index, dummy, position, scale, rotationY = 0) {
  dummy.position.set(position[0], position[1], position[2])
  dummy.rotation.set(0, rotationY, 0)
  dummy.scale.set(scale[0], scale[1], scale[2])
  dummy.updateMatrix()
  mesh.setMatrixAt(index, dummy.matrix)
}

function makeFlatTriangleGeometry() {
  const geometry = new THREE.BufferGeometry()
  geometry.setAttribute('position', new THREE.Float32BufferAttribute([
    -0.5, 0, -0.58,
    0, 0, 0.66,
    0.5, 0, -0.58,
  ], 3))
  geometry.setAttribute('normal', new THREE.Float32BufferAttribute([
    0, 1, 0,
    0, 1, 0,
    0, 1, 0,
  ], 3))
  geometry.setAttribute('uv', new THREE.Float32BufferAttribute([
    0, 0,
    0.5, 1,
    1, 0,
  ], 2))
  geometry.setIndex([0, 1, 2])
  return geometry
}

function localToWorld(building, local) {
  const cos = Math.cos(building.rot)
  const sin = Math.sin(building.rot)
  return {
    x: building.x + local[0] * cos + local[2] * sin,
    y: building.y + local[1],
    z: building.z - local[0] * sin + local[2] * cos,
  }
}

function setLocalInstance(mesh, index, dummy, building, local, scale, rotationOffset = 0) {
  const world = localToWorld(building, local)
  dummy.position.set(world.x, world.y, world.z)
  dummy.rotation.set(0, building.rot + rotationOffset, 0)
  dummy.scale.set(scale[0], scale[1], scale[2])
  dummy.updateMatrix()
  mesh.setMatrixAt(index, dummy.matrix)
}

const FACADE_FACES = ['north', 'south', 'east', 'west']

function entryFaceForBuilding(building) {
  return building.facadePlan?.entryFace || building.entryFace || building.interior?.entryFace || 'south'
}

function faceLength(building, face) {
  return face === 'north' || face === 'south' ? building.w : building.d
}

function faceLocal(building, face, along = 0, y = 0, outward = 0.16) {
  if (face === 'north') return [along, y, building.d / 2 + outward]
  if (face === 'south') return [along, y, -building.d / 2 - outward]
  if (face === 'east') return [building.w / 2 + outward, y, along]
  return [-building.w / 2 - outward, y, along]
}

function faceScale(face, width, height, thickness = 0.055) {
  return face === 'north' || face === 'south'
    ? [width, height, thickness]
    : [thickness, height, width]
}

function facePart(building, face, along, y, width, height, outward = 0.16, thickness = 0.055) {
  return {
    building,
    local: faceLocal(building, face, along, y, outward),
    scale: faceScale(face, width, height, thickness),
  }
}

function balconyModules(length, pattern, role) {
  if (pattern === 'paired-balanced' && length > 11.5) {
    const width = Math.min(3.2, length * 0.22)
    return [
      { along: -length * 0.18, width },
      { along: length * 0.18, width },
    ]
  }
  if (pattern === 'corner-return' && role === 'front' && length > 10.5) {
    return [
      { along: -length * 0.24, width: Math.min(3.4, length * 0.22) },
      { along: length * 0.24, width: Math.min(3.4, length * 0.22) },
    ]
  }
  return [{ along: 0, width: Math.min(5.4, length * 0.34) }]
}

function clamp(value, min, max) {
  return Math.max(min, Math.min(max, value))
}

function coreLabelFor(interior) {
  if (interior?.verticalCore === 'elevator') return 'Elevator'
  if (interior?.verticalCore === 'escalator') return 'Escalator'
  return 'Stairs'
}

function buildingDirectoryName(building) {
  return building.address || building.name || `${building.type || 'City'} lobby`
}

function useRoadLayout(roads) {
  return useMemo(() => {
    const vertical = roads.filter(road => road.axis === 'z')
    const horizontal = roads.filter(road => road.axis === 'x')
    const mainVertical = vertical.filter(road => road.main)
    const mainHorizontal = horizontal.filter(road => road.main)
    return { vertical, horizontal, mainVertical, mainHorizontal }
  }, [roads])
}

function exposeRenderingMetadata(patch) {
  if (typeof window === 'undefined' || !import.meta.env.DEV) return
  window.__REALCITY_RENDERING__ = {
    ...(window.__REALCITY_RENDERING__ || {}),
    ...patch,
  }
}

function Crosswalks({ roads }) {
  const ref = useRef()
  const baseRef = useRef()
  const stopRef = useRef()
  const { vertical, horizontal } = useRoadLayout(roads)
  const details = useMemo(() => {
    const stripes = []
    const bases = []
    const stops = []
    let signalizedCrossings = 0
    let priorityCrossings = 0
    let localGapCrossings = 0
    for (const h of horizontal) {
      for (const v of vertical) {
        const distance = Math.hypot(v.x, h.z)
        if (distance > CITY_GRID_HALF * 0.94) continue
        const signalized = h.main && v.main
        const priority = h.main || v.main
        if (signalized) signalizedCrossings += 1
        else if (priority) priorityCrossings += 1
        else localGapCrossings += 1
        const crossingWidth = signalized ? 14.4 : priority ? 11.8 : 8.8
        const hDepth = h.width * (signalized ? 0.58 : priority ? 0.5 : 0.43)
        const vDepth = v.width * (signalized ? 0.58 : priority ? 0.5 : 0.43)
        const offsets = signalized
          ? [-5.4, -3.6, -1.8, 0, 1.8, 3.6, 5.4]
          : priority
            ? [-4.2, -2.1, 0, 2.1, 4.2]
            : [-3.0, 0, 3.0]
        bases.push({ x: v.x, z: h.z - hDepth, sx: crossingWidth, sz: hDepth })
        bases.push({ x: v.x, z: h.z + hDepth, sx: crossingWidth, sz: hDepth })
        bases.push({ x: v.x - vDepth, z: h.z, sx: vDepth, sz: crossingWidth })
        bases.push({ x: v.x + vDepth, z: h.z, sx: vDepth, sz: crossingWidth })
        if (signalized) {
          stops.push({ x: v.x, z: h.z - h.width * 0.92, sx: 18.8, sz: 0.42 })
          stops.push({ x: v.x, z: h.z + h.width * 0.92, sx: 18.8, sz: 0.42 })
          stops.push({ x: v.x - v.width * 0.92, z: h.z, sx: 0.42, sz: 18.8 })
          stops.push({ x: v.x + v.width * 0.92, z: h.z, sx: 0.42, sz: 18.8 })
        }
        offsets.forEach(offset => {
          const stripeWidth = signalized ? 0.82 : priority ? 0.72 : 0.58
          stripes.push({ x: v.x + offset, z: h.z - hDepth, sx: stripeWidth, sz: hDepth })
          stripes.push({ x: v.x + offset, z: h.z + hDepth, sx: stripeWidth, sz: hDepth })
          stripes.push({ x: v.x - vDepth, z: h.z + offset, sx: vDepth, sz: stripeWidth })
          stripes.push({ x: v.x + vDepth, z: h.z + offset, sx: vDepth, sz: stripeWidth })
        })
      }
    }
    return { stripes, bases, stops, signalizedCrossings, priorityCrossings, localGapCrossings }
  }, [horizontal, vertical])

  useEffect(() => {
    exposeRenderingMetadata({
      crosswalks: {
        zebraStripes: details.stripes.length,
        crossingPads: details.bases.length,
        stopBars: details.stops.length,
        raisedAboveRoad: true,
        separatedFromSidewalks: true,
        allRoadCrossingCoverage: true,
        signalizedCrossings: details.signalizedCrossings,
        priorityZebraCrossings: details.priorityCrossings,
        localGapCrossings: details.localGapCrossings,
        corridorPolicy: 'every procedural road crossing receives visible zebra/gap paint matching the NPC crossing graph',
      },
    })
  }, [details])

  useLayoutEffect(() => {
    if (!ref.current || !baseRef.current || !stopRef.current) return
    const dummy = new THREE.Object3D()
    details.bases.forEach((base, i) => setInstance(baseRef.current, i, dummy, [base.x, CITY_BASE_Y + 0.187, base.z], [base.sx, 0.018, base.sz]))
    details.stripes.forEach((stripe, i) => setInstance(ref.current, i, dummy, [stripe.x, CITY_BASE_Y + 0.215, stripe.z], [stripe.sx, 0.035, stripe.sz]))
    details.stops.forEach((bar, i) => setInstance(stopRef.current, i, dummy, [bar.x, CITY_BASE_Y + 0.225, bar.z], [bar.sx, 0.038, bar.sz]))
    baseRef.current.instanceMatrix.needsUpdate = true
    ref.current.instanceMatrix.needsUpdate = true
    stopRef.current.instanceMatrix.needsUpdate = true
  }, [details])

  return (
    <>
      <instancedMesh ref={baseRef} args={[undefined, undefined, details.bases.length]} frustumCulled={false}>
        <boxGeometry args={[1, 1, 1]} />
        <meshBasicMaterial color="#606669" transparent opacity={0.7} toneMapped={false} />
      </instancedMesh>
      <instancedMesh ref={ref} args={[undefined, undefined, details.stripes.length]} frustumCulled={false}>
        <boxGeometry args={[1, 1, 1]} />
        <meshBasicMaterial color="#fbfff9" toneMapped={false} />
      </instancedMesh>
      <instancedMesh ref={stopRef} args={[undefined, undefined, details.stops.length]} frustumCulled={false}>
        <boxGeometry args={[1, 1, 1]} />
        <meshBasicMaterial color="#fffdf0" toneMapped={false} />
      </instancedMesh>
    </>
  )
}

function StreetLights({ roads }) {
  const poleRef = useRef()
  const armRef = useRef()
  const bulbRef = useRef()
  const { mainVertical, mainHorizontal } = useRoadLayout(roads)
  const lights = useMemo(() => {
    const items = []
    const spacing = ROAD_SPACING * 2.25
    for (const road of mainHorizontal) {
      for (let x = road.from + spacing; x < road.to - spacing; x += spacing) {
        if (Math.hypot(x, road.z) > CITY_GRID_HALF * 0.96) continue
        items.push({ x, z: road.z - road.width * 0.95, yaw: Math.PI / 2, side: -1 })
        items.push({ x, z: road.z + road.width * 0.95, yaw: -Math.PI / 2, side: 1 })
      }
    }
    for (const road of mainVertical) {
      for (let z = road.from + spacing; z < road.to - spacing; z += spacing) {
        if (Math.hypot(road.x, z) > CITY_GRID_HALF * 0.96) continue
        items.push({ x: road.x - road.width * 0.95, z, yaw: 0, side: -1 })
        items.push({ x: road.x + road.width * 0.95, z, yaw: Math.PI, side: 1 })
      }
    }
    return items
  }, [mainHorizontal, mainVertical])

  useLayoutEffect(() => {
    if (!poleRef.current || !armRef.current || !bulbRef.current) return
    const dummy = new THREE.Object3D()
    lights.forEach((light, i) => {
      setInstance(poleRef.current, i, dummy, [light.x, CITY_BASE_Y + 2.7, light.z], [0.07, 5.4, 0.07])
      const armX = light.x + Math.sin(light.yaw) * 0.72
      const armZ = light.z + Math.cos(light.yaw) * 0.72
      setInstance(armRef.current, i, dummy, [armX, CITY_BASE_Y + 5.35, armZ], [0.16, 0.12, 1.45], light.yaw)
      const bulbX = light.x + Math.sin(light.yaw) * 1.35
      const bulbZ = light.z + Math.cos(light.yaw) * 1.35
      setInstance(bulbRef.current, i, dummy, [bulbX, CITY_BASE_Y + 5.18, bulbZ], [0.28, 0.16, 0.28])
    })
    poleRef.current.instanceMatrix.needsUpdate = true
    armRef.current.instanceMatrix.needsUpdate = true
    bulbRef.current.instanceMatrix.needsUpdate = true
  }, [lights])

  return (
    <>
      <instancedMesh ref={poleRef} args={[undefined, undefined, lights.length]} castShadow frustumCulled={false}>
        <cylinderGeometry args={[1, 1, 1, 8]} />
        <meshStandardMaterial color="#2f3437" roughness={0.5} metalness={0.45} />
      </instancedMesh>
      <instancedMesh ref={armRef} args={[undefined, undefined, lights.length]} castShadow frustumCulled={false}>
        <boxGeometry args={[1, 1, 1]} />
        <meshStandardMaterial color="#2c3135" roughness={0.46} metalness={0.5} />
      </instancedMesh>
      <instancedMesh ref={bulbRef} args={[undefined, undefined, lights.length]} frustumCulled={false}>
        <sphereGeometry args={[1, 10, 8]} />
        <meshStandardMaterial color="#fff2be" emissive="#ffd470" emissiveIntensity={0.85} roughness={0.22} />
      </instancedMesh>
    </>
  )
}

function TrafficSignals({ roads, mobilitySystem }) {
  const poleRef = useRef()
  const headRef = useRef()
  const redRef = useRef()
  const yellowRef = useRef()
  const greenRef = useRef()
  const { mainVertical, mainHorizontal } = useRoadLayout(roads)
  const signals = useMemo(() => {
    const items = []
    for (const h of mainHorizontal) {
      for (const v of mainVertical) {
        if (Math.hypot(v.x, h.z) > CITY_GRID_HALF * 0.94) continue
        items.push({ x: v.x - v.width * 0.68, z: h.z - h.width * 0.68, yaw: Math.PI / 2, axis: 'x' })
        items.push({ x: v.x + v.width * 0.68, z: h.z + h.width * 0.68, yaw: -Math.PI / 2, axis: 'x' })
        items.push({ x: v.x + v.width * 0.68, z: h.z - h.width * 0.68, yaw: 0, axis: 'z' })
        items.push({ x: v.x - v.width * 0.68, z: h.z + h.width * 0.68, yaw: Math.PI, axis: 'z' })
      }
    }
    return items
  }, [mainHorizontal, mainVertical])

  useEffect(() => {
    exposeRenderingMetadata({
      trafficSignals: {
        heads: signals.length,
        controller: 'SUMO-inspired actuated tlLogic',
        phases: SUMO_TL_LOGIC.map(phase => phase.id),
        program: SUMO_TL_LOGIC.map(phase => ({ id: phase.id, duration: phase.duration, state: phase.sumoState })),
        linkOrder: ['x_vehicle_forward', 'x_vehicle_reverse', 'z_vehicle_forward', 'z_vehicle_reverse', 'ped_cross_x', 'ped_cross_z'],
        pedestrianLinks: { crossX: 'ped_cross_x', crossZ: 'ped_cross_z' },
        detectorPolicy: 'SUMO induction-loop-style pressure sensors actuate protected green duration from TrafficFlowObserved pressure',
        stopRule: 'vehicles stop at crosswalk stop bars on red/all-red; yellow decelerates when far and clears when close',
      },
    })
  }, [signals.length])

  useLayoutEffect(() => {
    if (!poleRef.current || !headRef.current || !redRef.current || !yellowRef.current || !greenRef.current) return
    const dummy = new THREE.Object3D()
    signals.forEach((signal, i) => {
      setInstance(poleRef.current, i, dummy, [signal.x, CITY_BASE_Y + 2.05, signal.z], [0.08, 4.1, 0.08])
      setInstance(headRef.current, i, dummy, [signal.x, CITY_BASE_Y + 4.02, signal.z], [0.52, 0.9, 0.22], signal.yaw)
      setInstance(redRef.current, i, dummy, [signal.x, CITY_BASE_Y + 4.28, signal.z], [0.09, 0.09, 0.09])
      setInstance(yellowRef.current, i, dummy, [signal.x, CITY_BASE_Y + 4.04, signal.z], [0.09, 0.09, 0.09])
      setInstance(greenRef.current, i, dummy, [signal.x, CITY_BASE_Y + 3.8, signal.z], [0.09, 0.09, 0.09])
    })
    poleRef.current.instanceMatrix.needsUpdate = true
    headRef.current.instanceMatrix.needsUpdate = true
    redRef.current.instanceMatrix.needsUpdate = true
    yellowRef.current.instanceMatrix.needsUpdate = true
    greenRef.current.instanceMatrix.needsUpdate = true
  }, [signals])

  useFrame(() => {
    if (!redRef.current || !yellowRef.current || !greenRef.current) return
    const timeMinutes = useCityStore.getState().timeMinutes
    const phase = trafficPhaseAt(timeMinutes, mobilitySystem)
    const dummy = new THREE.Object3D()
    let redHeads = 0
    let yellowHeads = 0
    let greenHeads = 0
    for (let i = 0; i < signals.length; i += 1) {
      const signal = signals[i]
      const state = trafficSignalForAxis(signal.axis, timeMinutes, mobilitySystem)
      if (state === 'red') redHeads += 1
      if (state === 'yellow') yellowHeads += 1
      if (state === 'green') greenHeads += 1
      const redScale = state === 'red' ? 1 : 0.26
      const yellowScale = state === 'yellow' ? 1 : 0.18
      const greenScale = state === 'green' ? 1 : 0.26
      setInstance(redRef.current, i, dummy, [signal.x, CITY_BASE_Y + 4.28, signal.z], [0.09 * redScale, 0.09 * redScale, 0.09 * redScale])
      setInstance(yellowRef.current, i, dummy, [signal.x, CITY_BASE_Y + 4.04, signal.z], [0.09 * yellowScale, 0.09 * yellowScale, 0.09 * yellowScale])
      setInstance(greenRef.current, i, dummy, [signal.x, CITY_BASE_Y + 3.8, signal.z], [0.09 * greenScale, 0.09 * greenScale, 0.09 * greenScale])
    }
    redRef.current.instanceMatrix.needsUpdate = true
    yellowRef.current.instanceMatrix.needsUpdate = true
    greenRef.current.instanceMatrix.needsUpdate = true
    exposeRenderingMetadata({
      trafficSignals: {
        ...(typeof window !== 'undefined' ? window.__REALCITY_RENDERING__?.trafficSignals || {} : {}),
        heads: signals.length,
        currentPhase: phase.kind,
        currentPhaseId: phase.id,
        currentLabel: phase.label,
        signalModel: phase.signalModel,
        cycleSeconds: Number((phase.cycleSeconds || 0).toFixed(2)),
        actuatedGreenSeconds: phase.actuationPolicy?.mode === 'actuated-detector-pressure' ? phase.duration : null,
        detectorPressure: phase.detectorPressure,
        sumoState: phase.sumoState,
        vehicleLinks: phase.vehicleLinks,
        movementLinks: phase.movementLinks,
        movementPriority: phase.movementPriority,
        protectedLeftTurnWindow: !!phase.leftTurnProtected,
        leftTurnWindowSeconds: phase.leftTurnWindowSeconds || 0,
        pedestrianLinks: phase.pedestrianLinks,
        noPedestrianStart: phase.noPedestrianStart,
        redHeads,
        yellowHeads,
        greenHeads,
      },
    })
  })

  return (
    <>
      <instancedMesh ref={poleRef} args={[undefined, undefined, signals.length]} castShadow frustumCulled={false}>
        <cylinderGeometry args={[1, 1, 1, 8]} />
        <meshStandardMaterial color="#22262a" roughness={0.5} metalness={0.45} />
      </instancedMesh>
      <instancedMesh ref={headRef} args={[undefined, undefined, signals.length]} castShadow frustumCulled={false}>
        <boxGeometry args={[1, 1, 1]} />
        <meshStandardMaterial color="#111315" roughness={0.38} metalness={0.2} />
      </instancedMesh>
      <instancedMesh ref={redRef} args={[undefined, undefined, signals.length]} frustumCulled={false}>
        <sphereGeometry args={[1, 8, 6]} />
        <meshStandardMaterial color="#ff6a60" emissive="#ff2f29" emissiveIntensity={1.3} />
      </instancedMesh>
      <instancedMesh ref={yellowRef} args={[undefined, undefined, signals.length]} frustumCulled={false}>
        <sphereGeometry args={[1, 8, 6]} />
        <meshStandardMaterial color="#ffd45e" emissive="#ffb300" emissiveIntensity={1.2} />
      </instancedMesh>
      <instancedMesh ref={greenRef} args={[undefined, undefined, signals.length]} frustumCulled={false}>
        <sphereGeometry args={[1, 8, 6]} />
        <meshStandardMaterial color="#64ffa6" emissive="#1fd86d" emissiveIntensity={1.15} />
      </instancedMesh>
    </>
  )
}

function PedestrianSignals({ roads, mobilitySystem }) {
  const poleRef = useRef()
  const headRef = useRef()
  const waitRef = useRef()
  const walkRef = useRef()
  const plateRef = useRef()
  const { mainVertical, mainHorizontal } = useRoadLayout(roads)
  const signals = useMemo(() => {
    const items = []
    for (const h of mainHorizontal) {
      for (const v of mainVertical) {
        if (Math.hypot(v.x, h.z) > CITY_GRID_HALF * 0.94) continue
        const hCurb = h.width * 0.76
        const vCurb = v.width * 0.76
        const offset = 5.6
        items.push({ x: v.x - offset, z: h.z - hCurb, yaw: 0, crossedAxis: 'x', roadName: h.name, crossRoadName: v.name })
        items.push({ x: v.x + offset, z: h.z + hCurb, yaw: Math.PI, crossedAxis: 'x', roadName: h.name, crossRoadName: v.name })
        items.push({ x: v.x - vCurb, z: h.z + offset, yaw: Math.PI / 2, crossedAxis: 'z', roadName: v.name, crossRoadName: h.name })
        items.push({ x: v.x + vCurb, z: h.z - offset, yaw: -Math.PI / 2, crossedAxis: 'z', roadName: v.name, crossRoadName: h.name })
      }
    }
    return items
  }, [mainHorizontal, mainVertical])

  useEffect(() => {
    exposeRenderingMetadata({
      pedestrianSignals: {
        heads: signals.length,
        labeledHeads: Math.min(24, signals.length),
        placement: 'curb-side crosswalk approach heads',
        rule: 'WALK lights activate only during the actuated protected phase where the crossed vehicle axis is red; yellow/all-red and protected-left-turn windows are clearance/no-start waits',
      },
    })
  }, [signals.length])

  useLayoutEffect(() => {
    if (!poleRef.current || !headRef.current || !waitRef.current || !walkRef.current || !plateRef.current) return
    const dummy = new THREE.Object3D()
    signals.forEach((signal, i) => {
      setInstance(poleRef.current, i, dummy, [signal.x, CITY_BASE_Y + 1.42, signal.z], [0.052, 2.84, 0.052])
      setInstance(headRef.current, i, dummy, [signal.x, CITY_BASE_Y + 2.92, signal.z], [0.58, 0.78, 0.16], signal.yaw)
      setInstance(plateRef.current, i, dummy, [signal.x, CITY_BASE_Y + 2.25, signal.z], [0.7, 0.2, 0.08], signal.yaw)
      setInstance(waitRef.current, i, dummy, [signal.x, CITY_BASE_Y + 3.1, signal.z], [0.16, 0.16, 0.16])
      setInstance(walkRef.current, i, dummy, [signal.x, CITY_BASE_Y + 2.74, signal.z], [0.13, 0.13, 0.13])
    })
    poleRef.current.instanceMatrix.needsUpdate = true
    headRef.current.instanceMatrix.needsUpdate = true
    plateRef.current.instanceMatrix.needsUpdate = true
    waitRef.current.instanceMatrix.needsUpdate = true
    walkRef.current.instanceMatrix.needsUpdate = true
  }, [signals])

  useFrame(() => {
    if (!waitRef.current || !walkRef.current || !signals.length) return
    const timeMinutes = useCityStore.getState().timeMinutes
    const phase = trafficPhaseAt(timeMinutes, mobilitySystem)
    const dummy = new THREE.Object3D()
    let walkHeads = 0
    let waitHeads = 0
    let clearanceHeads = 0
    for (let i = 0; i < signals.length; i += 1) {
      const signal = signals[i]
      const pedestrianSignal = pedestrianSignalForAxis(signal.crossedAxis, timeMinutes, mobilitySystem)
      const canWalk = pedestrianSignal.walk
      if (canWalk) walkHeads += 1
      else {
        waitHeads += 1
        if (pedestrianSignal.clearance) clearanceHeads += 1
      }
      const waitScale = canWalk ? 0.055 : 0.17
      const walkScale = canWalk ? 0.17 : 0.055
      setInstance(waitRef.current, i, dummy, [signal.x, CITY_BASE_Y + 3.1, signal.z], [waitScale, waitScale, waitScale])
      setInstance(walkRef.current, i, dummy, [signal.x, CITY_BASE_Y + 2.74, signal.z], [walkScale * 0.86, walkScale * 1.18, walkScale * 0.86])
    }
    waitRef.current.instanceMatrix.needsUpdate = true
    walkRef.current.instanceMatrix.needsUpdate = true
    exposeRenderingMetadata({
      pedestrianSignals: {
        ...(typeof window !== 'undefined' ? window.__REALCITY_RENDERING__?.pedestrianSignals || {} : {}),
        heads: signals.length,
        walkHeads,
        waitHeads,
        clearanceHeads,
        currentPhaseId: phase.id,
        currentPhase: phase.kind,
        pedestrianLinks: phase.pedestrianLinks,
        signalModel: phase.signalModel,
        liveSignalCoupling: 'protected-walk-only-when-crossed-road-vehicle-red-and-opposing-axis-green-not-in-protected-left-window',
      },
    })
  })

  return (
    <>
      <instancedMesh ref={poleRef} args={[undefined, undefined, signals.length]} castShadow frustumCulled={false}>
        <cylinderGeometry args={[1, 1, 1, 8]} />
        <meshStandardMaterial color="#23272b" roughness={0.46} metalness={0.54} />
      </instancedMesh>
      <instancedMesh ref={headRef} args={[undefined, undefined, signals.length]} castShadow frustumCulled={false}>
        <boxGeometry args={[1, 1, 1]} />
        <meshStandardMaterial color="#101315" roughness={0.34} metalness={0.22} />
      </instancedMesh>
      <instancedMesh ref={plateRef} args={[undefined, undefined, signals.length]} castShadow frustumCulled={false}>
        <boxGeometry args={[1, 1, 1]} />
        <meshStandardMaterial color="#2f3b42" roughness={0.38} metalness={0.32} />
      </instancedMesh>
      <instancedMesh ref={waitRef} args={[undefined, undefined, signals.length]} frustumCulled={false}>
        <boxGeometry args={[1, 1, 1]} />
        <meshStandardMaterial color="#ff766d" emissive="#ff302b" emissiveIntensity={1.35} roughness={0.28} />
      </instancedMesh>
      <instancedMesh ref={walkRef} args={[undefined, undefined, signals.length]} frustumCulled={false}>
        <capsuleGeometry args={[1, 0.9, 4, 8]} />
        <meshStandardMaterial color="#7cffad" emissive="#1ede70" emissiveIntensity={1.28} roughness={0.28} />
      </instancedMesh>
      {signals.slice(0, 24).map((signal, index) => (
        <Billboard key={`ped-signal-label-${index}-${signal.x}-${signal.z}`} position={[signal.x, CITY_BASE_Y + 2.25, signal.z]}>
          <Text fontSize={0.13} maxWidth={1.8} textAlign="center" color="#f8fbff" outlineWidth={0.012} outlineColor="#07111c">
            PED XING
          </Text>
        </Billboard>
      ))}
    </>
  )
}

function RoadNameSigns({ roads }) {
  const { mainVertical, mainHorizontal } = useRoadLayout(roads)
  const signs = useMemo(() => {
    const items = []
    let count = 0
    for (const h of mainHorizontal) {
      for (const v of mainVertical) {
        if (Math.hypot(v.x, h.z) > CITY_GRID_HALF * 0.62) continue
        if (count % 2 === 0) items.push({ x: v.x + v.width * 0.82, z: h.z + h.width * 0.82, primary: h.name, secondary: v.name })
        count += 1
      }
    }
    return items.slice(0, 28)
  }, [mainHorizontal, mainVertical])

  return (
    <>
      {signs.map(sign => (
        <group key={`${sign.primary}-${sign.secondary}-${sign.x}-${sign.z}`} position={[sign.x, CITY_BASE_Y, sign.z]}>
          <mesh castShadow position={[0, 1.6, 0]}>
            <cylinderGeometry args={[0.035, 0.035, 3.2, 8]} />
            <meshStandardMaterial color="#384147" roughness={0.42} metalness={0.55} />
          </mesh>
          <Billboard position={[0, 3.3, 0]}>
            <mesh castShadow>
              <boxGeometry args={[6.6, 1.05, 0.12]} />
              <meshStandardMaterial color="#175f54" roughness={0.36} metalness={0.16} />
            </mesh>
            <Text position={[0, 0.18, 0.08]} fontSize={0.32} maxWidth={6} textAlign="center" color="#f8fbff">
              {sign.primary}
            </Text>
            <Text position={[0, -0.22, 0.08]} fontSize={0.26} maxWidth={6} textAlign="center" color="#cfeee8">
              {sign.secondary}
            </Text>
          </Billboard>
        </group>
      ))}
    </>
  )
}

function TransitAndTaxiStops({ roads }) {
  const shelterRef = useRef()
  const poleRef = useRef()
  const signRef = useRef()
  const { mainHorizontal, mainVertical } = useRoadLayout(roads)
  const stops = useMemo(() => {
    const items = []
    const major = [...mainHorizontal, ...mainVertical]
      .filter(road => Math.hypot(road.axis === 'x' ? 0 : road.x, road.axis === 'x' ? road.z : 0) < CITY_GRID_HALF * 0.72)
    for (let i = 0; i < major.length; i += 2) {
      const road = major[i]
      const taxi = i % 4 === 0
      if (road.axis === 'x') {
        const x = -CITY_GRID_HALF * 0.62 + (i % 7) * ROAD_SPACING * 1.9
        items.push({ x, z: road.z + road.width * 1.24, yaw: Math.PI / 2, taxi, roadName: road.name })
      } else {
        const z = -CITY_GRID_HALF * 0.62 + (i % 7) * ROAD_SPACING * 1.9
        items.push({ x: road.x - road.width * 1.24, z, yaw: 0, taxi, roadName: road.name })
      }
    }
    return items.slice(0, 30)
  }, [mainHorizontal, mainVertical])

  useLayoutEffect(() => {
    if (!shelterRef.current || !poleRef.current || !signRef.current) return
    const dummy = new THREE.Object3D()
    const color = new THREE.Color()
    stops.forEach((stop, i) => {
      setInstance(shelterRef.current, i, dummy, [stop.x, CITY_BASE_Y + 1.25, stop.z], [3.8, 2.5, 0.22], stop.yaw)
      setInstance(poleRef.current, i, dummy, [stop.x + Math.sin(stop.yaw) * 2.55, CITY_BASE_Y + 1.7, stop.z + Math.cos(stop.yaw) * 2.55], [0.055, 3.4, 0.055])
      setInstance(signRef.current, i, dummy, [stop.x + Math.sin(stop.yaw) * 2.55, CITY_BASE_Y + 3.38, stop.z + Math.cos(stop.yaw) * 2.55], [0.58, 0.58, 0.08], stop.yaw)
      signRef.current.setColorAt(i, color.set(stop.taxi ? '#f6c445' : '#4aadff'))
    })
    shelterRef.current.instanceMatrix.needsUpdate = true
    poleRef.current.instanceMatrix.needsUpdate = true
    signRef.current.instanceMatrix.needsUpdate = true
    if (signRef.current.instanceColor) signRef.current.instanceColor.needsUpdate = true
  }, [stops])

  return (
    <>
      <instancedMesh ref={shelterRef} args={[undefined, undefined, stops.length]} castShadow receiveShadow frustumCulled={false}>
        <boxGeometry args={[1, 1, 1]} />
        <meshStandardMaterial color="#26323a" roughness={0.32} metalness={0.28} transparent opacity={0.82} />
      </instancedMesh>
      <instancedMesh ref={poleRef} args={[undefined, undefined, stops.length]} castShadow frustumCulled={false}>
        <cylinderGeometry args={[1, 1, 1, 8]} />
        <meshStandardMaterial color="#d1d7d9" roughness={0.36} metalness={0.58} />
      </instancedMesh>
      <instancedMesh ref={signRef} args={[undefined, undefined, stops.length]} castShadow frustumCulled={false}>
        <boxGeometry args={[1, 1, 1]} />
        <meshStandardMaterial color="#ffffff" vertexColors emissive="#17212b" emissiveIntensity={0.12} roughness={0.34} metalness={0.18} />
      </instancedMesh>
      {stops.slice(0, 12).map(stop => (
        <Billboard key={`label-${stop.x}-${stop.z}`} position={[stop.x + Math.sin(stop.yaw) * 2.55, CITY_BASE_Y + 4.15, stop.z + Math.cos(stop.yaw) * 2.55]}>
          <Text fontSize={0.36} maxWidth={4.4} textAlign="center" color={stop.taxi ? '#fff7b0' : '#d9efff'} outlineWidth={0.035} outlineColor="#07111d">
            {stop.taxi ? 'TAXI' : 'BUS'}
          </Text>
        </Billboard>
      ))}
    </>
  )
}

function orientedOffset(item, along = 0, outward = 0) {
  return {
    x: item.x + Math.cos(item.yaw) * along + Math.sin(item.yaw) * outward,
    z: item.z - Math.sin(item.yaw) * along + Math.cos(item.yaw) * outward,
  }
}

function SharedMobilityDocks({ roads, mobilitySystem }) {
  const padRef = useRef()
  const kioskRef = useRef()
  const rackRef = useRef()
  const bikeFrameRef = useRef()
  const bikeWheelRef = useRef()
  const bikeHandleRef = useRef()
  const scooterDeckRef = useRef()
  const scooterStemRef = useRef()
  const scooterWheelRef = useRef()
  const curbMarkRef = useRef()
  const curbSignRef = useRef()

  const details = useMemo(() => {
    const roadById = new Map(roads.map(road => [road.id, road]))
    const stations = (mobilitySystem?.gbfs?.stations || []).map((station, index) => {
      const road = roadById.get(station.roadId) || roads[0]
      const yaw = road?.axis === 'z' ? Math.PI / 2 : 0
      return { ...station, index, road, yaw }
    })
    const racks = []
    const bikes = []
    const scooters = []
    stations.forEach(station => {
      const rackCount = Math.min(8, Math.max(4, Math.round(station.capacity / 2)))
      for (let slot = 0; slot < rackCount; slot += 1) {
        const along = (slot - (rackCount - 1) / 2) * 0.72
        racks.push({ ...orientedOffset(station, along, -0.42), yaw: station.yaw, stationId: station.id })
      }
      const bikeCount = Math.min(5, station.numBikesAvailable || 0)
      for (let slot = 0; slot < bikeCount; slot += 1) {
        const along = (slot - (bikeCount - 1) / 2) * 0.82
        bikes.push({ ...orientedOffset(station, along, 0.08), yaw: station.yaw, stationId: station.id })
      }
      const scooterCount = Math.min(3, station.numScootersAvailable || 0)
      for (let slot = 0; slot < scooterCount; slot += 1) {
        const along = 2.5 + slot * 0.58
        scooters.push({ ...orientedOffset(station, along, 0.18), yaw: station.yaw, stationId: station.id })
      }
    })

    const curbZones = (mobilitySystem?.smartCity?.curbZones || []).map((zone, index) => {
      const road = roadById.get(zone.roadId) || roads[0]
      return {
        ...zone,
        index,
        yaw: road?.axis === 'z' ? Math.PI / 2 : 0,
      }
    })

    return { stations, racks, bikes, scooters, curbZones }
  }, [roads, mobilitySystem])

  useEffect(() => {
    exposeRenderingMetadata({
      sharedMobility: {
        gbfsStationModels: details.stations.length,
        dockPads: details.stations.length,
        racks: details.racks.length,
        parkedBikeProps: details.bikes.length,
        parkedScooterProps: details.scooters.length,
        curbZoneMarkings: details.curbZones.length,
        curbZonePurposes: [...new Set(details.curbZones.map(zone => zone.purpose))],
        standard: 'GBFS station_information/station_status + SmartCities ParkingSpot curb policy',
        placementRule: 'docks and scooters stay on curb-adjacent painted boxes with sidewalk clearance',
      },
    })
  }, [details])

  useLayoutEffect(() => {
    if (!padRef.current || !kioskRef.current || !rackRef.current || !bikeFrameRef.current || !bikeWheelRef.current || !bikeHandleRef.current || !scooterDeckRef.current || !scooterStemRef.current || !scooterWheelRef.current || !curbMarkRef.current || !curbSignRef.current) return
    const dummy = new THREE.Object3D()
    const color = new THREE.Color()
    const purposeColor = {
      'taxi-stand': '#f6c445',
      'delivery-loading': '#60a5fa',
      'bus-stop': '#34d399',
      'short-stay-parking': '#c4b5fd',
    }

    details.stations.forEach((station, i) => {
      setInstance(padRef.current, i, dummy, [station.x, CITY_BASE_Y + 0.245, station.z], [5.7, 0.035, 2.35], station.yaw)
      const kiosk = orientedOffset(station, -2.85, -0.92)
      setInstance(kioskRef.current, i, dummy, [kiosk.x, CITY_BASE_Y + 0.92, kiosk.z], [0.42, 1.72, 0.34], station.yaw)
    })

    details.racks.forEach((rack, i) => {
      setInstance(rackRef.current, i, dummy, [rack.x, CITY_BASE_Y + 0.52, rack.z], [0.05, 1.0, 0.36], rack.yaw)
    })

    details.bikes.forEach((bike, i) => {
      const wheelA = orientedOffset(bike, -0.27, 0)
      const wheelB = orientedOffset(bike, 0.27, 0)
      setInstance(bikeFrameRef.current, i, dummy, [bike.x, CITY_BASE_Y + 0.72, bike.z], [0.56, 0.08, 0.42], bike.yaw)
      setInstance(bikeHandleRef.current, i, dummy, [bike.x + Math.cos(bike.yaw) * 0.42, CITY_BASE_Y + 0.98, bike.z - Math.sin(bike.yaw) * 0.42], [0.56, 0.045, 0.05], bike.yaw)
      setInstance(bikeWheelRef.current, i * 2, dummy, [wheelA.x, CITY_BASE_Y + 0.47, wheelA.z], [0.22, 0.055, 0.22], bike.yaw + Math.PI / 2)
      setInstance(bikeWheelRef.current, i * 2 + 1, dummy, [wheelB.x, CITY_BASE_Y + 0.47, wheelB.z], [0.22, 0.055, 0.22], bike.yaw + Math.PI / 2)
    })

    details.scooters.forEach((scooter, i) => {
      const front = orientedOffset(scooter, 0.28, 0)
      const rear = orientedOffset(scooter, -0.24, 0)
      setInstance(scooterDeckRef.current, i, dummy, [scooter.x, CITY_BASE_Y + 0.38, scooter.z], [0.18, 0.055, 0.68], scooter.yaw)
      setInstance(scooterStemRef.current, i, dummy, [front.x, CITY_BASE_Y + 0.82, front.z], [0.05, 0.82, 0.05], scooter.yaw)
      setInstance(scooterWheelRef.current, i * 2, dummy, [front.x, CITY_BASE_Y + 0.32, front.z], [0.11, 0.04, 0.11], scooter.yaw + Math.PI / 2)
      setInstance(scooterWheelRef.current, i * 2 + 1, dummy, [rear.x, CITY_BASE_Y + 0.32, rear.z], [0.11, 0.04, 0.11], scooter.yaw + Math.PI / 2)
    })

    details.curbZones.forEach((zone, i) => {
      setInstance(curbMarkRef.current, i, dummy, [zone.x, CITY_BASE_Y + 0.258, zone.z], [6.2, 0.032, 1.05], zone.yaw)
      setInstance(curbSignRef.current, i, dummy, [zone.x, CITY_BASE_Y + 1.28, zone.z], [0.48, 1.1, 0.08], zone.yaw)
      curbMarkRef.current.setColorAt(i, color.set(purposeColor[zone.purpose] || '#93c5fd'))
      curbSignRef.current.setColorAt(i, color.set(purposeColor[zone.purpose] || '#93c5fd'))
    })

    padRef.current.instanceMatrix.needsUpdate = true
    kioskRef.current.instanceMatrix.needsUpdate = true
    rackRef.current.instanceMatrix.needsUpdate = true
    bikeFrameRef.current.instanceMatrix.needsUpdate = true
    bikeWheelRef.current.instanceMatrix.needsUpdate = true
    bikeHandleRef.current.instanceMatrix.needsUpdate = true
    scooterDeckRef.current.instanceMatrix.needsUpdate = true
    scooterStemRef.current.instanceMatrix.needsUpdate = true
    scooterWheelRef.current.instanceMatrix.needsUpdate = true
    curbMarkRef.current.instanceMatrix.needsUpdate = true
    curbSignRef.current.instanceMatrix.needsUpdate = true
    if (curbMarkRef.current.instanceColor) curbMarkRef.current.instanceColor.needsUpdate = true
    if (curbSignRef.current.instanceColor) curbSignRef.current.instanceColor.needsUpdate = true
  }, [details])

  return (
    <>
      <instancedMesh ref={padRef} args={[undefined, undefined, details.stations.length]} receiveShadow frustumCulled={false}>
        <boxGeometry args={[1, 1, 1]} />
        <meshStandardMaterial color="#123841" emissive="#0b6b78" emissiveIntensity={0.1} roughness={0.54} metalness={0.1} />
      </instancedMesh>
      <instancedMesh ref={kioskRef} args={[undefined, undefined, details.stations.length]} castShadow receiveShadow frustumCulled={false}>
        <boxGeometry args={[1, 1, 1]} />
        <meshStandardMaterial color="#d9f99d" emissive="#5eead4" emissiveIntensity={0.18} roughness={0.38} metalness={0.32} />
      </instancedMesh>
      <instancedMesh ref={rackRef} args={[undefined, undefined, details.racks.length]} castShadow frustumCulled={false}>
        <torusGeometry args={[1, 0.06, 6, 12, Math.PI]} />
        <meshStandardMaterial color="#b8c4c7" roughness={0.34} metalness={0.62} />
      </instancedMesh>
      <instancedMesh ref={bikeFrameRef} args={[undefined, undefined, details.bikes.length]} castShadow frustumCulled={false}>
        <boxGeometry args={[1, 1, 1]} />
        <meshStandardMaterial color="#38bdf8" roughness={0.36} metalness={0.32} />
      </instancedMesh>
      <instancedMesh ref={bikeWheelRef} args={[undefined, undefined, details.bikes.length * 2]} castShadow frustumCulled={false}>
        <torusGeometry args={[1, 0.18, 8, 14]} />
        <meshStandardMaterial color="#111827" roughness={0.82} metalness={0.05} />
      </instancedMesh>
      <instancedMesh ref={bikeHandleRef} args={[undefined, undefined, details.bikes.length]} castShadow frustumCulled={false}>
        <boxGeometry args={[1, 1, 1]} />
        <meshStandardMaterial color="#e5e7eb" roughness={0.34} metalness={0.48} />
      </instancedMesh>
      <instancedMesh ref={scooterDeckRef} args={[undefined, undefined, details.scooters.length]} castShadow frustumCulled={false}>
        <boxGeometry args={[1, 1, 1]} />
        <meshStandardMaterial color="#f97316" roughness={0.4} metalness={0.24} />
      </instancedMesh>
      <instancedMesh ref={scooterStemRef} args={[undefined, undefined, details.scooters.length]} castShadow frustumCulled={false}>
        <cylinderGeometry args={[1, 1, 1, 8]} />
        <meshStandardMaterial color="#e5e7eb" roughness={0.32} metalness={0.56} />
      </instancedMesh>
      <instancedMesh ref={scooterWheelRef} args={[undefined, undefined, details.scooters.length * 2]} castShadow frustumCulled={false}>
        <torusGeometry args={[1, 0.22, 8, 12]} />
        <meshStandardMaterial color="#111827" roughness={0.84} metalness={0.04} />
      </instancedMesh>
      <instancedMesh ref={curbMarkRef} args={[undefined, undefined, details.curbZones.length]} receiveShadow frustumCulled={false}>
        <boxGeometry args={[1, 1, 1]} />
        <meshStandardMaterial color="#ffffff" vertexColors transparent opacity={0.72} roughness={0.5} metalness={0.08} />
      </instancedMesh>
      <instancedMesh ref={curbSignRef} args={[undefined, undefined, details.curbZones.length]} castShadow frustumCulled={false}>
        <boxGeometry args={[1, 1, 1]} />
        <meshStandardMaterial color="#ffffff" vertexColors emissive="#0f172a" emissiveIntensity={0.1} roughness={0.34} metalness={0.22} />
      </instancedMesh>
      {details.stations.slice(0, 10).map(station => (
        <Billboard key={`mobility-label-${station.id}`} position={[station.x, CITY_BASE_Y + 2.15, station.z]}>
          <Text fontSize={0.24} maxWidth={5.2} textAlign="center" color="#e0fffb" outlineWidth={0.025} outlineColor="#062025">
            GBFS DOCK
          </Text>
        </Billboard>
      ))}
    </>
  )
}

function PlantersAndBenches({ roads }) {
  const planterRef = useRef()
  const shrubRef = useRef()
  const benchRef = useRef()
  const { mainHorizontal } = useRoadLayout(roads)
  const items = useMemo(() => {
    const placed = []
    const coreRoads = mainHorizontal.filter(road => Math.abs(road.z) < ROAD_SPACING * 3)
    for (const road of coreRoads) {
      for (let x = -CITY_GRID_HALF * 0.58; x < CITY_GRID_HALF * 0.58; x += ROAD_SPACING * 1.2) {
        if (Math.abs(x) < ROAD_SPACING) continue
        placed.push({ x, z: road.z + road.width * 1.35, yaw: 0 })
        placed.push({ x: x + ROAD_SPACING * 0.42, z: road.z - road.width * 1.35, yaw: Math.PI })
      }
    }
    return placed
  }, [mainHorizontal])

  useLayoutEffect(() => {
    if (!planterRef.current || !shrubRef.current || !benchRef.current) return
    const dummy = new THREE.Object3D()
    items.forEach((item, i) => {
      setInstance(planterRef.current, i, dummy, [item.x, CITY_BASE_Y + 0.34, item.z], [2.4, 0.52, 0.82], item.yaw)
      setInstance(shrubRef.current, i, dummy, [item.x, CITY_BASE_Y + 0.95, item.z], [1.92, 0.74, 0.58], item.yaw)
      setInstance(benchRef.current, i, dummy, [item.x + Math.sin(item.yaw) * 2.4, CITY_BASE_Y + 0.47, item.z + Math.cos(item.yaw) * 2.4], [1.9, 0.18, 0.42], item.yaw)
    })
    planterRef.current.instanceMatrix.needsUpdate = true
    shrubRef.current.instanceMatrix.needsUpdate = true
    benchRef.current.instanceMatrix.needsUpdate = true
  }, [items])

  return (
    <>
      <instancedMesh ref={planterRef} args={[undefined, undefined, items.length]} castShadow receiveShadow frustumCulled={false}>
        <boxGeometry args={[1, 1, 1]} />
        <meshStandardMaterial color="#5d5548" roughness={0.82} />
      </instancedMesh>
      <instancedMesh ref={shrubRef} args={[undefined, undefined, items.length]} castShadow frustumCulled={false}>
        <dodecahedronGeometry args={[1, 0]} />
        <meshStandardMaterial color="#3d8750" roughness={0.88} flatShading />
      </instancedMesh>
      <instancedMesh ref={benchRef} args={[undefined, undefined, items.length]} castShadow receiveShadow frustumCulled={false}>
        <boxGeometry args={[1, 1, 1]} />
        <meshStandardMaterial color="#8a6a4a" roughness={0.72} />
      </instancedMesh>
    </>
  )
}

function Bollards({ roads }) {
  const ref = useRef()
  const { mainVertical, mainHorizontal } = useRoadLayout(roads)
  const bollards = useMemo(() => {
    const items = []
    const spacing = 19
    for (const road of mainHorizontal) {
      for (let x = road.from + 28; x < road.to - 28; x += spacing) {
        if (Math.hypot(x, road.z) > CITY_GRID_HALF * 0.72) continue
        items.push({ x, z: road.z - road.width * 0.82 })
        items.push({ x, z: road.z + road.width * 0.82 })
      }
    }
    for (const road of mainVertical) {
      for (let z = road.from + 28; z < road.to - 28; z += spacing) {
        if (Math.hypot(road.x, z) > CITY_GRID_HALF * 0.72) continue
        items.push({ x: road.x - road.width * 0.82, z })
        items.push({ x: road.x + road.width * 0.82, z })
      }
    }
    return items.slice(0, 520)
  }, [mainHorizontal, mainVertical])

  useLayoutEffect(() => {
    if (!ref.current) return
    const dummy = new THREE.Object3D()
    bollards.forEach((item, i) => {
      setInstance(ref.current, i, dummy, [item.x, CITY_BASE_Y + 0.36, item.z], [0.12, 0.72, 0.12])
    })
    ref.current.instanceMatrix.needsUpdate = true
  }, [bollards])

  return (
    <instancedMesh ref={ref} args={[undefined, undefined, bollards.length]} castShadow frustumCulled={false}>
      <cylinderGeometry args={[1, 1, 1, 8]} />
      <meshStandardMaterial color="#d4d0bf" roughness={0.54} metalness={0.16} />
    </instancedMesh>
  )
}

function LaneReflectors({ roads }) {
  const reflectorRef = useRef()
  const arrowsRef = useRef()
  const turnPocketRef = useRef()
  const turnPocketEdgeRef = useRef()
  const turnArrowStemRef = useRef()
  const turnArrowBendRef = useRef()
  const turnArrowHeadRef = useRef()
  const yieldAreaRef = useRef()
  const yieldChevronRef = useRef()
  const flatTriangleGeometry = useMemo(() => makeFlatTriangleGeometry(), [])
  const { mainVertical, mainHorizontal } = useRoadLayout(roads)
  const details = useMemo(() => {
    const reflectors = []
    const arrows = []
    const turnPockets = []
    const turnPocketEdges = []
    const turnArrowStems = []
    const turnArrowBends = []
    const turnArrowHeads = []
    const yieldAreas = []
    const yieldChevrons = []
    const mainRoads = [...mainHorizontal, ...mainVertical]
    const addLanePoint = (road, along, lateral) => road.axis === 'x'
      ? { x: along, z: road.z + lateral }
      : { x: road.x + lateral, z: along }
    const yawFor = (road, direction) => road.axis === 'x'
      ? (direction > 0 ? Math.PI / 2 : -Math.PI / 2)
      : (direction > 0 ? 0 : Math.PI)
    const addApproachMarkings = (road, crossCoord, crossWidth, direction) => {
      const laneOffset = road.width * 0.27
      const laneLateral = road.axis === 'x' ? direction * laneOffset : -direction * laneOffset
      const turnLateral = laneLateral * 0.34
      const yieldLateral = laneLateral * 1.08
      const pocketLength = road.laneModel?.turnPocketLengthMeters || (road.main ? 34 : 18)
      const signalDistance = road.laneModel?.turnSignalDistanceMeters || (road.main ? 52 : 34)
      const stopAlong = crossCoord - direction * crossWidth * 0.92
      const pocketAlong = stopAlong - direction * pocketLength * 0.54
      const arrowAlong = stopAlong - direction * Math.min(signalDistance * 0.32, 18)
      const yieldAlong = stopAlong - direction * Math.min(signalDistance * 0.43, 23)
      const yaw = yawFor(road, direction)
      const pocket = addLanePoint(road, pocketAlong, turnLateral)
      const arrow = addLanePoint(road, arrowAlong, turnLateral)
      const yieldPoint = addLanePoint(road, yieldAlong, yieldLateral)
      const lateralBend = Math.max(1.4, road.width * 0.12)
      const leftBend = addLanePoint(road, arrowAlong + direction * 2.4, turnLateral - Math.sign(laneLateral || 1) * lateralBend)

      turnPockets.push({ ...pocket, sx: 1.18, sz: pocketLength, yaw })
      turnPocketEdges.push({ ...addLanePoint(road, pocketAlong, turnLateral - Math.sign(laneLateral || 1) * 0.82), sx: 0.16, sz: pocketLength * 0.94, yaw })
      turnPocketEdges.push({ ...addLanePoint(road, pocketAlong, turnLateral + Math.sign(laneLateral || 1) * 0.82), sx: 0.16, sz: pocketLength * 0.94, yaw })
      turnArrowStems.push({ ...arrow, sx: 0.34, sz: 8.8, yaw })
      turnArrowBends.push({ ...leftBend, sx: 3.4, sz: 0.36, yaw: yaw + Math.PI / 2 })
      turnArrowHeads.push({ ...addLanePoint(road, arrowAlong + direction * 5.2, turnLateral - Math.sign(laneLateral || 1) * lateralBend * 1.28), sx: 1.28, sz: 1.7, yaw: yaw + Math.PI / 2 })
      yieldAreas.push({ ...yieldPoint, sx: 2.8, sz: 3.1, yaw })
      yieldChevrons.push({ ...addLanePoint(road, yieldAlong - direction * 1.8, yieldLateral), sx: 0.18, sz: 2.7, yaw: yaw + 0.55 })
      yieldChevrons.push({ ...addLanePoint(road, yieldAlong + direction * 1.8, yieldLateral), sx: 0.18, sz: 2.7, yaw: yaw - 0.55 })
    }

    for (const road of mainRoads) {
      const laneOffset = road.width * 0.27
      for (let p = road.from + 46; p < road.to - 46; p += 38) {
        if (Math.hypot(road.axis === 'x' ? p : road.x, road.axis === 'x' ? road.z : p) > CITY_GRID_HALF * 0.88) continue
        if (road.axis === 'x') {
          reflectors.push({ x: p, z: road.z - laneOffset * 0.52, sx: 0.42, sz: 0.08, yaw: 0 })
          reflectors.push({ x: p, z: road.z + laneOffset * 0.52, sx: 0.42, sz: 0.08, yaw: 0 })
          if ((p + CITY_GRID_HALF) % 228 < 38) arrows.push({ x: p, z: road.z - laneOffset, sx: 1.1, sz: 2.4, yaw: Math.PI / 2 })
        } else {
          reflectors.push({ x: road.x - laneOffset * 0.52, z: p, sx: 0.08, sz: 0.42, yaw: 0 })
          reflectors.push({ x: road.x + laneOffset * 0.52, z: p, sx: 0.08, sz: 0.42, yaw: 0 })
          if ((p + CITY_GRID_HALF) % 228 < 38) arrows.push({ x: road.x + laneOffset, z: p, sx: 1.1, sz: 2.4, yaw: 0 })
        }
      }
    }
    for (const h of mainHorizontal) {
      for (const v of mainVertical) {
        if (Math.hypot(v.x, h.z) > CITY_GRID_HALF * 0.94) continue
        addApproachMarkings(h, v.x, v.width, 1)
        addApproachMarkings(h, v.x, v.width, -1)
        addApproachMarkings(v, h.z, h.width, 1)
        addApproachMarkings(v, h.z, h.width, -1)
      }
    }
    return {
      reflectors: reflectors.slice(0, 1300),
      arrows: arrows.slice(0, 90),
      turnPockets: turnPockets.slice(0, 120),
      turnPocketEdges: turnPocketEdges.slice(0, 240),
      turnArrowStems: turnArrowStems.slice(0, 120),
      turnArrowBends: turnArrowBends.slice(0, 120),
      turnArrowHeads: turnArrowHeads.slice(0, 120),
      yieldAreas: yieldAreas.slice(0, 120),
      yieldChevrons: yieldChevrons.slice(0, 240),
    }
  }, [mainHorizontal, mainVertical])

  useEffect(() => {
    exposeRenderingMetadata({
      turnLaneMarkings: {
        pocketMarkings: details.turnPockets.length,
        pocketEdgeLines: details.turnPocketEdges.length,
        turnArrowStems: details.turnArrowStems.length,
        turnArrowBends: details.turnArrowBends.length,
        turnArrowHeads: details.turnArrowHeads.length,
        rightTurnYieldAreas: details.yieldAreas.length,
        yieldChevrons: details.yieldChevrons.length,
        flatStencilArrows: true,
        stencilPolicy: 'painted left-turn pockets and right-turn yield areas mirror vehicle turnIntent and turnLaneRule telemetry',
        source: 'road.laneModel turnLanePolicy / turnPocketLengthMeters / turnSignalDistanceMeters',
      },
    })
  }, [details])

  useLayoutEffect(() => {
    if (!reflectorRef.current || !arrowsRef.current || !turnPocketRef.current || !turnPocketEdgeRef.current || !turnArrowStemRef.current || !turnArrowBendRef.current || !turnArrowHeadRef.current || !yieldAreaRef.current || !yieldChevronRef.current) return
    const dummy = new THREE.Object3D()
    details.reflectors.forEach((item, i) => {
      setInstance(reflectorRef.current, i, dummy, [item.x, CITY_BASE_Y + 0.205, item.z], [item.sx, 0.025, item.sz], item.yaw)
    })
    details.arrows.forEach((item, i) => {
      setInstance(arrowsRef.current, i, dummy, [item.x, CITY_BASE_Y + 0.212, item.z], [item.sx, 0.028, item.sz], item.yaw)
    })
    details.turnPockets.forEach((item, i) => {
      setInstance(turnPocketRef.current, i, dummy, [item.x, CITY_BASE_Y + 0.214, item.z], [item.sx, 0.018, item.sz], item.yaw)
    })
    details.turnPocketEdges.forEach((item, i) => {
      setInstance(turnPocketEdgeRef.current, i, dummy, [item.x, CITY_BASE_Y + 0.222, item.z], [item.sx, 0.024, item.sz], item.yaw)
    })
    details.turnArrowStems.forEach((item, i) => {
      setInstance(turnArrowStemRef.current, i, dummy, [item.x, CITY_BASE_Y + 0.236, item.z], [item.sx, 0.03, item.sz], item.yaw)
    })
    details.turnArrowBends.forEach((item, i) => {
      setInstance(turnArrowBendRef.current, i, dummy, [item.x, CITY_BASE_Y + 0.238, item.z], [item.sx, 0.03, item.sz], item.yaw)
    })
    details.turnArrowHeads.forEach((item, i) => {
      setInstance(turnArrowHeadRef.current, i, dummy, [item.x, CITY_BASE_Y + 0.242, item.z], [item.sx, 0.034, item.sz], item.yaw)
    })
    details.yieldAreas.forEach((item, i) => {
      setInstance(yieldAreaRef.current, i, dummy, [item.x, CITY_BASE_Y + 0.218, item.z], [item.sx, 0.018, item.sz], item.yaw)
    })
    details.yieldChevrons.forEach((item, i) => {
      setInstance(yieldChevronRef.current, i, dummy, [item.x, CITY_BASE_Y + 0.246, item.z], [item.sx, 0.03, item.sz], item.yaw)
    })
    reflectorRef.current.instanceMatrix.needsUpdate = true
    arrowsRef.current.instanceMatrix.needsUpdate = true
    turnPocketRef.current.instanceMatrix.needsUpdate = true
    turnPocketEdgeRef.current.instanceMatrix.needsUpdate = true
    turnArrowStemRef.current.instanceMatrix.needsUpdate = true
    turnArrowBendRef.current.instanceMatrix.needsUpdate = true
    turnArrowHeadRef.current.instanceMatrix.needsUpdate = true
    yieldAreaRef.current.instanceMatrix.needsUpdate = true
    yieldChevronRef.current.instanceMatrix.needsUpdate = true
  }, [details])

  return (
    <>
      <instancedMesh ref={reflectorRef} args={[undefined, undefined, details.reflectors.length]} frustumCulled={false}>
        <boxGeometry args={[1, 1, 1]} />
        <meshStandardMaterial color="#f7f3d8" emissive="#fff0a0" emissiveIntensity={0.18} roughness={0.34} />
      </instancedMesh>
      <instancedMesh ref={arrowsRef} args={[undefined, undefined, details.arrows.length]} frustumCulled={false}>
        <primitive object={flatTriangleGeometry} attach="geometry" />
        <meshBasicMaterial color="#f6f9f2" side={THREE.DoubleSide} toneMapped={false} />
      </instancedMesh>
      <instancedMesh ref={turnPocketRef} args={[undefined, undefined, details.turnPockets.length]} frustumCulled={false}>
        <boxGeometry args={[1, 1, 1]} />
        <meshStandardMaterial color="#ece8c7" emissive="#fff3ad" emissiveIntensity={0.05} roughness={0.48} transparent opacity={0.72} />
      </instancedMesh>
      <instancedMesh ref={turnPocketEdgeRef} args={[undefined, undefined, details.turnPocketEdges.length]} frustumCulled={false}>
        <boxGeometry args={[1, 1, 1]} />
        <meshStandardMaterial color="#fff7d6" emissive="#fff2a8" emissiveIntensity={0.18} roughness={0.36} />
      </instancedMesh>
      <instancedMesh ref={turnArrowStemRef} args={[undefined, undefined, details.turnArrowStems.length]} frustumCulled={false}>
        <boxGeometry args={[1, 1, 1]} />
        <meshStandardMaterial color="#f8f5dc" emissive="#ffffff" emissiveIntensity={0.12} roughness={0.38} />
      </instancedMesh>
      <instancedMesh ref={turnArrowBendRef} args={[undefined, undefined, details.turnArrowBends.length]} frustumCulled={false}>
        <boxGeometry args={[1, 1, 1]} />
        <meshStandardMaterial color="#f8f5dc" emissive="#ffffff" emissiveIntensity={0.12} roughness={0.38} />
      </instancedMesh>
      <instancedMesh ref={turnArrowHeadRef} args={[undefined, undefined, details.turnArrowHeads.length]} frustumCulled={false}>
        <primitive object={flatTriangleGeometry} attach="geometry" />
        <meshBasicMaterial color="#ffffff" side={THREE.DoubleSide} toneMapped={false} />
      </instancedMesh>
      <instancedMesh ref={yieldAreaRef} args={[undefined, undefined, details.yieldAreas.length]} frustumCulled={false}>
        <primitive object={flatTriangleGeometry} attach="geometry" />
        <meshBasicMaterial color="#f3ead1" transparent opacity={0.78} side={THREE.DoubleSide} toneMapped={false} />
      </instancedMesh>
      <instancedMesh ref={yieldChevronRef} args={[undefined, undefined, details.yieldChevrons.length]} frustumCulled={false}>
        <boxGeometry args={[1, 1, 1]} />
        <meshStandardMaterial color="#fff6d0" emissive="#fff4a8" emissiveIntensity={0.16} roughness={0.38} />
      </instancedMesh>
    </>
  )
}

function StreetFurniture({ roads }) {
  const kioskRef = useRef()
  const screenRef = useRef()
  const binRef = useRef()
  const { mainHorizontal, mainVertical } = useRoadLayout(roads)
  const items = useMemo(() => {
    const placed = []
    const roadsToUse = [...mainHorizontal, ...mainVertical]
      .filter(road => Math.hypot(road.axis === 'x' ? 0 : road.x, road.axis === 'x' ? road.z : 0) < CITY_GRID_HALF * 0.68)
    roadsToUse.forEach((road, i) => {
      const step = ROAD_SPACING * 2.1
      for (let p = road.from + 70 + (i % 3) * 19; p < road.to - 70 && placed.length < 110; p += step) {
        const side = i % 2 ? -1 : 1
        if (road.axis === 'x') {
          placed.push({ x: p, z: road.z + side * (road.width * 0.86 + 4.4), yaw: side > 0 ? Math.PI : 0, tint: i + p })
        } else {
          placed.push({ x: road.x + side * (road.width * 0.86 + 4.4), z: p, yaw: side > 0 ? -Math.PI / 2 : Math.PI / 2, tint: i + p })
        }
      }
    })
    return placed
  }, [mainHorizontal, mainVertical])

  useLayoutEffect(() => {
    if (!kioskRef.current || !screenRef.current || !binRef.current) return
    const dummy = new THREE.Object3D()
    const color = new THREE.Color()
    const palette = ['#26323a', '#174e62', '#4b394f', '#2e4635', '#5a4334']
    items.forEach((item, i) => {
      setInstance(kioskRef.current, i, dummy, [item.x, CITY_BASE_Y + 1.0, item.z], [1.05, 2.0, 0.46], item.yaw)
      setInstance(screenRef.current, i, dummy, [item.x + Math.sin(item.yaw) * 0.26, CITY_BASE_Y + 1.18, item.z + Math.cos(item.yaw) * 0.26], [0.76, 0.92, 0.035], item.yaw)
      setInstance(binRef.current, i, dummy, [item.x - Math.sin(item.yaw) * 1.22, CITY_BASE_Y + 0.45, item.z - Math.cos(item.yaw) * 1.22], [0.32, 0.9, 0.32])
      kioskRef.current.setColorAt(i, color.set(palette[Math.abs(Math.floor(item.tint)) % palette.length]))
    })
    kioskRef.current.instanceMatrix.needsUpdate = true
    screenRef.current.instanceMatrix.needsUpdate = true
    binRef.current.instanceMatrix.needsUpdate = true
    if (kioskRef.current.instanceColor) kioskRef.current.instanceColor.needsUpdate = true
  }, [items])

  return (
    <>
      <instancedMesh ref={kioskRef} args={[undefined, undefined, items.length]} castShadow receiveShadow frustumCulled={false}>
        <boxGeometry args={[1, 1, 1]} />
        <meshStandardMaterial color="#ffffff" vertexColors roughness={0.38} metalness={0.34} />
      </instancedMesh>
      <instancedMesh ref={screenRef} args={[undefined, undefined, items.length]} frustumCulled={false}>
        <boxGeometry args={[1, 1, 1]} />
        <meshStandardMaterial color="#a7ecff" emissive="#30bfff" emissiveIntensity={0.46} roughness={0.18} metalness={0.16} />
      </instancedMesh>
      <instancedMesh ref={binRef} args={[undefined, undefined, items.length]} castShadow receiveShadow frustumCulled={false}>
        <cylinderGeometry args={[1, 1, 1, 12]} />
        <meshStandardMaterial color="#2d3438" roughness={0.5} metalness={0.32} />
      </instancedMesh>
    </>
  )
}

function ParkedCars({ roads }) {
  const bodyRef = useRef()
  const cabinRef = useRef()
  const { vertical, horizontal } = useRoadLayout(roads)
  const cars = useMemo(() => {
    const items = []
    const allRoads = [...horizontal, ...vertical].filter(road => Math.hypot(road.axis === 'x' ? 0 : road.x, road.axis === 'x' ? road.z : 0) < CITY_GRID_HALF * 0.75)
    for (let i = 0; i < allRoads.length && items.length < 96; i += 2) {
      const road = allRoads[i]
      const side = i % 4 < 2 ? -1 : 1
      const offset = road.width * 0.72 * side
      const step = 116 + (i % 3) * 22
      for (let p = road.from + 42 + (i % 5) * 11; p < road.to - 42 && items.length < 96; p += step) {
        if (road.axis === 'x') {
          items.push({ x: p, z: road.z + offset, yaw: Math.PI / 2, tint: i + p })
        } else {
          items.push({ x: road.x + offset, z: p, yaw: 0, tint: i + p })
        }
      }
    }
    return items
  }, [horizontal, vertical])

  useLayoutEffect(() => {
    if (!bodyRef.current || !cabinRef.current) return
    const dummy = new THREE.Object3D()
    const color = new THREE.Color()
    const palette = ['#ef4444', '#e5e7eb', '#1f2937', '#2563eb', '#16a34a', '#f59e0b', '#6b7280']
    cars.forEach((car, i) => {
      setInstance(bodyRef.current, i, dummy, [car.x, CITY_BASE_Y + 0.55, car.z], [1.95, 0.62, 4.1], car.yaw)
      setInstance(cabinRef.current, i, dummy, [car.x, CITY_BASE_Y + 1.14, car.z - Math.cos(car.yaw) * 0.2], [1.42, 0.52, 1.55], car.yaw)
      bodyRef.current.setColorAt(i, color.set(palette[Math.abs(Math.floor(car.tint)) % palette.length]))
    })
    bodyRef.current.instanceMatrix.needsUpdate = true
    cabinRef.current.instanceMatrix.needsUpdate = true
    if (bodyRef.current.instanceColor) bodyRef.current.instanceColor.needsUpdate = true
  }, [cars])

  return (
    <>
      <instancedMesh ref={bodyRef} args={[undefined, undefined, cars.length]} castShadow receiveShadow frustumCulled={false}>
        <boxGeometry args={[1, 1, 1]} />
        <meshStandardMaterial color="#ffffff" vertexColors roughness={0.34} metalness={0.38} />
      </instancedMesh>
      <instancedMesh ref={cabinRef} args={[undefined, undefined, cars.length]} castShadow receiveShadow frustumCulled={false}>
        <boxGeometry args={[1, 1, 1]} />
        <meshStandardMaterial color="#111827" roughness={0.12} metalness={0.28} />
      </instancedMesh>
    </>
  )
}

function FacadeDetails({ buildings }) {
  const windowRef = useRef()
  const mullionRef = useRef()
  const sillRef = useRef()
  const facadeBandRef = useRef()
  const acRef = useRef()
  const drainPipeRef = useRef()
  const trimRef = useRef()
  const balconyRef = useRef()
  const railRef = useRef()
  const sideRailRef = useRef()
  const awningRef = useRef()
  const signRef = useRef()
  const details = useMemo(() => {
    const windows = []
    const mullions = []
    const sills = []
    const facadeBands = []
    const acUnits = []
    const drainPipes = []
    const trims = []
    const balconies = []
    const rails = []
    const sideRails = []
    const awnings = []
    const signs = []
    ;[...buildings]
      .filter(building => Math.hypot(building.x, building.z) < CITY_GRID_HALF * 0.88)
      .sort((a, b) => Math.hypot(a.x, a.z) - Math.hypot(b.x, b.z))
      .slice(0, 220)
      .forEach((building, i) => {
        const entryFace = entryFaceForBuilding(building)
        const planFaces = building.facadePlan?.faces || {}
        const baseColumns = building.type === 'skyscraper' ? 5 : building.type === 'office' ? 4 : building.type === 'apartment' ? 3 : 2
        const rows = building.type === 'skyscraper'
          ? Math.min(9, Math.max(4, Math.floor(building.h / 7.2)))
          : building.type === 'office'
            ? Math.min(6, Math.max(3, Math.floor(building.h / 6.4)))
            : building.type === 'apartment'
              ? Math.min(5, Math.max(2, Math.floor(building.h / 5.2)))
              : 2
        const panelHeight = building.type === 'house' ? 1.0 : 1.35
        for (const face of FACADE_FACES) {
          const facePlan = planFaces[face] || { glazingDensity: face === entryFace ? 0.8 : 0.58, balconyBias: false }
          const length = faceLength(building, face)
          const faceColumns = Math.max(1, Math.min(baseColumns, Math.floor(length / (building.type === 'house' ? 4.1 : 4.8))))
          const columns = Math.max(1, Math.floor(faceColumns * (0.74 + facePlan.glazingDensity * 0.32)))
          const panelWidth = Math.min(2.25, length * 0.58 / Math.max(1, columns))
          if (building.type !== 'house') {
            const bandHeight = Math.max(3.2, building.h * 0.78)
            const bandY = Math.max(2.8, bandHeight / 2 + 1.2)
            facadeBands.push(facePart(building, face, -length * 0.43, bandY, 0.12, Math.min(building.h - 1.4, bandHeight), 0.21, 0.09))
            facadeBands.push(facePart(building, face, length * 0.43, bandY, 0.12, Math.min(building.h - 1.4, bandHeight), 0.21, 0.09))
          }
          if (building.type === 'house' || building.type === 'apartment') {
            drainPipes.push(facePart(building, face, -length * 0.48, Math.max(1.8, building.h * 0.42), 0.07, Math.max(2.8, building.h * 0.76), 0.34, 0.07))
          }
          for (let row = 0; row < rows; row += 1) {
            const y = building.type === 'house' ? 2.0 + row * 2.0 : 3.2 + row * ((building.h - 4.8) / Math.max(1, rows))
            if (y > building.h - 1.1) continue
            for (let col = 0; col < columns; col += 1) {
              if ((i + row * 3 + col + face.length) % 9 === 0 && building.type !== 'skyscraper') continue
              const along = ((col + 0.5) / columns - 0.5) * length * 0.58
              windows.push(facePart(building, face, along, y, panelWidth, panelHeight, 0.24))
              mullions.push(facePart(building, face, along, y, 0.055, panelHeight * 1.04, 0.305, 0.062))
              if (building.type !== 'skyscraper' || col % 2 === 0) {
                sills.push(facePart(building, face, along, y - panelHeight * 0.58, panelWidth + 0.28, 0.06, 0.315, 0.12))
                sills.push(facePart(building, face, along, y + panelHeight * 0.58, panelWidth + 0.18, 0.045, 0.305, 0.09))
              }
              if (
                (building.type === 'apartment' || building.type === 'office') &&
                row > 0 &&
                (i + row + col + face.charCodeAt(0)) % 7 === 0
              ) {
                acUnits.push(facePart(building, face, along + panelWidth * 0.32, y - panelHeight * 0.88, Math.min(0.74, panelWidth * 0.52), 0.34, 0.42, 0.36))
              }
            }
            if (building.type !== 'house' && row % 2 === 0) {
              trims.push(facePart(building, face, 0, y - panelHeight * 0.82, length * 0.72, 0.055, 0.19, 0.09))
            }
          }
          if (building.type === 'house') {
            trims.push(facePart(building, face, 0, 1.32, length * 0.58, 0.08, 0.2, 0.1))
          }
          if (building.type === 'apartment' && facePlan.balconyBias) {
            const maxFloors = facePlan.role === 'rear' ? 3 : 5
            const floors = Math.min(maxFloors, Math.max(2, Math.floor(building.h / 6.2)))
            const modules = balconyModules(length, facePlan.balconyPattern, facePlan.role)
            const floorStep = clamp((building.h - 4.5) / Math.max(2, floors), 3.4, 4.45)
            for (let floor = 1; floor <= floors; floor += 1) {
              const y = Math.min(building.h - 1.6, 3.05 + floor * floorStep)
              modules.forEach(module => {
                balconies.push(facePart(building, face, module.along, y, module.width, 0.12, 0.48, 0.74))
                rails.push(facePart(building, face, module.along, y + 0.3, module.width, 0.42, 0.9, 0.05))
                sideRails.push(facePart(building, face, module.along - module.width / 2, y + 0.28, 0.05, 0.38, 0.9, 0.05))
                sideRails.push(facePart(building, face, module.along + module.width / 2, y + 0.28, 0.05, 0.38, 0.9, 0.05))
              })
            }
          }
        }
        if (building.type === 'office' || building.type === 'apartment') {
          awnings.push(facePart(building, entryFace, 0, 3.2, Math.min(8.5, faceLength(building, entryFace) * 0.46), 0.18, 0.72, 1.05))
        }
        if (building.type === 'office' || building.type === 'skyscraper') {
          signs.push(facePart(building, entryFace, 0, Math.min(building.h - 3, 5.2 + (i % 3)), Math.min(9.2, faceLength(building, entryFace) * 0.52), 1.0, 0.22, 0.08))
        }
        if (building.type === 'house' && i % 3 === 0) {
          awnings.push(facePart(building, entryFace, 0, 2.5, Math.min(4.2, faceLength(building, entryFace) * 0.42), 0.14, 0.55, 0.75))
        }
      })
    return { windows, mullions, sills, facadeBands, acUnits, drainPipes, trims, balconies, rails, sideRails, awnings, signs }
  }, [buildings])

  useEffect(() => {
    exposeRenderingMetadata({
      facadeDetails: {
        physicalWindowPanes: details.windows.length,
        physicalMullions: details.mullions.length,
        windowSills: details.sills.length,
        facadeBands: details.facadeBands.length,
        acUnits: details.acUnits.length,
        drainPipes: details.drainPipes.length,
        balconyDecks: details.balconies.length,
        balconyFrontRails: details.rails.length,
        balconySideRails: details.sideRails.length,
        materialBreakup: 'mullions, sills, vertical bands, service pipes, AC boxes, balcony side returns',
      },
    })
  }, [details])

  useLayoutEffect(() => {
    if (!windowRef.current || !mullionRef.current || !sillRef.current || !facadeBandRef.current || !acRef.current || !drainPipeRef.current || !trimRef.current || !balconyRef.current || !railRef.current || !sideRailRef.current || !awningRef.current || !signRef.current) return
    const dummy = new THREE.Object3D()
    details.windows.forEach((item, i) => setLocalInstance(windowRef.current, i, dummy, item.building, item.local, item.scale))
    details.mullions.forEach((item, i) => setLocalInstance(mullionRef.current, i, dummy, item.building, item.local, item.scale))
    details.sills.forEach((item, i) => setLocalInstance(sillRef.current, i, dummy, item.building, item.local, item.scale))
    details.facadeBands.forEach((item, i) => setLocalInstance(facadeBandRef.current, i, dummy, item.building, item.local, item.scale))
    details.acUnits.forEach((item, i) => setLocalInstance(acRef.current, i, dummy, item.building, item.local, item.scale))
    details.drainPipes.forEach((item, i) => setLocalInstance(drainPipeRef.current, i, dummy, item.building, item.local, item.scale))
    details.trims.forEach((item, i) => setLocalInstance(trimRef.current, i, dummy, item.building, item.local, item.scale))
    details.balconies.forEach((item, i) => setLocalInstance(balconyRef.current, i, dummy, item.building, item.local, item.scale))
    details.rails.forEach((item, i) => setLocalInstance(railRef.current, i, dummy, item.building, item.local, item.scale))
    details.sideRails.forEach((item, i) => setLocalInstance(sideRailRef.current, i, dummy, item.building, item.local, item.scale))
    details.awnings.forEach((item, i) => setLocalInstance(awningRef.current, i, dummy, item.building, item.local, item.scale))
    details.signs.forEach((item, i) => setLocalInstance(signRef.current, i, dummy, item.building, item.local, item.scale))
    windowRef.current.instanceMatrix.needsUpdate = true
    mullionRef.current.instanceMatrix.needsUpdate = true
    sillRef.current.instanceMatrix.needsUpdate = true
    facadeBandRef.current.instanceMatrix.needsUpdate = true
    acRef.current.instanceMatrix.needsUpdate = true
    drainPipeRef.current.instanceMatrix.needsUpdate = true
    trimRef.current.instanceMatrix.needsUpdate = true
    balconyRef.current.instanceMatrix.needsUpdate = true
    railRef.current.instanceMatrix.needsUpdate = true
    sideRailRef.current.instanceMatrix.needsUpdate = true
    awningRef.current.instanceMatrix.needsUpdate = true
    signRef.current.instanceMatrix.needsUpdate = true
  }, [details])

  return (
    <>
      <instancedMesh ref={windowRef} args={[undefined, undefined, details.windows.length]} castShadow frustumCulled={false}>
        <boxGeometry args={[1, 1, 1]} />
        <meshStandardMaterial color="#bfefff" roughness={0.12} metalness={0.32} transparent opacity={0.76} emissive="#2a8bc2" emissiveIntensity={0.18} />
      </instancedMesh>
      <instancedMesh ref={mullionRef} args={[undefined, undefined, details.mullions.length]} castShadow frustumCulled={false}>
        <boxGeometry args={[1, 1, 1]} />
        <meshStandardMaterial color="#18232c" roughness={0.28} metalness={0.62} />
      </instancedMesh>
      <instancedMesh ref={sillRef} args={[undefined, undefined, details.sills.length]} castShadow receiveShadow frustumCulled={false}>
        <boxGeometry args={[1, 1, 1]} />
        <meshStandardMaterial color="#f0ece1" roughness={0.47} metalness={0.12} />
      </instancedMesh>
      <instancedMesh ref={facadeBandRef} args={[undefined, undefined, details.facadeBands.length]} castShadow frustumCulled={false}>
        <boxGeometry args={[1, 1, 1]} />
        <meshStandardMaterial color="#d0d7da" roughness={0.38} metalness={0.18} />
      </instancedMesh>
      <instancedMesh ref={acRef} args={[undefined, undefined, details.acUnits.length]} castShadow receiveShadow frustumCulled={false}>
        <boxGeometry args={[1, 1, 1]} />
        <meshStandardMaterial color="#c4ccd1" roughness={0.42} metalness={0.32} />
      </instancedMesh>
      <instancedMesh ref={drainPipeRef} args={[undefined, undefined, details.drainPipes.length]} castShadow frustumCulled={false}>
        <boxGeometry args={[1, 1, 1]} />
        <meshStandardMaterial color="#9ea7aa" roughness={0.34} metalness={0.54} />
      </instancedMesh>
      <instancedMesh ref={trimRef} args={[undefined, undefined, details.trims.length]} castShadow frustumCulled={false}>
        <boxGeometry args={[1, 1, 1]} />
        <meshStandardMaterial color="#e3ddd0" roughness={0.42} metalness={0.18} />
      </instancedMesh>
      <instancedMesh ref={balconyRef} args={[undefined, undefined, details.balconies.length]} castShadow receiveShadow frustumCulled={false}>
        <boxGeometry args={[1, 1, 1]} />
        <meshStandardMaterial color="#aab1b5" roughness={0.32} metalness={0.42} />
      </instancedMesh>
      <instancedMesh ref={railRef} args={[undefined, undefined, details.rails.length]} castShadow frustumCulled={false}>
        <boxGeometry args={[1, 1, 1]} />
        <meshStandardMaterial color="#e6ecef" roughness={0.26} metalness={0.64} />
      </instancedMesh>
      <instancedMesh ref={sideRailRef} args={[undefined, undefined, details.sideRails.length]} castShadow frustumCulled={false}>
        <boxGeometry args={[1, 1, 1]} />
        <meshStandardMaterial color="#d5dee2" roughness={0.28} metalness={0.62} />
      </instancedMesh>
      <instancedMesh ref={awningRef} args={[undefined, undefined, details.awnings.length]} castShadow frustumCulled={false}>
        <boxGeometry args={[1, 1, 1]} />
        <meshStandardMaterial color="#b54545" roughness={0.62} metalness={0.04} />
      </instancedMesh>
      <instancedMesh ref={signRef} args={[undefined, undefined, details.signs.length]} frustumCulled={false}>
        <boxGeometry args={[1, 1, 1]} />
        <meshStandardMaterial color="#b8f2ff" emissive="#40c8ff" emissiveIntensity={0.9} roughness={0.22} metalness={0.24} />
      </instancedMesh>
    </>
  )
}

function BuildingInteriorHints({ buildings }) {
  const doorRef = useRef()
  const lobbyRef = useRef()
  const coreRef = useRef()
  const canopyRef = useRef()
  const directoryRef = useRef()
  const coreSignRef = useRef()
  const deskRef = useRef()
  const queueRailRef = useRef()
  const doorStateRef = useRef([])
  const metadataFrameRef = useRef(0)
  const doorDummyRef = useRef(new THREE.Object3D())
  const details = useMemo(() => {
    const doors = []
    const lobbies = []
    const cores = []
    const canopies = []
    const directories = []
    const coreSigns = []
    const desks = []
    const queueRails = []
    const labels = []
    const doorBuildingIds = new Set()
    ;[...buildings]
      .filter(building => building.interior && Math.hypot(building.x, building.z) < CITY_GRID_HALF * 0.9)
      .sort((a, b) => Math.hypot(a.x, a.z) - Math.hypot(b.x, b.z))
      .forEach((building, index) => {
        const interior = building.interior
        const face = entryFaceForBuilding(building)
        const faceLen = faceLength(building, face)
        const normalSpan = face === 'north' || face === 'south' ? building.d : building.w
        const doorWidth = Math.min(interior.doorWidth || 2.4, faceLen * 0.62)
        const lobbyDepth = clamp(interior.lobbyDepth || normalSpan * 0.34, 1.8, normalSpan * 0.7)
        const lobbyWidth = clamp(interior.lobbyWidth || faceLen * 0.52, 2.4, faceLen * 0.74)
        const coreDepth = clamp(interior.coreOffset?.depth || lobbyDepth + 1.8, lobbyDepth + 0.9, normalSpan * 0.74)
        const coreAlong = clamp(interior.coreOffset?.along || 0, -faceLen * 0.28, faceLen * 0.28)
        const coreHeight = Math.max(2.4, Math.min(building.h - 0.7, building.type === 'house' ? 3.8 : building.type === 'apartment' ? 8.8 : 12.5))
        const coreWidth = building.type === 'house' ? 1.6 : building.type === 'apartment' ? 2.5 : 3.4
        const coreThickness = building.type === 'house' ? 1.35 : building.type === 'apartment' ? 2.5 : 3.6
        const panelWidth = Math.max(0.62, doorWidth / 2 - 0.1)
        const panelHeight = 3.25
        const panelY = 1.78
        const panelOutward = 0.28
        const panelThickness = 0.12
        const openSlide = clamp(doorWidth * 0.32, 0.9, 2.6)
        const triggerRadius = clamp(doorWidth * 0.48 + lobbyDepth * 0.22, 5.2, 9.5)
        const entryWorld = localToWorld(building, faceLocal(building, face, 0, 1.2, 1.8))
        const labelWorld = localToWorld(building, faceLocal(building, face, 0, 4.05, 1.05))
        const directoryAlong = -Math.min(faceLen * 0.22, Math.max(1.4, doorWidth * 0.7))
        const coreSignAlong = Math.min(faceLen * 0.22, Math.max(1.4, doorWidth * 0.7))
        const directoryWidth = clamp(doorWidth * 0.28 + 0.75, 1.15, 2.1)
        const coreSignWidth = clamp(doorWidth * 0.42 + 1.1, 1.8, 3.4)
        const coreLabel = coreLabelFor(interior)
        const floors = interior.floors || interior.floorCount || 1

        doorBuildingIds.add(building.id)
        ;[-1, 1].forEach(side => {
          const baseAlong = side * doorWidth * 0.25
          doors.push({
            ...facePart(building, face, baseAlong, panelY, panelWidth, panelHeight, panelOutward, panelThickness),
            id: building.id,
            face,
            baseAlong,
            panelY,
            panelOutward,
            side,
            openSlide,
            triggerRadius,
            entryWorld,
          })
        })
        lobbies.push(facePart(building, face, 0, 0.11, lobbyWidth, 0.07, -lobbyDepth / 2, lobbyDepth))
        cores.push(facePart(building, face, coreAlong, coreHeight / 2, coreWidth, coreHeight, -coreDepth, coreThickness))
        canopies.push(facePart(building, face, 0, 3.7, Math.min(faceLen * 0.68, doorWidth + 2.2), 0.22, 0.86, 1.05))
        directories.push(facePart(building, face, directoryAlong, 2.12, directoryWidth, 1.72, 0.58, 0.08))
        coreSigns.push(facePart(building, face, coreSignAlong, 2.62, coreSignWidth, 0.56, 0.6, 0.08))
        desks.push(facePart(building, face, 0, 0.62, clamp(lobbyWidth * 0.48, 2.6, 6.2), 1.04, -Math.max(1.55, lobbyDepth * 0.36), 1.08))
        ;[-1, 1].forEach(side => {
          queueRails.push(facePart(building, face, side * clamp(lobbyWidth * 0.23, 1.4, 3.6), 0.72, 0.08, 1.15, -Math.max(1.9, lobbyDepth * 0.48), clamp(lobbyDepth * 0.34, 1.8, 4.8)))
        })
        if (index < 96) {
          labels.push({
            id: building.id,
            name: buildingDirectoryName(building),
            coreLabel,
            floors,
            x: labelWorld.x,
            y: labelWorld.y,
            z: labelWorld.z,
          })
        }
      })
    return {
      doors,
      lobbies,
      cores,
      canopies,
      directories,
      coreSigns,
      desks,
      queueRails,
      labels,
      doorBuildingCount: doorBuildingIds.size,
    }
  }, [buildings])

  useEffect(() => {
    exposeRenderingMetadata({
      buildingAccess: {
        visibleDoors: details.doorBuildingCount,
        automaticDoorPanels: details.doors.length,
        automaticDoorBuildings: details.doorBuildingCount,
        automaticDoorRule: 'two sliding glass panels open near the player and close after the doorway clears',
        visibleLobbies: details.lobbies.length,
        visibleVerticalCores: details.cores.length,
        visibleDirectoryBoards: details.directories.length,
        visibleCoreWayfindingSigns: details.coreSigns.length,
        visibleConciergeDesks: details.desks.length,
        visibleQueueRails: details.queueRails.length,
        readableDirectoryLabels: details.labels.length,
        interiorVisualRule: 'lobbies include floor directories, core wayfinding signs, desks, and queue rails',
        doorRule: 'procedural buildings expose one street-facing solid entry portal',
        verticalTravel: 'PageUp/PageDown changes floors while indoors',
      },
    })
  }, [details])

  useLayoutEffect(() => {
    if (
      !doorRef.current ||
      !lobbyRef.current ||
      !coreRef.current ||
      !canopyRef.current ||
      !directoryRef.current ||
      !coreSignRef.current ||
      !deskRef.current ||
      !queueRailRef.current
    ) return
    const dummy = new THREE.Object3D()
    details.doors.forEach((item, i) => setLocalInstance(doorRef.current, i, dummy, item.building, item.local, item.scale))
    details.lobbies.forEach((item, i) => setLocalInstance(lobbyRef.current, i, dummy, item.building, item.local, item.scale))
    details.cores.forEach((item, i) => setLocalInstance(coreRef.current, i, dummy, item.building, item.local, item.scale))
    details.canopies.forEach((item, i) => setLocalInstance(canopyRef.current, i, dummy, item.building, item.local, item.scale))
    details.directories.forEach((item, i) => setLocalInstance(directoryRef.current, i, dummy, item.building, item.local, item.scale))
    details.coreSigns.forEach((item, i) => setLocalInstance(coreSignRef.current, i, dummy, item.building, item.local, item.scale))
    details.desks.forEach((item, i) => setLocalInstance(deskRef.current, i, dummy, item.building, item.local, item.scale))
    details.queueRails.forEach((item, i) => setLocalInstance(queueRailRef.current, i, dummy, item.building, item.local, item.scale))
    doorRef.current.instanceMatrix.needsUpdate = true
    lobbyRef.current.instanceMatrix.needsUpdate = true
    coreRef.current.instanceMatrix.needsUpdate = true
    canopyRef.current.instanceMatrix.needsUpdate = true
    directoryRef.current.instanceMatrix.needsUpdate = true
    coreSignRef.current.instanceMatrix.needsUpdate = true
    deskRef.current.instanceMatrix.needsUpdate = true
    queueRailRef.current.instanceMatrix.needsUpdate = true
  }, [details])

  useFrame((_, delta) => {
    if (!doorRef.current || !details.doors.length) return
    const storePlayer = useCityStore.getState().player
    const doorProbe = typeof window !== 'undefined' ? window.__REALCITY_AUTODOOR_PROBE__ : null
    const player = doorProbe || storePlayer
    const dummy = doorDummyRef.current
    if (doorStateRef.current.length !== details.doors.length) {
      doorStateRef.current = details.doors.map(() => 0)
    }

    let openPanels = 0
    let nearestDoorDistance = Infinity
    let nearestDoorId = null
    const openDoorIds = new Set()
    const dt = Math.min(delta, 0.05)

    details.doors.forEach((item, index) => {
      const distance = Math.hypot(player.x - item.entryWorld.x, player.z - item.entryWorld.z)
      if (distance < nearestDoorDistance) {
        nearestDoorDistance = distance
        nearestDoorId = item.id
      }
      const radius = Number.isFinite(item.triggerRadius) ? item.triggerRadius : 6
      const target = distance <= radius || (player.indoors && player.placeId === item.id) ? 1 : 0
      const open = doorProbe ? target : THREE.MathUtils.damp(doorStateRef.current[index] || 0, target, 8.5, dt)
      doorStateRef.current[index] = open
      if (open > 0.35) {
        openPanels += 1
        openDoorIds.add(item.id)
      }
      const local = faceLocal(item.building, item.face, item.baseAlong + item.side * item.openSlide * open, item.panelY, item.panelOutward)
      setLocalInstance(doorRef.current, index, dummy, item.building, local, item.scale)
    })
    doorRef.current.instanceMatrix.needsUpdate = true

    metadataFrameRef.current += 1
    if (doorProbe || metadataFrameRef.current % 12 === 0) {
      exposeRenderingMetadata({
        buildingAccess: {
          ...(typeof window !== 'undefined' ? window.__REALCITY_RENDERING__?.buildingAccess || {} : {}),
          automaticDoorPanels: details.doors.length,
          automaticDoorBuildings: details.doorBuildingCount,
          automaticDoorRule: 'two sliding glass panels open near the player and close after the doorway clears',
          visibleDirectoryBoards: details.directories.length,
          visibleCoreWayfindingSigns: details.coreSigns.length,
          visibleConciergeDesks: details.desks.length,
          visibleQueueRails: details.queueRails.length,
          readableDirectoryLabels: details.labels.length,
          interiorVisualRule: 'lobbies include floor directories, core wayfinding signs, desks, and queue rails',
          openDoorPanels: openPanels,
          openDoorBuildings: openDoorIds.size,
          openDoorIds: [...openDoorIds],
          autoDoorProbeActive: !!doorProbe,
          nearestAutomaticDoorId: nearestDoorId,
          nearestAutomaticDoorDistance: Number(nearestDoorDistance.toFixed(2)),
        },
      })
    }
  })

  return (
    <>
      <instancedMesh ref={doorRef} args={[undefined, undefined, details.doors.length]} frustumCulled={false}>
        <boxGeometry args={[1, 1, 1]} />
        <meshStandardMaterial color="#b9edff" roughness={0.1} metalness={0.28} transparent opacity={0.64} emissive="#4ab9f0" emissiveIntensity={0.18} />
      </instancedMesh>
      <instancedMesh ref={lobbyRef} args={[undefined, undefined, details.lobbies.length]} receiveShadow frustumCulled={false}>
        <boxGeometry args={[1, 1, 1]} />
        <meshStandardMaterial color="#d8dce0" roughness={0.34} metalness={0.06} emissive="#1f2933" emissiveIntensity={0.08} />
      </instancedMesh>
      <instancedMesh ref={coreRef} args={[undefined, undefined, details.cores.length]} castShadow frustumCulled={false}>
        <boxGeometry args={[1, 1, 1]} />
        <meshStandardMaterial color="#46515a" roughness={0.38} metalness={0.34} emissive="#111820" emissiveIntensity={0.08} />
      </instancedMesh>
      <instancedMesh ref={canopyRef} args={[undefined, undefined, details.canopies.length]} castShadow frustumCulled={false}>
        <boxGeometry args={[1, 1, 1]} />
        <meshStandardMaterial color="#24313a" roughness={0.36} metalness={0.42} emissive="#10202b" emissiveIntensity={0.16} />
      </instancedMesh>
      <instancedMesh ref={directoryRef} args={[undefined, undefined, details.directories.length]} castShadow frustumCulled={false}>
        <boxGeometry args={[1, 1, 1]} />
        <meshStandardMaterial color="#10202b" roughness={0.28} metalness={0.34} emissive="#2dd4bf" emissiveIntensity={0.32} />
      </instancedMesh>
      <instancedMesh ref={coreSignRef} args={[undefined, undefined, details.coreSigns.length]} frustumCulled={false}>
        <boxGeometry args={[1, 1, 1]} />
        <meshStandardMaterial color="#0f1720" roughness={0.24} metalness={0.36} emissive="#ffd447" emissiveIntensity={0.52} />
      </instancedMesh>
      <instancedMesh ref={deskRef} args={[undefined, undefined, details.desks.length]} castShadow receiveShadow frustumCulled={false}>
        <boxGeometry args={[1, 1, 1]} />
        <meshStandardMaterial color="#6b7280" roughness={0.5} metalness={0.16} />
      </instancedMesh>
      <instancedMesh ref={queueRailRef} args={[undefined, undefined, details.queueRails.length]} castShadow frustumCulled={false}>
        <boxGeometry args={[1, 1, 1]} />
        <meshStandardMaterial color="#c8d4d8" roughness={0.26} metalness={0.62} />
      </instancedMesh>
      {details.labels.map(label => (
        <Billboard key={`directory-${label.id}`} position={[label.x, label.y, label.z]}>
          <mesh position={[0, 0, -0.01]}>
            <planeGeometry args={[2.35, 0.58]} />
            <meshBasicMaterial color="#07111c" transparent opacity={0.74} depthWrite={false} />
          </mesh>
          <Text
            position={[0, 0.12, 0]}
            fontSize={0.1}
            maxWidth={2.1}
            textAlign="center"
            color="#f8fbff"
            outlineWidth={0.008}
            outlineColor="#07111c"
          >
            {label.name}
          </Text>
          <Text
            position={[0, -0.1, 0]}
            fontSize={0.078}
            maxWidth={2.1}
            textAlign="center"
            color="#b8f2ff"
            outlineWidth={0.007}
            outlineColor="#07111c"
          >
            {`${label.coreLabel} / ${label.floors}F`}
          </Text>
        </Billboard>
      ))}
    </>
  )
}

function RooftopDetails({ buildings }) {
  const hvacRef = useRef()
  const antennaRef = useRef()
  const waterRef = useRef()
  const details = useMemo(() => {
    return buildings
      .filter(building => building.h > 18 && Math.hypot(building.x, building.z) < CITY_GRID_HALF * 0.9)
      .slice(0, 220)
      .map((building, i) => ({
        x: building.x,
        z: building.z,
        y: building.y + building.h,
        yaw: building.rot,
        hvac: [Math.max(1.8, building.w * 0.16), 0.7 + (i % 3) * 0.16, Math.max(1.5, building.d * 0.12)],
        water: building.type === 'apartment' || building.type === 'office',
        antenna: building.type === 'skyscraper',
      }))
  }, [buildings])

  const antennas = useMemo(() => details.filter(item => item.antenna), [details])
  const tanks = useMemo(() => details.filter(item => item.water), [details])

  useLayoutEffect(() => {
    if (!hvacRef.current || !antennaRef.current || !waterRef.current) return
    const dummy = new THREE.Object3D()
    details.forEach((detail, i) => {
      setInstance(hvacRef.current, i, dummy, [detail.x + Math.sin(detail.yaw) * 2.2, detail.y + 0.44, detail.z + Math.cos(detail.yaw) * 2.2], detail.hvac, detail.yaw)
    })
    antennas.forEach((detail, i) => {
      setInstance(antennaRef.current, i, dummy, [detail.x, detail.y + 3.8, detail.z], [0.06, 7.6, 0.06])
    })
    tanks.forEach((detail, i) => {
      setInstance(waterRef.current, i, dummy, [detail.x - Math.sin(detail.yaw) * 2.6, detail.y + 0.74, detail.z - Math.cos(detail.yaw) * 2.6], [0.85, 1.48, 0.85])
    })
    hvacRef.current.instanceMatrix.needsUpdate = true
    antennaRef.current.instanceMatrix.needsUpdate = true
    waterRef.current.instanceMatrix.needsUpdate = true
  }, [details, antennas, tanks])

  return (
    <>
      <instancedMesh ref={hvacRef} args={[undefined, undefined, details.length]} castShadow frustumCulled={false}>
        <boxGeometry args={[1, 1, 1]} />
        <meshStandardMaterial color="#515b60" roughness={0.48} metalness={0.38} />
      </instancedMesh>
      <instancedMesh ref={antennaRef} args={[undefined, undefined, antennas.length]} castShadow frustumCulled={false}>
        <cylinderGeometry args={[1, 1, 1, 6]} />
        <meshStandardMaterial color="#d4d9da" roughness={0.28} metalness={0.62} />
      </instancedMesh>
      <instancedMesh ref={waterRef} args={[undefined, undefined, tanks.length]} castShadow frustumCulled={false}>
        <cylinderGeometry args={[1, 1, 1, 12]} />
        <meshStandardMaterial color="#8ea0a7" roughness={0.42} metalness={0.34} />
      </instancedMesh>
    </>
  )
}

export default function UrbanDetails({ city }) {
  return (
    <>
      <Crosswalks roads={city.roads} />
      <StreetLights roads={city.roads} />
      <TrafficSignals roads={city.roads} mobilitySystem={city.mobilitySystem} />
      <PedestrianSignals roads={city.roads} mobilitySystem={city.mobilitySystem} />
      <LaneReflectors roads={city.roads} />
      <RoadNameSigns roads={city.roads} />
      <TransitAndTaxiStops roads={city.roads} />
      <SharedMobilityDocks roads={city.roads} mobilitySystem={city.mobilitySystem} />
      <Bollards roads={city.roads} />
      <StreetFurniture roads={city.roads} />
      <ParkedCars roads={city.roads} />
      <PlantersAndBenches roads={city.roads} />
      <FacadeDetails buildings={city.buildings} />
      <BuildingInteriorHints buildings={city.buildings} />
      <RooftopDetails buildings={city.buildings} />
    </>
  )
}
