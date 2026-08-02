# External Procedural City And Human Sources

This project keeps external reference repositories in `.external/` only while
developing. That folder is ignored by Git and is not shipped with RealCity.

## MakeHuman assets

- Source: https://github.com/makehumancommunity/makehuman-assets
- License status checked: the repository README states bundled MakeHuman assets
  are released under Creative Commons CC0 universal, with historical AGPL/GPL
  alternatives.
- Current use: RealCity uses a MakeHuman-style parametric digital-human rig in
  runtime code, not copied MakeHuman source code. Actual MakeHuman mesh assets
  can replace the procedural rig later through a GLB export/import pipeline.
- Note: the asset repository uses Git LFS. The local checkout did not fully
  materialize meshes because the remote LFS quota was exceeded, so this commit
  does not include binary MakeHuman assets.

## magnificus/Procedural-Cities

- Source: https://github.com/magnificus/Procedural-Cities
- License status checked: MIT license, copyright Tobias Elinder 2017.
- Current use: RealCity ports the compatible ideas, not Unreal-specific runtime
  code: noise-weighted road growth, heatmap/density pressure, block subdivision
  pressure, sidewalk decoration planning, and explicit source metadata.
- Implementation files: `src/engine/proceduralCityRules.js` and
  `src/engine/cityEngine.js`.

## phiresky/procedural-cities

- Source: https://github.com/phiresky/procedural-cities
- License status checked: AGPL v3.
- Current use: concept-only reference for L-system/global-goal/local-constraint
  road planning. RealCity does not copy or import AGPL implementation code.

## aljanue/Procedural-City-Blender-Addon

- Source: https://github.com/aljanue/Procedural-City-Blender-Addon
- License status checked: no explicit license was visible on GitHub.
- Current use: concept-only reference for adjustable building density and vehicle
  path animation controls. RealCity does not copy or import its Python code or
  bundled OBJ assets.
