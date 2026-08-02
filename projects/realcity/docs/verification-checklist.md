# RealCity Verification Checklist

This checklist tracks the full playable-city target. The automated local
harness is `npm run verify:realcity`, and production smoke coverage is
`npm run verify:production`; manual items remain here so the final completion
audit has a clear finish line.

## Automated Now

- Build: `npm run build` must complete without Vite or Rollup errors.
- Browser render: the main WebGL canvas must appear at desktop size and pass a
  canvas pixel/data check.
- Full map: clicking the circular minimap must open a city-wide map with the
  current player marker and landmark labels; map coordinate conversion and
  player state updates must sanitize `NaN` so MapLibre never receives invalid
  `LngLat` centers, and wheel zoom/scroll must not emit passive-listener
  `preventDefault` console warnings.
- Full map navigation: the map exposes a live navigation card, route start/end
  markers, progress marker, remaining distance, and lane-following point count
  whenever a taxi/walking route is active.
- Control model: `A` rotates avatar heading without translating the avatar.
- Free-look model: arrow keys change only temporary camera view, and the view
  returns behind the avatar after release.
- Movement: `W` moves the avatar forward in the avatar-facing direction.
- NPC access: `E` opens a nearby NPC interaction panel.
- Local LLM route: NPC greeting and request planning call the configured local
  provider when Ollama is available, currently `ollama:dolphin3:latest`, and
  expose live/fallback telemetry in the HUD and mission state.
- RealPhone UI: the lower-right phone opens, exposes message/contact/social/music
  apps, shows callable NPC contacts, has a music app entry point, and rejects
  mojibake/broken visible text in those phone surfaces.
- Multiplayer: the join panel exposes a room/player identity and invite URL,
  the server API synchronizes another player, invite links auto-join rooms, and
  remote peers render as smoothed shared-humanoid avatars with nameplates.
- RealPhone Taxi: the Taxi app and plain phone-message taxi intent both dispatch
  a cab directly as a `player_taxi` mission with no NPC/contact relay.
- Phone social layer: the harness sends a message, places a call, and sends a
  route-like request through a contact; the request must open an NPC interaction
  and produce a mission owned by that contacted NPC.
- Street norms: every road has a name, landmarks/buildings have road-name
  addresses, trees do not overlap road reserves, and social norm metadata exists
  for pedestrian/traffic/address rules; NPCs wait at curb approaches while the
  crossed vehicle axis has green/yellow and enter the crosswalk only when that
  vehicle axis turns red.
- Traffic signal law: main intersections use a SUMO-inspired actuated
  `tlLogic` sequence with detector-pressure green durations, protected green,
  yellow clearance, all-red clearance, stop-bar vehicle stopping, and protected
  pedestrian WALK instead of allowing ambiguous simultaneous starts.
- SUMO link model: the signal program must expose vehicle links, separate
  pedestrian crossing links, no-start clearance phases, countdown metadata,
  stop bars, and per-intersection controller records.
- SUMO movement links: left-turning traffic must expose permissive `g` and
  protected `G` priority telemetry, with a late protected-left window that
  prevents new pedestrian starts.
- SUMO detector/gap model: each main intersection must expose four detector
  records and an active pressure policy with computed green seconds; NPC
  crosswalk samples must identify traffic-light, priority-zebra, or
  uncontrolled-gap control with conservative vehicle-gap metadata.
- Shared mobility and curb policy: the city exposes GBFS-shaped station
  information/status, vehicle types, geofencing zones, SmartCities-style curb
  and traffic-flow data models, and GATSim-style disruption policies that can
  influence agent route/mode choices.
- Shared mobility rendering: GBFS docks and SmartCities curb zones must appear
  as physical painted pads/racks/kiosks/bike/scooter props, and NPC
  `shared-bike`/`shared-scooter` routes must expose visible ride props on the
  digital-human rig.
- Procedural 3D Tiles: the city exposes a 3D Tiles 1.1-style tileset root,
  child bounding volumes, procedural content URIs, terrain/road/building content
  metadata schema, and runtime near/mid/far LOD telemetry for visible city tiles.
- Pedestrian signals: crosswalk approaches expose visible curb-side WALK/WAIT
  signal heads, and their WALK state is coupled to the crossed vehicle axis
  being red.
- Traffic visual reactions: vehicle samples expose brake-light intensity, amber
  caution/turn signals, and driver reaction text when yielding, stopping, or
  following another car.
- Turn-lane behavior: roads expose right-hand turn-lane policy and vehicles
  publish straight/left/right intent, turn signal distance, turn decision
  distance, and active left/right signal-side telemetry.
