import { useEffect, useMemo, useRef } from 'react'
import { useFrame } from '@react-three/fiber'
import * as THREE from 'three'
import { terrainHeight } from '../engine/cityEngine'
import { currentInterior, resolveBuildingCollision } from '../engine/collision'
import { useCityStore } from '../engine/cityStore'
import { sampleRoute, taxiPassengerDoorPoint } from '../engine/taxiRouting'
import { makeProceduralTexture } from './proceduralTextures'

const WALK_SPEED = 6.2
const RUN_SPEED = 12.5
const GRAVITY = 23
const JUMP = 8.6
const CAMERA_DISTANCE = 10.5
const CAMERA_HEIGHT = 2.35
const CAMERA_BASE_ELEVATION = 0.12
const TURN_SPEED = 2.35
const FREE_LOOK_YAW = 1.18
const FREE_LOOK_PITCH_UP = 0.72
const FREE_LOOK_PITCH_DOWN = -0.22
const FREE_LOOK_IN_SPEED = 8.5
const FREE_LOOK_RETURN_SPEED = 16.5
const FLOOR_CHANGE_COOLDOWN = 0.42

// --- drive mode (press F near the parked player car to get in / out) ---
const DRIVE_ACCEL = 13          // m/s^2 forward push
const DRIVE_BRAKE = 24          // m/s^2 braking / reverse push
const DRIVE_DRAG = 0.9          // coast decay per second when off the throttle
const DRIVE_MAX_SPEED = 20      // ~72 km/h
const DRIVE_MAX_REVERSE = 6
const DRIVE_STEER_RATE = 1.7    // rad/s of yaw at full steer + reference speed
const DRIVE_STEER_REF = 7       // speed (m/s) at which steering reaches full authority
const DRIVE_CAMERA_DISTANCE = 15
const DRIVE_CAMERA_HEIGHT = 3.4
const CAR_ENTER_RADIUS = 3.9    // how close the player must be to board
const CAR_BODY_RADIUS = 1.5     // collision radius used while driving
const PLAYER_CAR_TEAL = '#12a594'

// 0 = full day, 1 = full night — used to light the car's lamps after dusk
function nightFactor(minutes) {
  const h = (Number(minutes) || 0) / 60
  if (h >= 6.5 && h <= 18) return 0
  if (h > 18 && h < 20) return (h - 18) / 2
  if (h >= 20 || h < 5) return 1
  if (h >= 5 && h < 6.5) return 1 - (h - 5) / 1.5
  return 0
}

function approach(current, target, speed, delta) {
  return current + (target - current) * (1 - Math.exp(-speed * delta))
}

function smoothstep(t) {
  return t * t * (3 - 2 * t)
}

function finiteNumber(value, fallback = 0) {
  const number = Number(value)
  return Number.isFinite(number) ? number : fallback
}

function finitePoint2(point) {
  return Number.isFinite(Number(point?.x)) && Number.isFinite(Number(point?.z))
}

function safePoint2(point, fallback = { x: 0, z: 40 }) {
  return {
    x: Number.isFinite(Number(point?.x)) ? Number(point.x) : fallback.x,
    z: Number.isFinite(Number(point?.z)) ? Number(point.z) : fallback.z,
  }
}

function finiteVector3(vector) {
  return Number.isFinite(vector?.x) && Number.isFinite(vector?.y) && Number.isFinite(vector?.z)
}

function finiteRoute(points = []) {
  return points.filter(finitePoint2)
}

function localPoint(item, x, z) {
  const dx = x - item.x
  const dz = z - item.z
  const cos = Math.cos(item.rot || 0)
  const sin = Math.sin(item.rot || 0)
  return {
    x: dx * cos - dz * sin,
    z: dx * sin + dz * cos,
  }
}

function cameraSolidHit(city, x, z, radius = 1.25) {
  const colliders = city.getNearbyBuildings?.(x, z) || city.buildings || []
  for (const building of colliders) {
    if (building.h < 3) continue
    const local = localPoint(building, x, z)
    if (Math.abs(local.x) < building.w / 2 + radius && Math.abs(local.z) < building.d / 2 + radius) return true
  }

  for (const place of city.landmarks || []) {
    const interior = place.interior
    if (!interior?.solidWalls) continue
    const local = localPoint(place, x, z)
    if (Math.abs(local.x) < interior.width / 2 + radius && Math.abs(local.z) < interior.depth / 2 + radius) return true
  }
  return false
}

function resolveCameraTarget(city, focus, target, radius = 1.35) {
  let targetX = target.x
  let targetZ = target.z
  let avoidedLineOfSight = false
  const dx = target.x - focus.x
  const dz = target.z - focus.z
  let previous = { x: focus.x, z: focus.z }

  for (let step = 1; step <= 14; step += 1) {
    const t = step / 14
    const probe = { x: focus.x + dx * t, z: focus.z + dz * t }
    if (cameraSolidHit(city, probe.x, probe.z, radius)) {
      targetX = previous.x
      targetZ = previous.z
      avoidedLineOfSight = true
      break
    }
    previous = probe
  }

  let [safeX, safeZ] = resolveBuildingCollision(city, focus.x, focus.z, targetX, targetZ, radius)
  const targetDistance = Math.hypot(dx, dz)
  if (Math.hypot(safeX - focus.x, safeZ - focus.z) < 4.2 && targetDistance > 0.001) {
    const scale = Math.min(1, 4.2 / targetDistance)
    ;[safeX, safeZ] = resolveBuildingCollision(city, focus.x, focus.z, focus.x + dx * scale, focus.z + dz * scale, radius)
  }
  const avoided = Math.hypot(safeX - target.x, safeZ - target.z) > 0.08
  if (!avoided && !avoidedLineOfSight) return { x: target.x, y: target.y, z: target.z, avoided: false }
  return {
    x: safeX,
    y: Math.max(target.y, terrainHeight(safeX, safeZ) + 3.2),
    z: safeZ,
    avoided: true,
  }
}

function isTypingTarget(target) {
  return !!target?.closest?.('input, textarea, select, button')
}

function useKeys() {
  const keys = useRef({})

  useEffect(() => {
    const down = (event) => {
      if (isTypingTarget(event.target)) return
      keys.current[event.code] = true
      if (['Space', 'ArrowUp', 'ArrowDown', 'ArrowLeft', 'ArrowRight', 'PageUp', 'PageDown'].includes(event.code)) event.preventDefault()
    }
    const up = (event) => {
      keys.current[event.code] = false
    }
    const clear = () => {
      keys.current = {}
    }
    window.addEventListener('keydown', down, { passive: false })
    window.addEventListener('keyup', up)
    window.addEventListener('blur', clear)
    return () => {
      window.removeEventListener('keydown', down)
      window.removeEventListener('keyup', up)
      window.removeEventListener('blur', clear)
    }
  }, [])

  return keys
}

