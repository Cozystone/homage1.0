import { spawn, spawnSync } from 'node:child_process'
import { existsSync } from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'
import { chromium } from 'playwright-core'

const __dirname = path.dirname(fileURLToPath(import.meta.url))
const root = path.resolve(__dirname, '..')
const port = 5290 + Math.floor(Math.random() * 120)
const baseUrl = `http://127.0.0.1:${port}`

function assert(condition, message) {
  if (!condition) throw new Error(message)
}

function sleep(ms) {
  return new Promise(resolve => setTimeout(resolve, ms))
}

function degreeDiff(a, b) {
  const radians = (((a - b) * Math.PI) / 180 + Math.PI * 3) % (Math.PI * 2) - Math.PI
  return (radians * 180) / Math.PI
}

function headingToMapDegrees(heading) {
  const degrees = (heading * 180) / Math.PI
  return ((degrees % 360) + 360) % 360
}

function headingToMinimapBearing(heading) {
  const degrees = headingToMapDegrees(heading)
  return degrees > 180 ? degrees - 360 : degrees
}

function findBrowserExecutable() {
  const candidates = process.platform === 'win32'
    ? [
        path.join(process.env.PROGRAMFILES || 'C:\\Program Files', 'Google\\Chrome\\Application\\chrome.exe'),
        path.join(process.env['PROGRAMFILES(X86)'] || 'C:\\Program Files (x86)', 'Google\\Chrome\\Application\\chrome.exe'),
        path.join(process.env.LOCALAPPDATA || '', 'Google\\Chrome\\Application\\chrome.exe'),
        path.join(process.env.PROGRAMFILES || 'C:\\Program Files', 'Microsoft\\Edge\\Application\\msedge.exe'),
        path.join(process.env['PROGRAMFILES(X86)'] || 'C:\\Program Files (x86)', 'Microsoft\\Edge\\Application\\msedge.exe'),
      ]
    : [
        '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',
        '/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge',
        '/usr/bin/google-chrome',
        '/usr/bin/chromium',
        '/usr/bin/chromium-browser',
        '/usr/bin/microsoft-edge',
      ]
  return candidates.find(candidate => candidate && existsSync(candidate))
}

function startDevServer() {
  const command = process.platform === 'win32' ? 'cmd.exe' : 'npm'
  const args = process.platform === 'win32'
    ? ['/d', '/s', '/c', `npm run dev -- --host 127.0.0.1 --port ${port} --strictPort`]
    : ['run', 'dev', '--', '--host', '127.0.0.1', '--port', String(port), '--strictPort']
  const child = spawn(command, args, {
    cwd: root,
    stdio: ['ignore', 'pipe', 'pipe'],
    env: { ...process.env, BROWSER: 'none' },
  })
  const logs = []
  child.stdout.on('data', chunk => logs.push(chunk.toString()))
  child.stderr.on('data', chunk => logs.push(chunk.toString()))
  return { child, logs }
}

function stopDevServer(child) {
  if (!child || child.killed) return
  if (process.platform === 'win32') {
    spawnSync('taskkill.exe', ['/PID', String(child.pid), '/T', '/F'], { stdio: 'ignore' })
    return
  }
  child.kill('SIGTERM')
}

async function waitForServer() {
  const started = Date.now()
  while (Date.now() - started < 45000) {
    try {
      const response = await fetch(baseUrl)
      if (response.ok) return
    } catch {
      await sleep(500)
    }
  }
  throw new Error(`Timed out waiting for Vite dev server at ${baseUrl}`)
}

async function holdClock(page, timeMinutes, day) {
  await page.evaluate(({ timeMinutes, day }) => {
    if (window.__REALCITY_ROAD_MINIMAP_CLOCK__) clearInterval(window.__REALCITY_ROAD_MINIMAP_CLOCK__)
    const store = window.__REALCITY_STORE__?.getState()
    store?.setClock?.(timeMinutes, day)
    window.__REALCITY_ROAD_MINIMAP_CLOCK__ = setInterval(() => {
      window.__REALCITY_STORE__?.getState()?.setClock?.(timeMinutes, day)
    }, 12)
  }, { timeMinutes, day })
}

