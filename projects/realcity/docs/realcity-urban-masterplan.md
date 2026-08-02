# RealCity Urban Masterplan

This document turns the GPT Image concept board into an implementation guide for the playable procedural city.

Concept board: `/concepts/realcity-masterplan-concept.png`

Implementation blueprint: `src/engine/cityBlueprint.js`

## Design Goal

RealCity should feel like a real playable city, not a random field of towers. The city needs a legible urban structure, meaningful places, daily NPC routes, traffic logic, and a visual hierarchy that works from both the minimap and the third-person street camera.

The current rendering target is a Korean near-future coastal metropolis with a dense core, residential rings, a civic transit spine, an industrial edge, a waterfront boundary, and a green hill backdrop.

## City Form

The city is organized as a ring-and-spine plan.

1. Central Core
   - The first playable area and visual anchor.
   - Contains Central Station, Civic Plaza, and the finance skyline.
   - Has the widest roads, the clearest sidewalks, and the highest pedestrian density.

2. Civic Spine
   - A north-south and east-west pair of major routes crossing through the center.
   - Connects station, hospital, market, school, park, waterfront, and logistics edge.
   - NPC schedules and public transport should favor this spine.

3. Residential Rings
   - Medium-density apartments near the core.
   - Low-density housing toward the outer hills and waterfront.
   - Mixed small retail nodes at transit stops and intersections.

4. Special Districts
   - Market Street: dense storefronts, pedestrians, delivery vans, signs, narrow side streets.
   - Hospital Campus: cleaner blocks, ambulance routes, controlled plaza.
   - School Campus: lower buildings, sports yard, morning/afternoon crowd pulses.
   - Industrial Logistics Zone: large footprints, trucks, warehouses, service roads.
   - North Hill Park: terrain transition, trees, trail paths, skyline viewpoints.
   - Waterfront District: promenade, harbor, lower skyline, reflective water.

## Scale Rules

The first correction target is stable scale. These values should guide the procedural generator:

| Element | Current Target | Design Intent |
| --- | ---: | --- |
| World size | `2400` units | Large enough for city plus surrounding terrain |
| Urban grid half-size | `920` units | Keeps the dense city readable and bounded |
| Local road spacing | `76` units | Roughly one compact urban block |
| Local road width | `11` units | Two-lane local street plus visual shoulder |
| Main road width | `17` units | Boulevard and transit route |
| Central open radius | `170` units | Prevents spawn from feeling crushed |
| Skyscraper height | `44-136` units | Tall but not wall-like from player view |
| Office height | `16-58` units | Mid-rise street canyon |
| Apartment height | `10-34` units | Residential ring scale |
| House height | `4.5-11` units | Outer district scale |

The player should start on a clear road or plaza, with at least one long sightline. Tall buildings can frame the view, but they should not occupy both sides of the camera at spawn.

## Road Hierarchy

Roads should be generated in three visible tiers.

1. Expressway / Ring Road
   - Outer movement and district boundary.
   - Faster traffic, fewer intersections, larger curves.

2. Primary Artery
   - The civic spine and cross-city routes.
   - Visible lane markings, median strips, transit stops, heavier traffic.

3. Local Street
   - Block access, short NPC paths, shops, homes.
   - Narrower road surface and calmer vehicle behavior.

Implementation note: current road meshes already separate road surface from road markings. Keep lane markings as actual geometry for distance readability rather than relying only on texture.

## Street Norms And Addressing

The city should behave like a society with shared rules, not a free-for-all
mesh field.

Current rules:

1. Every road has a virtual road name such as `Station-daero`, `Mirae-ro`, or
   `Garden-ro`.
2. Landmarks and procedural buildings receive road-name addresses such as
   `83 Station-daero`.
3. Taxis and NPC route plans can resolve destination addresses in addition to
   place names; building addresses point to sidewalk frontage, not building
   centers.
4. Trees are filtered out of road reserves so they do not spawn in drive lanes
   or on immediate curb space.
5. NPC pedestrians are pushed out of drive lanes unless they are near an
   intersection/crosswalk zone.
6. The ground layer separates asphalt roads, curb lines, sidewalks, paved
   blocks, crosswalks, and plaza surfaces.
7. Road-name signs, taxi stands, bus stops, traffic lights, bollards, parked
   cars, benches, planters, and storefront details create social street cues.

Long-term final version:

- Add a full pedestrian navigation graph with sidewalks, crossings, station
  concourses, building entrances, floor portals, and inaccessible vehicle lanes.
- Add traffic law states: red lights, pedestrian priority, no-parking zones,
  bus stops, taxi ranks, loading bays, emergency lanes, school zones, and
  one-way streets.
- Expand the address resolver so players can tell a taxi a road-name address,
  landmark alias, business name, floor number, unit, or contact location.
- Add civic services: police/security posts, clinics, schools, transit gates,
  trash pickup, deliveries, street cleaning, events, permits, and closing hours.
- Keep visible layout and rules aligned: if the ground looks like a sidewalk,
  NPCs should use it; if it looks like a road, cars should own it.

