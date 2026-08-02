# ATANOR General And Operator UI QA

## Source Visual Truth
- General app reference: `UI/KakaoTalk_20260614_123616792.jpg`
- Premium dashboard references:
  - `UI/ChatGPT Image 2026??6??14???ㅼ쟾 11_01_48.png`
  - `UI/ChatGPT Image 2026??6??14???ㅼ쟾 11_02_04.png`

## Implementation Screenshots
- Home, 1600px final: `UI/atanor-home-service-polish-1600-final-ko.png`
- Home, icon polish final: `UI/atanor-home-icons-final-ko.png`
- Home, graph overlay final: `UI/atanor-home-graph-layer-live-final-ko.png`
- Home, 1280px responsive final: `UI/atanor-home-responsive-1280-final-ko.png`
- Ontology split view: `UI/atanor-ontology-split-polish-1600-ko.png`
- Operator console: `UI/atanor-operator-console-refactor-ko.png`
- User settings screen: `UI/atanor-settings-operator-separation-ko.png`
- Operator separated command surface: `UI/atanor-operator-separated-final-ko.png`

## Viewport And State
- Desktop comparison: `1600x900`
- Responsive check: `1280x720`
- Route: `http://127.0.0.1:3022/?lang=ko&workspace=lab`
- Operator route: `http://127.0.0.1:3022/admin?lang=ko`
- Local companion: connected
- Live graph: `1,163 nodes / 6,590 relations`

## Findings
- No P0/P1/P2 blockers remain for this pass.
- P3: The home graph remains denser than the visual mock because it renders the real live memory graph rather than a small illustrative sample.
- P3: The graph card is intentionally darker and more operational than the mock to preserve ATANOR's black/neon product identity.

## Patches Made Since Previous Pass
- General app home graph now uses a lighter representative edge sample for the studio projection, while preserving real stored node and relation counts.
- Home graph camera fit now leaves more margin so the live graph does not clip in narrower desktop windows.
- Home and Cloud graph stages now fill their cards instead of leaving an empty lower black band when the right rail is taller.
- Verified Local Brain remains chat-capable with one textarea.
- Verified Cloud Brain remains viewer-only with zero textareas.
- Verified Ontology Graph uses the requested split UI: chat on the left, graph in the center, telemetry on the right.
- Verified Operator remains separate from general ATANOR and labels the graph as Cloud Brain command/knowledge graph rather than Local Brain.
- Sidebar section controls now use line icons instead of letter abbreviations.
- Top actions now include a compact graph-settled status badge while preserving the working Sync button.
- Graph viewport now includes a compact in-canvas legend, central ATANOR anchor label, and interaction hint matching the reference dashboard behavior.
- Default route without `lang` now opens in English. Korean preview remains available with `?lang=ko`.
- Added a dedicated Settings screen for the general ATANOR app so language, local Companion URL, web assist, contribution safety, CPU limit, sync, learning start, and checkpoint controls no longer fall through to a graph view.
- Operator sidebar and header now explicitly identify the build as `ATANOR Operator / OPERATOR ONLY`; the screen declares that it is a private Cloud Brain command surface, not the general user app.
- Operator startup now schedules a retry sync so the Cloud Brain graph no longer remains in a transient `0 nodes / 0 relations` waiting state after first load.

## Browser Verification
- `npm --workspace apps/web run build`: passed.
- Home 1600px console errors: `0`.
- Home 1280px console errors: `0`.
- Ontology split console errors: `0`.
- Local/Cloud tab behavior console errors: `0`.
- 1280px horizontal overflow: `false`.
- Icon polish browser check:
  - All sidebar nav items render SVG line icons.
  - Home graph settled badge renders as `洹몃옒???덉젙??.
  - Sync button remains clickable and reloads live data without console errors.
  - Quick action `????? still opens Local Brain chat.
