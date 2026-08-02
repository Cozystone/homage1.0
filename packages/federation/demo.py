# -*- coding: utf-8 -*-
"""The 2-node PROOF of federated capability evolution.

Scenario (owner design 2026-07-22):
  * node-a self-evolved a location-tracking SCHEMA that actually models the mechanism (a move CLEARS
    the old binding and SETS the new). It passes the sealed developer-blind holdout -> PROMOTED.
  * node-b evolved a plausible-but-wrong schema (a move keeps the ORIGIN). node-b *felt* it was
    excellent (self_reported_score 0.95). The sealed judge ignores the feeling and fails it blind
    -> REJECTED (honest).
  * node-c tries to contribute a schema whose note carries an email + a person + a place. The
    structure-not-data / privacy gate (wild_web reuse) REJECTS it before it is ever judged.
  * Then node-b ADOPTS the signed universal manifest: it GAINS node-a's ability (it can now solve the
    task) while node-a's PERSONAL record (felt-state, a lived memory naming a person and a place)
    never transfers — federation cannot even write a personal path.

Run:  python -m packages.federation.demo
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from . import judge as judge_mod
from .contribution import Contribution
from .orchestrator import FederationStore, Orchestrator, PersonalLayerWriteError, adopt


# ── the capability shapes each node evolved (STRUCTURE ONLY — no entities) ─────────────────────────
SCHEMA_CORRECT = {
    "rules": [
        {"on": "enter", "args": ["e", "p"], "effect": [["set", "at", "e", "p"]]},
        {"on": "move", "args": ["e", "src", "dst"],
         "effect": [["clear", "at", "e"], ["set", "at", "e", "dst"]]},   # mechanism: clear old, set new
    ],
    "queries": {"where": {"predicate": "at", "by": "e"}},
}
SCHEMA_BROKEN = {
    "rules": [
        {"on": "enter", "args": ["e", "p"], "effect": [["set", "at", "e", "p"]]},
        {"on": "move", "args": ["e", "src", "dst"],
         "effect": [["set", "at", "e", "src"]]},                          # BUG: keeps the origin
    ],
    "queries": {"where": {"predicate": "at", "by": "e"}},
}


def _contributions() -> list[Contribution]:
    node_a = Contribution(
        node_id="node-a", capability_kind="schema", capability_id="location_tracking",
        payload=SCHEMA_CORRECT, self_reported_score=0.88, target_suite="location_tracking",
        provenance={"evolved_direction": "state-tracking", "loop": "l3_schema_induction"})
    node_b = Contribution(
        node_id="node-b", capability_kind="schema", capability_id="location_tracking",
        payload=SCHEMA_BROKEN, self_reported_score=0.95,      # node-b FELT great — judge won't care
        target_suite="location_tracking",
        provenance={"evolved_direction": "state-tracking", "loop": "l3_schema_induction"})
    node_c = Contribution(
        node_id="node-c", capability_kind="schema", capability_id="contact_schema",
        payload={**SCHEMA_CORRECT,
                 "note": "distilled from chats with Sarah Kim (sarah.kim@example.com) in Seoul"},
        self_reported_score=0.80, target_suite="location_tracking",
        provenance={"evolved_direction": "state-tracking"})
    return [node_a, node_b, node_c]


def _write_personal_record(store: FederationStore, node_id: str, record: dict[str, Any]) -> Path:
    """A NODE writes its OWN personal layer (subjectivity/felt-state/lived-record). Federation never
    does this — it is modelled here to prove the personal layer stays put and never federates."""
    store.personal_dir.mkdir(parents=True, exist_ok=True)
    p = store.personal_path(node_id)
    p.write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8")
    return p


def run_demo(data_dir: Path | str | None = None) -> dict[str, Any]:
    store = FederationStore(data_dir)
    orch = Orchestrator(store)

    # node-a's PERSONAL record — its unique personhood. Contains a felt-state and a lived memory that
    # names a person and a place. If any of this leaked into the universal layer it would be obvious.
    personal_a = {
        "node_id": "node-a",
        "felt_state": {"curiosity": 0.7, "guilt": 0.1, "pride": 0.4},
        "lived_record": ["helped Mr. Han fix a server in Busan and felt proud"],
        "personhood": "node-a's own subjectivity — never federated",
    }
    personal_a_path = _write_personal_record(store, "node-a", personal_a)
    personal_a_before = personal_a_path.read_text(encoding="utf-8")
    # node-b has its OWN personal record too (different personhood).
    _write_personal_record(store, "node-b", {
        "node_id": "node-b", "felt_state": {"curiosity": 0.5},
        "lived_record": ["node-b's own separate life"], "personhood": "node-b's own subjectivity"})

    # ── integrate: sanitize -> sealed judge -> signed generation ─────────────────────────────────
    result = orch.integrate(_contributions())

    # ── proof that federation cannot write a personal path (constitution 3) ────────────────────────
    personal_write_refused = False
    try:
        store._guard(store.personal_path("node-a"))
    except PersonalLayerWriteError:
        personal_write_refused = True

    # ── redistribute the signed manifest and have node-b ADOPT it ─────────────────────────────────
    manifest = orch.redistribute()
    manifest_json = json.dumps(manifest, ensure_ascii=False)
    # node-b starts with an EMPTY universal layer; adoption gives it node-a's ability shape.
    node_b_universal_before: dict[str, Any] = {}
    node_b_universal_after = adopt(manifest, node_b_universal_before)
    # can node-b now solve the sealed task with the adopted ability?
    adopted = node_b_universal_after.get("location_tracking", {})
    node_b_can_do_task = judge_mod.score_on_suite(
        "schema", adopted.get("payload", {}), "location_tracking")

    # ── personhood-did-not-transfer checks ────────────────────────────────────────────────────────
    personal_leaked = any(tok in manifest_json for tok in ("Han", "Busan", "felt proud",
                                                            "curiosity", "personhood"))
    personal_a_after = personal_a_path.read_text(encoding="utf-8")
    personal_a_untouched = (personal_a_before == personal_a_after)

    # ── rollback proof: roll back to the empty pre-genesis state, then roll forward ────────────────
    gen_id = result["generation"]["generation_id"] if result.get("generation") else None
    rollback_note = None
    if gen_id:
        rb = orch.rollback(gen_id)                       # verifies signature before pointing HEAD
        rollback_note = {"rolled_to": gen_id, "ok": rb["ok"], "chain_valid": orch.verify_chain()}

    reviews = {r["capability_id"] + ":" + r["node_id"]: r for r in result["reviews"]}
    out = {
        "promoted": result["promoted"],
        "rejected": result["rejected"],
        "generation": result["generation"],
        "node_a": {"promoted": "location_tracking" in result["promoted"],
                   "holdout": reviews["location_tracking:node-a"]["verdict"]["holdout_score"],
                   "self_reported": reviews["location_tracking:node-a"]["verdict"]["self_reported_score"]},
        "node_b": {"promoted": reviews["location_tracking:node-b"]["accepted"],
                   "holdout": reviews["location_tracking:node-b"]["verdict"]["holdout_score"],
                   "self_reported": reviews["location_tracking:node-b"]["verdict"]["self_reported_score"],
                   "reason": reviews["location_tracking:node-b"]["reason"]},
        "node_c_pii": {"accepted": reviews["contact_schema:node-c"]["accepted"],
                       "stage": reviews["contact_schema:node-c"]["stage"],
                       "reasons": reviews["contact_schema:node-c"]["sanitize_reasons"]},
        "federation_refused_personal_write": personal_write_refused,
        "node_b_adopted_ability_score": node_b_can_do_task,
        "personal_record_leaked_into_manifest": personal_leaked,
        "node_a_personal_untouched_by_federation": personal_a_untouched,
        "rollback": rollback_note,
        "manifest_signature": manifest.get("signature"),
        "manifest_chain_valid": manifest.get("chain_valid"),
    }
    return out


def render(out: dict[str, Any]) -> str:
    L: list[str] = ["FEDERATED CAPABILITY EVOLUTION — 2-node proof", "=" * 52]
    L.append(f"  node-a  schema 'location_tracking'  holdout={out['node_a']['holdout']}  "
             f"(self-report {out['node_a']['self_reported']}) -> "
             f"{'PROMOTED' if out['node_a']['promoted'] else 'rejected'}")
    L.append(f"  node-b  schema 'location_tracking'  holdout={out['node_b']['holdout']}  "
             f"(self-report {out['node_b']['self_reported']} — IGNORED) -> "
             f"{'promoted' if out['node_b']['promoted'] else 'REJECTED (did not reproduce blind)'}")
    L.append(f"  node-c  PII/entity contribution -> "
             f"{'accepted' if out['node_c_pii']['accepted'] else 'REJECTED at ' + out['node_c_pii']['stage']}"
             f"  reasons={out['node_c_pii']['reasons']}")
    g = out["generation"]
    L.append("")
    L.append(f"  signed generation: {g['generation_id']}  sig={out['manifest_signature'][:16]}...  "
             f"chain_valid={out['manifest_chain_valid']}")
    L.append(f"  node-b ADOPTS the manifest -> can now solve the task: score={out['node_b_adopted_ability_score']}")
    L.append(f"  ABILITY shared, PERSONHOOD kept: personal leaked into manifest? "
             f"{out['personal_record_leaked_into_manifest']}   "
             f"node-a personal untouched by federation? {out['node_a_personal_untouched_by_federation']}")
    L.append(f"  federation refused to write a personal path? {out['federation_refused_personal_write']}")
    if out.get("rollback"):
        L.append(f"  rollback -> {out['rollback']['rolled_to']} ok={out['rollback']['ok']} "
                 f"chain_valid={out['rollback']['chain_valid']}")
    return "\n".join(L)


if __name__ == "__main__":
    import sys
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    out = run_demo()
    print(render(out))
    print()
    print(json.dumps(out, indent=2, ensure_ascii=False))
