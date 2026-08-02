import { existsSync, mkdirSync, writeFileSync } from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'
import { chromium } from 'playwright-core'

const __dirname = path.dirname(fileURLToPath(import.meta.url))
const root = path.resolve(__dirname, '..')
const artifactsDir = path.join(root, '.verification')
const productionUrl = process.env.REALCITY_PRODUCTION_URL || 'https://realcity.vercel.app'
const BROKEN_TEXT_PATTERN = /[�源뚯앹몃곕뺥吏紐媛醫蹂諛濡湲鍮]|[?]{2,}/u

function assert(condition, message) {
  if (!condition) throw new Error(message)
}

function assertReadableText(label, text) {
  assert(!BROKEN_TEXT_PATTERN.test(String(text || '')), `${label} contains mojibake text: ${text}`)
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

function isLocalOnlyRequest(url) {
  try {
    const parsed = new URL(url)
    if (['localhost', '127.0.0.1', '0.0.0.0'].includes(parsed.hostname)) return true
    return /\/ollama(?:\/|$)|\/ollama\/api\/generate/i.test(parsed.pathname)
  } catch {
    return /localhost|127\.0\.0\.1|0\.0\.0\.0|\/ollama/i.test(String(url))
  }
}

async function inspectCanvas(page) {
  const canvases = await page.evaluate(() => Array.from(document.querySelectorAll('canvas')).map((canvas, index) => {
    const rect = canvas.getBoundingClientRect()
    let dataUrlLength = 0
    let sampleError = null
    try {
      dataUrlLength = canvas.toDataURL('image/png').length
    } catch (error) {
      sampleError = error instanceof Error ? error.message : String(error)
    }
    return {
      index,
      width: canvas.width,
      height: canvas.height,
      clientWidth: Math.round(rect.width),
      clientHeight: Math.round(rect.height),
      dataUrlLength,
      sampleError,
    }
  }))

  const largest = [...canvases].sort((a, b) => (b.width * b.height) - (a.width * a.height))[0]
  assert(largest, 'No production canvas was rendered')
  assert(largest.width >= 900 && largest.height >= 560, `Production WebGL canvas is too small: ${largest.width}x${largest.height}`)
  assert(!largest.sampleError, `Production canvas pixel sample failed: ${largest.sampleError}`)
  assert(largest.dataUrlLength > 18000, `Production canvas appears blank: data URL length ${largest.dataUrlLength}`)
  return { canvases, largest }
}

async function maybeTriggerNpcRequest(page) {
  await page.keyboard.press('KeyE')
  const panel = page.locator('.interaction-panel textarea')
  try {
    await panel.waitFor({ state: 'visible', timeout: 8000 })
  } catch {
    return { opened: false, submitted: false }
  }

  await panel.fill('Where are you going now, and what is your schedule today?')
  await page.locator('.interaction-panel button[type="submit"]').click()
  await page.waitForTimeout(2500)
  const panelText = await page.locator('.interaction-panel').innerText({ timeout: 5000 }).catch(() => '')
  assertReadableText('Production NPC interaction panel', panelText)
  return {
    opened: true,
    submitted: true,
    panelText: panelText.split(/\r?\n/).slice(0, 8),
  }
}

async function inspectFullMapNpcPurpose(page) {
  const buttons = page.locator('.full-map-place-button')
  const placeCount = await buttons.count()
  const attempts = Math.max(1, Math.min(6, placeCount))
  const snapshots = []

  for (let index = 0; index < attempts; index += 1) {
    if (index > 0) await buttons.nth(index).click()
    const text = await page.locator('.full-map-place-card').innerText({ timeout: 5000 })
    const agentCount = await page.locator('.full-map-place-agent').count()
    snapshots.push(text.split(/\r?\n/).slice(0, 12))
    if (
      agentCount > 0 &&
      /walking|taxi|crosswalk|on-site|inbound/i.test(text) &&
      /arrived|~\d+ min/i.test(text)
    ) {
      assertReadableText('Production full map NPC purpose', text)
      return { agentCount, text: text.split(/\r?\n/).slice(0, 14) }
    }
  }

  throw new Error(`Production full map did not expose named NPC route purpose near any sampled place: ${JSON.stringify(snapshots)}`)
}

async function main() {
  mkdirSync(artifactsDir, { recursive: true })
  const executablePath = findBrowserExecutable()
  assert(executablePath, 'Chrome or Edge executable was not found for production verification')

  const consoleErrors = []
  const pageErrors = []
  const localOnlyRequests = []
  const failedRequests = []
  let browser

  try {
    browser = await chromium.launch({
      executablePath,
      headless: true,
      args: ['--ignore-gpu-blocklist', '--enable-webgl', '--use-gl=swiftshader'],
    })
    const page = await browser.newPage({
      viewport: { width: 1440, height: 920 },
      deviceScaleFactor: 1,
    })
    page.setDefaultTimeout(30000)

    page.on('console', message => {
      const text = message.text()
      if (message.type() === 'error' || /Unable to preventDefault inside passive event listener invocation/i.test(text)) consoleErrors.push(text)
    })
    page.on('pageerror', error => pageErrors.push(error.message))
    page.on('request', request => {
      const url = request.url()
      if (isLocalOnlyRequest(url)) localOnlyRequests.push(url)
    })
    page.on('requestfailed', request => {
      const url = request.url()
      if (!url.startsWith('data:')) failedRequests.push(`${request.failure()?.errorText || 'failed'} ${url}`)
    })

    const response = await page.goto(productionUrl, { waitUntil: 'domcontentloaded', timeout: 60000 })
    assert(response && response.status() >= 200 && response.status() < 400, `Production URL returned HTTP ${response?.status()}`)
    await page.waitForLoadState('networkidle', { timeout: 30000 }).catch(() => {})
    await page.locator('canvas').first().waitFor({ state: 'visible', timeout: 45000 })
    await page.locator('.prompt-stack').waitFor({ state: 'visible', timeout: 30000 })
    await page.waitForTimeout(3500)

    const canvas = await inspectCanvas(page)
    const promptText = await page.locator('.prompt-stack').innerText({ timeout: 5000 })
    assert(promptText.includes('Taxi') && promptText.includes('Map') && promptText.includes('Phone'), `Production context prompt is incomplete: ${promptText}`)
    assertReadableText('Production context prompt', promptText)
    assert(await page.locator('.agent-llm').count() === 1, 'Production Local LLM runtime card is missing')
    const llmMode = await page.locator('.agent-llm').getAttribute('data-llm-mode', { timeout: 5000 })
    const llmLive = await page.locator('.agent-llm').getAttribute('data-llm-live', { timeout: 5000 })
    const llmText = await page.locator('.agent-llm').innerText({ timeout: 5000 })
    assert(llmMode === 'production-fallback' && llmLive === 'false', `Production should expose local-Ollama fallback mode instead of pretending to be live: ${JSON.stringify({ llmMode, llmLive, llmText })}`)
    assert(/local llm|local only|vercel fallback/i.test(llmText), `Production LLM card is not readable: ${llmText}`)
    assertReadableText('Production LLM card', llmText)
    assert(await page.locator('.minimap-gps').count() === 1, 'Production minimap GPS overlay is missing')

    await page.locator('.map-shell').click()
    await page.locator('.full-map-panel').waitFor({ state: 'visible', timeout: 15000 })
    const mapText = await page.locator('.full-map-panel').innerText({ timeout: 5000 })
    assert(/live gps fix/i.test(mapText), `Production full map did not show a live GPS fix: ${mapText}`)
    assertReadableText('Production full map', mapText)
    assert(await page.locator('.full-map-player').count() === 1, 'Production full map did not render the player marker')
    assert(await page.locator('.full-map-controls').count() === 1, 'Production full map controls are missing')
    assert(await page.locator('.full-map-navigation-card').count() === 1, 'Production full map navigation card is missing')
    assert(await page.locator('.full-map-social-card[data-agent-social="true"]').count() === 1, 'Production full map NPC social card is missing')
    const socialCardText = await page.locator('.full-map-social-card').innerText({ timeout: 5000 })
    assert(/agent society|conversation|social traces|contacts/i.test(socialCardText), `Production full map social card is incomplete: ${socialCardText}`)
    assert(await page.locator('.full-map-social-agent').count() >= 1, `Production full map social card did not expose named NPC context: ${socialCardText}`)
    const navigationText = await page.locator('.full-map-navigation-card').innerText({ timeout: 5000 })
    assert(/live navigation/i.test(navigationText), `Production full map navigation card is incomplete: ${navigationText}`)
    assert(await page.locator('.full-map-place-card').count() === 1, 'Production full map place intel card is missing')
    const placeText = await page.locator('.full-map-place-card').innerText({ timeout: 5000 })
    assert(/place intel|access|distance|live/i.test(placeText), `Production full map place intel card is incomplete: ${placeText}`)
    assert(/inbound|on-site/i.test(placeText), `Production full map place rhythm is missing: ${placeText}`)
    assert(/direct cab dispatch|no NPC relay/i.test(placeText), `Production full map place card did not expose direct taxi dispatch: ${placeText}`)
    assert(await page.locator('.full-map-place-button').count() >= 6, 'Production full map nearby place directory is missing')
    assert(await page.locator('.full-map-place-taxi').count() === 1, 'Production full map direct taxi button is missing')
    assert(await page.locator('.full-map-place-pin').count() === 1, 'Production full map pin button is missing')
    const fullMapNpcPurpose = await inspectFullMapNpcPurpose(page)
    await page.locator('.full-map-place-button').nth(1).click()
    const zoomBeforeWheel = Number(await page.locator('.full-city-map').getAttribute('data-zoom', { timeout: 5000 }))
    await page.locator('.full-city-map').dispatchEvent('wheel', { deltaY: -160, bubbles: true, cancelable: true })
    await page.waitForFunction(previous => {
      const zoom = Number(document.querySelector('.full-city-map')?.getAttribute('data-zoom') || 0)
      return zoom > previous
    }, zoomBeforeWheel, { timeout: 5000 })
    const mapBox = await page.locator('.full-city-map').boundingBox()
    assert(mapBox, 'Production full map did not expose a scroll target')
    const zoomBeforePhysicalWheel = Number(await page.locator('.full-city-map').getAttribute('data-zoom', { timeout: 5000 }))
    await page.mouse.move(mapBox.x + mapBox.width * 0.5, mapBox.y + mapBox.height * 0.5)
    await page.mouse.wheel(0, -160)
    await page.waitForFunction(previous => {
      const zoom = Number(document.querySelector('.full-city-map')?.getAttribute('data-zoom') || 0)
      return zoom > previous
    }, zoomBeforePhysicalWheel, { timeout: 5000 })
    await page.locator('.full-map-place-pin').click()
    await page.waitForFunction(() => {
      const card = document.querySelector('.full-map-navigation-card')
      return card?.getAttribute('data-route-source') === 'map_place_pin' &&
        card.getAttribute('data-has-route') === 'true' &&
        document.querySelector('.full-map-route')
    }, null, { timeout: 10000 })
    const pinnedNavigationText = await page.locator('.full-map-navigation-card').innerText({ timeout: 5000 })
    assert(/pinned map route|remaining|lane-following/i.test(pinnedNavigationText), `Production map pin did not create a navigation route: ${pinnedNavigationText}`)
    const fullMapStats = {
      buildingFootprints: await page.locator('.full-map-buildings rect').count(),
      liveVehicles: await page.locator('.full-map-live-vehicles rect').count(),
      livePedestrians: await page.locator('.full-map-live-pedestrians circle').count(),
    }
    assert(fullMapStats.buildingFootprints > 20, 'Production full map building footprints are missing')
    assert(fullMapStats.liveVehicles > 0, 'Production full map live vehicles are missing')
    assert(fullMapStats.livePedestrians > 0, 'Production full map live NPC markers are missing')
    await page.locator('.full-map-header button').click()
    await page.locator('.full-map-panel').waitFor({ state: 'hidden', timeout: 10000 })

    await page.locator('.phone-toggle').click()
    await page.locator('.phone-device').waitFor({ state: 'visible', timeout: 15000 })
    await page.locator('.phone-tabs button[data-tab="messages"]').click()
    await page.locator('.phone-message-form input').fill('Where are you now, and can you meet me later?')
    await page.locator('.phone-message-form button[type="submit"]').click()
    await page.locator('.phone-bubbles p[data-llm-source^="fallback:"]').waitFor({ state: 'visible', timeout: 15000 })
    const phoneLlmBubbleSource = await page.locator('.phone-bubbles p[data-llm-source^="fallback:"]').getAttribute('data-llm-source', { timeout: 5000 })
    const phoneLlmBubbleText = await page.locator('.phone-bubbles p[data-llm-source^="fallback:"]').innerText({ timeout: 5000 })
    assert(phoneLlmBubbleSource === 'fallback:production-disabled', `Production RealPhone NPC message should disclose local-Ollama fallback source: ${JSON.stringify({ phoneLlmBubbleSource, phoneLlmBubbleText })}`)
    assert(/near|근처|RealPhone|message|위치|지금/i.test(phoneLlmBubbleText), `Production RealPhone NPC message fallback is not useful: ${phoneLlmBubbleText}`)
    assertReadableText('Production RealPhone LLM fallback message', phoneLlmBubbleText)
    await page.locator('.phone-tabs button[data-tab="taxi"]').click()
    const phoneTaxiText = await page.locator('.phone-device').innerText({ timeout: 5000 })
    assert(phoneTaxiText.includes('RealCity Taxi') && phoneTaxiText.includes('Direct cab dispatch'), `Production phone taxi UI is incomplete: ${phoneTaxiText}`)
    assert(phoneTaxiText.includes('no NPC relay') && phoneTaxiText.includes('no contact relay'), `Production phone taxi UI does not promise direct dispatch: ${phoneTaxiText}`)
    assertReadableText('Production phone taxi UI', phoneTaxiText)
    await page.locator('.phone-close').click()
    await page.locator('.phone-device').waitFor({ state: 'hidden', timeout: 10000 })

    const npcRequest = await maybeTriggerNpcRequest(page)
    const visibleText = await page.locator('body').innerText({ timeout: 5000 })
    assertReadableText('Production visible UI', visibleText)

    assert(localOnlyRequests.length === 0, `Production attempted local-only requests: ${localOnlyRequests.join(' | ')}`)
    assert(consoleErrors.length === 0, `Production console errors were reported: ${consoleErrors.join(' | ')}`)
    assert(pageErrors.length === 0, `Production page errors were reported: ${pageErrors.join(' | ')}`)

    const screenshotPath = path.join(artifactsDir, 'realcity-production-last-run.png')
    await page.screenshot({ path: screenshotPath, fullPage: false })
    const report = {
      checkedAt: new Date().toISOString(),
      url: productionUrl,
      browser: executablePath,
      canvas,
      promptText: promptText.split(/\r?\n/).slice(0, 8),
      map: {
        hasLiveGpsFix: /live gps fix/i.test(mapText),
        fullMapNpcPurpose,
        ...fullMapStats,
      },
      phoneTaxi: phoneTaxiText.split(/\r?\n/).slice(0, 14),
      phoneLlmBubbleSource,
      phoneLlmBubbleText,
      npcRequest,
      localOnlyRequests,
      failedRequests,
      consoleErrors,
      pageErrors,
      screenshotPath,
    }
    writeFileSync(path.join(artifactsDir, 'realcity-production-last-run.json'), JSON.stringify(report, null, 2))
    console.log(JSON.stringify({
      ok: true,
      url: productionUrl,
      canvas: canvas.largest,
      npcRequest,
      localOnlyRequestCount: localOnlyRequests.length,
      screenshotPath,
    }, null, 2))
  } finally {
    if (browser) await browser.close()
  }
}

main().catch(error => {
  console.error(error)
  process.exit(1)
})