function vehicleLocal(sample, x, z) {
  const dx = x - sample.x
  const dz = z - sample.z
  const cos = Math.cos(sample.yaw || 0)
  const sin = Math.sin(sample.yaw || 0)
  return {
    x: dx * cos - dz * sin,
    z: dx * sin + dz * cos,
  }
}

function vehicleWorld(sample, localX, localZ) {
  const cos = Math.cos(sample.yaw || 0)
  const sin = Math.sin(sample.yaw || 0)
  return {
    x: sample.x + localX * cos + localZ * sin,
    z: sample.z - localX * sin + localZ * cos,
  }
}

function resolveCircleCollision(px, pz, sample, radius) {
  const dx = px - sample.x
  const dz = pz - sample.z
  const distance = Math.hypot(dx, dz)
  if (distance >= radius) return null
  const nx = distance > 0.001 ? dx / distance : 1
  const nz = distance > 0.001 ? dz / distance : 0
  return {
    x: sample.x + nx * radius,
    z: sample.z + nz * radius,
    penetration: radius - distance,
    nx,
    nz,
  }
}

function resolveVehicleCollision(px, pz, sample, playerRadius, padding) {
  const local = vehicleLocal(sample, px, pz)
  const halfW = (sample.width || 2.1) / 2 + playerRadius + padding * 0.42
  const halfL = (sample.length || 4.4) / 2 + playerRadius + padding * 0.34
  if (Math.abs(local.x) >= halfW || Math.abs(local.z) >= halfL) return null

  const pushX = halfW - Math.abs(local.x)
  const pushZ = halfL - Math.abs(local.z)
  const safeLocal = { ...local }
  if (pushX < pushZ) safeLocal.x = Math.sign(local.x || 1) * halfW
  else safeLocal.z = Math.sign(local.z || 1) * halfL
  const safe = vehicleWorld(sample, safeLocal.x, safeLocal.z)
  return {
    ...safe,
    penetration: Math.min(pushX, pushZ),
    nx: safe.x - px,
    nz: safe.z - pz,
  }
}

function emitCollisionOnce(cooldowns, key, cooldownMs, callback) {
  const now = performance.now()
  const last = cooldowns.get(key) || 0
  if (now - last < cooldownMs) return
  cooldowns.set(key, now)
  callback()
}

function indoorFloorInfo(place, floorIndex = 0) {
  if (!place) return null
  const directory = Array.isArray(place.floorDirectory) ? place.floorDirectory : []
  const entry = directory[Math.max(0, Math.min(directory.length - 1, floorIndex))]
  const level = floorIndex + 1
  const core = place.verticalCore === 'elevator'
    ? 'Elevator bank'
    : place.verticalCore === 'escalator'
      ? 'Escalator hall'
      : 'Stair core'
  return entry || {
    level,
    label: level === 1 ? 'Ground lobby' : `Floor ${level}`,
    zone: level === 1 ? 'lobby and entry hall' : 'upper floor rooms',
    access: place.publicAccess || 'building access',
    core,
    guide: `${core} connects to ${place.floorCount || 1} floors.`,
  }
}

function resolveDynamicCollision(store, previousX, previousZ, x, z, isRunning, cooldowns) {
  let px = x
  let pz = z
  const rules = store.collisionRules || {}
  const playerRadius = rules.playerRadius || 0.72
  const pedestrianRadius = playerRadius + (rules.pedestrianRadius || 0.82)
  const vehiclePadding = rules.vehiclePadding || 0.78
  const movement = Math.hypot(x - previousX, z - previousZ)

  for (const pedestrian of store.pedestrianSamples || []) {
    if (!pedestrian?.id) continue
    const radius = playerRadius + (pedestrian.radius || 0.82)
    const result = resolveCircleCollision(px, pz, pedestrian, Math.max(radius, pedestrianRadius))
    if (!result) continue
    px = result.x
    pz = result.z
    const impulse = Math.min(1.6, (isRunning ? 1.05 : 0.58) + movement * 5 + result.penetration * 0.7)
    emitCollisionOnce(cooldowns, `npc:${pedestrian.id}`, 520, () => {
      store.registerPlayerImpact?.({
        kind: 'pedestrian',
        sourceId: pedestrian.id,
        sourceName: pedestrian.name,
        intensity: impulse,
        x: px,
        z: pz,
        nx: result.nx,
        nz: result.nz,
        text: `${pedestrian.name || 'A pedestrian'} is pushed back as you collide on the sidewalk.`,
      })
      window.dispatchEvent(new CustomEvent('realcity:player-hit-npc', {
        detail: {
          id: pedestrian.id,
          playerX: previousX,
          playerZ: previousZ,
          x: px,
          z: pz,
          impulse,
        },
      }))
    })
  }

  const missionTaxi = store.mission?.taxi?.pose && !store.ride
    ? [{
        id: store.mission.taxi.id || 'mission-taxi',
        kind: 'taxi',
        x: store.mission.taxi.pose.x,
        z: store.mission.taxi.pose.z,
        yaw: store.mission.taxi.pose.heading ?? store.mission.taxi.pose.yaw ?? 0,
        width: 2.22,
        length: 4.75,
      }]
    : []

  const vehicles = [...(store.vehicleSamples || []), ...missionTaxi].filter(vehicle => vehicle?.id)
  for (let pass = 0; pass < 3; pass += 1) {
    let hadVehicleContact = false
    for (const vehicle of vehicles) {
      const result = resolveVehicleCollision(px, pz, vehicle, playerRadius, vehiclePadding)
      if (!result) continue
      hadVehicleContact = true
      px = result.x
      pz = result.z
      emitCollisionOnce(cooldowns, `vehicle:${vehicle.id}`, 900, () => {
        const intensity = Math.min(1.8, 0.72 + result.penetration * 0.44 + movement * 6 + (vehicle.speed || 0) * 0.025)
        store.registerPlayerImpact?.({
          kind: 'vehicle',
          sourceId: vehicle.id,
          sourceName: vehicle.driverName || (vehicle.kind === 'taxi' ? 'taxi driver' : 'driver'),
          intensity,
          x: px,
          z: pz,
          nx: result.nx,
          nz: result.nz,
          text: `${vehicle.kind === 'taxi' ? 'The taxi' : 'The car'} brakes and pushes you clear of its solid body.`,
        })
      })
    }
    if (!hadVehicleContact) break
  }

  for (let pass = 0; pass < 2; pass += 1) {
    let adjusted = false
    for (const vehicle of vehicles) {
      const clearance = Math.min(vehicle.width || 2.1, vehicle.length || 4.4) / 2 + playerRadius + vehiclePadding
      const dx = px - vehicle.x
      const dz = pz - vehicle.z
      const distance = Math.hypot(dx, dz)
      if (distance >= clearance) continue
      const fallbackYaw = Number.isFinite(vehicle.yaw) ? vehicle.yaw + Math.PI / 2 : 0
      const nx = distance > 0.001 ? dx / distance : Math.sin(fallbackYaw)
      const nz = distance > 0.001 ? dz / distance : Math.cos(fallbackYaw)
      px = vehicle.x + nx * clearance
      pz = vehicle.z + nz * clearance
      adjusted = true
    }
    if (!adjusted) break
  }

  return [px, pz]
}