## Zoning Map

Suggested coordinate layout for the current procedural world:

| District | Approx Area | Main POI | Visual Character |
| --- | --- | --- | --- |
| Central Core | `radius < 190` | Civic Plaza | open plaza, high visibility, transit signs |
| Financial District | `x > 60, z < 40, radius < 420` | Aster Exchange | glass towers, polished sidewalks |
| Central Station | `x < 0, z around 40` | Central Station | station roof, bus loop, taxi queue |
| Market Ward | `x < -120, z < 180` | Market Lane | dense low/mid-rise storefronts |
| Medical Campus | `x > 170, z < 230` | Hanbit Hospital | clean campus blocks, emergency entry |
| Creative District | `z > 220` | Neon Square | apartments, signs, nightlife color |
| School Campus | `x > 320, z > 260` | Mirae School | low-rise campus and yard |
| North Hill Park | `x < -520, z > 430` | Hill Park | green edge, trails, viewpoint |
| Logistics Edge | `x > 520, z < -480` | South Depot | warehouses, trucks, service yards |
| Waterfront | `z around -980` | South Harbor | harbor, promenade, lower buildings |

## Procedural Block Rules

Each block should have a predictable structure:

1. Reserve road footprint first.
2. Add curb and sidewalk/pavement slabs.
3. Divide buildable area into slots.
4. Place buildings in slots instead of free random offsets.
5. Reserve landmarks and plazas before ordinary buildings.
6. Keep parks, courtyards, and transit plazas as negative space.

This prevents overlapping buildings and avoids the unstable "random city" feeling.

## Visual Layer Stack

The renderer should be organized from stable base layers to dynamic detail:

1. Terrain
   - Flat city floor inside the urban boundary.
   - Hills and natural ground only outside the city.
   - Waterfront on the south edge, not cutting through the spawn zone.

2. Urban Base
   - Road surface.
   - Curbs.
   - Sidewalk and paved blocks.
   - Lane markings as thin mesh geometry.

3. Architecture
   - Procedural massing for all background buildings.
   - External GLB assets for landmarks, transit hubs, vehicles, street furniture, and hero props.
   - Tripo3D prompts can replace temporary landmark geometry.

4. Simulation
   - Traffic.
   - Pedestrians and NPCs.
   - Local LLM agent bubbles and nearby conversations.
   - Weather, cloud movement, time of day.

5. Interface
   - MapLibre minimap from city GeoJSON.
   - Compass.
   - City state panel.
   - RealPhone lower-right smartphone for contacts, NPC messaging, social feed,
     route requests, calls, and music.
   - Nearby agent card and dialogue overlay.

## GPT Image Role

GPT Image is best used as a visual direction tool, not as a literal map source.

Use it for:

- masterplan composition
- district mood references
- street-level camera targets
- landmark silhouettes
- lighting and weather reference
- UI/map presentation style

Do not use it for:

- exact dimensions
- final collision geometry
- authoritative road coordinates
- text labels that must be precise

## External 3D Model Strategy

Use procedural geometry for scale and density, then replace important repeated or landmark assets with GLB models.

Priority assets:

1. Central Station roof and concourse.
2. Bus shelters, streetlights, benches, traffic signals.
3. 6-8 vehicle models with LOD variants.
4. Market stalls and storefront signs.
5. Hospital entrance and ambulance bay.
6. School gate and yard props.
7. Harbor props: cranes, boats, railings.
8. Residential facade modules.

Guideline: keep collision simple. Use box/capsule colliders even when visible GLB geometry is detailed.

## Building Interior Strategy

Buildings should be treated as places with solid envelopes, not just visual props.
The long-term target is that every meaningful building has an entrance, a door
state, an interior zone, and vertical circulation.

Current rules:

1. Ordinary background buildings are solid collision volumes.
2. Landmark buildings expose a front entrance and can only be entered through
   that doorway.
3. Landmark shells include a lobby floor, side/back/front wall segments, a solid
   roof slab, glass door panels, a reception/service counter, and one vertical
   circulation element.
4. Vertical circulation can be an elevator, stair, or escalator depending on the
   place type.
5. Automatic front door panels open when the player approaches the entry axis or
   stands in the lobby.
6. NPC escort and taxi destinations snap to the entrance apron of solid
   landmark buildings instead of the building center.
7. Scheduled NPCs gather at entry aprons for solid landmarks until per-floor
   interior navigation is added, avoiding visual wall clipping around landmarks.
8. Visual meshes may be detailed, but collision should remain simple and
   intentional: solid walls, clear door openings, and separate interior zones.

Long-term final version:

- Add room graphs per building: lobby, corridors, offices, apartments, service
  rooms, stairwells, elevators, shops, restrooms, loading bays, and restricted
  rooms.
- Extend interiors beyond landmarks so apartments, houses, warehouses, schools,
  hospitals, shops, offices, and transit buildings all have authored or
  procedural internal layouts.
- Add door state machines: locked, unlocked, automatic, held open, damaged,
  staff-only, emergency-open.
