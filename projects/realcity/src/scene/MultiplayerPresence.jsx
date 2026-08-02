import { useEffect, useMemo, useRef } from 'react'
import { useFrame } from '@react-three/fiber'
import { Billboard, Text } from '@react-three/drei'
import { useCityStore } from '../engine/cityStore'
import { DIGITAL_HUMAN_SOURCE } from './digitalHumanRig'

const SEND_INTERVAL = 0.72
const REMOTE_LERP_RATE = 8.2

function hashValue(value) {
  let hash = 0
  const text = String(value || '')
  for (let i = 0; i < text.length; i += 1) hash = (hash * 31 + text.charCodeAt(i)) >>> 0
  return hash
}

function finiteNumber(value, fallback = 0) {
  const number = Number(value)
  return Number.isFinite(number) ? number : fallback
}

function turnToward(current, target, amount) {
  const delta = Math.atan2(Math.sin(target - current), Math.cos(target - current))
  return current + delta * amount
}

function peerLook(peer) {
  const hash = hashValue(peer.id || peer.name)
  const skin = ['#f0c49b', '#d8a17d', '#b98262', '#efd2b3', '#9f6a4f'][hash % 5]
  const hair = ['#17100b', '#2b1b12', '#4b3527', '#111318', '#6b5949'][(hash >> 3) % 5]
  const pants = ['#17203a', '#1f2937', '#2f3a2d', '#3d2430', '#111827'][(hash >> 6) % 5]
  return {
    skin,
    hair,
    pants,
    jacket: peer.color || '#4aadff',
    accent: ['#f8fafc', '#e2e8f0', '#fef3c7', '#dbeafe'][(hash >> 9) % 4],
  }
}

function peerFromServer(player) {
  const pose = player.pose || {}
  return {
    id: player.id,
    name: player.name,
    color: player.color || '#4aadff',
    x: Number(pose.x || 0),
    y: Number(pose.y || 1),
    z: Number(pose.z || 0),
    heading: Number(pose.heading || 0),
    speed: Number(pose.speed || 0),
    district: pose.district || 'RealCity',
    status: player.status || 'exploring',
    updatedAt: player.updatedAt || 0,
  }
}

async function postPresence(multiplayer, player) {
  const response = await fetch('/api/multiplayer', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      roomId: multiplayer.roomId,
      playerId: multiplayer.playerId,
      name: multiplayer.name,
      color: multiplayer.color,
      status: player.indoors ? `inside ${player.placeName || 'a building'}` : `exploring ${player.district}`,
      pose: {
        x: player.x,
        y: player.y,
        z: player.z,
        heading: player.heading,
        speed: player.speed,
        district: player.district,
      },
    }),
  })
  if (!response.ok) throw new Error(`Multiplayer API ${response.status}`)
  return response.json()
}

function sendLeave(multiplayer) {
  if (!multiplayer?.playerId || !multiplayer?.roomId) return
  const body = JSON.stringify({
    action: 'leave',
    roomId: multiplayer.roomId,
    playerId: multiplayer.playerId,
  })
  try {
    const blob = new Blob([body], { type: 'application/json' })
    if (navigator.sendBeacon?.('/api/multiplayer', blob)) return
  } catch {
    // Fall through to fetch.
  }
  fetch('/api/multiplayer', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body,
    keepalive: true,
  }).catch(() => {})
}