async function clearClock(page) {
  await page.evaluate(() => {
    if (window.__REALCITY_ROAD_MINIMAP_CLOCK__) clearInterval(window.__REALCITY_ROAD_MINIMAP_CLOCK__)
    window.__REALCITY_ROAD_MINIMAP_CLOCK__ = null
  })
}

async function verifyRoadRendering(page) {
  await page.waitForFunction(() => {
    const rendering = window.__REALCITY_RENDERING__
    return rendering?.roadMarkings?.centerLineDashes > 0 &&
      rendering?.crosswalks?.allRoadCrossingCoverage &&
      rendering?.turnLaneMarkings?.flatStencilArrows &&
      rendering?.pedestrianSignals?.heads > 0
  }, null, { timeout: 25000 })
  const result = await page.evaluate(() => window.__REALCITY_RENDERING__)
  assert(result.roadMarkings.centerLineDashes >= result.streetHierarchy.sourceRoads * 20, `Road center markings are too sparse: ${JSON.stringify(result.roadMarkings)}`)
  assert(result.roadMarkings.roadEdgeLines >= result.streetHierarchy.sourceRoads * 2, `Road edge markings are incomplete: ${JSON.stringify(result.roadMarkings)}`)
  assert(result.crosswalks.priorityZebraCrossings > result.crosswalks.signalizedCrossings && result.crosswalks.localGapCrossings > 0, `Crosswalk coverage is incomplete: ${JSON.stringify(result.crosswalks)}`)
  assert(result.turnLaneMarkings.flatStencilArrows, `Turn arrows are not flat paint stencils: ${JSON.stringify(result.turnLaneMarkings)}`)
  return {
    roadMarkings: result.roadMarkings,
    crosswalks: result.crosswalks,
    turnLaneMarkings: result.turnLaneMarkings,
  }
}

async function verifyMinimapOrientation(page) {
  const readSample = () => page.evaluate(() => {
    const node = document.querySelector('.minimap')
    const runtime = window.__REALCITY_MINIMAP__ || {}
    const player = window.__REALCITY_STORE__?.getState()?.player || {}
    return {
      playerHeading: Number(player.viewHeading ?? player.heading),
      heading: Number(node?.getAttribute('data-heading')),
      mapHeading: Number(node?.getAttribute('data-map-heading')),
      bearing: Number(node?.getAttribute('data-bearing')),
      headingUp: node?.getAttribute('data-heading-up'),
      northZ: node?.getAttribute('data-north-z'),
      runtimeMapHeading: Number(runtime.mapHeading),
      headingUpProjection: runtime.headingUpProjection,
      projection: runtime.projection,
      orientationRule: runtime.orientationRule,
    }
  })
  const waitForCurrentFormula = async () => {
    await page.waitForFunction(() => {
      const node = document.querySelector('.minimap')
      const runtime = window.__REALCITY_MINIMAP__ || {}
      const player = window.__REALCITY_STORE__?.getState()?.player || {}
      const heading = Number(player.viewHeading ?? player.heading)
      const mapHeading = Number(node?.getAttribute('data-map-heading'))
      const bearing = Number(node?.getAttribute('data-bearing'))
      const headingUp = node?.getAttribute('data-heading-up')
      const northZ = node?.getAttribute('data-north-z')
      const expectedMapHeading = (((heading * 180) / Math.PI) % 360 + 360) % 360
      const expectedBearing = expectedMapHeading > 180 ? expectedMapHeading - 360 : expectedMapHeading
      return Number.isFinite(mapHeading) &&
        Number.isFinite(bearing) &&
        Math.abs((((mapHeading - expectedMapHeading + 540) % 360) - 180)) < 1.5 &&
        Math.abs((((bearing - expectedBearing + 540) % 360) - 180)) < 1.5 &&
        Math.abs((((Number(runtime.mapHeading) - expectedMapHeading + 540) % 360) - 180)) < 1.5 &&
        headingUp === 'true' &&
        northZ === 'positive' &&
        runtime.headingUpProjection === true &&
        Number(runtime.projection?.forwardDy) < -0.8
    }, null, { timeout: 8000 })
  }
  await waitForCurrentFormula()
  const before = await readSample()
  assert(Math.abs(degreeDiff(before.mapHeading, headingToMapDegrees(before.playerHeading))) < 1.5, `Initial minimap map heading is flipped: ${JSON.stringify(before)}`)
  assert(Math.abs(degreeDiff(before.bearing, headingToMinimapBearing(before.playerHeading))) < 1.5, `Initial minimap bearing is flipped: ${JSON.stringify(before)}`)
  assert(before.headingUp === 'true' && before.northZ === 'positive' && before.headingUpProjection === true && before.projection?.forwardDy < -0.8, `Initial minimap is vertically flipped: ${JSON.stringify(before)}`)

  await page.keyboard.down('KeyA')
  await page.waitForTimeout(900)
  await page.keyboard.up('KeyA')
  await page.waitForTimeout(350)
  await waitForCurrentFormula()
  const after = await readSample()
  const headingDelta = degreeDiff((after.playerHeading * 180) / Math.PI, (before.playerHeading * 180) / Math.PI)
  const bearingDelta = degreeDiff(after.bearing, before.bearing)
  assert(Math.abs(headingDelta) > 8, `A key did not rotate player heading enough for minimap orientation verification: ${JSON.stringify({ before, after, headingDelta })}`)
  assert(Math.abs(bearingDelta) > 8, `Minimap bearing did not update after player heading changed: ${JSON.stringify({ before, after, headingDelta, bearingDelta })}`)
  assert(after.headingUp === 'true' && after.northZ === 'positive' && after.headingUpProjection === true && after.projection?.forwardDy < -0.8, `Turned minimap is vertically flipped: ${JSON.stringify(after)}`)
  return [before, after]
}

