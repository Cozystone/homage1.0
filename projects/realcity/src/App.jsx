import { Suspense, useEffect, useMemo } from 'react'
import { Canvas } from '@react-three/fiber'
import * as THREE from 'three'
import { createRealCity } from './engine/cityEngine'
import { currentInterior, resolveBuildingCollision } from './engine/collision'
import './engine/citySystems'
import RealCityScene from './scene/RealCityScene'
import HUD from './ui/HUD'

export default function App() {
  const city = useMemo(() => createRealCity(), [])

  useEffect(() => {
    // always exposed: the CT world-system modules (citySystems.js) self-drive off this handle
    window.__REALCITY_CITY__ = city
    window.__REALCITY_COLLISION__ = { currentInterior, resolveBuildingCollision }
  }, [city])

  return (
    <main className="app">
      <Canvas
        shadows="soft"
        dpr={1}
        performance={{ min: 0.35 }}
        camera={{ fov: 68, near: 0.25, far: 3600, position: [18, 18, 34] }}
        gl={{
          antialias: false,
          alpha: false,
          depth: true,
          stencil: false,
          precision: 'highp',
          powerPreference: 'high-performance',
          toneMapping: THREE.ACESFilmicToneMapping,
          toneMappingExposure: 0.84,
          outputColorSpace: THREE.SRGBColorSpace,
          logarithmicDepthBuffer: true,
        }}
      >
        <Suspense fallback={null}>
          <RealCityScene city={city} />
        </Suspense>
      </Canvas>
      <HUD city={city} />
    </main>
  )
}
