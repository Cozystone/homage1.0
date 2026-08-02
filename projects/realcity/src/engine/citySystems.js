// City systems bootstrap — single mount point for the CT-track world systems (2026-07-21).
// Each module is a SELF-DRIVING side-effect module: it starts its own interval loop, waits for
// window.__REALCITY_CITY__ to exist, then attaches live state to BOTH window.__REALCITY_<NAME>__
// and city.systems.<name>. No module imports another — cross-talk goes through those globals and
// window CustomEvents, so the modules can be built/replaced independently.
//
// CONTRACTS (all modules follow these exactly):
//  clock      -> city.systems.clock   = { simMinutes, hour, minute, phase:'dawn'|'day'|'dusk'|'night',
//                                         timeLabel, sunAngle }            (+ __REALCITY_TIME__)
//  weather    -> city.systems.weather = { state:'clear'|'cloudy'|'rain'|'storm'|'fog'|'snow',
//                                         intensity:0..1, wet:0..1,
//                                         factors:{ walkSpeed, taxiDemand, shelter } }
//  norms      -> __REALCITY_NORMS__   = { list(), add(n), renameBuilding(id,name), setRule(r),
//                                         applyFromAtanor(edit) }  — localStorage-persisted
//  perception -> __REALCITY_PERCEPTION__ = { perceive(agent, city, opts?) } — FOV-limited senses:
//                { seen:[{id,name,kind,dist}], heard:[{kind,dist}], felt:{weather,phase,crowding} }
//  economy    -> __REALCITY_ECON__    = { wallets, shops, buy(agentId,shopId,item), audit() }
//  civic      -> __REALCITY_CIVIC__   = { buses, incidents, report(kind,at), streetlights }
//  ambient    -> __REALCITY_AUDIO__   = { enabled, unlock() } — procedural WebAudio, gesture-gated
//  atanorLink -> polls ATANOR :8502 for city edits + drives ambassador actions; dispatches
//                CustomEvent('realcity:avatar-action', { detail:{ agentId, animation, duration } })
//
// Avatar animation contract (Actors.jsx): listens for 'realcity:avatar-action' and exposes
// window.__REALCITY_AVATAR__ = { play(agentId, animation, duration) }.
import './cityClock'
import './weather'
import './norms'
import './perception'
import './economy'
import './civic'
import './ambientAudio'
import './atanorLink'
// wave 2 — life patterns by the clock, population brain mix, doctrine-gated dialogue observation
import './lifePatterns'
import './populationMix'
import './dialogueEavesdrop'
import './roamRights'
import './roleLife'
