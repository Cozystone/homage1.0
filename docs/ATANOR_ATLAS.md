# ATANOR Atlas

ATANOR Atlas is the user-facing visualization for Cloud Brain contribution
signals. It shows the ATANOR network as a privacy-preserving regional relay map
centered on the current Seoul Hub.

> ATANOR Atlas is not a surveillance map. It is an anonymous regional
> visualization of Cloud Brain contribution signals.

## What Atlas Shows

- Seoul Hub as the current visual/origin hub.
- A real WebGL Earth rendered with Three.js.
- UTC-based live solar terminator blending day Earth texture with night-light texture.
- Anonymous regional contributor glow points on the globe surface.
- A distinct local "My Node" marker, using coarse public-IP geolocation when
  available and a Seoul fallback when unavailable.
- Orange/gold sync arcs for task, fragment, and heartbeat flow.
- Provider state: `local`, `cloudflare`, `aws`, or `hybrid`.
- Broker state: `local_broker_mode`, `remote_connected`, `remote_error`, or
  `disabled`.
- Time-Zone Relay concept shown through the moving day/night Earth boundary.
- My Node status without exposing device identity.

## Privacy Guarantees

Atlas must not expose:

- Raw IP addresses.
- Exact coordinates.
- Device names.
- User names.
- Local file paths.
- Private Local Brain or Payload Vault records.
- Raw task payloads.

The API response uses only coarse anonymous regional fields:

- `display_id`
- `region_label`
- `country_code`
- `approximate_lat`
- `approximate_lng`
- `jitter_seed`
- `state`
- `activity_level`
- `last_seen_bucket`
- `source`

The current public UI reports `ip_geo_provider = none`. The local node marker
may use a coarse public-IP geolocation provider, but raw IP is never returned to
the UI and coordinates are rounded/coarsened before display.

## Korean Product Statement

ATANOR Atlas는 감시 지도가 아닙니다. Cloud Brain 기여 신호를 지역 단위로
익명 시각화하는 화면입니다.

원시 IP, 정확한 위치, 기기명, 사용자명, 개인 Payload Vault 데이터는 표시하거나
저장하지 않습니다.

## Current Modes

- `local_broker_mode`: local/preview only. The global contributor network is
  not claimed live.
- `remote_connected`: the local runtime is connected to a remote Cloud Brain
  broker.
- `remote_error`: the remote broker could not be reached; Atlas must not fake
  live global state.

## WebGL Earth Assets

Atlas uses local texture assets stored under `apps/web/public/atlas/`:

- `earth_atmos_2048.jpg`
- `earth_lights_2048.png`
- `earth_clouds_1024.png`

These files were sourced from the Three.js example texture set and are bundled
locally so production does not hotlink external image URLs. Before commercial
redistribution, keep a final asset-license audit in the release checklist.

The rendering pipeline itself is Three.js-based and does not expose user
identity, IP address, node identifiers, device names, exact locations, private
Local Brain data, Payload Vault content, or local file paths.

## Future Work

- Add a production-safe coarse geolocation provider.
- Aggregate sparse regions before display.
- Connect real remote contributor regional counts when the production broker
  provides them.
- Preserve the same no-PII response contract when AWS/R2/P2P transport is
  added.
- Replace preview regional points with verified remote contributor aggregates
  only after production broker verification.