async function placePlayerForMinimap(page, point) {
  await page.evaluate(point => {
    window.dispatchEvent(new CustomEvent('realcity:debug-place-player', {
      detail: { ...point, heading: Math.PI, pulse: 'verify minimap GPS cardinals' },
    }))
  }, point)
  await page.waitForFunction(point => {
    const player = window.__REALCITY_STORE__?.getState()?.player
    return player && Math.hypot(player.x - point.x, player.z - point.z) < 1
  }, point, { timeout: 8000 })
  await page.waitForFunction(() => {
    const text = document.querySelector('.minimap-gps')?.textContent || ''
    return /GPS/.test(text) && /[NS]/.test(text) && /[EW]/.test(text)
  }, null, { timeout: 8000 })
  return page.evaluate(() => ({
    text: document.querySelector('.minimap-gps')?.textContent || '',
    runtime: window.__REALCITY_MINIMAP__ || null,
  }))
}

async function verifyMinimapCardinals(page) {
  const southWest = await placePlayerForMinimap(page, { x: -180, z: -180 })
  assert(/S/.test(southWest.text) && /W/.test(southWest.text), `South-west GPS coordinate labels are inverted: ${JSON.stringify(southWest)}`)
  const northEast = await placePlayerForMinimap(page, { x: 180, z: 180 })
  assert(/N/.test(northEast.text) && /E/.test(northEast.text), `North-east GPS coordinate labels are inverted: ${JSON.stringify(northEast)}`)
  await placePlayerForMinimap(page, { x: 0, z: 40 })
  return { southWest: southWest.text, northEast: northEast.text }
}

