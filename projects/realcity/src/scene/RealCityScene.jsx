import Atmosphere from './Atmosphere'
import CityScape from './CityScape'
import Vehicles from './Vehicles'
import Actors from './Actors'
import PlayerRig from './PlayerRig'
import MultiplayerPresence from './MultiplayerPresence'
import Cinematic from './Cinematic'
import Interiors from './Interiors'

export default function RealCityScene({ city }) {
  // Shadow casting/receiving is configured per mesh inside the owning components
  // (Atmosphere drives the shadow-casting sun; CityMeshes/UrbanDetails/Actors own their meshes),
  // so there is nothing to toggle safely at this composition level.
  return (
    <>
      <Atmosphere />
      {/* architecture + landscaping, remodelled from scratch — replaces CityMeshes + UrbanDetails
          (both kept on disk for instant rollback) */}
      <CityScape city={city} />
      {/* kerb-side parked fleet (restores the cars lost when UrbanDetails was unmounted;
          the moving agent-driven fleet still renders inside Actors/Traffic) */}
      <Vehicles city={city} />
      <Interiors city={city} />
      <Actors city={city} />
      <MultiplayerPresence />
      <PlayerRig city={city} />
      {/* The scene's single post stack (cinematic HDR grade). Replaces the old PostFX mount —
          keeping exactly one EffectComposer avoids double full-scene renders. */}
      <Cinematic />
    </>
  )
}
