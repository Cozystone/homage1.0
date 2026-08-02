# Realcity asset sourcing and rendering plan

## Current external asset library

- Character candidate: `public/models/kenney/animated-characters-1/`
- Source: Kenney Animated Characters 1 via OpenGameArt/Kenney
- Source URL: `https://opengameart.org/content/animated-characters-1`
- License in included `License.txt`: Creative Commons Zero, CC0

This pack includes an FBX model plus idle/run/jump animation files. It is stored in the repo as a clean CC0 candidate, but the active player remains the procedural animated character until the FBX rig can be retargeted and verified from multiple camera angles. In a browser check, the raw FBX import was not yet visually stable enough for the main playable character.

## Avatar library

- Stored VRM candidate: `public/models/polydancer.vrm`
- Source registry: Open Source Avatars by ToxSam
- Model source URL: `https://arweave.net/jPOg-G0MPH55ZQmamFhT9f8cHn-hjeAQ0mRO5gWeKMQ`
- License in registry metadata: CC0

The VRM is kept as a clean CC0 candidate for a future VRM retargeting pass. It is not used as the active player because the file does not provide baked locomotion clips, which makes it less convincing for immediate GTA-style movement.

## Sketchfab and Fab

Sketchfab is useful for visual research and hand-picked asset replacement, but automated download is not a good default for this repo because the official Download API requires user OAuth, temporary download links, and per-model license handling. For production-safe commits, prefer assets with permanent hosting and clear CC0 or project-compatible licenses.

Recommended workflow:

1. Browse Sketchfab/Fab for inspiration and candidates.
2. Keep a screenshot or source URL for each chosen model.
3. Verify the exact license at download time.
4. Import only optimized glTF/GLB assets under `public/models`.
5. Record source, author, license, and modifications in this document.

## Unity AI

Unity AI is currently a Unity Editor/Unity Cloud centered workflow. It is useful for prototyping assets, behaviors, and Sentis-driven Unity runtime features, but it cannot be directly invoked inside this Three.js/Vite app unless the Unity Editor, Unity project packages, and export pipeline are installed.

On this machine, Unity Hub/Editor was not found during the local check, so the app keeps the runtime in Three.js/R3F. If Unity is added later, the clean integration point is:

1. Use Unity AI/Muse-style tools to generate or iterate assets in a Unity project.
2. Export final meshes as optimized glTF/GLB or VRM.
3. Import those assets into `public/models`.
4. Keep AI-generated asset metadata and license notes alongside the model entry here.

## Rendering direction

Realcity stays procedural at the city scale and uses external assets only where they add detail without compromising frame rate. The high-quality target is:

- Dense street furniture: crosswalks, lights, signals, benches, planters.
- Better vehicle silhouettes: cabins, wheels, headlights, taillights.
- Rooftop utility detail on tall buildings.
- Procedural massing now separates towers, offices, apartments, and houses
  with distinct profiles, roofs, wings, podiums, balconies, porches, garages,
  chimneys, and antennas before any external model replacement.
- Time-of-day lighting, moving cloud layer, fog, bloom, and ACES tone mapping.
- CC0 character assets where permanent download links and browser loading are reliable.