function Character({ moving, running }) {
  const leftLeg = useRef()
  const rightLeg = useRef()
  const leftArm = useRef()
  const rightArm = useRef()
  const leftLid = useRef()
  const rightLid = useRef()
  const phase = useRef(0)
  const faceClock = useRef(0)
  const textures = useMemo(() => ({
    fabric: makeProceduralTexture('city-fabric', { size: 128, seed: 31, repeatX: 2, repeatY: 2 }),
    skin: makeProceduralTexture('skin-pores', { size: 128, seed: 32, repeatX: 1.5, repeatY: 1.5 }),
    hair: makeProceduralTexture('hair-strands', { size: 128, seed: 33, repeatX: 2.4, repeatY: 1.2 }),
    rubber: makeProceduralTexture('rubber-tread', { size: 128, seed: 34, repeatX: 2, repeatY: 2 }),
    glass: makeProceduralTexture('glass-smudge', { size: 128, seed: 35, repeatX: 1.2, repeatY: 1.2 }),
  }), [])

  useFrame((_, delta) => {
    const rate = moving.current ? (running.current ? 10 : 6.5) : 0
    phase.current += delta * rate
    faceClock.current += delta
    const swing = Math.sin(phase.current) * (moving.current ? 0.52 : 0.05)
    if (leftLeg.current) leftLeg.current.rotation.x = swing
    if (rightLeg.current) rightLeg.current.rotation.x = -swing
    if (leftArm.current) leftArm.current.rotation.x = -swing * 0.55
    if (rightArm.current) rightArm.current.rotation.x = swing * 0.55
    const blinkWindow = 0.16
    const blinkPeriod = 3.85
    const blinkPhase = faceClock.current % blinkPeriod
    const blink = blinkPhase > blinkPeriod - blinkWindow
      ? Math.sin(((blinkPhase - (blinkPeriod - blinkWindow)) / blinkWindow) * Math.PI)
      : 0
    if (leftLid.current) leftLid.current.scale.y = Math.max(0.001, blink)
    if (rightLid.current) rightLid.current.scale.y = Math.max(0.001, blink)
  })

  return (
    <group position={[0, -0.9, 0]}>
      <mesh castShadow position={[0, 0.78, 0]}>
        <boxGeometry args={[0.38, 0.2, 0.25]} />
        <meshStandardMaterial map={textures.fabric} color="#1c2541" roughness={0.8} />
      </mesh>
      <mesh castShadow position={[0, 1.2, 0]}>
        <capsuleGeometry args={[0.21, 0.52, 4, 10]} />
        <meshStandardMaterial map={textures.fabric} color="#2f6f9f" roughness={0.72} />
      </mesh>
      <mesh castShadow position={[0, 1.27, 0.18]}>
        <boxGeometry args={[0.28, 0.34, 0.035]} />
        <meshStandardMaterial map={textures.glass} color="#e8f1f4" roughness={0.58} metalness={0.02} />
      </mesh>
      <mesh castShadow position={[0, 1.5, 0.205]}>
        <boxGeometry args={[0.18, 0.035, 0.018]} />
        <meshStandardMaterial map={textures.fabric} color="#f2eadc" roughness={0.7} />
      </mesh>
      <mesh castShadow position={[-0.08, 1.31, 0.212]} rotation={[0, 0, -0.18]}>
        <boxGeometry args={[0.04, 0.23, 0.016]} />
        <meshStandardMaterial map={textures.fabric} color="#d5e3ed" roughness={0.72} />
      </mesh>
      <mesh castShadow position={[0.08, 1.31, 0.212]} rotation={[0, 0, 0.18]}>
        <boxGeometry args={[0.04, 0.23, 0.016]} />
        <meshStandardMaterial map={textures.fabric} color="#d5e3ed" roughness={0.72} />
      </mesh>
      <mesh castShadow position={[0.12, 1.38, 0.224]}>
        <boxGeometry args={[0.035, 0.048, 0.012]} />
        <meshStandardMaterial color="#c59b53" roughness={0.32} metalness={0.35} />
      </mesh>
      <mesh castShadow position={[0, 1.57, 0]}>
        <capsuleGeometry args={[0.075, 0.12, 4, 8]} />
        <meshStandardMaterial map={textures.skin} color="#d9a47f" roughness={0.66} />
      </mesh>
      <group ref={leftLeg} position={[-0.12, 0.74, 0]}>
        <mesh castShadow position={[0, -0.34, 0]}>
          <capsuleGeometry args={[0.065, 0.52, 4, 8]} />
          <meshStandardMaterial map={textures.fabric} color="#17203a" roughness={0.84} />
        </mesh>
        <mesh castShadow position={[0, -0.58, 0.045]}>
          <boxGeometry args={[0.08, 0.03, 0.08]} />
          <meshStandardMaterial map={textures.fabric} color="#0d1118" roughness={0.86} />
        </mesh>
        <mesh castShadow position={[0, -0.67, 0.045]}>
          <boxGeometry args={[0.11, 0.06, 0.18]} />
          <meshStandardMaterial map={textures.rubber} color="#0d1118" roughness={0.85} />
        </mesh>
      </group>
      <group ref={rightLeg} position={[0.12, 0.74, 0]}>
        <mesh castShadow position={[0, -0.34, 0]}>
          <capsuleGeometry args={[0.065, 0.52, 4, 8]} />
          <meshStandardMaterial map={textures.fabric} color="#17203a" roughness={0.84} />
        </mesh>
        <mesh castShadow position={[0, -0.58, 0.045]}>
          <boxGeometry args={[0.08, 0.03, 0.08]} />
          <meshStandardMaterial map={textures.fabric} color="#0d1118" roughness={0.86} />
        </mesh>
        <mesh castShadow position={[0, -0.67, 0.045]}>
          <boxGeometry args={[0.11, 0.06, 0.18]} />
          <meshStandardMaterial map={textures.rubber} color="#0d1118" roughness={0.85} />
        </mesh>
      </group>
      <group ref={leftArm} position={[-0.28, 1.34, 0]}>
        <mesh castShadow position={[0, -0.26, 0]}>
          <capsuleGeometry args={[0.055, 0.42, 4, 8]} />
          <meshStandardMaterial map={textures.skin} color="#d9a47f" roughness={0.68} />
        </mesh>
        <mesh castShadow position={[0, -0.51, 0.015]}>
          <sphereGeometry args={[0.065, 10, 8]} />
          <meshStandardMaterial map={textures.skin} color="#d9a47f" roughness={0.68} />
        </mesh>
      </group>
      <group ref={rightArm} position={[0.28, 1.34, 0]}>
        <mesh castShadow position={[0, -0.26, 0]}>
          <capsuleGeometry args={[0.055, 0.42, 4, 8]} />
          <meshStandardMaterial map={textures.skin} color="#d9a47f" roughness={0.68} />
        </mesh>
        <mesh castShadow position={[0, -0.51, 0.015]}>
          <sphereGeometry args={[0.065, 10, 8]} />
          <meshStandardMaterial map={textures.skin} color="#d9a47f" roughness={0.68} />
        </mesh>
      </group>
      <mesh castShadow position={[0, 1.72, 0]}>
        <sphereGeometry args={[0.205, 18, 14]} />
        <meshStandardMaterial map={textures.skin} color="#efc29a" roughness={0.64} />
      </mesh>
      <mesh castShadow position={[-0.088, 1.745, 0.188]}>
        <sphereGeometry args={[0.03, 10, 8]} />
        <meshStandardMaterial color="#f7f3ea" roughness={0.44} />
      </mesh>
      <mesh castShadow position={[0.088, 1.745, 0.188]}>
        <sphereGeometry args={[0.03, 10, 8]} />
        <meshStandardMaterial color="#f7f3ea" roughness={0.44} />
      </mesh>
      <mesh castShadow position={[-0.088, 1.744, 0.208]}>
        <sphereGeometry args={[0.011, 8, 6]} />
        <meshStandardMaterial color="#05070a" roughness={0.32} />
      </mesh>
      <mesh castShadow position={[0.088, 1.744, 0.208]}>
        <sphereGeometry args={[0.011, 8, 6]} />
        <meshStandardMaterial color="#05070a" roughness={0.32} />
      </mesh>
      <mesh ref={leftLid} castShadow position={[-0.088, 1.748, 0.21]} scale={[1, 0.001, 1]}>
        <boxGeometry args={[0.058, 0.038, 0.015]} />
        <meshStandardMaterial map={textures.skin} color="#efc29a" roughness={0.7} />
      </mesh>
      <mesh ref={rightLid} castShadow position={[0.088, 1.748, 0.21]} scale={[1, 0.001, 1]}>
        <boxGeometry args={[0.058, 0.038, 0.015]} />
        <meshStandardMaterial map={textures.skin} color="#efc29a" roughness={0.7} />
      </mesh>
      <mesh castShadow position={[-0.088, 1.785, 0.202]} rotation={[0, 0, -0.08]}>
        <boxGeometry args={[0.06, 0.01, 0.012]} />
        <meshStandardMaterial map={textures.hair} color="#17100b" roughness={0.9} />
      </mesh>
      <mesh castShadow position={[0.088, 1.785, 0.202]} rotation={[0, 0, 0.08]}>
        <boxGeometry args={[0.06, 0.01, 0.012]} />
        <meshStandardMaterial map={textures.hair} color="#17100b" roughness={0.9} />
      </mesh>
      <mesh castShadow position={[0, 1.69, 0.215]}>
        <boxGeometry args={[0.035, 0.055, 0.035]} />
        <meshStandardMaterial map={textures.skin} color="#c98f70" roughness={0.68} />
      </mesh>
      <mesh castShadow position={[-0.07, 1.67, 0.218]}>
        <sphereGeometry args={[0.028, 8, 6]} />
        <meshStandardMaterial map={textures.skin} color="#e2ad89" roughness={0.72} />
      </mesh>
      <mesh castShadow position={[0.07, 1.67, 0.218]}>
        <sphereGeometry args={[0.028, 8, 6]} />
        <meshStandardMaterial map={textures.skin} color="#e2ad89" roughness={0.72} />
      </mesh>
      <mesh castShadow position={[0, 1.625, 0.202]}>
        <boxGeometry args={[0.09, 0.012, 0.014]} />
        <meshStandardMaterial color="#78323a" roughness={0.7} />
      </mesh>
      <mesh castShadow position={[-0.215, 1.705, 0]}>
        <sphereGeometry args={[0.035, 8, 6]} />
        <meshStandardMaterial map={textures.skin} color="#d9a47f" roughness={0.68} />
      </mesh>
      <mesh castShadow position={[0.215, 1.705, 0]}>
        <sphereGeometry args={[0.035, 8, 6]} />
        <meshStandardMaterial map={textures.skin} color="#d9a47f" roughness={0.68} />
      </mesh>
      <mesh castShadow position={[0, 1.88, -0.02]}>
        <sphereGeometry args={[0.205, 12, 8, 0, Math.PI * 2, 0, Math.PI * 0.55]} />
        <meshStandardMaterial map={textures.hair} color="#17100b" roughness={0.92} />
      </mesh>
      <mesh castShadow position={[0, 1.72, -0.145]}>
        <boxGeometry args={[0.34, 0.22, 0.08]} />
        <meshStandardMaterial map={textures.hair} color="#17100b" roughness={0.92} />
      </mesh>
    </group>
  )
}

