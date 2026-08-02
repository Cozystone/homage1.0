// Verify the Rapier rigid-body solver reproduces true physical law — headless in Node.
// Rapier is the city's BODY (physics authority). If the city's physics is TRUE, then what ATANOR
// observes in the digital twin is true, and ATANOR's physics knowledge cannot be contaminated by it.
import RAPIER from '@dimforge/rapier3d-compat'

await RAPIER.init()   // compat build inlines the wasm; runs anywhere including Node

const G = 9.81
let ok = true
const report = (pass, msg) => { ok = ok && pass; console.log((pass ? '  PASS ' : '  FAIL ') + msg) }

function world() {
  const w = new RAPIER.World({ x: 0, y: -G, z: 0 })
  w.timestep = 1 / 240
  return w
}
function ground(w, restitution = 0.0) {
  // static cuboid, top surface at y=0 (half-height 0.5, centered at y=-0.5)
  w.createCollider(RAPIER.ColliderDesc.cuboid(50, 0.5, 50).setTranslation(0, -0.5, 0).setRestitution(restitution))
}
function dropBox(w, y0, half = 0.25, restitution = 0.0) {
  const body = w.createRigidBody(RAPIER.RigidBodyDesc.dynamic().setTranslation(0, y0, 0))
  w.createCollider(RAPIER.ColliderDesc.cuboid(half, half, half).setRestitution(restitution).setDensity(100), body)
  return body
}
const boxY = (b) => b.translation().y

// ---- TEST 1: gravity is real — free fall matches y = y0 - 1/2 g t^2 (no ground) ----
{
  const w = world(), y0 = 10, T = 1
  const b = dropBox(w, y0)
  for (let t = 0; t < T - 1e-9; t += 1 / 240) w.step()
  const y = boxY(b), analytic = y0 - 0.5 * G * T * T
  const err = Math.abs(y - analytic)
  console.log(`  free-fall ${T}s: Rapier y=${y.toFixed(4)} analytic=${analytic.toFixed(4)} err=${err.toFixed(4)}`)
  report(err < 0.05, `gravity reproduces y = y0 - 1/2 g t^2 (err ${err.toFixed(4)} < 0.05)`)
  w.free()
}

// ---- TEST 2: support is real — a box dropped onto ground RESTS on it, never tunnels ----
{
  const w = world(); ground(w)
  const half = 0.25, b = dropBox(w, 5, half)
  let minY = 99
  for (let i = 0; i < 720; i++) { w.step(); minY = Math.min(minY, boxY(b)) }
  const yFinal = boxY(b)
  console.log(`  settle: final y=${yFinal.toFixed(4)} (rest ~${half}) lowest=${minY.toFixed(4)}`)
  report(Math.abs(yFinal - half) < 0.05, `box RESTS on support at y≈${half} (got ${yFinal.toFixed(4)})`)
  report(minY > -0.05, `box NEVER tunnels through ground (lowest ${minY.toFixed(4)})`)
  w.free()
}

// ---- TEST 3: restitution is real — a bouncy material rebounds after impact ----
{
  const w = world(); ground(w, 0.8)
  const b = dropBox(w, 5, 0.25, 0.8)
  let touched = false, apex = 0
  for (let i = 0; i < 900; i++) { w.step(); const y = boxY(b); if (y < 0.4) touched = true; if (touched && y > apex) apex = y }
  console.log(`  bounce: rebound apex=${apex.toFixed(3)}`)
  report(apex > 0.6, `elastic material bounces back up (apex ${apex.toFixed(3)} > 0.6)`)
  w.free()
}

// ---- TEST 4: momentum — a box shoved horizontally on a frozen (frictionless) floor keeps moving ----
{
  const w = world()
  w.createCollider(RAPIER.ColliderDesc.cuboid(50, 0.5, 50).setTranslation(0, -0.5, 0).setFriction(0))
  const b = w.createRigidBody(RAPIER.RigidBodyDesc.dynamic().setTranslation(0, 0.25, 0))
  w.createCollider(RAPIER.ColliderDesc.cuboid(0.25, 0.25, 0.25).setFriction(0).setDensity(100), b)
  b.setLinvel({ x: 3, y: 0, z: 0 }, true)
  const x0 = b.translation().x
  for (let i = 0; i < 120; i++) w.step()   // 0.5s
  const dx = b.translation().x - x0
  console.log(`  momentum: travelled dx=${dx.toFixed(3)} in 0.5s at 3 m/s (ideal ~1.5)`)
  report(dx > 1.2, `frictionless momentum carries the body (dx ${dx.toFixed(3)} > 1.2)`)
  w.free()
}

console.log('\nRAPIER TRUTH CHECK:', ok ? 'ALL PASS — the physics is physically true' : 'SOME FAILED')
process.exit(ok ? 0 : 1)