- Graph overlay browser check:
  - In-canvas legend rendered: Local Brain Node / Cloud Brain Node / Cloud Fragment / strong relation.
  - Center anchor rendered: `ATANOR / Anchor`.
  - Interaction hint rendered: drag, scroll, node selection.
  - Korean preview with live graph rendered `1,163 nodes / 6,590 relations`.
  - Default URL without `lang` rendered English copy.
- Settings screen browser check:
  - Korean preview rendered `ATANOR ?ㅽ뻾 ?섍꼍`, `?몄뼱? ?쒖떆`, `濡쒖뺄 Companion`, `湲곗뿬 ?덉쟾?μ튂`, and `吏꾨떒怨??좎?愿由?.
  - Settings controls rendered six inputs: web assist, backend URL, safe mode, public fragment jobs, local data sharing, and CPU range.
  - Settings screen rendered zero chat textareas as expected.
- Operator separation browser check:
  - `/admin?lang=ko` rendered `ATANOR Operator`, `OPERATOR ONLY`, and the private operator boundary sentence.
  - Operator graph title rendered `?대씪?곕뱶 釉뚮젅??吏??洹몃옒??; old `濡쒖뺄 釉뚮젅??吏??洹몃옒?? title was absent.
  - Initial load after retry rendered `1,163 nodes / 6,590 relations` without requiring manual Sync.

## Final Result
passed

## 2026-06-14 Local / Cloud / Dual Presentation Split
- Build verification: `npm --workspace apps/web run build` passed after the presentation split.
- New screenshots:
  - Home dual overview: `UI/atanor-home-dual-final-ko.png`
  - Local private memory: `UI/atanor-local-private-final-ko.png`
  - Cloud public ontology: `UI/atanor-cloud-public-final-ko.png`
  - Dual fusion graph: `UI/atanor-dual-fusion-final-ko.png`
  - Operator Cloud Brain control: `UI/atanor-operator-cloud-control-final-ko.png`
- General app browser checks at `http://127.0.0.1:3022/?lang=ko&workspace=lab`:
  - Home graph uses `home_unified_overview`; no horizontal overflow.
  - Local Brain uses `local_private_memory`, title `濡쒖뺄 釉뚮젅??媛쒖씤 硫붾え由?, one chat textarea, and Local-only routing copy.
  - Cloud Brain uses `cloud_world_knowledge`, title `?대씪?곕뱶 釉뚮젅??怨듭슜 ?⑦넧濡쒖?`, zero chat textareas, and Cloud Brain 100% status copy.
  - Ontology Graph uses `unified_projection`, title `???釉뚮젅???듯빀 洹몃옒??, one chat textarea, and unified local/cloud source-layer status rows.
- Operator browser checks at `http://127.0.0.1:3022/admin?lang=ko`:
  - Operator title remains `ATANOR Operator`.
  - The active task panel now reads `?대씪?곕뱶 釉뚮젅???쒖뼱 / ?대씪?곕뱶 釉뚮젅??/ 100%`.
  - `Local 96%`, `96% local`, and similar active-work ratio copy are absent from the operator surface.
  - Live graph still renders `1,163 nodes / 6,590 relations`.
- Full desktop verification:
  - The Codex in-app browser panel is fixed near `788x791`, so it shows the responsive compact layout.
  - A separate Chromium verification was run at `1600x900`.
  - Desktop screenshots:
    - `UI/atanor-home-dual-final-1600-real-ko.png`
    - `UI/atanor-local-private-final-1600-real-ko.png`
    - `UI/atanor-cloud-public-final-1600-real-ko.png`
  - `1600x900` checks: no horizontal overflow; Home uses `home_unified_overview`; Local uses `local_private_memory` with one chat textarea; Cloud uses `cloud_world_knowledge` with zero chat textareas.