- Add NPC interior routines: enter building, wait for elevator, go to office,
  meet someone, buy coffee, use stairs during crowding, leave by schedule.
- Add interior navigation mesh and per-floor portals.
- Add elevator, stair, and escalator travel as real state transitions with
  waiting, boarding, riding/climbing, exit choice, and crowd congestion.
- Add procedural interior LOD: nearby interiors are real rooms, distant interiors
  are simulated as aggregate occupancy and window light.
- Connect building access to social rules: reception desks, security, queues,
  visitor permissions, employee-only zones, and closing hours.

## AI NPC City Layer

NPC behavior should be tied to places, not just random movement.

Core place types:

- home
- workplace
- school
- hospital
- market
- cafe
- park
- transit stop
- logistics depot
- civic plaza

Daily routine pattern:

`home -> commute -> work/school -> third place -> errands/social -> home`

Activation model:

| Zone | Behavior |
| --- | --- |
| High-density activation | Nearby NPCs use local LLM dialogue, relationship memory, and reactive movement |
| Medium-density activation | NPCs run schedules and short templated exchanges |
| Low-density activation | NPCs are simulated as aggregate counts and route events |

This keeps the city feeling alive without trying to run a full LLM for every citizen every frame.

## Human Rendering Strategy

The visual target is not abstract pedestrians. People should read as citizens
with a front, back, body direction, clothing, and recognizable social presence.

Current rules:

1. The player avatar has a modeled face with eyes, nose, mouth, ears, hair cap,
   back hair mass, chest panel, hands, and shoes so movement direction is clear.
2. NPCs remain instanced for performance, but include face parts, chest panels,
   shoes, skin-tone variation, hair-tone variation, and bags.
3. Face parts are placed on the local forward side of the head so glances and
   turns have a visible direction.
4. Clothing color still reflects NPC role/personality, while small front details
   make the body orientation readable from street-camera distance.

Long-term final version:

- Replace hero pedestrians and nearby interactable NPCs with optimized GLB/VRM
  character assets, with LOD fallback to the current instanced human system.
- Add facial expressions, blinking, gaze targets, head turns, hand gestures,
  phone-holding, sitting, leaning, and taxi boarding animations.
- Use role-aware outfit sets: hospital staff, students, transit staff, couriers,
  office workers, market vendors, security, tourists, and residents.
- Add skeletal animation blending for idle, walk, jog, talk, wave, point, enter
  vehicle, sit, use phone, open door, and wait for elevator.
- Keep collision simple with capsule bodies even when visual characters are
  detailed.

## RealPhone Layer

The phone is the persistent diegetic UI for joining the city socially. It should
feel like a real device the player carries, not a detached settings menu.

Current rules:

1. The phone sits in the lower-right HUD and opens as an iPhone-like device.
2. Contacts are generated from known NPC identities and relationship scores.
3. Messages can be sent to contacts; route-like requests are forwarded into the
   NPC action system so contacted agents can plan walking or taxi actions.
4. Calls surface the selected NPC as an in-world dialogue response.
5. The social feed shows NPC status, place, and relationship context.
6. The music app can play simple generated ambient tones without requiring
   external audio files.

Long-term final version:

- Persist contacts, message history, social affinity, call logs, blocked
  contacts, and discovered profiles.
- Let NPCs proactively message the player based on relationships, emergencies,
  jobs, rumors, events, and schedule changes.
- Connect phone location sharing to taxi dispatch, meetups, navigation pins, and
  building entrances.
- Add apps for city map, bank/payment, transit, taxi, camera, photos, news,
  tasks, marketplace, and emergency services.
- Use local LLM memory per contact so each NPC's phone style, response time,
  boundaries, and willingness to help match their personality and current life.

## Implementation Priorities

1. Lock the urban form.
   - Core plaza.
   - Ring road.
   - Civic spine.
   - District boundaries.
   - Keep district and landmark definitions centralized in `cityBlueprint.js`.

2. Replace placeholder landmarks.
   - Start with Central Station, Aster Exchange, Hospital, Market Lane.

3. Improve street-level scale.
   - Curbs, sidewalks, lanes, crossings, signals.
   - More human-scale street props before adding more towers.

4. Connect simulation to district meaning.
   - NPC route heatmaps.
   - Traffic density per district.
   - Time-based activity pulses.

5. Add visualization modes.
   - In-game normal view.
   - Planning overlay.
   - District debug overlay.
   - NPC routine heatmap.
   - Traffic flow overlay.

## Acceptance Checklist

The city design is working when:

- The player immediately understands where the road, sidewalk, plaza, and buildings are.
- The first camera view has a stable scale reference.
- The minimap and 3D world describe the same districts.
- Each named POI has a purpose in NPC schedules.
- The skyline has height gradients instead of uniform walls.
- Natural terrain is outside the urban floor, not mixed into the asphalt city base.
- Traffic and NPC flows visibly prefer the civic spine and transit nodes.
- External models enhance landmarks without breaking performance or collision.
- Landmark walls are solid, and entry is possible only through visible doors.
- Important buildings have at least a basic lobby plus elevator, stair, or
  escalator concept.