- Turn-lane rendering: main intersections render visible left-turn pocket
  paint, hooked turn arrows, right-turn yield triangles, and chevrons tied to
  the same `laneModel`/`turnIntent` telemetry.
- Turn-lane conflict behavior: active left/right turn samples expose SUMO/GATSim
  priority rules, distinct turn slowdown intensity, and gap/crosswalk conflict
  checks instead of behaving exactly like through traffic.
- Turn-lane steering arcs: accepted non-taxi turns expose active or recently
  completed cubic Bezier steering telemetry, including from-road/to-road names,
  radius, curve length, and road-state transfer after the turn.
- Taxi route smoothing: dispatch paths, ride paths, NPC self-called taxis, and
  cruising taxi loops expose Bezier corner-smoothing metadata and enough curve
  samples to prove they are not hard 90-degree corner paths.
- Address routing: the city exposes a routable address book, and the harness
  asks an NPC for a taxi ride to a far procedural road-name address.
- Place meaning: every landmark exposes a gameplay role, address, access plan,
  and full-map place intel card with nearby activity counts and selectable
  place directory entries.
- NPC identity and autonomy metadata: all NPCs must expose unique names,
  persona signatures, appearance signatures, jobs, speech styles, home/work/
  third-place schedule data, needs, memories, and relationship state.
- NPC cognition architecture: runtime NPC samples expose a generative-agent
  inspired memory stream, recency/importance/relevance retrieval, reflection,
  utility-scored policy selection, behavior-tree execution contract, and local
  LLM prompt context grounded in executable city affordances.
- NPC autonomous LLM: when local Ollama is available, at least one NPC can run
  a local `npc-autonomy` thought outside a direct player request, update its
  current intent/memory, choose an executable city action, run that action
  through the simulator, and publish live city/pedestrian telemetry for the
  thought, action, outcome, target, latency, provider, and model.
- NPC mobility-aware LLM: the autonomy prompt must include live GBFS dock
  availability, SmartCities curb/geofence state, TrafficFlowObserved context,
  and GATSim disruption data; a forced verification run executes
  `use_shared_bike` as a real `shared-bike` route with dock telemetry, GBFS
  pickup inventory depletion, return-slot reservation, visible ride prop
  telemetry, and completed return inventory updates.
- NPC-to-NPC local LLM: when local Ollama is available, two NPCs can generate a
  short social exchange through `npc-social-conversation`, store per-person
  dialogue lines and memories, update relationship state, and publish a
  `local-llm-social` city event with latency/model telemetry.
- Need-driven autonomy: NPC hunger, energy, and social need thresholds can
  trigger a short real detour to a suitable cafe, park, retail, or social place;
  the detour must appear in pedestrian samples, city events, nearby agent card,
  and cognition metadata instead of remaining as invisible flavor text.
- NPC social life and reactions: the harness verifies live NPC-to-NPC
  conversation events, relationship memory, and a deterministic nearby NPC
  glance/turn reaction that also surfaces in the city pulse.
- NPC social visual cues: active conversations expose partner-facing body turns,
  speech cues, phone/hand gesture props, and runtime gesture metadata.
- Human direction readability: NPC render metadata exposes front cues
  (eye whites, pupils, nose bridge, mouth, badge/lapels), back cues
  (hairBack, vertical back seam, shoulder straps, backpack silhouette), and
  gait cues so street-camera direction is readable.
- Daily routine: the harness jumps city time through morning commute, workday,
  evening third-place time, and night; tracked NPCs must change scheduled target
  and activity across the day.
- Building variety: the city data must expose many massing profiles, multiple
  house profiles, multiple house roof types, and visible house accessories such
  as porches, garages, chimneys, and wings.
- Random avatar task: the harness chooses a random destination task, asks a
  nearby NPC to take the player there, waits for an escort mission, and verifies
  meaningful player travel plus arrival/completion text.
- Walking route: the harness asks a nearby NPC to walk to a close address,
  verifies the mission stays in walking mode, tracks stable sidewalk route
  samples, keeps the avatar close enough to follow, and confirms clean arrival.
- Runtime cleanliness: browser console errors and page errors must be empty.
- Automatic doors: landmark/procedural building entries expose two sliding
  glass panels; the harness moves the avatar near an entrance, confirms the
  panels open, moves away, and confirms that doorway closes again.
- Interior state and floors: the harness places the actual avatar rig inside a
  multi-floor building, confirms the HUD switches to that building interior,
  tests PageUp/PageDown floor movement, then restores the avatar.
- Interior visual detail: procedural lobbies expose visible directory boards,
  elevator/stair/escalator wayfinding, concierge desks, queue rails, and
  readable central-city directory labels.
