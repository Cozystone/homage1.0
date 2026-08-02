import { Bloom, BrightnessContrast, EffectComposer, HueSaturation, SMAA, ToneMapping, Vignette } from '@react-three/postprocessing'
import { ToneMappingMode } from 'postprocessing'

export default function PostFX() {
  return (
    <EffectComposer multisampling={0} enableNormalPass={false}>
      <SMAA />
      <Bloom luminanceThreshold={0.62} luminanceSmoothing={0.1} intensity={0.22} radius={0.48} mipmapBlur levels={3} />
      <HueSaturation saturation={0.07} hue={0} />
      <BrightnessContrast brightness={0.015} contrast={0.025} />
      <Vignette offset={0.48} darkness={0.08} />
      <ToneMapping mode={ToneMappingMode.ACES_FILMIC} />
    </EffectComposer>
  )
}
