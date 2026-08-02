import { createWriteStream, existsSync, mkdirSync, writeFileSync } from 'node:fs'
import { pipeline } from 'node:stream/promises'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

const __dirname = path.dirname(fileURLToPath(import.meta.url))
const root = path.resolve(__dirname, '..')
const targetRoot = path.join(root, 'public', 'assets', 'sketchfab')
const token = process.env.SKETCHFAB_TOKEN

const candidates = [
  {
    slug: 'low-poly-human',
    uid: 'ac9d4b28c49c45cb83f64385affe5acd',
    title: 'Low Poly human',
    author: 'Michael Gordon',
    authorHandle: 'Phyko.Gordo',
    sourceUrl: 'https://sketchfab.com/3d-models/low-poly-human-ac9d4b28c49c45cb83f64385affe5acd',
    license: 'CC Attribution',
    usage: 'NPC prototype replacement, after rig/scale validation',
  },
  {
    slug: 'taxi-low-poly',
    uid: 'c0165f18adf846a48ad803fc8f4d0f87',
    title: 'Taxi Low Poly',
    author: 'TheJester',
    authorHandle: 'The_Jester',
    sourceUrl: 'https://sketchfab.com/3d-models/taxi-low-poly-c0165f18adf846a48ad803fc8f4d0f87',
    license: 'CC Attribution',
    usage: 'Taxi mesh reference or optional taxi model replacement',
  },
  {
    slug: 'low-poly-city-buildings',
    uid: 'e0209ac5bb684d2d85e5ade96c92d2ff',
    title: 'Low-poly City Buildings',
    author: 'smooth998',
    authorHandle: 'smooth998',
    sourceUrl: 'https://sketchfab.com/3d-models/low-poly-city-buildings-e0209ac5bb684d2d85e5ade96c92d2ff',
    license: 'CC Attribution',
    usage: 'Background building kit and skyline density reference',
  },
  {
    slug: 'low-poly-detailed-building',
    uid: 'fec8960da9694c9e92b84bfeb9b50059',
    title: 'Low-Poly detailed building',
    author: 'Karim.Fares',
    authorHandle: 'Karim.Fares',
    sourceUrl: 'https://sketchfab.com/3d-models/low-poly-detailed-building-fec8960da9694c9e92b84bfeb9b50059',
    license: 'CC Attribution',
    usage: 'Photo-scanned facade detail reference for realistic mid-distance blocks',
  },
  {
    slug: 'modular-gameready-lowpoly-realistic-building',
    uid: '78f82fe06d0b4ca193280584b5710af6',
    title: 'Modular Gameready LowPoly Realistic Building',
    author: 'abhayexe',
    authorHandle: 'abhayexe',
    sourceUrl: 'https://sketchfab.com/3d-models/modular-gameready-lowpoly-realistic-building-78f82fe06d0b4ca193280584b5710af6',
    license: 'CC Attribution',
    usage: 'Modular landmark/facade replacement candidate',
  },
]

function selectedAssets() {
  const wanted = process.argv.slice(2)
  if (!wanted.length) return candidates
  const set = new Set(wanted)
  return candidates.filter(candidate => set.has(candidate.slug) || set.has(candidate.uid))
}

async function requestDownload(candidate) {
  const response = await fetch(`https://api.sketchfab.com/v3/models/${candidate.uid}/download`, {
    headers: { Authorization: `Bearer ${token}` },
  })
  if (!response.ok) {
    throw new Error(`${candidate.slug}: Sketchfab download request failed with ${response.status}`)
  }
  const data = await response.json()
  const gltf = data.gltf || data.glb
  if (!gltf?.url) throw new Error(`${candidate.slug}: no glTF/GLB archive URL returned`)
  return gltf.url
}

async function downloadArchive(candidate, url) {
  const folder = path.join(targetRoot, candidate.slug)
  mkdirSync(folder, { recursive: true })
  const archivePath = path.join(folder, `${candidate.slug}.zip`)
  const response = await fetch(url)
  if (!response.ok || !response.body) {
    throw new Error(`${candidate.slug}: archive download failed with ${response.status}`)
  }
  await pipeline(response.body, createWriteStream(archivePath))
  writeFileSync(path.join(folder, 'ATTRIBUTION.json'), JSON.stringify(candidate, null, 2))
  return archivePath
}

async function main() {
  mkdirSync(targetRoot, { recursive: true })
  writeFileSync(path.join(targetRoot, 'asset-candidates.json'), JSON.stringify(candidates, null, 2))

  if (!token) {
    console.log('Wrote asset candidate manifest.')
    console.log('Set SKETCHFAB_TOKEN to download CC Attribution glTF archives from Sketchfab.')
    return
  }

  for (const candidate of selectedAssets()) {
    const archiveUrl = await requestDownload(candidate)
    const archivePath = await downloadArchive(candidate, archiveUrl)
    console.log(`${candidate.slug}: ${archivePath}`)
  }

  if (existsSync(path.join(targetRoot, 'asset-candidates.json'))) {
    console.log(`Attribution manifest: ${path.join(targetRoot, 'asset-candidates.json')}`)
  }
}

main().catch(error => {
  console.error(error)
  process.exit(1)
})
