# Sketchfab Asset Candidates

Sketchfab is allowed for RealCity, but every imported model must be
downloadable and license-compliant. The current rule is: use only models with a
clear download button and compatible attribution terms, store attribution beside
the archive, then optimize before using it in the runtime scene.

## Download Pipeline

- Candidate metadata lives in `scripts/fetch-sketchfab-assets.mjs`.
- Run `npm run assets:sketchfab` to write
  `public/assets/sketchfab/asset-candidates.json`.
- Set `SKETCHFAB_TOKEN` before downloading archives. Sketchfab's Download API
  requires authenticated requests before it returns temporary glTF archive URLs.
- Downloaded archives are written under `public/assets/sketchfab/<slug>/` with
  `ATTRIBUTION.json`.
- Archives should be unpacked and optimized outside the render path before a
  model is promoted into the actual city.

## Shortlist

| Use | Candidate | Author | License | Why |
| --- | --- | --- | --- | --- |
| NPC prototype | Low Poly human | Michael Gordon / Phyko.Gordo | CC Attribution | Very small character mesh, useful as the first replacement for capsule NPCs. |
| Taxi | Taxi Low Poly | TheJester / The_Jester | CC Attribution | Distinct taxi mesh candidate for replacing the procedural taxi boxes. |
| Building kit | Low-poly City Buildings | smooth998 | CC Attribution | Many low-poly city buildings suitable for skyline/background density. |
| Facade detail | Low-Poly detailed building | Karim.Fares | CC Attribution | Photo-scanned building candidate for realistic facade reference. |
| Modular block | Modular Gameready LowPoly Realistic Building | abhayexe | CC Attribution | More realistic modular building candidate for landmarks or repeated blocks. |

## Runtime Criteria

- Keep first-pass imported NPCs under roughly 2k triangles per visible character
  or use instancing/LOD.
- Keep first-pass vehicles under roughly 10k triangles for moving traffic; use
  higher-detail versions only for nearby parked cars or taxis.
- Use glTF/GLB with PBR materials, compressed textures, and real-world scale.
- Add attribution in any public release notes or in-app credits before shipping
  imported assets.