- Player physics: the harness jumps with Space and confirms an arc plus gravity
  return, drives the avatar into a blocked building side wall and confirms the
  player cannot clip into the solid footprint, then forces a vehicle-body
  contact and verifies the avatar is pushed clear while HUD impact/stability
  feedback and a collision city event are recorded.
- Responsive performance: the harness opens a mobile-like viewport, checks the
  WebGL canvas pixel sample, verifies core HUD controls stay inside the viewport,
  and confirms key UI text does not overflow or overlap.
- Production deployment: `npm run verify:production` opens
  `https://realcity.vercel.app`, checks the WebGL canvas, minimap GPS, full map,
  direct RealPhone Taxi UI, visible UI text readability, and confirms production
  makes no `/ollama`, `localhost`, `127.0.0.1`, or `0.0.0.0` requests.
- Artifacts: `.verification/realcity-last-run.json` and
  `.verification/realcity-last-run.png` record the last local verification run;
  `.verification/realcity-production-last-run.json` and
  `.verification/realcity-production-last-run.png` record the last production
  smoke run.

## Manual Or Final-Audit Items

- NPC identity visual pass: sample at least 10 agents in the rendered city and
  confirm each distinct data profile is readable at normal street distance.
- Human model readability: confirm player and NPCs have visible front-facing
  face cues, hair/back cues, clothing detail, hands/feet, and readable walking
  direction at street-camera distance beyond the automated metadata check.
- Digital-human source audit: confirm actor metadata reports the
  MakeHuman-style CC0 parametric base, per-agent morph variation, and no copied
  MakeHuman source code or unlicensed external mesh code.
- NPC social life visual pass: observe NPC-to-NPC talks near social places and
  confirm the rendered poses face each other believably, beyond the automated
  event/relationship checks.
- Phone social breadth: sample several different contacts and confirm their
  replies, call text, and resulting action plans stay distinct to their persona.
- Social reactions visual pass: pass close to several standing NPCs and confirm
  the rendered body/head direction reads as a natural glance, beyond the
  automated reaction-state check.
- Traffic norms: step into a lane and confirm nearby drivers brake/yield; taxis
  must be visually distinguishable from private cars.
- Pedestrian norms: observe NPCs near roads and confirm they favor sidewalks,
  plazas, entrances, and crosswalks instead of walking down the middle of a lane.
- Address layer: open the full map and verify landmarks show road-name
  addresses; ask for several taxi routes by landmark name, road-name address,
  and contact location.
- Place meaning: confirm every landmark has a visible form, map point, gameplay
  role, and is reachable by NPC/player movement.
- Procedural city source audit: confirm roads/buildings expose heatmap-growth,
  block-subdivision, public-frontage, and sidewalk-decoration metadata from the
  MIT-compatible city-rule port; AGPL/no-license sources must remain concept-only.
- Landmark interiors: confirm named buildings have solid wall shells, visible
  door openings, a lobby/readable interior, and elevator/stair/escalator props.
- Entry rules: verify the player cannot walk through landmark side/back walls
  and can enter/exit through the front door opening.
- Automatic doors visual pass: confirm the animated glass panels are readable
  from street-camera distance and do not obscure the door opening.
- Interior visual pass: enter several landmark/procedural lobbies and confirm
  floor labels, vertical cores, and interior props read clearly in normal play.
- Entrance routing: request taxi or walking escorts to solid landmarks and
  confirm arrival happens at the entrance apron, not through the side wall or
  building center.
- Daily routine visual pass: observe several named agents over time and confirm
  the visible walking routes match their schedule changes.
- Taxi route: request taxi escorts to at least three distant landmarks and
  confirm boarding, ride, camera visibility after pressing `F`, arrival, and
  mission completion.
- Walking route visual pass: request several different nearby walking escorts
  and confirm the visible route feels natural around crossings and entrances.
- Physics feel visual pass: manually sample jump timing, slopes, collisions with
  vehicles/NPCs, and wall contact so the verified physics also feels natural.
- Performance visual pass: sample desktop and small viewports interactively for
  frame pacing, readable HUD, and no distracting overlap during active play.
- Deployment visual pass: after major interaction changes, manually sample the
  Vercel link for frame pacing and first-person feel beyond the automated
  production smoke checks.
- Local resources: after verification, no leftover Vite dev server, browser, or
  local LLM process should keep consuming noticeable resources.

## Completion Gate

The overall goal should be considered complete only after:

1. All automated checks pass on a clean local run.
2. The Vercel preview is redeployed from the latest commit and opens correctly.
3. The manual/final-audit items above are sampled and any major gaps are either
   fixed or explicitly documented as future scope.