// The player's own car. Its group is positioned/rotated each frame by PlayerRig from the shared
// `car` ref (parked pose, or the live driven pose). Local geometry is modelled with y=0 at the
// ground. A seated driver appears only while `driving`, and the head-lamps glow after dusk.
function PlayerCar({ car, driving }) {
  const driverRef = useRef()
  const headMat = useRef()
  const tailMat = useRef()
  const textures = useMemo(() => ({
    paint: makeProceduralTexture('vehicle-paint', { size: 128, seed: 71, repeatX: 1.5, repeatY: 1.2 }),
    glass: makeProceduralTexture('glass-smudge', { size: 128, seed: 72, repeatX: 1.2, repeatY: 1.2 }),
    rubber: makeProceduralTexture('rubber-tread', { size: 128, seed: 73, repeatX: 1.8, repeatY: 1.8 }),
  }), [])

  useFrame(() => {
    if (driverRef.current) driverRef.current.visible = !!driving.current
    const nf = nightFactor(useCityStore.getState().timeMinutes)
    if (headMat.current) headMat.current.emissiveIntensity = (driving.current ? 0.6 : 0.12) + nf * 1.5
    if (tailMat.current) {
      const braking = driving.current && (car.current.speed || 0) < -0.2
      tailMat.current.emissiveIntensity = (braking ? 1.4 : 0.1) + nf * 0.7
    }
  })

  const wheel = (x, z, key) => (
    <mesh key={key} position={[x, 0.33, z]} rotation={[0, 0, Math.PI / 2]} castShadow>
      <cylinderGeometry args={[0.33, 0.33, 0.2, 16]} />
      <meshStandardMaterial map={textures.rubber} color="#0a0c10" roughness={0.7} metalness={0.15} />
    </mesh>
  )

  return (
    <group>
      {/* body + roof cabin */}
      <mesh position={[0, 0.52, 0]} castShadow receiveShadow>
        <boxGeometry args={[2.02, 0.72, 4.5]} />
        <meshPhysicalMaterial map={textures.paint} color={PLAYER_CAR_TEAL} roughness={0.26} metalness={0.44} clearcoat={0.7} clearcoatRoughness={0.2} />
      </mesh>
      <mesh position={[0, 1.02, -0.15]} castShadow>
        <boxGeometry args={[1.78, 0.56, 2.0]} />
        <meshPhysicalMaterial map={textures.glass} color="#12202c" roughness={0.08} metalness={0.3} clearcoat={1} />
      </mesh>
      {/* windshield + rear glass */}
      <mesh position={[0, 1.05, 0.92]} rotation={[-0.28, 0, 0]}>
        <boxGeometry args={[1.66, 0.5, 0.05]} />
        <meshPhysicalMaterial color="#a6e2ff" roughness={0.04} transparent opacity={0.68} clearcoat={1} />
      </mesh>
      <mesh position={[0, 1.06, -1.18]} rotation={[0.24, 0, 0]}>
        <boxGeometry args={[1.6, 0.46, 0.05]} />
        <meshPhysicalMaterial color="#95d3ef" roughness={0.05} transparent opacity={0.64} clearcoat={1} />
      </mesh>
      {wheel(-0.86, 1.42, 'fl')}
      {wheel(0.86, 1.42, 'fr')}
      {wheel(-0.86, -1.42, 'rl')}
      {wheel(0.86, -1.42, 'rr')}
      {/* head lamps (front, +z) and tail lamps (rear, -z) */}
      <mesh position={[-0.62, 0.52, 2.26]}>
        <boxGeometry args={[0.3, 0.16, 0.09]} />
        <meshStandardMaterial ref={headMat} color="#fff6d8" emissive="#ffe4a0" emissiveIntensity={0.4} roughness={0.28} />
      </mesh>
      <mesh position={[0.62, 0.52, 2.26]}>
        <boxGeometry args={[0.3, 0.16, 0.09]} />
        <meshStandardMaterial color="#fff6d8" emissive="#ffe4a0" emissiveIntensity={0.4} roughness={0.28} />
      </mesh>
      <mesh position={[-0.64, 0.54, -2.26]}>
        <boxGeometry args={[0.3, 0.15, 0.09]} />
        <meshStandardMaterial ref={tailMat} color="#b3201d" emissive="#ff2419" emissiveIntensity={0.1} roughness={0.34} />
      </mesh>
      <mesh position={[0.64, 0.54, -2.26]}>
        <boxGeometry args={[0.3, 0.15, 0.09]} />
        <meshStandardMaterial color="#b3201d" emissive="#ff2419" emissiveIntensity={0.1} roughness={0.34} />
      </mesh>
      {/* seated driver — only shown while the player is inside */}
      <group ref={driverRef} visible={false}>
        <mesh position={[-0.34, 1.0, -0.1]} castShadow>
          <capsuleGeometry args={[0.17, 0.34, 4, 8]} />
          <meshStandardMaterial color="#26313f" roughness={0.78} />
        </mesh>
        <mesh position={[-0.34, 1.34, -0.05]} castShadow>
          <sphereGeometry args={[0.15, 12, 10]} />
          <meshStandardMaterial map={textures.paint} color="#d9a47f" roughness={0.66} />
        </mesh>
      </group>
    </group>
  )
}