async function verifyCrosswalkLaneHold(page) {
  const setup = await page.evaluate(() => {
    const store = window.__REALCITY_STORE__?.getState()
    const debug = window.__REALCITY_NPC_DEBUG__
    const originalDay = store?.day || 1
    const originalTime = store?.timeMinutes || 0
    const candidate = (store?.pedestrianSamples || []).find(sample => !sample.taxiPhase && !sample.talkPartnerId) || (store?.pedestrianSamples || [])[0]
    const result = debug?.startCrosswalkWait?.({ id: candidate?.id || 'npc_0', axis: 'x', speedScale: 8 })
    if (!result) return null
    return {
      ...result,
      originalDay,
      originalTime,
      greenTime: result.roadAxis === 'x' ? 0.1 : 0.55,
      redTime: result.roadAxis === 'x' ? 0.55 : 0.1,
    }
  })
  assert(setup?.id && Number.isFinite(setup.roadWidth), `Could not set up crosswalk lane-hold verification: ${JSON.stringify(setup)}`)
  await holdClock(page, setup.greenTime, setup.originalDay)
  await page.waitForFunction(setup => {
    const sample = (window.__REALCITY_STORE__?.getState()?.pedestrianSamples || []).find(item => item.id === setup.id)
    return sample?.crosswalkWaiting && sample.routeMode === 'crosswalk-waiting'
  }, setup, { timeout: 10000 })
  await holdClock(page, setup.redTime, setup.originalDay)
  await page.waitForFunction(setup => {
    const sample = (window.__REALCITY_STORE__?.getState()?.pedestrianSamples || []).find(item => item.id === setup.id)
    if (!sample) return false
    const moved = Math.hypot(sample.x - setup.approach.x, sample.z - setup.approach.z)
    const enteredDriveLane = setup.roadAxis === 'x'
      ? Math.abs(sample.z - setup.roadCenter) < setup.roadWidth / 2 - 0.2
      : Math.abs(sample.x - setup.roadCenter) < setup.roadWidth / 2 - 0.2
    return !sample.crosswalkWaiting &&
      sample.routeMode === 'crosswalk-crossing' &&
      moved > 0.8 &&
      enteredDriveLane &&
      sample.crosswalkLaneHold &&
      sample.crosswalkCorridorMeters > 0 &&
      /holding .* crosswalk corridor/i.test(sample.routeStatus || '')
  }, setup, { timeout: 18000 })
  const result = await page.evaluate(setup => {
    const sample = (window.__REALCITY_STORE__?.getState()?.pedestrianSamples || []).find(item => item.id === setup.id)
    return {
      roadName: setup.roadName,
      roadAxis: setup.roadAxis,
      movedFromApproach: sample ? Number(Math.hypot(sample.x - setup.approach.x, sample.z - setup.approach.z).toFixed(2)) : 0,
      sample,
    }
  }, setup)
  await clearClock(page)
  return result
}

async function main() {
  const server = startDevServer()
  let browser
  try {
    await waitForServer()
    const executablePath = findBrowserExecutable()
    assert(executablePath, 'Chrome or Edge executable was not found')
    browser = await chromium.launch({
      executablePath,
      headless: true,
      args: ['--ignore-gpu-blocklist', '--enable-webgl', '--use-gl=swiftshader'],
    })
    const page = await browser.newPage({ viewport: { width: 1440, height: 920 }, deviceScaleFactor: 1 })
    await page.goto(baseUrl, { waitUntil: 'domcontentloaded', timeout: 45000 })
    await page.locator('canvas').first().waitFor({ state: 'visible', timeout: 30000 })
    await page.waitForTimeout(2500)

    const roadRendering = await verifyRoadRendering(page)
    const minimapOrientation = await verifyMinimapOrientation(page)
    const minimapCardinals = await verifyMinimapCardinals(page)
    const crosswalkLaneHold = await verifyCrosswalkLaneHold(page)

    console.log(JSON.stringify({
      ok: true,
      roadRendering,
      minimapOrientation,
      minimapCardinals,
      crosswalkLaneHold: {
        roadName: crosswalkLaneHold.roadName,
        roadAxis: crosswalkLaneHold.roadAxis,
        movedFromApproach: crosswalkLaneHold.movedFromApproach,
        routeMode: crosswalkLaneHold.sample?.routeMode,
        routeStatus: crosswalkLaneHold.sample?.routeStatus,
        crosswalkLaneHold: crosswalkLaneHold.sample?.crosswalkLaneHold,
        crosswalkCorridorMeters: crosswalkLaneHold.sample?.crosswalkCorridorMeters,
      },
    }, null, 2))
  } finally {
    if (browser) await browser.close()
    stopDevServer(server.child)
  }
}

main().catch(error => {
  console.error(error)
  process.exit(1)
})
