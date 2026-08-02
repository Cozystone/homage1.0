import * as THREE from 'three'

export const PROCEDURAL_TEXTURE_CATALOG = [
  'cloud-vapor',
  'city-fabric',
  'skin-pores',
  'hair-strands',
  'vehicle-paint',
  'rubber-tread',
  'brushed-metal',
  'glass-smudge',
  'paper-plate',
]

function createRng(seed = 1) {
  let state = seed >>> 0
  return () => {
    state = (state * 1664525 + 1013904223) >>> 0
    return state / 4294967296
  }
}

function clampByte(value) {
  return Math.max(0, Math.min(255, Math.round(value)))
}

function makeCanvas(size) {
  const canvas = document.createElement('canvas')
  canvas.width = size
  canvas.height = size
  return canvas
}

function drawFineNoise(ctx, size, rng, base, spread, alpha = 255) {
  const image = ctx.createImageData(size, size)
  for (let i = 0; i < image.data.length; i += 4) {
    const grain = (rng() - 0.5) * spread
    const value = clampByte(base + grain)
    image.data[i] = value
    image.data[i + 1] = value
    image.data[i + 2] = value
    image.data[i + 3] = alpha
  }
  ctx.putImageData(image, 0, 0)
}

function strokeRandomLines(ctx, size, rng, count, color, vertical = false, alpha = 0.16) {
  ctx.save()
  ctx.globalAlpha = alpha
  ctx.strokeStyle = color
  for (let i = 0; i < count; i += 1) {
    ctx.lineWidth = 0.45 + rng() * 1.6
    ctx.beginPath()
    if (vertical) {
      const x = rng() * size
      ctx.moveTo(x, rng() * size * 0.16)
      ctx.lineTo(x + (rng() - 0.5) * 5, size - rng() * size * 0.16)
    } else {
      const y = rng() * size
      ctx.moveTo(rng() * size * 0.12, y)
      ctx.lineTo(size - rng() * size * 0.12, y + (rng() - 0.5) * 5)
    }
    ctx.stroke()
  }
  ctx.restore()
}

function drawSoftCloud(ctx, size, rng) {
  drawFineNoise(ctx, size, rng, 238, 20, 240)
  strokeRandomLines(ctx, size, rng, 120, '#ffffff', false, 0.11)
  strokeRandomLines(ctx, size, rng, 65, '#cfdbe5', false, 0.08)
  ctx.save()
  ctx.globalAlpha = 0.1
  ctx.fillStyle = '#e4edf4'
  for (let y = 0; y < size; y += 12) {
    const wave = Math.sin(y * 0.13) * 4
    ctx.fillRect(wave, y + rng() * 4, size, 2 + rng() * 2)
  }
  ctx.restore()
}

function drawPattern(kind, ctx, size, rng) {
  if (kind === 'cloud-vapor') {
    drawSoftCloud(ctx, size, rng)
    return
  }

  if (kind === 'rubber-tread') {
    drawFineNoise(ctx, size, rng, 74, 56)
    ctx.strokeStyle = 'rgba(18,20,22,0.45)'
    ctx.lineWidth = 3
    for (let y = -size; y < size * 2; y += 18) {
      ctx.beginPath()
      ctx.moveTo(0, y)
      ctx.lineTo(size, y + size * 0.45)
      ctx.stroke()
    }
    return
  }

  if (kind === 'brushed-metal') {
    drawFineNoise(ctx, size, rng, 186, 42)
    strokeRandomLines(ctx, size, rng, 120, '#ffffff', false, 0.16)
    strokeRandomLines(ctx, size, rng, 90, '#4c555e', false, 0.12)
    return
  }

  if (kind === 'glass-smudge') {
    drawFineNoise(ctx, size, rng, 220, 26, 148)
    strokeRandomLines(ctx, size, rng, 26, '#ffffff', true, 0.12)
    strokeRandomLines(ctx, size, rng, 18, '#9ec9d8', false, 0.14)
    return
  }

  if (kind === 'skin-pores') {
    drawFineNoise(ctx, size, rng, 222, 20)
    for (let i = 0; i < 380; i += 1) {
      ctx.fillStyle = `rgba(120,78,58,${0.03 + rng() * 0.045})`
      ctx.beginPath()
      ctx.arc(rng() * size, rng() * size, 0.35 + rng() * 0.95, 0, Math.PI * 2)
      ctx.fill()
    }
    return
  }

  if (kind === 'hair-strands') {
    drawFineNoise(ctx, size, rng, 188, 58)
    strokeRandomLines(ctx, size, rng, 160, '#ffffff', true, 0.1)
    strokeRandomLines(ctx, size, rng, 130, '#222222', true, 0.14)
    return
  }

  if (kind === 'vehicle-paint') {
    drawFineNoise(ctx, size, rng, 235, 18)
    strokeRandomLines(ctx, size, rng, 28, '#ffffff', false, 0.18)
    for (let i = 0; i < 80; i += 1) {
      ctx.fillStyle = `rgba(255,255,255,${0.03 + rng() * 0.08})`
      ctx.fillRect(rng() * size, rng() * size, 0.8 + rng() * 3, 0.4 + rng() * 1.6)
    }
    return
  }

  if (kind === 'paper-plate') {
    drawFineNoise(ctx, size, rng, 236, 22)
    strokeRandomLines(ctx, size, rng, 40, '#c7c1ae', false, 0.14)
    return
  }

  drawFineNoise(ctx, size, rng, 212, 36)
  strokeRandomLines(ctx, size, rng, 80, '#ffffff', true, 0.11)
  strokeRandomLines(ctx, size, rng, 70, '#5c6570', false, 0.1)
}

export function makeProceduralTexture(kind, options = {}) {
  if (typeof document === 'undefined') return null
  const size = options.size || 128
  const canvas = makeCanvas(size)
  const ctx = canvas.getContext('2d')
  const seed = options.seed ?? (kind.length * 997)
  const rng = createRng(seed)
  drawPattern(kind, ctx, size, rng)

  const texture = new THREE.CanvasTexture(canvas)
  texture.colorSpace = THREE.SRGBColorSpace
  texture.wrapS = THREE.RepeatWrapping
  texture.wrapT = THREE.RepeatWrapping
  texture.repeat.set(options.repeatX || 1, options.repeatY || 1)
  texture.anisotropy = options.anisotropy || 6
  texture.needsUpdate = true
  return texture
}

export function exposeTextureCatalog() {
  if (typeof window === 'undefined' || !import.meta.env.DEV) return
  window.__REALCITY_TEXTURES__ = {
    procedural: true,
    classes: PROCEDURAL_TEXTURE_CATALOG,
  }
}