- 2026-06-14 ontology split refinement:
  - Source reference: `UI/KakaoTalk_20260614_123616792.jpg`
  - Implementation screenshot: `UI/atanor-ontology-split-refined-live-1600-ko.png`
  - Viewport/state: `1600x900`, Korean preview, `?⑦넧濡쒖? 洹몃옒?? / Unified Brain active.
  - Patch summary: added the reference-style left guide block, replaced the ontology right rail with `Brain Routing`, `Epistemic State`, and `Selected Memory`, and compacted graph metrics inside the graph card.
  - Live graph evidence: `1,163 nodes / 6,590 relations` rendered after waiting for live sync.
  - Interaction checks:
    - Default URL without `lang` opens with English active.
    - Korean toggle works.
    - Home `洹몃옒???먯깋` opens the ontology graph split view.
    - Home `????? opens Local Brain with one chat textarea.
    - Home `硫붾え由?寃?? opens Local Brain with one chat textarea.
- Console notes: no application runtime errors observed; headless Chromium emitted only WebGL software-rendering/performance warnings.
- Remaining P3: the live graph is intentionally denser and less illustrative than the reference mock because it renders the real ATANOR graph rather than a hand-curated mini diagram.

## 2026-06-14 Fullscreen Korean Service UI Refinement
- Source intent: make the user app closer to the provided ATANOR dashboard references while preserving the real live graph.
- Build verification: `npm --workspace apps/web run build` passed.
- Browser route: `http://127.0.0.1:3022/?lang=ko&workspace=lab`.
- Viewport verification: `1920x1080` through the in-app browser viewport override.
- UI patches:
  - Sidebar reduced to `??쒕낫??/ 梨꾪똿 / 硫붾え由?洹몃옒??/ 湲곗뿬 / ?ㅼ젙`.
  - Home view keeps chat hidden and marks `???釉뚮젅?? as the active top brain tab.
  - Graph controls render `- / + / 珥덇린?? in Korean.
  - Ontology right rail headings render as `釉뚮젅???쇱슦??/ ?몄떇 ?곹깭 / ?좏깮 硫붾え由?.
  - Right-rail cards were compacted to better match the premium reference panel density.
  - Graph activation spread was reduced so the real graph does not become a full orange mass; inactive memory remains colder and active paths glow locally.
- Interaction checks:
  - Home: no chat textarea, right rail has `?쒖뒪???곹깭 / ?쒖꽦 ?묒뾽 / 鍮좊Ⅸ ?ㅽ뻾`.
  - Chat quick action: opens Local Brain with one chat textarea.
  - Graph quick action: opens Memory Graph with one chat textarea and `???釉뚮젅?? active.
  - Local Brain tab: one chat textarea, no right rail.
  - Cloud Brain tab: zero chat textareas, read-only right rail.
  - Language toggle EN -> KO works and returns to Korean preview.
  - Graph `-`, `+`, and `珥덇린?? buttons click without runtime errors.
- Console result: no browser console errors observed during the verification pass.
- Remaining P3: browser screenshot capture can time out on the WebGL canvas, so this pass relies on DOM/runtime verification rather than a new side-by-side screenshot artifact.

## 2026-06-14 Settings And Contribution Copy Integrity Pass
- Build verification: `npm --workspace apps/web run build` passed.
- Browser route: `http://127.0.0.1:3022/?lang=ko&workspace=lab`.
- Viewport verification: `1920x1080`.
- Copy integrity:
  - `rg` scan found no remaining mojibake markers in `apps/web/app/page.tsx`, `apps/web/app/globals.css`, or `apps/web/app/Rag3DScene.tsx`.
  - Settings headings rendered cleanly: `ATANOR ?ㅽ뻾 ?섍꼍`, `?몄뼱? ?쒖떆`, `濡쒖뺄 Companion`, `湲곗뿬 ?덉쟾?μ튂`, `吏꾨떒怨??좎?愿由?.
  - Contribution headings rendered cleanly: `湲곗뿬 ?쇱슦??, `?좏깮???묒뾽`, `湲곗뿬 ?щ젅??, `?덉쟾 諛?媛쒖씤?뺣낫`, `怨좉툒 ?먯썝 ?ㅼ젙`, `湲곗뿬 媛?ν븳 ?묒뾽`, `?ㅼ떆媛??묐룞 濡쒓렇`, `?ν썑 ?좏겙??濡쒕뱶留?.