function RemoteAvatar({ peer }) {
  const group = useRef(null)
  const yaw = useRef(finiteNumber(peer.heading, 0))
  const look = useMemo(() => peerLook(peer), [peer.id, peer.name, peer.color])

  useFrame((_, delta) => {
    if (!group.current) return
    const amount = 1 - Math.exp(-REMOTE_LERP_RATE * Math.min(delta, 0.1))
    const targetX = finiteNumber(peer.x)
    const targetY = finiteNumber(peer.y, 1)
    const targetZ = finiteNumber(peer.z)
    group.current.position.lerp({ x: targetX, y: targetY, z: targetZ }, amount)
    yaw.current = turnToward(yaw.current, finiteNumber(peer.heading, yaw.current), amount)
    group.current.rotation.y = yaw.current
  })

  return (
    <group
      ref={group}
      position={[finiteNumber(peer.x), finiteNumber(peer.y, 1), finiteNumber(peer.z)]}
      rotation={[0, finiteNumber(peer.heading), 0]}
    >
      <group position={[0, -0.9, 0]}>
        <mesh castShadow position={[0, 0.78, 0]}>
          <boxGeometry args={[0.38, 0.2, 0.25]} />
          <meshStandardMaterial color={look.pants} roughness={0.8} />
        </mesh>
        <mesh castShadow position={[0, 1.2, 0]}>
          <capsuleGeometry args={[0.21, 0.52, 4, 10]} />
          <meshStandardMaterial color={look.jacket} roughness={0.72} />
        </mesh>
        <mesh castShadow position={[0, 1.27, 0.18]}>
          <boxGeometry args={[0.28, 0.34, 0.035]} />
          <meshStandardMaterial color={look.accent} roughness={0.56} metalness={0.02} />
        </mesh>
        <mesh castShadow position={[0, 1.57, 0]}>
          <capsuleGeometry args={[0.075, 0.12, 4, 8]} />
          <meshStandardMaterial color={look.skin} roughness={0.66} />
        </mesh>
        <mesh castShadow position={[-0.12, 0.4, 0]}>
          <capsuleGeometry args={[0.065, 0.52, 4, 8]} />
          <meshStandardMaterial color={look.pants} roughness={0.84} />
        </mesh>
        <mesh castShadow position={[0.12, 0.4, 0]}>
          <capsuleGeometry args={[0.065, 0.52, 4, 8]} />
          <meshStandardMaterial color={look.pants} roughness={0.84} />
        </mesh>
        <mesh castShadow position={[-0.12, 0.07, 0.045]}>
          <boxGeometry args={[0.11, 0.06, 0.18]} />
          <meshStandardMaterial color="#0d1118" roughness={0.85} />
        </mesh>
        <mesh castShadow position={[0.12, 0.07, 0.045]}>
          <boxGeometry args={[0.11, 0.06, 0.18]} />
          <meshStandardMaterial color="#0d1118" roughness={0.85} />
        </mesh>
        <mesh castShadow position={[-0.28, 1.08, 0]}>
          <capsuleGeometry args={[0.055, 0.42, 4, 8]} />
          <meshStandardMaterial color={look.skin} roughness={0.68} />
        </mesh>
        <mesh castShadow position={[0.28, 1.08, 0]}>
          <capsuleGeometry args={[0.055, 0.42, 4, 8]} />
          <meshStandardMaterial color={look.skin} roughness={0.68} />
        </mesh>
        <mesh castShadow position={[0, 1.72, 0]}>
          <sphereGeometry args={[0.205, 18, 14]} />
          <meshStandardMaterial color={look.skin} roughness={0.64} />
        </mesh>
        <mesh castShadow position={[-0.088, 1.745, 0.188]}>
          <sphereGeometry args={[0.024, 8, 6]} />
          <meshStandardMaterial color="#05070a" roughness={0.34} />
        </mesh>
        <mesh castShadow position={[0.088, 1.745, 0.188]}>
          <sphereGeometry args={[0.024, 8, 6]} />
          <meshStandardMaterial color="#05070a" roughness={0.34} />
        </mesh>
        <mesh castShadow position={[0, 1.88, -0.02]}>
          <sphereGeometry args={[0.205, 12, 8, 0, Math.PI * 2, 0, Math.PI * 0.55]} />
          <meshStandardMaterial color={look.hair} roughness={0.92} />
        </mesh>
        <mesh castShadow position={[0, 1.72, -0.145]}>
          <boxGeometry args={[0.34, 0.22, 0.08]} />
          <meshStandardMaterial color={look.hair} roughness={0.92} />
        </mesh>
      </group>
      <Billboard position={[0, 0.72, 0]}>
        <mesh position={[0, 0.02, -0.01]}>
          <planeGeometry args={[1.62, 0.48]} />
          <meshBasicMaterial color="#06111d" transparent opacity={0.74} depthWrite={false} />
        </mesh>
        <Text
          position={[0, 0.12, 0]}
          fontSize={0.13}
          maxWidth={1.42}
          textAlign="center"
          color="#f8fbff"
          outlineWidth={0.012}
          outlineColor="#06111d"
        >
          {peer.name || 'Player'}
        </Text>
        <Text
          position={[0, -0.08, 0]}
          fontSize={0.075}
          maxWidth={1.42}
          textAlign="center"
          color="#b8d8f2"
          outlineWidth={0.008}
          outlineColor="#06111d"
        >
          {peer.status || peer.district || 'online'}
        </Text>
      </Billboard>
    </group>
  )
}

export default function MultiplayerPresence() {
  const enabled = useCityStore(state => state.multiplayer.enabled)
  const peers = useCityStore(state => state.multiplayer.peers)
  const elapsed = useRef(0)
  const inflight = useRef(false)
  const lastIdentity = useRef(null)
  const wasEnabled = useRef(false)

  useEffect(() => {
    if (!enabled && wasEnabled.current) sendLeave(lastIdentity.current)
    wasEnabled.current = enabled
  }, [enabled])

  useEffect(() => () => sendLeave(lastIdentity.current), [])

  useEffect(() => {
    if (typeof window === 'undefined') return
    window.__REALCITY_MULTIPLAYER__ = {
      enabled,
      roomId: useCityStore.getState().multiplayer.roomId,
      peerCount: peers.length,
      remoteAvatarBase: DIGITAL_HUMAN_SOURCE.base,
      renderMode: 'smoothed-nameplate-peer-avatar',
      peers: peers.map(peer => ({ id: peer.id, name: peer.name, district: peer.district })),
    }
  }, [enabled, peers])

  useFrame((_, delta) => {
    if (!enabled || inflight.current || typeof fetch === 'undefined') return
    elapsed.current += delta
    if (elapsed.current < SEND_INTERVAL) return
    elapsed.current = 0

    const state = useCityStore.getState()
    const multiplayer = state.multiplayer
    lastIdentity.current = multiplayer
    inflight.current = true
    postPresence(multiplayer, state.player)
      .then(data => {
        if (!data?.ok) throw new Error(data?.error || 'Multiplayer update failed')
        useCityStore.getState().setMultiplayerPresence({
          status: 'online',
          lastError: null,
          serverTime: data.serverTime,
          playerCount: data.playerCount,
          peers: (data.peers || []).map(peerFromServer),
        })
      })
      .catch(error => {
        useCityStore.getState().setMultiplayerPresence({
          status: 'offline',
          lastError: error instanceof Error ? error.message : String(error),
        })
      })
      .finally(() => {
        inflight.current = false
      })
  })

  if (!enabled || peers.length === 0) return null
  return peers.slice(0, 24).map(peer => <RemoteAvatar key={peer.id} peer={peer} />)
}