export default function PlayerRig({ city }) {
  const keys = useKeys()
  const root = useRef()
  const heading = useRef(Math.PI)
  const lookYaw = useRef(0)
  const lookPitch = useRef(0)
  const velocityY = useRef(0)
  const grounded = useRef(false)
  const pos = useRef(new THREE.Vector3(0, terrainHeight(0, 40) + 2.2, 40))
  const moving = useRef(false)
  const running = useRef(false)
  const move = useMemo(() => new THREE.Vector3(), [])
  const camTarget = useMemo(() => new THREE.Vector3(), [])
  const lookAt = useMemo(() => new THREE.Vector3(), [])
  const lastPlace = useRef(null)
  const floorLevel = useRef(0)
  const floorCooldown = useRef(0)
  const collisionCooldowns = useRef(new Map())
  // drive mode: a dedicated player car parked near the spawn; F gets in / out.
  const car = useRef({ x: 6, z: 40, yaw: Math.PI / 2, speed: 0 })
  const driving = useRef(false)
  const fEdge = useRef(false)
  const nearCarHint = useRef(false)
  const carRef = useRef()
  const charRef = useRef()

  useEffect(() => {
    if (!import.meta.env.DEV || typeof window === 'undefined') return undefined

    const debugPlace = (detail = {}) => {
      const x = Number(detail.x)
      const z = Number(detail.z)
      if (!Number.isFinite(x) || !Number.isFinite(z)) return false

      const place = currentInterior(city, x, z)
      const floorCount = place?.floorCount || 1
      const requestedFloor = Number.isFinite(Number(detail.floor)) ? Math.floor(Number(detail.floor)) : 0
      const nextFloor = place ? Math.max(0, Math.min(floorCount - 1, requestedFloor)) : 0
      const baseY = terrainHeight(x, z) + 1.1
      const y = Number.isFinite(Number(detail.y))
        ? Number(detail.y)
        : baseY + nextFloor * (place?.floorHeight || 3.6)

      floorLevel.current = nextFloor
      floorCooldown.current = 0
      heading.current = Number.isFinite(Number(detail.heading)) ? Number(detail.heading) : heading.current
      lookYaw.current = Number.isFinite(Number(detail.lookYaw)) ? Number(detail.lookYaw) : 0
      lookPitch.current = Number.isFinite(Number(detail.lookPitch)) ? Number(detail.lookPitch) : 0
      velocityY.current = 0
      grounded.current = true
      moving.current = false
      running.current = false
      lastPlace.current = null
      pos.current.set(x, y, z)
      if (root.current) {
        root.current.position.copy(pos.current)
        root.current.rotation.y = heading.current
      }
      if (typeof detail.pulse === 'string' && detail.pulse.trim()) {
        useCityStore.getState().setPulse(detail.pulse.trim())
      }
      return true
    }

    const onDebugPlace = event => debugPlace(event.detail || {})
    window.__REALCITY_PLAYER_RIG__ = { debugPlace }
    window.addEventListener('realcity:debug-place-player', onDebugPlace)
    return () => {
      window.removeEventListener('realcity:debug-place-player', onDebugPlace)
      if (window.__REALCITY_PLAYER_RIG__?.debugPlace === debugPlace) delete window.__REALCITY_PLAYER_RIG__
    }
  }, [city])

  useFrame((state, delta) => {
    const dt = Math.min(delta, 0.12)
    const store = useCityStore.getState()
    store.tick(dt)
    const ride = store.ride
    if (!Number.isFinite(pos.current.x) || !Number.isFinite(pos.current.y) || !Number.isFinite(pos.current.z)) {
      pos.current.set(0, terrainHeight(0, 40) + 1.1, 40)
      heading.current = Math.PI
      velocityY.current = 0
      store.setPulse('Recovered camera position after invalid movement data.')
    }

    if (ride) {
      floorLevel.current = 0
      const startedAt = finiteNumber(ride.startedAt, performance.now())
      const duration = Math.max(0.5, finiteNumber(ride.duration, 6))
      const t = Math.min(1, Math.max(0, (performance.now() - startedAt) / (duration * 1000)))
      if (ride.path?.length >= 2) {
        const path = finiteRoute(ride.path)
        const routeMeters = Math.max(1, finiteNumber(ride.routeMeters, 1))
        if (path.length < 2) {
          store.finishRide('Taxi ride stopped because route data was invalid.')
          return
        }
        const distance = routeMeters * t
        const pose = sampleRoute(path, distance)
        if (!finitePoint2(pose)) {
          store.finishRide('Taxi ride stopped because route position was invalid.')
          return
        }
        heading.current = finiteNumber(pose.heading, heading.current)
        pos.current.set(pose.x, terrainHeight(pose.x, pose.z) + 1.1, pose.z)
        ride.taxiPose = { x: pose.x, z: pose.z, heading: heading.current, yaw: heading.current, routeCurve: pose.routeCurve || null }
        ride.routeCurve = pose.routeCurve || null
        ride.progress = t
        moving.current = true
        running.current = false
        grounded.current = true
        velocityY.current = 0
        if (t >= 1) {
          if (finitePoint2(ride.exitPoint)) {
            pos.current.set(ride.exitPoint.x, terrainHeight(ride.exitPoint.x, ride.exitPoint.z) + 1.1, ride.exitPoint.z)
          }
          store.finishRide(`Arrived at ${ride.destinationName || 'destination'}.`)
        }
      } else {
        if (!finitePoint2(ride.from) || !finitePoint2(ride.to)) {
          store.finishRide('Taxi ride stopped because endpoints were invalid.')
          return
        }
        const eased = smoothstep(t)
        const x = ride.from.x + (ride.to.x - ride.from.x) * eased
        const z = ride.from.z + (ride.to.z - ride.from.z) * eased
        heading.current = finiteNumber(Math.atan2(ride.to.x - ride.from.x, ride.to.z - ride.from.z), heading.current)
        pos.current.set(x, terrainHeight(x, z) + 1.1, z)
        moving.current = true
        running.current = false
        grounded.current = true
        velocityY.current = 0
        if (t >= 1) {
          if (finitePoint2(ride.exitPoint)) {
            pos.current.set(ride.exitPoint.x, terrainHeight(ride.exitPoint.x, ride.exitPoint.z) + 1.1, ride.exitPoint.z)
          }
          store.finishRide(`Arrived at ${ride.destinationName || 'destination'}.`)
        }
      }
    } else if (store.mission?.mode === 'taxi' && store.mission.phase === 'taxi_boarding' && store.mission.taxi?.pose) {
      const mission = store.mission
      const taxi = mission.taxi
      const startedAt = mission.boardingStartedAt || performance.now()
      const t = smoothstep(Math.min(1, Math.max(0, (performance.now() - startedAt) / 1450)))
      const start = finitePoint2(mission.boardingPlayerStart)
        ? safePoint2(mission.boardingPlayerStart)
        : { x: pos.current.x, z: pos.current.z }
      const rawDoor = taxiPassengerDoorPoint(taxi, 'player')
      const door = finitePoint2(rawDoor)
        ? rawDoor
        : safePoint2(taxi.passengerPickup || mission.pickup || taxi.pickupStop || taxi.pose, start)
      const x = start.x + (door.x - start.x) * t
      const z = start.z + (door.z - start.z) * t
      heading.current = finiteNumber(taxi.pose.heading ?? door.heading, heading.current)
      pos.current.set(x, terrainHeight(x, z) + 1.1, z)
      moving.current = t < 0.98
      running.current = false
      grounded.current = true
      velocityY.current = 0
    } else {
      // --- free movement: on foot, or driving the player car (F gets in / out) ---
      const fDown = !!keys.current.KeyF
      const fPressed = fDown && !fEdge.current
      fEdge.current = fDown

      if (driving.current) {
        if (fPressed) {
          // step out beside the car and hand control back to the on-foot rig
          driving.current = false
          car.current.speed = 0
          const rgtX = Math.cos(car.current.yaw)
          const rgtZ = -Math.sin(car.current.yaw)
          let exX = car.current.x + rgtX * 1.95
          let exZ = car.current.z + rgtZ * 1.95
          ;[exX, exZ] = resolveBuildingCollision(city, car.current.x, car.current.z, exX, exZ, 0.7)
          heading.current = car.current.yaw
          velocityY.current = 0
          grounded.current = true
          moving.current = false
          pos.current.set(exX, terrainHeight(exX, exZ) + 1.1, exZ)
          store.setPulse('You parked the car and stepped out.')
        } else {
          // simple bicycle model: speed is damped, steering authority grows with speed
          const throttle = (keys.current.KeyW ? 1 : 0) - (keys.current.KeyS ? 1 : 0)
          const steer = (keys.current.KeyA ? 1 : 0) - (keys.current.KeyD ? 1 : 0)
          const c = car.current
          if (throttle > 0) c.speed += DRIVE_ACCEL * dt
          else if (throttle < 0) c.speed -= (c.speed > 0 ? DRIVE_BRAKE : DRIVE_ACCEL) * dt
          else {
            c.speed -= c.speed * DRIVE_DRAG * dt
            if (Math.abs(c.speed) < 0.05) c.speed = 0
          }
          c.speed = Math.max(-DRIVE_MAX_REVERSE, Math.min(DRIVE_MAX_SPEED, c.speed))
          const authority = Math.min(1, Math.abs(c.speed) / DRIVE_STEER_REF)
          c.yaw += steer * DRIVE_STEER_RATE * authority * Math.sign(c.speed) * dt
          const nx = c.x + Math.sin(c.yaw) * c.speed * dt
          const nz = c.z + Math.cos(c.yaw) * c.speed * dt
          const [sx, sz] = resolveBuildingCollision(city, c.x, c.z, nx, nz, CAR_BODY_RADIUS)
          if (Math.hypot(sx - nx, sz - nz) > 0.05) c.speed *= 0.25 // scraped a wall — bleed off speed
          c.x = sx
          c.z = sz
          heading.current = c.yaw
          moving.current = Math.abs(c.speed) > 0.1
          running.current = false
          grounded.current = true
          velocityY.current = 0
          pos.current.set(c.x, terrainHeight(c.x, c.z) + 1.1, c.z)
        }
      } else if (fPressed && grounded.current
                 && Math.hypot(pos.current.x - car.current.x, pos.current.z - car.current.z) < CAR_ENTER_RADIUS) {
        // board the parked car
        driving.current = true
        car.current.speed = 0
        heading.current = car.current.yaw
        moving.current = false
        velocityY.current = 0
        grounded.current = true
        pos.current.set(car.current.x, terrainHeight(car.current.x, car.current.z) + 1.1, car.current.z)
        store.setPulse('You got in. W/S to accelerate and brake, A/D to steer, F to get out.')
      } else {
        const nearCar = Math.hypot(pos.current.x - car.current.x, pos.current.z - car.current.z) < CAR_ENTER_RADIUS
        if (nearCar && !nearCarHint.current) {
          nearCarHint.current = true
          store.setPulse('Press F to drive the car.')
        } else if (!nearCar && nearCarHint.current) {
          nearCarHint.current = false
        }
      if (keys.current.KeyA) heading.current += TURN_SPEED * dt
      if (keys.current.KeyD) heading.current -= TURN_SPEED * dt

      const targetLookYaw = keys.current.ArrowLeft
        ? FREE_LOOK_YAW
        : keys.current.ArrowRight
          ? -FREE_LOOK_YAW
          : 0
      const targetLookPitch = keys.current.ArrowUp
        ? FREE_LOOK_PITCH_UP
        : keys.current.ArrowDown
          ? FREE_LOOK_PITCH_DOWN
          : 0
      const lookSpeed = targetLookYaw || targetLookPitch ? FREE_LOOK_IN_SPEED : FREE_LOOK_RETURN_SPEED
      lookYaw.current = approach(lookYaw.current, targetLookYaw, lookSpeed, dt)
      lookPitch.current = approach(lookPitch.current, targetLookPitch, lookSpeed, dt)

      // Vehicle-style keyboard control: WASD drives the body's heading; arrows are temporary free-look only.
      const forwardX = Math.sin(heading.current)
      const forwardZ = Math.cos(heading.current)
      const throttle = (keys.current.KeyW ? 1 : 0) - (keys.current.KeyS ? 1 : 0)
      move.set(0, 0, 0)

      running.current = !!(keys.current.ShiftLeft || keys.current.ShiftRight)
      moving.current = Math.abs(throttle) > 0.001

      if (moving.current) {
        const distance = throttle * (running.current ? RUN_SPEED : WALK_SPEED) * dt
        move.set(forwardX * distance, 0, forwardZ * distance)
      }

      velocityY.current -= GRAVITY * dt
      if (keys.current.Space && grounded.current) {
        velocityY.current = JUMP
        grounded.current = false
      }

      const nextX = pos.current.x + move.x
      const nextZ = pos.current.z + move.z
      let [safeX, safeZ] = resolveBuildingCollision(city, pos.current.x, pos.current.z, nextX, nextZ)
      ;[safeX, safeZ] = resolveDynamicCollision(store, pos.current.x, pos.current.z, safeX, safeZ, running.current, collisionCooldowns.current)
      const placeAtNext = currentInterior(city, safeX, safeZ)
      const floorOffset = placeAtNext ? floorLevel.current * (placeAtNext.floorHeight || 3.6) : 0
      const groundY = terrainHeight(safeX, safeZ) + 1.1 + floorOffset
      let nextY = pos.current.y + velocityY.current * dt
      if (nextY <= groundY) {
        nextY = groundY
        velocityY.current = 0
        grounded.current = true
      }

      pos.current.set(safeX, nextY, safeZ)
      }
    }

    if (root.current) {
      // keep the parked/driven car synced to its pose; hide the walking body while driving
      if (carRef.current) {
        carRef.current.position.set(car.current.x, terrainHeight(car.current.x, car.current.z), car.current.z)
        carRef.current.rotation.y = car.current.yaw
      }
      if (charRef.current) charRef.current.visible = !driving.current
      root.current.position.copy(pos.current)
      root.current.rotation.y += Math.atan2(Math.sin(heading.current - root.current.rotation.y), Math.cos(heading.current - root.current.rotation.y)) * 0.22
    }

    const viewHeading = heading.current + lookYaw.current
    const cameraOrbit = viewHeading + Math.PI
    const cameraElevation = CAMERA_BASE_ELEVATION + lookPitch.current
    const ce = Math.cos(cameraElevation)
    const rideCamera = !!ride || (store.mission?.mode === 'taxi' && ['taxi_boarding', 'taxi_ride'].includes(store.mission.phase))
    const camDist = driving.current ? DRIVE_CAMERA_DISTANCE : CAMERA_DISTANCE
    const camHeight = driving.current ? DRIVE_CAMERA_HEIGHT : CAMERA_HEIGHT
    camTarget.set(
      pos.current.x + camDist * Math.sin(cameraOrbit) * ce,
      pos.current.y + camHeight + camDist * Math.sin(cameraElevation),
      pos.current.z + camDist * Math.cos(cameraOrbit) * ce,
    )
    const impactShake = rideCamera ? 0 : Math.min(0.32, (store.playerPhysics?.impactFlash || 0) * 0.24)
    if (impactShake > 0.001) {
      camTarget.x += Math.sin(state.clock.elapsedTime * 34.7) * impactShake
      camTarget.y += Math.sin(state.clock.elapsedTime * 42.1 + 0.8) * impactShake * 0.42
      camTarget.z += Math.cos(state.clock.elapsedTime * 31.3) * impactShake
    }
    const cameraPlace = currentInterior(city, pos.current.x, pos.current.z)
    const cameraSafety = !cameraPlace || rideCamera
      ? resolveCameraTarget(city, pos.current, camTarget, rideCamera ? 2.4 : 1.35)
      : { x: camTarget.x, y: camTarget.y, z: camTarget.z, avoided: false }
    camTarget.set(cameraSafety.x, cameraSafety.y, cameraSafety.z)
    if (!Number.isFinite(camTarget.x) || !Number.isFinite(camTarget.y) || !Number.isFinite(camTarget.z)) {
      camTarget.set(pos.current.x, pos.current.y + CAMERA_HEIGHT + 2, pos.current.z + CAMERA_DISTANCE)
    }
    if (!finiteVector3(state.camera.position)) {
      state.camera.position.set(camTarget.x, camTarget.y, camTarget.z)
    } else {
      state.camera.position.lerp(camTarget, 0.12)
    }
    if (!finiteVector3(state.camera.position)) {
      state.camera.position.set(pos.current.x, pos.current.y + CAMERA_HEIGHT + 2, pos.current.z + CAMERA_DISTANCE)
    }
    lookAt.set(pos.current.x, pos.current.y + 1.2, pos.current.z)
    if (!Number.isFinite(lookAt.x) || !Number.isFinite(lookAt.y) || !Number.isFinite(lookAt.z)) {
      lookAt.set(0, terrainHeight(0, 40) + 2.3, 40)
    }
    state.camera.lookAt(lookAt)
    if (import.meta.env.DEV && typeof window !== 'undefined') {
      window.__REALCITY_CAMERA_STATE__ = {
        mode: ride ? 'taxi_ride' : rideCamera ? 'taxi_boarding' : cameraPlace ? 'interior' : 'walk',
        avoidedSolid: cameraSafety.avoided,
        camera: {
          x: state.camera.position.x,
          y: state.camera.position.y,
          z: state.camera.position.z,
        },
        target: {
          x: camTarget.x,
          y: camTarget.y,
          z: camTarget.z,
        },
        focus: {
          x: pos.current.x,
          y: pos.current.y,
          z: pos.current.z,
        },
      }
    }

    const district = city.districtAt(pos.current.x, pos.current.z).name
    const place = cameraPlace
    const storeNow = useCityStore.getState()
    if ((place?.id || null) !== lastPlace.current) {
      lastPlace.current = place?.id || null
      floorLevel.current = 0
      if (place) {
        const info = indoorFloorInfo(place, 0)
        storeNow.setPulse(`You entered ${place.name}. ${info.label}: ${info.zone}. ${info.core} is visible from the lobby.`)
      }
    }
    floorCooldown.current = Math.max(0, floorCooldown.current - dt)
    if (!place) {
      floorLevel.current = 0
    } else if ((place.floorCount || 1) > 1 && floorCooldown.current <= 0) {
      const floorDelta = (keys.current.PageUp || keys.current.KeyR ? 1 : 0) - (keys.current.PageDown || keys.current.KeyF ? 1 : 0)
      if (floorDelta) {
        const nextFloor = Math.max(0, Math.min((place.floorCount || 1) - 1, floorLevel.current + floorDelta))
        if (nextFloor !== floorLevel.current) {
          floorLevel.current = nextFloor
          floorCooldown.current = FLOOR_CHANGE_COOLDOWN
          velocityY.current = 0
          grounded.current = true
          pos.current.y = terrainHeight(pos.current.x, pos.current.z) + 1.1 + floorLevel.current * (place.floorHeight || 3.6)
          const info = indoorFloorInfo(place, floorLevel.current)
          storeNow.setPulse(`${info.core} to ${info.label} in ${place.name}: ${info.zone}.`)
        }
      }
    }
    const floorInfo = indoorFloorInfo(place, floorLevel.current)
    storeNow.setPlayer({
      x: pos.current.x,
      y: pos.current.y,
      z: pos.current.z,
      heading: heading.current,
      viewHeading,
      speed: moving.current ? (running.current ? RUN_SPEED : WALK_SPEED) : 0,
      district,
      placeId: place?.id || null,
      placeName: place?.name || null,
      indoors: !!place,
      floor: place ? floorLevel.current + 1 : 0,
      floorCount: place?.floorCount || 0,
      verticalCore: place?.verticalCore || null,
      floorLabel: floorInfo?.label || null,
      floorZone: floorInfo?.zone || null,
      accessHint: floorInfo?.access || null,
      coreHint: floorInfo?.core || null,
      floorGuide: floorInfo?.guide || null,
      floorDirectory: place?.floorDirectory || [],
    })
  })

  return (
    <>
      <group ref={root} position={pos.current.toArray()}>
        <group ref={charRef}>
          <Character moving={moving} running={running} />
        </group>
      </group>
      <group
        ref={carRef}
        position={[car.current.x, terrainHeight(car.current.x, car.current.z), car.current.z]}
        rotation={[0, car.current.yaw, 0]}
      >
        <PlayerCar car={car} driving={driving} />
      </group>
    </>
  )
}