- Interaction checks:
  - Settings rendered eight expected controls/buttons: `English`, `?쒓뎅??, `?ъ뿰寃?, `湲곕낯媛?, `?댁젣`, `?숆린??, `?숈뒿 ?쒖옉`, `泥댄겕?ъ씤??.
  - Contribution rendered active action buttons `湲곗뿬 媛깆떊` and `?덉쟾 議곌굔 ?湲?.
  - Settings rendered six inputs; Contribution rendered five inputs.
  - Console result: no browser console errors observed.
- Final result for this pass: passed.

## 2026-06-14 Fullscreen Topbar And Graph Control Pass
- Build verification: `npm --workspace apps/web run build` passed.
- Preview server: restarted `http://127.0.0.1:3022` from the latest production build.
- Browser route: `http://127.0.0.1:3022/?lang=ko&workspace=lab`.
- Viewport verification: `1920x1080`.
- UI patches:
  - Added functional top-right notification and profile icon buttons to match the premium ATANOR reference structure.
  - Notification icon runs the same live sync action as the Sync button.
  - Profile icon opens Settings and correctly displays its active state.
  - Topbar clock now uses a subtle divider to match the reference header rhythm.
  - Graph base edge color and activation spread were toned down so the graph reads as a cold semantic field, with orange reserved for local activation.
  - Graph control layer z-index and pointer events were strengthened so the canvas no longer competes with the control buttons.
- Interaction checks:
  - Profile icon opens `settings`; active state becomes `true`.
  - Notification icon runs without console errors.
  - Main navigation works:
    - `硫붾え由?洹몃옒??: one chat textarea and right rail visible.
    - `濡쒖뺄 釉뚮젅??: one chat textarea and no right rail.
    - `?대씪?곕뱶 釉뚮젅??: zero textareas and read-only right rail visible.
    - `??쒕낫??: zero textareas and viewer-focused home graph.
  - Graph controls now mutate the live 3D camera:
    - Zoom out: `cameraZ 23.5 -> 27.7`.
    - Zoom in: `cameraZ 27.7 -> 22.7`.
    - Reset emits `lastControlAction=reset`.
  - Home preview after verification: Korean, `home`, `1163` graph nodes, `idle`, zero chat textareas.
- Console result: no browser console errors observed.
- Screenshot note: in-app browser screenshot capture still times out on the WebGL canvas, so this pass uses DOM/runtime verification.
- Final result for this pass: passed.

## 2026-06-14 True Fullscreen Verification Pass
- User correction: QA must be judged from a fullscreen-sized browser, not from a small foreground window.
- Build verification: `npm --workspace apps/web run build` passed.
- Preview server: restarted `http://127.0.0.1:3022` from the latest production build.
- Browser route: `http://127.0.0.1:3022/?lang=ko&workspace=lab`.
- Viewport verification: explicit `1920x1080`.
- Runtime result:
  - `window.innerWidth=1920`, `window.innerHeight=1080`.
  - `documentElement.scrollHeight=1080`, `scrollWidth=1920`; no layout overflow in the verified browser.
  - Console errors/warnings: none.
  - ATANOR logo image loaded: `1047x1047`.
  - User-facing error banners: none in the verified browser.
  - Graph controls are separated and clickable: `-`, `+`, `珥덇린??.
- UI patches in this pass:
  - Moved the graph state pill from the lower-right control area to the upper-right graph area.
  - Made graph control buttons fixed-size inline-flex buttons so Korean labels do not collide.
  - Converted raw `Failed to fetch` layout text into a non-blocking sync toast with sanitized user copy.
- Screenshot notes:
  - OS-level Chrome captures can include stale foreground Chrome windows and cached bundles, so they are not treated as the final source of truth for this pass.
  - In-app WebGL screenshot capture still times out; DOM/runtime verification is clean.
- Final result for this pass: passed.

